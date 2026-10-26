#!/usr/bin/env python3
"""Safe M15 root.dat/fileinfo synchronizer for gamelist_manager.py."""
import io
import os
import shutil
import tempfile
import zipfile
import datetime
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from m15core import find_system_folder as _find_system_folder
from m15core import get_text as _get_text
from m15core import local_tag as _tag
from m15core import next_backup_suffix, prune_backups
from systems import FILEINFO_SYSTEM_ORDER

# fileinfo fields: total, existing reserved field, then system counts in this order.
MEMBER_LANGUAGES = {
    "fileinfo.001": "zh_CN",
    "fileinfo.002": "zh_TW",
    "fileinfo.003": "ko_KR",
}


def _text(e, tag):
    return _get_text(e, tag)


def _folder(root, name):
    return _find_system_folder(root, name)


def _catalog_path(system, raw):
    value = (raw or "").strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return f"{system}/{value}"


def _unprefix(value):
    if len(value) >= 7 and value[:5].isdigit() and value[5:7] == "  ":
        return value[7:]
    return value


def _old_localized_titles(root_dat):
    result = {m: {} for m in MEMBER_LANGUAGES}
    with zipfile.ZipFile(root_dat, "r") as z:
        expected = set(MEMBER_LANGUAGES)
        if set(z.namelist()) != expected:
            raise ValueError(
                f"Unexpected root.dat members {z.namelist()!r}; expected {sorted(expected)!r}"
            )
        bad = z.testzip()
        if bad:
            raise ValueError(f"Corrupt root.dat member: {bad}")
        for member in MEMBER_LANGUAGES:
            for lineno, line in enumerate(z.read(member).decode("utf-8-sig").splitlines(), 1):
                if not line:
                    continue
                fields = line.split("\t")
                if len(fields) != 6:
                    raise ValueError(f"{member} line {lineno}: expected 6 tab-separated fields")
                result[member][fields[0]] = _unprefix(fields[3])
    return result


def _read_xml_catalog(root_folder, system_names):
    games = {}
    counts = Counter()
    ids_seen = {}
    errors = []
    for system in system_names:
        try:
            folder = _folder(root_folder, system)
        except OSError as exc:
            errors.append(f"Cannot list ROM root: {exc}")
            break
        if folder is None:
            errors.append(f"Missing system folder: {system}")
            continue
        xml_path = folder / "gamelist.xml"
        if not xml_path.is_file():
            errors.append(f"Missing XML: {xml_path}")
            continue
        try:
            xml_root = ET.parse(xml_path).getroot()
        except Exception as exc:
            errors.append(f"Cannot parse {xml_path}: {exc}")
            continue
        if _tag(xml_root) != "gameList":
            errors.append(f"Unexpected root tag in {xml_path}: {_tag(xml_root)!r}")
            continue

        for i, entry in enumerate(xml_root, 1):
            if _tag(entry) != "game":
                continue
            raw_path = _text(entry, "path")
            gameid = _text(entry, "gameid")
            if not raw_path:
                errors.append(f"{xml_path}: game #{i} has no <path>")
                continue
            if not gameid.isdigit():
                errors.append(f"{xml_path}: {raw_path!r} has missing/non-numeric gameid {gameid!r}")
                continue
            canonical_id = str(int(gameid))
            label = f"{system}/{raw_path}"
            if canonical_id in ids_seen:
                errors.append(f"Duplicate gameid {gameid!r}: {ids_seen[canonical_id]} and {label}")
                continue
            ids_seen[canonical_id] = label
            key = _catalog_path(system, raw_path)
            if key in games:
                errors.append(f"Duplicate catalog path: {key}")
                continue

            name = _text(entry, "name") or Path(raw_path.replace("\\", "/")).stem
            image = _text(entry, "image").replace("\\", "/")
            while image.startswith("./"):
                image = image[2:]
            if not image:
                image = "images/" + Path(raw_path.replace("\\", "/")).stem + ".png"
            games[key] = {
                "system": system,
                "id": str(int(gameid)).zfill(5),
                "name": name,
                "image": image,
                "local": {
                    lang: (_text(entry, lang) or name)
                    for lang in ("zh_CN", "zh_TW", "ko_KR")
                },
            }
            counts[system] += 1

    if errors:
        raise ValueError(
            "Catalog update stopped; every system XML must be readable and globally unique:\n - "
            + "\n - ".join(errors[:60])
            + (f"\n ... plus {len(errors)-60} more issue(s)" if len(errors) > 60 else "")
        )
    return games, counts


def catalog_issues(roots, system_names):
    """Return catalog-validation issues for in-memory gamelist roots.

    ``roots`` maps system name to an ElementTree root (or None when the
    system is missing or unreadable). The rules match _read_xml_catalog.
    """
    issues = []
    ids_seen = {}
    paths_seen = {}

    for system in system_names:
        root = roots.get(system)
        if root is None:
            issues.append(f"Missing or unreadable gamelist: {system}")
            continue
        if _tag(root) != "gameList":
            issues.append(f"{system}: unexpected root <{_tag(root)}>")
            continue

        for index, entry in enumerate(root, 1):
            if _tag(entry) != "game":
                continue
            raw_path = _text(entry, "path")
            gameid = _text(entry, "gameid")
            if not raw_path:
                issues.append(f"{system}: game #{index} has no <path>")
                continue
            if not gameid.isdigit():
                issues.append(
                    f"{system}/{raw_path}: non-numeric <gameid> {gameid!r}"
                )
                continue
            canonical_id = str(int(gameid))
            label = f"{system}/{raw_path}"
            if canonical_id in ids_seen:
                issues.append(
                    f"Duplicate gameid {gameid!r}: "
                    f"{ids_seen[canonical_id]} and {label}"
                )
                continue
            ids_seen[canonical_id] = label
            key = _catalog_path(system, raw_path)
            if key in paths_seen:
                issues.append(f"Duplicate catalog path: {key}")
                continue
            paths_seen[key] = label

    return issues


def _fileinfo_fields(fileinfo_path):
    fields = fileinfo_path.read_text(encoding="ascii").strip().split(",")
    if len(fields) != 25 or any(not x.strip().isdigit() for x in fields):
        raise ValueError(
            "fileinfo must contain exactly 25 comma-separated "
            "non-negative integers"
        )
    return fields


def catalog_file_issues(root_dat, fileinfo_path):
    """Return issues with the catalog files themselves (read-only)."""
    issues = []
    try:
        _old_localized_titles(root_dat)
    except Exception as exc:
        issues.append(f"root.dat: {exc}")
    try:
        _fileinfo_fields(fileinfo_path)
    except Exception as exc:
        issues.append(f"fileinfo: {exc}")
    return issues


def _member_bytes(games, member, language, old_titles):
    lines = []
    for path in sorted(games, key=str.casefold):
        g = games[path]
        localized = old_titles.get(path) or g["local"][language]
        name = g["name"]
        fields = (
            path,
            f'{g["id"]}  {name}',
            f'{g["id"]}  {name.upper()}',
            f'{g["id"]}  {localized}',
            name,
            g["image"],
        )
        lines.append("\t".join(fields))
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def _atomic_write(path, data):
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_bytes(data)
        with temp.open("rb") as f:
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def sync_catalog(
    root_folder,
    root_dat,
    fileinfo_path,
    system_names,
    dry_run=False,
    keep_baks=0,
):
    """Regenerate global catalogs from all XMLs; preserve old localized titles by ROM path."""
    root_folder = Path(root_folder).resolve()
    root_dat = Path(root_dat).resolve()
    fileinfo_path = Path(fileinfo_path).resolve()
    if not root_dat.is_file() or not fileinfo_path.is_file():
        raise FileNotFoundError(f"Expected both {root_dat} and {fileinfo_path}")

    old_fields = _fileinfo_fields(fileinfo_path)

    old_titles = _old_localized_titles(root_dat)
    games, counts = _read_xml_catalog(root_folder, system_names)

    count_fields = [str(len(games)), old_fields[1]]
    count_fields.extend(str(counts.get(system, 0)) for system in FILEINFO_SYSTEM_ORDER)
    if len(count_fields) != 25:
        raise AssertionError("Generated fileinfo does not contain 25 fields")

    members = {
        member: _member_bytes(games, member, language, old_titles[member])
        for member, language in MEMBER_LANGUAGES.items()
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for member in ("fileinfo.001", "fileinfo.002", "fileinfo.003"):
            z.writestr(member, members[member])
    new_root = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(new_root), "r") as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"Generated root.dat failed validation: {bad}")
        for member in MEMBER_LANGUAGES:
            if len(z.read(member).decode("utf-8").splitlines()) != len(games):
                raise ValueError(f"Generated row count mismatch for {member}")
    new_info = ",".join(count_fields).encode("ascii")

    unchanged = False
    with zipfile.ZipFile(root_dat, "r") as existing:
        existing_names = existing.namelist()
        if (
            existing_names == list(MEMBER_LANGUAGES)
            and all(
                existing.read(name) == members[name]
                for name in MEMBER_LANGUAGES
            )
            and fileinfo_path.read_bytes() == new_info
        ):
            unchanged = True

    summary = {
        "games": len(games),
        "system_counts": dict(counts),
        "root_dat": str(root_dat),
        "fileinfo": str(fileinfo_path),
        "dry_run": dry_run,
        "unchanged": unchanged,
    }
    if dry_run or unchanged:
        return summary

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = next_backup_suffix([root_dat, fileinfo_path], stamp)
    rb = root_dat.with_name(f"{root_dat.name}.{stamp}{suffix}.bak")
    ib = fileinfo_path.with_name(f"{fileinfo_path.name}.{stamp}{suffix}.bak")
    shutil.copy2(root_dat, rb)
    shutil.copy2(fileinfo_path, ib)
    try:
        _atomic_write(root_dat, new_root)
        _atomic_write(fileinfo_path, new_info)
        with zipfile.ZipFile(root_dat, "r") as z:
            if z.testzip():
                raise ValueError("Installed root.dat failed ZIP validation")
        if fileinfo_path.read_bytes() != new_info:
            raise ValueError("Installed fileinfo failed byte-for-byte validation")
    except Exception:
        shutil.copy2(rb, root_dat)
        shutil.copy2(ib, fileinfo_path)
        raise
    summary["root_dat_backup"] = str(rb)
    summary["fileinfo_backup"] = str(ib)

    root_deleted, root_errors = prune_backups(
        root_dat.parent, root_dat.name, keep_baks, protect=[rb]
    )
    info_deleted, info_errors = prune_backups(
        fileinfo_path.parent,
        fileinfo_path.name,
        keep_baks,
        protect=[ib],
    )
    summary["pruned"] = len(root_deleted) + len(info_deleted)
    summary["prune_warnings"] = root_errors + info_errors
    return summary
