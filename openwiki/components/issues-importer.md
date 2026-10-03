---
type: subsystem
title: External Issue Import (GitHub & Jira)
description: The issues/ subsystem that deterministically ingests external tracker issues (GitHub via gh CLI, Jira) into Kanban tasks — label-driven priority/category inference, deterministic task IDs and dedup keys, board resolution, and PR linkage back to the source issue.
tags: [issues-import, github, jira, external-issue-tracker, dedup, kanban-import]
verified:
  - by: openwiki/0.6.0
    at: 2026-10-03T01:15:19.967Z
sources:
  - id: openwiki-source-4942bcbe129130ccad2b7e2a
    resource: repo://__init__.py
  - id: openwiki-source-c705147b9966f3d6f300034a
    resource: repo://dashboard/routes/tasks.py
  - id: openwiki-source-9f9b3c9d5afeac588f3cdae1
    resource: repo://dispatcher/scheduler.py
  - id: openwiki-source-de41792489ddc53f78c74500
    resource: repo://issues/base.py
  - id: openwiki-source-77f07e5fa775445ef0704ec6
    resource: repo://issues/github.py
  - id: openwiki-source-992af5f6e480f39b3a3a184e
    resource: repo://issues/importer.py
  - id: openwiki-source-c6c907af11cbf112e6ff56ce
    resource: repo://issues/jira.py
  - id: openwiki-source-6b26d87a1c92fff15057316c
    resource: repo://tests/unit/issues/test_issues.py
generated: { by: "hermes", at: "2026-10-03T01:15:19.967Z" }
---

# External Issue Import (GitHub & Jira)

The `issues/` package gives the factory a single, deterministic entry point from
external issue trackers into the Kanban board. A GitHub or Jira issue is fetched,
normalized into an `ExternalIssue`, and materialized as a Kanban task — so a real
world bug report can flow through the same builder → reviewer pipeline as any
hand-typed ticket, and the PR that fixes it links back to the source issue.

## The `ExternalIssue` model

`ExternalIssue` (`repo://issues/base.py#L32-L46`) is the tracker-agnostic
dataclass: `source` (`github`/`jira`), `id`, display `key` (`#42`, `PROJ-123`),
title, body, url, author, labels, and the owning `repo_or_project`. Two derived
identities make ingestion idempotent across repeated runs:

- **dedup key** — `to_dedup_key()` yields `issue:<source>:<repo_lower>:<id>`
  (`repo://issues/base.py#L48-L56`), stored as the task's `dedup_key` so a
  re-import of the same issue resolves to the existing task.
- **task id** — `to_task_id(board_slug)` derives a stable id from the board code
  (up to 3 initials) + source + sanitized issue id, e.g. board
  `hotcode-dev-zerofactory` + GitHub `#42` → `zf-hdz-gh42`
  (`repo://issues/base.py#L58-L78`). Because the id is a pure function of
  board + source + issue, imports are deterministic and repeat-safe.

**Label inference** is deterministic and evaluated in order:
`infer_priority()` maps labels to `P0` (critical/blocker/security/hotfix),
`P1` (high/major/bug), `P3` (low/trivial/nice-to-have), defaulting to `P2`
(`repo://issues/base.py#L80-L90`); `infer_category()` maps labels to
`security`, `performance`, `bug-fix`, `refactoring`, `documentation`,
`testing`, or `config`, defaulting to `bug-fix`
(`repo://issues/base.py#L92-L99`). Both are overridable by explicit
`--priority` / task fields at import time.

## Tracker clients

Both clients implement `BaseIssueClient` (`repo://issues/base.py#L145-L156`)
(`fetch_issue`, `test_connection`):

- **`GitHubIssueClient`** (`repo://issues/github.py#L64-L166`) — fetches via the
  authenticated `gh` CLI (`gh auth status` for `test_connection`).
  `parse_github_issue_ref` accepts a bare number, `owner/repo#42`, or a full
  issue URL.
- **`JiraIssueClient`** (`repo://issues/jira.py#L68-L112`) — accepts a
  `PROJ-123`-style key (optionally prefixed with a project) and parses issue
  payloads; live REST fetching is gated on `JIRA_BASE_URL` + `JIRA_API_TOKEN`
  and raises `NotImplementedError` until that integration lands, while
  `mock_data` payloads are parsed for tests/webhooks.

## The import flow

`import_external_issue` (`repo://issues/importer.py#L98-L178`) is the single
entry point:

1. **Board resolution** — `resolve_board_for_issue`
   (`repo://issues/importer.py#L30-L96`) picks the target board: an explicit
   valid `board_slug` wins, then a match between the issue's
   `repo_or_project` and each board's `git_url`/slug, then the current working
   directory's `git remote origin` against board URLs; it falls back to the
   board slug argument or the default board.
2. **Deterministic identity** — task id + dedup key from the `ExternalIssue`
   methods above; priority/category inferred unless overridden.
3. **Task creation** — builds a `TaskCreate` with an explicit `task_id` and
   merged `metadata` (including `external_issue`, `dedup_key`, `category`),
   tags (`issue:github`, `github-42`, `cat:bug-fix`, sanitized label tags), and
   a `[<key>] <title>` title. The dashboard create-task endpoint honors the
   explicit `task_id`: if the row already exists it returns a `duplicate`
   response with the current status instead of inserting
   (`repo://dashboard/routes/tasks.py#L267-L284`,
   `repo://dashboard/models.py#L130-L135`).
4. **Result** — the caller receives `{ok, id, duplicate, board_slug, status,
   priority, category, source, issue_key, issue_url}` so the CLI can report a
   "Duplicate Skipped" cleanly.

## CLI surface

`hermes zerofactory import-gh-issue <issue>` registers the command in the
plugin shell (`repo://__init__.py#L283-L316`): `<issue>` may be a number,
`#42`, a full GitHub URL, or `owner/repo#42`; `--repo` (inferred from the
board `git_url` or git remote when omitted), `--board`, `--status` (default
`triage`), `--priority`, `--assignee` (default `unassigned`), and `--actor`
round out the flags. The handler fetches via `GitHubIssueClient` and prints the
imported task id, board, status, priority, and URL
(`repo://__init__.py#L604-L640`).

## Downstream: PR linkage

Tasks carrying `external_issue` metadata are closed the loop on the source
tracker: when the dispatcher opens the PR for such a task, the body appends
`Fixes #<n>` (GitHub) or `Resolves: <KEY>` (Jira)
(`repo://dispatcher/scheduler.py#L1277-L1295`), so a human merge on GitHub also
closes or references the original issue.

## Tests

`tests/unit/issues/test_issues.py` covers ref parsing, priority/category
inference, task-id and dedup-key derivation, board resolution, and import
behavior (16 tests, part of the `tests/unit` tier; see
[Conventions](/openwiki/conventions.md#tests-pytest-three-tiers)).

## Relationships

Upstream: external trackers and the `gh` CLI. Downstream: the Kanban board
(substrate in [Architecture](/openwiki/architecture.md)) — imported tasks flow
through the [Dispatch Engine](/openwiki/components/dispatcher.md) unchanged.
The CLI is documented in [Quickstart](/openwiki/quickstart.md).
