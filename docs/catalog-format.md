# Catalog format

The device catalog is made of two files:

- `root.dat` — a ZIP with localized game lists.
- `cubegm/fileinfo` — 25 counters.

`catalog_sync.py` rebuilds both from the system `gamelist.xml` files. The main
utility runs it after a non-dry-run pass.

## `root.dat`

A ZIP archive with exactly these three members, one per UI language:

| Member | Language |
|---|---|
| `fileinfo.001` | Simplified Chinese (`zh_CN`) |
| `fileinfo.002` | Traditional Chinese (`zh_TW`) |
| `fileinfo.003` | Korean (`ko_KR`) |

Each line has 6 tab-separated fields:

```text
system/rom.zip <TAB> "00803  Display Name" <TAB> "00803  DISPLAY NAME" <TAB> "00803  Localized Name" <TAB> Display Name <TAB> images/rom.png
```

Fields 2–4 carry a rendered `NNNNN␣␣` ID prefix (5 digits + 2 spaces), stripped
when existing localized titles are read back and preserved by ROM path.

When validating generated output, compare `root.dat` by its three uncompressed
member payloads, not by the archive bytes: ZIP headers include a timestamp and
change between runs. `gamelist.xml` and `fileinfo` are byte-stable.

## `cubegm/fileinfo`

25 comma-separated non-negative integers:

```text
<total games>,<reserved>,<per-system counts in FILEINFO_SYSTEM_ORDER>
```

`FILEINFO_SYSTEM_ORDER` is:

```text
arcade, fbneo, mame, atari2600, atari5200, atari7800, atarilynx, cps1, cps2,
cps3, pcengine, nes, nesh, gb, sfc, snes, gbc, gba, genesis, gamegear, megadrive,
ngpc, psx
```

The 2nd field is preserved as-is from the existing file (its meaning is not
documented in the scripts).

## Preconditions

Both files must already exist:

- `root.dat` must be a ZIP with exactly `fileinfo.001`, `fileinfo.002`,
  `fileinfo.003`.
- `fileinfo` must be exactly 25 comma-separated non-negative integers.
- A collection with zero games is valid; generated members are empty files.

The catalog validates that:

- each document has a `<gameList>` root,
- every game entry has a `<path>`,
- every `<gameid>` is numeric and globally unique,
- catalog paths are unique.

**Validation is all-or-nothing:** if any check fails, no catalog file is written.

The main utility also runs the same rules as a **preflight before writing any
gamelist**, including the catalog file formats, so a catalog-invalid collection
fails without changing files. The post-write validation remains in place.

## Localization and counts

Localized members are generated for `zh_CN`, `zh_TW`, and `ko_KR`. Existing
titles are preserved by ROM path where possible; otherwise the gamelist language
value (or `<name>`) is used.

`fileinfo` gets the new total and per-system counts in `FILEINFO_SYSTEM_ORDER`,
keeping the existing 2nd field.

Writes are validated, timestamped-backed-up, and rolled back if post-write
validation fails. If the generated content is identical to the installed
catalog, nothing is written and no backup is created.

Catalog backups follow `--keep-baks` (default 5). The newest backup of each file
is always kept.

## Custom paths

Override the paths when needed (CLI only; the GUI assumes the standard layout):

```bash
python3 gamelist_manager.py \
  --root /path/to/roms \
  --root-dat /path/to/root.dat \
  --fileinfo /path/to/fileinfo
```

## Related

- [Device layout](device-layout.md)
- [Backups and restore](backups.md)
- [Troubleshooting](troubleshooting.md)
