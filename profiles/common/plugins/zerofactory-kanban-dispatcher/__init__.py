"""Kanban Dispatcher Plugin for Zero Factory."""

import sqlite3
import threading
import time
import os
import subprocess
from pathlib import Path

def get_all_kanban_dbs():
    dbs = []
    default_db = Path.home() / ".hermes" / "kanban.db"
    if default_db.exists():
        dbs.append(default_db)
        
    boards_dir = Path.home() / ".hermes" / "kanban" / "boards"
    if boards_dir.exists():
        for board in boards_dir.iterdir():
            if board.is_dir():
                board_db = board / "kanban.db"
                if board_db.exists():
                    dbs.append(board_db)
    return dbs

def run_dispatch_cycle(db_path):
    """Run a single dispatch cycle to auto-assign tasks and unblock dependencies."""
    if not db_path.exists():
        return

    try:
        with sqlite3.connect(db_path) as conn:
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
                print(f"[zerofactory-kanban-dispatcher] Unblocking task {row['id']}: {row['title']}")
                cursor.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (row['id'],))
            
            # 2. Auto-promote Todo to Ready (WIP Limit enforced)
            MAX_ACTIVE_TASKS = 3
            
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('ready', 'in progress')")
            active_count = cursor.fetchone()[0]
            
            if active_count < MAX_ACTIVE_TASKS:
                limit = MAX_ACTIVE_TASKS - active_count
                cursor.execute("SELECT id FROM tasks WHERE status = 'todo' ORDER BY priority DESC LIMIT ?", (limit,))
                todos = cursor.fetchall()
                for row in todos:
                    print(f"[zerofactory-kanban-dispatcher] Auto-promoting Todo task {row['id']} to Ready (WIP Slot Available)")
                    cursor.execute("UPDATE tasks SET status = 'ready' WHERE id = ?", (row['id'],))

            # 3. Auto-Assign Ready tasks and setup git worktree
            cursor.execute("""
                SELECT id, title, workspace_path, assignee, tenant FROM tasks
                WHERE status = 'ready'
            """)
            ready_tasks = cursor.fetchall()
            for row in ready_tasks:
                task_id = row['id']
                title = row['title'] or ""
                assignee = row['assignee']
                workspace_path = row['workspace_path']
                tenant = row['tenant']
                
                # Sanitize assignee - protect against LLM hallucination (e.g. 'researcher-a')
                valid_profiles = ('builder', 'reviewer', 'qa', 'orchestrator')
                
                # Assign if unassigned or invalid
                if not assignee or assignee == 'unassigned' or assignee not in valid_profiles:
                    if "[qa]" in title:
                        assignee = "qa"
                    elif "[reviewer]" in title:
                        assignee = "reviewer"
                    elif "[builder]" in title:
                        assignee = "builder"
                    elif "[orchestrator]" in title:
                        assignee = "orchestrator"
                    else:
                        assignee = "builder" # Default to builder
                    
                    print(f"[zerofactory-kanban-dispatcher] Auto-assigning task {task_id} to {assignee} and clearing hallucinated skills")
                    cursor.execute("UPDATE tasks SET assignee = ?, skills = '[]' WHERE id = ?", (assignee, task_id))
                
                # Create programmatic worktree if not set
                if not workspace_path:
                    # Resolve to repository based on tenant
                    if tenant and tenant.lower() != 'default':
                        tenant_path = Path(os.path.expanduser(tenant))
                        if tenant_path.is_absolute():
                            repo_path = tenant_path
                            reponame = tenant_path.name
                        else:
                            reponame = tenant
                            repo_path = Path(os.getcwd()).parent / reponame
                    else:
                        if "boards" in db_path.parts:
                            reponame = db_path.parent.name
                        else:
                            reponame = Path(os.getcwd()).name
                        repo_path = Path(os.getcwd()).parent / reponame
                        
                    if not repo_path.exists():
                        repo_path = Path(os.getcwd())
                        reponame = repo_path.name
                        
                    worktree_dir = repo_path.parent / f"{reponame}-worktrees" / task_id
                    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        branch_name = f"task/{task_id}"
                        # Check if branch exists locally in the target repo
                        res = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], cwd=repo_path)
                        if res.returncode == 0:
                            print(f"[zerofactory-kanban-dispatcher] Creating git worktree for existing branch {branch_name} at {worktree_dir}")
                            subprocess.run(["git", "worktree", "add", str(worktree_dir), branch_name], check=True, cwd=repo_path)
                        else:
                            print(f"[zerofactory-kanban-dispatcher] Creating new git worktree branch {branch_name} at {worktree_dir}")
                            subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, "origin/main"], check=True, cwd=repo_path)
                        cursor.execute("UPDATE tasks SET workspace_kind = 'dir', workspace_path = ? WHERE id = ?", (str(worktree_dir), task_id))
                    except subprocess.CalledProcessError as e:
                        print(f"[zerofactory-kanban-dispatcher] Failed to create worktree for task {task_id} in {repo_path}: {e}")

            # 4. Handle Blocked tasks (Programmatic PRs and Reviewer Loop)
            cursor.execute("""
                SELECT id, title, workspace_path, assignee, tenant FROM tasks
                WHERE status = 'blocked' AND workspace_path IS NOT NULL
            """)
            blocked_tasks = cursor.fetchall()
            for row in blocked_tasks:
                task_id = row['id']
                title = row['title']
                workspace_path = row['workspace_path']
                assignee = row['assignee']
                tenant = row['tenant']
                
                # Resolve to repository based on tenant
                if tenant and tenant.lower() != 'default':
                    tenant_path = Path(os.path.expanduser(tenant))
                    if tenant_path.is_absolute():
                        repo_path = tenant_path
                        reponame = tenant_path.name
                    else:
                        reponame = tenant
                        repo_path = Path(os.getcwd()).parent / reponame
                else:
                    if "boards" in db_path.parts:
                        reponame = db_path.parent.name
                    else:
                        reponame = Path(os.getcwd()).name
                    repo_path = Path(os.getcwd()).parent / reponame
                    
                if not repo_path.exists():
                    repo_path = Path(os.getcwd())
                    reponame = repo_path.name
                
                if assignee not in ('reviewer', 'qa'):
                    # Author finished coding -> Push, PR, and Route to QA
                    print(f"[zerofactory-kanban-dispatcher] Programmatically opening/updating PR for task {task_id}")
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
                        subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=True, cwd=repo_path)
                        
                        # Route to QA first
                        import re
                        new_title = title
                        if not re.search(r'\[PR Opened by .*?\]', title):
                            new_title = f"{title} [PR Opened by {assignee}]"
                        cursor.execute("UPDATE tasks SET title = ?, workspace_path = NULL, workspace_kind = 'scratch', assignee = 'qa', status = 'ready' WHERE id = ?", (new_title, task_id))
                        
                    except subprocess.CalledProcessError as e:
                        print(f"[zerofactory-kanban-dispatcher] Failed to process blocked task {task_id} (Author): {e}")

                else:
                    # Reviewer finished reviewing -> Check GitHub PR State
                    print(f"[zerofactory-kanban-dispatcher] Checking Reviewer decision for task {task_id}")
                    try:
                        # Cleanup Reviewer's worktree
                        subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=True, cwd=repo_path)
                        
                        # Check PR State
                        import json
                        import re
                        result = subprocess.run(["gh", "pr", "view", f"task/{task_id}", "--json", "reviewDecision,state"], capture_output=True, text=True, cwd=repo_path)
                        if result.returncode == 0:
                            data = json.loads(result.stdout)
                            pr_state = data.get("state")
                            decision = data.get("reviewDecision")
                            
                            if pr_state == "MERGED":
                                print(f"[zerofactory-kanban-dispatcher] PR for task {task_id} was MERGED by human. Marking task as done.")
                                cursor.execute("UPDATE tasks SET status = 'done', workspace_path = NULL, workspace_kind = 'scratch' WHERE id = ?", (task_id,))
                                continue
                                
                            if decision == "CHANGES_REQUESTED":
                                print(f"[zerofactory-kanban-dispatcher] Changes requested by {assignee} for task {task_id}. Routing back to author and lowering priority.")
                                # Find original author from title
                                match = re.search(r'\[PR Opened by (.*?)\]', title)
                                prev_author = match.group(1) if match else 'builder'
                                
                                cursor.execute("UPDATE tasks SET priority = priority - 1, workspace_path = NULL, workspace_kind = 'scratch', assignee = ?, status = 'ready' WHERE id = ?", (prev_author, task_id))
                            
                            elif decision == "APPROVED":
                                if assignee == 'qa':
                                    print(f"[zerofactory-kanban-dispatcher] QA approved task {task_id}. Routing to Reviewer.")
                                    cursor.execute("UPDATE tasks SET workspace_path = NULL, workspace_kind = 'scratch', assignee = 'reviewer', status = 'ready' WHERE id = ?", (task_id,))
                                else:
                                    print(f"[zerofactory-kanban-dispatcher] Reviewer approved task {task_id}. Sending to Human Review.")
                                    new_title = f"{title} [Human Review]" if "[Human Review]" not in title else title
                                    cursor.execute("UPDATE tasks SET title = ?, workspace_path = NULL, workspace_kind = 'scratch' WHERE id = ?", (new_title, task_id))
                                
                            else:
                                print(f"[zerofactory-kanban-dispatcher] Task {task_id} reviewed by {assignee} but no decision found. Bouncing back.")
                                cursor.execute("UPDATE tasks SET workspace_path = NULL, workspace_kind = 'scratch', status = 'ready' WHERE id = ?", (task_id,))
                        else:
                            print(f"[zerofactory-kanban-dispatcher] Could not fetch PR state for task {task_id}: {result.stderr}")
                            
                    except subprocess.CalledProcessError as e:
                        print(f"[zerofactory-kanban-dispatcher] Failed to process blocked task {task_id} (Reviewer): {e}")
            
            conn.commit()
    except Exception as e:
        print(f"[zerofactory-kanban-dispatcher] Error in dispatch cycle: {e}")

def kanban_dispatcher_loop():
    """Background loop."""
    while True:
        for db in get_all_kanban_dbs():
            run_dispatch_cycle(db)
        time.sleep(30)

def register(ctx):
    """Register the plugin hooks and commands."""
    
    def on_startup():
        print("[zerofactory-kanban-dispatcher] Starting background daemon thread...")
        thread = threading.Thread(target=kanban_dispatcher_loop, daemon=True)
        thread.start()

    ctx.register_hook("gateway:startup", on_startup)

    def cmd_setup(parser):
        pass
        
    def cmd_run(args):
        print("Running zerofactory-kanban-dispatcher cycle once...")
        for db in get_all_kanban_dbs():
            print(f"Processing DB: {db}")
            run_dispatch_cycle(db)
        print("Done.")
        
    ctx.register_cli_command(
        name="zerofactory-kanban-dispatch",
        help="Manually trigger the kanban auto-assign loop",
        setup_fn=cmd_setup,
        handler_fn=cmd_run
    )
