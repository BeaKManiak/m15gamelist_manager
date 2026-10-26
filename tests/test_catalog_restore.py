"""Characterization tests for catalog sync, restore, and backup pruning."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

import catalog_sync
import delete_gamelist_backups
import gamelist_manager
import restore_gamelist
from conftest import (
    MEMBER_NAMES,
    make_game,
    read_fileinfo,
    read_zip_members,
    run_prune,
    run_restore,
    snapshot_tree,
    write_backup,
    write_fileinfo,
    write_gamelist,
)


def test_sync_catalog_output_and_localized_title_preservation(make_collection_factory):
    old_member = (
        "nes/foo.zip\t00001  Foo\t00001  FOO\t00001  Old Chinese\tFoo\timages/foo.png\n"
    )
    collection = make_collection_factory(
        games={
            "nes": [make_game({"gameid": "1", "path": "./foo.zip", "name": "Foo"})],
            "snes": [
                make_game(
                    {
                        "gameid": "2",
                        "path": "./bar.zip",
                        "name": "Bar",
                        "image": "./images/bar.png",
                        "zh_CN": "Bar",
                        "zh_TW": "Bar",
                        "ko_KR": "Bar",
                    }
                )
            ],
        },
        fileinfo_values=[99, 42] + [0] * 23,
        root_dat_members={
            "fileinfo.001": old_member.encode("utf-8"),
            "fileinfo.002": b"",
            "fileinfo.003": b"",
        },
    )

    summary = catalog_sync.sync_catalog(
        collection.root,
        collection.root_dat,
        collection.fileinfo,
        system_names=list(gamelist_manager.SYSTEMS),
    )

    assert summary["games"] == 2
    members = read_zip_members(collection.root_dat)
    assert tuple(members) == MEMBER_NAMES
    lines = members["fileinfo.001"].decode("utf-8").splitlines()
    assert lines == [
        "nes/foo.zip\t00001  Foo\t00001  FOO\t00001  Old Chinese\tFoo\timages/foo.png",
        "snes/bar.zip\t00002  Bar\t00002  BAR\t00002  Bar\tBar\timages/bar.png",
    ]
    values = read_fileinfo(collection.fileinfo)
    assert values[0] == 2
    assert values[1] == 42
    assert sum(values[2:]) == 2
    assert values[2 + 11] == 1  # nes
    assert values[2 + 15] == 1  # snes


@pytest.mark.parametrize("system_name", ["missing", "missing-xml", "bad-root", "text-id"])
def test_sync_catalog_failures_do_not_write(make_collection_factory, system_name):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "1", "path": "./foo.zip"})]}
    )
    if system_name == "missing-xml":
        collection.gamelist("nes").unlink()
    elif system_name == "bad-root":
        collection.gamelist("nes").write_text("<?xml version='1.0'?><notGameList />")
    elif system_name == "text-id":
        write_gamelist(
            collection.gamelist("nes"),
            [make_game({"gameid": "abc", "path": "./foo.zip"})],
        )
    systems = list(gamelist_manager.SYSTEMS)
    if system_name == "missing":
        systems = ["missing"]

    before = snapshot_tree(collection.root)
    with pytest.raises(ValueError):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=systems,
        )
    assert snapshot_tree(collection.root) == before


def test_sync_catalog_rejects_duplicate_ids(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [make_game({"gameid": "1", "path": "./a.zip"})],
            "snes": [make_game({"gameid": "001", "path": "./b.zip"})],
        }
    )
    before = snapshot_tree(collection.root)
    with pytest.raises(ValueError, match="Duplicate gameid"):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
        )
    assert snapshot_tree(collection.root) == before


def test_sync_catalog_rejects_duplicate_catalog_path(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [
                make_game({"gameid": "1", "path": "./a.zip"}),
                make_game({"gameid": "2", "path": "a.zip"}),
            ]
        }
    )
    before = snapshot_tree(collection.root)
    with pytest.raises(ValueError, match="Duplicate catalog path"):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
        )
    assert snapshot_tree(collection.root) == before


def test_sync_catalog_rejects_wrong_member_set(make_collection_factory):
    collection = make_collection_factory()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fileinfo.001", b"")
    collection.root_dat.write_bytes(buf.getvalue())

    with pytest.raises(ValueError, match="Unexpected root.dat members"):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
        )


def test_sync_catalog_rejects_invalid_fileinfo(make_collection_factory):
    collection = make_collection_factory()
    write_fileinfo(collection.fileinfo, [0] * 24)

    with pytest.raises(ValueError, match="fileinfo must contain exactly 25"):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
        )


def test_sync_catalog_rejects_corrupt_root_dat(make_collection_factory):
    collection = make_collection_factory()
    collection.root_dat.write_bytes(b"not a zip")

    with pytest.raises(zipfile.BadZipFile):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
        )


def test_restore_system_uses_newest_valid_backup(make_collection_factory):
    collection = make_collection_factory()
    system = collection.system_dir("nes")
    current = collection.gamelist("nes")
    current.write_text("<?xml version='1.0'?><gameList><game /></gameList>")
    old = write_backup(
        system,
        "20200101_000000",
        games=[make_game({"gameid": "1", "path": "./old.zip", "name": "Old"})],
    )
    write_backup(system, "20210101_000000", valid=False)

    assert restore_gamelist.restore_system(system, dry_run=False)

    assert current.read_bytes() == old.read_bytes()
    assert list(system.glob("gamelist.xml.*.recovery.bak"))
    assert old.exists()


def test_restore_dry_run_changes_nothing(make_collection_factory):
    collection = make_collection_factory()
    system = collection.system_dir("nes")
    write_backup(system, "20200101_000000")
    before = snapshot_tree(collection.root)

    assert restore_gamelist.restore_system(system, dry_run=True)
    assert snapshot_tree(collection.root) == before


def test_restore_without_backup_returns_false(make_collection_factory, capsys):
    collection = make_collection_factory()
    system = collection.system_dir("nes")

    assert not restore_gamelist.restore_system(system, dry_run=False)
    assert "No valid timestamped backup" in capsys.readouterr().out


def test_restore_main_dry_run_exit_code(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    write_backup(collection.system_dir("nes"), "20200101_000000")
    monkeypatch.chdir(collection.root)

    assert run_restore(monkeypatch, "--system", "nes", "--dry-run") == 0


def test_restore_main_no_backup_returns_one(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    monkeypatch.chdir(collection.root)

    assert run_restore(monkeypatch, "--system", "nes", "--dry-run") == 1


def test_restore_recursive_finds_nested_backups(make_collection_factory, monkeypatch, capsys):
    collection = make_collection_factory()
    nested = collection.root / "nested" / "nes"
    nested.mkdir(parents=True)
    write_backup(nested, "20200101_000000")
    monkeypatch.chdir(collection.root)

    assert run_restore(monkeypatch, "--recursive", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "System: nes" in out
    assert "1/1 system(s) processed" in out


def test_prune_dry_run_and_apply(make_collection_factory, monkeypatch, capsys):
    collection = make_collection_factory()
    system = collection.system_dir("nes")
    regular = write_backup(system, "20200101_000000")
    recovery = write_backup(system, "20200101_000001")
    recovery.rename(system / "gamelist.xml.20200101_000001.recovery.bak")
    unrelated = system / "keep.txt"
    unrelated.write_text("keep")
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch, "--system", "nes", "--dry-run") == 0
    assert regular.exists()
    assert unrelated.exists()
    assert "WOULD DELETE" in capsys.readouterr().out

    assert run_prune(monkeypatch, "--system", "nes") == 0
    assert not regular.exists()
    assert not recovery.exists()
    assert unrelated.exists()
    assert "Deleted: 2" in capsys.readouterr().out


def test_prune_missing_system_returns_two(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch, "--system", "missing") == 2


def test_prune_recursive(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    nested = collection.root / "nested" / "nes"
    nested.mkdir(parents=True)
    backup = write_backup(nested, "20200101_000000")
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch, "--recursive") == 0
    assert not backup.exists()


def test_prune_no_backups_returns_zero(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch) == 0


def test_restore_main_accepts_explicit_root_without_chdir(make_collection_factory, monkeypatch, tmp_path):
    collection = make_collection_factory()
    write_backup(collection.system_dir("nes"), "20200101_000000")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    lines = []

    code = restore_gamelist.main(
        ["--system", "nes", "--dry-run"],
        root=collection.root,
        output=lines.append,
    )

    assert code == 0
    assert Path.cwd() == elsewhere
    assert "Root:" in "\n".join(lines)


def test_prune_main_accepts_explicit_root_without_chdir(make_collection_factory, monkeypatch, tmp_path):
    collection = make_collection_factory()
    backup = write_backup(collection.system_dir("nes"), "20200101_000000")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    lines = []

    code = delete_gamelist_backups.main(
        ["--system", "nes"],
        root=collection.root,
        output=lines.append,
    )

    assert code == 0
    assert Path.cwd() == elsewhere
    assert not backup.exists()
    assert "DELETED" in "\n".join(lines)


def test_sync_catalog_second_call_is_noop(make_collection_factory):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "1", "path": "./foo.zip"})]}
    )
    first = catalog_sync.sync_catalog(
        collection.root,
        collection.root_dat,
        collection.fileinfo,
        system_names=list(gamelist_manager.SYSTEMS),
    )
    assert first["unchanged"] is False
    before = snapshot_tree(collection.root)
    before[".catalog"] = (0, 0, "")
    for path in collection.catalog_dir.iterdir():
        before[f"catalog/{path.name}"] = (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            path.read_bytes().hex(),
        )

    second = catalog_sync.sync_catalog(
        collection.root,
        collection.root_dat,
        collection.fileinfo,
        system_names=list(gamelist_manager.SYSTEMS),
    )

    assert second["unchanged"] is True
    after = snapshot_tree(collection.root)
    after[".catalog"] = (0, 0, "")
    for path in collection.catalog_dir.iterdir():
        after[f"catalog/{path.name}"] = (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            path.read_bytes().hex(),
        )
    assert after == before


def test_sync_catalog_changed_content_writes_again(make_collection_factory):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "1", "path": "./foo.zip"})]}
    )
    catalog_sync.sync_catalog(
        collection.root,
        collection.root_dat,
        collection.fileinfo,
        system_names=list(gamelist_manager.SYSTEMS),
    )
    write_gamelist(
        collection.gamelist("nes"),
        [
            make_game({"gameid": "1", "path": "./foo.zip"}),
            make_game({"gameid": "2", "path": "./bar.zip", "name": "Bar"}),
        ],
    )
    backup_count = len(list(collection.root.glob("root.dat.*.bak")))

    summary = catalog_sync.sync_catalog(
        collection.root,
        collection.root_dat,
        collection.fileinfo,
        system_names=list(gamelist_manager.SYSTEMS),
    )

    assert summary["unchanged"] is False
    assert summary["games"] == 2
    assert len(list(collection.root.glob("root.dat.*.bak"))) == backup_count + 1


def test_prune_catalog_backups(make_collection_factory, monkeypatch, capsys):
    collection = make_collection_factory()
    for index in range(3):
        stamp = f"20200101_00000{index}"
        (collection.root / f"root.dat.{stamp}.bak").write_bytes(b"x")
        (collection.catalog_dir / f"fileinfo.{stamp}.bak").write_bytes(b"x")
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch, "--catalog", "--dry-run") == 0
    assert len(list(collection.root.glob("root.dat.*.bak"))) == 3
    assert "WOULD DELETE" in capsys.readouterr().out

    assert run_prune(monkeypatch, "--catalog") == 0
    assert list(collection.root.glob("root.dat.*.bak")) == []
    assert list(collection.catalog_dir.glob("fileinfo.*.bak")) == []
    assert "Deleted: 6" in capsys.readouterr().out


def test_prune_default_leaves_catalog_backups(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    (collection.root / "root.dat.20200101_000000.bak").write_bytes(b"x")
    (collection.catalog_dir / "fileinfo.20200101_000000.bak").write_bytes(b"x")
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch) == 0
    assert (collection.root / "root.dat.20200101_000000.bak").exists()
    assert (collection.catalog_dir / "fileinfo.20200101_000000.bak").exists()


def test_prune_catalog_with_system_scope(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    (collection.root / "root.dat.20200101_000000.bak").write_bytes(b"x")
    (collection.catalog_dir / "fileinfo.20200101_000000.bak").write_bytes(b"x")
    other = write_backup(collection.system_dir("nes"), "20200101_000000")
    monkeypatch.chdir(collection.root)

    assert run_prune(monkeypatch, "--system", "nes", "--catalog") == 0
    assert not other.exists()
    assert not (collection.root / "root.dat.20200101_000000.bak").exists()
    assert not (collection.catalog_dir / "fileinfo.20200101_000000.bak").exists()


def test_catalog_fileinfo_field_two_is_preserved(make_collection_factory):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "1", "path": "./foo.zip"})]},
        fileinfo_values=[0, 77] + [0] * 23,
    )
    catalog_sync.sync_catalog(
        collection.root,
        collection.root_dat,
        collection.fileinfo,
        system_names=list(gamelist_manager.SYSTEMS),
    )
    assert read_fileinfo(collection.fileinfo)[1] == 77


def test_catalog_missing_system_folder_names_the_system(make_collection_factory):
    collection = make_collection_factory()
    (collection.root / "nes").rename(collection.root / "removed")
    with pytest.raises(ValueError, match="Missing system folder: nes"):
        catalog_sync.sync_catalog(
            collection.root,
            collection.root_dat,
            collection.fileinfo,
            system_names=list(gamelist_manager.SYSTEMS),
        )
