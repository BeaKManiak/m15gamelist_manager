"""Tests for catalog backup restoration."""

from __future__ import annotations

from pathlib import Path

import catalog_sync
import restore_catalog
from conftest import (
    make_root_dat,
    snapshot_tree,
    write_fileinfo,
)


def catalog_backup_pair(collection, stamp, title="Foo"):
    line = (
        f"nes/foo.zip\t00001  {title}\t00001  {title.upper()}\t"
        f"00001  {title}\t{title}\timages/foo.png\n"
    )
    root_backup = collection.root / f"root.dat.{stamp}.bak"
    info_backup = collection.catalog_dir / f"fileinfo.{stamp}.bak"
    make_root_dat(root_backup, {
        "fileinfo.001": line.encode("utf-8"),
        "fileinfo.002": line.encode("utf-8"),
        "fileinfo.003": line.encode("utf-8"),
    })
    write_fileinfo(info_backup, [1, 7] + [0] * 23)
    return root_backup, info_backup


def test_restore_catalog_uses_newest_valid_pair(make_collection_factory):
    collection = make_collection_factory()
    catalog_backup_pair(collection, "20200101_000000", "Old")
    new_root, new_info = catalog_backup_pair(collection, "20210101_000000", "New")

    assert restore_catalog.restore_catalog(
        collection.root_dat, collection.fileinfo
    )
    assert collection.root_dat.read_bytes() == new_root.read_bytes()
    assert collection.fileinfo.read_bytes() == new_info.read_bytes()
    assert list(collection.root.glob("root.dat.*.recovery.bak"))
    assert list(collection.catalog_dir.glob("fileinfo.*.recovery.bak"))


def test_restore_catalog_skips_invalid_newest_pair(make_collection_factory):
    collection = make_collection_factory()
    old_root, old_info = catalog_backup_pair(
        collection, "20200101_000000", "Old"
    )
    write_fileinfo(
        collection.catalog_dir / "fileinfo.20210101_000000.bak",
        [0] * 24,
    )
    make_root_dat(collection.root / "root.dat.20210101_000000.bak")

    assert restore_catalog.restore_catalog(
        collection.root_dat, collection.fileinfo
    )
    assert collection.root_dat.read_bytes() == old_root.read_bytes()
    assert collection.fileinfo.read_bytes() == old_info.read_bytes()


def test_restore_catalog_dry_run_changes_nothing(make_collection_factory):
    collection = make_collection_factory()
    catalog_backup_pair(collection, "20200101_000000")
    before = snapshot_tree(collection.root)
    before["catalog/fileinfo"] = (
        collection.fileinfo.stat().st_size,
        collection.fileinfo.stat().st_mtime_ns,
        collection.fileinfo.read_bytes().hex(),
    )

    assert restore_catalog.restore_catalog(
        collection.root_dat, collection.fileinfo, dry_run=True
    )
    assert snapshot_tree(collection.root) == {
        key: value for key, value in before.items() if not key.startswith("catalog/")
    }
    assert collection.fileinfo.read_bytes().hex() == before["catalog/fileinfo"][2]


def test_restore_catalog_without_pair_returns_false(make_collection_factory, capsys):
    collection = make_collection_factory()
    assert not restore_catalog.restore_catalog(
        collection.root_dat, collection.fileinfo
    )
    assert "No valid root.dat + fileinfo backup pair" in capsys.readouterr().out


def test_restore_catalog_main_accepts_explicit_root(make_collection_factory, tmp_path, monkeypatch):
    collection = make_collection_factory()
    catalog_backup_pair(collection, "20200101_000000")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    lines = []

    code = restore_catalog.main(
        ["--dry-run"], root=collection.root, output=lines.append
    )

    assert code == 0
    assert Path.cwd() == elsewhere
    assert "Selected backup pair" in "\n".join(lines)


def test_restore_catalog_main_returns_one_without_pair(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    monkeypatch.chdir(collection.root)
    assert restore_catalog.main(["--dry-run"]) == 1


def test_find_backup_pairs_returns_newest_first(make_collection_factory):
    collection = make_collection_factory()
    catalog_backup_pair(collection, "20200101_000000", "Old")
    catalog_backup_pair(collection, "20210101_000000", "New")

    pairs = restore_catalog.find_backup_pairs(
        collection.root_dat, collection.fileinfo
    )
    assert len(pairs) == 2
    assert pairs[0][0].name == "root.dat.20210101_000000.bak"


def test_catalog_backup_validation_matches_catalog_sync(make_collection_factory):
    collection = make_collection_factory()
    root_backup, info_backup = catalog_backup_pair(
        collection, "20200101_000000"
    )
    assert catalog_sync.catalog_file_issues(root_backup, info_backup) == []
