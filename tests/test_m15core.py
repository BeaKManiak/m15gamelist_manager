"""Tests for the shared core helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import catalog_sync
import gamelist_manager
import m15core


def test_xml_helpers_match_previous_behavior():
    entry = ET.Element("game")
    ET.SubElement(entry, "name").text = "  Foo  "
    ET.SubElement(entry, "{urn:test}gameid").text = " 7 "

    assert m15core.local_tag(entry[0]) == "name"
    assert m15core.local_tag(entry[1]) == "gameid"
    assert m15core.get_text(entry, "name") == "Foo"
    assert m15core.get_text(entry, "gameid") == "7"
    assert m15core.get_child(entry, "gameid") is entry[1]
    assert m15core.set_child_text(entry, "name", "Bar").text == "Bar"


def test_manager_helpers_are_aliases_to_core():
    assert gamelist_manager.local_tag is m15core.local_tag
    assert gamelist_manager.get_child is m15core.get_child
    assert gamelist_manager.get_text is m15core.get_text
    assert gamelist_manager.set_child_text is m15core.set_child_text


def test_catalog_helpers_are_aliases_to_core():
    assert catalog_sync._tag is m15core.local_tag
    entry = ET.Element("game")
    ET.SubElement(entry, "name").text = "Foo"
    assert catalog_sync._text(entry, "name") == "Foo"


def test_folder_lookup_modes(tmp_path, monkeypatch):
    direct = tmp_path / "nes"
    direct.mkdir()
    assert m15core.find_system_folder(tmp_path, "nes") == direct
    assert gamelist_manager.find_system_folder(tmp_path, "nes") == direct
    assert catalog_sync._folder(tmp_path, "nes") == direct

    def fail(self):
        raise OSError("no listing")

    monkeypatch.setattr(Path, "iterdir", fail)
    assert m15core.find_system_folder(tmp_path, "missing", ignore_oserror=True) is None
    assert gamelist_manager.find_system_folder(tmp_path, "missing") is None
    with pytest.raises(OSError, match="no listing"):
        m15core.find_system_folder(tmp_path, "missing")
    with pytest.raises(OSError, match="no listing"):
        catalog_sync._folder(tmp_path, "missing")
