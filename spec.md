# Task Description: Implement `taskwm` (Task-Centric Workspaces for bspwm)

## Overview

Build an application called **`taskwm`** that adds a task-based workflow on top of **bspwm**:

* **Desktop “tasks”** (bound to **Super+1**) is a *task picker / todo list* UI. It should contain **only one window** (the picker).
* **Desktop “active”** (bound to **Super+2**) is the *current task workspace*: it shows the task’s windows and a **thin top bar** with the task title and actions.
* All other workspaces (Super+0, Super+3..9) should behave as usual (legacy behavior).

The app should:

* manage tasks (create, select, close/done),
* map each task to its own hidden desktop (`t:<id>`),
* “activate” a task by moving its windows into the `active` desktop,
* let the user switch tasks from the bar without visiting the task list.

Target environment: **Arch Linux**, **X11**, **bspwm**, **sxhkd**, minimal desktop environment.

Constraints:

* No Rust.
* Prefer **Python** and simple system tools.
* Dark mode, “text-mode-like” feel: monospace font, minimal colors, simple widgets.
* If CLI exists, commands must be **short**.

---

## Non-Goals

* No Wayland support in v1.
* No deep integration with external task systems (Taskwarrior, CalDAV) in v1. (Design so it can be added later.)
* No complex EWMH struts/window-reservation unless easy; padding toggling is acceptable.

---

## Deliverables

1. `taskwm` executable(s) installed into `~/.local/bin/`:

   * `tw` (short CLI)
   * background daemon `taskwm-daemon` (may be `tw daemon`)
   * UI modes (picker + bar) started by daemon
2. State storage (JSON) under `~/.local/state/taskwm/state.json`
3. Config file support under `~/.config/taskwm/config.json`
4. README with:

   * dependencies
   * install steps
   * sample `bspwmrc` and `sxhkdrc` snippets
   * usage examples
   * troubleshooting commands

---

## High-Level Behavior

### Desktops / Workspaces

* Two special desktops exist on a configured monitor:

  * **`tasks`**: task list UI (Super+1)
  * **`active`**: current task workspace + top bar (Super+2)
* Each task has its own dedicated desktop:

  * **`t:<id>`** (example: `t:12`, `t:13`, …)
* Legacy desktops remain numeric:

  * `0`, `3`, `4`, `5`, `6`, `7`, `8`, `9`

### Selecting a task

When a task is selected (from picker or bar menu):

1. If there is a previously selected task:

   * Move all windows currently in `active` back to the previous task desktop (`t:<oldid>`).
2. Move all windows from the selected task desktop (`t:<newid>`) into `active`.
3. Set `current_task_id` to the selected task.
4. Update the bar title text.

### Completing/closing a task

When the user closes/completes the current task:

1. Show a confirmation dialog if windows exist in `active`:

   * “This will close X windows. Are you sure?”
2. Close all windows in `active`.
3. Mark task as done (and/or delete it depending on config).
4. Remove task desktop (`t:<id>`) if it’s empty.
5. Clear `current_task_id` and update bar.

### Picker desktop enforcement

* The `tasks` desktop should contain **only the picker window**.
* If any other window appears on `tasks`, immediately move it to `active` (or last focused legacy desktop; choose one and document it).

---

## UX Requirements

### Task Picker window (Desktop `tasks`)

Dark theme, monospace, minimal UI.

Layout:

* Top row: `[ input field........ ] [ + ]`

  * Enter adds a new task with that title (same as +).
* Below: scrollable list of tasks.

  * Each row shows:

    * task title (truncate with ellipsis)
    * small buttons: `[Select]` `[Close]`
  * `Select`: select task and focus `active` desktop.
  * `Close`: triggers confirmation: “will close windows if active; remove task desktop; continue?”
* Keyboard support:

  * Up/Down to navigate list
  * Enter = Select highlighted
  * Delete (or Ctrl+D) = Close highlighted (with confirm)
  * Ctrl+N focuses input
  * Esc hides picker (optional) or clears focus

### Active Task Bar (Desktop `active`)

Thin bar at top (e.g. 24px), always on top, dark theme.

Content:

* **Centered**: current task title (or “No active task”)
* Right side: a menu button (e.g. “≡”)

  * Clicking opens a menu listing tasks.
  * Selecting a task switches current task **without switching to the `tasks` desktop** (stay in `active`).
* Optional: a `[Done]` button either left or right (configurable).

Behavior:

* Bar should ideally only be visible while `active` is focused; otherwise it can hide (withdraw) or show minimal.
* Prevent covering windows:

  * v1 acceptable approach: daemon toggles `bspc config top_padding` when desktop focus enters/leaves `active` (store and restore old value).

---

## Tech Stack Requirements (v1)

**Preferred implementation: Python 3 + Tkinter** (simple, common, hackable).

* Dependencies:

  * `python` (3.x)
  * `tk` (for Tkinter on Arch)
  * `bspwm` / `bspc`
  * `xprop` (for WM_CLASS checks) if needed
* No additional big frameworks required.

Design for hackability:

* Keep WM interaction in a small module (`bspwm.py`) that shells out to `bspc`.
* Keep state management in `state.py`.
* Keep UI as separate modules.

---

## CLI Spec (short commands)

Provide a single entrypoint: **`tw`**.

Commands (short, stable):

* `tw a "title"` — add a task, return id
* `tw l` — list tasks (id + title; machine readable preferred)
* `tw s <id>` — select task (swap windows into `active`)
* `tw d` — mark current task done/close (with confirmation only in UI; CLI can force close with `-f`)
* `tw r <id>` — remove task (and optionally close windows if active; require `-f` if windows exist)
* `tw cur` — print current task id (or empty)
* `tw title` — print current task title (for bar)
* `tw daemon` — run background manager (starts/monitors UI + bspwm events)

Optional convenience:

* `tw ui` — start picker + bar without daemon (dev)

Exit codes:

* 0 success
* nonzero on failure (invalid id, bspc missing, etc.)

Output formatting:

* `tw l` should output lines like: `12\tFix ceph scrub` (tab-separated).
* `tw a` prints id only to stdout.

---

## State Storage

Single JSON file:

* `~/.local/state/taskwm/state.json`

Schema (example):

```json
{
  "version": 1,
  "current_task_id": 12,
  "last_task_id": 11,
  "tasks": [
    {"id": 12, "title": "Work on pricing model", "created": 1736540000, "done": false},
    {"id": 13, "title": "Fix Ruckus roam", "created": 1736541000, "done": false}
  ],
  "settings_cache": {
    "monitor": "DP-2",
    "bar_height": 24,
    "active_padding_prev": 0
  }
}
```

Rules:

* IDs are monotonically increasing integers.
* Titles are plain strings; sanitize newlines.
* Tasks can be soft-done or deleted depending on config.

---

## Config File

`~/.config/taskwm/config.json`

Must support:

* `monitor`: which monitor hosts `tasks` and `active` desktops (string; default: focused monitor at daemon start)
* `bar_height`: int (default 24)
* theme:

  * `font`: e.g. `"monospace 10"`
  * `bg`: `#111111`
  * `fg`: `#e6e6e6`
  * `accent`: `#66aaff` (optional)
* behavior:

  * `close_policy`: `"archive"` or `"delete"`
  * `move_stray_on_tasks_to`: `"active"` or `"last"` (v1 default `"active"`)
  * `hide_bar_when_not_active`: bool

Provide defaults if config missing.

---

## bspwm Integration Details

### Desktop naming

On daemon start:

* Ensure desktops exist on target monitor:

  * `tasks`, `active`, `0`, `3..9`
* If numeric desktops already exist, do not reorder destructively; but ensure `tasks` and `active` exist and are reachable.

### Window identification

The UI windows must set distinct WM_CLASS so bspwm rules can target them.

* Picker WM_CLASS: `taskwm` / `picker`
* Bar WM_CLASS: `taskwm` / `bar`

In Tkinter, you can set window class via:

* `root.wm_class("taskwm", "picker")` (verify exact call works; otherwise use `tk` options or `xprop` testing and document).

After UI window created, it must:

* obtain X11 window id (`root.winfo_id()`)
* move itself to appropriate desktop:

  * picker → `tasks`
  * bar → `active`
* optionally set floating, sticky, borderless, topmost.

### Event loop / daemon

Daemon should subscribe to bspwm events:

* `bspc subscribe desktop_focus node_add node_remove node_transfer`
  (Choose minimal set necessary.)

Daemon responsibilities:

1. Enforce: only picker window on `tasks`.
2. Track focus changes to toggle `top_padding` when entering/leaving `active`.
3. Keep state consistent if windows are moved manually.
4. Notify UI to refresh (simplest: UI polls state file every 200–500ms; acceptable).

---

## Implementation Plan (Modules)

Suggested repo layout:

```
taskwm/
  README.md
  pyproject.toml (or setup.cfg) / or plain scripts
  taskwm/
    __init__.py
    cli.py
    state.py
    bspwm.py
    daemon.py
    ui_picker.py
    ui_bar.py
    util.py
bin/
  tw  (small wrapper to python -m taskwm.cli)
```

### `bspwm.py`

* `run_bspc(args: list[str]) -> str`
* `desktop_exists(name) -> bool`
* `ensure_desktops(monitor, names: list[str])`
* `list_windows(desktop_name) -> list[winid]`
* `move_window(winid, desktop_name)`
* `close_window(winid)`
* `focused_desktop() -> str`
* `monitor_of_desktop(desktop_name) -> str`

Everything uses `subprocess.run` and robust quoting.

### `state.py`

* load/save JSON with atomic writes (write temp + rename)
* CRUD tasks:

  * add, list, remove, mark done
  * set current task
* helper: get title by id

### `daemon.py`

* determine target monitor
* ensure desktops exist
* start UI windows (picker + bar) if not running
* subscribe to bspwm events, enforce rules, toggle padding
* optionally keep a PID file or lock to prevent duplicates

### `ui_picker.py` (Tkinter)

* dark theme, monospace
* input entry + add button
* scrollable list with per-row select/close
* confirmation dialogs (Tk messagebox OK/Cancel)
* actions call `tw` internal functions or import state+bspwm directly (prefer direct import; avoid forking unless needed)

### `ui_bar.py` (Tkinter)

* thin borderless top window, topmost
* centered label reading current task title
* menu button opens a popup menu listing tasks; selecting triggers select logic
* optional Done button
* update loop refreshes title when state changes

---

## Acceptance Criteria

A build is “done” when:

1. User can run `tw daemon` from `bspwmrc` and get:

   * picker on `tasks` desktop,
   * bar on `active` desktop.
2. `Super+1` focuses `tasks`, `Super+2` focuses `active`, and legacy desktops remain normal.
3. From picker:

   * add tasks,
   * select task (moves its windows into `active`),
   * close task (prompts if needed, closes windows, removes/archives task).
4. From bar:

   * shows current task title centered,
   * menu lists tasks and switches tasks without leaving `active`,
   * Done closes current task windows and clears current task.
5. Selecting tasks swaps windows correctly:

   * active windows return to previous task desktop,
   * chosen task windows move into active.
6. `tasks` desktop remains single-window (picker). Any other window moved away automatically.
7. State persists across restarts (tasks remain, current task restored, desktops re-created if missing).
8. All commands handle errors cleanly (missing `bspc`, invalid task id) with clear stderr messages.

---

## Integration Snippets (to include in README)

### `sxhkdrc`

```sh
super + 1
  bspc desktop -f '^tasks'

super + 2
  bspc desktop -f '^active'

super + {0,3,4,5,6,7,8,9}
  bspc desktop -f '^{0,3,4,5,6,7,8,9}'

# optional:
super + shift + 2
  tw d
```

### `bspwmrc`

```sh
# start taskwm
tw daemon &
```

---

## Notes / Implementation Tips

* Prefer named desktops (`tasks`, `active`, `t:<id>`) over numeric indices.
* Use atomic state writes to avoid corruption.
* Keep UI logic thin; core logic should be callable both from UI and CLI.
* Don’t over-engineer: polling state file is fine in v1.
* Ensure the app remains “hackable”: readable code, few deps, clear boundaries, simple config.

---

If you want, I can also provide:

* a concrete default color palette + Tkinter styling recipe that looks “terminal-like,” and
* a reference implementation of `select_task()` / “swap windows” that handles edge cases (empty tasks, missing desktops, manual window moves).

