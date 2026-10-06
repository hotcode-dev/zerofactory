-- 0005_running_awaiting_pr.sql
-- 'done' is strictly terminal: the deterministic packaging phase (precommit ->
-- commit -> push -> PR -> reviewer) runs while the task is still 'running'.
-- In-flight rows parked as done+awaiting_pr are moved back to 'running' so the
-- dispatcher packages them instead of finalizing them as terminal.

UPDATE tasks SET status = 'running'
WHERE status = 'done' AND metadata LIKE '%"awaiting_pr": true%';
