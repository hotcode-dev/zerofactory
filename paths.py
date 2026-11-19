"""Zero Factory — shared profile-path resolution & assignee normalization.

Single source of truth shared by the dispatcher (``dispatcher.py``) and the
dashboard (``dashboard/plugin_api.py``):

* **canonical assignee normalization** — mapping a raw assignee string onto the
  recognized ``zf-*`` specialist profiles (or ``"unassigned"``);
* **per-profile ``state.db`` path resolution** — locating the SQLite state
  database for a given agent profile so a spawned worker's ``session_id`` can be
  correlated with a real Hermes session.

Both consumers import from this module, so the valid-profile set, the
normalizer, and the state.db resolution strategy stay identical across both
surfaces.

Resolution strategy for ``resolve_profile_state_db``
---------------------------------------------------
The union of the strategies each surface previously implemented, in priority
order. Each candidate is checked for on-disk existence and the first hit wins;
``None`` is returned only when none exist:

1. ``~/.hermes/profiles/<canonical>/state.db`` — the canonical, per-profile
   layout (the primary location in current deployments).
2. ``<3 levels up from this file>/<canonical>/state.db`` — plugin-relative
   layout (profiles colocated next to the plugin checkout).
3. ``~/.hermes/state.db`` — the global/default Hermes state database.

The helper is **path-blind by design**: it recomputes every candidate on each
call and never caches a resolved path, so a change of ``ZEROFACTORY_DB``,
``HOME``, or the process working directory is picked up immediately rather than
stuck on a previously resolved value (the same class of bug the sibling
``_DB_INITIALIZED`` fix guarded against).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# --- Canonical repository metadata (source of truth) -----------------------
ZEROFACTORY_REPO = "hotcode-dev/zerofactory"
ZEROFACTORY_GITHUB_URL = f"https://github.com/{ZEROFACTORY_REPO}"
ZEROFACTORY_ISSUES_URL = f"https://github.com/{ZEROFACTORY_REPO}/issues"

# --- Canonical profile identity (source of truth) ---------------------------

#: Recognized Zero Factory specialist profiles. This is the single source of
#: truth for "which profiles exist"; both the dispatcher's ``VALID_PROFILES``
#: tuple and the dashboard's ``VALID_ASSIGNEES`` set derive from it.
PROFILE_MAP = {
    "zf-builder": "zf-builder",
    "zf-reviewer": "zf-reviewer",
    "zf-orchestrator": "zf-orchestrator",
    "zf-goldfish": "zf-goldfish",
}

#: Canonical sequence of recognized agent roles.
AGENT_ROLES = tuple(PROFILE_MAP)

#: Sentinel assignee meaning "no agent is responsible for this task".
UNASSIGNED = "unassigned"

#: Sentinel assignee meaning a human developer/reviewer is responsible for this task.
HUMAN = "human"

#: Full set of valid assignee values (the sentinels plus every specialist
#: profile). This is the single source of truth for the dashboard's
#: ``VALID_ASSIGNEES`` guard; the dispatcher's ``VALID_PROFILES`` tuple is the
#: profiles-only view (``tuple(PROFILE_MAP)``) and intentionally excludes the
#: sentinels.
VALID_ASSIGNEES = {UNASSIGNED, HUMAN, *PROFILE_MAP}


def normalize_assignee(assignee: str | None) -> str:
    """Normalize an assignee onto a canonical ``zf-*`` profile, ``"human"``, or ``"unassigned"``.

    * empty / ``None`` / ``"unassigned"`` -> ``"unassigned"``
    * ``"human"`` -> ``"human"``
    * a recognized profile -> its canonical name
    * any other value -> ``"unassigned"`` (unknown assignees are not valid
      specialist profiles and are treated as unassigned rather than passed
      through verbatim)
    """
    if not assignee or assignee == UNASSIGNED:
        return UNASSIGNED
    if assignee == HUMAN:
        return HUMAN
    return PROFILE_MAP.get(assignee, UNASSIGNED)


#: Deterministic taxonomy for ``metadata.blocked_reason_type``. Agents emit one
#: of these codes verbatim via ``hermes zerofactory block <id> --reason <code>``;
#: (the dispatcher emits ``"stuck"`` when a retry budget is exhausted);
#: ``blocked_reason`` stays free text for humans. Anything else classifies as
#: the human gate.
BLOCKED_REASON_TYPES = frozenset(
    {"changes-requested", "approved", "human-gate", "stuck"}
)
BLOCKED_REASON_TYPE_HUMAN_GATE = "human-gate"


def normalize_blocked_reason_type(reason: str | None) -> str:
    """Classify a ``block --reason`` value into a canonical ``blocked_reason_type``.

    Deterministic exact-match classification — no prose heuristics: a canonical
    code passes through (lower-cased, stripped), every other value is the human
    gate (``"human-gate"``).
    """
    raw = (reason or "").strip().lower()
    return raw if raw in BLOCKED_REASON_TYPES else BLOCKED_REASON_TYPE_HUMAN_GATE


VALID_TODO_ASSIGNEES = frozenset({"zf-builder", "zf-reviewer", "zf-goldfish"})
VALID_TRIAGE_ASSIGNEES = frozenset({"human", "zf-orchestrator"})
VALID_TASK_STAGES = (
    "triage",
    "interview",
    "spec_approval",
    "awaiting_merge",
    "blocked",
    "grill",
    "spec_draft",
    "spec_audit",
    "building",
    "review",
    "recovery",
    "packaging",
    "done",
)
HUMAN_STAGES = frozenset(
    {"triage", "interview", "spec_approval", "awaiting_merge", "blocked"}
)


def resolve_status_assignee(
    target_status: str,
    current_assignee: str | None = None,
    target_assignee: str | None = None,
    blocked_reason_type: str | None = None,
    triage_phase: str | None = None,
    metadata: dict[str, Any] | str | None = None,
) -> str:
    """Deterministically derive the canonical assignee for a target Kanban status."""
    meta: dict[str, Any] = {}
    if isinstance(metadata, dict):
        meta = metadata
    elif isinstance(metadata, str) and metadata.strip():
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}
    t_phase = (
        triage_phase
        if triage_phase is not None
        else str(meta.get("triage_phase") or "").strip().lower()
    )
    b_type = (
        blocked_reason_type
        if blocked_reason_type is not None
        else str(meta.get("blocked_reason_type") or "").strip().lower()
    )
    status = (target_status or "").strip().lower()
    if status == "triage":
        if target_assignee is not None:
            cand = normalize_assignee(target_assignee)
            return cand if cand in VALID_TRIAGE_ASSIGNEES else HUMAN
        curr = normalize_assignee(current_assignee)
        if curr == "zf-orchestrator" and t_phase != "recovery":
            return "zf-orchestrator"
        return HUMAN

    if status == "todo":
        cand = (
            normalize_assignee(target_assignee)
            if target_assignee is not None
            else normalize_assignee(current_assignee)
        )
        if t_phase == "recovery" and cand == "zf-orchestrator":
            return "zf-orchestrator"
        return cand if cand in VALID_TODO_ASSIGNEES else "zf-builder"

    if status == "running":
        cand = normalize_assignee(
            target_assignee if target_assignee is not None else current_assignee
        )
        return cand if cand in PROFILE_MAP else "zf-builder"

    if status == "blocked":
        if b_type == "changes-requested":
            cand = normalize_assignee(
                target_assignee if target_assignee is not None else current_assignee
            )
            return cand if cand in PROFILE_MAP else "zf-builder"
        return HUMAN

    if status == "done":
        cand = normalize_assignee(
            target_assignee if target_assignee is not None else current_assignee
        )
        return cand if (cand in PROFILE_MAP or cand == HUMAN) else "zf-builder"

    cand = normalize_assignee(
        target_assignee if target_assignee is not None else current_assignee
    )
    return cand if cand != UNASSIGNED else "zf-builder"


def derive_task_stage(
    status: str | None,
    assignee: str | None,
    pr_url: str | None = None,
    metadata: dict[str, Any] | str | None = None,
) -> str:
    """Compute the canonical 13-stage identifier for a task."""
    stat = (status or "triage").strip().lower()
    if stat == "done":
        return "done"

    meta: dict[str, Any] = {}
    if isinstance(metadata, dict):
        meta = metadata
    elif isinstance(metadata, str) and metadata.strip():
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}

    asgn = normalize_assignee(assignee)
    t_phase = str(meta.get("triage_phase") or "").strip().lower()

    if stat == "blocked":
        has_pr = bool(pr_url and str(pr_url).strip())
        b_type = str(meta.get("blocked_reason_type") or "").strip().lower()
        if (
            has_pr
            and b_type not in ("changes-requested", "stuck")
            and not meta.get("permanently_blocked")
            and not meta.get("conflict_retries")
            and not meta.get("precommit_retries")
            and not meta.get("review_cap_reached")
        ):
            return "awaiting_merge"
        return "blocked"

    if stat == "triage":
        if meta.get("awaiting_approval") or t_phase == "human_approval":
            return "spec_approval"
        if meta.get("awaiting_interview"):
            return "interview"
        if asgn == "zf-orchestrator":
            if (
                meta.get("egm") or t_phase == "elephant_drafting"
            ) and t_phase != "recovery":
                return "spec_draft"
            return "grill"
        return "triage"

    if stat == "running" and meta.get("awaiting_pr"):
        return "packaging"
    if asgn == "zf-reviewer":
        return "review"
    if asgn == "zf-goldfish" or t_phase == "goldfish_auditing":
        return "spec_audit"
    if asgn == "zf-orchestrator":
        if t_phase == "recovery":
            return "recovery"
        if meta.get("egm") or t_phase == "elephant_drafting":
            return "spec_draft"
        return "grill"
    return "building"


def derive_ui_column(status: str | None, stage: str | None) -> str:
    """Map task status and stage onto the 4 actor-separated Kanban UI columns."""
    stat = (status or "triage").strip().lower()
    stg = (stage or "triage").strip().lower()
    if stat == "done" or stg == "done":
        return "done"
    if stat == "running" or stg == "packaging":
        return "running"
    if stg in HUMAN_STAGES:
        return "human"
    return "todo"


def get_hermes_home() -> Path:
    """Return the active Hermes home directory.

    Uses ``HERMES_HOME`` directly (without stripping ``profiles/``) when set,
    falling back to ``~/.hermes`` otherwise.
    """
    env_home = os.environ.get("HERMES_HOME")
    if env_home and env_home.strip():
        return Path(env_home.strip()).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def get_active_profile() -> str | None:
    """Return the active Hermes profile name from HERMES_PROFILE or HERMES_HOME.

    Hermes's sandboxed terminal tool sets ``HERMES_HOME=<base>/profiles/<name>``
    but may omit ``HERMES_PROFILE``; falling back to the ``profiles/<name>``
    segment preserves agent identity across CLI invocations.
    """
    profile = (os.environ.get("HERMES_PROFILE") or "").strip()
    if profile:
        return profile
    env_home = (os.environ.get("HERMES_HOME") or "").strip()
    if env_home:
        p = Path(env_home).expanduser()
        if p.parent.name == "profiles" and p.name:
            return p.name
    return None


def _hermes_profiles_root() -> Path:
    """Root directory holding per-profile state directories."""
    return get_hermes_home() / "profiles"


def _plugin_profiles_root() -> Path | None:
    """Plugin-relative profiles directory, or ``None`` when not resolvable.

    The profiles directory is anchored to a fixed ancestor of this file
    (``parents[4]``) so the layout assumption is identical to the original
    dashboard implementation and never drifts. When this file is loaded from a
    tree shallower than expected (``len(parents) <= 4``) the ancestor is not
    meaningful and ``None`` is returned so the caller skips that candidate.
    """
    try:
        resolved_parents = Path(__file__).resolve().parents
        if len(resolved_parents) > 4:
            return resolved_parents[4]
    except Exception:
        pass
    return None


def resolve_profile_state_db(assignee: str) -> Path | None:
    """Resolve the ``state.db`` path for an agent profile.

    See the module docstring for the full strategy. Accepts either a raw
    assignee string or a canonical ``zf-*`` name (both are normalized first),
    Returns the first candidate that exists on disk, or ``None`` when none do.
    Never caches — re-resolves on every call.

    ``"unassigned"`` is treated like any other key: the per-profile candidates
    simply do not exist for it, so it falls through to the global
    ``~/.hermes/state.db`` and ``None`` when nothing is present.
    """
    norm_asgn = normalize_assignee(assignee)

    # 1. Canonical per-profile location.
    p1 = _hermes_profiles_root() / norm_asgn / "state.db"
    if p1.exists():
        return p1

    # 2. Plugin-relative location (profiles colocated with the plugin checkout).
    plugin_root = _plugin_profiles_root()
    if plugin_root is not None:
        try:
            p3 = plugin_root / norm_asgn / "state.db"
            if p3.exists():
                return p3
        except Exception:
            pass

    # 3. Global/default Hermes state database (last resort).
    p4 = get_hermes_home() / "state.db"
    if p4.exists():
        return p4

    return None


def get_workspaces_root() -> Path:
    """Return the root directory for Zero Factory managed repositories and worktrees.

    Defaults to ``~/.zerofactory/workspaces`` unless overridden by
    ``ZEROFACTORY_WORKSPACES_DIR``.
    """
    import os

    override = os.environ.get("ZEROFACTORY_WORKSPACES_DIR")
    if override and override.strip():
        return Path(os.path.expanduser(override.strip())).resolve()
    return Path.home() / ".zerofactory" / "workspaces"


def get_board_repos_dir(board_slug: str) -> Path:
    """Return the base repositories directory for a board under ~/.zerofactory/workspaces/<board_slug>/repos."""
    return get_workspaces_root() / board_slug / "repos"


def get_board_worktrees_dir(board_slug: str) -> Path:
    """Return the task worktrees directory for a board under ~/.zerofactory/workspaces/<board_slug>/worktrees."""
    return get_workspaces_root() / board_slug / "worktrees"
