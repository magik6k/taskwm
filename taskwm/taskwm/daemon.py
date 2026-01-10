#!/usr/bin/env python3
"""Background daemon for taskwm - manages UI and bspwm events."""

import os
import sys
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import bspwm, state, config

RUNTIME_DIR = Path.home() / ".local" / "state" / "taskwm"
PID_FILE = RUNTIME_DIR / "daemon.pid"
PICKER_PID_FILE = RUNTIME_DIR / "picker.pid"
BAR_PID_FILE = RUNTIME_DIR / "bar.pid"

# Special desktops
TASKS_DESKTOP = "tasks"
ACTIVE_DESKTOP = "active"
LEGACY_DESKTOPS = ["0", "3", "4", "5", "6", "7", "8", "9"]


class Daemon:
    """Main daemon class."""

    def __init__(self):
        self.cfg = config.get_config()
        self.st = state.get_state()
        self.monitor = None
        self.picker_proc = None
        self.bar_proc = None
        self.event_proc = None
        self.running = False
        self.picker_window_id = None
        self.bar_window_id = None

    def setup(self):
        """Initial setup - determine monitor, ensure desktops."""
        # Determine target monitor
        self.monitor = self.cfg.monitor
        if not self.monitor:
            try:
                self.monitor = bspwm.get_focused_monitor()
            except bspwm.BspwmError:
                monitors = bspwm.get_monitors()
                if monitors:
                    self.monitor = monitors[0]
                else:
                    raise RuntimeError("No monitors found")

        # Save monitor to state
        self.st.set_setting('monitor', self.monitor)

        # Ensure required desktops exist
        required = [TASKS_DESKTOP, ACTIVE_DESKTOP] + LEGACY_DESKTOPS
        bspwm.ensure_desktops(self.monitor, required)

        # Also ensure task desktops for existing tasks
        for task in self.st.list_tasks():
            bspwm.ensure_task_desktop(self.monitor, task['id'])

        print(f"[daemon] Using monitor: {self.monitor}", file=sys.stderr)

    def start_picker(self):
        """Start the picker UI process."""
        if self.picker_proc and self.picker_proc.poll() is None:
            return  # Already running

        script_dir = Path(__file__).parent
        env = os.environ.copy()
        env['TASKWM_COMPONENT'] = 'picker'

        self.picker_proc = subprocess.Popen(
            [sys.executable, '-m', 'taskwm.ui_picker'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Save PID
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        PICKER_PID_FILE.write_text(str(self.picker_proc.pid))

        print(f"[daemon] Started picker (PID {self.picker_proc.pid})", file=sys.stderr)

    def start_bar(self):
        """Start the bar UI process."""
        if self.bar_proc and self.bar_proc.poll() is None:
            return  # Already running

        script_dir = Path(__file__).parent
        env = os.environ.copy()
        env['TASKWM_COMPONENT'] = 'bar'

        self.bar_proc = subprocess.Popen(
            [sys.executable, '-m', 'taskwm.ui_bar'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Save PID
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        BAR_PID_FILE.write_text(str(self.bar_proc.pid))

        print(f"[daemon] Started bar (PID {self.bar_proc.pid})", file=sys.stderr)

    def check_ui_processes(self):
        """Check and restart UI processes if needed."""
        if self.picker_proc and self.picker_proc.poll() is not None:
            print("[daemon] Picker process died, restarting...", file=sys.stderr)
            self.start_picker()

        if self.bar_proc and self.bar_proc.poll() is not None:
            print("[daemon] Bar process died, restarting...", file=sys.stderr)
            self.start_bar()

    def get_picker_window_id(self):
        """Try to find the picker window ID by WM_CLASS."""
        try:
            # Query all windows and check WM_CLASS
            result = subprocess.run(
                ['xdotool', 'search', '--class', 'taskwm-picker'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # Convert decimal to hex format (0x...) to match bspc output
                dec_id = int(result.stdout.strip().split('\n')[0])
                return hex(dec_id)
        except Exception:
            pass
        return None

    def get_bar_window_id(self):
        """Try to find the bar window ID by WM_CLASS."""
        try:
            result = subprocess.run(
                ['xdotool', 'search', '--class', 'taskwm-bar'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # Convert decimal to hex format (0x...) to match bspc output
                dec_id = int(result.stdout.strip().split('\n')[0])
                return hex(dec_id)
        except Exception:
            pass
        return None

    def _normalize_window_id(self, wid: str) -> int:
        """Convert window ID string to int for comparison."""
        if wid is None:
            return 0
        if isinstance(wid, int):
            return wid
        # Handle both "0x00C00052" and "0xc00052" formats
        return int(wid, 16) if wid.startswith('0x') else int(wid)

    def enforce_tasks_desktop(self, event_window_id=None):
        """Ensure only picker window is on tasks desktop."""
        windows = bspwm.list_windows(TASKS_DESKTOP)

        # Update picker window ID if we don't have it
        if not self.picker_window_id:
            self.picker_window_id = self.get_picker_window_id()

        picker_id_int = self._normalize_window_id(self.picker_window_id)

        for win in windows:
            # Skip the picker window (compare as integers to handle format differences)
            win_int = self._normalize_window_id(win)
            if picker_id_int and win_int == picker_id_int:
                continue

            # Move stray window to active desktop
            target = self.cfg.move_stray_to
            if target == "last":
                # Could track last focused, but for v1 just use active
                target = ACTIVE_DESKTOP

            try:
                bspwm.move_window(win, ACTIVE_DESKTOP)
                print(f"[daemon] Moved stray window {win} from tasks to active", file=sys.stderr)
            except bspwm.BspwmError as e:
                print(f"[daemon] Failed to move window {win}: {e}", file=sys.stderr)

    def handle_desktop_focus(self, desktop: str):
        """Handle desktop focus change - manage bar visibility and padding."""
        if desktop == ACTIVE_DESKTOP:
            # Entering active desktop - show bar and set padding
            bar_height = self.cfg.bar_height
            try:
                # Save current padding
                current_padding = bspwm.get_config('top_padding', self.monitor)
                self.st.set_setting('active_padding_prev', int(current_padding))
            except Exception:
                pass

            try:
                bspwm.set_config('top_padding', bar_height, self.monitor)
            except bspwm.BspwmError:
                pass

        else:
            # Leaving active desktop - restore padding if configured
            if self.cfg.hide_bar_when_not_active:
                try:
                    prev_padding = self.st.get_setting('active_padding_prev', 0)
                    bspwm.set_config('top_padding', prev_padding, self.monitor)
                except bspwm.BspwmError:
                    pass

    def event_loop(self):
        """Main event loop - subscribe to bspwm events."""
        events = ['desktop_focus', 'node_add', 'node_transfer']

        while self.running:
            try:
                self.event_proc = bspwm.subscribe(events)

                for line in self.event_proc.stdout:
                    if not self.running:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    parts = line.split()
                    if not parts:
                        continue

                    event_type = parts[0]

                    if event_type == 'desktop_focus':
                        # desktop_focus <monitor_id> <desktop_id> <desktop_name>
                        if len(parts) >= 4:
                            desktop_name = parts[3] if len(parts) > 3 else parts[2]
                            # Try to extract desktop name from the event
                            try:
                                desktop_name = bspwm.get_focused_desktop()
                            except Exception:
                                pass
                            self.handle_desktop_focus(desktop_name)

                    elif event_type == 'node_add':
                        # node_add <monitor_id> <desktop_id> <ip_id> <node_id>
                        # Only enforce if a window appeared on tasks desktop
                        if len(parts) >= 3:
                            desktop_id = parts[2]
                            try:
                                # Get tasks desktop ID
                                tasks_id = bspwm.run_bspc(['query', '-D', '-d', TASKS_DESKTOP], check=False)
                                if desktop_id == tasks_id.strip():
                                    self.enforce_tasks_desktop()
                            except Exception:
                                pass

                    elif event_type == 'node_transfer':
                        # node_transfer <src_mon> <src_desk> <src_node> <dst_mon> <dst_desk> <dst_node>
                        # Only enforce if destination is tasks desktop
                        if len(parts) >= 6:
                            dst_desktop_id = parts[5]
                            try:
                                tasks_id = bspwm.run_bspc(['query', '-D', '-d', TASKS_DESKTOP], check=False)
                                if dst_desktop_id == tasks_id.strip():
                                    self.enforce_tasks_desktop()
                            except Exception:
                                pass

            except Exception as e:
                print(f"[daemon] Event loop error: {e}", file=sys.stderr)
                if self.running:
                    time.sleep(1)  # Brief pause before retry

            finally:
                if self.event_proc:
                    self.event_proc.terminate()
                    self.event_proc = None

    def run(self):
        """Main daemon run method."""
        # Write PID file
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

        def cleanup(signum, frame):
            print("\n[daemon] Shutting down...", file=sys.stderr)
            self.running = False

            if self.event_proc:
                self.event_proc.terminate()

            if self.picker_proc:
                self.picker_proc.terminate()

            if self.bar_proc:
                self.bar_proc.terminate()

            # Clean up PID files
            for f in [PID_FILE, PICKER_PID_FILE, BAR_PID_FILE]:
                try:
                    f.unlink()
                except Exception:
                    pass

            sys.exit(0)

        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)

        try:
            self.setup()
        except Exception as e:
            print(f"[daemon] Setup failed: {e}", file=sys.stderr)
            return 1

        # Start UI processes
        self.start_picker()
        time.sleep(0.5)  # Brief delay between starts
        self.start_bar()

        # Allow UI to initialize - wait longer and retry getting window IDs
        for attempt in range(10):
            time.sleep(0.5)
            self.picker_window_id = self.get_picker_window_id()
            self.bar_window_id = self.get_bar_window_id()
            if self.picker_window_id and self.bar_window_id:
                print(f"[daemon] Found picker: {self.picker_window_id}, bar: {self.bar_window_id}", file=sys.stderr)
                break
            print(f"[daemon] Waiting for UI windows (attempt {attempt + 1})...", file=sys.stderr)

        if not self.picker_window_id:
            print("[daemon] WARNING: Could not find picker window ID", file=sys.stderr)

        self.running = True

        # Start event loop in a thread
        event_thread = threading.Thread(target=self.event_loop, daemon=True)
        event_thread.start()

        # Main loop - monitor UI processes
        print("[daemon] Running...", file=sys.stderr)
        while self.running:
            time.sleep(5)

            # Check if UI processes need restart
            picker_restarted = self.picker_proc and self.picker_proc.poll() is not None
            bar_restarted = self.bar_proc and self.bar_proc.poll() is not None

            self.check_ui_processes()

            # Update window IDs if processes restarted or IDs are missing
            if picker_restarted or not self.picker_window_id:
                new_id = self.get_picker_window_id()
                if new_id:
                    self.picker_window_id = new_id
            if bar_restarted or not self.bar_window_id:
                new_id = self.get_bar_window_id()
                if new_id:
                    self.bar_window_id = new_id

        return 0


def is_daemon_running() -> bool:
    """Check if daemon is already running."""
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # Stale PID file
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        return False


def run_daemon():
    """Entry point for daemon."""
    if is_daemon_running():
        print("Daemon is already running", file=sys.stderr)
        return 1

    daemon = Daemon()
    return daemon.run()


if __name__ == '__main__':
    sys.exit(run_daemon())
