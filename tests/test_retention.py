"""Tests for timestamped backup retention."""

from __future__ import annotations

import pytest

import catalog_sync
import gamelist_manager
import m15core
from conftest import (
    backup_names,
    make_game,
    write_gamelist,
)


def touch_backup(directory, base, stamp, sequence=None):
    suffix = f"_{sequence}" if sequence is not None else ""
    path = directory / f"{base}.{stamp}{suffix}.bak"
    path.write_text("x")
    return path


def test_prune_backups_keeps_newest_n(tmp_path):
    oldest = touch_backup(tmp_path, "gamelist.xml", "20200101_000000")
    middle = touch_backup(tmp_path, "gamelist.xml", "20200101_000001")
    newest = touch_backup(tmp_path, "gamelist.xml", "20200101_000002")
    recovery = touch_backup(tmp_path, "gamelist.xml", "20200101_000003")
    recovery_path = tmp_path / "gamelist.xml.20200101_000003.recovery.bak"
    recovery.rename(recovery_path)
    other = touch_backup(tmp_path, "root.dat", "20200101_000000")

    deleted, errors = m15core.prune_backups(
        tmp_path, "gamelist.xml", 2
    )

    assert errors == []
    assert sorted(deleted) == [oldest.name]
    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()
    assert recovery_path.exists()
    assert other.exists()


def test_prune_backups_zero_keeps_all(tmp_path):
    paths = [
        touch_backup(tmp_path, "gamelist.xml", f"20200101_00000{i}")
        for i in range(3)
    ]
    deleted, errors = m15core.prune_backups(tmp_path, "gamelist.xml", 0)
    assert deleted == []
    assert errors == []
    assert all(path.exists() for path in paths)


def test_prune_backups_protects_newest(tmp_path):
    paths = [
        touch_backup(tmp_path, "gamelist.xml", f"20200101_00000{i}")
        for i in range(3)
    ]
    deleted, errors = m15core.prune_backups(
        tmp_path, "gamelist.xml", 1, protect=[paths[-1]]
    )
    assert errors == []
    assert paths[-1].exists()
    assert len(deleted) == 2


def test_xml_writes_prune_old_backups(make_collection_factory):
    collection = make_collection_factory()
    recovery = collection.system_dir("nes") / "gamelist.xml.20200101_000000.recovery.bak"
    recovery.write_text("<?xml version='1.0'?><gameList />")

    for _ in range(7):
        result = gamelist_manager.run(
            gamelist_manager.Options(
                root=collection.root,
                system="nes",
                force_write=True,
                keep_baks=2,
            ),
            output=lambda _text: None,
        )
        assert result.exit_code == 0

    assert len(backup_names(collection.system_dir("nes"))) == 2
    assert recovery.exists()


def test_catalog_writes_prune_old_backups(make_collection_factory):
    collection = make_collection_factory()
    for index in range(6):
        write_gamelist(
            collection.gamelist("nes"),
            [
                make_game(
                    {
                        "gameid": str(index + 1),
                        "path": f"./game{index}.zip",
                        "name": f"Game {index}",
                    }
                )
            ],
        )
        summary = catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
            keep_baks=2,
        )
        assert summary["unchanged"] is False

    assert len(list(collection.root.glob("root.dat.*.bak"))) == 2
    assert len(list(collection.catalog_dir.glob("fileinfo.*.bak"))) == 2


def test_keep_baks_zero_keeps_all_xml_backups(make_collection_factory):
    collection = make_collection_factory()
    for _ in range(4):
        result = gamelist_manager.run(
            gamelist_manager.Options(
                root=collection.root,
                system="nes",
                force_write=True,
                keep_baks=0,
            ),
            output=lambda _text: None,
        )
        assert result.exit_code == 0
    assert len(backup_names(collection.system_dir("nes"))) == 4


def test_default_keep_baks_is_five(make_collection_factory):
    collection = make_collection_factory()
    for _ in range(7):
        result = gamelist_manager.run(
            gamelist_manager.Options(
                root=collection.root,
                system="nes",
                force_write=True,
            ),
            output=lambda _text: None,
        )
        assert result.exit_code == 0
    assert len(backup_names(collection.system_dir("nes"))) == 5


def test_noop_run_enforces_retention(make_collection_factory):
    collection = make_collection_factory()
    system = collection.system_dir("nes")
    for index in range(7):
        stamp = f"20200101_00000{index}"
        touch_backup(system, "gamelist.xml", stamp)
        touch_backup(collection.root, "root.dat", stamp)
        touch_backup(collection.catalog_dir, "fileinfo", stamp)

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root, system="nes", keep_baks=2
        ),
        output=lambda _text: None,
    )

    assert result.exit_code == 0
    assert len(backup_names(system)) == 2
    assert len(list(collection.root.glob("root.dat.*.bak"))) == 2
    assert len(list(collection.catalog_dir.glob("fileinfo.*.bak"))) == 2


def test_noop_dry_run_does_not_prune(make_collection_factory):
    collection = make_collection_factory()
    system = collection.system_dir("nes")
    for index in range(7):
        touch_backup(system, "gamelist.xml", f"20200101_00000{index}")

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root,
            system="nes",
            keep_baks=2,
            dry_run=True,
        ),
        output=lambda _text: None,
    )

    assert result.exit_code == 0
    assert len(backup_names(system)) == 7


def test_skip_catalog_does_not_prune_catalog_backups(make_collection_factory):
    collection = make_collection_factory()
    system = collection.system_dir("nes")
    for index in range(7):
        stamp = f"20200101_00000{index}"
        touch_backup(system, "gamelist.xml", stamp)
        touch_backup(collection.root, "root.dat", stamp)
        touch_backup(collection.catalog_dir, "fileinfo", stamp)

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root,
            system="nes",
            keep_baks=2,
            skip_catalog=True,
        ),
        output=lambda _text: None,
    )

    assert result.exit_code == 0
    assert len(backup_names(system)) == 2
    assert len(list(collection.root.glob("root.dat.*.bak"))) == 7
    assert len(list(collection.catalog_dir.glob("fileinfo.*.bak"))) == 7


def test_options_default_keep_baks():
    assert gamelist_manager.Options(root=".").keep_baks == 5


def test_cli_rejects_negative_keep_baks():
    parser = gamelist_manager.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--keep-baks", "-1"])
