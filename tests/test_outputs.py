"""Characterization tests for gamelist processing and the XML writer."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

import gamelist_manager
from conftest import (
    backup_names,
    game_fields,
    make_game,
    parse_gamelist,
    read_fileinfo,
    read_zip_members,
    run_main,
    snapshot_tree,
    write_gamelist,
)


def games_of(root: ET.Element) -> list[ET.Element]:
    return [child for child in root if gamelist_manager.local_tag(child) == "game"]


def test_add_new_rom_writes_entry_backup_and_catalog(make_collection_factory, monkeypatch):
    collection = make_collection_factory(rom_files={"nes": ["Mario.zip"]})

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    entries = games_of(parse_gamelist(collection.gamelist("nes")))
    assert len(entries) == 1
    fields = game_fields(entries[0])
    assert fields["gameid"] == "1"
    assert fields["path"] == "./Mario.zip"
    assert fields["image"] == "./images/Mario.png"
    assert fields["video_id"] == "0"
    assert fields["class_type"] == "0"
    assert fields["game_type"] == "2"
    assert fields["timer"] == "nes"
    assert fields["name"] == "Mario"
    assert len(backup_names(collection.system_dir("nes"))) == 1

    members = read_zip_members(collection.root_dat)
    assert b"nes/Mario.zip" in members["fileinfo.001"]
    values = read_fileinfo(collection.fileinfo)
    assert values[0] == 1
    assert values[2 + 11] == 1  # nes in FILEINFO_SYSTEM_ORDER


def test_remove_missing_rom(make_collection_factory, monkeypatch, capsys):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "5", "path": "./Missing.zip", "name": "Missing"})]}
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    assert games_of(parse_gamelist(collection.gamelist("nes"))) == []
    assert "Removed entries" in capsys.readouterr().out
    assert len(backup_names(collection.system_dir("nes"))) == 1


def test_skip_remove_missing_keeps_entry(make_collection_factory, monkeypatch, capsys):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "5", "path": "./Missing.zip", "name": "Missing"})]}
    )

    code = run_main(
        monkeypatch,
        "--root",
        str(collection.root),
        "--system",
        "nes",
        "--skip-remove-missing",
    )

    assert code == 0
    entries = games_of(parse_gamelist(collection.gamelist("nes")))
    assert len(entries) == 1
    assert game_fields(entries[0])["path"] == "./Missing.zip"
    assert backup_names(collection.system_dir("nes")) == []
    assert "Kept entry with missing ROM" in capsys.readouterr().out


def test_missing_gameid_is_allocated(make_collection_factory, monkeypatch):
    game = make_game({"path": "./Foo.zip"})
    game.pop("gameid")
    collection = make_collection_factory(
        games={"nes": [game]},
        rom_files={"nes": ["Foo.zip"]},
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    fields = game_fields(games_of(parse_gamelist(collection.gamelist("nes")))[0])
    assert fields["gameid"] == "1"


def test_existing_id_is_reused_when_safe(make_collection_factory, monkeypatch):
    game = make_game({"path": "./Foo.zip", "id": "7"})
    game.pop("gameid")
    collection = make_collection_factory(
        games={"nes": [game]},
        rom_files={"nes": ["Foo.zip"]},
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    fields = game_fields(games_of(parse_gamelist(collection.gamelist("nes")))[0])
    assert fields["gameid"] == "7"


def test_conflicting_id_gets_a_new_gameid(make_collection_factory, monkeypatch):
    first = make_game({"gameid": "1", "path": "./One.zip", "name": "One"})
    second = make_game({"path": "./Two.zip", "name": "Two", "id": "1"})
    second.pop("gameid")
    collection = make_collection_factory(
        games={"nes": [first, second]},
        rom_files={"nes": ["One.zip", "Two.zip"]},
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    entries = games_of(parse_gamelist(collection.gamelist("nes")))
    fields = [game_fields(entry) for entry in entries]
    assert fields[0]["gameid"] == "1"
    assert fields[1]["gameid"] == "2"
    assert fields[1]["id"] == "1"


def test_normalize_language_titles(make_collection_factory, monkeypatch):
    game = make_game(
        {
            "gameid": "1",
            "path": "./Foo.zip",
            "zh_CN": "01 Chinese",
            "en_US": "2 English",
            "zh_TW": "No prefix",
            "ko_KR": " 3  Korean",
        }
    )
    collection = make_collection_factory(
        games={"nes": [game]},
        rom_files={"nes": ["Foo.zip"]},
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    fields = game_fields(games_of(parse_gamelist(collection.gamelist("nes")))[0])
    assert fields["zh_CN"] == "Chinese"
    assert fields["en_US"] == "English"
    assert fields["zh_TW"] == "No prefix"
    assert fields["ko_KR"] == "Korean"


def test_sort_alphabetically_by_name(make_collection_factory, monkeypatch):
    zed = make_game({"gameid": "1", "path": "./Zed.zip", "name": "Zed"})
    alpha = make_game({"gameid": "2", "path": "./Alpha.zip", "name": "Alpha"})
    collection = make_collection_factory(
        games={"nes": [zed, alpha]},
        rom_files={"nes": ["Zed.zip", "Alpha.zip"]},
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    names = [
        game_fields(entry)["name"]
        for entry in games_of(parse_gamelist(collection.gamelist("nes")))
    ]
    assert names == ["Alpha", "Zed"]


@pytest.mark.parametrize(
    "mode,expected_paths,expected_removed",
    [
        ("none", ["./a.zip", "./b.zip", "./a.zip"], 0),
        ("path", ["./a.zip", "./b.zip"], 1),
        ("gameid", ["./a.zip", "./a.zip"], 1),
        ("both", ["./a.zip"], 2),
    ],
)
def test_dedup_modes(mode, expected_paths, expected_removed):
    games = [
        make_game({"gameid": "1", "path": "./a.zip", "name": "A"}),
        make_game({"gameid": "1", "path": "./b.zip", "name": "B"}),
        make_game({"gameid": "2", "path": "./a.zip", "name": "C"}),
    ]
    root = ET.Element("gameList")
    for fields in games:
        entry = ET.SubElement(root, "game")
        for tag, value in fields.items():
            ET.SubElement(entry, tag).text = str(value)

    removals = gamelist_manager.deduplicate_games(root, "nes", mode)

    paths = [gamelist_manager.get_text(entry, "path") for entry in root]
    assert paths == expected_paths
    assert len(removals) == expected_removed


def test_non_game_children_keep_their_places(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    write_gamelist(
        collection.gamelist("nes"),
        [make_game({"gameid": "2", "path": "./Bar.zip", "name": "Bar"})],
        extras=[("info", "keep me")],
    )
    (collection.system_dir("nes") / "Bar.zip").write_bytes(b"rom")

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    root = parse_gamelist(collection.gamelist("nes"))
    tags = [gamelist_manager.local_tag(child) for child in root]
    assert tags[0] == "info"
    assert tags.count("game") == 1


def test_orphan_images_dry_run_apply_and_delete(make_collection_factory, monkeypatch, capsys):
    game = make_game({"gameid": "1", "path": "./Foo.zip", "image": "./images/used.png"})
    collection = make_collection_factory(
        games={"nes": [game]},
        rom_files={"nes": ["Foo.zip"]},
        image_files={"nes": ["used.png", "orphan.png"]},
    )
    images = collection.images("nes")

    code = run_main(
        monkeypatch, "--root", str(collection.root), "--system", "nes", "--dry-run"
    )
    assert code == 0
    assert {path.name for path in images.iterdir()} == {"used.png", "orphan.png"}
    out = capsys.readouterr().out
    assert "orphan.png" in out
    assert "Dry-run: no files changed" in out

    code = run_main(
        monkeypatch, "--root", str(collection.root), "--system", "nes", "--no-prompt"
    )
    assert code == 0
    assert {path.name for path in images.iterdir()} == {"used.png", "orphan.png"}
    assert "orphan.png" in capsys.readouterr().out

    code = run_main(
        monkeypatch,
        "--root",
        str(collection.root),
        "--system",
        "nes",
        "--delete-orphaned-images",
    )
    assert code == 0
    assert {path.name for path in images.iterdir()} == {"used.png"}
    assert "Deleted images" in capsys.readouterr().out


def test_dry_run_does_not_touch_files(make_collection_factory, monkeypatch):
    collection = make_collection_factory(rom_files={"nes": ["Mario.zip"]})
    before = snapshot_tree(collection.root)

    code = run_main(
        monkeypatch, "--root", str(collection.root), "--system", "nes", "--dry-run"
    )

    assert code == 0
    assert snapshot_tree(collection.root) == before


def test_force_write_creates_backup_without_changes(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    before = collection.gamelist("nes").read_bytes()

    code = run_main(
        monkeypatch,
        "--root",
        str(collection.root),
        "--system",
        "nes",
        "--force-write",
    )

    assert code == 0
    assert collection.gamelist("nes").read_bytes() == before
    assert len(backup_names(collection.system_dir("nes"))) == 1


def test_bom_is_preserved(make_collection_factory, monkeypatch):
    game = make_game({"path": "./Foo.zip"})
    game.pop("gameid")
    collection = make_collection_factory(
        games={"nes": [game]},
        rom_files={"nes": ["Foo.zip"]},
    )
    write_gamelist(collection.gamelist("nes"), [game], bom=True)

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    assert collection.gamelist("nes").read_bytes().startswith(b"\xef\xbb\xbf")


def test_double_declaration(make_collection_factory, monkeypatch):
    collection = make_collection_factory()

    code = run_main(
        monkeypatch,
        "--root",
        str(collection.root),
        "--system",
        "nes",
        "--force-write",
        "--xml-declaration",
        "double",
    )

    assert code == 0
    assert collection.gamelist("nes").read_bytes().startswith(
        b'<?xml version="1.0" encoding="utf-8"?>\n'
    )


def test_no_indent(make_collection_factory, monkeypatch):
    collection = make_collection_factory()
    collection.gamelist("nes").write_bytes(
        b"<?xml version='1.0' encoding='utf-8'?>\n<gameList />"
    )

    code = run_main(
        monkeypatch,
        "--root",
        str(collection.root),
        "--system",
        "nes",
        "--force-write",
        "--no-indent",
    )

    assert code == 0
    assert b"\n  <" not in collection.gamelist("nes").read_bytes()


def test_safe_write_matches_elementtree_serialization(tmp_path):
    def make_tree():
        root = ET.Element("gameList")
        entry = ET.SubElement(root, "game")
        ET.SubElement(entry, "name").text = "Foo"
        return ET.ElementTree(root)

    xml_path = tmp_path / "gamelist.xml"
    gamelist_manager.safe_write_xml(make_tree(), xml_path, indent=True)
    expected_tree = make_tree()
    ET.indent(expected_tree, space="  ")
    expected = ET.tostring(
        expected_tree.getroot(), encoding="utf-8", xml_declaration=True
    )
    assert xml_path.read_bytes() == expected
    assert list(tmp_path.glob("*.tmp")) == []

    double_path = tmp_path / "double.xml"
    gamelist_manager.safe_write_xml(
        make_tree(), double_path, indent=True, declaration="double"
    )
    body = ET.tostring(
        expected_tree.getroot(), encoding="utf-8", xml_declaration=False
    )
    assert double_path.read_bytes() == (
        b'<?xml version="1.0" encoding="utf-8"?>\n' + body
    )


def test_safe_write_preserves_bom_bytes(tmp_path):
    xml_path = tmp_path / "gamelist.xml"
    xml_path.write_bytes(b"\xef\xbb\xbf<?xml version='1.0' encoding='utf-8'?>\n<gameList />")
    tree = ET.ElementTree(ET.Element("gameList"))

    gamelist_manager.safe_write_xml(tree, xml_path, indent=True)

    data = xml_path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.count(b"\xef\xbb\xbf") == 1


def test_safe_write_rolls_back_when_installed_file_fails_validation(tmp_path, monkeypatch):
    xml_path = tmp_path / "gamelist.xml"
    original = b"<?xml version='1.0' encoding='utf-8'?>\n<gameList />"
    xml_path.write_bytes(original)
    tree = ET.ElementTree(ET.Element("gameList"))

    real_parse = gamelist_manager.ET.parse
    calls = {"count": 0}

    def flaky_parse(path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise ET.ParseError("simulated failure")
        return real_parse(path)

    monkeypatch.setattr(gamelist_manager.ET, "parse", flaky_parse)

    with pytest.raises(ET.ParseError):
        gamelist_manager.safe_write_xml(tree, xml_path)

    assert xml_path.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob("gamelist.xml.*.bak"))


def test_empty_collection_catalog_sync(make_collection_factory, monkeypatch):
    collection = make_collection_factory()

    code = run_main(monkeypatch, "--root", str(collection.root), "--system", "nes")

    assert code == 0
    members = read_zip_members(collection.root_dat)
    assert set(members) == {"fileinfo.001", "fileinfo.002", "fileinfo.003"}
    assert all(payload == b"" for payload in members.values())
    assert read_fileinfo(collection.fileinfo)[0] == 0


def test_roundtrip_writes_xml_and_skips_unchanged_catalog(
    make_collection_factory, monkeypatch, capsys
):
    collection = make_collection_factory()
    before = collection.gamelist("nes").read_bytes()
    catalog_before = (
        collection.root_dat.read_bytes(),
        collection.fileinfo.read_bytes(),
    )

    code = run_main(monkeypatch, "--root", str(collection.root), "--roundtrip")

    assert code == 0
    assert collection.gamelist("nes").read_bytes() == before
    assert len(backup_names(collection.system_dir("nes"))) == 1
    assert list(collection.root.glob("root.dat.*.bak")) == []
    assert list(collection.catalog_dir.glob("fileinfo.*.bak")) == []
    assert (
        collection.root_dat.read_bytes(),
        collection.fileinfo.read_bytes(),
    ) == catalog_before
    assert "Catalog unchanged" in capsys.readouterr().out


def test_second_apply_is_idempotent(make_collection_factory, monkeypatch):
    collection = make_collection_factory(rom_files={"nes": ["Mario.zip"]})
    assert run_main(monkeypatch, "--root", str(collection.root), "--system", "nes") == 0
    before = snapshot_tree(collection.root)

    assert run_main(monkeypatch, "--root", str(collection.root), "--system", "nes") == 0

    assert snapshot_tree(collection.root) == before
