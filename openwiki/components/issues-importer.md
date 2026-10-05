---
type: subsystem
title: External Issue Import (GitHub & Jira)
description: The issues/ subsystem that deterministically ingests external tracker issues (GitHub via gh CLI, Jira Cloud via REST) into Kanban tasks — label-driven priority/category/type inference, deterministic task IDs and dedup keys, board resolution, and PR linkage back to the source issue; plus the dashboard endpoints that drive synchronization/import and the task-based GitHub issues setup flow (P0 zf-builder task, align-mode template generator).
tags: [issues-import, github, jira, external-issue-tracker, dedup, kanban-import, gh-issues-setup]
sources:
  - id: openwiki-source-4942bcbe129130ccad2b7e2a
    resource: repo://__init__.py
  - id: openwiki-source-4751ad71b24eb2ac313122ba
    resource: repo://dashboard/gh_issues_service.py
  - id: openwiki-source-51d54395961048122dcc244f
    resource: repo://dashboard/routes/boards.py
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
generated: { by: "hermes", at: "2026-10-05T10:11:27.384Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-10-05T10:11:27.384Z
---

# External Issue Import (GitHub & Jira)

The `issues/` package gives the factory a single, deterministic entry point from
external issue trackers into the Kanban board. A GitHub or Jira issue is fetched,
normalized into an `ExternalIssue`, and materialized as a Kanban task — so a real
world bug report can flow through the same builder → reviewer pipeline as any
hand-typed ticket, and the PR that fixes it links back to the source issue.

## The `ExternalIssue` model

`ExternalIssue` (`repo://issues/base.py#L65-L80`) is the tracker-agnostic
dataclass: `source` (`github`/`jira`), `id`, display `key` (`#42`, `PROJ-123`),
title, body, url, author, labels, and the owning `repo_or_project`. Two derived
identities make ingestion idempotent across repeated runs:

- **dedup key** — `to_dedup_key()` yields `issue:<source>:<repo_lower>:<id>`
  (`repo://issues/base.py#L82-L90`), stored as the task's `dedup_key` so a
  re-import of the same issue resolves to the existing task.
- **task id** — `to_task_id(board_slug)` derives a stable id from the board code
  (up to 3 initials) + source + sanitized issue id, e.g. board
  `hotcode-dev-zerofactory` + GitHub `#42` → `zf-hdz-gh42`
  (`repo://issues/base.py#L92-L112`). Because the id is a pure function of
  board + source + issue, imports are deterministic and repeat-safe.

**Label inference** is deterministic and evaluated in order:
`infer_priority()` maps labels to `P0` (critical/blocker/security/hotfix),
`P1` (high/major/bug), `P3` (low/trivial/nice-to-have), defaulting to `P2`
(`repo://issues/base.py#L161-L171`); `infer_category()` maps labels to
`security`, `performance`, `bug-fix`, `refactoring`, `documentation`,
`testing`, or `config`, defaulting to `feature` when the issue type is a
feature, else `bug-fix` (`repo://issues/base.py#L173-L182`).
`infer_issue_type()` (`repo://issues/base.py#L114-L147`) infers `bug`/`feature`
from raw tracker fields (e.g. Jira `issuetype`), labels, then title prefixes.
`has_ai_request_label()` (`repo://issues/base.py#L149-L158`) recognizes the
human AI-investigation labels (`zerofactory`, `ai-investigate`, `ai-triage`,
`ai-review`, `ai`). Both priority and category are overridable by explicit
`--priority` / task fields at import time.

## Tracker clients

Both clients implement `BaseIssueClient` (`repo://issues/base.py#L237-L248`)
(`fetch_issue`, `test_connection`):

- **`GitHubIssueClient`** (`repo://issues/github.py#L64-L215`) — fetches via the
  authenticated `gh` CLI (`gh auth status` for `test_connection`).
  `parse_github_issue_ref` accepts a bare number, `owner/repo#42`, or a full
  issue URL. `fetch_investigation_issues` (`repo://issues/github.py#L175-L215`)
  lists all open issues carrying the AI-investigation label for bulk
  synchronization.
- **`JiraIssueClient`** (`repo://issues/jira.py#L94-L255`) — accepts a
  `PROJ-123`-style key (optionally prefixed with a project) and parses issue
  payloads via the Jira REST API 3 endpoint
  (`repo://issues/jira.py#L212-L255`); the instance URL resolves from the
  board's `jira_url` column or `JIRA_BASE_URL`, credentials from
  `JIRA_EMAIL` / `JIRA_API_TOKEN`, and a missing URL raises a descriptive
  `ValueError` rather than a hard stub; `mock_data` payloads are parsed for
  tests/webhooks.

## The import flow

`import_external_issue` (`repo://issues/importer.py#L111-L220`) is the single
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
   a `[Triage] [<Type>] [<key>] <title>` title. The dashboard create-task
   endpoint honors the explicit `task_id`: if the row already exists it returns
   a `duplicate` response with the current status instead of inserting
   (`repo://dashboard/routes/tasks.py#L272-L286`,
   `repo://dashboard/models.py#L130-L135`). An optional
   `require_ai_request` guard rejects issues lacking the human AI-investigation
   label unless `--force` is passed.
4. **Result** — the caller receives `{ok, id, duplicate, board_slug, status,
   priority, category, source, issue_key, issue_url}` so the CLI can report a
   "Duplicate Skipped" cleanly.

## Dashboard-driven sync & import

The dashboard wires the same import machinery into the operator UI
(`repo://dashboard/gh_issues_service.py` + `repo://dashboard/routes/boards.py`):

- **Synchronization** — `GET/POST /boards/{slug}/sync-gh-issues` scans the
  board's repository for open issues flagged with the AI-investigation label
  and imports each via the same deterministic path
  (`repo://dashboard/routes/boards.py#L535-L560`).
- **Single import** — `POST /boards/{slug}/import-gh-issue` imports one issue
  by number/URL (`repo://dashboard/routes/boards.py#L621-L680`).
- **Task-based setup** — `GET /boards/{slug}/gh-issues-status` reports
  whether the repo has the standard `.github/ISSUE_TEMPLATE` configuration;
  `POST /boards/{slug}/setup-gh-issues` no longer writes templates in place —
  it routes through the shared setup-task helper
  (`create_gh_issues_setup_task` in `repo://dashboard/gh_issues_service.py#L100-L118`)
  to file (or dedup to) a P0 `zf-builder` task whose prompt runs
  `python3 scripts/setup_gh_issues.py --path . --align`: in align mode
  `config.yml` is always regenerated repo-aware, while `bug_report.yml` /
  `feature_request.yml` are rewritten only when missing or when they lack the
  expected `zerofactory` label, so repository-customized templates are
  preserved; labels are provisioned via the `gh` CLI when authenticated
  (`repo://scripts/setup_gh_issues.py`). The CLI `setup-gh-issues` now reports
  the created/already-active task id instead of inline template output.
- **Jira link** — `POST /boards/{slug}/setup-jira` writes the board's
  `jira_url` and `POST /boards/{slug}/test-jira` runs
  `JiraIssueClient.check_connection` against it
  (`repo://dashboard/routes/boards.py#L691-L730`).

## CLI surface

`hermes zerofactory import-gh-issue <issue>` registers the command in the
plugin shell (`repo://__init__.py#L291-L354`): `<issue>` may be a number,
`#42`, a full GitHub URL, or `owner/repo#42`; `--repo` (inferred from the
board `git_url` or git remote when omitted), `--board`, `--status` (default
`triage`), `--priority`, `--assignee` (default `zf-orchestrator`), `--label`
(default `zerofactory`), `--force`, `--sync` (bulk-import all labeled open
issues), `--type`, and `--actor` round out the flags. The handler
(`repo://__init__.py#L779-L905`) fetches via `GitHubIssueClient` and prints the
imported task id, board, status, priority, and URL. A sibling
`hermes zerofactory import-jira-issue` (`repo://__init__.py#L356-L402`) does the
same for Jira Cloud issues (handler at `repo://__init__.py#L907-L1024`).

## Downstream: PR linkage

Tasks carrying `external_issue` metadata are closed the loop on the source
tracker: when the dispatcher opens the PR for such a task, the body appends
`Fixes #<n>` (GitHub) or `Resolves: <KEY>` (Jira)
(`repo://dispatcher/scheduler.py#L1316-L1335`), so a human merge on GitHub also
closes or references the original issue.

## Tests

`tests/unit/issues/test_issues.py` covers ref parsing, priority/category
inference, task-id and dedup-key derivation, board resolution, and import
behavior (part of the `tests/unit` tier; see
[Conventions](/openwiki/conventions.md#tests-pytest-three-tiers)).

## Relationships

Upstream: external trackers and the `gh` CLI. Downstream: the Kanban board
(substrate in [Architecture](/openwiki/architecture.md)) — imported tasks flow
through the [Dispatch Engine](/openwiki/components/dispatcher.md) unchanged.
The CLI is documented in [Quickstart](/openwiki/quickstart.md).
