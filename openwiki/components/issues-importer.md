---
type: subsystem
title: External Issue Import (GitHub)
description: The issues/ subsystem that deterministically ingests GitHub issues (via the gh CLI) into Kanban tasks — label-driven priority/category/type inference, deterministic task IDs and dedup keys, board resolution, and PR linkage back to the source issue; plus the dashboard endpoints that drive synchronization/import and the task-based GitHub issues setup flow.
tags: [issues-import, github, external-issue-tracker, dedup, kanban-import, gh-issues-setup]
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
  - id: openwiki-source-6b26d87a1c92fff15057316c
    resource: repo://tests/unit/issues/test_issues.py
generated: { by: "hermes", at: "2026-11-19T06:27:25.202Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-11-20T15:20:57.003Z
---

# External Issue Import (GitHub)

The `issues/` package gives the factory a single, deterministic entry point
from external issue trackers into the Kanban board. A GitHub issue is fetched
via the authenticated `gh` CLI, normalized into an `ExternalIssue`, and
materialized as a Kanban task — so a real-world bug report flows through the
same builder → reviewer pipeline as any hand-typed ticket, and the PR that
fixes it links back to the source issue.

Jira integration has been **removed** from the codebase (the former
`issues/jira.py`, `import-jira-issue` CLI command, and `setup-jira` /
`test-jira` dashboard routes no longer exist). Ingestion is GitHub-only. The
legacy `ExternalIssue.source` type still carries a `"jira"` literal
(`repo://issues/base.py#L68`) and the PR body generator keeps a defensive
`Resolves: <KEY>` branch for pre-removal `external_issue` metadata, but no new
Jira data is ever fetched.

## The `ExternalIssue` model

`ExternalIssue` (`repo://issues/base.py#L65-L236`) is the tracker-agnostic
dataclass: `source`, `id`, display `key` (`#42`), title, body, url, author,
labels, assignees, and the owning `repo_or_project`. Two derived identities
make ingestion idempotent across repeated runs:

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
`security`, `performance`, `bug-fix`, `refactoring`, `documentation`, `testing`,
or `config`, defaulting to `feature` when the issue type is a feature, else
`bug-fix` (`repo://issues/base.py#L173-L182`).
`infer_issue_type()` (`repo://issues/base.py#L114-L147`) infers `bug`/`feature`
from labels then title prefixes, and `has_ai_request_label()`
(`repo://issues/base.py#L149-L158`) recognizes the human AI-investigation
labels (`zerofactory`, `ai-investigate`, `ai-triage`, `ai-review`, `ai`). Both
priority and category are overridable by explicit `--priority` / task fields
at import time.

## The GitHub client

`GitHubIssueClient` (`repo://issues/github.py#L64-L277`) implements
`BaseIssueClient` (`repo://issues/base.py#L237-L248`: `fetch_issue`,
`test_connection`):

- **`parse_github_issue_ref`** (`repo://issues/github.py#L23`) accepts a bare
  number, `#42`, a full issue URL, or `owner/repo#42`.
- **`fetch_issue`** (`repo://issues/github.py#L85`) fetches a single issue via
  the authenticated `gh` CLI.
- **`fetch_investigation_issues`** (`repo://issues/github.py#L175`) lists all
  open issues carrying the AI-investigation label for bulk synchronization.

## The import flow

`import_external_issue` (`repo://issues/importer.py#L112-L229`) is the single
entry point:

1. **Board resolution** — `resolve_board_for_issue`
   (`repo://issues/importer.py#L29-L111`) picks the target board: an explicit
   valid `board_slug` wins, then a match between the issue's `repo_or_project`
   and each board's `git_url` / `repo_alias` / slug (via a `LEFT JOIN` over
   `board_repositories`), then the current working directory's `git remote
   origin` against board URLs; it falls back to the supplied board slug or the
   first available board.
2. **Deterministic identity** — task id + dedup key from the `ExternalIssue`
   methods above; priority/category inferred unless overridden.
3. **Task creation** — builds a `TaskCreate` with an explicit `task_id` and
   merged `metadata` (including `external_issue`, `dedup_key`, `category`),
   tags (`issue:github`, `github-42`, `cat:bug-fix`, sanitized label tags), and
   a `[Triage] [<Type>] [<key>] <title>` title. The dashboard create-task
   endpoint honors the explicit `task_id`: if the row already exists it returns
   a `duplicate` response with the current status instead of inserting
   (`repo://dashboard/routes/tasks.py`). An optional `require_ai_request` guard
   rejects issues lacking the human AI-investigation label unless `--force` is
   passed.
4. **Result** — the caller receives `{ok, id, duplicate, board_slug, status,
   priority, category, source, issue_key, issue_url}` so the CLI can report a
   "Duplicate Skipped" cleanly.

## Dashboard-driven sync & import

The dashboard wires the same import machinery into the operator UI
(`repo://dashboard/routes/boards.py` + `repo://dashboard/gh_issues_service.py`):

- **Synchronization** — `GET/POST /boards/{slug}/sync-gh-issues` (per-repo
  variant included) scans the board's repository for open issues flagged with
  the AI-investigation label and imports each via the same deterministic path
  (`repo://dashboard/routes/boards.py#L992-L1091`).
- **Single import** — `POST /boards/{slug}/import-gh-issue` imports one issue by
  number/URL, resolving the board's `git_url` from `board_repositories`
  (`repo://dashboard/routes/boards.py#L1092-L1152`).
- **Task-based setup** — `GET /boards/{slug}/gh-issues-status` reports whether
  the repo has the standard `.github/ISSUE_TEMPLATE` configuration
  (`repo://dashboard/routes/boards.py#L956-L972`,
  `repo://dashboard/gh_issues_service.py#L86-L103`); `POST
  /boards/{slug}/setup-gh-issues` no longer writes templates in place — it
  routes through the shared setup-task helper
  (`create_gh_issues_setup_task` in `repo://dashboard/gh_issues_service.py#L104-L125`)
  to file (or dedup to) a P0 `zf-builder` task whose prompt runs
  `python3 scripts/setup_gh_issues.py --path . --align`: in align mode
  `config.yml` is always regenerated repo-aware, while `bug_report.yml` /
  `feature_request.yml` are rewritten only when missing or lacking the expected
  `zerofactory` label, so repository-customized templates are preserved; labels
  are provisioned via the `gh` CLI when authenticated
  (`repo://dashboard/routes/boards.py#L973-L991`). The CLI `setup-gh-issues`
  reports the created/already-active task id instead of inline template
  output.

## CLI surface

`hermes zerofactory import-gh-issue <issue>` is registered in the plugin shell
(`repo://__init__.py#L412-L473`): `<issue>` may be a number, `#42`, a full
GitHub URL, or `owner/repo#42` (or omitted when using `--sync`); flags include
`--repo` (inferred from board `git_url` or git remote when omitted), `--board`,
`--status` (default `triage`), `--priority`, `--assignee` (default `human`),
`--label` (default `zerofactory`), `--force`, `--sync` (bulk-import all labeled
open issues), `--type` (`bug`/`feature` override), and `--actor`. The handler
(`repo://__init__.py#L1031-L1154`) fetches via `GitHubIssueClient` and prints
the imported task id, board, status, priority, and URL.

## Downstream: PR linkage

Tasks carrying `external_issue` metadata close the loop on the source tracker:
when the dispatcher opens the PR, the body appends `Fixes #<n>` (GitHub) so
merging the PR closes the original issue
(`repo://dispatcher/scheduler.py#L2157-L2175`), and for GitHub issues the
dispatcher posts a single idempotent "PR opened" status reply on the source
issue via `post_issue_pr_comment` (gated on `has_ai_request`, marker-deduped
with `<!-- zf-task:<task_id> -->`)
(`repo://dispatcher/scheduler.py#L961-L1049`).

## Tests

`tests/unit/issues/test_issues.py` covers issue-ref parsing,
priority/category inference, deterministic task-id and dedup-key derivation,
board resolution, import behavior (deterministic and idempotent), the CLI
import flow with label enforcement, and `setup_gh_issues` template generation
(including align-mode writes) — part of the `tests/unit` tier; see
[Conventions](/openwiki/conventions.md#tests-pytest-three-tiers).

## Relationships

Upstream: external GitHub issues and the `gh` CLI. Downstream: the Kanban
board (substrate in [Architecture](/openwiki/architecture.md)) — imported
tasks flow through the [Dispatch Engine](/openwiki/components/dispatcher.md)
unchanged. The CLI is documented in
[Quickstart](/openwiki/quickstart.md).
