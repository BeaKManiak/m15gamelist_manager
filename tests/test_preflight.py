"""Tests for the catalog preflight added in T10b."""

from __future__ import annotations

import gamelist_manager
from conftest import make_game, snapshot_tree


def test_text_gameid_fails_before_any_write(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [
                make_game(
                    {"gameid": "abc", "path": "./Foo.zip", "name": "Foo"}
                )
            ]
        },
        rom_files={"nes": ["Foo.zip"]},
    )
    before = snapshot_tree(collection.root)

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes"),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    assert result.preflight_issues
    assert snapshot_tree(collection.root) == before
    assert not list(collection.root.rglob("*.bak"))


def test_duplicate_gameids_fail_before_any_write(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [
                make_game({"gameid": "1", "path": "./A.zip", "name": "A"})
            ],
            "snes": [
                make_game({"gameid": "001", "path": "./B.zip", "name": "B"})
            ],
        },
        rom_files={"nes": ["A.zip"], "snes": ["B.zip"]},
    )
    before = snapshot_tree(collection.root)

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    assert any("Duplicate gameid" in issue for issue in result.preflight_issues)
    assert snapshot_tree(collection.root) == before


def test_duplicate_catalog_path_fails_before_any_write(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [
                make_game({"gameid": "1", "path": "./a.zip", "name": "A"}),
                make_game({"gameid": "2", "path": "a.zip", "name": "B"}),
            ]
        },
        rom_files={"nes": ["a.zip"]},
    )
    before = snapshot_tree(collection.root)

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root, system="nes", dedup="none"
        ),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    assert any("Duplicate catalog path" in issue for issue in result.preflight_issues)
    assert snapshot_tree(collection.root) == before


def test_entry_without_path_fails_before_any_write(make_collection_factory):
    game = make_game({"gameid": "1", "name": "No path"})
    game.pop("path")
    collection = make_collection_factory(games={"nes": [game]})
    before = snapshot_tree(collection.root)

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes"),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    assert any("has no <path>" in issue for issue in result.preflight_issues)
    assert snapshot_tree(collection.root) == before


def test_missing_xml_fails_before_any_write(make_collection_factory):
    collection = make_collection_factory()
    collection.gamelist("nes").unlink()
    before = snapshot_tree(collection.root)

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes"),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    assert any("gamelist.xml not found" in issue for issue in result.preflight_issues)
    assert snapshot_tree(collection.root) == before


def test_dry_run_reports_preflight_errors_without_writing(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [
                make_game(
                    {"gameid": "abc", "path": "./Foo.zip", "name": "Foo"}
                )
            ]
        },
        rom_files={"nes": ["Foo.zip"]},
    )
    before = snapshot_tree(collection.root)
    lines = []

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root, system="nes", dry_run=True
        ),
        output=lines.append,
    )

    assert result.exit_code == 1
    assert result.preflight_issues
    assert snapshot_tree(collection.root) == before
    assert "CATALOG PREFLIGHT FAILED" in "\n".join(lines)


def test_missing_catalog_files_fail_preflight(make_collection_factory):
    collection = make_collection_factory()
    collection.root_dat.unlink()
    collection.fileinfo.unlink()

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root, system="nes", dry_run=True
        ),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    text = "\n".join(result.preflight_issues)
    assert "root.dat:" in text
    assert "fileinfo:" in text


def test_valid_run_still_writes_and_syncs_catalog(make_collection_factory):
    collection = make_collection_factory(rom_files={"nes": ["Mario.zip"]})

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes"),
        output=lambda _text: None,
    )

    assert result.exit_code == 0
    assert result.preflight_issues is None
    assert result.catalog_summary is not None
    assert result.systems["nes"]["added"] == ["Mario.zip"]


def test_skip_ids_with_missing_ids_fails_preflight(make_collection_factory):
    game = make_game({"path": "./Foo.zip", "name": "Foo"})
    game.pop("gameid")
    collection = make_collection_factory(
        games={"nes": [game]},
        rom_files={"nes": ["Foo.zip"]},
    )
    before = snapshot_tree(collection.root)

    result = gamelist_manager.run(
        gamelist_manager.Options(
            root=collection.root, system="nes", skip_ids=True
        ),
        output=lambda _text: None,
    )

    assert result.exit_code == 1
    assert any("non-numeric <gameid>" in issue for issue in result.preflight_issues)
    assert snapshot_tree(collection.root) == before
