"""Platform, settings, and summary helpers for the M15 manager GUI.

This module deliberately has no tkinter dependency so its logic can be tested
on machines and CI runners without a display. ``m15_gui`` builds the widgets
and calls into here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import catalog_sync
import gamelist_manager

SYSTEMS = gamelist_manager.SYSTEMS
ALL_SYSTEMS = "All systems"

APP_NAME = "M15Manager"

DEDUP_CHOICES = [
    ("both", "Path and game ID"),
    ("path", "Path only"),
    ("gameid", "Game ID only"),
    ("none", "None"),
]
DECLARATION_CHOICES = [
    ("et", "Standard"),
    ("double", "Legacy (double quotes)"),
]

DEFAULT_SETTINGS = {
    "system": ALL_SYSTEMS,
    "dedup": "both",
    "declaration": "et",
    "remove_missing": True,
    "add": True,
    "ids": True,
    "normalize": True,
    "sort": True,
    "indent": True,
    "force_write": False,
    "delete_orphans": False,
    "keep_baks": 5,
}


def app_base_dir() -> Path:
    """Where the app lives, or the cwd when frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    """Locate a bundled data file both in source and in a frozen build."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidate = Path(bundle) / name
        if candidate.is_file():
            return candidate
    return app_base_dir() / name


# --------------------------------------------------------------- preferences


def config_dir() -> Path:
    """Per-user configuration folder for the current platform."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "m15manager"


def config_file() -> Path:
    return config_dir() / "config.json"


def load_config(path=None) -> dict:
    """Read the saved preferences; any problem falls back to empty settings."""
    target = Path(path) if path else config_file()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_config(data, path=None) -> None:
    """Write preferences atomically so a crash cannot leave a partial file."""
    target = Path(path) if path else config_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(target)


def normalized_settings(raw) -> dict:
    """Return a complete, validated settings dict built from saved values."""
    settings = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return settings

    system = raw.get("system")
    if system == ALL_SYSTEMS or system in SYSTEMS:
        settings["system"] = system

    dedup_values = {value for value, _ in DEDUP_CHOICES}
    if raw.get("dedup") in dedup_values:
        settings["dedup"] = raw["dedup"]

    declaration_values = {value for value, _ in DECLARATION_CHOICES}
    if raw.get("declaration") in declaration_values:
        settings["declaration"] = raw["declaration"]

    for key in (
        "remove_missing",
        "add",
        "ids",
        "normalize",
        "sort",
        "indent",
        "force_write",
        "delete_orphans",
    ):
        value = raw.get(key)
        if isinstance(value, bool):
            settings[key] = value

    try:
        keep_baks = int(raw.get("keep_baks"))
    except (TypeError, ValueError):
        keep_baks = DEFAULT_SETTINGS["keep_baks"]
    settings["keep_baks"] = min(max(keep_baks, 0), 99)
    return settings


# ------------------------------------------------------------------ discovery


def looks_like_rom_root(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
    except OSError:
        return False
    if not (path / "root.dat").is_file():
        return False
    return any((path / name).is_dir() for name in SYSTEMS)


def _child_dirs(path: Path) -> list:
    """Directories directly inside *path*, ignoring hidden entries."""
    try:
        entries = list(path.iterdir())
    except OSError:
        return []
    children = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                children.append(entry)
        except OSError:
            continue
    return children


def _windows_mount_points() -> list:
    """Removable drives first, then fixed drives, on Windows."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
    except Exception:
        return []

    removable = []
    fixed = []
    for index in range(26):
        if not (mask >> index) & 1:
            continue
        root = Path("%s:\\" % chr(ord("A") + index))
        try:
            kind = kernel32.GetDriveTypeW(str(root))
        except Exception:
            continue
        if kind == 2:  # DRIVE_REMOVABLE
            removable.append((root, True))
        elif kind == 3:  # DRIVE_FIXED
            fixed.append((root, False))
    return removable + fixed


def _mount_points() -> list:
    """Return ``(path, deep)`` mount points for the current platform.

    ``deep`` means one level of folders below the mount is worth checking.
    """
    if sys.platform == "win32":
        return _windows_mount_points()
    if sys.platform == "darwin":
        return [(path, True) for path in _child_dirs(Path("/Volumes"))]

    points = []
    for base in (Path("/media"), Path("/mnt")):
        for child in _child_dirs(base):
            points.append((child, True))
    for user_dir in _child_dirs(Path("/run/media")):
        points.append((user_dir, True))
        for mount in _child_dirs(user_dir):
            points.append((mount, True))
    return points


def rom_root_candidates() -> list:
    """Places to look for a collection, most likely first."""
    candidates = [(app_base_dir(), False)]
    candidates.extend(_mount_points())
    return candidates


def detect_rom_roots() -> list:
    """Best-effort guesses at ROM root folders, ordered by likelihood."""
    found = []
    seen = set()
    for base, deep in rom_root_candidates():
        probes = [base, base / "roms"]
        if deep:
            probes.extend(_child_dirs(base))
        for probe in probes:
            try:
                if not looks_like_rom_root(probe):
                    continue
                key = str(probe.resolve())
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            found.append(key)
    return found


# ------------------------------------------------------------------ summaries


def plural(count: int, singular: str, plural_form: str = None) -> str:
    if count == 1:
        return f"1 {singular}"
    return f"{count} {plural_form or singular + 's'}"


def _system_changed(item: dict) -> bool:
    changed_keys = (
        "added",
        "removed",
        "deduplicated",
        "normalized",
        "ids_added",
        "deleted",
    )
    return bool(item.get("sorted")) or any(item.get(key) for key in changed_keys)


def summarize_result(result) -> dict:
    """Turn a RunResult into plain counts used by the summary and dialog."""
    counts = {
        key: 0
        for key in (
            "added",
            "removed",
            "deduplicated",
            "normalized",
            "ids_added",
            "deleted",
            "orphans",
        )
    }
    systems_changed = 0
    systems_unchanged = 0
    sorted_systems = 0
    for item in result.systems.values():
        for key in counts:
            counts[key] += len(item.get(key) or [])
        if item.get("sorted"):
            sorted_systems += 1
        if _system_changed(item):
            systems_changed += 1
        elif item.get("status") == "OK":
            systems_unchanged += 1

    counts["sorted_systems"] = sorted_systems
    counts["systems"] = len(result.systems)
    counts["systems_changed"] = systems_changed
    counts["systems_unchanged"] = systems_unchanged
    counts["errors"] = result.errors
    counts["skipped"] = result.skipped
    counts["preflight"] = len(result.preflight_issues or [])
    return counts


def format_confirmation(
    counts: dict, catalog_refresh: bool, delete_orphans: bool = False
) -> list:
    """Plain-language lines for the confirmation dialog."""
    lines = []
    if counts["added"]:
        lines.append(f"{plural(counts['added'], 'new game')} will be added")
    if counts["removed"]:
        lines.append(
            "%s will be removed (the file is gone)"
            % plural(counts["removed"], "entry", "entries")
        )
    if counts["deduplicated"]:
        lines.append(
            "%s will be removed as duplicates"
            % plural(counts["deduplicated"], "entry", "entries")
        )
    if counts["normalized"]:
        lines.append(
            "%s will be tidied" % plural(counts["normalized"], "title")
        )
    if counts["ids_added"]:
        lines.append(
            "%s will be assigned" % plural(counts["ids_added"], "game ID")
        )
    if counts["deleted"]:
        lines.append(
            "%s will be deleted" % plural(counts["deleted"], "unused image")
        )
    if delete_orphans and counts["orphans"]:
        lines.append(
            "%s will be deleted permanently"
            % plural(counts["orphans"], "unused image")
        )
    if counts["sorted_systems"]:
        lines.append(
            "%s will be sorted alphabetically"
            % plural(counts["sorted_systems"], "game list")
        )
    if catalog_refresh:
        lines.append("The device catalog will be refreshed")
    if counts["systems_unchanged"]:
        lines.append(
            "%s already up to date"
            % plural(counts["systems_unchanged"], "system", "systems")
        )
    lines.append("")
    lines.append("Changed gamelists and catalog files are backed up first.")
    return lines


def format_last_run(result) -> str:
    """One-line summary of what an applied run changed."""
    counts = summarize_result(result)
    parts = []
    if counts["added"]:
        parts.append(plural(counts["added"], "new game"))
    if counts["removed"]:
        parts.append(f"{counts['removed']} removed")
    if counts["deduplicated"]:
        parts.append(
            "%s removed" % plural(counts["deduplicated"], "duplicate")
        )
    if counts["normalized"]:
        parts.append("%s tidied" % plural(counts["normalized"], "title"))
    if counts["ids_added"]:
        parts.append(
            "%s assigned" % plural(counts["ids_added"], "game ID")
        )
    if counts["deleted"]:
        parts.append("%s deleted" % plural(counts["deleted"], "image"))
    catalog = getattr(result, "catalog_summary", None)
    if catalog is not None:
        if catalog.get("unchanged"):
            if parts:
                parts.append("catalog unchanged")
        else:
            parts.append("catalog refreshed")
    if not parts:
        parts.append("no changes")
    return " · ".join(parts)


def catalog_needs_refresh(root, options, *, sync=None):
    """Check the device catalog without writing, when gamelists are unchanged.

    Returns ``True`` if the catalog would change, ``False`` if it is already
    up to date, and ``None`` when the check itself failed.
    """
    sync = sync or catalog_sync.sync_catalog
    root_path = Path(root)
    root_dat, fileinfo = gamelist_manager.catalog_paths(options, root_path)
    try:
        summary = sync(
            root_folder=root_path,
            root_dat=root_dat,
            fileinfo_path=fileinfo,
            system_names=list(SYSTEMS),
            dry_run=True,
            keep_baks=options.keep_baks,
        )
    except Exception:
        return None
    return not summary.get("unchanged", False)
