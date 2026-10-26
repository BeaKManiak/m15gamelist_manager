
#!/usr/bin/env python3
"""
Delete timestamped gamelist.xml backups created by updatelists
and restore_gamelist.py.

Run from the root directory containing system folders (snes, gb, etc.).

Default: delete matching backups.
Use --dry-run to preview without deleting.
"""

import argparse
import re
import sys
from pathlib import Path


BACKUP_PATTERN = re.compile(
    r"^gamelist\.xml\."
    r"\d{8}_\d{6}"
    r"(?:_\d+)?"
    r"(?:\.recovery)?"
    r"\.bak$"
)


def find_backups(root: Path, recursive: bool):
    """Find matching backup files."""
    iterator = root.rglob("*") if recursive else root.glob("*")

    for path in iterator:
        if path.is_file() and BACKUP_PATTERN.fullmatch(path.name):
            yield path


def main(argv=None, root=None, *, output=print) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Delete timestamped gamelist.xml backups from the current "
            "systems root directory. Deletion is the default behavior."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview matching backups without deleting them.",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Also search nested directories.",
    )

    parser.add_argument(
        "--system",
        help="Limit operation to one system folder, e.g. snes or gb.",
    )

    args = parser.parse_args(argv)
    root = Path.cwd().resolve() if root is None else Path(root).expanduser().resolve()

    if args.system:
        if (
            Path(args.system).name != args.system
            or args.system in (".", "..")
            or "/" in args.system
            or "\\" in args.system
        ):
            parser.error("--system must be a folder name, such as snes.")

        search_root = root / args.system

        if not search_root.is_dir():
            output(f"ERROR: System directory does not exist: {search_root}")
            return 2
    else:
        search_root = root

    backups = sorted(find_backups(search_root, args.recursive))

    output(f"Root: {root}")
    output(f"Search directory: {search_root}")
    output(f"Mode: {'DRY RUN' if args.dry_run else 'DELETE'}")
    output(f"Matching backups: {len(backups)}")

    if not backups:
        output("No matching gamelist backups found.")
        return 0

    deleted = 0
    errors = 0

    for path in backups:
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = path

        if args.dry_run:
            output(f"WOULD DELETE: {relative}")
            continue

        try:
            path.unlink()
            output(f"DELETED: {relative}")
            deleted += 1
        except OSError as exc:
            output(f"ERROR deleting {relative}: {exc}")
            errors += 1

    if args.dry_run:
        output(f"\nDry run complete: {len(backups)} backup(s) would be deleted.")
        output("No files were changed.")
        return 0

    output(f"\nDeleted: {deleted}")
    output(f"Errors: {errors}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
