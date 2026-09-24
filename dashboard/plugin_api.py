"""Zero Factory — Backend API Routes & Durable SQLite Layer.

Mounted at /api/plugins/zerofactory/ in the Hermes Dashboard.
Provides a durable, rock-solid, multi-board task management engine specifically
crafted for Zero Factory multi-agent coordination.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure zerofactory plugin root and dashboard dir are in sys.path
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

# Shared global-settings source of truth (defaults + parsing)
try:
    from ..settings import (  # type: ignore
        DEFAULT_MAX_ACTIVE_TASKS, DEFAULT_SCAN_ON_IDLE,
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD, DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_MAX_TODO, DEFAULT_ACTIVITY_RETENTION_DAYS,
        DEFAULT_SETTING_VALUES, load_settings,
    )
except (ImportError, ValueError):
    from settings import (  # type: ignore
        DEFAULT_MAX_ACTIVE_TASKS, DEFAULT_SCAN_ON_IDLE,
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD, DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_MAX_TODO, DEFAULT_ACTIVITY_RETENTION_DAYS,
        DEFAULT_SETTING_VALUES, load_settings,
    )

# Shared profile-path resolution & assignee normalization
try:
    from ..paths import (  # type: ignore
        PROFILE_MAP,
        UNASSIGNED,
        VALID_ASSIGNEES,
        normalize_assignee,
        resolve_profile_state_db,
    )
except (ImportError, ValueError):
    from paths import (  # type: ignore
        PROFILE_MAP,
        UNASSIGNED,
        VALID_ASSIGNEES,
        normalize_assignee,
        resolve_profile_state_db,
    )

try:
    from ..profile_manager import sync_langfuse_profiles  # type: ignore
except (ImportError, ValueError):
    try:
        from profile_manager import sync_langfuse_profiles  # type: ignore
    except (ImportError, ValueError):
        sync_langfuse_profiles = None  # type: ignore

_log = logging.getLogger(__name__)

# --- Re-export DB layer ------------------------------------------------------
try:
    from .db import (
        ACTIVITY_PRUNE_INTERVAL_SECONDS,
        DEFAULT_DB_PATH,
        _DB_INITIALIZED_PATHS,
        _load_scanner_gate_module,
        _mark_scanner_task_created,
        _scanner_gate_mod,
        derive_board_code,
        generate_task_id,
        get_db_conn,
        get_db_path,
        init_db,
        log_activity,
        parse_git_url,
        prune_old_activity,
        row_to_dict,
    )
except (ImportError, ValueError):
    from db import (  # type: ignore
        ACTIVITY_PRUNE_INTERVAL_SECONDS,
        DEFAULT_DB_PATH,
        _DB_INITIALIZED_PATHS,
        _load_scanner_gate_module,
        _mark_scanner_task_created,
        _scanner_gate_mod,
        derive_board_code,
        generate_task_id,
        get_db_conn,
        get_db_path,
        init_db,
        log_activity,
        parse_git_url,
        prune_old_activity,
        row_to_dict,
    )

# --- Re-export Pydantic Models & Enums ----------------------------------------
try:
    from .models import (
        ACTIVITY_ACTORS,
        MEMORY_CONTENT_MAX_LENGTH,
        VALID_MEMORY_CATEGORIES,
        VALID_PRIORITIES,
        VALID_STATUSES,
        BoardCreate,
        BoardUpdate,
        CommentCreate,
        CronJobUpdate,
        CronToggleRequest,
        DependencyLink,
        LangfuseTestRequest,
        MemoryCreate,
        MemoryUpdate,
        SettingsUpdate,
        TaskCreate,
        TaskMove,
        TaskUpdate,
    )
except (ImportError, ValueError):
    from models import (  # type: ignore
        ACTIVITY_ACTORS,
        MEMORY_CONTENT_MAX_LENGTH,
        VALID_MEMORY_CATEGORIES,
        VALID_PRIORITIES,
        VALID_STATUSES,
        BoardCreate,
        BoardUpdate,
        CommentCreate,
        CronJobUpdate,
        CronToggleRequest,
        DependencyLink,
        LangfuseTestRequest,
        MemoryCreate,
        MemoryUpdate,
        SettingsUpdate,
        TaskCreate,
        TaskMove,
        TaskUpdate,
    )

# --- Re-export Memory Service ------------------------------------------------
try:
    from .memory_service import (
        AUTO_MEMORY_PREFIX_REGEX,
        compute_dedup_key,
        extract_and_record_memory,
        normalize_file_path,
        normalize_memory_content,
    )
except (ImportError, ValueError):
    from memory_service import (  # type: ignore
        AUTO_MEMORY_PREFIX_REGEX,
        compute_dedup_key,
        extract_and_record_memory,
        normalize_file_path,
        normalize_memory_content,
    )

# --- Re-export Session Service -----------------------------------------------
try:
    from .session_service import (
        AGENT_ICONS,
        AGENT_LABELS,
        _compute_stuck_status,
        get_profile_state_db,
        list_all_sessions,
        resolve_task_all_sessions,
        resolve_task_session_progress,
    )
except (ImportError, ValueError):
    from session_service import (  # type: ignore
        AGENT_ICONS,
        AGENT_LABELS,
        _compute_stuck_status,
        get_profile_state_db,
        list_all_sessions,
        resolve_task_all_sessions,
        resolve_task_session_progress,
    )

# --- Routes and Master APIRouter ---------------------------------------------
try:
    from .routes import (
        agents_router,
        boards_router,
        cron_router,
        dispatch_router,
        memories_router,
        router,
        settings_router,
        stats_router,
        tasks_router,
    )
    from .routes.agents import get_agents_status
    from .routes.boards import (
        _get_cron_helpers,
        create_board,
        delete_board,
        list_boards,
        update_board,
    )
    from .routes.cron import (
        get_builtin_cron_jobs,
        reset_builtin_cron_job,
        run_builtin_cron_job,
        sync_builtin_cron_jobs,
        toggle_builtin_cron_job,
        toggle_cron_scheduler,
        update_builtin_cron_job,
    )
    from .routes.dispatch import (
        get_dispatch_status,
        get_stuck_tasks,
        import_legacy,
        reap_all_stuck_tasks,
        reap_single_task,
        trigger_dispatch,
    )
    from .routes.memories import (
        create_board_memory,
        create_memory,
        delete_board_memory,
        delete_memory,
        list_board_memories,
        list_memories,
        update_board_memory,
        update_memory,
    )
    from .routes.settings import (
        get_settings,
        test_langfuse_connection,
        update_settings,
    )
    from .routes.stats import (
        count_orchestrator_scans_today,
        get_activities,
        get_orchestrator_scan_activities,
        get_stats,
    )
    from .routes.tasks import (
        add_comment,
        add_dependency,
        create_task,
        delete_task,
        get_comments,
        get_task,
        get_task_session,
        get_task_sessions,
        list_tasks,
        move_task,
        remove_dependency,
        update_task,
    )
except (ImportError, ValueError):
    from routes import (  # type: ignore
        agents_router,
        boards_router,
        cron_router,
        dispatch_router,
        memories_router,
        router,
        settings_router,
        stats_router,
        tasks_router,
    )
    from routes.agents import get_agents_status  # type: ignore
    from routes.boards import (  # type: ignore
        _get_cron_helpers,
        create_board,
        delete_board,
        list_boards,
        update_board,
    )
    from routes.cron import (  # type: ignore
        get_builtin_cron_jobs,
        reset_builtin_cron_job,
        run_builtin_cron_job,
        sync_builtin_cron_jobs,
        toggle_builtin_cron_job,
        toggle_cron_scheduler,
        update_builtin_cron_job,
    )
    from routes.dispatch import (  # type: ignore
        get_dispatch_status,
        get_stuck_tasks,
        import_legacy,
        reap_all_stuck_tasks,
        reap_single_task,
        trigger_dispatch,
    )
    from routes.memories import (  # type: ignore
        create_board_memory,
        create_memory,
        delete_board_memory,
        delete_memory,
        list_board_memories,
        list_memories,
        update_board_memory,
        update_memory,
    )
    from routes.settings import (  # type: ignore
        get_settings,
        test_langfuse_connection,
        update_settings,
    )
    from routes.stats import (  # type: ignore
        count_orchestrator_scans_today,
        get_activities,
        get_orchestrator_scan_activities,
        get_stats,
    )
    from routes.tasks import (  # type: ignore
        add_comment,
        add_dependency,
        create_task,
        delete_task,
        get_comments,
        get_task,
        get_task_session,
        get_task_sessions,
        list_tasks,
        move_task,
        remove_dependency,
        update_task,
    )

# Initialize on import
try:
    init_db()
    if not os.environ.get("ZEROFACTORY_SKIP_DISPATCHER"):
        try:
            from ..dispatcher import start_background_dispatcher
            start_background_dispatcher()
        except Exception:
            try:
                from dispatcher import start_background_dispatcher  # type: ignore
                start_background_dispatcher()
            except Exception:
                pass
except Exception as e:
    _log.error("Failed to initialize Zero Factory Kanban database: %s", e)
