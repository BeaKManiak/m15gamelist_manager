# Device layout and supported systems

## Directory layout

Run the CLI tools from the folder that contains the system folders. By default the
main script uses its own directory as the ROM root.

```text
/Volumes/M15/
├── cubegm/
│   └── fileinfo                 # 25 comma-separated counters (outside roms/)
└── roms/                        # <- select/run here
    ├── gamelist_manager.py
    ├── catalog_sync.py
    ├── m15core.py
    ├── systems.py
    ├── restore_gamelist.py
    ├── restore_catalog.py
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

Defaults used by `gamelist_manager.py`:

- `root.dat`: `<root>/root.dat`
- `fileinfo`: `<root>/../cubegm/fileinfo`

Both can be overridden with `--root-dat` and `--fileinfo`.

The GUI assumes this standard layout. The CLI supports overrides.

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

The registry lives in `systems.py`. The same file defines
`FILEINFO_SYSTEM_ORDER`, which must stay in sync with the device catalog.

## Related

- [Catalog format](catalog-format.md)
- [CLI reference](cli.md)
- [Troubleshooting](troubleshooting.md)
