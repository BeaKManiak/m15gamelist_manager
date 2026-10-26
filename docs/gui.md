# GUI guide

`m15_gui.py` is the desktop front-end and the released app. It calls the manager,
restore, and prune APIs directly on a background thread and streams output into a
log pane. It does not patch `sys.argv`, `sys.stdout`, or the working directory.

## Main window

For the selected ROM folder:

- **System:** all systems or one system.
- **Deduplicate:** `none`, `path`, `gameid`, or `both`.
- **XML declaration:** ElementTree default or the double-quoted declaration.
- **Feature checkboxes:** remove missing, add, IDs, normalize, sort, indent,
  force write, delete orphan images.
- **Keep backups:** newest N per file; `0` keeps all.
- **Preview (dry run)** and **Apply changes**.
- **Restore gamelist (preview)** and **Restore gamelist**.
- **Restore catalog (preview)** and **Restore catalog**.
- **Delete backups (preview)** and **Delete backups**, with an option to include
  catalog backups.
- A live output log and automatic ROM-folder detection.

The GUI assumes the standard catalog layout. It does not expose custom
`root.dat`/`fileinfo` paths; use the CLI for those.

## Preview vs apply

- **Preview** runs the full processing and catalog preflight but writes nothing.
  It does not create backups, delete images, or touch the catalog.
- **Apply** asks for confirmation, then writes only if the catalog preflight
  passes. If preflight fails, no gamelist, image, or catalog file changes.

A catalog preflight failure lists the offending entries. Typical causes are a
non-numeric `<gameid>`, duplicate IDs or paths, or a missing `<path>`.

## Restore gamelist

Replaces a system's `gamelist.xml` with the newest valid timestamped backup.

- Preview shows the selected backup without changing files.
- Apply saves the current file as `*.recovery.bak` first.
- Invalid backups are skipped.
- Non-zero exit codes during a preview often just mean a folder had no backup.

## Restore catalog

Restores `root.dat` and `fileinfo` together from the newest valid matching backup
pair.

- Pairs are matched by timestamp and sequence number.
- The current catalog files are saved as `*.recovery.bak` first.
- Both files are rolled back if the restored pair fails validation.

## Delete backups

Deletion is permanent. Always run the preview first.

- Default: timestamped `gamelist.xml.*.bak` files, including numbered variants and
  `.recovery.bak`.
- **Also delete catalog backups:** includes `root.dat.*.bak` and
  `fileinfo.*.bak`.
- `--system` scopes XML backups to one folder; catalog backups are global.

The main utility prunes its own timestamped backups after an apply according to
**Keep backups**. It never deletes `.recovery.bak` files automatically.

## Run from source

```bash
python3 m15_gui.py
```

Requires Python 3.9+ with tkinter.

## Related

- [CLI reference](cli.md)
- [Backups and restore](backups.md)
- [Troubleshooting](troubleshooting.md)
