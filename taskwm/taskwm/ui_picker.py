#!/usr/bin/env python3
"""Task picker UI for taskwm - pywebview-based HTML/JS interface."""

import sys
import os
from pathlib import Path

from . import state, bspwm, config

TASKS_DESKTOP = "tasks"
ACTIVE_DESKTOP = "active"
TOKEN_FILE = Path.home() / ".local" / "state" / "taskwm" / "token"


class PickerAPI:
    """API exposed to the webview JavaScript."""

    def __init__(self, token: str):
        self._token = token
        self._cfg = config.get_config()
        self._st = state.get_state()

    def _verify_token(self, token: str) -> bool:
        """Verify the provided token matches."""
        return token == self._token

    def get_tasks(self) -> list:
        """Get list of non-done tasks."""
        self._st.reload()
        return self._st.list_tasks(include_done=False)

    def get_current_task_id(self) -> int | None:
        """Get the current task ID."""
        self._st.reload()
        return self._st.get_current_task_id()

    def get_config(self) -> dict:
        """Get configuration for theming."""
        return {
            'theme': self._cfg.theme,
            'monitor': self._cfg.monitor
        }

    def add_task(self, title: str) -> int | None:
        """Add a new task, return its ID."""
        title = title.strip()
        if not title:
            return None
        try:
            task = self._st.add_task(title)
            return task['id']
        except ValueError:
            return None

    def select_task(self, task_id: int) -> bool:
        """Select a task and switch to active desktop."""
        monitor = self._st.get_setting('monitor')
        if not monitor:
            try:
                monitor = bspwm.get_focused_monitor()
                self._st.set_setting('monitor', monitor)
            except bspwm.BspwmError:
                return False

        old_task_id = self._st.get_current_task_id()

        try:
            bspwm.swap_task_windows(monitor, old_task_id, task_id)
            self._st.set_current_task_id(task_id)
            bspwm.focus_desktop(ACTIVE_DESKTOP)
            return True
        except bspwm.BspwmError:
            return False

    def close_task(self, task_id: int) -> bool:
        """Close a task, closing its windows."""
        task = self._st.get_task(task_id)
        if not task:
            return False

        current_id = self._st.get_current_task_id()

        try:
            # Close windows
            if task_id == current_id:
                bspwm.close_all_windows(ACTIVE_DESKTOP)
            else:
                desktop = bspwm.task_desktop_name(task_id)
                if bspwm.desktop_exists(desktop):
                    bspwm.close_all_windows(desktop)

            # Handle based on policy
            if self._cfg.close_policy == "archive":
                self._st.mark_done(task_id)
            else:
                self._st.remove_task(task_id)

            # Remove desktop
            bspwm.remove_task_desktop(task_id)

            # If we closed the current task, auto-select next one
            if task_id == current_id:
                remaining = self._st.list_tasks(include_done=False)
                if remaining:
                    next_task = remaining[0]
                    monitor = self._st.get_setting('monitor') or self._cfg.monitor
                    if monitor:
                        bspwm.swap_task_windows(monitor, None, next_task['id'])
                        self._st.set_current_task_id(next_task['id'])
                else:
                    self._st.set_current_task_id(None)

            return True
        except bspwm.BspwmError:
            return False

    def move_task_up(self, task_id: int) -> bool:
        """Move a task up in the list."""
        return self._st.move_task_up(task_id)

    def move_task_down(self, task_id: int) -> bool:
        """Move a task down in the list."""
        return self._st.move_task_down(task_id)

    def reorder_task(self, task_id: int, new_index: int) -> bool:
        """Move a task to a specific index."""
        return self._st.reorder_task(task_id, new_index)

    def get_window_count(self, task_id: int) -> int:
        """Get window count for a task."""
        current_id = self._st.get_current_task_id()

        if task_id == current_id:
            return bspwm.get_window_count(ACTIVE_DESKTOP)
        else:
            desktop = bspwm.task_desktop_name(task_id)
            if bspwm.desktop_exists(desktop):
                return bspwm.get_window_count(desktop)
            return 0


class TaskPicker:
    """Task picker window using pywebview."""

    def __init__(self, token: str):
        self.token = token
        self.api = PickerAPI(token)
        self.window = None

    def run(self):
        """Start the picker."""
        try:
            import webview
        except ImportError:
            print("[picker] ERROR: pywebview not installed. Run: pip install pywebview", file=sys.stderr)
            sys.exit(1)

        # Get HTML file path
        ui_dir = Path(__file__).parent / 'ui'
        html_file = ui_dir / 'index.html'

        if not html_file.exists():
            print(f"[picker] ERROR: UI file not found: {html_file}", file=sys.stderr)
            sys.exit(1)

        # Read HTML content directly
        html_content = html_file.read_text()

        # Create window with API using HTML string
        self.window = webview.create_window(
            'taskwm - Tasks',
            html=html_content,
            js_api=self.api,
            width=600,
            height=500,
            resizable=True,
            text_select=False,
        )

        # Position window on tasks desktop after it's shown
        def on_shown():
            self._position_window()

        self.window.events.shown += on_shown

        # Start webview (blocking)
        webview.start()

    def _position_window(self):
        """Position window on tasks desktop."""
        try:
            import subprocess

            # Find our window by title
            result = subprocess.run(
                ['xdotool', 'search', '--name', 'taskwm - Tasks'],
                capture_output=True, text=True, timeout=2
            )

            if result.returncode == 0 and result.stdout.strip():
                dec_id = int(result.stdout.strip().split('\n')[0])
                window_id = hex(dec_id)

                # Move to tasks desktop and tile
                bspwm.move_window(window_id, TASKS_DESKTOP)
                bspwm.set_window_state(window_id, 'tiled')
        except Exception as e:
            print(f"[picker] Could not position window: {e}", file=sys.stderr)


def run_picker():
    """Entry point for picker UI."""
    # Read token from file
    token = ''
    if TOKEN_FILE.exists():
        try:
            token = TOKEN_FILE.read_text().strip()
        except Exception as e:
            print(f"[picker] WARNING: Could not read token file: {e}", file=sys.stderr)

    if not token:
        print("[picker] WARNING: No token found, running in dev mode", file=sys.stderr)
        token = 'dev-mode'

    picker = TaskPicker(token)
    picker.run()


if __name__ == '__main__':
    run_picker()
