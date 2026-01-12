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
            "done": False,
            "size": "M",
            "category": None,
            "prepared": False,
            "blocked": False
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

    def rename_task(self, task_id: int, new_title: str) -> bool:
        """Rename a task. Returns True if found and renamed."""
        new_title = new_title.replace('\n', ' ').replace('\r', '').strip()
        if not new_title:
            return False

        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["title"] = new_title
                self.save()
                return True
        return False

    def set_task_size(self, task_id: int, size: str) -> bool:
        """Set task t-shirt size. Valid sizes: S, M, L."""
        valid_sizes = ("S", "M", "L")
        if size not in valid_sizes:
            return False

        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["size"] = size
                self.save()
                return True
        return False

    def set_task_category(self, task_id: int, category_id: Optional[int]) -> bool:
        """Set task category. Use None to clear category."""
        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["category"] = category_id
                self.save()
                return True
        return False

    def set_task_prepared(self, task_id: int, prepared: bool) -> bool:
        """Set task prepared state."""
        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["prepared"] = prepared
                self.save()
                return True
        return False

    def set_task_blocked(self, task_id: int, blocked: bool) -> bool:
        """Set task blocked state."""
        data = self.load()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["blocked"] = blocked
                self.save()
                return True
        return False

    # Category management

    def get_categories(self) -> list:
        """Get all categories."""
        return self.get_setting("categories", [])

    def add_category(self, name: str, color: str) -> Optional[int]:
        """Add a new category. Returns the new category ID."""
        name = name.strip()
        if not name:
            return None

        data = self.load()
        if "settings_cache" not in data:
            data["settings_cache"] = {}

        categories = data["settings_cache"].get("categories", [])
        next_id = data["settings_cache"].get("next_category_id", 1)

        category = {
            "id": next_id,
            "name": name,
            "color": color
        }
        categories.append(category)

        data["settings_cache"]["categories"] = categories
        data["settings_cache"]["next_category_id"] = next_id + 1
        self.save()

        return next_id

    def update_category(self, category_id: int, name: str, color: str) -> bool:
        """Update a category's name and color."""
        name = name.strip()
        if not name:
            return False

        data = self.load()
        categories = data.get("settings_cache", {}).get("categories", [])

        for cat in categories:
            if cat["id"] == category_id:
                cat["name"] = name
                cat["color"] = color
                self.save()
                return True
        return False

    def remove_category(self, category_id: int) -> bool:
        """Remove a category. Clears category from all tasks using it."""
        data = self.load()
        categories = data.get("settings_cache", {}).get("categories", [])

        original_len = len(categories)
        categories = [c for c in categories if c["id"] != category_id]

        if len(categories) < original_len:
            data["settings_cache"]["categories"] = categories
            # Clear category from tasks that had it
            for task in data["tasks"]:
                if task.get("category") == category_id:
                    task["category"] = None
            self.save()
            return True
        return False

    def move_task_up(self, task_id: int) -> bool:
        """Move a task up in the list. Returns True if moved."""
        data = self.load()
        tasks = data["tasks"]
        for i, task in enumerate(tasks):
            if task["id"] == task_id and i > 0:
                tasks[i], tasks[i-1] = tasks[i-1], tasks[i]
                self.save()
                return True
        return False

    def move_task_down(self, task_id: int) -> bool:
        """Move a task down in the list. Returns True if moved."""
        data = self.load()
        tasks = data["tasks"]
        for i, task in enumerate(tasks):
            if task["id"] == task_id and i < len(tasks) - 1:
                tasks[i], tasks[i+1] = tasks[i+1], tasks[i]
                self.save()
                return True
        return False

    def reorder_task(self, task_id: int, new_index: int) -> bool:
        """Move a task to a specific index. Returns True if moved."""
        data = self.load()
        tasks = data["tasks"]

        # Find current index
        current_index = None
        for i, task in enumerate(tasks):
            if task["id"] == task_id:
                current_index = i
                break

        if current_index is None:
            return False

        # Clamp new_index to valid range
        new_index = max(0, min(new_index, len(tasks) - 1))

        if current_index == new_index:
            return True  # Already at position

        # Remove and insert at new position
        task = tasks.pop(current_index)
        tasks.insert(new_index, task)
        self.save()
        return True

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
