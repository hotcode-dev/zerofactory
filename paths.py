"""Zero Factory — shared profile-path resolution & assignee normalization.

Single source of truth for the two things the dispatcher (``dispatcher.py``) and
the dashboard (``dashboard/plugin_api.py``) each used to re-implement and have
let drift apart:

* **canonical assignee normalization** — mapping a raw assignee string onto the
  recognized ``zf-*`` specialist profiles (or ``"unassigned"``);
* **per-profile ``state.db`` path resolution** — locating the SQLite state
  database for a given agent profile so a spawned worker's ``session_id`` can be
  correlated with a real Hermes session.

Both consumers import from this module instead of carrying their own copies, so
the alias table, the valid-profile set, the normalizer, and the state.db
resolution strategy can no longer diverge between the two surfaces.

Resolution strategy for ``resolve_profile_state_db``
---------------------------------------------------
The union of the strategies each surface previously implemented, in priority
order. Each candidate is checked for on-disk existence and the first hit wins;
``None`` is returned only when none exist:

1. ``~/.hermes/profiles/<canonical>/state.db`` — the canonical, per-profile
   layout (the primary location in current deployments).
2. ``~/.hermes/profiles/<canonical-without-zf-prefix>/state.db`` — legacy
   un-prefixed profile directories.
3. ``<3 levels up from this file>/<canonical>/state.db`` — plugin-relative
   layout (profiles colocated next to the plugin checkout).
4. ``~/.hermes/state.db`` — the global/default Hermes state database.

The helper is **path-blind by design**: it recomputes every candidate on each
call and never caches a resolved path, so a change of ``ZEROFACTORY_DB``,
``HOME``, or the process working directory is picked up immediately rather than
stuck on a previously resolved value (the same class of bug the sibling
``_DB_INITIALIZED`` fix guarded against).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# --- Canonical profile identity (source of truth) ---------------------------

#: Recognized Zero Factory specialist profiles. This is the single source of
#: truth for "which profiles exist"; both the dispatcher's ``VALID_PROFILES``
#: tuple and the dashboard's ``VALID_ASSIGNEES`` set derive from it.
PROFILE_MAP = {
    "zf-builder": "zf-builder",
    "zf-reviewer": "zf-reviewer",
    "zf-orchestrator": "zf-orchestrator",
}

#: Sentinel assignee meaning "no agent is responsible for this task".
UNASSIGNED = "unassigned"

#: Full set of valid assignee values (the sentinel plus every specialist
#: profile). This is the single source of truth for the dashboard's
#: ``VALID_ASSIGNEES`` guard; the dispatcher's ``VALID_PROFILES`` tuple is the
#: profiles-only view (``tuple(PROFILE_MAP)``) and intentionally excludes the
#: sentinel.
VALID_ASSIGNEES = {UNASSIGNED, *PROFILE_MAP}


def normalize_assignee(assignee: Optional[str]) -> str:
    """Normalize an assignee onto a canonical ``zf-*`` profile or ``"unassigned"``.

    * empty / ``None`` / ``"unassigned"`` -> ``"unassigned"``
    * a recognized profile (or an alias that maps to one) -> its canonical name
    * any other value -> ``"unassigned"`` (unknown assignees are not valid
      specialist profiles and are treated as unassigned rather than passed
      through verbatim)
    """
    if not assignee or assignee == UNASSIGNED:
        return UNASSIGNED
    return PROFILE_MAP.get(assignee, UNASSIGNED)


def _hermes_profiles_root() -> Path:
    """Root directory holding per-profile state directories."""
    return Path.home() / ".hermes" / "profiles"


def _plugin_profiles_root() -> Optional[Path]:
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


def resolve_profile_state_db(assignee: str) -> Optional[Path]:
    """Resolve the ``state.db`` path for an agent profile.

    See the module docstring for the full strategy. Accepts either a raw
    assignee string or a canonical ``zf-*`` name (both are normalized first),
    Returns the first candidate that exists on disk, or ``None`` when none do.
    Never caches — re-resolves on every call.

    ``"unassigned"`` is treated like any other key: the per-profile candidates
    simply do not exist for it, so it falls through to the global
    ``~/.hermes/state.db`` (matching the dashboard's historical behavior) and
    ``None`` when nothing is present.
    """
    norm_asgn = normalize_assignee(assignee)

    # 1. Canonical per-profile location.
    p1 = _hermes_profiles_root() / norm_asgn / "state.db"
    if p1.exists():
        return p1

    # 2. Legacy un-prefixed profile directory.
    unprefixed = norm_asgn.replace("zf-", "")
    if unprefixed != norm_asgn:
        p2 = _hermes_profiles_root() / unprefixed / "state.db"
        if p2.exists():
            return p2

    # 3. Plugin-relative location (profiles colocated with the plugin checkout).
    plugin_root = _plugin_profiles_root()
    if plugin_root is not None:
        try:
            p3 = plugin_root / norm_asgn / "state.db"
            if p3.exists():
                return p3
        except Exception:
            pass

    # 4. Global/default Hermes state database (last resort).
    p4 = Path.home() / ".hermes" / "state.db"
    if p4.exists():
        return p4

    return None
