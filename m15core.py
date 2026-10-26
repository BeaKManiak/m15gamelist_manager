"""Shared XML and filesystem helpers for the M15 tools."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path


BACKUP_NAME = re.compile(
    r"^(?P<base>.+)\.(?P<stamp>\d{8}_\d{6})(?:_(?P<sequence>\d+))?\.bak$"
)


def local_tag(element) -> str:
    """Return a tag name without an optional XML namespace."""
    return (
        element.tag.rsplit("}", 1)[-1]
        if isinstance(element.tag, str)
        else ""
    )


def get_child(element, name):
    for item in element:
        if local_tag(item) == name:
            return item
    return None


def get_text(element, name) -> str:
    item = get_child(element, name)
    return item.text.strip() if item is not None and item.text else ""


def set_child_text(element, name, value):
    item = get_child(element, name)
    if item is None:
        item = ET.SubElement(element, name)
    item.text = str(value)
    return item


def find_system_folder(root: Path, name: str, *, ignore_oserror: bool = False):
    """Find a system folder, optionally ignoring directory-listing errors."""
    direct = root / name
    if direct.is_dir():
        return direct
    try:
        for candidate in root.iterdir():
            if (
                candidate.is_dir()
                and candidate.name.casefold() == name.casefold()
            ):
                return candidate
    except OSError:
        if ignore_oserror:
            return None
        raise
    return None


def next_backup_suffix(paths, stamp: str) -> str:
    """Return the next sequence suffix for a timestamped backup name."""
    max_sequence = -1
    for path in paths:
        pattern = re.compile(
            rf"^{re.escape(path.name)}\.{re.escape(stamp)}"
            r"(?:_(\d+))?\.bak$"
        )
        try:
            entries = path.parent.iterdir()
        except OSError:
            continue
        for sibling in entries:
            match = pattern.fullmatch(sibling.name)
            if match:
                max_sequence = max(
                    max_sequence, int(match.group(1) or 0)
                )
    return "" if max_sequence < 0 else f"_{max_sequence + 1}"


def prune_backups(
    directory: Path,
    base_name: str,
    keep: int,
    *,
    protect=(),
) -> tuple[list[str], list[str]]:
    """Delete old timestamped backups, keeping the newest ``keep``.

    Returns ``(deleted_names, errors)``. ``keep <= 0`` disables pruning.
    Recovery backups (``*.recovery.bak``) never match the pattern. Paths in
    ``protect`` are never deleted.
    """
    if keep <= 0:
        return [], []

    protected = {Path(path).resolve() for path in protect if path is not None}
    candidates = []
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        return [], [f"Could not list {directory}: {exc}"]

    for path in entries:
        if not path.is_file():
            continue
        match = BACKUP_NAME.fullmatch(path.name)
        if not match or match.group("base") != base_name:
            continue
        candidates.append(
            (
                match.group("stamp"),
                int(match.group("sequence") or 0),
                path,
            )
        )

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    deleted = []
    errors = []
    for _stamp, _sequence, path in candidates[keep:]:
        if path.resolve() in protected:
            continue
        try:
            path.unlink()
            deleted.append(path.name)
        except OSError as exc:
            errors.append(f"Could not delete {path.name}: {exc}")
    return deleted, errors
