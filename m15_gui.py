#!/usr/bin/env python3
"""Tkinter GUI for the M15 ROM collection manager.

A thin front-end over the manager, restore, and backup-pruning APIs:

    gamelist_manager.py
    restore_gamelist.py
    delete_gamelist_backups.py

The GUI calls their ``Options``/``run()`` or ``main()`` functions directly on a
background thread and streams output into a log window. It does not patch
``sys.argv``, ``sys.stdout``, or the process working directory.

Standard library only (tkinter), Python 3.9+.
"""

from __future__ import annotations

import io
import os
import queue
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import gamelist_manager
import restore_gamelist
import delete_gamelist_backups

SYSTEMS = gamelist_manager.SYSTEMS
ALL_SYSTEMS = "All systems"


def app_base_dir() -> Path:
    """Where the app lives, or the cwd when frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    """Locate a bundled data file both in source and in a frozen build."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidate = Path(bundle) / name
        if candidate.is_file():
            return candidate
    return app_base_dir() / name


def looks_like_rom_root(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
    except OSError:
        return False
    if not (path / "root.dat").is_file():
        return False
    return any((path / name).is_dir() for name in SYSTEMS)


def detect_rom_roots() -> list:
    """Best-effort guesses at the ROM root folder."""
    candidates = [app_base_dir()]
    volumes = Path("/Volumes")
    if volumes.is_dir():
        try:
            for drive in volumes.iterdir():
                if drive.name.startswith("."):
                    continue
                candidates.append(drive)
                candidates.append(drive / "roms")
                try:
                    for child in drive.iterdir():
                        if child.is_dir():
                            candidates.append(child)
                except OSError:
                    pass
        except OSError:
            pass
    found = []
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if looks_like_rom_root(candidate):
            found.append(str(candidate))
    return found


class QueueWriter(io.TextIOBase):
    """A file-like object that forwards writes to a queue."""

    def __init__(self, sink: queue.Queue):
        self.sink = sink

    def write(self, text):
        if text:
            self.sink.put(("out", text))
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False

    def writable(self):
        return True


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.preview = False

        root.title("M15 ROM Manager")
        root.minsize(820, 620)

        self._build_widgets()
        self._autodetect(quiet=True)

    # ---------------------------------------------------------------- layout

    def _build_widgets(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        self._build_location(outer)
        self._build_options(outer)
        self._build_actions(outer)
        self._build_log(outer)
        self._build_status(outer)

    def _build_location(self, parent):
        box = ttk.LabelFrame(parent, text="Collection folder", padding=8)
        box.pack(fill="x")

        self.root_var = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.root_var)
        entry.pack(side="left", fill="x", expand=True)

        ttk.Button(box, text="Browse...", command=self.browse_root).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(box, text="Auto-detect", command=self._autodetect).pack(
            side="left", padx=(6, 0)
        )

        self.root_hint = ttk.Label(
            parent, foreground="#b06", text="", wraplength=760, justify="left"
        )
        self.root_hint.pack(fill="x", pady=(4, 0))

    def _build_options(self, parent):
        box = ttk.LabelFrame(parent, text="Options", padding=8)
        box.pack(fill="x", pady=(10, 0))

        self.system_var = tk.StringVar(value=ALL_SYSTEMS)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="System:").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.system_var,
            state="readonly",
            width=18,
            values=[ALL_SYSTEMS] + sorted(SYSTEMS),
        ).pack(side="left", padx=(6, 0))

        ttk.Label(row, text="Deduplicate:").pack(side="left", padx=(18, 0))
        self.dedup_var = tk.StringVar(value="both")
        ttk.Combobox(
            row,
            textvariable=self.dedup_var,
            state="readonly",
            width=10,
            values=["none", "path", "gameid", "both"],
        ).pack(side="left", padx=(6, 0))

        ttk.Label(row, text="XML declaration:").pack(side="left", padx=(18, 0))
        self.decl_var = tk.StringVar(value="et")
        ttk.Combobox(
            row,
            textvariable=self.decl_var,
            state="readonly",
            width=8,
            values=["et", "double"],
        ).pack(side="left", padx=(6, 0))

        switches = ttk.Frame(box)
        switches.pack(fill="x", pady=(8, 0))

        self.remove_missing_var = tk.BooleanVar(value=True)
        self.add_var = tk.BooleanVar(value=True)
        self.ids_var = tk.BooleanVar(value=True)
        self.normalize_var = tk.BooleanVar(value=True)
        self.sort_var = tk.BooleanVar(value=True)
        self.indent_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.orphans_var = tk.BooleanVar(value=False)

        def boxed(text, var, hint, column, row=0):
            frame = ttk.Frame(switches)
            frame.grid(row=row, column=column, sticky="w", padx=(0, 22), pady=2)
            ttk.Checkbutton(frame, text=text, variable=var).pack(anchor="w")
            ttk.Label(frame, text=hint, foreground="#666").pack(anchor="w")

        boxed("Remove missing ROM entries", self.remove_missing_var,
              "Uncheck to keep broken entries", 0)
        boxed("Add newly found ROMs", self.add_var,
              "Uncheck to only clean up", 1)
        boxed("Add missing <gameid>", self.ids_var,
              "Assign IDs to entries without one", 2)
        boxed("Normalize titles", self.normalize_var,
              "Strip leading numeric prefixes", 3)
        boxed("Sort alphabetically", self.sort_var,
              "Sort entries by <name>", 0, row=1)
        boxed("Pretty-print XML", self.indent_var,
              "Uncheck to skip re-indenting", 1, row=1)
        boxed("Force write", self.force_var,
              "Write even if nothing changed", 2, row=1)
        boxed("Delete orphan images", self.orphans_var,
              "Remove unreferenced images", 3, row=1)

        backups = ttk.Frame(box)
        backups.pack(fill="x", pady=(8, 0))
        ttk.Label(backups, text="Keep backups:").pack(side="left")
        self.keep_baks_var = tk.StringVar(value="5")
        ttk.Spinbox(
            backups,
            from_=0,
            to=99,
            textvariable=self.keep_baks_var,
            width=5,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            backups,
            text="per file (0 = keep all)",
            foreground="#666",
        ).pack(side="left", padx=(6, 0))

    def _build_actions(self, parent):
        box = ttk.LabelFrame(parent, text="Run", padding=8)
        box.pack(fill="x", pady=(10, 0))

        row1 = ttk.Frame(box)
        row1.pack(fill="x")
        self.preview_btn = ttk.Button(
            row1, text="1. Preview (dry run)",
            command=lambda: self.run_manager(dry_run=True),
        )
        self.preview_btn.pack(side="left")
        self.apply_btn = ttk.Button(
            row1, text="2. Apply changes",
            command=lambda: self.run_manager(dry_run=False),
        )
        self.apply_btn.pack(side="left", padx=(8, 0))
        ttk.Button(row1, text="Open README", command=self.open_readme).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(row1, text="Clear log", command=self.clear_log).pack(
            side="left", padx=(8, 0)
        )

        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=(8, 0))
        self.restore_preview_btn = ttk.Button(
            row2, text="Restore gamelist (preview)",
            command=lambda: self.run_restore(dry_run=True),
        )
        self.restore_preview_btn.pack(side="left")
        self.restore_btn = ttk.Button(
            row2, text="Restore gamelist",
            command=lambda: self.run_restore(dry_run=False),
        )
        self.restore_btn.pack(side="left", padx=(8, 0))
        self.prune_preview_btn = ttk.Button(
            row2, text="Delete backups (preview)",
            command=lambda: self.run_prune(dry_run=True),
        )
        self.prune_preview_btn.pack(side="left", padx=(8, 0))
        self.prune_btn = ttk.Button(
            row2, text="Delete backups",
            command=lambda: self.run_prune(dry_run=False),
        )
        self.prune_btn.pack(side="left", padx=(8, 0))

        ttk.Label(
            box,
            foreground="#b06",
            wraplength=760,
            justify="left",
            text=(
                "Applying rewrites gamelist.xml files and rebuilds "
                "root.dat + fileinfo. A dry run never writes anything. "
                "Deleting backups is permanent."
            ),
        ).pack(fill="x", pady=(8, 0))

    def _build_log(self, parent):
        box = ttk.LabelFrame(parent, text="Output", padding=6)
        box.pack(fill="both", expand=True, pady=(10, 0))
        self.log = ScrolledText(
            box, wrap="word", height=18,
            font=tkfont.nametofont("TkFixedFont"),
            state="disabled",
        )
        self.log.pack(fill="both", expand=True)

    def _build_status(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(8, 0))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side="right")

    # ------------------------------------------------------------- helpers

    def log_append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_busy(self, busy, message=""):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for btn in (
            self.preview_btn, self.apply_btn, self.restore_preview_btn,
            self.restore_btn, self.prune_preview_btn, self.prune_btn,
        ):
            btn.configure(state=state)
        if busy:
            self.progress.start(60)
            self.status_var.set(message or "Working...")
        else:
            self.progress.stop()
            self.status_var.set(message or "Ready.")

    def browse_root(self):
        chosen = filedialog.askdirectory(title="Select the ROM collection folder")
        if chosen:
            self.root_var.set(chosen)
            self.validate_root(quiet=True)

    def _autodetect(self, quiet=False):
        found = detect_rom_roots()
        if not found:
            if not quiet:
                messagebox.showinfo(
                    "Auto-detect",
                    "No folder containing root.dat and system folders "
                    "was found. Use Browse to select it manually.",
                )
            return
        self.root_var.set(found[0])
        if not quiet and len(found) > 1:
            messagebox.showinfo(
                "Auto-detect",
                "Multiple candidates found; using the first:\n\n"
                + "\n".join(found),
            )

    def validate_root(self, quiet=False):
        text = self.root_var.get().strip()
        if not text:
            self.root_hint.configure(text="Choose the folder that holds the ROM systems.")
            return None
        path = Path(text).expanduser()
        if not path.is_dir():
            self.root_hint.configure(text=f"Not a folder: {path}")
            return None
        if not looks_like_rom_root(path):
            self.root_hint.configure(
                text=(
                    f"Warning: {path} has no root.dat or system folders. "
                    "Double-check this is the right folder."
                )
            )
        else:
            self.root_hint.configure(text="")
        return str(path.resolve())

    def selected_system(self):
        value = self.system_var.get()
        return None if value == ALL_SYSTEMS else value

    # ------------------------------------------------------------ runners

    def run_manager(self, dry_run):
        root = self.validate_root()
        if not root:
            messagebox.showerror(
                "No folder", "Select the ROM collection folder first."
            )
            return
        if not dry_run:
            if not messagebox.askyesno(
                "Apply changes",
                "Rewrite the gamelist.xml files and rebuild "
                "root.dat + fileinfo?\n\n"
                "A dry run is recommended first. Continue?",
            ):
                return
            if self.orphans_var.get() and not messagebox.askyesno(
                "Delete orphan images",
                "Unreferenced images will be permanently deleted. "
                "Continue?",
            ):
                return

        self.log_append(
            "\n=== gamelist_manager %s ===\nroot=%s system=%s dedup=%s\n"
            % (
                "(dry run)" if dry_run else "(apply)",
                root,
                self.selected_system() or "all",
                self.dedup_var.get(),
            )
        )
        options = self.build_manager_options(root, dry_run)
        label = "Applying changes..." if not dry_run else "Previewing..."
        self.run_direct(
            lambda writer: self._run_manager_job(options, writer),
            label,
            preview=dry_run,
        )

    def build_manager_options(self, root, dry_run):
        system = self.selected_system()
        delete_orphans = self.orphans_var.get() and not dry_run
        try:
            keep_baks = int(str(self.keep_baks_var.get()).strip() or 5)
        except (TypeError, ValueError):
            keep_baks = 5
        keep_baks = max(0, keep_baks)
        return gamelist_manager.Options(
            root=Path(root),
            system=system,
            dry_run=dry_run,
            delete_orphaned_images=delete_orphans,
            no_prompt=not delete_orphans,
            skip_remove_missing=not self.remove_missing_var.get(),
            skip_add=not self.add_var.get(),
            skip_ids=not self.ids_var.get(),
            skip_normalize=not self.normalize_var.get(),
            skip_sort=not self.sort_var.get(),
            dedup=self.dedup_var.get(),
            indent=self.indent_var.get(),
            xml_declaration=self.decl_var.get(),
            force_write=self.force_var.get(),
            keep_baks=keep_baks,
        )

    def _run_manager_job(self, options, writer):
        result = gamelist_manager.run(options, output=writer.write)
        gamelist_manager.print_report(result, output=writer.write)
        return result.exit_code

    def run_restore(self, dry_run):
        root = self.validate_root()
        if not root:
            messagebox.showerror(
                "No folder", "Select the ROM collection folder first."
            )
            return
        if not dry_run and not messagebox.askyesno(
            "Restore gamelists",
            "Replace gamelist.xml with the newest valid backup in each "
            "system folder? The current file is saved as *.recovery.bak "
            "first.",
        ):
            return
        args = []
        system = self.selected_system()
        if system:
            args += ["--system", system]
        if dry_run:
            args.append("--dry-run")
        self.log_append(
            "\n=== restore_gamelist %s ===\n$ restore_gamelist.py %s\n"
            % ("(dry run)" if dry_run else "(restore)", " ".join(args) or "(all)")
        )
        self.run_direct(
            lambda writer: restore_gamelist.main(
                args, root=root, output=writer.write
            ),
            "Restoring..." if not dry_run else "Previewing restore...",
            preview=dry_run,
        )

    def run_prune(self, dry_run):
        root = self.validate_root()
        if not root:
            messagebox.showerror(
                "No folder", "Select the ROM collection folder first."
            )
            return
        if not dry_run and not messagebox.askyesno(
            "Delete backups",
            "Permanently delete timestamped gamelist backups "
            "(including *.recovery.bak) in this folder?\n\n"
            "This cannot be undone.",
        ):
            return
        args = []
        system = self.selected_system()
        if system:
            args += ["--system", system]
        if dry_run:
            args.append("--dry-run")
        self.log_append(
            "\n=== delete_gamelist_backups %s ===\n$ delete_gamelist_backups.py %s\n"
            % ("(dry run)" if dry_run else "(delete)", " ".join(args) or "(all)")
        )
        self.run_direct(
            lambda writer: delete_gamelist_backups.main(
                args, root=root, output=writer.write
            ),
            "Deleting backups..." if not dry_run else "Listing backups...",
            preview=dry_run,
        )

    def run_direct(self, func, label, preview=False):
        """Run a callable that receives a writer and returns an exit code."""
        if self.busy:
            return
        self.preview = preview
        self.set_busy(True, label)
        worker = threading.Thread(
            target=self._direct_worker, args=(func,), daemon=True
        )
        worker.start()
        self.root.after(80, self.poll)

    def _direct_worker(self, func):
        writer = QueueWriter(self.events)
        code = 0
        try:
            result = func(writer)
            if isinstance(result, int):
                code = result
        except Exception:
            traceback.print_exc(file=writer)
            code = 1
        finally:
            self.events.put(("done", code))

    def poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "out":
                    self.log_append(payload)
                elif kind == "done":
                    self.finish(payload)
        except queue.Empty:
            pass
        if self.busy:
            self.root.after(80, self.poll)

    def finish(self, code):
        if code == 0:
            self.set_busy(False, "Finished successfully.")
            self.log_append("\n--- finished (exit code 0) ---\n")
            return

        self.set_busy(False, f"Finished with issues (exit code {code}).")
        self.log_append(f"\n--- finished (exit code {code}) ---\n")
        if self.preview:
            # Previews commonly exit non-zero (e.g. a system folder with no
            # backup); keep it quiet and just note it in the log.
            self.log_append(
                "Note: exit code %s during a preview usually just means the "
                "tool found nothing to do for at least one system.\n" % code
            )
            return
        messagebox.showwarning(
            "Done with issues",
            "The command finished with exit code %s. "
            "See the output for details." % code,
        )

    def open_readme(self):
        readme = resource_path("README.md")
        if not readme.is_file():
            messagebox.showinfo("README", f"README.md not found at {readme}")
            return
        try:
            if sys.platform == "darwin":
                os.system(f'open "{readme}"')
            elif os.name == "nt":
                os.startfile(str(readme))  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{readme}"')
        except Exception as exc:
            messagebox.showerror("README", str(exc))


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
