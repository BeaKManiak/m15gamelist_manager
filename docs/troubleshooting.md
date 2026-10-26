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
- The GUI’s **Keep backups** control mirrors it.
- Use `delete_gamelist_backups.py --dry-run` first, then apply.
- Add `--catalog` to include `root.dat`/`fileinfo` backups.
- Recovery backups are never pruned automatically; delete them explicitly only
  after verifying the device.

## The GUI will not open on macOS

The app is ad-hoc signed, not notarized. Right-click → **Open** → **Open**, or:

```bash
xattr -dr com.apple.quarantine /Applications/M15Manager.app
```

## Windows SmartScreen warning

Click **More info** → **Run anyway**. The binaries are unsigned.

## Preview exits non-zero

During a preview this often just means at least one inspected system folder had
no usable backup. Check the log for the specific message.

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
