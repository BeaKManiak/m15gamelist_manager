# ADR 0001: One primary update action for the GUI

- Status: accepted
- Date: 2026-10-27

## Context

The GUI presented every capability with equal weight: eight action buttons, three
dropdowns, eight switches, and an always-visible technical log. The everyday
task — “I added a game to the SD card; update the data on the device” — was the
least obvious thing on screen, and the README asked users to run a preview and
then click a second button to apply it.

The backend already separates a non-writing dry run from the writing run, and the
catalog preflight guarantees that a failed check changes nothing.

## Decision

- The main window has one primary action, **Update library**. It runs the dry
  run, turns the result into plain-language counts, and asks for confirmation in
  a dedicated dialog. Only then does it run the apply pass.
- If neither the gamelists nor the device catalog would change, the app reports
  “already up to date” and skips both the confirmation and the write. `Force
  write` remains the explicit way to rewrite unchanged files.
- Individual switches, the system filter, the XML style, and backup retention
  live in a collapsed **Advanced options** section. Settings and the last folder
  are remembered between launches.
- Restore and backup pruning live in a separate **Backups & restore** window
  under the **Tools** menu. They are rare recovery actions, not part of the
  everyday flow.
- The technical log stays behind **Show details** and opens automatically only
  when something fails.
- Folder selection is a compact status line. On launch the app reuses the saved
  folder; otherwise it searches mounted volumes (macOS `/Volumes`, Windows
  logical drives, Linux media paths) and asks when several match.
- The GUI's tkinter-free logic lives in `gui_support.py` so settings, detection,
  and summary behavior are testable without a display.

## Consequences

- An update scans the collection twice (check, then apply). This is accepted in
  exchange for keeping the backend's proven preview-then-write safety model and
  avoiding a plan/commit refactor.
- Advanced settings persist, so a forgotten single-system filter could silently
  narrow an update. The collapsed **Advanced options** label shows the active
  system filter to make that visible.
- The confirmation summary must stay accurate: orphan-image deletion is not an
  XML change, so it is counted and shown explicitly instead of being treated as
  “nothing to do”.
- Advanced settings and the log are full-width accordion rows rather than links,
  so the disclosure affordance is obvious. The window has a fixed default
  geometry: resizing it when the log opened or closed was visibly laggy under Tk
  on macOS.
- Custom fonts are configured with persistent font specs, not `tkfont.Font`
  objects. Tk stores only the font name, so a garbage-collected `Font` silently
  reverts widgets and styles to the default font.
- CLI behavior and output are unchanged; the GUI continues to call the manager,
  restore, and prune APIs directly.
