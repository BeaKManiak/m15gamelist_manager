# M15 ROM Collection Manager

[![CI](https://github.com/BeaKManiak/m15gamelist_manager/actions/workflows/ci.yml/badge.svg)](https://github.com/BeaKManiak/m15gamelist_manager/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/BeaKManiak/m15gamelist_manager?label=release)](https://github.com/BeaKManiak/m15gamelist_manager/releases/latest)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

Keep the ROM library, per-system gamelists, and device catalog of an **M15 retro
handheld** in sync.

The app scans system folders, adds newly discovered ROMs, removes entries whose
files disappeared, normalizes metadata, deduplicates, sorts, and rebuilds
`root.dat` + `cubegm/fileinfo`. A desktop GUI is the recommended way to use it;
the CLI is there for scripting and debugging.

## Download

Grab the latest release from
[**Releases**](https://github.com/BeaKManiak/m15gamelist_manager/releases/latest).

| Platform | Download |
|---|---|
| macOS, Apple Silicon | `M15Manager-ARM64.zip` |
| Windows | `M15Manager-windows.zip` |

**No Python installation is required.** The app is self-contained.

The builds are not notarized and are not signed with a trusted certificate, so
the first launch shows a warning. See [Install](docs/install.md) for the macOS
and Windows steps.

## Quick start

1. Connect the M15 storage and note the folder that contains `root.dat` and the
   system folders (usually `roms`).
2. Open **M15Manager**. It reuses your last folder, or finds the card itself.
3. Click **Update library**.
4. Review the plain-language summary and confirm. Nothing is written before this
   point, and the app says so if the library is already up to date.
5. Eject safely and verify the library on the device.

The check looks for new games, entries whose files are gone, and catalog drift.
A catalog preflight failure means nothing was written; fix the reported entries
and try again.

## What it does

- **Scans ROM folders** for supported files, non-recursively.
- **Maintains gamelists**: adds new ROMs and removes entries for missing files.
- **Normalizes metadata**: assigns game IDs and strips numeric title prefixes.
- **Deduplicates and sorts** entries.
- **Handles orphaned images**: reports them and deletes only when asked.
- **Rebuilds the device catalog** (`root.dat` and `cubegm/fileinfo`).
- **Writes safely**: validates before and after writing, preserves BOMs, creates
  timestamped backups, and rolls back on failure.
- **Restores backups** for both gamelists and the catalog.

## The 30-second layout

```text
M15 storage/
├── cubegm/
│   └── fileinfo                 # 25 counters used by the device
└── roms/                        # select this folder in the GUI
    ├── root.dat                 # device catalog
    ├── arcade/
    │   ├── gamelist.xml
    │   ├── images/
    │   └── *.zip
    └── ...
```

The GUI assumes this standard layout. Full details and the supported-system table
are in [Device layout](docs/device-layout.md).

## GUI

The desktop app provides:

- one **Update library** action that checks first, explains the plan in plain
  language, and only writes after you confirm,
- automatic ROM-folder detection and a remembered last folder,
- a system selector and every maintenance switch under **Advanced options**,
- **Backups & restore** (restore gamelists, restore catalog, prune backups) in a
  separate window,
- a live details log that stays out of the way unless you open it or something
  fails.

See [GUI guide](docs/gui.md) for every button and option.

## Safety

- **Update library** checks first; nothing is written until you confirm.
- Modified files get timestamped backups. Catalog and gamelist restores create
  `*.recovery.bak` safety copies.
- `--keep-baks N` keeps the newest N backups per file (default `5`, `0` keeps
  all). Recovery backups are never pruned automatically.
- The release binaries are unsigned. Treat downloads like any other unsigned
  executable and verify the published SHA-256 checksums.

## Command line (optional)

Source users and tinkerers can run the scripts directly:

```bash
python3 gamelist_manager.py --dry-run    # preview
python3 gamelist_manager.py              # apply
python3 restore_gamelist.py --system nes # restore one gamelist
```

See the [CLI reference](docs/cli.md) for all commands, flags, diagnostics, and
the bisecting workflow.

## Requirements

- **GUI:** no Python required. macOS Apple Silicon or Windows.
- **CLI/source:** Python 3.9+; standard library only.
- Existing `root.dat` and `cubegm/fileinfo` if catalog synchronization is needed.
- Read/write access to the ROM folders and catalog files.

## Documentation

| Guide | Contents |
|---|---|
| [Install](docs/install.md) | Downloads, first launch, unsigned-app warnings. |
| [GUI guide](docs/gui.md) | Every button, option, and restore action. |
| [CLI reference](docs/cli.md) | Commands, flags, presets, diagnostics, examples. |
| [Device layout](docs/device-layout.md) | Folder layout, defaults, supported systems. |
| [Catalog format](docs/catalog-format.md) | `root.dat`, `fileinfo`, localization, preflight rules. |
| [Backups and restore](docs/backups.md) | Backup names, retention, restore, pruning. |
| [Troubleshooting](docs/troubleshooting.md) | Common failures and fixes. |
| [Development](docs/development.md) | Architecture, tests, lint, adding a system. |
| [Releasing](docs/releasing.md) | Local builds, GitHub Actions, artifacts, checksums. |
| [Refactor plan](docs/refactor-plan.md) | Historical notes from the refactor. |

## Development

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 -m ruff check .
```

The project stays flat: `gamelist_manager.py`, `catalog_sync.py`, `m15core.py`,
`systems.py`, the restore/prune scripts, `gui_support.py`, and `m15_gui.py`. See
[Development](docs/development.md) and [Releasing](docs/releasing.md).

## License

No license has been specified yet. Add one before redistributing the project or
its binaries.
