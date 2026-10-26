"""System registry shared by the manager, catalog, and GUI."""

from __future__ import annotations

SYSTEMS = {
    "arcade": {
        "extensions": {".fba", ".zip"}, "video_id": "0",
        "class_type": "0", "game_type": "0", "timer": "/sdcard/game/cps",
    },
    "atari2600": {
        "extensions": {".a26"}, "video_id": "15",
        "class_type": "15", "game_type": "0", "timer": "atari2600",
    },
    "atari5200": {
        "extensions": {".zip"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "atari5200",
    },
    "atari7800": {
        "extensions": {".a78", ".zip"}, "video_id": "17",
        "class_type": "17", "game_type": "0", "timer": "atari7800",
    },
    "atarilynx": {
        "extensions": {".zip"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "atarilynx",
    },
    "cps1": {
        "extensions": {".fba", ".zip"}, "video_id": "0",
        "class_type": "0", "game_type": "0", "timer": "cps1",
    },
    "cps2": {
        "extensions": {".fba", ".zip"}, "video_id": "0",
        "class_type": "0", "game_type": "0", "timer": "cps2",
    },
    "cps3": {
        "extensions": {".zip", ".fba"}, "video_id": "18",
        "class_type": "18", "game_type": "0", "timer": "/sdcard/game/cps",
    },
    "fbneo": {
        "extensions": {".zip", ".fba"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "fbneo",
    },
    "gb": {
        "extensions": {".zip", ".gb"}, "video_id": "7",
        "class_type": "7", "game_type": "0", "timer": "gb",
    },
    "gba": {
        "extensions": {".zip"}, "video_id": "7",
        "class_type": "7", "game_type": "0", "timer": "gba",
    },
    "gbc": {
        "extensions": {".zip"}, "video_id": "7",
        "class_type": "7", "game_type": "0", "timer": "gbc",
    },
    "gamegear": {
        "extensions": {".zip"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "gamegear",
    },
    "genesis": {
        "extensions": {".zip"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "genesis",
    },
    "mame": {
        "extensions": {".zip"}, "video_id": "0",
        "class_type": "0", "game_type": "0", "timer": "/sdcard/game/cps",
    },
    "megadrive": {
        "extensions": {".zip"}, "video_id": "5",
        "class_type": "5", "game_type": "0", "timer": "megadrive",
    },
    "nes": {
        "extensions": {".zip"}, "video_id": "0",
        "class_type": "0", "game_type": "2", "timer": "nes",
    },
    "nesh": {
        "extensions": {".zip"}, "video_id": "0",
        "class_type": "0", "game_type": "2", "timer": "nesh",
    },
    "ngpc": {
        "extensions": {".zip"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "ngpc",
    },
    "pcengine": {
        "extensions": {".zip"}, "video_id": "-12",
        "class_type": "-12", "game_type": "0", "timer": "pcengine",
    },
    "psx": {
        "extensions": {
            ".img", ".pbp", ".iso", ".bin", ".chd", ".cue", ".ccd",
            ".mdf", ".mds", ".nrg", ".cso", ".zso", ".ecm",
        },
        "video_id": "x", "class_type": None,
        "game_type": "0", "timer": "psx",
        "core": "pcsx_rearmed_chd_libretro.so",
    },
    "sfc": {
        "extensions": {".zip"}, "video_id": "6",
        "class_type": "6", "game_type": "0", "timer": "sfc",
    },
    "snes": {
        "extensions": {".zip"}, "video_id": "6",
        "class_type": "6", "game_type": "0", "timer": "snes",
    },
}

# fileinfo fields are: total, reserved, then counts in this exact device order.
FILEINFO_SYSTEM_ORDER = (
    "arcade", "fbneo", "mame", "atari2600", "atari5200", "atari7800",
    "atarilynx", "cps1", "cps2", "cps3", "pcengine", "nes", "nesh",
    "gb", "sfc", "snes", "gbc", "gba", "genesis", "gamegear",
    "megadrive", "ngpc", "psx",
)

if set(FILEINFO_SYSTEM_ORDER) != set(SYSTEMS):
    raise RuntimeError("FILEINFO_SYSTEM_ORDER must match the systems registry")
