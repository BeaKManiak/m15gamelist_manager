"""Tests for the centralized system registry."""

from __future__ import annotations

import catalog_sync
import gamelist_manager
import systems


EXPECTED_ORDER = (
    "arcade", "fbneo", "mame", "atari2600", "atari5200", "atari7800",
    "atarilynx", "cps1", "cps2", "cps3", "pcengine", "nes", "nesh",
    "gb", "sfc", "snes", "gbc", "gba", "genesis", "gamegear",
    "megadrive", "ngpc", "psx",
)


def test_fileinfo_order_is_unchanged():
    assert systems.FILEINFO_SYSTEM_ORDER == EXPECTED_ORDER
    assert catalog_sync.FILEINFO_SYSTEM_ORDER is systems.FILEINFO_SYSTEM_ORDER


def test_systems_are_re_exported_for_compatibility():
    assert gamelist_manager.SYSTEMS is systems.SYSTEMS


def test_every_system_has_required_keys():
    for name, profile in systems.SYSTEMS.items():
        assert isinstance(name, str) and name
        assert profile["extensions"]
        assert "video_id" in profile
        assert "class_type" in profile
        assert "game_type" in profile
        assert "timer" in profile


def test_system_names_are_unique_case_insensitively():
    folded = [name.casefold() for name in systems.SYSTEMS]
    assert len(folded) == len(set(folded))
