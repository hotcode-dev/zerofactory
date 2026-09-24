"""Zero Factory Dashboard — Route aggregation and master APIRouter."""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter

try:
    from .agents import router as agents_router
    from .boards import router as boards_router
    from .cron import router as cron_router
    from .dispatch import router as dispatch_router
    from .memories import router as memories_router
    from .settings import router as settings_router
    from .stats import router as stats_router
    from .tasks import router as tasks_router
except (ImportError, ValueError):
    try:
        from routes.agents import router as agents_router  # type: ignore
        from routes.boards import router as boards_router  # type: ignore
        from routes.cron import router as cron_router  # type: ignore
        from routes.dispatch import router as dispatch_router  # type: ignore
        from routes.memories import router as memories_router  # type: ignore
        from routes.settings import router as settings_router  # type: ignore
        from routes.stats import router as stats_router  # type: ignore
        from routes.tasks import router as tasks_router  # type: ignore
    except (ImportError, ValueError):
        from .agents import router as agents_router  # type: ignore
        from .boards import router as boards_router  # type: ignore
        from .cron import router as cron_router  # type: ignore
        from .dispatch import router as dispatch_router  # type: ignore
        from .memories import router as memories_router  # type: ignore
        from .settings import router as settings_router  # type: ignore
        from .stats import router as stats_router  # type: ignore
        from .tasks import router as tasks_router  # type: ignore

router = APIRouter()
router.include_router(boards_router)
router.include_router(tasks_router)
router.include_router(stats_router)
router.include_router(settings_router)
router.include_router(dispatch_router)
router.include_router(cron_router)
router.include_router(memories_router)
router.include_router(agents_router)

__all__ = [
    "router",
    "agents_router",
    "boards_router",
    "cron_router",
    "dispatch_router",
    "memories_router",
    "settings_router",
    "stats_router",
    "tasks_router",
]
