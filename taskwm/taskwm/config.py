"""Configuration handling for taskwm."""

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "taskwm"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "monitor": None,  # None = auto-detect (focused monitor at daemon start)
    "bar_height": 24,
    "theme": {
        "font": "monospace 10",
        "bg": "#111111",
        "fg": "#e6e6e6",
        "accent": "#66aaff",
        "button_bg": "#222222",
        "button_fg": "#e6e6e6",
        "entry_bg": "#1a1a1a",
        "entry_fg": "#e6e6e6",
        "select_bg": "#333333",
        "border": "#333333"
    },
    "behavior": {
        "close_policy": "delete",  # "archive" or "delete"
        "move_stray_on_tasks_to": "active",  # "active" or "last"
        "hide_bar_when_not_active": False
    }
}


class Config:
    """Handles configuration loading with defaults."""

    def __init__(self, config_file: Path = CONFIG_FILE):
        self.config_file = config_file
        self._data = None

    def _ensure_dir(self):
        """Ensure config directory exists."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge override into base."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load(self) -> dict:
        """Load config from file, merging with defaults."""
        if self._data is not None:
            return self._data

        self._ensure_dir()

        # Start with defaults
        self._data = json.loads(json.dumps(DEFAULT_CONFIG))  # Deep copy

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)
                self._data = self._deep_merge(self._data, user_config)
            except (json.JSONDecodeError, IOError):
                pass  # Use defaults on error

        return self._data

    def reload(self):
        """Force reload from disk."""
        self._data = None
        return self.load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dot-notation key (e.g., 'theme.bg')."""
        data = self.load()
        keys = key.split('.')
        value = data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    # Convenience properties
    @property
    def monitor(self) -> str:
        """Get configured monitor (may be None for auto-detect)."""
        return self.get('monitor')

    @property
    def bar_height(self) -> int:
        """Get bar height."""
        return self.get('bar_height', 24)

    @property
    def theme(self) -> dict:
        """Get theme configuration."""
        return self.get('theme', DEFAULT_CONFIG['theme'])

    @property
    def close_policy(self) -> str:
        """Get close policy ('archive' or 'delete')."""
        return self.get('behavior.close_policy', 'delete')

    @property
    def move_stray_to(self) -> str:
        """Get where to move stray windows on tasks desktop."""
        return self.get('behavior.move_stray_on_tasks_to', 'active')

    @property
    def hide_bar_when_not_active(self) -> bool:
        """Whether to hide bar when not on active desktop."""
        return self.get('behavior.hide_bar_when_not_active', False)


# Singleton instance
_config_instance = None

def get_config() -> Config:
    """Get the singleton config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def create_default_config():
    """Create a default config file if it doesn't exist."""
    config = Config()
    config._ensure_dir()
    if not config.config_file.exists():
        with open(config.config_file, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
