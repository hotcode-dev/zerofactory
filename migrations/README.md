# Zero Factory SQLite Database Migrations

This directory contains versioned SQLite database migrations for Zero Factory.

## How It Works

1. **Ordering**: Migrations are executed in alphabetical order based on their numerical prefix (e.g. `0001_`, `0002_`, `0003_`).
2. **Tracking**: Applied migrations are recorded in the `schema_migrations` table:
   ```sql
   CREATE TABLE schema_migrations (
       version TEXT PRIMARY KEY,
       applied_at INTEGER NOT NULL
   );
   ```
3. **Automatic Execution**: When Zero Factory starts (`init_db()`), any pending migrations are automatically discovered and executed within a transaction.
4. **Idempotency**: Statements such as `ALTER TABLE ... ADD COLUMN` are executed safely. If a column or index already exists, the runner ignores `duplicate column name` or `already exists` errors.

---

## Adding a New Migration

### 1. SQL Migration (`.sql`)

Create a new file in this directory following the `XXXX_<description>.sql` naming pattern:

Example: `0003_add_task_deadline.sql`

```sql
-- 0003_add_task_deadline.sql
-- Add deadline timestamp column to tasks table

ALTER TABLE tasks ADD COLUMN deadline INTEGER DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
```

### 2. Python Migration (`.py`)

If a migration requires data transformation or complex business logic beyond SQL DDL:

Example: `0004_backfill_metadata.py`

```python
# 0004_backfill_metadata.py
import json
import sqlite3

def up(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT id, metadata FROM tasks WHERE metadata IS NOT NULL")
    for task_id, raw_meta in cursor.fetchall():
        try:
            meta = json.loads(raw_meta or "{}")
            if "version" not in meta:
                meta["version"] = 1
                cursor.execute(
                    "UPDATE tasks SET metadata = ? WHERE id = ?",
                    (json.dumps(meta), task_id)
                )
        except Exception:
            pass
```

---

## Running Migrations Manually

### Check Migration Status
```bash
python3 -m migrations.runner --status
# Or via zerofactory CLI:
hermes zerofactory migrate --status
```

### Apply Pending Migrations
```bash
python3 -m migrations.runner
# Or via zerofactory CLI:
hermes zerofactory migrate
```
