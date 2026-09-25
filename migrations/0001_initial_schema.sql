-- 0001_initial_schema.sql
-- Zero Factory core schema initialization

CREATE TABLE IF NOT EXISTS boards (
    slug TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    git_url TEXT DEFAULT '',
    target_branch TEXT NOT NULL DEFAULT '',
    max_concurrent_running INTEGER NOT NULL DEFAULT 1,
    auto_record_memory INTEGER NOT NULL DEFAULT 1,
    additional_reviewer_usernames TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    board_slug TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'triage',
    assignee TEXT NOT NULL DEFAULT 'unassigned',
    priority TEXT NOT NULL DEFAULT 'P2',
    workspace_path TEXT,
    workspace_kind TEXT DEFAULT 'worktree',
    branch_name TEXT,
    pr_url TEXT,
    tenant TEXT DEFAULT '',
    skills TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_links (
    parent_id TEXT NOT NULL,
    child_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (parent_id, child_id),
    FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (child_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT DEFAULT '',
    created_at INTEGER NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS board_memories (
    id TEXT PRIMARY KEY,
    board_slug TEXT NOT NULL,
    task_id TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    author TEXT DEFAULT 'agent',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_board_status ON tasks(board_slug, status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_links_parent ON task_links(parent_id);
CREATE INDEX IF NOT EXISTS idx_links_child ON task_links(child_id);
CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_task ON task_activity(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_board ON board_memories(board_slug, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_category ON board_memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_board_content ON board_memories(board_slug, content);
CREATE INDEX IF NOT EXISTS idx_activity_created ON task_activity(created_at, id);
CREATE INDEX IF NOT EXISTS idx_activity_actor ON task_activity(actor, created_at);
