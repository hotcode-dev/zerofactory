"""Kanban Dispatcher Plugin for Zero Factory."""

import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path.home() / ".hermes" / "kanban.db"

def run_dispatch_cycle():
    """Run a single dispatch cycle to auto-assign tasks and unblock dependencies."""
    if not DB_PATH.exists():
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Unblock tasks whose parents are all 'done'
            cursor.execute("""
                SELECT id, title FROM tasks
                WHERE status = 'blocked'
                AND id IN (SELECT child_id FROM task_links)
                AND NOT EXISTS (
                    SELECT 1 FROM task_links tl
                    JOIN tasks pt ON pt.id = tl.parent_id
                    WHERE tl.child_id = tasks.id AND pt.status != 'done'
                )
            """)
            to_unblock = cursor.fetchall()
            for row in to_unblock:
                print(f"[kanban-dispatcher] Unblocking task {row['id']}: {row['title']}")
                cursor.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (row['id'],))
            
            # 2. Auto-Assign Ready tasks
            cursor.execute("""
                SELECT id, title FROM tasks
                WHERE status = 'ready' AND (assignee IS NULL OR assignee = '' OR assignee = 'unassigned')
            """)
            unassigned = cursor.fetchall()
            for row in unassigned:
                title = row['title'].lower()
                if "[researcher]" in title:
                    assignee = "researcher"
                elif "[qa]" in title:
                    assignee = "qa"
                elif "[scribe]" in title:
                    assignee = "scribe"
                elif "[reviewer]" in title:
                    assignee = "reviewer"
                else:
                    assignee = "builder" # default to builder
                
                print(f"[kanban-dispatcher] Auto-assigning task {row['id']} to {assignee}")
                cursor.execute("UPDATE tasks SET assignee = ? WHERE id = ?", (assignee, row['id']))
            
            conn.commit()
    except Exception as e:
        print(f"[kanban-dispatcher] Error in dispatch cycle: {e}")

def kanban_dispatcher_loop():
    """Background loop."""
    while True:
        run_dispatch_cycle()
        time.sleep(30)

def register(ctx):
    """Register the plugin hooks and commands."""
    
    def on_startup():
        print("[kanban-dispatcher] Starting background daemon thread...")
        thread = threading.Thread(target=kanban_dispatcher_loop, daemon=True)
        thread.start()

    ctx.register_hook("gateway:startup", on_startup)

    def cmd_setup(parser):
        pass
        
    def cmd_run(args):
        print("Running kanban-dispatcher cycle once...")
        run_dispatch_cycle()
        print("Done.")
        
    ctx.register_cli_command(
        name="kanban-dispatch",
        help="Manually trigger the kanban auto-assign loop",
        setup_fn=cmd_setup,
        handler_fn=cmd_run
    )
