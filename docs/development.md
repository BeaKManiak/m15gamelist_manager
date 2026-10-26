# Development

## Project structure

The project stays flat and uses only the Python standard library at runtime.

| File | Purpose |
|---|---|
| `gamelist_manager.py` | Main utility: scans ROMs, maintains gamelists, runs catalog sync. |
| `catalog_sync.py` | Regenerates localized `root.dat` members and `fileinfo` counts. |
| `m15core.py` | Shared XML, folder-lookup, and backup-retention helpers. |
| `systems.py` | System registry and `FILEINFO_SYSTEM_ORDER`. |
| `restore_gamelist.py` | Restores a system gamelist from a timestamped backup. |
| `restore_catalog.py` | Restores `root.dat` + `fileinfo` as a pair. |
| `delete_gamelist_backups.py` | Finds and deletes timestamped backups. |
| `m15_gui.py` | Tkinter desktop app. |
| `tests/` | Pytest fixtures and regression tests. |

## Running from source

```bash
python3 gamelist_manager.py --help
python3 m15_gui.py
```

Python 3.9+ is required because `ET.indent` is used by the writer.

No third-party packages are needed to run the tools. Keep the modules together:
`gamelist_manager.py` imports `catalog_sync.py`, `m15core.py`, and `systems.py`.

## Tests and lint

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 -m ruff check .
```

Tests create temporary fixture collections and do not touch the real ROM library.
CI runs on Python 3.9, 3.13, and 3.14.

## Architecture notes

- `gamelist_manager.run(options)` performs the work and returns a `RunResult`.
  `main()` parses argv, calls `run`, prints the report, and returns an exit code.
- Processing is split into transform and commit phases so the catalog preflight
  can validate the post-transformation trees before any write.
- `catalog_sync` rebuilds the device catalog from all system gamelists. It skips
  the write when the content is unchanged.
- Backup retention is shared through `m15core.prune_backups`.
- The GUI calls the manager/restore/prune APIs directly; it does not patch
  `sys.argv`, `sys.stdout`, or the working directory.
- The GUI disables terminal spinners because windowed PyInstaller builds may not
  have a usable `sys.stdout`.

## Adding a system

1. Add the system and its extensions/metadata to `systems.py`.
2. Add the system to `FILEINFO_SYSTEM_ORDER` in the same file, in the exact order
   the device expects.
3. Add or update tests.
4. Update [Device layout](device-layout.md).

The registry raises an error at import time if the two lists disagree.

## Distribution model

- Released product: the frozen GUI app (`.app` / `.exe`).
- CLI: source-only for scripting and tinkering.
- No package layout and no external configuration file; PyInstaller follows the
  flat imports.

## Related

- [Releasing](releasing.md)
- [Catalog format](catalog-format.md)
- [CLI reference](cli.md)
