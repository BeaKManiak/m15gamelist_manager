# Releasing

## Build a standalone app locally

```bash
python3 -m pip install "pyinstaller==6.22.3"
pyinstaller --noconfirm --clean --windowed --name M15Manager \
  --add-data "README.md:." \
  --add-data "docs:docs" \
  m15_gui.py
# macOS:  dist/M15Manager.app
# Windows: dist/M15Manager.exe  (add --onefile; use ; in --add-data)
```

The result needs no Python installed on the target machine.

## GitHub Actions

Open **Actions → Build / release desktop app → Run workflow**. There are three
modes:

### Build only (default)

Leave **Publish a GitHub Release** unchecked.

- Tests and lint run.
- macOS and Windows builds are produced.
- Artifacts are uploaded to the workflow run.
- No tag is created.
- No version is bumped.
- No release is published.

Download the zips from the workflow run's **Artifacts** section. They expire
according to the repository's artifact retention setting.

### Build + release

Check **Publish a GitHub Release**.

- The workflow runs tests and lint first.
- It bumps the latest `vMAJOR.MINOR.PATCH` tag, or uses `tag_override`.
- `tag_override` must look like `v1.2.3` or `v1.2.3-rc1`.
- An existing manual tag is rejected.
- Pre-release suffixes are published as GitHub pre-releases.
- A `SHA256SUMS.txt` file is attached next to the zips.

### Tag push

Pushing a tag such as `v1.2.3` builds and publishes that exact tag. Tags matching
`v[0-9]*` are accepted; other `v*` tags are ignored.

## Artifacts

| Artifact | Platform |
|---|---|
| `M15Manager-ARM64.zip` | macOS, Apple Silicon |
| `M15Manager-windows.zip` | Windows |
| `SHA256SUMS.txt` | Checksums (release only) |

## CI

`.github/workflows/ci.yml` runs pytest and ruff on Python 3.9, 3.13, and 3.14 for
every push and pull request.

`.github/workflows/build-app.yml`:

- runs tests and lint on Python 3.13 before building,
- uses pinned PyInstaller 6.22.3,
- builds on `macos-15` (Apple Silicon) and `windows-2025`,
- serializes runs with a concurrency group,
- verifies the ad-hoc macOS signature,
- creates checksums for releases.

History:

- Intel macOS builds are not produced; GitHub retired the `macos-13` image.
- The macOS app is ad-hoc signed, not notarized.
- Windows binaries are unsigned.

## Signing

To remove first-launch warnings entirely you need:

- an Apple Developer ID certificate and notarization for macOS,
- a code-signing certificate for Windows.

Both require paid accounts/certificates and are outside the current workflow.

## Repository hygiene

Keep ROM files out of the repository. Only scripts, tests, and docs should be
committed; otherwise every CI run clones the whole collection.

## Related

- [Install](install.md)
- [Development](development.md)
