"""Shared XML and filesystem helpers for the M15 tools."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


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
