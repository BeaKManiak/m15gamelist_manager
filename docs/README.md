# M15 ROM Collection Manager — documentation

Start with the [main README](../README.md) for download and quick start.

| Guide | Contents |
|---|---|
| [Install](install.md) | Downloads, first launch, unsigned-app warnings. |
| [GUI guide](gui.md) | Every button, option, and restore action. |
| [CLI reference](cli.md) | Commands, flags, presets, diagnostics, examples. |
| [Device layout](device-layout.md) | Folder layout, defaults, supported systems. |
| [Catalog format](catalog-format.md) | `root.dat`, `fileinfo`, localization, preflight rules. |
| [Backups and restore](backups.md) | Backup names, retention, restore, pruning. |
| [Troubleshooting](troubleshooting.md) | Common failures and fixes. |
| [Development](development.md) | Architecture, tests, lint, adding a system. |
| [Releasing](releasing.md) | Local builds, GitHub Actions, artifacts, checksums. |
| [Refactor plan](refactor-plan.md) | Historical notes from the refactor. |

## Distribution model

- The released product is the self-contained GUI app (`.app` on macOS, `.exe` on
  Windows). End users do **not** install Python.
- The command-line tools stay in the repository as source for scripting and
  tinkering. They are not shipped as separate executables.
- The GUI assumes the standard catalog layout; it does not expose custom
  `root.dat` or `fileinfo` paths. Use the CLI for non-standard layouts.
