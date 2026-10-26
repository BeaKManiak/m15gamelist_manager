# CLI reference

The CLI is source-only. It is intended for scripting, debugging, and non-standard
catalog layouts. Released users should normally use the GUI.

## Requirements

- Python 3.9+.
- Standard library only.
- Existing `root.dat` and `cubegm/fileinfo` for catalog synchronization.
- Read/write access to the ROM folders and catalog files.

Keep the modules together: `gamelist_manager.py` imports `catalog_sync.py`,
`m15core.py`, and `systems.py`.

Quick check:

```bash
python3 -c "import catalog_sync, gamelist_manager, m15core, systems; print('ok')"
```

## Main utility

```bash
python3 gamelist_manager.py
```

With no arguments it uses the script's directory as the ROM root and processes all
configured systems.

### Common commands

```bash
# Preview everything without writing
python3 gamelist_manager.py --dry-run

# Process a single system
python3 gamelist_manager.py --system nes

# Use a different ROM root
python3 gamelist_manager.py --root /path/to/roms

# Delete orphan images without prompting
python3 gamelist_manager.py --delete-orphaned-images

# Keep entries whose ROM files are missing
python3 gamelist_manager.py --skip-remove-missing

# Parse and re-save XML only (skips preflight and catalog sync)
python3 gamelist_manager.py --roundtrip

# Keep only the newest 3 backups per file (0 = keep all)
python3 gamelist_manager.py --keep-baks 3
```

> **`--roundtrip` is not read-only.** It disables the individual features but
> *forces* an XML write. It skips catalog preflight and catalog sync, so it is
> safe for bisecting invalid XML. Combine with `--dry-run` to preview.

> **`--system` only changes one system.** Duplicate detection and ID allocation
> still use every system, so a new ID cannot collide with another system. The
> catalog is still rebuilt from all systems.

> **Diagnostics:** `--skip-preflight` writes even when the catalog would reject
> the XML, and `--skip-catalog` leaves `root.dat`/`fileinfo` untouched. Both are
> for debugging only and can leave the catalog stale.

### Command-line options

| Option | Description |
|---|---|
| `--root PATH` | ROM collection root (default: the script's directory). |
| `--system NAME` | Process only the named system (IDs still come from the global pool). |
| `--dry-run` | Preview changes and run catalog preflight; no writes, no catalog sync. |
| `--delete-orphaned-images` | Delete orphan images without prompting. |
| `--no-prompt` | Report orphan images without asking (never deletes). |
| `--root-dat PATH` | Path to `root.dat` (default `<root>/root.dat`). |
| `--fileinfo PATH` | Path to `fileinfo` (default `<root>/../cubegm/fileinfo`). |
| `--skip-preflight` | Diagnostics: write even if catalog preflight fails. |
| `--skip-catalog` | Diagnostics: do not rebuild `root.dat`/`fileinfo`. |

### Feature switches

| Option | Effect |
|---|---|
| `--skip-remove-missing` | Keep entries whose ROM file is missing. |
| `--skip-add` | Do not add newly discovered ROMs. |
| `--skip-ids` | Do not add missing `<gameid>` values. |
| `--skip-normalize` | Do not strip numeric prefixes from titles. |
| `--skip-sort` | Do not sort alphabetically. |
| `--dedup {none,path,gameid,both}` | Duplicate criteria (default `both`). |

### Writer options

| Option | Effect |
|---|---|
| `--no-indent` | Skip `ET.indent` whitespace reformatting. |
| `--xml-declaration {et,double}` | `et` = single-quoted ElementTree default; `double` = `<?xml version="1.0" encoding="utf-8"?>`. |
| `--force-write` | Write even if nothing changed. |
| `--keep-baks N` | Keep the newest N timestamped backups per file (default `5`; `0` = keep all). Recovery backups are never pruned. |

### What the main utility does

Per system, subject to the selected options:

1. Scans the system folder for supported ROM files.
2. Removes entries whose referenced ROM files are missing.
3. Adds entries for newly found ROM files.
4. Assigns `<gameid>` to entries lacking one (reuses a safe existing `<id>`, else
   allocates from the global max + 1 across all systems).
5. Strips numeric prefixes from the `zh_CN`, `en_US`, `zh_TW`, and `ko_KR` fields.
6. Removes duplicate entries per `--dedup`.
7. Reports orphaned images and deletes them only with `--delete-orphaned-images`
   (or after a `y` answer at the prompt).
8. Sorts entries alphabetically by `<name>`.
9. **Catalog preflight:** validates the transformed gamelists before writing
   anything. Every entry needs a `<path>` and a numeric, globally unique
   `<gameid>`. If preflight fails, no gamelist, image, or catalog file changes.
10. Validates and safely writes modified gamelists (temp file, timestamped backup,
    BOM preserved), keeping the newest `--keep-baks` backups.
11. After all systems, rebuilds `root.dat` and `fileinfo` (unless `--dry-run`).
    An unchanged catalog is not rewritten and creates no backup.
12. Enforces `--keep-baks` across XML and catalog backups, including files that
    were not rewritten in this run.

New entries get a generated game ID, a `<path>`, an image path
`./images/<rom-filename-without-extension>.png`, system-specific metadata
(`video_id`, `class_type`, `game_type`, `timer`, and for `psx` a `core`), and the
four language fields.

Non-numeric `<gameid>` values are rejected by preflight; they cannot produce a
valid device catalog. Fix or remove them before applying.

### Bisecting a device problem

The M15 is fussy about which change broke it, so every behavior can be toggled.

```bash
# 1. Does a pure parse/save break it? (XML only; catalog untouched)
python3 gamelist_manager.py --roundtrip

# Same thing as a preview:
python3 gamelist_manager.py --roundtrip --dry-run

# 2. Re-enable one behavior (e.g. sorting only):
python3 gamelist_manager.py --skip-remove-missing --skip-add --skip-ids \
    --skip-normalize --dedup none --dry-run

# 3. Full apply:
python3 gamelist_manager.py
```

### Recommended workflow

1. **Preview:**

   ```bash
   python3 gamelist_manager.py --dry-run
   ```

2. **Review** the reported changes (adds, removals, dedupes, sorts, orphan
   images). A catalog preflight failure means nothing was written; fix the
   reported entries first.

3. **Apply:**

   ```bash
   python3 gamelist_manager.py
   ```

4. **Verify** that `root.dat` and `fileinfo` were rebuilt successfully and that
   the device sees the expected library.

5. **Restore** a single system if something looks wrong:

   ```bash
   python3 restore_gamelist.py --system nes
   ```

6. **Prune backups** only once you're confident. See
   [Backups and restore](backups.md).

## Related

- [Device layout](device-layout.md)
- [Catalog format](catalog-format.md)
- [Backups and restore](backups.md)
- [Troubleshooting](troubleshooting.md)
