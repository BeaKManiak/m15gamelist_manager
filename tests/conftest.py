"""Shared fixtures for the M15 tests."""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET

import pytest

import delete_gamelist_backups
import gamelist_manager
import restore_gamelist


SYSTEM_NAMES = tuple(sorted(gamelist_manager.SYSTEMS))
MEMBER_NAMES = ("fileinfo.001", "fileinfo.002", "fileinfo.003")


@dataclass
class Collection:
    root: Path
    catalog_dir: Path
    root_dat: Path
    fileinfo: Path

    def system_dir(self, name: str) -> Path:
        return self.root / name

    def gamelist(self, name: str) -> Path:
        return self.system_dir(name) / "gamelist.xml"

    def images(self, name: str) -> Path:
        return self.system_dir(name) / "images"


def make_game(overrides: Mapping[str, object] | None = None) -> dict:
    game = {
        "gameid": "1",
        "path": "./foo.zip",
        "image": "./images/foo.png",
        "name": "Foo",
        "zh_CN": "Foo",
        "en_US": "Foo",
        "zh_TW": "Foo",
        "ko_KR": "Foo",
    }
    if overrides:
        game.update(overrides)
    return game


def write_gamelist(
    path: Path,
    games: Sequence[Mapping[str, object]] = (),
    *,
    extras: Sequence[tuple[str, str]] = (),
    bom: bool = False,
    indent: bool = True,
) -> bytes:
    root = ET.Element("gameList")
    for tag, text in extras:
        ET.SubElement(root, tag).text = text
    for fields in games:
        entry = ET.SubElement(root, "game")
        for tag, value in fields.items():
            ET.SubElement(entry, tag).text = str(value)
    if indent:
        ET.indent(root, space="  ")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def make_root_dat(path: Path, members: Mapping[str, bytes] | None = None) -> None:
    payloads = members or {name: b"" for name in MEMBER_NAMES}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in MEMBER_NAMES:
            archive.writestr(name, payloads[name])
    path.write_bytes(buf.getvalue())


def write_fileinfo(path: Path, values: Iterable[int] | None = None) -> None:
    fields = list(values) if values is not None else [0] * 25
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(str(value) for value in fields), encoding="ascii")


def make_collection(
    tmp_path: Path,
    *,
    games: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    rom_files: Mapping[str, Sequence[str]] | None = None,
    image_files: Mapping[str, Sequence[str]] | None = None,
    fileinfo_values: Iterable[int] | None = None,
    root_dat_members: Mapping[str, bytes] | None = None,
) -> Collection:
    root = tmp_path / "roms"
    root.mkdir()
    catalog_dir = tmp_path / "cubegm"
    catalog_dir.mkdir()
    root_dat = root / "root.dat"
    fileinfo = catalog_dir / "fileinfo"
    make_root_dat(root_dat, root_dat_members)
    write_fileinfo(fileinfo, fileinfo_values)

    games = games or {}
    rom_files = rom_files or {}
    image_files = image_files or {}

    for name in SYSTEM_NAMES:
        system_dir = root / name
        system_dir.mkdir()
        write_gamelist(system_dir / "gamelist.xml", games.get(name, []))
        for filename in rom_files.get(name, []):
            (system_dir / filename).write_bytes(b"rom")
        if image_files.get(name):
            images = system_dir / "images"
            images.mkdir()
            for filename in image_files[name]:
                (images / filename).write_bytes(b"image")

    return Collection(root, catalog_dir, root_dat, fileinfo)


@pytest.fixture
def make_collection_factory(tmp_path):
    def factory(**kwargs) -> Collection:
        # Each call gets its own subdirectory so a test can build several roots.
        target = tmp_path / f"collection-{len(list(tmp_path.iterdir()))}"
        target.mkdir()
        return make_collection(target, **kwargs)

    return factory


@pytest.fixture
def collection(make_collection_factory) -> Collection:
    return make_collection_factory()


def run_main(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["gamelist_manager.py", *args])
    return gamelist_manager.main()


def run_restore(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["restore_gamelist.py", *args])
    return restore_gamelist.main()


def run_prune(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["delete_gamelist_backups.py", *args])
    return delete_gamelist_backups.main()


def read_zip_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def read_fileinfo(path: Path) -> list[int]:
    return [int(value) for value in path.read_text(encoding="ascii").split(",")]


def snapshot_tree(root: Path) -> dict[str, tuple[int, int, str]]:
    """Return a stable description of every file under root."""
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        stat = path.stat()
        result[str(path.relative_to(root))] = (
            stat.st_size,
            stat.st_mtime_ns,
            hashlib.sha256(data).hexdigest(),
        )
    return result


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def parse_gamelist(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def game_fields(entry: ET.Element) -> dict[str, str]:
    return {
        child.tag: (child.text or "")
        for child in entry
    }


def backup_names(system_dir: Path) -> list[str]:
    return sorted(
        path.name
        for path in system_dir.iterdir()
        if path.is_file() and path.name.startswith("gamelist.xml.") and path.name.endswith(".bak")
    )


def write_backup(
    system_dir: Path,
    stamp: str,
    *,
    sequence: int | None = None,
    valid: bool = True,
    games: Sequence[Mapping[str, object]] | None = None,
) -> Path:
    suffix = f"_{sequence}" if sequence is not None else ""
    path = system_dir / f"gamelist.xml.{stamp}{suffix}.bak"
    if valid:
        write_gamelist(path, games or [])
    else:
        path.write_bytes(b"<gameList><game>")
    return path


def catalog_json(members: Mapping[str, bytes]) -> dict[str, str]:
    return {name: payload.decode("utf-8") for name, payload in members.items()}
