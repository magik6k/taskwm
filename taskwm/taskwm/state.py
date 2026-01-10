"""State management for taskwm - handles task persistence."""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

STATE_DIR = Path.home() / ".local" / "state" / "taskwm"
STATE_FILE = STATE_DIR / "state.json"

DEFAULT_STATE = {
    "version": 1,
    "current_task_id": None,
    "next_id": 1,
    "tasks": [],
    "settings_cache": {
        "monitor": None,
        "bar_height": 24,
        "active_padding_prev": 0
    }
}


class State:
    """Manages taskwm state with atomic file operations."""

    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self._data = None

    def _ensure_dir(self):
        """Ensure state directory exists."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        """Load state from file, creating default if missing."""
        if self._data is not None:
            return self._data

        self._ensure_dir()

        if not self.state_file.exists():
            self._data = DEFAULT_STATE.copy()
            self._data["tasks"] = []
            self._data["settings_cache"] = DEFAULT_STATE["settings_cache"].copy()
            self.save()
            return self._data

        try:
            with open(self.state_file, 'r') as f:
                self._data = json.load(f)
            return self._data
        except (json.JSONDecodeError, IOError):
            self._data = DEFAULT_STATE.copy()
            self._data["tasks"] = []
            self._data["settings_cache"] = DEFAULT_STATE["settings_cache"].copy()
            return self._data

    def save(self):
        """Save state atomically (write to temp, then rename)."""
        self._ensure_dir()

        if self._data is None:
            return

        fd, tmp_path = tempfile.mkstemp(dir=self.state_file.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self._data, f, indent=2)
            os.rename(tmp_path, self.state_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def reload(self):
        """Force reload from disk."""
        self._data = None
        return self.load()

    # Task CRUD operations

    def add_task(self, title: str) -> int:
        """Add a new task and return its ID."""
        data = self.load()

        # Sanitize title (remove newlines)
        title = title.replace('\n', ' ').replace('\r', '').strip()
        if not title:
            raise ValueError("Task title cannot be empty")

        task_id = data["next_id"]
        data["next_id"] += 1

        task = {
            "id": task_id,
            "title": title,
            "created": int(time.time()),
            "done": False
        }
        data["tasks"].append(task)
        self.save()

        return task_id

    def list_tasks(self, include_done: bool = False) -> list:
        """List all tasks (optionally including done tasks)."""
        data = self.load()
        if include_done:
            return data["tasks"]
        return [t for t in data["tasks"] if not t.get("done", False)]

    def get_task(self, task_id: int) -> Optional[dict]:
        """Get a task by ID."""
        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                return task
        return None

    def remove_task(self, task_id: int) -> bool:
        """Remove a task by ID. Returns True if found and removed."""
        data = self.load()
        original_len = len(data["tasks"])
        data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]

        if len(data["tasks"]) < original_len:
            # Clear current_task_id if we removed the active task
            if data["current_task_id"] == task_id:
                data["current_task_id"] = None
            self.save()
            return True
        return False

    def mark_done(self, task_id: int) -> bool:
        """Mark a task as done. Returns True if found."""
        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["done"] = True
                task["done_at"] = int(time.time())
                if data["current_task_id"] == task_id:
                    data["current_task_id"] = None
                self.save()
                return True
        return False

    # Current task management

    def get_current_task_id(self) -> Optional[int]:
        """Get the ID of the currently selected task."""
        data = self.load()
        return data.get("current_task_id")

    def set_current_task_id(self, task_id: Optional[int]):
        """Set the currently selected task ID."""
        data = self.load()
        data["current_task_id"] = task_id
        self.save()

    def get_current_task(self) -> Optional[dict]:
        """Get the currently selected task."""
        task_id = self.get_current_task_id()
        if task_id is None:
            return None
        return self.get_task(task_id)

    def get_current_title(self) -> str:
        """Get the title of the current task, or empty string."""
        task = self.get_current_task()
        if task:
            return task["title"]
        return ""

    # Settings cache

    def get_setting(self, key: str, default=None):
        """Get a cached setting."""
        data = self.load()
        return data.get("settings_cache", {}).get(key, default)

    def set_setting(self, key: str, value):
        """Set a cached setting."""
        data = self.load()
        if "settings_cache" not in data:
            data["settings_cache"] = {}
        data["settings_cache"][key] = value
        self.save()


# Singleton instance for convenience
_state_instance = None

def get_state() -> State:
    """Get the singleton state instance."""
    global _state_instance
    if _state_instance is None:
        _state_instance = State()
    return _state_instance
