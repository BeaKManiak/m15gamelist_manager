"""Import smoke tests for the flat script layout."""

from __future__ import annotations

import pytest


def test_cli_modules_import():
    import catalog_sync
    import delete_gamelist_backups
    import gamelist_manager
    import restore_catalog
    import restore_gamelist

    assert callable(gamelist_manager.main)
    assert callable(catalog_sync.sync_catalog)
    assert callable(restore_catalog.main)
    assert callable(restore_gamelist.main)
    assert callable(delete_gamelist_backups.main)
    assert len(gamelist_manager.SYSTEMS) == 23


def test_gui_module_mapping_is_importable_when_tkinter_exists():
    try:
        import m15_gui
    except ImportError as exc:
        pytest.skip(f"tkinter is not available: {exc}")

    import gamelist_manager

    assert m15_gui.SYSTEMS is gamelist_manager.SYSTEMS
