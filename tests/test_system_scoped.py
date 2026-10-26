"""Tests for system-scoped runs and global ID allocation."""

from __future__ import annotations

import gamelist_manager
from conftest import game_fields, make_game, parse_gamelist


def test_system_run_allocates_from_global_id_pool(make_collection_factory):
    collection = make_collection_factory(
        games={
            "snes": [
                make_game(
                    {
                        "gameid": "1",
                        "path": "./Contra.zip",
                        "name": "Contra",
                    }
                )
            ]
        },
        rom_files={
            "nes": ["Mario.zip"],
            "snes": ["Contra.zip"],
        },
    )
    snes_before = collection.gamelist("snes").read_bytes()

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes"),
        output=lambda _text: None,
    )

    assert result.exit_code == 0
    nes_entries = [
        child
        for child in parse_gamelist(collection.gamelist("nes"))
        if gamelist_manager.local_tag(child) == "game"
    ]
    assert len(nes_entries) == 1
    assert game_fields(nes_entries[0])["gameid"] == "2"
    assert collection.gamelist("snes").read_bytes() == snes_before
    assert result.systems["nes"]["status"] == "OK"
    assert result.catalog_summary["games"] == 2


def test_full_run_still_processes_every_system(make_collection_factory):
    collection = make_collection_factory(
        rom_files={"nes": ["Mario.zip"], "snes": ["Contra.zip"]}
    )

    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root),
        output=lambda _text: None,
    )

    assert result.exit_code == 0
    assert set(result.systems) == set(gamelist_manager.SYSTEMS)
    assert result.systems["nes"]["added"] == ["Mario.zip"]
    assert result.systems["snes"]["added"] == ["Contra.zip"]
