-- 0002_add_board_settings.sql
-- Add concurrency and memory settings columns to boards table

ALTER TABLE boards ADD COLUMN max_concurrent_running INTEGER NOT NULL DEFAULT 1;
ALTER TABLE boards ADD COLUMN auto_record_memory INTEGER NOT NULL DEFAULT 1;
ALTER TABLE boards ADD COLUMN additional_reviewer_usernames TEXT NOT NULL DEFAULT '[]';
