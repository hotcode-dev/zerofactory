"""Process group termination, worker process management, and active worker registry."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional

from .config import _active_workers, _d, _log


def is_pid_alive(pid: Optional[int]) -> bool:
    """Check if a process exists and is actively running (not a zombie/defunct)."""
    if not pid or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError, ValueError):
        return False

    # If it is a direct child of the current process, non-blocking waitpid can also reap it
    try:
        res_pid, _ = os.waitpid(pid, os.WNOHANG)
        if res_pid == pid:
            return False
    except (ChildProcessError, OSError):
        pass

    # On Linux, inspect /proc/<pid>/status to ensure the process is not a zombie (defunct)
    try:
        status_path = Path(f"/proc/{pid}/status")
        if status_path.exists():
            for line in status_path.read_text().splitlines():
                if line.startswith("State:"):
                    # 'Z' indicates zombie state (e.g. "State:\tZ (zombie)")
                    return "Z" not in line and "zombie" not in line.lower()
    except Exception:
        pass

    return True


def terminate_process_group(proc: Optional[subprocess.Popen], pid: Optional[int], grace: float = 2.0) -> None:
    """Terminate a worker's ENTIRE process group (session), not just the child.

    All Zero Factory spawn sites run children with ``start_new_session=True``
    so the tree survives the spawner; the direct child (the ``hermes`` CLI
    wrapper) spawns its own descendants (the agent loop, git, npm, network
    subprocesses). Signalling only the direct child (``proc.terminate()`` /
    ``os.kill(pid, ...)``) left the whole descendant tree orphaned: it kept
    consuming LLM API credits, could write to the worktree/GitHub after the
    task had already transitioned, and (when a descendant held the combined
    stdout log pipe open) blocked the dispatcher on ``proc.wait(timeout=...)``.

    Because ``start_new_session=True`` puts the child in a NEW session whose
    PGID equals its PID, ``os.killpg`` on that group reaches every descendant.
    Linux-only (``os.killpg``); Windows is not a target platform.

    Fail-open contract (matches the previous child-only termination path):
    every failure mode — dead/unknown group (``ProcessLookupError``),
    permission problems, recycled PIDs — is logged and swallowed; this never
    raises. A cheap pre-flight ``killpg(pgid, 0)`` probes the group without
    delivering a signal and guards against signalling a recycled PGID.
    """
    _disp = _d()
    _os = getattr(_disp, "os", os)
    _time = getattr(_disp, "time", time)

    pgid: Optional[int] = None
    if proc is not None and isinstance(proc.pid, int):
        try:
            pgid = _os.getpgid(proc.pid)
        except (AttributeError, OSError):
            pgid = None
    if pgid is None and isinstance(pid, int) and pid > 0:
        # PID-only fallback (metadata path, no live handle): start_new_session
        # guarantees PGID == PID, so signal the group via the child's PID.
        pgid = pid

    if pgid is None:
        _log.debug("terminate_process_group: no resolvable process group (proc=%s, pid=%s)", proc, pid)
        return

    # Cheap guard: make sure the group still exists before signalling (avoids
    # racing a recycled PGID). killpg(..., 0) probes without delivering a
    # signal; a recycled/unknown group raises ProcessLookupError here.
    try:
        _os.killpg(pgid, 0)
    except ProcessLookupError:
        # Not a process group leader (e.g. spawned without start_new_session) or already dead.
        if pid:
            if not _d().is_pid_alive(pid):
                try:
                    _os.waitpid(pid, os.WNOHANG)
                except (ChildProcessError, OSError):
                    pass
                return
            try:
                _os.kill(pid, signal.SIGTERM)
                _time.sleep(min(grace, 0.5))
                _os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                _os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
        return
    except OSError as e:
        # EPERM (we lack permission for the group) still proves it exists —
        # proceed and let the TERM/KILL attempts handle it.
        _log.debug("terminate_process_group: probe on group %s failed: %s", pgid, e)

    try:
        _os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError) as e:
        _log.debug("terminate_process_group: SIGTERM to group %s failed: %s", pgid, e)
        return

    if proc is not None and isinstance(proc.pid, int):
        try:
            proc.wait(timeout=grace)
            return  # group exited gracefully within the grace window
        except Exception:
            pass
    elif grace > 0:
        _time.sleep(grace)

    try:
        _os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError) as e:
        # Group likely exited between the grace window and the SIGKILL — fine.
        _log.debug("terminate_process_group: SIGKILL to group %s failed: %s", pgid, e)

    if proc is not None and isinstance(proc.pid, int):
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    elif pid and isinstance(pid, int):
        try:
            _os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass


def terminate_worker_process(proc: Optional[subprocess.Popen], pid: Optional[int]) -> None:
    """Safely terminate a worker process with SIGTERM then SIGKILL.

    Signals the worker's whole process group (session) rather than just the
    direct child, because all spawn sites use ``start_new_session=True`` and
    the ``hermes`` CLI wrapper spawns its own descendants. Fail-open: never
    raises. See ``terminate_process_group`` for details.
    """
    try:
        _d().terminate_process_group(proc, pid)
    except Exception as e:  # defensive: the helper is fail-open, but never leak
        _log.debug("terminate_worker_process: group termination raised: %s", e)


def stop_task_worker(task_id: str, cursor: Optional[sqlite3.Cursor] = None) -> None:
    """Safely terminate any active worker process for a task.

    Invoked before git worktree removal or task transitions to prevent orphaned
    zombie processes from running in deleted directories, leaking resources,
    and corrupting plugin symlinks. Checks in-memory workers first, then falls
    back to metadata `worker_pid`. Idempotent and exception-safe.
    """
    proc = _active_workers.pop(task_id, None)
    pid = None
    if proc is not None:
        pid = proc.pid
    elif cursor:
        try:
            cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                raw_meta = row["metadata"] if hasattr(row, "keys") or isinstance(row, dict) else row[0]
                meta = json.loads(raw_meta or "{}")
                pid = meta.get("worker_pid")
        except Exception:
            pass
    _d().terminate_worker_process(proc, pid)
