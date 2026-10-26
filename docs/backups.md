# Backups and restore

Every write can leave a timestamped backup. The main utility also prunes old
backups according to `--keep-baks`.

## Backup names

- `gamelist.xml.YYYYMMDD_HHMMSS.bak`
- `gamelist.xml.YYYYMMDD_HHMMSS_N.bak`
- `root.dat.YYYYMMDD_HHMMSS.bak`
- `fileinfo.YYYYMMDD_HHMMSS.bak`
- `*.recovery.bak` — safety copies made before a restore

Recovery backups are never pruned automatically by the main utility.

## Retention

`gamelist_manager.py --keep-baks N` keeps the newest N timestamped backups per
file family:

- per system `gamelist.xml` backups,
- the `root.dat` / `fileinfo` pair.

Default is `5`; `0` keeps all. Retention runs after every apply, including files
that were not rewritten in that run.

## Restore a gamelist

```bash
python3 restore_gamelist.py --dry-run            # preview
python3 restore_gamelist.py                       # restore all systems
python3 restore_gamelist.py --system nes
python3 restore_gamelist.py --recursive
```

Behavior:

- Matches `gamelist.xml.YYYYMMDD_HHMMSS.bak` and `..._N.bak`.
- Excludes its own `*.recovery.bak` files from source candidates.
- Tries the newest first; skips invalid (non-well-formed) XML.
- Saves the current file as `*.recovery.bak` before replacing it.
- Copies (does not move) the backup, validates the result, and rolls back on
  failure.

> **Exit codes:** returns non-zero if *any* inspected folder had no usable backup
> — which is normal when some system folders have no backups yet, even if every
> actual restore succeeded.

## Restore the catalog

Restores `root.dat` and `fileinfo` together from the newest valid matching
timestamped backup pair.

```bash
python3 restore_catalog.py --dry-run      # preview
python3 restore_catalog.py                # restore
```

- Pairs backups by timestamp and sequence number.
- Skips pairs where either file is missing or fails catalog validation.
- Saves the current `root.dat` and `fileinfo` as `*.recovery.bak` first.
- Rolls back both files if the restored pair fails validation.

The GUI has matching **Restore catalog (preview)** and **Restore catalog**
buttons.

## Delete old backups

```bash
python3 delete_gamelist_backups.py --dry-run       # preview (recommended)
python3 delete_gamelist_backups.py                 # XML backups in cwd
python3 delete_gamelist_backups.py --system nes
python3 delete_gamelist_backups.py --recursive
python3 delete_gamelist_backups.py --catalog       # also root.dat/fileinfo
```

Matches timestamped `gamelist.xml` backups, including numbered variants **and**
`.recovery.bak` files. **Deletion is the default behavior**, so always inspect
with `--dry-run` first.

`--catalog` also deletes `root.dat.*.bak` and `fileinfo.*.bak` backups. It is
independent of `--system`; catalog backups are global.

## Related

- [Catalog format](catalog-format.md)
- [GUI guide](gui.md)
- [Troubleshooting](troubleshooting.md)
