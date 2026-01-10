#!/usr/bin/env python3
"""CLI entrypoint for taskwm - the 'tw' command."""

import argparse
import sys

from . import state, bspwm, config


def cmd_add(args):
    """Add a new task."""
    title = ' '.join(args.title) if isinstance(args.title, list) else args.title
    if not title.strip():
        print("Error: Task title cannot be empty", file=sys.stderr)
        return 1

    s = state.get_state()
    try:
        task_id = s.add_task(title)
        print(task_id)
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args):
    """List tasks."""
    s = state.get_state()
    tasks = s.list_tasks(include_done=args.all if hasattr(args, 'all') else False)

    for task in tasks:
        done_marker = "[done] " if task.get("done") else ""
        print(f"{task['id']}\t{done_marker}{task['title']}")

    return 0


def cmd_select(args):
    """Select a task (swap windows into active)."""
    s = state.get_state()
    cfg = config.get_config()

    try:
        task_id = int(args.id)
    except ValueError:
        print(f"Error: Invalid task ID: {args.id}", file=sys.stderr)
        return 1

    task = s.get_task(task_id)
    if not task:
        print(f"Error: Task {task_id} not found", file=sys.stderr)
        return 1

    if task.get("done"):
        print(f"Error: Task {task_id} is already done", file=sys.stderr)
        return 1

    # Get monitor from state cache or config
    monitor = s.get_setting('monitor') or cfg.monitor
    if not monitor:
        try:
            monitor = bspwm.get_focused_monitor()
            s.set_setting('monitor', monitor)
        except bspwm.BspwmError as e:
            print(f"Error: Could not determine monitor: {e}", file=sys.stderr)
            return 1

    old_task_id = s.get_current_task_id()

    try:
        bspwm.swap_task_windows(monitor, old_task_id, task_id)
        s.set_current_task_id(task_id)
        return 0
    except bspwm.BspwmError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_done(args):
    """Mark current task as done/close."""
    s = state.get_state()
    cfg = config.get_config()

    task_id = s.get_current_task_id()
    if task_id is None:
        print("Error: No active task", file=sys.stderr)
        return 1

    task = s.get_task(task_id)
    if not task:
        print(f"Error: Task {task_id} not found", file=sys.stderr)
        return 1

    # Check for windows in active
    window_count = bspwm.get_window_count('active')

    if window_count > 0 and not args.force:
        print(f"Error: {window_count} window(s) in active. Use -f to force close.", file=sys.stderr)
        return 1

    monitor = s.get_setting('monitor') or cfg.monitor
    if not monitor:
        monitor = bspwm.get_focused_monitor()

    try:
        # Close windows
        if window_count > 0:
            bspwm.close_all_windows('active', force=args.force)

        # Handle task based on close policy
        if cfg.close_policy == "archive":
            s.mark_done(task_id)
        else:
            s.remove_task(task_id)

        # Remove task desktop
        bspwm.remove_task_desktop(task_id)

        # Clear current task
        s.set_current_task_id(None)

        return 0
    except bspwm.BspwmError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_remove(args):
    """Remove a task."""
    s = state.get_state()

    try:
        task_id = int(args.id)
    except ValueError:
        print(f"Error: Invalid task ID: {args.id}", file=sys.stderr)
        return 1

    task = s.get_task(task_id)
    if not task:
        print(f"Error: Task {task_id} not found", file=sys.stderr)
        return 1

    # Check if this is the active task
    current_id = s.get_current_task_id()
    desktop_name = bspwm.task_desktop_name(task_id)

    # Check for windows
    window_count = 0
    if current_id == task_id:
        window_count = bspwm.get_window_count('active')
    elif bspwm.desktop_exists(desktop_name):
        window_count = bspwm.get_window_count(desktop_name)

    if window_count > 0 and not args.force:
        print(f"Error: Task has {window_count} window(s). Use -f to force remove.", file=sys.stderr)
        return 1

    try:
        # Close windows if any
        if window_count > 0:
            if current_id == task_id:
                bspwm.close_all_windows('active', force=args.force)
            else:
                bspwm.close_all_windows(desktop_name, force=args.force)

        # Remove task
        s.remove_task(task_id)

        # Remove task desktop
        bspwm.remove_task_desktop(task_id)

        return 0
    except bspwm.BspwmError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_current(args):
    """Print current task ID."""
    s = state.get_state()
    task_id = s.get_current_task_id()
    if task_id is not None:
        print(task_id)
    return 0


def cmd_title(args):
    """Print current task title."""
    s = state.get_state()
    title = s.get_current_title()
    print(title)
    return 0


def cmd_daemon(args):
    """Run the daemon."""
    from . import daemon
    return daemon.run_daemon()


def cmd_ui(args):
    """Start UI components for development."""
    from . import ui_picker, ui_bar
    import threading

    if args.picker:
        ui_picker.run_picker()
    elif args.bar:
        ui_bar.run_bar()
    else:
        # Start both
        bar_thread = threading.Thread(target=ui_bar.run_bar, daemon=True)
        bar_thread.start()
        ui_picker.run_picker()

    return 0


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog='tw',
        description='taskwm - Task-Centric Workspaces for bspwm'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # tw a "title" - add task
    add_parser = subparsers.add_parser('a', help='Add a new task')
    add_parser.add_argument('title', nargs='+', help='Task title')
    add_parser.set_defaults(func=cmd_add)

    # tw l - list tasks
    list_parser = subparsers.add_parser('l', help='List tasks')
    list_parser.add_argument('-a', '--all', action='store_true', help='Include done tasks')
    list_parser.set_defaults(func=cmd_list)

    # tw s <id> - select task
    select_parser = subparsers.add_parser('s', help='Select a task')
    select_parser.add_argument('id', help='Task ID')
    select_parser.set_defaults(func=cmd_select)

    # tw d - done/close current task
    done_parser = subparsers.add_parser('d', help='Mark current task done/close')
    done_parser.add_argument('-f', '--force', action='store_true', help='Force close windows')
    done_parser.set_defaults(func=cmd_done)

    # tw r <id> - remove task
    remove_parser = subparsers.add_parser('r', help='Remove a task')
    remove_parser.add_argument('id', help='Task ID')
    remove_parser.add_argument('-f', '--force', action='store_true', help='Force remove with windows')
    remove_parser.set_defaults(func=cmd_remove)

    # tw cur - print current task id
    cur_parser = subparsers.add_parser('cur', help='Print current task ID')
    cur_parser.set_defaults(func=cmd_current)

    # tw title - print current task title
    title_parser = subparsers.add_parser('title', help='Print current task title')
    title_parser.set_defaults(func=cmd_title)

    # tw daemon - run daemon
    daemon_parser = subparsers.add_parser('daemon', help='Run the background daemon')
    daemon_parser.set_defaults(func=cmd_daemon)

    # tw ui - start UI (dev mode)
    ui_parser = subparsers.add_parser('ui', help='Start UI components')
    ui_parser.add_argument('--picker', action='store_true', help='Start only picker')
    ui_parser.add_argument('--bar', action='store_true', help='Start only bar')
    ui_parser.set_defaults(func=cmd_ui)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
