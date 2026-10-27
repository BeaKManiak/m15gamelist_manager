# GUI guide

`m15_gui.py` is the desktop front-end and the released app. It calls the manager,
restore, and prune APIs directly on a background thread and streams output into a
details pane. It does not patch `sys.argv`, `sys.stdout`, or the working directory.

## The everyday flow

The main window is built around one action:

1. Open the app. It uses the collection folder you used last time, or looks for a
   mounted SD card.
2. Click **Update library**.
3. The app checks the collection without writing anything, then shows a
   plain-language summary — for example “3 new games will be added · 1 entry
   will be removed (the file is gone) · The device catalog will be refreshed”.
4. Confirm, and the change is applied. Changed gamelists and catalog files get
   timestamped backups first.

There is no separate “preview then apply” step to remember: the check always
happens, and nothing is written until you confirm. If the collection and the
device catalog are already up to date, the app says so and skips the
confirmation and the write entirely.

The main window also shows:

- **SD card** — the selected folder, with **Change…** to pick another one.
- **Last update** — a short summary of the previous run.
- **Advanced options** — the individual switches, collapsed by default.
- **Show details** — the full technical log, collapsed by default. It opens
  automatically when something fails.

## SD card detection

- On launch the app reuses the last folder if it is still valid. That is instant
  and avoids scanning every mounted disk.
- With no valid saved folder it searches for a collection: a folder containing
  `root.dat` plus at least one system folder. It checks the volume root, a
  `roms` subfolder, and one level deeper.
- macOS: `/Volumes/*`. Windows: removable drives first, then fixed drives
  (network and optical drives are skipped). Linux: `/media`, `/run/media`,
  and `/mnt`.
- If several collections are found, the app asks which one to use instead of
  guessing. If none is found, use **Change…** and browse.
- Android phones and other MTP devices do not expose a drive letter, so those
  need **Change…**.

Detection runs off the UI thread, so a slow or disconnected disk cannot freeze
the window.

## Advanced options

Expand **Advanced options** to change how an update behaves. Settings are saved
between launches; **Reset to defaults** restores the values below without
changing the selected folder.

| Control | Default | Effect |
|---|---|---|
| System | All systems | Limit processing and duplicate checks to one system. The device catalog is always rebuilt. When a single system is selected, the collapsed **Advanced options** label shows it (for example “Advanced options · nes only”). |
| Duplicate games | Path and game ID | Remove entries duplicated by path, by game ID, by both, or keep all (`None`). |
| XML style | Standard | `Legacy (double quotes)` writes the older double-quoted XML declaration. |
| Remove entries for games that are gone | on | Drop entries whose ROM file no longer exists. |
| Add new games | on | Add discovered ROMs that are missing from the gamelist. |
| Assign missing game IDs | on | Give entries without a `<gameid>` a new ID. |
| Clean up game titles | on | Strip leading numeric prefixes from titles. |
| Sort alphabetically | on | Sort entries by `<name>`. |
| Pretty-print the XML | on | Re-indent the file instead of writing a compact one. |
| Force write (rewrite even if nothing changed) | off | Rewrite every gamelist even when no entry changed. |
| Delete unused images (permanent) | off | Delete images no gamelist refers to. Only runs on an apply. |
| Keep backups | 5 | Keep the newest N backups per file. `0` keeps all. Recovery backups are never pruned automatically. |

Removing entries and deleting images are the only destructive options. Both are
off or listed explicitly in the confirmation summary before anything happens.

## What the check protects you from

The check runs the full processing and catalog preflight without writing:

- It reports parse problems and catalog issues in plain language.
- If the catalog preflight fails, no gamelist, image, or catalog file changes.
- The confirmation shows how many entries would be removed, so a stale or wrong
  folder is visible before it can do damage.

## Backups & restore

Open **Tools → Backups & restore…**. The window has three independent sections,
each with a non-writing **Preview**:

- **Restore gamelists** — replace the selected system’s (or every system’s)
  `gamelist.xml` with its most recent valid backup. The current file is saved as
  `*.recovery.bak` first.
- **Restore device catalog** — restore `root.dat` and `fileinfo` together from
  the newest valid matching backup pair. Both files are rolled back if the
  restored pair fails validation.
- **Delete old backups** — permanently delete timestamped backups for the
  selected system (or every system). Enable *Include catalog backups* to also
  prune `root.dat` and `fileinfo` backups; catalog backups are always global.

The window has its own output pane, so recovery work does not hide the main
window’s details. Preview can exit non-zero when a folder simply has no backup;
that is not an error.

## Menus

- **File → Change folder…** — pick another collection; **Quit**.
- **Tools → Backups & restore…** — the recovery window above.
- **Help → Open guide**, **Troubleshooting** — open the bundled documentation.

## Preferences

The app stores the last folder and the advanced settings in a small JSON file:

- macOS: `~/Library/Application Support/M15Manager/config.json`
- Windows: `%APPDATA%\M15Manager\config.json`
- Linux: `$XDG_CONFIG_HOME/m15manager/config.json` (or `~/.config/m15manager/`)

Deleting the file is safe: the next launch starts from defaults and auto-detect.
Corrupt or partially written files are ignored rather than preventing startup.

## Run from source

```bash
python3 m15_gui.py
```

Requires Python 3.9+ with tkinter. On macOS, Apple’s `/usr/bin/python3` ships
the deprecated Tk 8.5 and opens a blank window. Use a Python with Tk 8.6+ (the
python.org installer or `brew install python@3.14 python-tk@3.14`) or the
packaged app. With pyenv, either call the Homebrew Python by its full path
(`/opt/homebrew/bin/python3.14 m15_gui.py`) or rebuild a pyenv Python with
Homebrew’s `tcl-tk` installed — see
[Troubleshooting](troubleshooting.md#the-gui-window-is-blank-when-run-from-source).

## Related

- [CLI reference](cli.md)
- [Backups and restore](backups.md)
- [Troubleshooting](troubleshooting.md)
