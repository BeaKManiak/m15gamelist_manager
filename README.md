# M15 ROM Collection Manager

A set of standard-library Python utilities for maintaining the ROM library of an
**M15** retro handheld: editing per-system `gamelist.xml` files, rebuilding the
device catalog (`root.dat` and `cubegm/fileinfo`), and managing backups and
restoration.

The tools scan system folders, add newly discovered ROMs, remove entries for
missing files, normalize metadata, deduplicate, sort, and keep the device catalog
synchronized. The main script is heavily switchable on purpose — the M15 is fussy
about which change broke it, so each behavior can be toggled to bisect a problem.

## Features

- **Automatic ROM scanning:** detect supported ROM files in configured system
  directories (non-recursive; `._*` sidecars ignored).
- **Gamelist management:** add missing games and remove entries whose ROM files
  no longer exist.
- **Metadata normalization:** assign missing game IDs and strip numeric prefixes
  from language-specific name fields.
- **Duplicate removal:** dedupe by ROM path, game ID, both, or neither.
- **Sorting:** sort entries alphabetically by `<name>`.
- **Orphaned image handling:** report images no longer referenced by any entry and
  optionally delete them.
- **XML safety:** validate before/after writing, preserve an existing BOM, write
  via temp files, and back up first.
- **Catalog synchronization:** rebuild `root.dat` and `fileinfo` from the
  gamelists.
- **Backup utilities:** preview or delete old backups, and restore a gamelist from
  a valid backup with automatic rollback.

## Requirements

- Python 3.9+. (`ET.indent`, used by the writer, was added in 3.9.)
- Read/write access to the ROM directories and the catalog files.
- Existing `root.dat` and `fileinfo` if catalog synchronization is required.

No third-party packages are needed to run the tools. Keep the Python modules
together: `gamelist_manager.py` imports `catalog_sync.py`, `m15core.py`, and
`systems.py`. Quick check:

```bash
python3 -c "import catalog_sync, gamelist_manager, m15core, systems; print('ok')"
```

## Project files

| File | Purpose |
|---|---|
| `gamelist_manager.py` | Main utility: scans ROMs, maintains system gamelists, then triggers catalog sync. |
| `catalog_sync.py` | Library that regenerates localized `root.dat` members and `fileinfo` counts. Not run directly. |
| `m15core.py` | Shared XML, folder-lookup, and backup-retention helpers. |
| `systems.py` | System registry and the device's `FILEINFO_SYSTEM_ORDER`. |
| `restore_gamelist.py` | Restores a system's `gamelist.xml` from the newest valid timestamped backup. |
| `delete_gamelist_backups.py` | Finds and deletes matching timestamped gamelist backups, with a dry-run option. |
| `m15_gui.py` | Optional Tkinter desktop GUI. It is the released desktop app. |
| `tests/` | Pytest fixtures and characterization/regression tests. |
| `pyproject.toml`, `requirements-dev.txt` | Test and lint configuration (development only). |
| `.github/workflows/ci.yml` | Tests and lint on push and pull request. |
| `.github/workflows/build-app.yml` | Packages `m15_gui.py` into macOS/Windows apps. |

## Distribution

- The released product is the self-contained GUI app (`.app` on macOS, `.exe` on
  Windows). End users do **not** install Python.
- The command-line tools stay in the repository as source for scripting and
  tinkering. They are not shipped as separate executables.
- The GUI assumes the standard catalog layout shown below; it does not expose
  custom `root.dat` or `fileinfo` paths.

## Directory layout

Run the CLI tools from the folder that contains the system folders. By default the
main script uses its own directory as the ROM root.

```text
/Volumes/M15/
├── cubegm/
│   └── fileinfo                 # 25 comma-separated counters (outside roms/)
└── roms/                        # <- run the scripts here
    ├── gamelist_manager.py
    ├── catalog_sync.py
    ├── m15core.py
    ├── systems.py
    ├── restore_gamelist.py
    ├── delete_gamelist_backups.py
    ├── README.md
    ├── root.dat                 # ZIP: fileinfo.001/.002/.003
    ├── arcade/
    │   ├── gamelist.xml
    │   ├── images/              # images live per system folder
    │   └── *.zip
    ├── nes/
    │   └── ...
    ├── snes/
    │   └── ...
    └── psx/
        └── ...
```

Other defaults used by `gamelist_manager.py`:

- `root.dat`: `<root>/root.dat`
- `fileinfo`: `<root>/../cubegm/fileinfo`

Both can be overridden with `--root-dat` and `--fileinfo`.

## Supported systems and ROM extensions

Only files **directly inside** each system folder are scanned (no recursion), and
files starting with `._` are ignored.

| System | Extensions |
|---|---|
| `arcade` | `.fba`, `.zip` |
| `atari2600` | `.a26` |
| `atari5200` | `.zip` |
| `atari7800` | `.a78`, `.zip` |
| `atarilynx` | `.zip` |
| `cps1` | `.fba`, `.zip` |
| `cps2` | `.fba`, `.zip` |
| `cps3` | `.zip`, `.fba` |
| `fbneo` | `.zip`, `.fba` |
| `gb` | `.zip`, `.gb` |
| `gba` | `.zip` |
| `gbc` | `.zip` |
| `gamegear` | `.zip` |
| `genesis` | `.zip` |
| `mame` | `.zip` |
| `megadrive` | `.zip` |
| `nes` | `.zip` |
| `nesh` | `.zip` |
| `ngpc` | `.zip` |
| `pcengine` | `.zip` |
| `psx` | `.img`, `.pbp`, `.iso`, `.bin`, `.chd`, `.cue`, `.ccd`, `.mdf`, `.mds`, `.nrg`, `.cso`, `.zso`, `.ecm` |
| `sfc` | `.zip` |
| `snes` | `.zip` |

## Device catalog formats

**`root.dat`** — a ZIP archive with exactly these three members, one per UI
language:

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

**`cubegm/fileinfo`** — 25 comma-separated non-negative integers:

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

## Main utility: `gamelist_manager.py`

```bash
python3 gamelist_manager.py
```

With no arguments it uses the script's directory as the root and processes all
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

# Parse and re-save only (all features off + force write)
python3 gamelist_manager.py --roundtrip

# Keep only the newest 3 backups per file (0 = keep all)
python3 gamelist_manager.py --keep-baks 3
```

> **`--roundtrip` is not read-only.** It disables the individual features but
> *forces* an XML write. It also skips catalog preflight and catalog sync, so it
> is safe for bisecting invalid XML. Combine with `--dry-run` to preview.

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

New entries get a generated game ID, a `<path>`, an image path
`./images/<rom-filename-without-extension>.png`, system-specific metadata
(`video_id`, `class_type`, `game_type`, `timer`, and for `psx` a `core`), and the
four language fields.

Non-numeric `<gameid>` values are rejected by preflight; they cannot produce a
valid device catalog. Fix or remove them before applying.

### Bisecting a device problem

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

## Catalog synchronization: `catalog_sync.py`

Imported by the main utility and called after a non-dry-run pass. It rebuilds:

- Localized data in `root.dat`.
- Game counts in `fileinfo`.

### Preconditions

Both files must already exist:

- `root.dat` must be a ZIP with exactly `fileinfo.001`, `fileinfo.002`,
  `fileinfo.003`.
- `fileinfo` must be exactly 25 comma-separated non-negative integers.
- A collection with zero games is valid; generated members are empty files.

It reads all configured gamelists and validates that:

- Each document has a `<gameList>` root.
- Every game entry has a `<path>`.
- Every `<gameid>` is numeric and globally unique.
- Catalog paths are unique.

**Validation is all-or-nothing:** if any check fails, no catalog file is written.

The main utility also runs the same rules as a **preflight before writing any
gamelist**, including the catalog file formats, so a catalog-invalid collection
fails without changing files. The post-write validation above remains in place.

### Localization and counts

Localized members are generated for `zh_CN`, `zh_TW`, and `ko_KR`. Existing
titles are preserved by ROM path where possible; otherwise the gamelist language
value (or `<name>`) is used. `fileinfo` gets the new total and per-system counts
in `FILEINFO_SYSTEM_ORDER`, keeping the existing 2nd field.

Writes are validated, timestamped-backed-up, and rolled back if post-write
validation fails. If the generated content is identical to the installed
catalog, nothing is written and no backup is created.

Catalog backups follow `--keep-baks` (default 5). The newest backup of each file
is always kept.

Override the paths when needed (CLI only; the GUI assumes the standard layout):

```bash
python3 gamelist_manager.py \
  --root /path/to/roms \
  --root-dat /path/to/root.dat \
  --fileinfo /path/to/fileinfo
```

## Restoring a gamelist: `restore_gamelist.py`

Restores the newest valid timestamped backup in each system folder.

```bash
python3 restore_gamelist.py --dry-run            # preview
python3 restore_gamelist.py                       # restore all systems
python3 restore_gamelist.py --system nes
python3 restore_gamelist.py --recursive
```

### Behavior

- Matches `gamelist.xml.YYYYMMDD_HHMMSS.bak` and `..._N.bak`.
- Excludes its own `*.recovery.bak` files from source candidates.
- Tries the newest first; skips invalid (non-well-formed) XML.
- Saves the current file as `*.recovery.bak` before replacing it.
- Copies (does not move) the backup, validates the result, and rolls back on
  failure.

> **Exit codes:** returns non-zero if *any* inspected folder had no usable backup
> — which is normal when some system folders have no backups yet, even if every
> actual restore succeeded.

## Deleting old backups: `delete_gamelist_backups.py`

```bash
python3 delete_gamelist_backups.py --dry-run       # preview (recommended)
python3 delete_gamelist_backups.py                 # delete in cwd
python3 delete_gamelist_backups.py --system nes
python3 delete_gamelist_backups.py --recursive
```

Matches timestamped `gamelist.xml` backups, including numbered variants **and**
`.recovery.bak` files. **Deletion is the default behavior**, so always inspect
with `--dry-run` first.

The main utility prunes only its own timestamped XML/catalog backups according
to `--keep-baks`; it never deletes `.recovery.bak` files. Use this tool when you
want to remove those too.

## Recommended workflow

1. **Preview** the maintenance run:

   ```bash
   python3 gamelist_manager.py --dry-run
   ```

2. **Review** the reported changes (adds, removals, dedupes, sorts, orphan
   images). A catalog preflight failure means nothing was written; fix the
   reported entries first.

3. **Apply**:

   ```bash
   python3 gamelist_manager.py
   ```

4. **Verify** that `root.dat` and `fileinfo` were rebuilt successfully and that
   the device sees the expected library.

5. **Restore** a single system if something looks wrong:

   ```bash
   python3 restore_gamelist.py --system nes
   ```

6. **Prune backups** only once you're confident:

   ```bash
   python3 delete_gamelist_backups.py --dry-run
   python3 delete_gamelist_backups.py
   ```

## Desktop app (GUI)

`m15_gui.py` is the graphical front-end and the released desktop app. It calls
the manager's `Options`/`run()` API directly on a background thread and streams
output into a log pane; it does not patch `sys.argv`, `sys.stdout`, or the
working directory.

It provides, for the selected ROM folder:

- System selector (all systems or one), `--dedup`, and XML-declaration choices.
- Checkboxes mirroring every feature switch (remove missing, add, IDs, normalize,
  sort, indent, force write, delete orphan images).
- A **Keep backups** control matching `--keep-baks` (`0` keeps all).
- **Preview (dry run)** and **Apply** buttons, plus **Restore gamelist** and
  **Delete backups** with preview variants.
- A live output log and an auto-detected ROM folder (looks for `root.dat` plus
  system folders under `/Volumes`).

The GUI assumes the standard catalog layout; it does not expose custom
`root.dat`/`fileinfo` paths. Use the CLI for those.

### Run it from source

```bash
python3 m15_gui.py
```

### Build a standalone app locally

```bash
python3 -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name M15Manager m15_gui.py
# macOS:  dist/M15Manager.app
# Windows: dist/M15Manager.exe  (add --onefile)
```

The result needs no Python installed on the target machine.

### Tests and lint

Development tooling is optional and never imported by the shipped scripts:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
python3 -m ruff check .
```

Tests use temporary fixture collections and do not touch the real ROM library.

### Build via GitHub Actions

Push the repo and open **Actions → Build desktop app → Run workflow**. The
workflow also runs automatically when you push a `v*` tag, and in that case
attaches the builds to a GitHub Release.

It produces, for each platform:

| Artifact | Platform |
|---|---|
| `M15Manager-ARM64.zip` | macOS, Apple Silicon |
| `M15Manager-windows.zip` | Windows |

### First-launch notes (unsigned apps)

The builds are **not code-signed or notarized**, because that requires a paid
Apple Developer account (and a Windows certificate). Users will see a warning
the first time:

- **macOS:** "Apple cannot check it for malicious software." Right-click the app
  → **Open** → **Open**, or run
  `xattr -dr com.apple.quarantine /Applications/M15Manager.app`.
- **Windows:** SmartScreen "Windows protected your PC" → **More info** →
  **Run anyway**.

To remove these warnings entirely, add a Developer ID certificate and notarize
(macOS) or sign the executable (Windows) inside the workflow.

### CI notes

- `.github/workflows/ci.yml` runs pytest and ruff on Python 3.9 and 3.14 for
  every push and pull request.
- `.github/workflows/build-app.yml` builds on `macos-15` (Apple Silicon) and
  `windows-2025`, using Python 3.13 with Tkinter.
- Intel macOS builds are not produced; GitHub retired the `macos-13` image.
- Keep ROM files out of the repository; only the scripts need to be committed,
  otherwise every CI run clones the whole collection.

## Troubleshooting

### Catalog preflight fails

The run stopped before changing any files. Check the listed entries:

- Every game entry needs a non-empty `<path>`.
- Every `<gameid>` must be numeric (for example `42`, not `game42`) and globally
  unique across all systems.
- Two entries cannot resolve to the same catalog path.
- Every configured system folder must exist with a readable `gamelist.xml`.
- `root.dat` and `fileinfo` must exist and match the documented formats.

A dry run performs the same preflight, so you can iterate without touching the
device.

### Catalog synchronization fails

Check that:

- `root.dat` exists and is a valid ZIP with exactly `fileinfo.001`, `.002`, `.003`.
- `fileinfo` exists and is exactly 25 comma-separated non-negative integers.
- All configured gamelists are valid XML with a `<gameList>` root.
- Every entry has a `<path>` and a numeric, globally unique `<gameid>`.
- No catalog paths are duplicated.

If the catalog step fails after the XMLs were written, the gamelists are newer
than `root.dat`/`fileinfo`. Restore the backups reported in the output.

### A ROM is not added

- It must be directly inside the system folder (no subfolders).
- Its extension must be supported for that system.
- The filename must not start with `._`.
- The run must not use `--skip-add`.
- The correct `--root` and `--system` must be selected.

### An entry was removed

Entries whose ROM files are missing are removed by default. Keep them with:

```bash
python3 gamelist_manager.py --skip-remove-missing
```

### A restore skips a backup

Candidate backups that are not well-formed XML are skipped, so an older valid
backup may be chosen. `.recovery.bak` files are never used as sources.

### Preview without modifying anything

```bash
python3 gamelist_manager.py --dry-run
python3 restore_gamelist.py --system nes --dry-run
python3 delete_gamelist_backups.py --dry-run
```

## Safety notes

- Keep an off-device copy of `root.dat` and `cubegm/fileinfo` before large runs.
- Always `--dry-run` first where available.
- Be cautious with `--delete-orphaned-images`; confirm the images are genuinely
  unused.
- Catalog synchronization expects a consistent set of gamelists and stops on
  invalid or duplicate IDs/paths. Preflight catches this before any write.
- `--roundtrip` forces a write; don't treat it as a preview.
- The default `--keep-baks 5` prunes older timestamped backups. Recovery backups
  are never pruned automatically; keep the ones you need.
- Keep recovery backups until the resulting gamelists and catalogs are verified.
- Eject the volume cleanly before disconnecting the M15's storage.

## License

No license is specified in the scripts. Add one before distributing.
