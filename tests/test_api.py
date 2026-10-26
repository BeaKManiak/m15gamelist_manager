"""Tests for the public Options/run API."""

from __future__ import annotations

from pathlib import Path

import gamelist_manager
from conftest import make_game, parse_gamelist


def test_options_from_args_roundtrip_sets_every_switch():
    parser = gamelist_manager.build_parser()
    args = parser.parse_args(["--root", "/tmp", "--roundtrip"])
    options = gamelist_manager.options_from_args(args)

    assert options.skip_remove_missing
    assert options.skip_add
    assert options.skip_ids
    assert options.skip_normalize
    assert options.skip_sort
    assert options.dedup == "none"
    assert options.force_write
    assert options.no_prompt
    assert options.root == Path("/tmp").resolve()


def test_run_api_processes_without_argv(make_collection_factory):
    collection = make_collection_factory(
        games={
            "nes": [
                make_game(
                    {
                        "gameid": "1",
                        "path": "./Foo.zip",
                        "name": "Foo",
                        "zh_CN": "01 Foo",
                    }
                )
            ]
        },
        rom_files={"nes": ["Foo.zip"]},
    )
    options = gamelist_manager.Options(
        root=collection.root,
        system="nes",
        skip_sort=True,
    )

    result = gamelist_manager.run(options, output=lambda _text: None)

    assert result.exit_code == 0
    assert result.errors == 0
    assert result.catalog_summary is not None
    fields = {
        child.tag: child.text
        for child in next(iter(parse_gamelist(collection.gamelist("nes"))))
    }
    assert fields["zh_CN"] == "Foo"


def test_run_api_reports_system_results(make_collection_factory):
    collection = make_collection_factory(rom_files={"nes": ["Mario.zip"]})
    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes"),
        output=lambda _text: None,
    )

    assert set(result.systems) == {"nes"}
    assert result.systems["nes"]["added"] == ["Mario.zip"]
    assert result.systems["nes"]["status"] == "OK"


def test_gui_option_mapping_matches_cli_flags():
    import pytest

    try:
        import m15_gui
    except ImportError as exc:
        pytest.skip(f"tkinter is not available: {exc}")

    class Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    app = m15_gui.App.__new__(m15_gui.App)
    app.system_var = Var(m15_gui.ALL_SYSTEMS)
    app.remove_missing_var = Var(False)
    app.add_var = Var(False)
    app.ids_var = Var(False)
    app.normalize_var = Var(False)
    app.sort_var = Var(False)
    app.indent_var = Var(False)
    app.force_var = Var(True)
    app.orphans_var = Var(True)
    app.dedup_var = Var("path")
    app.decl_var = Var("double")

    options = app.build_manager_options("/tmp/roms", dry_run=False)

    assert options.root == Path("/tmp/roms")
    assert options.system is None
    assert options.delete_orphaned_images is True
    assert options.no_prompt is False
    assert options.skip_remove_missing is True
    assert options.skip_add is True
    assert options.skip_ids is True
    assert options.skip_normalize is True
    assert options.skip_sort is True
    assert options.dedup == "path"
    assert options.indent is False
    assert options.xml_declaration == "double"
    assert options.force_write is True

    preview = app.build_manager_options("/tmp/roms", dry_run=True)
    assert preview.delete_orphaned_images is False
    assert preview.no_prompt is True


def test_print_report_uses_previous_format(make_collection_factory):
    collection = make_collection_factory()
    result = gamelist_manager.run(
        gamelist_manager.Options(root=collection.root, system="nes", dry_run=True),
        output=lambda _text: None,
    )
    lines = []
    gamelist_manager.print_report(result, output=lines.append)

    text = "\n".join(lines)
    assert "FINAL REPORT" in text
    assert "Mode: DRY RUN (no writes or deletions)" in text
    assert "Finished: 1 systems, 0 errors, 0 skipped." in text
