"""Kanban Dispatcher Plugin for Zero Factory."""

import sqlite3
import threading
import time
import os
import subprocess
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
            
            # 2. Auto-promote Todo to Ready (skip human planning review)
            cursor.execute("SELECT id FROM tasks WHERE status = 'todo'")
            todos = cursor.fetchall()
            for row in todos:
                print(f"[kanban-dispatcher] Auto-promoting Todo task {row['id']} to Ready")
                cursor.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (row['id'],))

            # 3. Auto-Assign Ready tasks and setup git worktree
            cursor.execute("""
                SELECT id, title, workspace_path, assignee FROM tasks
                WHERE status = 'ready'
            """)
            ready_tasks = cursor.fetchall()
            for row in ready_tasks:
                task_id = row['id']
                title = row['title'].lower()
                assignee = row['assignee']
                workspace_path = row['workspace_path']
                
                # Assign if unassigned
                if not assignee or assignee == 'unassigned':
                    if "[researcher]" in title:
                        assignee = "researcher"
                    elif "[qa]" in title:
                        assignee = "qa"
                    elif "[scribe]" in title:
                        assignee = "scribe"
                    elif "[reviewer]" in title:
                        assignee = "reviewer"
                    elif "[builder]" in title:
                        assignee = "builder"
                    elif "[orchestrator]" in title:
                        assignee = "orchestrator"
                    else:
                        assignee = "builder" # Default to builder
                    
                    print(f"[kanban-dispatcher] Auto-assigning task {task_id} to {assignee}")
                    cursor.execute("UPDATE tasks SET assignee = ? WHERE id = ?", (assignee, task_id))
                
                # Create programmatic worktree if not set
                if not workspace_path:
                    # Resolve to absolute path for Hermes
                    reponame = Path(os.getcwd()).name
                    worktree_dir = Path(os.getcwd()).parent / f"{reponame}-worktrees" / task_id
                    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        print(f"[kanban-dispatcher] Creating git worktree for task {task_id} at {worktree_dir}")
                        subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", f"task/{task_id}", "origin/main"], check=True, cwd=os.getcwd())
                        cursor.execute("UPDATE tasks SET workspace_kind = 'path', workspace_path = ? WHERE id = ?", (str(worktree_dir), task_id))
                    except subprocess.CalledProcessError as e:
                        print(f"[kanban-dispatcher] Failed to create worktree for task {task_id}: {e}")

            # 4. Handle Blocked tasks (Programmatic PRs and Reviewer Loop)
            cursor.execute("""
                SELECT id, title, workspace_path, assignee FROM tasks
                WHERE status = 'blocked' AND workspace_path IS NOT NULL
            """)
            blocked_tasks = cursor.fetchall()
            for row in blocked_tasks:
                task_id = row['id']
                title = row['title']
                workspace_path = row['workspace_path']
                assignee = row['assignee']
                
                if assignee != 'reviewer':
                    # Author finished coding -> Push, PR, and Route to Reviewer
                    print(f"[kanban-dispatcher] Programmatically opening/updating PR for task {task_id}")
                    try:
                        # Git commit and push
                        subprocess.run(["git", "add", "."], check=True, cwd=workspace_path)
                        # Ignore error if nothing to commit
                        subprocess.run(["git", "commit", "-m", f"Complete task {task_id}"], cwd=workspace_path)
                        subprocess.run(["git", "push", "-u", "origin", f"task/{task_id}"], check=True, cwd=workspace_path)
                        
                        # Create PR if title doesn't have [PR Opened]
                        if "[PR Opened" not in title:
                            pr_title = f"Task {task_id}: {title}"
                            pr_body = f"Automated PR for task {task_id}"
                            subprocess.run(["gh", "pr", "create", "--title", pr_title, "--body", pr_body], cwd=workspace_path)
                        
                        # Cleanup worktree
                        subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=True, cwd=os.getcwd())
                        
                        # Route to Reviewer
                        import re
                        new_title = title
                        if not re.search(r'\[PR Opened by .*?\]', title):
                            new_title = f"{title} [PR Opened by {assignee}]"
                        cursor.execute("UPDATE tasks SET title = ?, workspace_path = NULL, workspace_kind = 'scratch', assignee = 'reviewer', status = 'ready' WHERE id = ?", (new_title, task_id))
                        
                    except subprocess.CalledProcessError as e:
                        print(f"[kanban-dispatcher] Failed to process blocked task {task_id} (Author): {e}")

                else:
                    # Reviewer finished reviewing -> Check GitHub PR State
                    print(f"[kanban-dispatcher] Checking Reviewer decision for task {task_id}")
                    try:
                        # Cleanup Reviewer's worktree
                        subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=True, cwd=os.getcwd())
                        
                        # Check PR State
                        import json
                        import re
                        result = subprocess.run(["gh", "pr", "view", f"task/{task_id}", "--json", "reviewDecision"], capture_output=True, text=True, cwd=os.getcwd())
                        if result.returncode == 0:
                            data = json.loads(result.stdout)
                            decision = data.get("reviewDecision")
                            
                            if decision == "CHANGES_REQUESTED":
                                print(f"[kanban-dispatcher] Changes requested for task {task_id}. Routing back to author.")
                                # Find original author from title
                                match = re.search(r'\[PR Opened by (.*?)\]', title)
                                prev_author = match.group(1) if match else 'builder'
                                
                                cursor.execute("UPDATE tasks SET workspace_path = NULL, workspace_kind = 'scratch', assignee = ?, status = 'ready' WHERE id = ?", (prev_author, task_id))
                            
                            elif decision == "APPROVED":
                                print(f"[kanban-dispatcher] Task {task_id} approved. Sending to Human Review.")
                                new_title = f"{title} [Human Review]" if "[Human Review]" not in title else title
                                cursor.execute("UPDATE tasks SET title = ?, workspace_path = NULL, workspace_kind = 'scratch' WHERE id = ?", (new_title, task_id))
                                
                            else:
                                print(f"[kanban-dispatcher] Task {task_id} reviewed but no decision found. Bouncing back to reviewer.")
                                cursor.execute("UPDATE tasks SET workspace_path = NULL, workspace_kind = 'scratch', status = 'ready' WHERE id = ?", (task_id,))
                        else:
                            print(f"[kanban-dispatcher] Could not fetch PR state for task {task_id}: {result.stderr}")
                            
                    except subprocess.CalledProcessError as e:
                        print(f"[kanban-dispatcher] Failed to process blocked task {task_id} (Reviewer): {e}")
            
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
