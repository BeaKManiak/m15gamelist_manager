#!/usr/bin/env python3
"""Restore root.dat and fileinfo from a matching timestamped backup pair."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from catalog_sync import catalog_file_issues

BACKUP_PATTERN = re.compile(
    r"^(?P<base>root\.dat|fileinfo)\."
    r"(?P<timestamp>\d{8}_\d{6})"
    r"(?:_(?P<sequence>\d+))?\.bak$"
)


def _backup_key(path: Path):
    match = BACKUP_PATTERN.fullmatch(path.name)
    if not match:
        return None
    return (
        match.group("timestamp"),
        int(match.group("sequence") or 0),
        match.group("base"),
    )


def find_backup_pairs(root_dat: Path, fileinfo_path: Path):
    """Return valid (root.dat, fileinfo) backup pairs, newest first."""
    candidates = {}
    for target in (root_dat, fileinfo_path):
        for path in target.parent.glob(f"{target.name}.*.bak"):
            if not path.is_file():
                continue
            key = _backup_key(path)
            if key is None:
                continue
            base = key[2]
            pair_key = (key[0], key[1])
            candidates.setdefault(pair_key, {})[base] = path

    pairs = []
    for (timestamp, sequence), files in candidates.items():
        if set(files) != {"root.dat", "fileinfo"}:
            continue
        pairs.append((timestamp, sequence, files["root.dat"], files["fileinfo"]))
    pairs.sort(key=lambda item: (item[0], item[1]), reverse=True)

    valid = []
    for _timestamp, _sequence, root_backup, info_backup in pairs:
        if not catalog_file_issues(root_backup, info_backup):
            valid.append((root_backup, info_backup))
    return valid


def make_recovery_backup(current_file: Path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = current_file.with_name(
        f"{current_file.name}.{timestamp}.recovery.bak"
    )
    counter = 1
    while destination.exists():
        destination = current_file.with_name(
            f"{current_file.name}.{timestamp}_{counter}.recovery.bak"
        )
        counter += 1
    shutil.copy2(current_file, destination)
    return destination


def restore_catalog(root_dat: Path, fileinfo_path: Path, dry_run=False, *, output=print):
    """Restore the newest valid catalog backup pair."""
    root_dat = Path(root_dat)
    fileinfo_path = Path(fileinfo_path)
    pairs = find_backup_pairs(root_dat, fileinfo_path)
    if not pairs:
        output("SKIP: No valid root.dat + fileinfo backup pair found.")
        return False

    root_backup, info_backup = pairs[0]
    output(f"Selected backup pair: {root_backup.name} + {info_backup.name}")

    if dry_run:
        output("  DRY RUN: No files changed.")
        if root_dat.exists() or fileinfo_path.exists():
            output("  Current catalog files would be preserved before restore.")
        else:
            output("  Catalog files would be created from the selected backups.")
        return True

    recovery = []
    preexisting = {
        current for current in (root_dat, fileinfo_path) if current.exists()
    }
    try:
        for current in (root_dat, fileinfo_path):
            if current.exists():
                backup = make_recovery_backup(current)
                recovery.append((current, backup))
                output(f"  Safety backup: {backup.name}")

        shutil.copy2(root_backup, root_dat)
        shutil.copy2(info_backup, fileinfo_path)

        issues = catalog_file_issues(root_dat, fileinfo_path)
        if issues:
            raise ValueError("; ".join(issues))

        output("  RESTORED successfully.")
        return True
    except Exception as exc:
        output(f"ERROR: Catalog restore failed: {exc}")
        for current, backup in recovery:
            try:
                shutil.copy2(backup, current)
                output(f"  Restored previous {current.name} from safety backup.")
            except OSError as rollback_exc:
                output(f"CRITICAL: Rollback failed for {current.name}: {rollback_exc}")
        for current in (root_dat, fileinfo_path):
            if current not in preexisting and current.exists():
                try:
                    current.unlink()
                except OSError:
                    pass
        return False


def main(argv=None, root=None, root_dat=None, fileinfo=None, *, output=print) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Restore root.dat and fileinfo from the newest valid matching "
            "timestamped backup pair."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the selected pair without changing files.",
    )
    parser.add_argument(
        "--root-dat",
        type=Path,
        help="Path to root.dat (default: <root>/root.dat).",
    )
    parser.add_argument(
        "--fileinfo",
        type=Path,
        help="Path to fileinfo (default: <root>/../cubegm/fileinfo).",
    )
    args = parser.parse_args(argv)

    root = Path.cwd().resolve() if root is None else Path(root).expanduser().resolve()
    root_dat = args.root_dat or root_dat or (root / "root.dat")
    fileinfo = args.fileinfo or fileinfo or (root.parent / "cubegm" / "fileinfo")

    output(f"Root: {root}")
    output(f"root.dat: {root_dat}")
    output(f"fileinfo: {fileinfo}")
    output(f"Mode: {'DRY RUN' if args.dry_run else 'RECOVERY'}")

    success = restore_catalog(
        root_dat, fileinfo, dry_run=args.dry_run, output=output
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
