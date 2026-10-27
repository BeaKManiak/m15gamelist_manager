# Install and first launch

## Download

Open the [latest release](https://github.com/BeaKManiak/m15gamelist_manager/releases/latest)
and download:

| Platform | File |
|---|---|
| macOS, Apple Silicon | `M15Manager-ARM64.zip` |
| Windows | `M15Manager-windows.zip` |

The GUI is self-contained. **Do not install Python** to use the released app.

Build-only artifacts from a manual GitHub Actions run are available under that
workflow run. They are not releases and expire according to the repository's
artifact retention setting.

## macOS

1. Unzip `M15Manager-ARM64.zip`.
2. Move `M15Manager.app` to Applications (optional).
3. The build is ad-hoc signed, not notarized. On first launch macOS may say:
   **“Apple cannot check it for malicious software.”**
4. Right-click the app → **Open** → **Open**, or run:

   ```bash
   xattr -dr com.apple.quarantine /Applications/M15Manager.app
   ```

Only Apple Silicon is built. Intel macOS builds are not produced.

## Windows

1. Unzip `M15Manager-windows.zip`.
2. Run `M15Manager.exe`.
3. SmartScreen may say **“Windows protected your PC.”**
   Click **More info** → **Run anyway**.

The build is unsigned. Verify the SHA-256 checksum from the release before
running it.

## Checksums

Release pages include `SHA256SUMS.txt` for the zipped builds.

macOS/Linux:

```bash
shasum -a 256 M15Manager-ARM64.zip
```

Windows PowerShell:

```powershell
Get-FileHash .\M15Manager-windows.zip -Algorithm SHA256
```

Compare the result with the release's `SHA256SUMS.txt`.

## First run

1. Connect the M15 storage.
2. Open **M15Manager**. It reuses the last folder or finds the card itself.
3. If needed, use **Change…** to select the folder that contains `root.dat` and
   the system folders — usually the `roms` folder on the device.
4. Click **Update library**.
5. Review the summary, then confirm. Nothing is written before you confirm.

The GUI expects the standard layout:

```text
M15 storage/
├── cubegm/
│   └── fileinfo
└── roms/
    ├── root.dat
    └── <system folders>/
```

If your catalog files live elsewhere, use the CLI with `--root-dat` and
`--fileinfo`.

## Removing the warnings completely

That requires a paid Apple Developer ID and notarization on macOS, and a code
signing certificate on Windows. The workflows are set up for ad-hoc signing only.
