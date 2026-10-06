-- 0004_migrate_ready_to_todo.sql
-- Retire the legacy 'ready' task status (its Kanban column was removed).
-- 'ready' was a redundant alias of 'todo' claimed by the same dispatcher query;
-- stranded rows are folded into 'todo' so they remain claimable instead of being
-- silently orphaned.

INSERT INTO task_activity (task_id, actor, action, details, created_at)
SELECT id, 'dispatcher', 'migrate', 'Status ready migrated to todo (ready column removed)', CAST(strftime('%s', 'now') AS INTEGER)
FROM tasks WHERE status = 'ready';

UPDATE tasks SET status = 'todo' WHERE status = 'ready';
