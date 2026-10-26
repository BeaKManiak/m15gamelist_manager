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
from dataclasses import dataclass
from pathlib import Path
from catalog_sync import catalog_issues, sync_catalog
from m15core import (
    find_system_folder as _find_system_folder,
    get_child,
    get_text,
    local_tag,
    set_child_text,
)
from systems import SYSTEMS

LANGUAGES = ("zh_CN", "en_US", "zh_TW", "ko_KR")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


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


@dataclass
class Options:
    root: Path
    system: str | None = None
    dry_run: bool = False
    delete_orphaned_images: bool = False
    no_prompt: bool = False
    root_dat: Path | None = None
    fileinfo: Path | None = None
    skip_remove_missing: bool = False
    skip_add: bool = False
    skip_ids: bool = False
    skip_normalize: bool = False
    skip_sort: bool = False
    dedup: str = "both"
    indent: bool = True
    xml_declaration: str = "et"
    force_write: bool = False


@dataclass
class RunResult:
    root_folder: Path
    options: Options
    systems: dict
    duplicates: list
    catalog_skipped: bool = False
    catalog_sync_error: bool = False
    catalog_summary: dict | None = None
    preflight_issues: list | None = None

    @property
    def errors(self) -> int:
        return (
            sum(
                result["status"] == "ERROR"
                for result in self.systems.values()
            )
            + int(self.catalog_sync_error)
            + int(bool(self.preflight_issues))
        )

    @property
    def skipped(self) -> int:
        return sum(
            result["status"] == "SKIPPED"
            for result in self.systems.values()
        )

    @property
    def exit_code(self) -> int:
        return 1 if self.errors else 0


def build_parser():
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
    return parser


def options_from_args(args) -> Options:
    if args.roundtrip:
        args.skip_remove_missing = True
        args.skip_add = True
        args.skip_ids = True
        args.skip_normalize = True
        args.skip_sort = True
        args.dedup = "none"
        args.force_write = True
        args.no_prompt = True

    return Options(
        root=args.root.expanduser().resolve(),
        system=args.system,
        dry_run=args.dry_run,
        delete_orphaned_images=args.delete_orphaned_images,
        no_prompt=args.no_prompt,
        root_dat=args.root_dat,
        fileinfo=args.fileinfo,
        skip_remove_missing=args.skip_remove_missing,
        skip_add=args.skip_add,
        skip_ids=args.skip_ids,
        skip_normalize=args.skip_normalize,
        skip_sort=args.skip_sort,
        dedup=args.dedup,
        indent=not args.no_indent,
        xml_declaration=args.xml_declaration,
        force_write=args.force_write,
    )


def new_system_result(system_name, record):
    return {
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


def collect_existing_ids(records):
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
    return existing_gameids, max_numeric_id, duplicates


class IdAllocator:
    def __init__(self, existing_gameids, max_numeric_id):
        self.used_ids = set(existing_gameids)
        self.next_id = max_numeric_id + 1

    def reuse(self, key):
        if key is not None:
            self.used_ids.add(key)

    def allocate(self):
        while id_key(str(self.next_id)) in self.used_ids:
            self.next_id += 1
        value = str(self.next_id)
        self.used_ids.add(id_key(value))
        self.next_id += 1
        return value


def transform_system(system_name, record, options, allocator):
    """Apply all in-memory changes for one system without writing files."""
    result = new_system_result(system_name, record)

    if record.get("status") != "OK":
        return result, None

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
        return result, None

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
            if not options.skip_remove_missing:
                result["removed"].append(raw_path)
                xml_changed = True
                continue
            result["notes"].append(
                f"Kept entry with missing ROM: {raw_path}"
            )

        retained.append(entry)
        if rom_exists:
            known_files.add(resolved.name.casefold())

        if not options.skip_ids:
            existing_gameid = get_text(entry, "gameid")
            existing_id = get_text(entry, "id")

            if not existing_gameid:
                old_id_key = id_key(existing_id)

                if (
                    existing_id
                    and old_id_key is not None
                    and old_id_key not in allocator.used_ids
                ):
                    new_gameid = existing_id
                    allocator.reuse(old_id_key)
                else:
                    new_gameid = allocator.allocate()
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

        if not options.skip_normalize:
            changed_languages = normalize_language_fields(entry)
            if changed_languages:
                result["normalized"].append(
                    f"{raw_path} ({', '.join(changed_languages)})"
                )
                xml_changed = True

    replace_game_children(root, retained)

    if not options.skip_add:
        for _, game_file in discovered.items():
            if game_file.name.casefold() in known_files:
                continue

            new_gameid = allocator.allocate()
            root.append(make_entry(game_file.name, new_gameid, profile))
            result["added"].append(game_file.name)
            known_files.add(game_file.name.casefold())
            xml_changed = True

    dedup_removals = deduplicate_games(root, system_name, options.dedup)
    if dedup_removals:
        result["deduplicated"].extend(dedup_removals)
        xml_changed = True

    orphans, orphan_note = find_orphan_images(folder, root)
    result["orphans"] = orphans
    if orphan_note:
        result["notes"].append(orphan_note)

    if not options.skip_sort:
        if sort_games_alphabetically(root):
            result["sorted"] = True
            result["notes"].append(
                "Game entries sorted alphabetically by <name>."
            )
            xml_changed = True

    if options.dry_run:
        result["notes"].append("Dry-run: no files changed.")

    context = {
        "folder": folder,
        "xml_path": xml_path,
        "tree": tree,
        "root": root,
        "xml_changed": xml_changed,
    }
    return result, context


def commit_system(result, context, options, *, output=print, ask=input):
    """Write one transformed system and delete its orphans if requested."""
    if context is None or options.dry_run:
        return

    if context["xml_changed"] or options.force_write:
        try:
            result["backup"] = safe_write_xml(
                context["tree"], context["xml_path"],
                indent=options.indent,
                declaration=options.xml_declaration,
            )
        except Exception as exc:
            result["status"] = "ERROR"
            result["notes"].append(f"XML replacement failed: {exc}")
            return

    delete_orphans_if_requested(
        result["system"], result, options, output=output, ask=ask
    )


def process_system(
    system_name,
    record,
    options,
    allocator,
    *,
    output=print,
    ask=input,
):
    """Transform and commit one system (kept for direct unit tests)."""
    result, context = transform_system(system_name, record, options, allocator)
    commit_system(result, context, options, output=output, ask=ask)
    return result


def find_orphan_images(folder, root):
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
    if not image_folder.is_dir():
        return [], None

    try:
        orphans = sorted(
            [
                path for path in image_folder.iterdir()
                if path.is_file()
                and path.suffix.lower() in IMAGE_EXTENSIONS
                and path.name.casefold() not in referenced_images
            ],
            key=lambda path: path.name.casefold(),
        )
        return orphans, None
    except OSError as exc:
        return [], f"Could not scan images: {exc}"


def delete_orphans_if_requested(
    system_name,
    result,
    options,
    *,
    output=print,
    ask=input,
):
    orphans = result["orphans"]

    if not orphans:
        return

    if options.delete_orphaned_images:
        should_delete = True
    elif options.no_prompt:
        should_delete = False
    else:
        output(f"\n{system_name}: orphaned images")
        for path in orphans:
            output(f"  {path.name}")
        try:
            answer = ask(
                "Delete these images? [y/N]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        should_delete = answer in {"y", "yes"}

    if should_delete:
        for path in orphans:
            try:
                path.unlink()
                result["deleted"].append(path.name)
            except OSError as exc:
                result["notes"].append(
                    f"Could not delete {path.name}: {exc}"
                )


def run_catalog_sync(options, root_folder, *, output=print):
    if options.dry_run:
        output(
            "\nGlobal catalog synchronization skipped: "
            "dry-run does not write catalog files."
        )
        return True, False, None

    catalog_root = options.root_dat or (root_folder / "root.dat")
    catalog_counts = (
        options.fileinfo
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
        output("\nGLOBAL CATALOG SYNCHRONIZATION")
        output(f"  Games indexed: {summary['games']}")
        output(f"  root.dat backup: {summary['root_dat_backup']}")
        output(f"  fileinfo backup: {summary['fileinfo_backup']}")
        output("  Catalog validation: passed")
        return False, False, summary
    except Exception as exc:
        output(f"\nGLOBAL CATALOG SYNCHRONIZATION FAILED: {exc}")
        output(
            "  The catalog files were not intentionally left partially "
            "updated; check the backups and XML/catalog consistency."
        )
        return False, True, None


def collect_preflight_issues(records, transformed):
    """Validate the post-transformation trees before any file is written."""
    issues = []
    roots = {}

    for system_name in sorted(SYSTEMS, key=str.casefold):
        record = records.get(system_name)
        if record is None or record.get("status") != "OK":
            detail = "; ".join(record.get("notes", [])) if record else ""
            issues.append(
                f"{system_name}: {detail or 'system folder/XML not readable'}"
            )
            continue
        context = transformed.get(system_name)
        roots[system_name] = (
            context["root"] if context else record["root"]
        )

    issues.extend(catalog_issues(roots, list(roots)))
    return issues


def run(options: Options, *, output=print, ask=input) -> RunResult:
    root_folder = options.root
    if options.system is None:
        records = read_system_xmls(root_folder, list(SYSTEMS))
        pool_records = records
    else:
        # Build the ID pool and duplicate report globally, but only transform
        # the selected system. Catalog sync still rebuilds every system.
        pool_records = read_system_xmls(root_folder, list(SYSTEMS))
        records = {options.system: pool_records[options.system]}

    existing_gameids, max_numeric_id, duplicates = collect_existing_ids(pool_records)
    allocator = IdAllocator(existing_gameids, max_numeric_id)

    results = {}
    transformed = {}
    for system_name in sorted(records, key=str.casefold):
        result, context = transform_system(
            system_name,
            records[system_name],
            options,
            allocator,
        )
        results[system_name] = result
        if context is not None:
            transformed[system_name] = context

    preflight_issues = collect_preflight_issues(pool_records, transformed)
    if preflight_issues:
        output("\nCATALOG PREFLIGHT FAILED (no files were changed):")
        for issue in preflight_issues:
            output(f"  - {issue}")
        return RunResult(
            root_folder=root_folder,
            options=options,
            systems=results,
            duplicates=duplicates,
            catalog_skipped=True,
            preflight_issues=preflight_issues,
        )

    for system_name in sorted(results, key=str.casefold):
        commit_system(
            results[system_name],
            transformed.get(system_name),
            options,
            output=output,
            ask=ask,
        )

    catalog_skipped, catalog_sync_error, catalog_summary = run_catalog_sync(
        options, root_folder, output=output
    )

    return RunResult(
        root_folder=root_folder,
        options=options,
        systems=results,
        duplicates=duplicates,
        catalog_skipped=catalog_skipped,
        catalog_sync_error=catalog_sync_error,
        catalog_summary=catalog_summary,
    )


def print_report(result: RunResult, *, output=print) -> None:
    options = result.options
    root_folder = result.root_folder
    results = result.systems

    output("\n" + "=" * 84)
    output("FINAL REPORT")
    output("=" * 84)
    output(f"Root: {root_folder}")
    output(
        "Mode: DRY RUN (no writes or deletions)"
        if options.dry_run else "Mode: APPLY"
    )
    output("Features:")
    output(f"  remove missing ROM entries : {'OFF' if options.skip_remove_missing else 'on'}")
    output(f"  add new ROMs               : {'OFF' if options.skip_add else 'on'}")
    output(f"  add missing <gameid>       : {'OFF' if options.skip_ids else 'on'}")
    output(f"  normalize titles           : {'OFF' if options.skip_normalize else 'on'}")
    output(f"  alphabetical sort          : {'OFF' if options.skip_sort else 'on'}")
    output(f"  dedup                      : {options.dedup}")
    output(f"  indent                     : {'OFF' if not options.indent else 'on'}")
    output(f"  xml declaration            : {options.xml_declaration}")
    output(f"  force write                : {'on' if options.force_write else 'off'}")

    output(f"\nGLOBAL DUPLICATE <gameid> VALUES BEFORE CLEANUP: {len(result.duplicates)}")
    if result.duplicates:
        for _, occurrences in result.duplicates:
            value = occurrences[0]["value"]
            output(f"  Duplicate <gameid> {value!r}:")
            for occurrence in occurrences:
                output(f"    - {occurrence['label']}")
    else:
        output("  None found among readable selected systems.")

    total_deduplicated = sum(
        len(item["deduplicated"]) for item in results.values()
    )
    output(f"\nDUPLICATE ENTRIES REMOVED OR PLANNED: {total_deduplicated}")

    for system_name in sorted(results, key=str.casefold):
        item = results[system_name]
        output(f"\n{system_name} [{item['status']}]")
        output(
            f"  Added: {len(item['added'])} | "
            f"Removed (missing ROM): {len(item['removed'])} | "
            f"Deduplicated: {len(item['deduplicated'])} | "
            f"Titles normalized: {len(item['normalized'])} | "
            f"<gameid> added: {len(item['ids_added'])} | "
            f"Orphan images: {len(item['orphans'])} | "
            f"Deleted images: {len(item['deleted'])}"
        )
        output(
            "  Alphabetical sorting needed: "
            f"{'Yes' if item['sorted'] else 'No'}"
        )

        if item["backup"]:
            output(f"  Backup: {item['backup'].name}")

        report_lists = (
            ("Added games", "added", "+"),
            ("Removed entries (missing ROM)", "removed", "-"),
            ("Entries given <gameid>", "ids_added", "ID"),
            ("Normalized language titles", "normalized", "~"),
            ("<id>/<gameid> conflicts", "id_conflicts", "!"),
        )

        for label, key, prefix in report_lists:
            if item[key]:
                output(f"  {label}:")
                for value in item[key]:
                    output(f"    {prefix} {value}")

        if item["deduplicated"]:
            output("  Duplicate entries removed or planned:")
            for value in item["deduplicated"]:
                output(
                    f"    - path={value['path']!r}, "
                    f"gameid={value['gameid']!r}, "
                    f"name={value['name']!r}"
                )
                output(f"      Reason: {value['reason']}")

        if item["orphans"]:
            output("  Orphan images:")
            for path in item["orphans"]:
                output(f"    ? {path.name}")

        if item["deleted"]:
            output("  Deleted images:")
            for name in item["deleted"]:
                output(f"    x {name}")

        for note in item["notes"]:
            output(f"  Note: {note}")

    output(
        f"\nFinished: {len(results)} systems, "
        f"{result.errors} errors, {result.skipped} skipped."
    )

    if options.system:
        output(
            "Note: --system limits duplicate checking and ID allocation "
            "to the selected system."
        )


def main():
    parser = build_parser()
    args = parser.parse_args()
    options = options_from_args(args)
    if not options.root.is_dir():
        parser.error(f"Root folder does not exist: {options.root}")

    result = run(options)
    print_report(result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
