
#!/usr/bin/env python3
"""
Restore gamelist.xml files from timestamped backups.

Run from the root directory containing system folders (snes, gb, etc.).

Expected source backup names:
    gamelist.xml.YYYYMMDD_HHMMSS.bak
    gamelist.xml.YYYYMMDD_HHMMSS_N.bak

Safety backups created by this script:
    gamelist.xml.YYYYMMDD_HHMMSS.recovery.bak
    gamelist.xml.YYYYMMDD_HHMMSS_N.recovery.bak

Recovery is the default behavior. Use --dry-run to preview only.
"""

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


# Match updatelists backups, excluding this script's .recovery.bak files.
BACKUP_PATTERN = re.compile(
    r"^gamelist\.xml\."
    r"(?P<timestamp>\d{8}_\d{6})"
    r"(?:_(?P<sequence>\d+))?"
    r"\.bak$"
)


def valid_xml(path: Path) -> bool:
    """Return True if the file is well-formed XML."""
    try:
        ET.parse(path)
        return True
    except (ET.ParseError, OSError, UnicodeError):
        return False


def find_latest_valid_backup(system_dir: Path, *, output=print):
    """Return the newest valid timestamped backup, or None."""
    try:
        entries = list(system_dir.iterdir())
    except OSError as exc:
        output(f"ERROR: Cannot read directory {system_dir}: {exc}")
        return None

    candidates = []

    for path in entries:
        if not path.is_file():
            continue

        match = BACKUP_PATTERN.fullmatch(path.name)
        if not match:
            continue

        try:
            timestamp = datetime.strptime(
                match.group("timestamp"), "%Y%m%d_%H%M%S"
            )
        except ValueError:
            continue

        sequence = int(match.group("sequence") or 0)
        candidates.append((timestamp, sequence, path))

    # Newest timestamp first, then highest sequence number.
    candidates.sort(
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )

    for timestamp, sequence, path in candidates:
        if valid_xml(path):
            return path

        output(f"WARNING: Skipping invalid XML backup: {path.name}")

    return None


def make_recovery_backup(current_file: Path) -> Path:
    """Copy the current gamelist to a uniquely named safety backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    destination = current_file.with_name(
        f"gamelist.xml.{timestamp}.recovery.bak"
    )

    counter = 1
    while destination.exists():
        destination = current_file.with_name(
            f"gamelist.xml.{timestamp}_{counter}.recovery.bak"
        )
        counter += 1

    shutil.copy2(current_file, destination)
    return destination


def restore_system(system_dir: Path, dry_run: bool, *, output=print) -> bool:
    """Restore one system directory. Return whether it was processed."""
    if not system_dir.is_dir():
        output(f"ERROR: System directory does not exist: {system_dir}")
        return False

    current_file = system_dir / "gamelist.xml"
    backup = find_latest_valid_backup(system_dir, output=output)

    if backup is None:
        output(f"\nSKIP: No valid timestamped backup in {system_dir.name}")
        return False

    output(f"\nSystem: {system_dir.name}")
    output(f"  Selected backup: {backup.name}")

    if not valid_xml(backup):
        output("ERROR: Backup failed XML validation.")
        return False

    if dry_run:
        output("  DRY RUN: No files changed.")
        if current_file.exists():
            output("  Current gamelist.xml would be preserved before restore.")
        else:
            output("  gamelist.xml would be created from the selected backup.")
        return True

    safety_backup = None

    try:
        # Preserve the current file before replacing it.
        if current_file.exists():
            safety_backup = make_recovery_backup(current_file)
            output(f"  Safety backup: {safety_backup.name}")

        # Copy, rather than move, so the source backup remains intact.
        shutil.copy2(backup, current_file)

        # Verify the copied file.
        if not valid_xml(current_file):
            output("ERROR: Restored file failed XML validation.")

            # Attempt to roll back if an existing file was preserved.
            if safety_backup is not None:
                shutil.copy2(safety_backup, current_file)
                output("  Previous gamelist.xml has been restored from safety backup.")

            return False

        output("  RESTORED successfully.")
        return True

    except OSError as exc:
        output(f"ERROR: Restore failed for {system_dir.name}: {exc}")

        # If possible, restore the original file after a failed copy.
        if safety_backup is not None:
            try:
                shutil.copy2(safety_backup, current_file)
                output("  Previous gamelist.xml restored from safety backup.")
            except OSError as rollback_exc:
                output(f"CRITICAL: Rollback failed: {rollback_exc}")
                output(f"  Safety backup remains at: {safety_backup}")

        return False


def main(argv=None, root=None, *, output=print) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Restore gamelist.xml from the newest valid timestamped backup. "
            "Run from the root directory containing system folders."
        )
    )

    parser.add_argument(
        "--system",
        help="Restore only this system folder, e.g. snes or gb.",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search nested directories for system folders with backups.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the selected recoveries without changing files.",
    )

    args = parser.parse_args(argv)

    # Like updatelists, use the current working directory unless a root is given.
    root_path = Path.cwd().resolve() if root is None else Path(root).expanduser().resolve()
    root = root_path

    if args.system:
        # Accept a folder name, not a path outside the root.
        if (
            Path(args.system).name != args.system
            or args.system in (".", "..")
            or "/" in args.system
            or "\\" in args.system
        ):
            parser.error("--system must be a folder name, such as snes.")

        system_dirs = [root / args.system]

    elif args.recursive:
        # Find directories containing matching timestamped source backups.
        system_dirs = sorted(
            {
                backup.parent
                for backup in root.rglob("gamelist.xml.*.bak")
                if BACKUP_PATTERN.fullmatch(backup.name)
            }
        )

    else:
        # Inspect immediate child folders only.
        try:
            system_dirs = sorted(
                path for path in root.iterdir() if path.is_dir()
            )
        except OSError as exc:
            output(f"ERROR: Cannot read root directory {root}: {exc}")
            return 2

    if not system_dirs:
        output(f"No system directories found under {root}")
        return 1

    mode = "DRY RUN — no files will be changed" if args.dry_run else "RECOVERY"
    output(f"Root: {root}")
    output(f"Mode: {mode}")
    output(f"Systems to inspect: {len(system_dirs)}")

    successes = 0
    for system_dir in system_dirs:
        if restore_system(system_dir, args.dry_run, output=output):
            successes += 1

    output(f"\nFinished: {successes}/{len(system_dirs)} system(s) processed.")

    if args.dry_run:
        output("Preview only. Run without --dry-run to perform recovery.")

    return 0 if successes == len(system_dirs) else 1


if __name__ == "__main__":
    sys.exit(main())
