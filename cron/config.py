"""Zero Factory Cron — Constants, Configurations, and Process Registries."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

_log = logging.getLogger("zerofactory.cron")

DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"

# Bounded synchronous wait for `hermes cron run` triggered via trigger_builtin_job.
CRON_RUN_TIMEOUT = 300
CRON_RUN_OUTPUT_TAIL_CHARS = 2048

# Registry tracking active on-demand cron-run child processes keyed by job_id:
# {job_id: subprocess.Popen}.
_active_cron_runs: Dict[str, subprocess.Popen] = {}


def _c() -> Any:
    """Dynamic lookup for mockable module namespace (builtin_cron or cron)."""
    return sys.modules.get("builtin_cron") or sys.modules.get("cron")


def reap_active_cron_runs() -> int:
    """Reap finished on-demand cron-run child processes."""
    disp = _c()
    active_runs = getattr(disp, "_active_cron_runs", _active_cron_runs) if disp else _active_cron_runs

    reaped = 0
    for jid, proc in list(active_runs.items()):
        if proc is not None:
            retcode = proc.poll()
            if retcode is not None:
                active_runs.pop(jid, None)
                reaped += 1
                _log.debug("Cron-run process for job '%s' exited with code %d", jid, retcode)
    return reaped


def get_db_path() -> Path:
    override = os.environ.get("ZEROFACTORY_DB")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def _load_env_defaults() -> tuple[str, str, str]:
    """Resolve default model, provider, and base_url from env or configs."""
    model = os.getenv("HERMES_MODEL")
    provider = os.getenv("HERMES_INFERENCE_PROVIDER")
    base_url = os.getenv("CUSTOM_BASE_URL")

    search_files = [
        Path(os.path.expanduser("~/.hermes/profiles/zf-orchestrator/.env")),
        Path(__file__).resolve().parent.parent / ".env",
        Path(os.path.expanduser("~/.hermes/.env")),
    ]
    env_override = os.getenv("HERMES_ENV_FILE")
    if env_override:
        search_files.insert(0, Path(os.path.expanduser(env_override)))
    for env_file in search_files:
        if model and provider and base_url:
            break
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "HERMES_MODEL" and not model:
                        model = v
                    elif k == "HERMES_INFERENCE_PROVIDER" and not provider:
                        provider = v
                    elif k == "CUSTOM_BASE_URL" and not base_url:
                        base_url = v
            except Exception:
                pass

    return (
        model or "qwen38-27b-unsloth-nvfp4-dflash2",
        provider or "custom",
        base_url or "https://spark.ntsd.dev:8001/v1",
    )


DEFAULT_CRON_MODEL, DEFAULT_CRON_PROVIDER, DEFAULT_CRON_BASE_URL = _load_env_defaults()

TASK_QUEUE_CHECK_PROMPT = """Check the Zero Factory Kanban board (using `hermes zerofactory list` or querying `~/.hermes/zerofactory.db`) - are any tasks stuck in 'running' too long? Any tasks stuck in 'blocked' with '[Human Review]'? Any PRs stuck waiting for Reviewer feedback? Create a new Kanban task using `hermes zerofactory create "[Report] Queue Health" --description "..." --status done` containing your bottleneck report and recommendations."""

DAILY_REPORT_PROMPT = """Generate a comprehensive daily report for Zero Factory using `hermes zerofactory stats` and querying `~/.hermes/zerofactory.db`. Include: total tasks completed, tasks currently running, tasks blocked, agent throughput, and open issues. Summarize with actionable items. Create a new task using `hermes zerofactory create "[Report] Daily Report" --description "..." --status done` with your full report."""
