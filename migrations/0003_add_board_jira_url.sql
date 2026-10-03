-- 0003_add_board_jira_url.sql
-- Add jira_url column to boards table for optional Jira Cloud link

ALTER TABLE boards ADD COLUMN jira_url TEXT NOT NULL DEFAULT '';
