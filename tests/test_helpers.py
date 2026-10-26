"""Characterization tests for small, pure helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import catalog_sync
import delete_gamelist_backups
import gamelist_manager
import restore_gamelist


def test_local_tag_strips_namespace():
    element = ET.Element("{urn:test}game")
    assert gamelist_manager.local_tag(element) == "game"
    assert gamelist_manager.local_tag(ET.Comment("x")) == ""


def test_get_child_get_text_and_set_child_text():
    entry = ET.Element("game")
    ET.SubElement(entry, "name").text = "  Foo  "
    assert gamelist_manager.get_text(entry, "name") == "Foo"
    assert gamelist_manager.get_text(entry, "missing") == ""

    child = gamelist_manager.set_child_text(entry, "name", "Bar")
    assert child.text == "Bar"
    assert gamelist_manager.get_text(entry, "name") == "Bar"

    new_child = gamelist_manager.set_child_text(entry, "gameid", 7)
    assert new_child.text == "7"
    assert gamelist_manager.get_text(entry, "gameid") == "7"


def test_id_key_modes():
    assert gamelist_manager.id_key("") is None
    assert gamelist_manager.id_key("  ") is None
    assert gamelist_manager.id_key("007") == ("numeric", "7")
    assert gamelist_manager.id_key("ABC") == ("text", "abc")
    assert gamelist_manager.id_key(" a B ") == ("text", "a b")


def test_gameid_sort_key_orders_numeric_then_text_then_missing():
    def entry(value):
        element = ET.Element("game")
        if value is not None:
            ET.SubElement(element, "gameid").text = value
        return element

    values = [entry(None), entry("beta"), entry("10"), entry("2")]
    ordered = sorted(
        enumerate(values),
        key=lambda pair: gamelist_manager.gameid_sort_key(pair[1], pair[0]),
    )
    assert [gamelist_manager.get_text(item, "gameid") for _, item in ordered] == [
        "2",
        "10",
        "beta",
        "",
    ]


def test_strip_numeric_prefix_only_when_followed_by_whitespace():
    assert gamelist_manager.strip_numeric_prefix("01 Foo") == "Foo"
    assert gamelist_manager.strip_numeric_prefix("  12   Foo") == "Foo"
    assert gamelist_manager.strip_numeric_prefix("Foo") == "Foo"
    assert gamelist_manager.strip_numeric_prefix("123") == "123"
    assert gamelist_manager.strip_numeric_prefix("") == ""


def test_find_system_folder_direct_and_case_insensitive(tmp_path):
    direct = tmp_path / "nes"
    direct.mkdir()
    assert gamelist_manager.find_system_folder(tmp_path, "nes") == direct

    mixed = tmp_path / "Snes"
    mixed.mkdir()
    found = gamelist_manager.find_system_folder(tmp_path, "snes")
    assert found is not None
    assert found.name.casefold() == "snes"
    assert gamelist_manager.find_system_folder(tmp_path, "missing") is None


def test_find_system_folder_swallows_iterdir_error(tmp_path, monkeypatch):
    def fail(self):
        raise OSError("no listing")

    monkeypatch.setattr(Path, "iterdir", fail)
    assert gamelist_manager.find_system_folder(tmp_path, "missing") is None


def test_resolve_game_path(tmp_path):
    folder = tmp_path / "nes"
    folder.mkdir()
    assert gamelist_manager.resolve_game_path(folder, "./foo.zip") == (folder / "foo.zip").resolve()
    assert gamelist_manager.resolve_game_path(folder, "sub\\bar.zip") == (
        folder / "sub" / "bar.zip"
    ).resolve()


def test_make_entry_for_nes_and_psx():
    nes = gamelist_manager.make_entry("Mario.zip", "12", gamelist_manager.SYSTEMS["nes"])
    assert gamelist_manager.get_text(nes, "gameid") == "12"
    assert gamelist_manager.get_text(nes, "path") == "./Mario.zip"
    assert gamelist_manager.get_text(nes, "image") == "./images/Mario.png"
    assert gamelist_manager.get_text(nes, "video_id") == "0"
    assert gamelist_manager.get_text(nes, "class_type") == "0"
    assert gamelist_manager.get_text(nes, "game_type") == "2"
    assert gamelist_manager.get_text(nes, "timer") == "nes"
    assert gamelist_manager.get_text(nes, "name") == "Mario"
    for language in gamelist_manager.LANGUAGES:
        assert gamelist_manager.get_text(nes, language) == "Mario"
    assert gamelist_manager.get_child(nes, "core") is None

    psx = gamelist_manager.make_entry("Disc.cue", "13", gamelist_manager.SYSTEMS["psx"])
    assert gamelist_manager.get_text(psx, "video_id") == "x"
    assert gamelist_manager.get_child(psx, "class_type") is None
    assert gamelist_manager.get_text(psx, "core") == "pcsx_rearmed_chd_libretro.so"


def test_timestamped_backup_is_unique(tmp_path):
    xml_path = tmp_path / "gamelist.xml"
    xml_path.write_text("x")
    first = gamelist_manager.timestamped_backup(xml_path)
    first.write_text("backup")
    second = gamelist_manager.timestamped_backup(xml_path)
    assert first != second
    assert second.name.endswith(".bak")


def test_catalog_unprefix_requires_five_digits_and_two_spaces():
    assert catalog_sync._unprefix("00001  Foo") == "Foo"
    assert catalog_sync._unprefix("1  Foo") == "1  Foo"
    assert catalog_sync._unprefix("00001 Foo") == "00001 Foo"
    assert catalog_sync._unprefix("Foo") == "Foo"


def test_catalog_path_strips_leading_dot_slashes():
    assert catalog_sync._catalog_path("nes", "./foo.zip") == "nes/foo.zip"
    assert catalog_sync._catalog_path("nes", ".\\sub\\foo.zip") == "nes/sub/foo.zip"
    assert catalog_sync._catalog_path("nes", "././foo.zip") == "nes/foo.zip"


def test_restore_valid_xml(tmp_path):
    valid = tmp_path / "valid.xml"
    valid.write_text("<?xml version='1.0'?><gameList />")
    invalid = tmp_path / "invalid.xml"
    invalid.write_text("<gameList>")
    missing = tmp_path / "missing.xml"
    assert restore_gamelist.valid_xml(valid)
    assert not restore_gamelist.valid_xml(invalid)
    assert not restore_gamelist.valid_xml(missing)


def test_restore_picks_newest_valid_backup_and_ignores_recovery(tmp_path, capsys):
    system = tmp_path / "nes"
    system.mkdir()
    old = system / "gamelist.xml.20200101_000000.bak"
    old.write_text("<?xml version='1.0'?><gameList />")
    bad_new = system / "gamelist.xml.20210101_000000.bak"
    bad_new.write_text("<gameList>")
    recovery = system / "gamelist.xml.20220101_000000.recovery.bak"
    recovery.write_text("<?xml version='1.0'?><gameList />")

    assert restore_gamelist.find_latest_valid_backup(system) == old
    assert "Skipping invalid XML backup" in capsys.readouterr().out


def test_backup_patterns():
    assert restore_gamelist.BACKUP_PATTERN.fullmatch("gamelist.xml.20200101_000000.bak")
    assert restore_gamelist.BACKUP_PATTERN.fullmatch("gamelist.xml.20200101_000000_2.bak")
    assert not restore_gamelist.BACKUP_PATTERN.fullmatch(
        "gamelist.xml.20200101_000000.recovery.bak"
    )

    assert delete_gamelist_backups.BACKUP_PATTERN.fullmatch(
        "gamelist.xml.20200101_000000.recovery.bak"
    )
    assert delete_gamelist_backups.BACKUP_PATTERN.fullmatch(
        "gamelist.xml.20200101_000000_2.bak"
    )
    assert not delete_gamelist_backups.BACKUP_PATTERN.fullmatch("gamelist.xml.bak")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("arcade", {".fba", ".zip"}),
        ("atari2600", {".a26"}),
        ("psx", {
            ".img", ".pbp", ".iso", ".bin", ".chd", ".cue", ".ccd",
            ".mdf", ".mds", ".nrg", ".cso", ".zso", ".ecm",
        }),
    ],
)
def test_system_extensions(name, expected):
    assert gamelist_manager.SYSTEMS[name]["extensions"] == expected


def test_fileinfo_order_matches_systems():
    assert len(catalog_sync.FILEINFO_SYSTEM_ORDER) == len(gamelist_manager.SYSTEMS)
    assert set(catalog_sync.FILEINFO_SYSTEM_ORDER) == set(gamelist_manager.SYSTEMS)
