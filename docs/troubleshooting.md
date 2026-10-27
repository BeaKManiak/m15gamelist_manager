# Troubleshooting

## Catalog preflight fails

The run stopped before changing any files. Check the listed entries:

- Every game entry needs a non-empty `<path>`.
- Every `<gameid>` must be numeric (for example `42`, not `game42`) and globally
  unique across all systems.
- Two entries cannot resolve to the same catalog path.
- Every configured system folder must exist with a readable `gamelist.xml`.
- `root.dat` and `fileinfo` must exist and match the documented formats.

A dry run performs the same preflight, so you can iterate without touching the
device.

## Catalog synchronization fails

Check that:

- `root.dat` exists and is a valid ZIP with exactly `fileinfo.001`, `.002`, `.003`.
- `fileinfo` exists and is exactly 25 comma-separated non-negative integers.
- All configured gamelists are valid XML with a `<gameList>` root.
- Every entry has a `<path>` and a numeric, globally unique `<gameid>`.
- No catalog paths are duplicated.

If the catalog step fails after the XMLs were written, the gamelists are newer
than `root.dat`/`fileinfo`. Restore the backups reported in the output, or use:

```bash
python3 restore_catalog.py --dry-run
python3 restore_catalog.py
```

## A ROM is not added

- It must be directly inside the system folder (no subfolders).
- Its extension must be supported for that system.
- The filename must not start with `._`.
- The run must not use `--skip-add`.
- The correct `--root` and `--system` must be selected.

See [Device layout](device-layout.md) for the extension table.

## An entry was removed

Entries whose ROM files are missing are removed by default. Keep them with:

```bash
python3 gamelist_manager.py --skip-remove-missing
```

## A restore skips a backup

Candidate backups that are not well-formed XML are skipped, so an older valid
backup may be chosen. `.recovery.bak` files are never used as restore sources.

See [Backups and restore](backups.md).

## Backups are using too much space

- Lower `--keep-baks` (default 5; `0` keeps all).
- In the GUI, **Advanced options → Keep backups** mirrors it.
- Use `delete_gamelist_backups.py --dry-run` first, then apply, or use
  **Tools → Backups & restore… → Delete old backups**.
- Add `--catalog` to include `root.dat`/`fileinfo` backups.
- Recovery backups are never pruned automatically; delete them explicitly only
  after verifying the device.

## The GUI will not open on macOS

The app is ad-hoc signed, not notarized. Right-click → **Open** → **Open**, or:

```bash
xattr -dr com.apple.quarantine /Applications/M15Manager.app
```

## The GUI window is blank when run from source

Apple’s `/usr/bin/python3` links to the deprecated Tk 8.5, which no longer draws
ttk interfaces on current macOS. The app builds and maps its widgets normally, so
the window appears empty.

Use a Python built against Tk 8.6 or newer:

```bash
brew install python@3.14 python-tk@3.14
/opt/homebrew/bin/python3.14 m15_gui.py
```

If you use pyenv, `python3` still points at pyenv’s build (which has no usable
Tk). Either call the Homebrew interpreter by its full path, as above, or rebuild
a pyenv Python now that Homebrew’s `tcl-tk` is present:

```bash
pyenv install 3.14.10       # python-build auto-detects Homebrew tcl-tk
pyenv global 3.14.10        # or: pyenv local 3.14.10
python3 -c "import tkinter; print(tkinter.TkVersion)"   # expect 9.1
python3 m15_gui.py
```

To rebuild an existing pyenv version instead, save its packages first:

```bash
~/.pyenv/versions/3.14.9/bin/python3 -m pip freeze > /tmp/pyenv-3.14.9.txt
pyenv uninstall -f 3.14.9
pyenv install 3.14.9
~/.pyenv/versions/3.14.9/bin/python3 -m pip install -r /tmp/pyenv-3.14.9.txt
```

`python-build` prefers `tcl-tk@8` when it is installed and falls back to
`tcl-tk`; both provide Tk 8.6+.

Keep Homebrew’s `tcl-tk` installed: the pyenv `_tkinter` extension links to its
dylibs at runtime. If `brew autoremove` removed it, `brew install tcl-tk`
restores the same version without rebuilding Python; re-running the install also
marks it as a top-level formula so it is not autoremoved again. Upgrading
`tcl-tk` to a new version does require rebuilding the pyenv Python.

Installing Python from [python.org](https://www.python.org/downloads/) also
works. The released **M15Manager** app bundles a current Tk and is unaffected.
The app prints a hint to stderr when it detects Tk 8.5.

## Windows SmartScreen warning

Click **More info** → **Run anyway**. The binaries are unsigned.

## A CLI preview exits non-zero

During a CLI preview this often just means at least one inspected system folder
had no usable backup. Check the log for the specific message. The GUI does not
show a warning for this: a preview with nothing to do is reported as “already up
to date”.

## Preview without modifying anything

```bash
python3 gamelist_manager.py --dry-run
python3 restore_gamelist.py --system nes --dry-run
python3 restore_catalog.py --dry-run
python3 delete_gamelist_backups.py --dry-run
```

## Related

- [CLI reference](cli.md)
- [Catalog format](catalog-format.md)
- [Backups and restore](backups.md)
