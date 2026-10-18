-- 0002_add_automerge.sql
-- Add automerge flag to boards table for automated PR merging

ALTER TABLE boards ADD COLUMN automerge INTEGER NOT NULL DEFAULT 0;
