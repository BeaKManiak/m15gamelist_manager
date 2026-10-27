import json
from types import SimpleNamespace

import gamelist_manager
import gui_support

gui = gui_support


def system_item(**overrides):
    item = {
        key: []
        for key in (
            "added",
            "removed",
            "deduplicated",
            "normalized",
            "ids_added",
            "deleted",
            "orphans",
        )
    }
    item["sorted"] = False
    item["status"] = "OK"
    item.update(overrides)
    return item


def run_result(systems, catalog_summary=None):
    return SimpleNamespace(
        systems=systems,
        errors=0,
        skipped=0,
        preflight_issues=None,
        catalog_summary=catalog_summary,
    )


def make_collection(base):
    base.mkdir(parents=True, exist_ok=True)
    (base / "root.dat").write_bytes(b"")
    (base / list(gui.SYSTEMS)[0]).mkdir()
    return base


def test_normalized_settings_ignores_bad_values():
    settings = gui.normalized_settings(
        {
            "system": "not-a-system",
            "dedup": "sometimes",
            "declaration": "fancy",
            "remove_missing": "yes",
            "keep_baks": "many",
        }
    )

    assert settings == gui.DEFAULT_SETTINGS


def test_normalized_settings_keeps_valid_values_and_clamps_counts():
    settings = gui.normalized_settings(
        {
            "dedup": "none",
            "declaration": "double",
            "force_write": True,
            "keep_baks": 1000,
        }
    )

    assert settings["dedup"] == "none"
    assert settings["declaration"] == "double"
    assert settings["force_write"] is True
    assert settings["keep_baks"] == 99
    assert gui.normalized_settings({"keep_baks": -5})["keep_baks"] == 0
    assert (
        gui.normalized_settings({"system": gui.ALL_SYSTEMS})["system"]
        == gui.ALL_SYSTEMS
    )


def test_config_roundtrip_creates_parent_folders(tmp_path):
    target = tmp_path / "nested" / "config.json"

    assert gui.load_config(target) == {}

    gui.save_config({"root": "/tmp/roms", "settings": {"add": True}}, target)

    assert gui.load_config(target) == {
        "root": "/tmp/roms",
        "settings": {"add": True},
    }


def test_config_tolerates_corrupt_or_wrong_shapes(tmp_path):
    target = tmp_path / "config.json"

    target.write_text("{not json", encoding="utf-8")
    assert gui.load_config(target) == {}

    target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert gui.load_config(target) == {}


def test_detect_rom_roots_checks_nested_roms_folder(tmp_path, monkeypatch):
    collection = make_collection(tmp_path / "card" / "roms")
    monkeypatch.setattr(
        gui, "rom_root_candidates", lambda: [(tmp_path / "card", False)]
    )

    assert gui.detect_rom_roots() == [str(collection.resolve())]


def test_detect_rom_roots_scans_one_level_when_deep(tmp_path, monkeypatch):
    collection = make_collection(tmp_path / "card" / "M15")
    monkeypatch.setattr(
        gui, "rom_root_candidates", lambda: [(tmp_path / "card", True)]
    )

    assert gui.detect_rom_roots() == [str(collection.resolve())]


def test_detect_rom_roots_keeps_candidate_order_and_dedupes(tmp_path, monkeypatch):
    first = make_collection(tmp_path / "first")
    second = make_collection(tmp_path / "second")
    monkeypatch.setattr(
        gui,
        "rom_root_candidates",
        lambda: [(second, False), (first, False), (second, False)],
    )

    assert gui.detect_rom_roots() == [
        str(second.resolve()),
        str(first.resolve()),
    ]


def test_detect_rom_roots_ignores_plain_folders(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setattr(gui, "rom_root_candidates", lambda: [(plain, True)])

    assert gui.detect_rom_roots() == []


def test_catalog_needs_refresh_reports_each_outcome(tmp_path):
    options = gamelist_manager.Options(root=tmp_path)
    calls = {}

    def unchanged(**kwargs):
        calls.update(kwargs)
        return {"unchanged": True}

    assert gui.catalog_needs_refresh(tmp_path, options, sync=unchanged) is False
    assert calls["dry_run"] is True
    assert calls["system_names"] == list(gui.SYSTEMS)

    def changed(**_kwargs):
        return {"unchanged": False}

    assert gui.catalog_needs_refresh(tmp_path, options, sync=changed) is True

    def failing(**_kwargs):
        raise FileNotFoundError("no catalog")

    assert gui.catalog_needs_refresh(tmp_path, options, sync=failing) is None


def test_summarize_result_counts_changes_and_untouched_systems():
    result = run_result(
        {
            "nes": system_item(added=["a.zip", "b.zip"], removed=["c.zip"], sorted=True),
            "snes": system_item(added=["d.zip"]),
            "gb": system_item(),
            "gba": system_item(status="SKIPPED"),
        }
    )

    counts = gui.summarize_result(result)

    assert counts["added"] == 3
    assert counts["removed"] == 1
    assert counts["systems_changed"] == 2
    assert counts["systems_unchanged"] == 1
    assert counts["sorted_systems"] == 1


def test_confirmation_lines_are_plain_language():
    counts = gui.summarize_result(
        run_result(
            {
                "nes": system_item(added=["a.zip", "b.zip", "c.zip"], removed=["d.zip"]),
                "snes": system_item(),
            }
        )
    )

    text = "\n".join(gui.format_confirmation(counts, catalog_refresh=True))

    assert "3 new games will be added" in text
    assert "1 entry will be removed (the file is gone)" in text
    assert "1 system already up to date" in text
    assert "The device catalog will be refreshed" in text
    assert "Changed gamelists and catalog files are backed up first." in text


def test_confirmation_mentions_catalog_only_when_it_changes():
    counts = gui.summarize_result(run_result({"nes": system_item(added=["a.zip"])}))

    text = "\n".join(gui.format_confirmation(counts, catalog_refresh=False))

    assert "device catalog" not in text


def test_confirmation_mentions_orphan_deletion_when_enabled():
    counts = gui.summarize_result(
        run_result({"nes": system_item(orphans=["a.png", "b.png"])})
    )

    text = "\n".join(
        gui.format_confirmation(counts, catalog_refresh=False, delete_orphans=True)
    )

    assert "2 unused images will be deleted permanently" in text
    assert "will be deleted permanently" not in "\n".join(
        gui.format_confirmation(counts, catalog_refresh=False)
    )


def test_format_last_run_summarizes_applied_changes():
    result = run_result(
        {"nes": system_item(added=["a.zip", "b.zip"], removed=["c.zip"])},
        catalog_summary={"unchanged": False},
    )

    assert gui.format_last_run(result) == "2 new games · 1 removed · catalog refreshed"


def test_format_last_run_says_no_changes_when_nothing_happened():
    result = run_result({"nes": system_item()}, catalog_summary={"unchanged": True})

    assert gui.format_last_run(result) == "no changes"


def test_pluralization():
    assert gui.plural(1, "game") == "1 game"
    assert gui.plural(2, "game") == "2 games"
    assert gui.plural(2, "entry", "entries") == "2 entries"
