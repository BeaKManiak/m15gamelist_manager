#!/usr/bin/env python3
"""Tkinter GUI for the M15 ROM collection manager.

The everyday flow is one button: **Update library** checks the collection
without writing, explains the planned changes in plain language, and only then
applies them. Everything else — the individual switches, restore, and backup
pruning — is available without crowding the main window.

The GUI calls the manager, restore, and backup-pruning APIs directly on a
background thread and streams output into a details pane. It does not patch
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

import delete_gamelist_backups
import gamelist_manager
import restore_catalog
import restore_gamelist
from gui_support import (
    ALL_SYSTEMS,
    DECLARATION_CHOICES,
    DEFAULT_SETTINGS,
    DEDUP_CHOICES,
    SYSTEMS,
    catalog_needs_refresh,
    detect_rom_roots,
    format_confirmation,
    format_last_run,
    load_config,
    looks_like_rom_root,
    normalized_settings,
    plural,
    resource_path,
    save_config,
    summarize_result,
)

BG = "#f5f7fa"
CARD = "#ffffff"
BORDER = "#d9dee7"
TEXT = "#1f2430"
MUTED = "#5f6b7c"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
ACCENT_PRESSED = "#1e40af"

INFO_COLOR = MUTED
WARN_COLOR = "#b42318"
OK_COLOR = "#067647"


def _ui_font(size, bold=False):
    """A persisted font spec; tkinter Font objects get GC'd and deleted."""
    base = tkfont.nametofont("TkDefaultFont")
    family = base.actual("family")
    return (family, size, "bold" if bold else "normal")



# --------------------------------------------------------------------- widgets


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


class ConfirmDialog(tk.Toplevel):
    """A small modal confirmation with an explicit action button."""

    def __init__(self, app, title, lines, confirm_text):
        super().__init__(app.root)
        self.result = False
        self._app = app
        self.title(title)
        self.transient(app.root)
        self.resizable(False, False)
        self.configure(background=BG)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)

        base_font = tkfont.nametofont("TkDefaultFont")
        heading_size = int(base_font.cget("size"))
        if heading_size <= 0:
            heading_size = 13
        ttk.Label(body, text=title, font=_ui_font(heading_size + 2, True)).pack(
            anchor="w"
        )
        ttk.Label(
            body,
            text="\n".join(lines),
            justify="left",
            wraplength=430,
        ).pack(anchor="w", pady=(10, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(18, 0))
        ttk.Button(
            buttons,
            text=confirm_text,
            style="PrimarySmall.TButton",
            command=self._confirm,
        ).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side="right", padx=(0, 8)
        )

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self._center(app.root)

    def _center(self, parent):
        self.update_idletasks()
        try:
            width = self.winfo_reqwidth()
            height = self.winfo_reqheight()
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

    def _confirm(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()

    @classmethod
    def ask(cls, app, title, lines, confirm_text="Update library"):
        dialog = cls(app, title, lines, confirm_text)
        app.root.wait_window(dialog)
        return dialog.result


class DisclosureHeader(tk.Frame):
    """A full-width accordion row: bordered, chevron, clickable anywhere."""

    def __init__(self, parent, title, command):
        super().__init__(
            parent,
            background=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            cursor="hand2",
        )
        base = tkfont.nametofont("TkDefaultFont")
        size = int(base.cget("size"))
        if size <= 0:
            size = 13
        font = _ui_font(size + 3, True)

        self.title = title
        self.command = command
        self._open = False
        self.label = tk.Label(
            self,
            text=self._label_text(),
            anchor="w",
            background=CARD,
            foreground=ACCENT,
            font=font,
            cursor="hand2",
            padx=13,
            pady=10,
        )
        self.label.pack(fill="x")
        self.label.bind("<Button-1>", self._click)
        self.label.bind("<Enter>", self._hover)
        self.label.bind("<Leave>", self._unhover)

    def _label_text(self):
        arrow = "\u25be" if self._open else "\u25b8"
        return f"{arrow}  {self.title}"

    def set_open(self, opened):
        self._open = bool(opened)
        self.label.configure(text=self._label_text())

    def set_title(self, title):
        self.title = title
        self.label.configure(text=self._label_text())

    def _click(self, _event):
        self.command()

    def _hover(self, _event):
        self.configure(background="#eef4ff")
        self.label.configure(background="#eef4ff")

    def _unhover(self, _event):
        self.configure(background=CARD)
        self.label.configure(background=CARD)


class FolderDialog(tk.Toplevel):
    """Pick a collection folder, searching for mounted cards in the background."""

    def __init__(self, app, initial=None):
        super().__init__(app.root)
        self.app = app
        self.events: queue.Queue = queue.Queue()
        self.found = []
        self._running = False
        self._generation = 0
        self._alive = True

        self.title("Choose the collection folder")
        self.transient(app.root)
        self.resizable(True, False)
        self.configure(background=BG)
        self.minsize(560, 280)
        self._build()

        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        if initial is None:
            self.search()
        else:
            self._show_results(list(initial))

    def _build(self):
        ttk.Label(
            self,
            text=(
                "Pick the folder that contains root.dat and the system "
                "folders (usually named \u201croms\u201d)."
            ),
            wraplength=540,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=14)
        self.listbox = tk.Listbox(body, height=6, activestyle="none")
        self.listbox.configure(
            background=CARD,
            foreground=TEXT,
            selectbackground=ACCENT,
            selectforeground="#ffffff",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            relief="flat",
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            body, orient="vertical", command=self.listbox.yview
        )
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda _event: self.use_selected())
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self._sync_use_button())

        self.status_var = tk.StringVar(value="")
        ttk.Label(
            self,
            textvariable=self.status_var,
            foreground=INFO_COLOR,
            wraplength=540,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(8, 0))

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=14, pady=14)
        ttk.Button(buttons, text="Search again", command=self.search).pack(
            side="left"
        )
        ttk.Button(buttons, text="Browse\u2026", command=self.browse).pack(
            side="left", padx=(6, 0)
        )
        self.use_btn = ttk.Button(
            buttons,
            text="Use this folder",
            style="PrimarySmall.TButton",
            command=self.use_selected,
        )
        self.use_btn.pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.close).pack(
            side="right", padx=(0, 6)
        )

    # -- searching

    def search(self):
        if self._running:
            return
        self._generation += 1
        generation = self._generation
        self._running = True
        self.found = []
        self.listbox.delete(0, "end")
        self.use_btn.configure(state="disabled")
        self.status_var.set("Looking for your SD card\u2026")
        threading.Thread(
            target=self._detect, args=(generation,), daemon=True
        ).start()
        self.after(80, self._poll)

    def _detect(self, generation):
        try:
            found = detect_rom_roots()
        except Exception:
            found = []
        self.events.put((generation, found))

    def _poll(self):
        if not self._alive or not self._running:
            return
        try:
            generation, found = self.events.get_nowait()
        except queue.Empty:
            self.after(80, self._poll)
            return
        if generation != self._generation:
            self.after(80, self._poll)
            return
        self._running = False
        self._show_results(found)

    def _show_results(self, found):
        self.found = list(found)
        self.listbox.delete(0, "end")
        for path in self.found:
            self.listbox.insert("end", path)
        if self.found:
            self.listbox.selection_set(0)
            self.status_var.set(
                "%s found. Select one, or browse for another."
                % plural(len(self.found), "folder")
            )
        else:
            self.status_var.set(
                "No SD card found. Plug it in and search again, or browse "
                "for the folder."
            )
        self._sync_use_button()

    def _sync_use_button(self):
        state = "normal" if self.listbox.curselection() else "disabled"
        self.use_btn.configure(state=state)

    # -- actions

    def browse(self):
        self._generation += 1
        self._running = False
        chosen = filedialog.askdirectory(
            parent=self,
            title="Select the collection folder",
            mustexist=True,
        )
        if not chosen:
            return
        self.found = [str(Path(chosen).expanduser().resolve())]
        self._show_results(self.found)

    def use_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        path = self.found[selection[0]]
        self.app.apply_folder(path)
        self.close()

    def close(self):
        self._alive = False
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class RecoveryWindow(tk.Toplevel):
    """Restore gamelists or the catalog, and prune old backups."""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self._alive = True
        self.title("Backups & restore")
        self.transient(app.root)
        self.minsize(640, 580)
        self.configure(background=BG)
        self.resizable(True, True)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self):
        ttk.Label(
            self,
            text=(
                "Recovery tools. Previews never change anything; restoring "
                "keeps a safety copy of the current file."
            ),
            style="Muted.TLabel",
            wraplength=580,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        self.restore_system_var = tk.StringVar(value=ALL_SYSTEMS)
        self.prune_system_var = tk.StringVar(value=ALL_SYSTEMS)
        self.catalog_backups_var = tk.BooleanVar(value=False)
        self.buttons = []

        self._build_restore_gamelists()
        self._build_restore_catalog()
        self._build_delete_backups()
        self._build_output()

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=14, pady=(0, 14))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")
        self.close_btn = ttk.Button(footer, text="Close", command=self.close)
        self.close_btn.pack(side="right")

    def _build_restore_gamelists(self):
        box = ttk.LabelFrame(self, text="Restore gamelists", padding=10)
        box.pack(fill="x", padx=14)
        ttk.Label(
            box,
            text=(
                "Replace a gamelist with its most recent backup. The current "
                "file is kept as a safety copy."
            ),
            wraplength=560,
            justify="left",
        ).pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="System").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.restore_system_var,
            state="readonly",
            width=18,
            values=[ALL_SYSTEMS] + sorted(SYSTEMS),
        ).pack(side="left", padx=(6, 0))
        self.restore_btn = ttk.Button(
            row, text="Restore", command=lambda: self.run_restore(dry_run=False)
        )
        self.restore_btn.pack(side="right")
        self.restore_preview_btn = ttk.Button(
            row, text="Preview", command=lambda: self.run_restore(dry_run=True)
        )
        self.restore_preview_btn.pack(side="right", padx=(0, 6))
        self.buttons += [self.restore_preview_btn, self.restore_btn]

    def _build_restore_catalog(self):
        box = ttk.LabelFrame(self, text="Restore device catalog", padding=10)
        box.pack(fill="x", padx=14, pady=(10, 0))
        ttk.Label(
            box,
            text=(
                "Put root.dat and fileinfo back from the newest matching "
                "backup pair."
            ),
            wraplength=560,
            justify="left",
        ).pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        self.catalog_restore_btn = ttk.Button(
            row,
            text="Restore",
            command=lambda: self.run_catalog_restore(dry_run=False),
        )
        self.catalog_restore_btn.pack(side="right")
        self.catalog_restore_preview_btn = ttk.Button(
            row,
            text="Preview",
            command=lambda: self.run_catalog_restore(dry_run=True),
        )
        self.catalog_restore_preview_btn.pack(side="right", padx=(0, 6))
        self.buttons += [self.catalog_restore_preview_btn, self.catalog_restore_btn]

    def _build_delete_backups(self):
        box = ttk.LabelFrame(self, text="Delete old backups", padding=10)
        box.pack(fill="x", padx=14, pady=(10, 0))
        ttk.Label(
            box,
            text="Frees space. Deleted backups cannot be recovered.",
            wraplength=560,
            justify="left",
        ).pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="System").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.prune_system_var,
            state="readonly",
            width=18,
            values=[ALL_SYSTEMS] + sorted(SYSTEMS),
        ).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            row,
            text="Include catalog backups",
            variable=self.catalog_backups_var,
        ).pack(side="left", padx=(18, 0))

        actions = ttk.Frame(box)
        actions.pack(fill="x", pady=(8, 0))
        self.prune_btn = ttk.Button(
            actions, text="Delete", command=lambda: self.run_prune(dry_run=False)
        )
        self.prune_btn.pack(side="right")
        self.prune_preview_btn = ttk.Button(
            actions, text="Preview", command=lambda: self.run_prune(dry_run=True)
        )
        self.prune_preview_btn.pack(side="right", padx=(0, 6))
        self.buttons += [self.prune_preview_btn, self.prune_btn]

    def _build_output(self):
        box = ttk.LabelFrame(
            self, text="Output", padding=8, style="Card.TLabelframe"
        )
        box.pack(fill="both", expand=True, padx=14, pady=(10, 10))
        self.output = ScrolledText(
            box,
            wrap="word",
            height=8,
            font=tkfont.nametofont("TkFixedFont"),
            state="disabled",
        )
        configure_text_widget(self.output)
        self.output.pack(fill="both", expand=True)

    # -- helpers

    def append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def set_busy(self, busy, message=""):
        state = "disabled" if busy else "normal"
        for button in self.buttons:
            button.configure(state=state)
        self.close_btn.configure(state=state)
        self.status_var.set(message or ("Working\u2026" if busy else "Ready."))

    def _collection_root(self):
        root = self.app.current_root()
        if not root:
            messagebox.showerror(
                "No folder",
                "Choose the collection folder first.",
                parent=self,
            )
            return None
        return root

    def _start(self, func, label, preview):
        self.app.run_task(
            func,
            label,
            preview=preview,
            output=self.append_output,
            on_busy=self.set_busy,
            on_done=self._done,
        )

    def _done(self, code, result):
        self.app.finish_default(code, result, self.append_output, self)
        if code == 0:
            self.status_var.set("Finished.")
        else:
            self.status_var.set(f"Finished with issues (exit code {code}).")

    # -- actions

    def run_restore(self, dry_run):
        root = self._collection_root()
        if not root:
            return
        if not dry_run and not messagebox.askyesno(
            "Restore gamelists",
            "Replace the selected gamelist with its most recent backup?\n\n"
            "The current file is kept as a .recovery.bak safety copy.",
            parent=self,
        ):
            return
        args = []
        system = self.restore_system_var.get()
        if system != ALL_SYSTEMS:
            args += ["--system", system]
        if dry_run:
            args.append("--dry-run")
        self.append_output(
            "\n=== Restore gamelists (%s) ===\n"
            % ("preview" if dry_run else "restore")
        )
        self._start(
            lambda writer: restore_gamelist.main(args, root=root, output=writer.write),
            "Checking backups\u2026" if dry_run else "Restoring gamelists\u2026",
            dry_run,
        )

    def run_catalog_restore(self, dry_run):
        root = self._collection_root()
        if not root:
            return
        if not dry_run and not messagebox.askyesno(
            "Restore device catalog",
            "Replace root.dat and fileinfo with the newest matching backup "
            "pair?\n\nThe current files are kept as .recovery.bak safety "
            "copies.",
            parent=self,
        ):
            return
        args = ["--dry-run"] if dry_run else []
        self.append_output(
            "\n=== Restore device catalog (%s) ===\n"
            % ("preview" if dry_run else "restore")
        )
        self._start(
            lambda writer: restore_catalog.main(args, root=root, output=writer.write),
            "Checking catalog backups\u2026" if dry_run else "Restoring catalog\u2026",
            dry_run,
        )

    def run_prune(self, dry_run):
        root = self._collection_root()
        if not root:
            return
        include_catalog = self.catalog_backups_var.get()
        if not dry_run and not messagebox.askyesno(
            "Delete old backups",
            "Permanently delete old gamelist backups"
            + (" and catalog backups" if include_catalog else "")
            + " in this collection?\n\nThis cannot be undone.",
            icon="warning",
            parent=self,
        ):
            return
        args = []
        system = self.prune_system_var.get()
        if system != ALL_SYSTEMS:
            args += ["--system", system]
        if include_catalog:
            args.append("--catalog")
        if dry_run:
            args.append("--dry-run")
        self.append_output(
            "\n=== Delete old backups (%s) ===\n"
            % ("preview" if dry_run else "delete")
        )
        self._start(
            lambda writer: delete_gamelist_backups.main(
                args, root=root, output=writer.write
            ),
            "Listing backups\u2026" if dry_run else "Deleting backups\u2026",
            dry_run,
        )

    def close(self):
        if self.app.busy:
            messagebox.showinfo(
                "Still working",
                "Wait for the current operation to finish.",
                parent=self,
            )
            return
        self._alive = False
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.preview = False
        self._alive = True
        self._detecting = False
        self._task_output = None
        self._task_done = None
        self._task_busy = None
        self._update_root = None
        self._recovery = None

        saved = load_config()
        settings = normalized_settings(saved.get("settings"))

        root.title("M15 Manager")
        root.minsize(720, 520)
        root.geometry("820x720")

        self._create_vars(settings)
        self._build_widgets()
        self._update_controls()
        self._build_menu()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(80, self._poll_events)

        self._restore_folder(saved.get("root"))

    # ---------------------------------------------------------------- layout

    def _create_vars(self, settings):
        self.folder_var = tk.StringVar(value="")
        self.hint_var = tk.StringVar(value="")
        self.result_var = tk.StringVar(value="No update yet.")
        self.status_var = tk.StringVar(value="Ready.")

        self.system_var = tk.StringVar(value=settings["system"])
        self.dedup_var = tk.StringVar(value=settings["dedup"])
        self.decl_var = tk.StringVar(value=settings["declaration"])
        self.dedup_display = tk.StringVar(
            value=self._label_for(DEDUP_CHOICES, settings["dedup"])
        )
        self.decl_display = tk.StringVar(
            value=self._label_for(DECLARATION_CHOICES, settings["declaration"])
        )

        self.remove_missing_var = tk.BooleanVar(value=settings["remove_missing"])
        self.add_var = tk.BooleanVar(value=settings["add"])
        self.ids_var = tk.BooleanVar(value=settings["ids"])
        self.normalize_var = tk.BooleanVar(value=settings["normalize"])
        self.sort_var = tk.BooleanVar(value=settings["sort"])
        self.indent_var = tk.BooleanVar(value=settings["indent"])
        self.force_var = tk.BooleanVar(value=settings["force_write"])
        self.orphans_var = tk.BooleanVar(value=settings["delete_orphans"])
        self.keep_baks_var = tk.StringVar(value=str(settings["keep_baks"]))

        self.advanced_open = False
        self.details_open = False

    @staticmethod
    def _label_for(choices, value):
        for key, label in choices:
            if key == value:
                return label
        return choices[0][1]

    @staticmethod
    def _value_for(choices, label, fallback):
        for key, text in choices:
            if text == label:
                return key
        return fallback

    def _build_widgets(self):
        self.status_bar = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        self.status_bar.pack(side="bottom", fill="x")
        ttk.Separator(self.root).pack(side="bottom", fill="x")
        ttk.Label(self.status_bar, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(
            self.status_bar, mode="indeterminate", length=140
        )

        outer = ttk.Frame(self.root, padding=(14, 12, 14, 6))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(7, weight=1)

        self._build_folder(outer, row=0)
        self._build_primary(outer, row=2)
        self._build_result(outer, row=3)
        self._build_advanced_header(outer, row=4)
        self._build_advanced(outer, row=5)
        self._build_details_header(outer, row=6)
        self._build_log(outer, row=7)

    def _build_folder(self, parent, row):
        box = ttk.LabelFrame(
            parent, text="SD card", padding=10, style="Card.TLabelframe"
        )
        box.grid(row=row, column=0, sticky="ew")
        self.folder_label = ttk.Label(
            box,
            textvariable=self.folder_var,
            anchor="w",
            justify="left",
            wraplength=520,
            style="Card.TLabel",
        )
        self.folder_label.pack(side="left", fill="x", expand=True)
        self.change_btn = ttk.Button(
            box, text="Change\u2026", command=self.choose_folder
        )
        self.change_btn.pack(side="left", padx=(8, 0))

        self.folder_hint = ttk.Label(
            parent,
            textvariable=self.hint_var,
            foreground=INFO_COLOR,
            wraplength=660,
            justify="left",
        )
        self.folder_hint.grid(row=row + 1, column=0, sticky="ew", pady=(4, 0))

    def _build_primary(self, parent, row):
        card = ttk.Frame(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        self.update_btn = ttk.Button(
            card,
            text="Update library",
            style="Primary.TButton",
            command=self.start_update,
        )
        self.update_btn.pack(fill="x")
        ttk.Label(
            card,
            text=(
                "Scan for new games, remove entries whose files are gone, "
                "and refresh the device catalog."
            ),
            style="Muted.TLabel",
            anchor="center",
            justify="center",
            wraplength=620,
        ).pack(fill="x", pady=(8, 0))

    def _build_result(self, parent, row):
        ttk.Label(
            parent,
            textvariable=self.result_var,
            wraplength=660,
            justify="left",
        ).grid(row=row, column=0, sticky="w", pady=(12, 0))

    def _build_advanced_header(self, parent, row):
        self.advanced_header = DisclosureHeader(
            parent, "Advanced options", self.toggle_advanced
        )
        self.advanced_header.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        self.system_var.trace_add(
            "write", lambda *_args: self._update_advanced_label()
        )

    def _build_details_header(self, parent, row):
        self.details_header = DisclosureHeader(
            parent, "Show details", self.toggle_details
        )
        self.details_header.grid(row=row, column=0, sticky="ew", pady=(8, 0))

    def _build_advanced(self, parent, row):
        self.advanced_frame = ttk.Frame(parent, padding=(12, 6, 0, 0))
        self.advanced_frame.grid(row=row, column=0, sticky="ew", pady=(6, 0))
        self.advanced_frame.grid_remove()
        self.advanced_frame.columnconfigure(1, weight=1)

        grid = ttk.Frame(self.advanced_frame)
        grid.grid(row=0, column=0, columnspan=2, sticky="ew")
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="System").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(
            grid,
            textvariable=self.system_var,
            state="readonly",
            width=20,
            values=[ALL_SYSTEMS] + sorted(SYSTEMS),
        ).grid(row=0, column=1, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(grid, text="Duplicate games").grid(
            row=1, column=0, sticky="w", pady=2
        )
        dedup_combo = ttk.Combobox(
            grid,
            textvariable=self.dedup_display,
            state="readonly",
            width=20,
            values=[label for _key, label in DEDUP_CHOICES],
        )
        dedup_combo.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=2)
        dedup_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._choice_changed(
                DEDUP_CHOICES, self.dedup_display, self.dedup_var
            )
        )

        ttk.Label(grid, text="XML style").grid(
            row=2, column=0, sticky="w", pady=2
        )
        decl_combo = ttk.Combobox(
            grid,
            textvariable=self.decl_display,
            state="readonly",
            width=20,
            values=[label for _key, label in DECLARATION_CHOICES],
        )
        decl_combo.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=2)
        decl_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._choice_changed(
                DECLARATION_CHOICES, self.decl_display, self.decl_var
            )
        )

        checks = ttk.Frame(self.advanced_frame)
        checks.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        checkboxes = [
            ("Remove entries for games that are gone", self.remove_missing_var),
            ("Add new games", self.add_var),
            ("Assign missing game IDs", self.ids_var),
            ("Clean up game titles", self.normalize_var),
            ("Sort alphabetically", self.sort_var),
            ("Pretty-print the XML", self.indent_var),
            ("Force write (rewrite even if nothing changed)", self.force_var),
            ("Delete unused images (permanent)", self.orphans_var),
        ]
        for index, (text, variable) in enumerate(checkboxes):
            ttk.Checkbutton(
                checks,
                text=text,
                variable=variable,
                command=self.persist_settings,
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, 28),
                pady=2,
            )

        bottom = ttk.Frame(self.advanced_frame)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(bottom, text="Keep backups").pack(side="left")
        ttk.Spinbox(
            bottom,
            from_=0,
            to=99,
            width=4,
            textvariable=self.keep_baks_var,
            command=self.persist_settings,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            bottom, text="per file (0 keeps all)", foreground=INFO_COLOR
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            bottom,
            text="Reset to defaults",
            style="Disclosure.TButton",
            command=self.reset_settings,
        ).pack(side="right")

    def _build_log(self, parent, row):
        self.log_frame = ttk.LabelFrame(
            parent, text="Details", padding=8, style="Card.TLabelframe"
        )
        self.log_frame.grid(row=row, column=0, sticky="nsew", pady=(8, 0))
        self.log_frame.grid_remove()
        self.log = ScrolledText(
            self.log_frame,
            wrap="word",
            height=12,
            font=tkfont.nametofont("TkFixedFont"),
            state="disabled",
        )
        configure_text_widget(self.log)
        self.log.pack(fill="both", expand=True)

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="Change folder\u2026", command=self.choose_folder
        )
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(
            label="Backups & restore\u2026", command=self.open_recovery
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(
            label="Open guide", command=lambda: self.open_doc("README.md")
        )
        help_menu.add_command(
            label="Troubleshooting",
            command=lambda: self.open_doc("docs/troubleshooting.md"),
        )
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menubar)

    # --------------------------------------------------------------- helpers

    def log_append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_hint(self, text, level="info"):
        colors = {"info": INFO_COLOR, "warn": WARN_COLOR, "ok": OK_COLOR}
        self.hint_var.set(text)
        self.folder_hint.configure(foreground=colors.get(level, INFO_COLOR))

    def set_status(self, text):
        self.status_var.set(text)

    def set_result(self, text):
        self.result_var.set(text)

    def _update_controls(self):
        has_folder = bool(self.folder_var.get().strip())
        self.update_btn.configure(
            state="normal" if has_folder and not self.busy else "disabled"
        )
        self.change_btn.configure(state="disabled" if self.busy else "normal")

    def set_busy(self, busy, message=""):
        self.busy = busy
        self._update_controls()
        if busy:
            self.progress.pack(side="right")
            self.progress.start(60)
            self.set_status(message or "Working\u2026")
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.set_status(message or "Ready.")

    def _update_advanced_label(self):
        title = "Advanced options"
        system = self.system_var.get()
        if system != ALL_SYSTEMS:
            title += f"  \u00b7  {system} only"
        self.advanced_header.set_title(title)

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced_frame.grid()
        else:
            self.advanced_frame.grid_remove()
        self.advanced_header.set_open(self.advanced_open)

    def toggle_details(self):
        self.show_details(not self.details_open)

    def show_details(self, visible):
        self.details_open = visible
        if visible:
            self.log_frame.grid()
        else:
            self.log_frame.grid_remove()
        self.details_header.set_open(visible)

    def _choice_changed(self, choices, display_var, internal_var):
        internal_var.set(
            self._value_for(choices, display_var.get(), internal_var.get())
        )
        self.persist_settings()

    def _sync_choice(self, choices, display_var, internal_var):
        display_var.set(self._label_for(choices, internal_var.get()))

    def reset_settings(self):
        self._apply_settings(DEFAULT_SETTINGS)
        self.persist_settings()
        self.set_status("Advanced options reset to defaults.")

    def _apply_settings(self, settings):
        self.system_var.set(settings["system"])
        self.dedup_var.set(settings["dedup"])
        self.decl_var.set(settings["declaration"])
        self.remove_missing_var.set(settings["remove_missing"])
        self.add_var.set(settings["add"])
        self.ids_var.set(settings["ids"])
        self.normalize_var.set(settings["normalize"])
        self.sort_var.set(settings["sort"])
        self.indent_var.set(settings["indent"])
        self.force_var.set(settings["force_write"])
        self.orphans_var.set(settings["delete_orphans"])
        self.keep_baks_var.set(str(settings["keep_baks"]))
        self._sync_choice(DEDUP_CHOICES, self.dedup_display, self.dedup_var)
        self._sync_choice(
            DECLARATION_CHOICES, self.decl_display, self.decl_var
        )

    def _settings_snapshot(self):
        keep_baks = self.keep_baks_var.get()
        try:
            keep_baks = int(str(keep_baks).strip() or 5)
        except (TypeError, ValueError):
            keep_baks = DEFAULT_SETTINGS["keep_baks"]
        return {
            "system": self.system_var.get(),
            "dedup": self.dedup_var.get(),
            "declaration": self.decl_var.get(),
            "remove_missing": bool(self.remove_missing_var.get()),
            "add": bool(self.add_var.get()),
            "ids": bool(self.ids_var.get()),
            "normalize": bool(self.normalize_var.get()),
            "sort": bool(self.sort_var.get()),
            "indent": bool(self.indent_var.get()),
            "force_write": bool(self.force_var.get()),
            "delete_orphans": bool(self.orphans_var.get()),
            "keep_baks": min(max(keep_baks, 0), 99),
        }

    def persist_settings(self):
        data = {
            "root": self.folder_var.get().strip() or None,
            "settings": self._settings_snapshot(),
        }
        try:
            save_config(data)
        except OSError:
            pass

    # ---------------------------------------------------------------- folders

    def apply_folder(self, path):
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = str(path)
        self.folder_var.set(resolved)
        self.set_result("No update yet.")
        self._update_controls()
        self.current_root()
        self.persist_settings()
        self.set_status("Folder selected.")

    def current_root(self):
        text = self.folder_var.get().strip()
        if not text:
            self.set_hint(
                "Choose the folder that holds root.dat and the system folders."
            )
            return None
        path = Path(text).expanduser()
        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False
        if not is_dir:
            self.set_hint(f"That folder is not available: {path}", "warn")
            return None
        if not looks_like_rom_root(path):
            self.set_hint(
                "This folder has no root.dat or system folders. "
                "Check it before updating.",
                "warn",
            )
        else:
            self.set_hint("")
        try:
            return str(path.resolve())
        except OSError:
            return str(path)

    def choose_folder(self):
        if self.busy:
            return
        dialog = FolderDialog(self)
        self.root.wait_window(dialog)

    def _restore_folder(self, remembered):
        if remembered:
            path = Path(str(remembered)).expanduser()
            if looks_like_rom_root(path):
                self.apply_folder(path)
                self.set_status("Ready.")
                return
        self._start_detection()

    def _start_detection(self):
        if self._detecting:
            return
        self._detecting = True
        self.set_hint("Looking for your SD card\u2026")
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def _detect_worker(self):
        try:
            found = detect_rom_roots()
        except Exception:
            found = []
        self.events.put(("roots", found))

    def _on_detected(self, found):
        self._detecting = False
        if self.folder_var.get().strip():
            return
        if not found:
            self.set_hint(
                "No SD card found. Plug in your M15 or insert the card, then "
                "click Change\u2026."
            )
            self.set_status("No SD card found yet.")
            return
        if len(found) == 1:
            self.apply_folder(found[0])
            self.set_status("Found your library.")
            return
        self.set_hint(
            "Found %s. Choose the right one." % plural(len(found), "library", "libraries")
        )
        self.set_status("Several collections found \u2014 choose one.")
        self.root.after(60, lambda: self._open_folder_dialog(found))

    def _open_folder_dialog(self, initial):
        if self.busy or self.folder_var.get().strip():
            return
        dialog = FolderDialog(self, initial=initial)
        self.root.wait_window(dialog)

    # ------------------------------------------------------------------- runs

    def run_task(
        self,
        func,
        label,
        *,
        preview=False,
        output=None,
        on_done=None,
        on_busy=None,
    ):
        """Run ``func(writer)`` on a worker thread and stream its output."""
        if self.busy:
            return False
        self.preview = preview
        self._task_output = output or self.log_append
        self._task_done = on_done
        self._task_busy = on_busy
        self.set_busy(True, label)
        if on_busy:
            on_busy(True, label)
        threading.Thread(target=self._worker, args=(func,), daemon=True).start()
        return True

    def _worker(self, func):
        writer = QueueWriter(self.events)
        code = 0
        result = None
        try:
            value = func(writer)
            if isinstance(value, bool):
                result = value
            elif isinstance(value, int):
                code = value
            else:
                result = value
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        except Exception:
            traceback.print_exc(file=writer)
            code = 1
        finally:
            self.events.put(("done", (code, result)))

    def _poll_events(self):
        if not self._alive:
            return
        pending = []
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "out":
                    pending.append(payload)
                    continue
                if pending:
                    sink = self._task_output or self.log_append
                    sink("".join(pending))
                    pending.clear()
                if kind == "done":
                    self._finish_task(*payload)
                elif kind == "roots":
                    self._on_detected(payload)
        except queue.Empty:
            pass
        if pending:
            sink = self._task_output or self.log_append
            sink("".join(pending))
        try:
            self.root.after(80, self._poll_events)
        except tk.TclError:
            self._alive = False

    def _finish_task(self, code, result):
        self.busy = False
        self.set_busy(False)
        on_busy = self._task_busy
        self._task_busy = None
        if on_busy:
            on_busy(False)
        sink = self._task_output or self.log_append
        on_done = self._task_done
        self._task_done = None
        self._task_output = None
        if on_done:
            on_done(code, result)
        else:
            self.finish_default(code, result, sink)

    def finish_default(self, code, result, output=None, parent=None):
        sink = output or self.log_append
        if code == 0:
            self.set_status("Finished successfully.")
            sink("\n--- finished (exit code 0) ---\n")
            return

        self.set_status(f"Finished with issues (exit code {code}).")
        sink(f"\n--- finished (exit code {code}) ---\n")
        if self.preview:
            sink(
                "Note: a preview can exit non-zero when a folder has nothing "
                "to do.\n"
            )
            return
        messagebox.showwarning(
            "Finished with issues",
            "The command finished with exit code %s. See the output for "
            "details." % code,
            parent=parent or self.root,
        )

    # ------------------------------------------------------------------ update

    def start_update(self):
        if self.busy:
            return
        root = self.current_root()
        if not root:
            self.set_status("Choose the collection folder first.")
            return
        if not looks_like_rom_root(Path(root)):
            if not messagebox.askyesno(
                "Check the folder",
                f"{root}\n\nThis folder has no root.dat or system folders. "
                "Update it anyway?",
                icon="warning",
                parent=self.root,
            ):
                return
        self._update_root = root
        options = self.build_manager_options(root, dry_run=True)
        self.log_append(
            "\n=== Update library \u2014 check ===\nFolder: %s\n" % root
        )
        self.set_result("Checking for changes\u2026")
        self.run_task(
            lambda writer: self._run_manager_job(options, writer),
            "Checking library\u2026",
            preview=True,
            on_done=self._after_preview,
        )

    def build_manager_options(self, root, dry_run):
        system = None if self.system_var.get() == ALL_SYSTEMS else self.system_var.get()
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
            show_spinner=False,
        )

    def _run_manager_job(self, options, writer):
        result = gamelist_manager.run(options, output=writer.write)
        gamelist_manager.print_report(result, output=writer.write)
        return result

    def _after_preview(self, code, result):
        if result is None:
            self.set_status("The check failed. Nothing was changed.")
            self.show_details(True)
            messagebox.showerror(
                "Update library",
                "Something went wrong while checking.\n\nNothing was changed. "
                "See the details for the reason.",
                parent=self.root,
            )
            return

        if result.preflight_issues or result.errors or result.catalog_sync_error:
            self.set_status("The check found problems. Nothing was changed.")
            self.show_details(True)
            messagebox.showerror(
                "Update library",
                self._failure_message(result),
                parent=self.root,
            )
            return

        counts = summarize_result(result)
        if counts["systems_changed"] == 0 and not self.force_var.get():
            delete_orphans = bool(self.orphans_var.get()) and counts["orphans"] > 0
            self.set_status("Checking the device catalog\u2026")
            options = self.build_manager_options(self._update_root, dry_run=True)
            self.run_task(
                lambda writer: catalog_needs_refresh(self._update_root, options),
                "Checking the device catalog\u2026",
                preview=True,
                on_done=lambda _code, refresh: self._after_catalog_check(
                    counts, refresh, delete_orphans
                ),
            )
            return

        self._confirm_update(counts, True)

    def _after_catalog_check(self, counts, refresh, delete_orphans=False):
        if refresh is False and not delete_orphans:
            message = "Library is up to date \u2014 nothing to change."
            self.set_status(message)
            self.set_result(message)
            self.log_append(
                "\nNo changes: the game lists and device catalog are already "
                "up to date.\n"
            )
            return
        self._confirm_update(counts, refresh is not False)

    def _confirm_update(self, counts, catalog_refresh):
        lines = format_confirmation(
            counts, catalog_refresh, delete_orphans=bool(self.orphans_var.get())
        )
        if self.force_var.get() and counts["systems_changed"] == 0:
            lines.insert(
                -2,
                "All game lists will be rewritten because Force write is on.",
            )
        if not ConfirmDialog.ask(self, "Update library", lines):
            self.set_status("Update cancelled \u2014 nothing was changed.")
            self.set_result("Update cancelled.")
            return

        options = self.build_manager_options(self._update_root, dry_run=False)
        self.log_append("\n=== Update library \u2014 apply ===\n")
        self.run_task(
            lambda writer: self._run_manager_job(options, writer),
            "Updating library\u2026",
            on_done=self._after_apply,
        )

    def _after_apply(self, code, result):
        if result is None:
            self.set_status("The update failed.")
            self.show_details(True)
            messagebox.showerror(
                "Update library",
                "Something went wrong while updating. See the details for the "
                "reason.",
                parent=self.root,
            )
            return

        if result.exit_code:
            self.set_status("Update finished with problems.")
            self.show_details(True)
            messagebox.showerror(
                "Update library",
                "The update finished with problems. Some files may already "
                "have been changed.\n\nSee the details for the reason.",
                parent=self.root,
            )
            return

        summary = format_last_run(result)
        self.set_result("Last update: " + summary)
        self.set_status("Update complete.")
        self.log_append("\nUpdate complete.\n")
        self.persist_settings()

    def _failure_message(self, result):
        if result.preflight_issues:
            return (
                "Nothing was changed.\n\nThe check found %s that must be fixed "
                "before anything is written.\n\nOpen the details to see exactly "
                "what needs attention."
                % plural(len(result.preflight_issues), "problem")
            )
        if result.errors:
            broken = sorted(
                name
                for name, item in result.systems.items()
                if item.get("status") == "ERROR"
            )
            return (
                "Nothing was changed.\n\nThese game lists could not be read: "
                "%s.\n\nSee the details for the reason." % ", ".join(broken)
            )
        return "Something went wrong. See the details for the reason."

    # ------------------------------------------------------------- maintenance

    def open_recovery(self):
        if self.busy:
            messagebox.showinfo(
                "Please wait",
                "Let the current operation finish first.",
                parent=self.root,
            )
            return
        if self._recovery is not None:
            try:
                if self._recovery.winfo_exists():
                    self._recovery.lift()
                    return
            except tk.TclError:
                pass
        self._recovery = RecoveryWindow(self)

    def open_doc(self, relative):
        path = resource_path(relative)
        if not path.is_file():
            messagebox.showinfo(
                "Help", f"{relative} was not found next to the app.", parent=self.root
            )
            return
        try:
            if sys.platform == "darwin":
                os.system(f'open "{path}"')
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            messagebox.showerror("Help", str(exc), parent=self.root)

    def on_close(self):
        if self.busy:
            messagebox.showwarning(
                "Still working",
                "An operation is still running. Wait for it to finish before "
                "closing.",
                parent=self.root,
            )
            return
        self.persist_settings()
        self._alive = False
        self.root.destroy()


def configure_styles(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    base = tkfont.nametofont("TkDefaultFont")
    base_size = int(base.cget("size"))
    if base_size <= 0:
        base_size = 13

    small_bold = _ui_font(base_size + 1, True)
    disclosure = _ui_font(base_size + 3, True)
    primary_font = _ui_font(base_size * 2 + 10, True)
    primary_small = _ui_font(base_size + 2, True)

    root.configure(background=BG)
    style.configure(".", background=BG, foreground=TEXT, font=base)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)

    style.configure(
        "TLabelframe",
        background=BG,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=BG,
        foreground=MUTED,
        font=small_bold,
    )
    style.configure(
        "Card.TLabelframe",
        background=CARD,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=CARD,
        foreground=MUTED,
        font=small_bold,
    )

    style.configure("TCheckbutton", background=BG, foreground=TEXT)
    style.configure("Card.TCheckbutton", background=CARD, foreground=TEXT)

    style.configure(
        "TButton",
        background=CARD,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=CARD,
        darkcolor=BORDER,
        padding=(12, 7),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[
            ("disabled", "#eef1f6"),
            ("pressed", "#e4eaf3"),
            ("active", "#f0f3f8"),
        ],
        foreground=[("disabled", "#9aa4b2")],
        bordercolor=[("focus", ACCENT)],
    )

    style.configure(
        "Primary.TButton",
        font=primary_font,
        padding=(24, 12),
        foreground="#ffffff",
        background=ACCENT,
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        relief="flat",
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", "#c7d2e4"),
            ("pressed", ACCENT_PRESSED),
            ("active", ACCENT_HOVER),
        ],
        foreground=[("disabled", "#7c889c")],
        bordercolor=[("disabled", "#c7d2e4")],
    )

    style.configure(
        "PrimarySmall.TButton",
        font=primary_small,
        padding=(14, 9),
        foreground="#ffffff",
        background=ACCENT,
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        relief="flat",
    )
    style.map(
        "PrimarySmall.TButton",
        background=[
            ("disabled", "#c7d2e4"),
            ("pressed", ACCENT_PRESSED),
            ("active", ACCENT_HOVER),
        ],
        foreground=[("disabled", "#7c889c")],
        bordercolor=[("disabled", "#c7d2e4")],
    )

    style.configure(
        "Disclosure.TButton",
        background=BG,
        foreground=ACCENT,
        font=disclosure,
        padding=(10, 6),
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Disclosure.TButton",
        background=[("pressed", "#dbe6fb"), ("active", "#e8effc")],
        foreground=[("active", ACCENT_HOVER)],
    )

    style.configure(
        "CardDisclosure.TButton",
        background=CARD,
        foreground=ACCENT,
        font=disclosure,
        padding=(8, 4),
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "CardDisclosure.TButton",
        background=[("pressed", "#dbe6fb"), ("active", "#eef4ff")],
        foreground=[("active", ACCENT_HOVER)],
    )

    style.configure(
        "TEntry",
        fieldbackground=CARD,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        insertcolor=TEXT,
        padding=5,
    )
    style.map("TEntry", bordercolor=[("focus", ACCENT)])

    style.configure(
        "TCombobox",
        fieldbackground=CARD,
        background=CARD,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        arrowcolor=MUTED,
        padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", CARD)],
        background=[("readonly", CARD)],
        foreground=[("readonly", TEXT)],
        selectbackground=[("readonly", CARD)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT)],
    )

    style.configure(
        "TSpinbox",
        fieldbackground=CARD,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        arrowcolor=MUTED,
        padding=4,
    )
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)])

    style.configure(
        "Vertical.TScrollbar",
        background="#e4e9f1",
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=MUTED,
        lightcolor="#e4e9f1",
        darkcolor="#e4e9f1",
    )
    style.configure(
        "TProgressbar",
        background=ACCENT,
        troughcolor="#e4e9f1",
        bordercolor=BG,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
    )
    style.configure("TSeparator", background=BORDER)


def configure_text_widget(widget):
    """Give a classic Tk text widget the app's flat, modern look."""
    widget.configure(
        background=CARD,
        foreground=TEXT,
        insertbackground=TEXT,
        selectbackground="#cfe0fb",
        selectforeground=TEXT,
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        padx=10,
        pady=8,
    )
    frame = getattr(widget, "frame", None)
    if frame is not None:
        frame.configure(background=CARD)


def warn_about_legacy_tk():
    """Explain the blank window caused by Apple's unsupported Tk 8.5."""
    if sys.platform != "darwin" or tk.TkVersion >= 8.6:
        return
    print(
        "Warning: this Python uses Apple's deprecated Tk 8.5, which cannot "
        "draw the interface on current macOS (the window appears blank).\n"
        "Use a Python built against Tk 8.6 or newer — for example the "
        "python.org installer, or `brew install python@3.14 python-tk@3.14` "
        "and run /opt/homebrew/bin/python3.14 m15_gui.py (pyenv's `python3` "
        "still points at its own build) — or run the packaged M15Manager app.",
        file=sys.stderr,
    )


def main():
    warn_about_legacy_tk()
    root = tk.Tk()
    configure_styles(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
