#!/usr/bin/env python3
"""
Gamelist manager with per-feature switches, for isolating what breaks the M15.

Every behavior that modifies the XML can be turned off:
  --skip-remove-missing   keep entries whose ROM file is missing
  --skip-add              do not add newly found ROMs
  --skip-ids              do not add missing <gameid> to existing entries
  --skip-normalize        do not strip numeric prefixes from titles
  --skip-sort             do not sort alphabetically
  --dedup {none,path,gameid,both}   what counts as a duplicate (default both)

Writer options:
  --no-indent             do not reformat whitespace with ET.indent
  --xml-declaration {et,double}   et = ElementTree default (single quotes),
                                  double = <?xml version="1.0" encoding="utf-8"?>
  --force-write           write even if nothing changed (round-trip test)

Shortcut:
  --roundtrip             all features off + force-write: parse and re-save only
"""

import argparse
import datetime
import os
import re
import shutil
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from catalog_sync import sync_catalog
from m15core import (
    find_system_folder as _find_system_folder,
    get_child,
    get_text,
    local_tag,
    set_child_text,
)

LANGUAGES = ("zh_CN", "en_US", "zh_TW", "ko_KR")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

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


class Spinner:
    def __init__(self, message):
        self.message = message
        self.stop_event = threading.Event()
        self.thread = None

    def __enter__(self):
        if sys.stdout.isatty():
            self.thread = threading.Thread(
                target=self._animate, daemon=True
            )
            self.thread.start()
        return self

    def _animate(self):
        frames = "|/-\\"
        i = 0
        while not self.stop_event.wait(0.12):
            sys.stdout.write(
                f"\r{self.message} {frames[i % len(frames)]}"
            )
            sys.stdout.flush()
            i += 1

    def __exit__(self, *args):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
            sys.stdout.write("\r" + " " * (len(self.message) + 8) + "\r")
            sys.stdout.flush()


def id_key(value):
    """Numeric IDs compare by value; text IDs compare case-insensitively."""
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return ("numeric", str(int(value)))
    return ("text", value.casefold())


def gameid_sort_key(entry, original_index):
    value = get_text(entry, "gameid")
    if value.isdigit():
        return (0, int(value), original_index)
    if value:
        return (1, value.casefold(), original_index)
    return (2, "", original_index)


def strip_numeric_prefix(value):
    """Remove a leading number only when followed by whitespace."""
    if not value:
        return value
    match = re.match(r"^\s*\d+\s+", value)
    return value[match.end():].lstrip() if match else value


def normalize_language_fields(entry):
    changed = []
    for language in LANGUAGES:
        item = get_child(entry, language)
        if item is None:
            continue
        old_value = item.text or ""
        new_value = strip_numeric_prefix(old_value)
        if new_value != old_value:
            item.text = new_value
            changed.append(language)
    return changed


def find_system_folder(root, name):
    return _find_system_folder(root, name, ignore_oserror=True)


def scan_game_files(folder, extensions):
    files = {}
    with Spinner(f"Scanning {folder.name} ROM files"):
        for path in folder.iterdir():
            if not path.is_file() or path.name.startswith("._"):
                continue
            if path.suffix.lower() in extensions:
                files[path.name.casefold()] = path
    return dict(sorted(files.items()))


def resolve_game_path(folder, raw_path):
    value = raw_path.strip().replace("\\", os.sep)
    if value.startswith("./") or value.startswith(".\\"):
        value = value[2:]
    return (folder / value).resolve()


def make_entry(filename, gameid, profile):
    stem = Path(filename).stem
    entry = ET.Element("game")

    def add(tag, value):
        ET.SubElement(entry, tag).text = str(value)

    add("gameid", gameid)
    add("path", f"./{filename}")
    add("image", f"./images/{stem}.png")
    add("video_id", profile["video_id"])

    if profile.get("class_type") is not None:
        add("class_type", profile["class_type"])

    if profile.get("core"):
        add("core", profile["core"])

    add("game_type", profile["game_type"])
    add("timer", profile["timer"])

    for language in LANGUAGES:
        add(language, stem)

    add("name", stem)
    return entry


def timestamped_backup(xml_path):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = xml_path.with_name(f"{xml_path.name}.{stamp}.bak")
    suffix = 1
    while candidate.exists():
        candidate = xml_path.with_name(
            f"{xml_path.name}.{stamp}_{suffix}.bak"
        )
        suffix += 1
    return candidate


def safe_write_xml(tree, xml_path, indent=True, declaration="et"):
    """
    Write and validate a temporary XML, back up the original, then replace it.
    Preserves an existing UTF-8 BOM.

    indent:      run ET.indent before writing
    declaration: "et"     -> ElementTree's own declaration (single quotes)
                 "double" -> <?xml version="1.0" encoding="utf-8"?>
    """
    temp_path = None
    backup_path = None
    had_bom = False

    if xml_path.exists():
        with xml_path.open("rb") as stream:
            had_bom = stream.read(3) == b"\xef\xbb\xbf"

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{xml_path.name}.",
        suffix=".tmp",
        dir=xml_path.parent,
    )
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        if indent:
            ET.indent(tree, space="  ")

        if declaration == "double":
            tree.write(temp_path, encoding="utf-8", xml_declaration=False)
            body = temp_path.read_bytes()
            temp_path.write_bytes(
                b'<?xml version="1.0" encoding="utf-8"?>\n' + body
            )
        else:
            tree.write(temp_path, encoding="utf-8", xml_declaration=True)

        if had_bom:
            temp_path.write_bytes(
                b"\xef\xbb\xbf" + temp_path.read_bytes()
            )

        ET.parse(temp_path)

        if xml_path.exists():
            backup_path = timestamped_backup(xml_path)
            shutil.copy2(xml_path, backup_path)

        os.replace(temp_path, xml_path)
        temp_path = None

        try:
            ET.parse(xml_path)
        except Exception:
            if backup_path and backup_path.exists():
                shutil.copy2(backup_path, xml_path)
            raise

        return backup_path

    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def read_system_xmls(root_folder, system_names):
    records = {}

    for name in sorted(system_names, key=str.casefold):
        folder = find_system_folder(root_folder, name)

        if folder is None:
            records[name] = {
                "status": "SKIPPED",
                "notes": ["System folder not found."],
            }
            continue

        xml_path = folder / "gamelist.xml"
        if not xml_path.is_file():
            records[name] = {
                "status": "SKIPPED",
                "folder": folder,
                "xml_path": xml_path,
                "notes": ["gamelist.xml not found."],
            }
            continue

        try:
            with Spinner(f"Reading {name} XML"):
                tree = ET.parse(xml_path)

            root = tree.getroot()
            if local_tag(root) != "gameList":
                raise ValueError(
                    f"Unexpected root <{local_tag(root)}>; expected <gameList>."
                )

            records[name] = {
                "status": "OK",
                "folder": folder,
                "xml_path": xml_path,
                "tree": tree,
                "root": root,
                "notes": [],
            }

        except Exception as exc:
            records[name] = {
                "status": "ERROR",
                "folder": folder,
                "xml_path": xml_path,
                "notes": [f"Could not read XML: {exc}"],
            }

    return records


def entry_label(system_name, entry, index):
    path = get_text(entry, "path") or "(no path)"
    gameid = get_text(entry, "gameid") or "(no gameid)"
    name = get_text(entry, "name") or "(no name)"
    return (
        f"{system_name}/{path} "
        f"[gameid={gameid!r}, name={name!r}, entry #{index}]"
    )


def replace_game_children(root, entries):
    """Replace direct <game> slots; non-game children keep their order."""
    original_children = list(root)
    entry_iter = iter(entries)
    replacement_children = []

    for child in original_children:
        if local_tag(child) == "game":
            replacement = next(entry_iter, None)
            if replacement is not None:
                replacement_children.append(replacement)
        else:
            replacement_children.append(child)

    replacement_children.extend(entry_iter)
    root[:] = replacement_children


def deduplicate_games(root, system_name, mode="both"):
    """
    Remove duplicate entries.

    mode:
      "path"   -> only entries sharing an exact <path>
      "gameid" -> only entries sharing a canonical <gameid>
      "both"   -> either (original behavior)
      "none"   -> do nothing
    """
    if mode == "none":
        return []

    check_path = mode in ("path", "both")
    check_id = mode in ("gameid", "both")

    games = [
        (index, entry)
        for index, entry in enumerate(list(root), start=1)
        if local_tag(entry) == "game"
    ]

    path_counts = defaultdict(int)
    for _, entry in games:
        path = get_text(entry, "path")
        if path:
            path_counts[path] += 1

    ordered_games = sorted(
        games,
        key=lambda pair: (
            -path_counts.get(get_text(pair[1], "path"), 0),
            gameid_sort_key(pair[1], pair[0]),
        ),
    )

    kept = []
    kept_by_path = {}
    kept_by_id = {}
    removals = []

    for original_index, entry in ordered_games:
        path = get_text(entry, "path")
        gameid = get_text(entry, "gameid")
        canonical_id = id_key(gameid)

        path_conflict = (
            kept_by_path.get(path) if check_path and path else None
        )
        id_conflict = (
            kept_by_id.get(canonical_id)
            if check_id and canonical_id is not None
            else None
        )

        if path_conflict is not None or id_conflict is not None:
            reasons = []

            if path_conflict is not None:
                reasons.append(
                    f"duplicate exact path {path!r}; "
                    f"kept gameid {get_text(path_conflict, 'gameid')!r}"
                )

            if id_conflict is not None:
                reasons.append(
                    f"duplicate gameid {gameid!r}; "
                    f"kept path {get_text(id_conflict, 'path')!r}"
                )

            removals.append({
                "system": system_name,
                "entry": entry,
                "index": original_index,
                "path": path or "(no path)",
                "gameid": gameid or "(no gameid)",
                "name": get_text(entry, "name") or "(no name)",
                "reason": "; ".join(reasons),
            })
            continue

        kept.append(entry)

        if path:
            kept_by_path[path] = entry

        if canonical_id is not None:
            kept_by_id[canonical_id] = entry

    if removals:
        # Keep the surviving entries in their ORIGINAL document order,
        # not in the priority order used to pick winners.
        kept_ids = {id(e) for e in kept}
        original_order = [e for _, e in games if id(e) in kept_ids]
        replace_game_children(root, original_order)

    return removals


def sort_games_alphabetically(root):
    original_children = list(root)
    original_games = [
        child for child in original_children
        if local_tag(child) == "game"
    ]

    sorted_games = sorted(
        original_games,
        key=lambda entry: get_text(entry, "name").strip().casefold(),
    )

    if original_games == sorted_games:
        return False

    game_iter = iter(sorted_games)
    reordered_children = [
        next(game_iter) if local_tag(child) == "game" else child
        for child in original_children
    ]

    root[:] = reordered_children
    return True


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize gamelists with per-feature switches for "
            "isolating problems."
        )
    )
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parent,
                        help="Parent directory containing the system folders.")
    parser.add_argument("--system", choices=sorted(SYSTEMS),
                        help="Process one system.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing or deleting.")
    parser.add_argument("--delete-orphaned-images", action="store_true",
                        help="Delete orphan images without prompting.")
    parser.add_argument("--no-prompt", action="store_true",
                        help="Report orphan images without asking.")
    parser.add_argument(
        "--root-dat",
        type=Path,
        help="Path to root.dat (default: <root>/root.dat).",
    )
    parser.add_argument(
        "--fileinfo",
        type=Path,
        help="Path to cubegm/fileinfo (default: <root>/../cubegm/fileinfo).",
    )

    feat = parser.add_argument_group("feature switches")
    feat.add_argument("--skip-remove-missing", action="store_true",
                      help="Keep entries whose ROM file is missing.")
    feat.add_argument("--skip-add", action="store_true",
                      help="Do not add newly discovered ROMs.")
    feat.add_argument("--skip-ids", action="store_true",
                      help="Do not add <gameid> to entries lacking one.")
    feat.add_argument("--skip-normalize", action="store_true",
                      help="Do not strip numeric prefixes from titles.")
    feat.add_argument("--skip-sort", action="store_true",
                      help="Do not sort entries alphabetically.")
    feat.add_argument("--dedup", choices=["none", "path", "gameid", "both"],
                      default="both",
                      help="Duplicate criteria (default: both).")

    writer = parser.add_argument_group("writer options")
    writer.add_argument("--no-indent", action="store_true",
                        help="Skip ET.indent whitespace reformatting.")
    writer.add_argument("--xml-declaration", choices=["et", "double"],
                        default="et",
                        help="et: single-quoted (ElementTree default); "
                             "double: <?xml version=\"1.0\" ...?>")
    writer.add_argument("--force-write", action="store_true",
                        help="Write XML even when nothing changed.")
    writer.add_argument("--roundtrip", action="store_true",
                        help="All features off + force-write (parse and "
                             "re-save only).")

    args = parser.parse_args()

    if args.roundtrip:
        args.skip_remove_missing = True
        args.skip_add = True
        args.skip_ids = True
        args.skip_normalize = True
        args.skip_sort = True
        args.dedup = "none"
        args.force_write = True
        args.no_prompt = True

    root_folder = args.root.expanduser().resolve()
    if not root_folder.is_dir():
        parser.error(f"Root folder does not exist: {root_folder}")

    system_names = list(SYSTEMS) if args.system is None else [args.system]
    records = read_system_xmls(root_folder, system_names)

    existing_gameids = defaultdict(list)
    max_numeric_id = 0

    for system_name, record in records.items():
        if record.get("status") != "OK":
            continue

        for index, entry in enumerate(record["root"], start=1):
            if local_tag(entry) != "game":
                continue

            for tag in ("gameid", "id"):
                value = get_text(entry, tag)
                if value.isdigit():
                    max_numeric_id = max(max_numeric_id, int(value))

            value = get_text(entry, "gameid")
            key = id_key(value)
            if key is not None:
                existing_gameids[key].append({
                    "system": system_name,
                    "entry": entry,
                    "index": index,
                    "label": entry_label(system_name, entry, index),
                    "value": value,
                })

    duplicates = [
        (key, occurrences)
        for key, occurrences in existing_gameids.items()
        if len(occurrences) > 1
    ]
    duplicates.sort(key=lambda pair: str(pair[0]))

    used_ids = set(existing_gameids.keys())
    next_id = max_numeric_id + 1

    def allocate_id():
        nonlocal next_id
        while id_key(str(next_id)) in used_ids:
            next_id += 1
        value = str(next_id)
        used_ids.add(id_key(value))
        next_id += 1
        return value

    results = {}

    for system_name in sorted(records, key=str.casefold):
        record = records[system_name]
        result = {
            "system": system_name,
            "status": record.get("status", "ERROR"),
            "added": [],
            "removed": [],
            "deduplicated": [],
            "normalized": [],
            "ids_added": [],
            "id_conflicts": [],
            "orphans": [],
            "deleted": [],
            "backup": None,
            "notes": list(record.get("notes", [])),
            "sorted": False,
        }
        results[system_name] = result

        if record.get("status") != "OK":
            continue

        folder = record["folder"]
        xml_path = record["xml_path"]
        tree = record["tree"]
        root = record["root"]
        profile = SYSTEMS[system_name]
        xml_changed = False

        try:
            discovered = scan_game_files(folder, profile["extensions"])
        except OSError as exc:
            result["status"] = "ERROR"
            result["notes"].append(f"Could not scan game files: {exc}")
            continue

        retained = []
        known_files = set()

        for entry in list(root):
            if local_tag(entry) != "game":
                continue

            raw_path = get_text(entry, "path")
            if not raw_path:
                retained.append(entry)
                result["notes"].append(
                    "Kept an existing game entry without <path>."
                )
                continue

            resolved = resolve_game_path(folder, raw_path)
            rom_exists = resolved.is_file()

            if not rom_exists:
                if not args.skip_remove_missing:
                    result["removed"].append(raw_path)
                    xml_changed = True
                    continue
                result["notes"].append(
                    f"Kept entry with missing ROM: {raw_path}"
                )

            retained.append(entry)
            if rom_exists:
                known_files.add(resolved.name.casefold())

            if not args.skip_ids:
                existing_gameid = get_text(entry, "gameid")
                existing_id = get_text(entry, "id")

                if not existing_gameid:
                    old_id_key = id_key(existing_id)

                    if (
                        existing_id
                        and old_id_key is not None
                        and old_id_key not in used_ids
                    ):
                        new_gameid = existing_id
                        used_ids.add(old_id_key)
                    else:
                        new_gameid = allocate_id()
                        if existing_id:
                            result["id_conflicts"].append(
                                f"{raw_path}: existing <id>{existing_id}</id> "
                                f"was not safe to reuse; assigned "
                                f"<gameid>{new_gameid}</gameid>."
                            )

                    set_child_text(entry, "gameid", new_gameid)
                    result["ids_added"].append(
                        f"{raw_path} -> {new_gameid}"
                    )
                    xml_changed = True

            if not args.skip_normalize:
                changed_languages = normalize_language_fields(entry)
                if changed_languages:
                    result["normalized"].append(
                        f"{raw_path} ({', '.join(changed_languages)})"
                    )
                    xml_changed = True

        replace_game_children(root, retained)

        if not args.skip_add:
            for _, game_file in discovered.items():
                if game_file.name.casefold() in known_files:
                    continue

                new_gameid = allocate_id()
                root.append(make_entry(game_file.name, new_gameid, profile))
                result["added"].append(game_file.name)
                known_files.add(game_file.name.casefold())
                xml_changed = True

        dedup_removals = deduplicate_games(root, system_name, args.dedup)
        if dedup_removals:
            result["deduplicated"].extend(dedup_removals)
            xml_changed = True

        referenced_images = set()
        for entry in root:
            if local_tag(entry) != "game":
                continue

            image_value = get_text(entry, "image")
            if image_value:
                referenced_images.add(
                    Path(image_value.replace("\\", "/")).name.casefold()
                )

        image_folder = folder / "images"
        if image_folder.is_dir():
            try:
                result["orphans"] = sorted(
                    [
                        path for path in image_folder.iterdir()
                        if path.is_file()
                        and path.suffix.lower() in IMAGE_EXTENSIONS
                        and path.name.casefold() not in referenced_images
                    ],
                    key=lambda path: path.name.casefold(),
                )
            except OSError as exc:
                result["notes"].append(f"Could not scan images: {exc}")

        if not args.skip_sort:
            if sort_games_alphabetically(root):
                result["sorted"] = True
                result["notes"].append(
                    "Game entries sorted alphabetically by <name>."
                )
                xml_changed = True

        if args.dry_run:
            result["notes"].append("Dry-run: no files changed.")
            continue

        if xml_changed or args.force_write:
            try:
                result["backup"] = safe_write_xml(
                    tree, xml_path,
                    indent=not args.no_indent,
                    declaration=args.xml_declaration,
                )
            except Exception as exc:
                result["status"] = "ERROR"
                result["notes"].append(f"XML replacement failed: {exc}")
                continue

        if result["orphans"]:
            if args.delete_orphaned_images:
                should_delete = True
            elif args.no_prompt:
                should_delete = False
            else:
                print(f"\n{system_name}: orphaned images")
                for path in result["orphans"]:
                    print(f"  {path.name}")
                try:
                    answer = input(
                        "Delete these images? [y/N]: "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "n"
                should_delete = answer in {"y", "yes"}

            if should_delete:
                for path in result["orphans"]:
                    try:
                        path.unlink()
                        result["deleted"].append(path.name)
                    except OSError as exc:
                        result["notes"].append(
                            f"Could not delete {path.name}: {exc}"
                        )

                # Synchronize the global catalog after XML processing.
    if args.dry_run:
        print(
            "\nGlobal catalog synchronization skipped: "
            "dry-run does not write catalog files."
        )
    else:
        catalog_root = args.root_dat or (root_folder / "root.dat")
        catalog_counts = (
            args.fileinfo
            or (root_folder.parent / "cubegm" / "fileinfo")
        )

        try:
            summary = sync_catalog(
                root_folder=root_folder,
                root_dat=catalog_root,
                fileinfo_path=catalog_counts,
                system_names=list(SYSTEMS),
                dry_run=False,
            )
            print("\nGLOBAL CATALOG SYNCHRONIZATION")
            print(f"  Games indexed: {summary['games']}")
            print(f"  root.dat backup: {summary['root_dat_backup']}")
            print(f"  fileinfo backup: {summary['fileinfo_backup']}")
            print("  Catalog validation: passed")
        except Exception as exc:
            print(f"\nGLOBAL CATALOG SYNCHRONIZATION FAILED: {exc}")
            print(
                "  The catalog files were not intentionally left partially "
                "updated; check the backups and XML/catalog consistency."
            )
            catalog_sync_error = True
        else:
            catalog_sync_error = False

    # Final report.
    print("\n" + "=" * 84)
    print("FINAL REPORT")
    print("=" * 84)
    print(f"Root: {root_folder}")
    print(
        "Mode: DRY RUN (no writes or deletions)"
        if args.dry_run else "Mode: APPLY"
    )
    print("Features:")
    print(f"  remove missing ROM entries : {'OFF' if args.skip_remove_missing else 'on'}")
    print(f"  add new ROMs               : {'OFF' if args.skip_add else 'on'}")
    print(f"  add missing <gameid>       : {'OFF' if args.skip_ids else 'on'}")
    print(f"  normalize titles           : {'OFF' if args.skip_normalize else 'on'}")
    print(f"  alphabetical sort          : {'OFF' if args.skip_sort else 'on'}")
    print(f"  dedup                      : {args.dedup}")
    print(f"  indent                     : {'OFF' if args.no_indent else 'on'}")
    print(f"  xml declaration            : {args.xml_declaration}")
    print(f"  force write                : {'on' if args.force_write else 'off'}")

    print(f"\nGLOBAL DUPLICATE <gameid> VALUES BEFORE CLEANUP: {len(duplicates)}")
    if duplicates:
        for _, occurrences in duplicates:
            value = occurrences[0]["value"]
            print(f"  Duplicate <gameid> {value!r}:")
            for occurrence in occurrences:
                print(f"    - {occurrence['label']}")
    else:
        print("  None found among readable selected systems.")

    total_deduplicated = sum(
        len(result["deduplicated"]) for result in results.values()
    )
    print(f"\nDUPLICATE ENTRIES REMOVED OR PLANNED: {total_deduplicated}")

    for system_name in sorted(results, key=str.casefold):
        result = results[system_name]
        print(f"\n{system_name} [{result['status']}]")
        print(
            f"  Added: {len(result['added'])} | "
            f"Removed (missing ROM): {len(result['removed'])} | "
            f"Deduplicated: {len(result['deduplicated'])} | "
            f"Titles normalized: {len(result['normalized'])} | "
            f"<gameid> added: {len(result['ids_added'])} | "
            f"Orphan images: {len(result['orphans'])} | "
            f"Deleted images: {len(result['deleted'])}"
        )
        print(
            "  Alphabetical sorting needed: "
            f"{'Yes' if result['sorted'] else 'No'}"
        )

        if result["backup"]:
            print(f"  Backup: {result['backup'].name}")

        report_lists = (
            ("Added games", "added", "+"),
            ("Removed entries (missing ROM)", "removed", "-"),
            ("Entries given <gameid>", "ids_added", "ID"),
            ("Normalized language titles", "normalized", "~"),
            ("<id>/<gameid> conflicts", "id_conflicts", "!"),
        )

        for label, key, prefix in report_lists:
            if result[key]:
                print(f"  {label}:")
                for item in result[key]:
                    print(f"    {prefix} {item}")

        if result["deduplicated"]:
            print("  Duplicate entries removed or planned:")
            for item in result["deduplicated"]:
                print(
                    f"    - path={item['path']!r}, "
                    f"gameid={item['gameid']!r}, "
                    f"name={item['name']!r}"
                )
                print(f"      Reason: {item['reason']}")

        if result["orphans"]:
            print("  Orphan images:")
            for path in result["orphans"]:
                print(f"    ? {path.name}")

        if result["deleted"]:
            print("  Deleted images:")
            for name in result["deleted"]:
                print(f"    x {name}")

        for note in result["notes"]:
            print(f"  Note: {note}")

    errors = (
        sum(r["status"] == "ERROR" for r in results.values())
        + int(locals().get("catalog_sync_error", False))
    )
    skipped = sum(r["status"] == "SKIPPED" for r in results.values())

    print(
        f"\nFinished: {len(results)} systems, "
        f"{errors} errors, {skipped} skipped."
    )

    if args.system:
        print(
            "Note: --system limits duplicate checking and ID allocation "
            "to the selected system."
        )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())