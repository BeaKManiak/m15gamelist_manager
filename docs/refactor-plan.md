# Handoff plan (historical)

> This is the original refactor plan, kept for project history. For current
> behavior and usage, start with the [main README](../README.md) and
> [documentation index](README.md).

Repo: BeaKManiak/m15gamelist_manager (branch from `main`). Stdlib-only Python 3.8+; tkinter GUI (`m15_gui.py`) calls `gamelist_manager.main()` in a thread. Files: `gamelist_manager.py` (1061 lines), `m15_gui.py` (615), `catalog_sync.py` (263), `restore_gamelist.py` (261), `delete_gamelist_backups.py` (126), `.github/workflows/build-app.yml`.

Hard constraints: keep stdlib-only; keep CLI command names/flags working (or document removals); gamelist.xml / root.dat / fileinfo output must stay byte-identical for the same inputs; do tests first; one small commit per todo; do not bundle unrelated changes.

Key code pointers: `safe_write_xml` (gamelist_manager.py ~L316), `read_system_xmls` (~L385), `main()` (L590–end, nested `allocate_id`), GUI `build_manager_args`/`_worker` (m15_gui.py ~L424, ~L524), `catalog_sync._read_xml_catalog`/`sync_catalog`, `SYSTEMS` dict (gamelist_manager.py L39–~L135).

# Optimization plan – M15 ROM Collection Manager

## Findings
~2.3k lines of stdlib Python, 5 flat scripts, no tests, no package layout.

1. **Duplicated helpers** – XML tag/text/child helpers, system-folder lookup, `_unprefix`/`strip_numeric_prefix`, XML parsing and validation are re-implemented in `gamelist_manager.py` and `catalog_sync.py` (and `valid_xml` in `restore_gamelist.py`). Each does its own `ET.parse` of every gamelist (parsed twice per run).
2. **`gamelist_manager.main()` is a ~470-line monolith** – arg parsing, ID allocation, per-system processing, orphan image handling, writing, catalog sync, reporting all in one function with nested closures. Hard to test or reuse.
3. **GUI drives CLI via hacks** – `m15_gui.py` builds argv strings, patches `sys.argv`, `sys.stdout`, `os.chdir`, and catches `SystemExit`. Not thread-safe, brittle. Should call a function with a typed options object.
4. **Switch explosion** – many bisect flags (`--skip-*`, `--roundtrip`, `--xml-declaration`, `--no-indent`, `--force-write`). Group into an `Options` dataclass / presets; keep only flags that are still useful, hide the rest behind an "advanced" section.
5. **`SYSTEMS` config (≈100 lines) hard-coded in code** – move to a data file (JSON) or a separate `systems.py`, so adding a system doesn't touch logic.
6. **Spinner / progress output** – threads and `\r` animation break in GUI log capture; replace with simple progress callback/logging.
7. **Error handling** – broad `except Exception` (8 places), prints instead of `logging`, inconsistent exit codes.
8. **Backup growth** – every write creates a `.bak`; no retention policy besides separate `delete_gamelist_backups.py`. Add optional "keep last N" in the writer. Also `safe_write_xml` reads/writes temp file 2–3 times (BOM/declaration); build bytes in memory instead.
9. **Performance** – ROM scan, path resolution and orphan-image checks use repeated per-entry filesystem calls and list lookups; use one `scandir` per folder + sets/dicts.
10. **No tests / CI check** – only a build workflow. Add pytest tests (fixtures with tiny gamelists) covering dedupe, ID allocation, normalization, safe write/rollback, catalog sync, restore. Add lint (ruff) step.
11. **Packaging/docs** – scripts must sit side-by-side; README says so. Convert to a package (`m15/` with `core`, `catalog`, `backups`, `cli`, `gui`), thin entry-point wrappers keep existing command names. Update workflow to build from the new entry point.

## Todos
1. `add-tests` – Characterization tests for current behavior (before refactoring). 
2. `extract-core` – Shared module: XML helpers, folder lookup, parsing (parse once, share with catalog sync), systems config to data file.
3. `split-main` – Break `main()` into functions + `Options` dataclass; return a result object.
4. `gui-direct-call` – GUI calls the API directly; drop argv/stdout/chdir patching; progress via callback/logging. (depends: split-main)
5. `simplify-flags` – Consolidate switches/presets; update CLI help, GUI, README. (depends: split-main)
6. `writer-and-perf` – In-memory XML write, backup retention, scandir/set-based lookups. (depends: extract-core)
7. `error-handling` – Narrow exceptions, logging, consistent exit codes. (depends: split-main)
8. `package-and-ci` – Package layout, wrapper entry points, ruff + pytest in CI, adjust build workflow, README. (depends: all above)

9. `readme-rework` – Final todo (depends: package-and-ci): rewrite README.md to match the final state: new package layout/entry points, simplified flags/presets, GUI usage, backup retention option, running tests/lint, build/release workflow. Remove outdated notes (e.g. "keep catalog_sync.py next to gamelist_manager.py"). Each earlier todo must also update README sections it touches; this todo is the final consistency pass.

## Notes
- Output format of gamelist.xml / root.dat / fileinfo must stay byte-identical (the M15 is fussy); characterization tests should lock this first.
- Do tests first, then refactor in small steps.
