"""bspwm interaction module - handles all bspc commands."""

import subprocess
import shutil
from typing import Optional


class BspwmError(Exception):
    """Error interacting with bspwm."""
    pass


def _check_bspc():
    """Check if bspc is available."""
    if not shutil.which('bspc'):
        raise BspwmError("bspc not found in PATH. Is bspwm installed?")


def run_bspc(args: list, check: bool = True) -> str:
    """Run a bspc command and return output.

    Args:
        args: Arguments to pass to bspc
        check: If True, raise on non-zero exit

    Returns:
        stdout as string (stripped)
    """
    _check_bspc()

    cmd = ['bspc'] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        if check and result.returncode != 0:
            stderr = result.stderr.strip()
            raise BspwmError(f"bspc {' '.join(args)} failed: {stderr}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise BspwmError(f"bspc {' '.join(args)} timed out")
    except FileNotFoundError:
        raise BspwmError("bspc not found")


def desktop_exists(name: str) -> bool:
    """Check if a desktop with the given name exists."""
    try:
        desktops = run_bspc(['query', '-D', '--names'])
        return name in desktops.split('\n')
    except BspwmError:
        return False


def get_desktops(monitor: Optional[str] = None) -> list:
    """Get list of desktop names, optionally filtered by monitor."""
    args = ['query', '-D', '--names']
    if monitor:
        args.extend(['-m', monitor])
    try:
        output = run_bspc(args)
        return [d for d in output.split('\n') if d]
    except BspwmError:
        return []


def get_monitors() -> list:
    """Get list of monitor names."""
    try:
        output = run_bspc(['query', '-M', '--names'])
        return [m for m in output.split('\n') if m]
    except BspwmError:
        return []


def get_focused_monitor() -> str:
    """Get the currently focused monitor name."""
    return run_bspc(['query', '-M', '-m', 'focused', '--names'])


def get_focused_desktop() -> str:
    """Get the currently focused desktop name."""
    return run_bspc(['query', '-D', '-d', 'focused', '--names'])


def monitor_of_desktop(desktop: str) -> Optional[str]:
    """Get the monitor that contains the given desktop."""
    try:
        return run_bspc(['query', '-M', '-d', desktop, '--names'])
    except BspwmError:
        return None


def ensure_desktop(monitor: str, name: str):
    """Ensure a desktop exists on the given monitor."""
    if not desktop_exists(name):
        run_bspc(['monitor', monitor, '-a', name])


def ensure_desktops(monitor: str, names: list):
    """Ensure multiple desktops exist on the given monitor."""
    existing = set(get_desktops(monitor))
    for name in names:
        if name not in existing:
            run_bspc(['monitor', monitor, '-a', name])


def remove_desktop(name: str) -> bool:
    """Remove a desktop. Returns True if successful."""
    try:
        run_bspc(['desktop', name, '-r'])
        return True
    except BspwmError:
        return False


def list_windows(desktop: str) -> list:
    """List window IDs on a desktop."""
    try:
        output = run_bspc(['query', '-N', '-d', desktop, '-n', '.window'])
        return [w for w in output.split('\n') if w]
    except BspwmError:
        return []


def move_window(window_id: str, desktop: str):
    """Move a window to a desktop."""
    run_bspc(['node', window_id, '-d', desktop])


def close_window(window_id: str):
    """Close a window gracefully."""
    run_bspc(['node', window_id, '-c'])


def kill_window(window_id: str):
    """Kill a window forcefully."""
    run_bspc(['node', window_id, '-k'])


def focus_desktop(name: str):
    """Focus a desktop by name."""
    run_bspc(['desktop', '-f', name])


def get_config(key: str, monitor: Optional[str] = None) -> str:
    """Get a bspc config value."""
    args = ['config']
    if monitor:
        args.extend(['-m', monitor])
    args.append(key)
    return run_bspc(args)


def set_config(key: str, value, monitor: Optional[str] = None):
    """Set a bspc config value."""
    args = ['config']
    if monitor:
        args.extend(['-m', monitor])
    args.extend([key, str(value)])
    run_bspc(args)


def set_window_state(window_id: str, state: str):
    """Set window state (floating, tiled, etc.)."""
    run_bspc(['node', window_id, '-t', state])


def set_window_flag(window_id: str, flag: str, value: bool = True):
    """Set or unset a window flag (sticky, locked, etc.)."""
    prefix = '' if value else '~'
    run_bspc(['node', window_id, '-g', f'{prefix}{flag}'])


def set_window_layer(window_id: str, layer: str):
    """Set window layer (below, normal, above)."""
    run_bspc(['node', window_id, '-l', layer])


def subscribe(events: list):
    """Subscribe to bspwm events. Returns a Popen object.

    Caller should read from proc.stdout line by line.
    """
    _check_bspc()
    cmd = ['bspc', 'subscribe'] + events
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


# Task-specific helpers

def task_desktop_name(task_id: int) -> str:
    """Get the desktop name for a task ID."""
    # Use underscore instead of colon to avoid conflicts with bspc's monitor:desktop syntax
    return f"t_{task_id}"


def ensure_task_desktop(monitor: str, task_id: int):
    """Ensure a task desktop exists."""
    ensure_desktop(monitor, task_desktop_name(task_id))


def remove_task_desktop(task_id: int) -> bool:
    """Remove a task desktop if it exists and is empty."""
    name = task_desktop_name(task_id)
    if not desktop_exists(name):
        return True

    # Check if empty
    windows = list_windows(name)
    if windows:
        return False

    return remove_desktop(name)


def _is_taskwm_window(window_id: str) -> bool:
    """Check if a window belongs to taskwm (picker or bar)."""
    try:
        result = subprocess.run(
            ['xprop', '-id', window_id, 'WM_CLASS'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            wm_class = result.stdout.lower()
            return 'taskwm' in wm_class
    except Exception:
        pass
    return False


def swap_task_windows(monitor: str, old_task_id: Optional[int], new_task_id: Optional[int]):
    """Swap windows between active desktop and task desktops.

    1. Move windows from 'active' to old task desktop (if old_task_id)
    2. Move windows from new task desktop to 'active' (if new_task_id)
    """
    # Ensure desktops exist
    ensure_desktop(monitor, 'active')
    if old_task_id is not None:
        ensure_task_desktop(monitor, old_task_id)
    if new_task_id is not None:
        ensure_task_desktop(monitor, new_task_id)

    # Move current windows from active to old task (skip taskwm windows)
    if old_task_id is not None:
        old_desktop = task_desktop_name(old_task_id)
        for win in list_windows('active'):
            if not _is_taskwm_window(win):
                move_window(win, old_desktop)

    # Move windows from new task to active (skip taskwm windows)
    if new_task_id is not None:
        new_desktop = task_desktop_name(new_task_id)
        for win in list_windows(new_desktop):
            if not _is_taskwm_window(win):
                move_window(win, 'active')


def close_all_windows(desktop: str, force: bool = False):
    """Close all windows on a desktop."""
    windows = list_windows(desktop)
    for win in windows:
        if force:
            kill_window(win)
        else:
            close_window(win)


def get_window_count(desktop: str) -> int:
    """Get the number of windows on a desktop."""
    return len(list_windows(desktop))
