"""Tests for the extracted processing units."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import gamelist_manager
from conftest import make_game, snapshot_tree, write_gamelist


def test_spinner_handles_missing_stdout(monkeypatch):
    monkeypatch.setattr(gamelist_manager.sys, "stdout", None)
    with gamelist_manager.Spinner("Working") as spinner:
        assert spinner.thread is None


def test_spinner_can_be_disabled(monkeypatch):
    class FakeStream:
        def __init__(self):
            self.writes = []

        def isatty(self):
            return True

        def write(self, text):
            self.writes.append(text)

        def flush(self):
            pass

    stream = FakeStream()
    monkeypatch.setattr(gamelist_manager.sys, "stdout", stream)
    with gamelist_manager.Spinner("Working", enabled=False) as spinner:
        assert spinner.thread is None
    assert stream.writes == []


def test_id_allocator_skips_used_numeric_and_text_ids():
    allocator = gamelist_manager.IdAllocator(
        {
            gamelist_manager.id_key("1"): [],
            gamelist_manager.id_key("2"): [],
            gamelist_manager.id_key("abc"): [],
        },
        max_numeric_id=2,
    )

    assert allocator.allocate() == "3"
    assert allocator.allocate() == "4"
    allocator.reuse(gamelist_manager.id_key("5"))
    assert allocator.allocate() == "6"


def test_collect_existing_ids_finds_duplicates_across_systems():
    def record(games):
        root = ET.Element("gameList")
        for fields in games:
            entry = ET.SubElement(root, "game")
            for tag, value in fields.items():
                ET.SubElement(entry, tag).text = str(value)
        return {"status": "OK", "root": root}

    records = {
        "nes": record([make_game({"gameid": "1", "path": "./a.zip"})]),
        "snes": record([make_game({"gameid": "001", "path": "./b.zip"})]),
    }

    _existing, max_id, duplicates = gamelist_manager.collect_existing_ids(records)

    assert max_id == 1
    assert len(duplicates) == 1
    assert len(duplicates[0][1]) == 2


def test_process_system_dry_run_does_not_write(make_collection_factory):
    collection = make_collection_factory(
        games={"nes": [make_game({"gameid": "1", "path": "./Foo.zip"})]},
        rom_files={"nes": ["Foo.zip"]},
    )
    records = gamelist_manager.read_system_xmls(collection.root, ["nes"])
    before = snapshot_tree(collection.root)
    options = gamelist_manager.Options(
        root=collection.root, system="nes", dry_run=True
    )

    result = gamelist_manager.process_system(
        "nes", records["nes"], options, gamelist_manager.IdAllocator({}, 0)
    )

    assert result["status"] == "OK"
    assert snapshot_tree(collection.root) == before


def test_find_orphan_images_and_delete(make_collection_factory):
    collection = make_collection_factory(
        image_files={"nes": ["used.png", "orphan.png"]}
    )
    root = ET.Element("gameList")
    entry = ET.SubElement(root, "game")
    ET.SubElement(entry, "image").text = "./images/used.png"

    orphans, note = gamelist_manager.find_orphan_images(
        collection.system_dir("nes"), root
    )

    assert note is None
    assert [path.name for path in orphans] == ["orphan.png"]

    result = {"orphans": orphans, "deleted": [], "notes": []}
    gamelist_manager.delete_orphans_if_requested(
        "nes",
        result,
        gamelist_manager.Options(root=collection.root, no_prompt=True),
        output=lambda _text: None,
    )
    assert result["deleted"] == []
    assert (collection.images("nes") / "orphan.png").exists()

    gamelist_manager.delete_orphans_if_requested(
        "nes",
        result,
        gamelist_manager.Options(
            root=collection.root, delete_orphaned_images=True
        ),
        output=lambda _text: None,
    )
    assert result["deleted"] == ["orphan.png"]
    assert not (collection.images("nes") / "orphan.png").exists()


def test_run_catalog_sync_dry_run(make_collection_factory):
    collection = make_collection_factory()
    lines = []

    skipped, error, summary = gamelist_manager.run_catalog_sync(
        gamelist_manager.Options(root=collection.root, dry_run=True),
        collection.root,
        output=lines.append,
    )

    assert skipped is True
    assert error is False
    assert summary is None
    assert "dry-run does not write catalog files" in "\n".join(lines)


def test_write_gamelist_helper_is_well_formed(make_collection_factory):
    collection = make_collection_factory()
    write_gamelist(collection.gamelist("nes"), [make_game()])
    assert ET.parse(collection.gamelist("nes")).getroot().tag == "gameList"
