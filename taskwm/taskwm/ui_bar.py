#!/usr/bin/env python3
"""Top bar UI for taskwm - shows current task and provides task switching menu."""

import tkinter as tk
from tkinter import messagebox
import sys
import subprocess

from . import state, bspwm, config

ACTIVE_DESKTOP = "active"


class TaskBar:
    """Thin top bar showing current task."""

    def __init__(self):
        self.cfg = config.get_config()
        self.st = state.get_state()
        self.theme = self.cfg.theme
        self.bar_height = self.cfg.bar_height

        self.root = tk.Tk(className="taskwm-bar")
        self.root.title("taskwm-bar")

        # Remove window decorations
        self.root.overrideredirect(True)

        self.setup_ui()

        # Schedule window positioning
        self.root.after(100, self.position_window)

        # Start polling for state changes
        self.root.after(500, self.poll_state)

    def setup_ui(self):
        """Build the bar UI."""
        bg = self.theme.get('bg', '#111111')
        fg = self.theme.get('fg', '#e6e6e6')
        button_bg = self.theme.get('button_bg', '#222222')
        accent = self.theme.get('accent', '#66aaff')
        font_spec = self.theme.get('font', 'monospace 10')

        font_parts = font_spec.rsplit(' ', 1)
        font_family = font_parts[0] if len(font_parts) > 1 else 'monospace'
        font_size = int(font_parts[1]) if len(font_parts) > 1 else 10

        self.root.configure(bg=bg)

        # Main frame
        self.main_frame = tk.Frame(self.root, bg=bg, height=self.bar_height)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.pack_propagate(False)

        # Done button (left side)
        self.done_btn = tk.Button(
            self.main_frame,
            text="Done",
            bg=button_bg,
            fg=fg,
            activebackground='#aa3333',
            activeforeground='#ffffff',
            font=(font_family, font_size - 1),
            relief=tk.FLAT,
            command=self.done_task,
            padx=8
        )
        self.done_btn.pack(side=tk.LEFT, padx=5, pady=2)

        # Menu button (right side)
        self.menu_btn = tk.Button(
            self.main_frame,
            text="\u2261",  # ≡ hamburger menu
            bg=button_bg,
            fg=fg,
            activebackground=accent,
            activeforeground='#000000',
            font=(font_family, font_size + 2),
            relief=tk.FLAT,
            command=self.show_menu,
            padx=8
        )
        self.menu_btn.pack(side=tk.RIGHT, padx=5, pady=2)

        # Center title label
        self.title_label = tk.Label(
            self.main_frame,
            text="No active task",
            bg=bg,
            fg=fg,
            font=(font_family, font_size)
        )
        self.title_label.pack(expand=True)

        # Create popup menu
        self.task_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=bg,
            fg=fg,
            activebackground=accent,
            activeforeground='#000000',
            font=(font_family, font_size - 1),
            relief=tk.FLAT
        )

    def position_window(self):
        """Position bar at top of screen on active desktop."""
        # Get screen dimensions
        try:
            # Get monitor geometry using xrandr or bspwm
            monitor = self.st.get_setting('monitor')
            if not monitor:
                monitor = bspwm.get_focused_monitor()

            # Try to get monitor geometry
            result = subprocess.run(
                ['bspc', 'query', '-T', '-m', monitor],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                import json
                monitor_info = json.loads(result.stdout)
                rect = monitor_info.get('rectangle', {})
                x = rect.get('x', 0)
                y = rect.get('y', 0)
                width = rect.get('width', self.root.winfo_screenwidth())
            else:
                x, y = 0, 0
                width = self.root.winfo_screenwidth()
        except Exception:
            x, y = 0, 0
            width = self.root.winfo_screenwidth()

        # Set geometry: full width, bar_height tall, at top
        self.root.geometry(f"{width}x{self.bar_height}+{x}+{y}")

        # Keep window on top (Tk level, since we're override-redirect)
        self.root.attributes('-topmost', True)

        # Force position with xdotool as Tk geometry doesn't always work with override-redirect
        self.root.update_idletasks()
        try:
            wid = self.root.winfo_id()
            subprocess.run(['xdotool', 'windowmove', str(wid), str(x), str(y)], timeout=2)
            subprocess.run(['xdotool', 'windowsize', str(wid), str(width), str(self.bar_height)], timeout=2)
        except Exception:
            pass

        # Check initial visibility
        self.check_visibility()

    def update_title(self):
        """Update the title label from state."""
        self.st.reload()
        task = self.st.get_current_task()

        if task:
            title = task['title']
            if len(title) > 60:
                title = title[:57] + "..."
            self.title_label.configure(text=title)
        else:
            self.title_label.configure(text="No active task")

    def show_menu(self):
        """Show the task switching menu."""
        # Clear existing menu items
        self.task_menu.delete(0, tk.END)

        # Reload tasks
        self.st.reload()
        tasks = self.st.list_tasks()
        current_id = self.st.get_current_task_id()

        if not tasks:
            self.task_menu.add_command(label="(no tasks)", state=tk.DISABLED)
        else:
            for task in tasks:
                title = task['title']
                if len(title) > 40:
                    title = title[:37] + "..."

                # Mark current task
                prefix = "\u2713 " if task['id'] == current_id else "   "

                self.task_menu.add_command(
                    label=f"{prefix}{title}",
                    command=lambda tid=task['id']: self.select_task(tid)
                )

        self.task_menu.add_separator()
        self.task_menu.add_command(
            label="Go to Tasks",
            command=self.go_to_tasks
        )

        # Show menu below the button
        x = self.menu_btn.winfo_rootx()
        y = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height()
        self.task_menu.post(x, y)

    def select_task(self, task_id: int):
        """Select a task from the menu."""
        monitor = self.st.get_setting('monitor')
        if not monitor:
            try:
                monitor = bspwm.get_focused_monitor()
                self.st.set_setting('monitor', monitor)
            except bspwm.BspwmError:
                return

        old_task_id = self.st.get_current_task_id()

        if task_id == old_task_id:
            return  # Already selected

        try:
            bspwm.swap_task_windows(monitor, old_task_id, task_id)
            self.st.set_current_task_id(task_id)
            self.update_title()
        except bspwm.BspwmError as e:
            print(f"[bar] Error selecting task: {e}", file=sys.stderr)

    def go_to_tasks(self):
        """Switch to tasks desktop."""
        try:
            bspwm.focus_desktop("tasks")
        except bspwm.BspwmError:
            pass

    def done_task(self):
        """Mark current task as done."""
        task_id = self.st.get_current_task_id()
        if task_id is None:
            return

        window_count = bspwm.get_window_count(ACTIVE_DESKTOP)

        if window_count > 0:
            result = messagebox.askyesno(
                "Confirm Done",
                f"This will close {window_count} window(s).\nAre you sure?"
            )
            if not result:
                return

        try:
            # Close windows
            bspwm.close_all_windows(ACTIVE_DESKTOP)

            # Handle based on policy
            if self.cfg.close_policy == "archive":
                self.st.mark_done(task_id)
            else:
                self.st.remove_task(task_id)

            # Remove task desktop
            bspwm.remove_task_desktop(task_id)

            self.update_title()
        except bspwm.BspwmError as e:
            print(f"[bar] Error completing task: {e}", file=sys.stderr)

    def poll_state(self):
        """Poll state file for changes."""
        self.update_title()
        self.check_visibility()
        self.root.after(500, self.poll_state)

    def check_visibility(self):
        """Show/hide bar based on current desktop on our monitor."""
        try:
            # Get the focused desktop on our specific monitor, not globally
            monitor = self.st.get_setting('monitor') or 'DP-0'
            result = subprocess.run(
                ['bspc', 'query', '-D', '-d', f'{monitor}:focused', '--names'],
                capture_output=True, text=True, timeout=2
            )
            current = result.stdout.strip() if result.returncode == 0 else ''

            if current == ACTIVE_DESKTOP:
                self.root.deiconify()
            else:
                self.root.withdraw()
        except Exception:
            pass

    def run(self):
        """Start the bar."""
        self.root.mainloop()


def run_bar():
    """Entry point for bar UI."""
    bar = TaskBar()
    bar.run()


if __name__ == '__main__':
    run_bar()
