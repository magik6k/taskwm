# taskwm - Task-Centric Workspaces for bspwm

A task-based workflow manager for bspwm that lets you organize your work into tasks, each with its own set of windows.

## Features

- **Task Picker** (Super+1): A dedicated desktop for managing tasks
- **Active Workspace** (Super+2): Your current task's windows with a title bar
- **Window Swapping**: Seamlessly switch between tasks, windows follow automatically
- **Task Bar**: Shows current task, switch tasks without leaving your workspace
- **CLI Interface**: Short commands for scripting and quick actions

## Dependencies

**Required:**
- Python 3.x
- Tkinter (`tk` package on Arch)
- bspwm / bspc
- xdotool (for window ID detection)

**Optional:**
- xprop (for WM_CLASS inspection)

### Installing on Arch Linux

```sh
sudo pacman -S python tk bspwm xdotool
```

## Installation

1. Clone or copy the taskwm directory:

```sh
git clone <repo> ~/src/taskwm
# or copy the taskwm folder to your preferred location
```

2. Create symlinks in your PATH:

```sh
mkdir -p ~/.local/bin
ln -sf ~/src/taskwm/taskwm/bin/tw ~/.local/bin/tw
```

3. Ensure `~/.local/bin` is in your PATH (add to `~/.bashrc` or `~/.zshrc`):

```sh
export PATH="$HOME/.local/bin:$PATH"
```

4. Optionally create a default config:

```sh
mkdir -p ~/.config/taskwm
cat > ~/.config/taskwm/config.json << 'EOF'
{
  "monitor": null,
  "bar_height": 24,
  "theme": {
    "font": "monospace 10",
    "bg": "#111111",
    "fg": "#e6e6e6",
    "accent": "#66aaff"
  },
  "behavior": {
    "close_policy": "delete",
    "move_stray_on_tasks_to": "active"
  }
}
EOF
```

## Configuration

### sxhkdrc

Add these keybindings to your `~/.config/sxhkd/sxhkdrc`:

```sh
# Task workspaces
super + 1
    bspc desktop -f tasks

super + 2
    bspc desktop -f active

# Legacy numeric desktops
super + {0,3,4,5,6,7,8,9}
    bspc desktop -f {0,3,4,5,6,7,8,9}

# Move window to desktop
super + shift + {0,1,2,3,4,5,6,7,8,9}
    bspc node -d {0,tasks,active,3,4,5,6,7,8,9}

# Quick done - close current task (optional)
super + shift + d
    tw d -f
```

### bspwmrc

Add to your `~/.config/bspwm/bspwmrc`:

```sh
# Start taskwm daemon (after sxhkd)
tw daemon &

# Optional: bspwm rules for taskwm windows
bspc rule -a taskwm-picker desktop=tasks state=floating
bspc rule -a taskwm-bar desktop=active state=floating sticky=on layer=above
```

**Important:** The daemon will create the `tasks` and `active` desktops automatically. You may want to adjust your existing desktop setup. For example, change:

```sh
# Old:
bspc monitor -d I II III IV V VI VII VIII IX X

# New (let taskwm manage tasks/active):
bspc monitor -d 0 3 4 5 6 7 8 9
```

## Usage

### CLI Commands

```sh
tw a "title"     # Add a new task, prints ID
tw l             # List tasks (ID<tab>title)
tw l -a          # List all tasks including done
tw s <id>        # Select task (swap windows into active)
tw d             # Mark current task done (prompts if windows exist)
tw d -f          # Force done (closes windows without prompt)
tw r <id>        # Remove task
tw r <id> -f     # Force remove (closes windows)
tw cur           # Print current task ID
tw title         # Print current task title
tw daemon        # Run the background daemon
tw ui            # Start UI without daemon (for development)
```

### Workflow

1. **Start the daemon** (automatic if in bspwmrc):
   ```sh
   tw daemon &
   ```

2. **Create a task**:
   - Press Super+1 to go to the Tasks desktop
   - Type a task name and press Enter or click +
   - Or from CLI: `tw a "Fix bug #123"`

3. **Select a task**:
   - Click "Select" in the picker, or
   - Use the bar menu (≡) on the Active desktop, or
   - From CLI: `tw s 1`

4. **Work on your task**:
   - Press Super+2 to go to Active desktop
   - Open windows, they stay with your task
   - Switch tasks anytime - windows move automatically

5. **Complete a task**:
   - Click "Done" in the bar, or
   - Click "Close" in the picker, or
   - From CLI: `tw d`

### Keyboard Shortcuts (in Picker)

| Key | Action |
|-----|--------|
| Up/Down | Navigate task list |
| Enter | Select highlighted task (or add if typing) |
| Delete / Ctrl+D | Close highlighted task |
| Ctrl+N | Focus input field |
| Escape | Clear input / deselect |

## File Locations

- **State**: `~/.local/state/taskwm/state.json`
- **Config**: `~/.config/taskwm/config.json`
- **PID files**: `~/.local/state/taskwm/*.pid`

## Configuration Options

```json
{
  "monitor": "DP-0",           // Monitor for tasks/active desktops (null = auto)
  "bar_height": 24,            // Top bar height in pixels
  "theme": {
    "font": "monospace 10",    // Font family and size
    "bg": "#111111",           // Background color
    "fg": "#e6e6e6",           // Foreground color
    "accent": "#66aaff",       // Accent/highlight color
    "button_bg": "#222222",    // Button background
    "entry_bg": "#1a1a1a",     // Input field background
    "select_bg": "#333333",    // Selection highlight
    "border": "#333333"        // Border color
  },
  "behavior": {
    "close_policy": "delete",  // "delete" or "archive"
    "move_stray_on_tasks_to": "active",  // Where to move stray windows
    "hide_bar_when_not_active": false    // Hide bar on other desktops
  }
}
```

## Troubleshooting

### Check if daemon is running

```sh
ps aux | grep 'tw daemon'
cat ~/.local/state/taskwm/daemon.pid
```

### Restart the daemon

```sh
pkill -f 'taskwm'
tw daemon &
```

### View state

```sh
cat ~/.local/state/taskwm/state.json | python -m json.tool
```

### Check desktops

```sh
bspc query -D --names
```

### Reset state

```sh
rm ~/.local/state/taskwm/state.json
pkill -f 'taskwm'
tw daemon &
```

### Windows not moving correctly

1. Ensure task desktops exist:
   ```sh
   bspc query -D --names | grep 't:'
   ```

2. Manually ensure desktops:
   ```sh
   bspc monitor -a tasks
   bspc monitor -a active
   ```

### UI not appearing

1. Check if Tkinter is installed:
   ```sh
   python -c "import tkinter"
   ```

2. Start UI manually for debugging:
   ```sh
   tw ui --picker
   tw ui --bar
   ```

## Architecture

```
taskwm/
├── taskwm/
│   ├── __init__.py      # Package init
│   ├── __main__.py      # Module entry point
│   ├── cli.py           # CLI commands (tw)
│   ├── state.py         # State management (JSON)
│   ├── config.py        # Configuration handling
│   ├── bspwm.py         # bspwm interaction (bspc wrapper)
│   ├── daemon.py        # Background daemon
│   ├── ui_picker.py     # Task picker UI (Tkinter)
│   └── ui_bar.py        # Top bar UI (Tkinter)
└── bin/
    └── tw               # CLI wrapper script
```

## License

MIT
