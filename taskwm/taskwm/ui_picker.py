#!/usr/bin/env python3
"""Task picker UI for taskwm - Tkinter-based dark theme task list."""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

from . import state, bspwm, config

TASKS_DESKTOP = "tasks"
ACTIVE_DESKTOP = "active"


class TaskPicker:
    """Task picker window."""

    def __init__(self):
        self.cfg = config.get_config()
        self.st = state.get_state()
        self.theme = self.cfg.theme
        self.selected_index = 0
        self.task_frames = []

        self.root = tk.Tk(className="taskwm-picker")
        self.root.title("taskwm - Tasks")

        self.setup_theme()
        self.setup_ui()
        self.setup_bindings()

        # Schedule window positioning after window is mapped
        self.root.after(100, self.position_window)

        # Start polling for state changes
        self.root.after(500, self.poll_state)

    def setup_theme(self):
        """Configure dark theme."""
        bg = self.theme.get('bg', '#111111')
        fg = self.theme.get('fg', '#e6e6e6')
        font = self.theme.get('font', 'monospace 10')

        self.root.configure(bg=bg)

        # Configure ttk style
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('.',
            background=bg,
            foreground=fg,
            font=font
        )

        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=fg, font=font)
        style.configure('TEntry',
            fieldbackground=self.theme.get('entry_bg', '#1a1a1a'),
            foreground=fg,
            font=font
        )
        style.configure('TButton',
            background=self.theme.get('button_bg', '#222222'),
            foreground=self.theme.get('button_fg', '#e6e6e6'),
            font=font,
            padding=5
        )
        style.map('TButton',
            background=[('active', self.theme.get('accent', '#66aaff'))]
        )

        # Custom style for task rows
        style.configure('Task.TFrame', background=bg)
        style.configure('TaskSelected.TFrame',
            background=self.theme.get('select_bg', '#333333')
        )

    def setup_ui(self):
        """Build the UI."""
        bg = self.theme.get('bg', '#111111')
        fg = self.theme.get('fg', '#e6e6e6')
        entry_bg = self.theme.get('entry_bg', '#1a1a1a')
        font_spec = self.theme.get('font', 'monospace 10')

        # Parse font spec
        font_parts = font_spec.rsplit(' ', 1)
        font_family = font_parts[0] if len(font_parts) > 1 else 'monospace'
        font_size = int(font_parts[1]) if len(font_parts) > 1 else 10

        # Main container
        self.main_frame = ttk.Frame(self.root, style='TFrame')
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Top row: input + add button
        top_frame = ttk.Frame(self.main_frame, style='TFrame')
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.entry = tk.Entry(
            top_frame,
            bg=entry_bg,
            fg=fg,
            insertbackground=fg,
            font=(font_family, font_size),
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.theme.get('border', '#333333'),
            highlightcolor=self.theme.get('accent', '#66aaff')
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)

        self.add_btn = tk.Button(
            top_frame,
            text="+",
            bg=self.theme.get('button_bg', '#222222'),
            fg=self.theme.get('button_fg', '#e6e6e6'),
            activebackground=self.theme.get('accent', '#66aaff'),
            activeforeground='#000000',
            font=(font_family, font_size),
            relief=tk.FLAT,
            width=3,
            command=self.add_task
        )
        self.add_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Scrollable task list
        self.canvas = tk.Canvas(
            self.main_frame,
            bg=bg,
            highlightthickness=0
        )
        self.scrollbar = ttk.Scrollbar(
            self.main_frame,
            orient=tk.VERTICAL,
            command=self.canvas.yview
        )

        self.task_list_frame = tk.Frame(self.canvas, bg=bg)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.task_list_frame,
            anchor=tk.NW
        )

        # Bind resize events
        self.task_list_frame.bind('<Configure>', self.on_frame_configure)
        self.canvas.bind('<Configure>', self.on_canvas_configure)

        # Initial task list population
        self.refresh_tasks()

    def on_frame_configure(self, event):
        """Update scroll region when frame size changes."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        """Update frame width when canvas resizes."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def setup_bindings(self):
        """Setup keyboard bindings."""
        self.root.bind('<Return>', self.on_enter)
        self.root.bind('<Up>', self.on_up)
        self.root.bind('<Down>', self.on_down)
        self.root.bind('<Delete>', self.on_delete)
        self.root.bind('<Control-d>', self.on_delete)
        self.root.bind('<Control-n>', self.focus_entry)
        self.root.bind('<Escape>', self.on_escape)

        # Mouse wheel scrolling
        self.canvas.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-1, 'units'))
        self.canvas.bind('<Button-5>', lambda e: self.canvas.yview_scroll(1, 'units'))

    def focus_entry(self, event=None):
        """Focus the input entry."""
        self.entry.focus_set()
        return 'break'

    def on_escape(self, event=None):
        """Handle escape key - clear entry or deselect."""
        if self.entry.get():
            self.entry.delete(0, tk.END)
        else:
            self.root.focus_set()
        return 'break'

    def on_enter(self, event=None):
        """Handle enter key - add task if in entry, otherwise select."""
        if self.entry.get():
            self.add_task()
        else:
            self.select_current()
        return 'break'

    def on_up(self, event=None):
        """Move selection up."""
        if self.task_frames and self.selected_index > 0:
            self.selected_index -= 1
            self.update_selection()
        return 'break'

    def on_down(self, event=None):
        """Move selection down."""
        if self.task_frames and self.selected_index < len(self.task_frames) - 1:
            self.selected_index += 1
            self.update_selection()
        return 'break'

    def on_delete(self, event=None):
        """Close highlighted task."""
        if self.task_frames:
            task_id = self.task_frames[self.selected_index]['task_id']
            self.close_task(task_id)
        return 'break'

    def update_selection(self):
        """Update visual selection highlighting."""
        bg = self.theme.get('bg', '#111111')
        select_bg = self.theme.get('select_bg', '#333333')

        for i, tf in enumerate(self.task_frames):
            if i == self.selected_index:
                tf['frame'].configure(bg=select_bg)
                tf['label'].configure(bg=select_bg)
            else:
                tf['frame'].configure(bg=bg)
                tf['label'].configure(bg=bg)

        # Scroll to make selected visible
        if self.task_frames:
            frame = self.task_frames[self.selected_index]['frame']
            self.canvas.update_idletasks()

            # Get frame position relative to canvas
            y = frame.winfo_y()
            height = frame.winfo_height()
            canvas_height = self.canvas.winfo_height()

            # Scroll if needed
            top = self.canvas.canvasy(0)
            bottom = top + canvas_height

            if y < top:
                self.canvas.yview_moveto(y / self.task_list_frame.winfo_height())
            elif y + height > bottom:
                self.canvas.yview_moveto((y + height - canvas_height) / self.task_list_frame.winfo_height())

    def add_task(self):
        """Add a new task from entry."""
        title = self.entry.get().strip()
        if not title:
            return

        try:
            self.st.add_task(title)
            self.entry.delete(0, tk.END)
            self.refresh_tasks()
        except ValueError as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def refresh_tasks(self):
        """Refresh the task list from state."""
        # Clear existing
        for tf in self.task_frames:
            tf['frame'].destroy()
        self.task_frames = []

        # Reload state
        self.st.reload()
        tasks = self.st.list_tasks()

        bg = self.theme.get('bg', '#111111')
        fg = self.theme.get('fg', '#e6e6e6')
        button_bg = self.theme.get('button_bg', '#222222')
        accent = self.theme.get('accent', '#66aaff')
        font_spec = self.theme.get('font', 'monospace 10')

        font_parts = font_spec.rsplit(' ', 1)
        font_family = font_parts[0] if len(font_parts) > 1 else 'monospace'
        font_size = int(font_parts[1]) if len(font_parts) > 1 else 10

        current_id = self.st.get_current_task_id()

        for task in tasks:
            frame = tk.Frame(self.task_list_frame, bg=bg)
            frame.pack(fill=tk.X, pady=1)

            # Title label (with current indicator)
            title = task['title']
            if len(title) > 50:
                title = title[:47] + "..."

            prefix = "▶ " if task['id'] == current_id else "   "
            label = tk.Label(
                frame,
                text=f"{prefix}{title}",
                bg=bg,
                fg=accent if task['id'] == current_id else fg,
                font=(font_family, font_size + 3),
                anchor=tk.W
            )
            label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))

            # Controls frame (can be hidden for confirm)
            controls = tk.Frame(frame, bg=bg)
            controls.pack(side=tk.RIGHT)

            # Window count
            if task['id'] == current_id:
                win_count = bspwm.get_window_count(ACTIVE_DESKTOP)
            else:
                desktop = bspwm.task_desktop_name(task['id'])
                win_count = bspwm.get_window_count(desktop) if bspwm.desktop_exists(desktop) else 0

            ctrl_font_size = font_size + 2

            win_label = tk.Label(
                controls,
                text=f"{win_count}w",
                bg=bg,
                fg='#666666',
                font=(font_family, ctrl_font_size)
            )
            win_label.pack(side=tk.LEFT, padx=(0, 12))

            # Move buttons
            up_btn = tk.Label(
                controls, text="↑", bg=bg, fg='#555555',
                font=(font_family, ctrl_font_size + 4), cursor="hand2"
            )
            up_btn.pack(side=tk.LEFT)
            up_btn.bind('<Button-1>', lambda e, tid=task['id']: self.move_task_up(tid))
            up_btn.bind('<Enter>', lambda e, w=up_btn: w.configure(fg='#888888'))
            up_btn.bind('<Leave>', lambda e, w=up_btn: w.configure(fg='#555555'))

            down_btn = tk.Label(
                controls, text="↓", bg=bg, fg='#555555',
                font=(font_family, ctrl_font_size + 4), cursor="hand2"
            )
            down_btn.pack(side=tk.LEFT, padx=(0, 12))
            down_btn.bind('<Button-1>', lambda e, tid=task['id']: self.move_task_down(tid))
            down_btn.bind('<Enter>', lambda e, w=down_btn: w.configure(fg='#888888'))
            down_btn.bind('<Leave>', lambda e, w=down_btn: w.configure(fg='#555555'))

            # Select button
            select_btn = tk.Label(
                controls,
                text="[Select]",
                bg=bg,
                fg='#888888',
                font=(font_family, ctrl_font_size),
                cursor="hand2"
            )
            select_btn.pack(side=tk.LEFT, padx=(0, 6))
            select_btn.bind('<Button-1>', lambda e, tid=task['id']: self.select_task(tid))
            select_btn.bind('<Enter>', lambda e, w=select_btn: w.configure(fg=accent))
            select_btn.bind('<Leave>', lambda e, w=select_btn: w.configure(fg='#888888'))

            # Close button
            close_btn = tk.Label(
                controls,
                text="[Close]",
                bg=bg,
                fg='#664444',
                font=(font_family, ctrl_font_size),
                cursor="hand2"
            )
            close_btn.pack(side=tk.LEFT, padx=(0, 5))
            close_btn.bind('<Button-1>', lambda e, tid=task['id']: self.close_task(tid))
            close_btn.bind('<Enter>', lambda e, w=close_btn: w.configure(fg='#aa4444'))
            close_btn.bind('<Leave>', lambda e, w=close_btn: w.configure(fg='#664444'))

            self.task_frames.append({
                'frame': frame,
                'label': label,
                'win_label': win_label,
                'controls': controls,
                'task_id': task['id']
            })

        # Clamp selection
        if self.selected_index >= len(self.task_frames):
            self.selected_index = max(0, len(self.task_frames) - 1)

        self.update_selection()

    def move_task_up(self, task_id: int):
        """Move a task up in the list."""
        self.st.move_task_up(task_id)
        self.refresh_tasks()

    def move_task_down(self, task_id: int):
        """Move a task down in the list."""
        self.st.move_task_down(task_id)
        self.refresh_tasks()

    def select_task(self, task_id: int):
        """Select a task and switch to active desktop."""
        monitor = self.st.get_setting('monitor')
        if not monitor:
            try:
                monitor = bspwm.get_focused_monitor()
                self.st.set_setting('monitor', monitor)
            except bspwm.BspwmError:
                messagebox.showerror("Error", "Could not determine monitor", parent=self.root)
                return

        old_task_id = self.st.get_current_task_id()

        try:
            bspwm.swap_task_windows(monitor, old_task_id, task_id)
            self.st.set_current_task_id(task_id)
            self.refresh_tasks()

            # Switch to active desktop
            bspwm.focus_desktop(ACTIVE_DESKTOP)
        except bspwm.BspwmError as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def select_current(self):
        """Select the currently highlighted task."""
        if self.task_frames:
            task_id = self.task_frames[self.selected_index]['task_id']
            self.select_task(task_id)

    def show_inline_confirm(self, task_id: int, message: str, on_confirm):
        """Show inline confirmation replacing task controls."""
        # Find the task frame
        tf = None
        for t in self.task_frames:
            if t['task_id'] == task_id:
                tf = t
                break
        if not tf:
            return

        # Cancel any existing confirm
        if hasattr(self, '_confirm_task_id') and self._confirm_task_id:
            self._cancel_confirm()

        self._confirm_task_id = task_id
        self._confirm_controls = tf['controls']
        self._confirm_callback = on_confirm

        # Hide controls
        tf['controls'].pack_forget()

        # Create confirm frame in its place
        bg = self.theme.get('bg', '#111111')
        fg = self.theme.get('fg', '#e6e6e6')

        self._confirm_frame = tk.Frame(tf['frame'], bg=bg)
        self._confirm_frame.pack(side=tk.RIGHT)

        msg_label = tk.Label(self._confirm_frame, text=message, bg=bg, fg='#ff6666',
                            font=(self.theme.get('font', 'monospace 10').rsplit(' ', 1)[0], 9))
        msg_label.pack(side=tk.LEFT, padx=(0, 8))

        yes_btn = tk.Label(self._confirm_frame, text="[Yes]", bg=bg, fg='#ff6666',
                          cursor="hand2")
        yes_btn.pack(side=tk.LEFT, padx=(0, 4))
        yes_btn.bind('<Button-1>', lambda e: self._do_confirm())
        yes_btn.bind('<Enter>', lambda e, w=yes_btn: w.configure(fg='#ff8888'))
        yes_btn.bind('<Leave>', lambda e, w=yes_btn: w.configure(fg='#ff6666'))

        no_btn = tk.Label(self._confirm_frame, text="[No]", bg=bg, fg='#888888',
                         cursor="hand2")
        no_btn.pack(side=tk.LEFT)
        no_btn.bind('<Button-1>', lambda e: self._cancel_confirm())
        no_btn.bind('<Enter>', lambda e, w=no_btn: w.configure(fg='#aaaaaa'))
        no_btn.bind('<Leave>', lambda e, w=no_btn: w.configure(fg='#888888'))

    def _cancel_confirm(self):
        """Cancel inline confirmation."""
        if hasattr(self, '_confirm_frame') and self._confirm_frame:
            self._confirm_frame.destroy()
            self._confirm_frame = None
        if hasattr(self, '_confirm_controls') and self._confirm_controls:
            self._confirm_controls.pack(side=tk.RIGHT)
        self._confirm_task_id = None

    def _do_confirm(self):
        """Execute confirmation callback."""
        callback = self._confirm_callback if hasattr(self, '_confirm_callback') else None
        self._cancel_confirm()
        if callback:
            callback()

    def close_task(self, task_id: int):
        """Close/remove a task with confirmation."""
        task = self.st.get_task(task_id)
        if not task:
            return

        current_id = self.st.get_current_task_id()
        window_count = 0

        if task_id == current_id:
            window_count = bspwm.get_window_count(ACTIVE_DESKTOP)
        else:
            desktop = bspwm.task_desktop_name(task_id)
            if bspwm.desktop_exists(desktop):
                window_count = bspwm.get_window_count(desktop)

        if window_count > 0:
            self.show_inline_confirm(
                task_id,
                f"Close {window_count}w?",
                lambda: self._do_close_task(task_id, current_id)
            )
            return

        self._do_close_task(task_id, current_id)

    def _do_close_task(self, task_id: int, current_id: int):
        try:
            # Close windows
            if task_id == current_id:
                bspwm.close_all_windows(ACTIVE_DESKTOP)
            else:
                desktop = bspwm.task_desktop_name(task_id)
                if bspwm.desktop_exists(desktop):
                    bspwm.close_all_windows(desktop)

            # Handle based on policy
            if self.cfg.close_policy == "archive":
                self.st.mark_done(task_id)
            else:
                self.st.remove_task(task_id)

            # Remove desktop
            bspwm.remove_task_desktop(task_id)

            # If we closed the current task, auto-select next one
            if task_id == current_id:
                remaining = self.st.list_tasks(include_done=False)
                if remaining:
                    next_task = remaining[0]
                    monitor = self.st.get_setting('monitor') or self.cfg.monitor
                    if monitor:
                        bspwm.swap_task_windows(monitor, None, next_task['id'])
                        self.st.set_current_task_id(next_task['id'])
                else:
                    self.st.set_current_task_id(None)

            self.refresh_tasks()
        except bspwm.BspwmError as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def _update_window_counts(self):
        """Update window count labels without full refresh."""
        current_id = self.st.get_current_task_id()
        for tf in self.task_frames:
            task_id = tf['task_id']
            if task_id == current_id:
                win_count = bspwm.get_window_count(ACTIVE_DESKTOP)
            else:
                desktop = bspwm.task_desktop_name(task_id)
                win_count = bspwm.get_window_count(desktop) if bspwm.desktop_exists(desktop) else 0
            tf['win_label'].configure(text=f"{win_count} win")

    def poll_state(self):
        """Poll state file for changes - only refresh if state changed."""
        try:
            import os
            state_file = self.st.state_file
            mtime = os.path.getmtime(state_file) if state_file.exists() else 0

            if not hasattr(self, '_last_mtime'):
                self._last_mtime = 0

            if mtime != self._last_mtime:
                self._last_mtime = mtime
                self.refresh_tasks()
            else:
                # Update current task indicator and window counts
                self._update_current_indicator()
                self._update_window_counts()
        except Exception:
            pass

        self.root.after(500, self.poll_state)

    def _update_current_indicator(self):
        """Update just the current task indicator without rebuilding."""
        try:
            self.st.reload()
            current_id = self.st.get_current_task_id()
            accent = self.theme.get('accent', '#66aaff')
            fg = self.theme.get('fg', '#e6e6e6')

            # Find index of current task and update selection to match
            for i, tf in enumerate(self.task_frames):
                task_id = tf['task_id']
                label = tf['label']
                # Get current text and strip any prefix (▶ or spaces)
                text = label.cget('text')
                if text.startswith('▶'):
                    text = text[2:]  # Remove "▶ "
                else:
                    text = text.lstrip()

                if task_id == current_id:
                    label.configure(text=f'▶ {text}', fg=accent)
                    self.selected_index = i
                else:
                    label.configure(text=f'   {text}', fg=fg)

            # Update visual selection
            self.update_selection()
        except Exception:
            pass

    def position_window(self):
        """Position window on tasks desktop."""
        # Get window ID and move to tasks desktop
        try:
            window_id = hex(self.root.winfo_id())
            bspwm.move_window(window_id, TASKS_DESKTOP)

            # Set tiled to maximize on the desktop
            bspwm.set_window_state(window_id, 'tiled')
        except Exception as e:
            print(f"[picker] Could not position window: {e}", file=sys.stderr)

    def run(self):
        """Start the picker."""
        self.root.mainloop()


def run_picker():
    """Entry point for picker UI."""
    picker = TaskPicker()
    picker.run()


if __name__ == '__main__':
    run_picker()
