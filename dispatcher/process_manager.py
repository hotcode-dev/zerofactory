"""Process group termination, worker process management, and active worker registry."""

from __future__ import annotations

import enum
import json
import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from .config import _active_workers, _log


class ProcessState(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CRASHED = "CRASHED"


def build_shell_wrapper(cmd: list[str], exit_prefix: Path | str) -> list[str]:
    """Wrap command in a POSIX shell invocation that atomically writes integer exit code on exit/signal."""
    script = (
        'prefix="$1"; shift; '
        'trap "rc=\\$?; printf \\"%d\\n\\" \\"\\$rc\\" > \\"${prefix}.exit.tmp\\" && '
        'mv \\"${prefix}.exit.tmp\\" \\"${prefix}.exit\\"; exit \\$rc" EXIT INT TERM; '
        '"$@"'
    )
    return ["sh", "-c", script, "zf-runner", str(exit_prefix)] + cmd


def get_exit_file_path(task_id: str) -> Path:
    """Return standard .exit file path for a task worker in ~/.hermes/logs."""
    logs_dir = Path.home() / ".hermes" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"worker_{task_id}.exit"


def cleanup_process_artifacts(task_id: str) -> None:
    """Unlink lingering .exit and .exit.tmp files for task_id."""
    logs_dir = Path.home() / ".hermes" / "logs"
    for name in (f"worker_{task_id}.exit", f"worker_{task_id}.exit.tmp"):
        p = logs_dir / name
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def is_pid_alive(pid: int | None) -> bool:
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


def get_process_exit_code(
    task_id: str, pid: int | None
) -> Tuple[ProcessState, Optional[int]]:
    """Determine process status and return code using .exit file and OS PID checks.

    Returns:
        (ProcessState.COMPLETED, returncode): when .exit file exists and is parsed.
        (ProcessState.RUNNING, None): when process is actively running and matches identity.
        (ProcessState.CRASHED, -1): when process is missing or zombie with no .exit file.
    """
    exit_path = get_exit_file_path(task_id)
    if exit_path.exists():
        try:
            content = exit_path.read_text(encoding="utf-8").strip()
            if content:
                rc = int(content)
                return ProcessState.COMPLETED, rc
        except Exception:
            pass

    if pid and is_pid_alive(pid):
        # Validate process identity before confirming running state
        is_hermes = False
        try:
            cmdline_path = Path(f"/proc/{pid}/cmdline")
            if cmdline_path.exists():
                cmd_data = cmdline_path.read_bytes().decode("utf-8", errors="replace")
                if (
                    "hermes" in cmd_data
                    or task_id in cmd_data
                    or "zf-runner" in cmd_data
                ):
                    is_hermes = True
            else:
                is_hermes = True
        except Exception:
            is_hermes = True
        if is_hermes:
            return ProcessState.RUNNING, None

    return ProcessState.CRASHED, -1


def terminate_process_group(
    proc: subprocess.Popen | None, pid: int | None, grace: float = 2.0
) -> None:
    """Terminate a worker's ENTIRE process group (session), not just the child.

    All Zero Factory spawn sites run children with ``start_new_session=True``
    so the tree survives the spawner; the direct child (the ``hermes`` CLI
    wrapper) spawns its own descendants (the agent loop, git, npm, network
    subprocesses).

    Because ``start_new_session=True`` puts the child in a NEW session whose
    PGID equals its PID, ``os.killpg`` on that group reaches every descendant.
    """
    pgid: int | None = None
    if proc is not None and isinstance(proc.pid, int):
        try:
            pgid = os.getpgid(proc.pid)
        except (AttributeError, OSError):
            pgid = None
    if pgid is None and isinstance(pid, int) and pid > 0:
        pgid = pid

    if pgid is None:
        _log.debug(
            "terminate_process_group: no resolvable process group (proc=%s, pid=%s)",
            proc,
            pid,
        )
        return

    # Cheap guard: probe group existence before signalling
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        if pid:
            if not is_pid_alive(pid):
                try:
                    os.waitpid(pid, os.WNOHANG)
                except (ChildProcessError, OSError):
                    pass
                return
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(min(grace, 0.5))
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
        return
    except OSError as e:
        _log.debug("terminate_process_group: probe on group %s failed: %s", pgid, e)

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError) as e:
        _log.debug("terminate_process_group: SIGTERM to group %s failed: %s", pgid, e)
        return

    if proc is not None and isinstance(proc.pid, int):
        try:
            proc.wait(timeout=grace)
            return  # group exited gracefully within grace window
        except Exception:
            pass
    elif grace > 0:
        time.sleep(grace)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError) as e:
        _log.debug("terminate_process_group: SIGKILL to group %s failed: %s", pgid, e)

    if proc is not None and isinstance(proc.pid, int):
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    elif pid and isinstance(pid, int):
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass


def terminate_worker_process(proc: subprocess.Popen | None, pid: int | None) -> None:
    """Safely terminate a worker process group with SIGTERM then SIGKILL."""
    try:
        terminate_process_group(proc, pid)
    except Exception as e:
        _log.debug("terminate_worker_process: group termination raised: %s", e)


def terminate_task_worker(task_id: str, pid: int | None) -> None:
    """Safely terminate any active worker process group for a task and clean up artifacts."""
    _active_workers.pop(task_id, None)
    if pid and is_pid_alive(pid):
        terminate_process_group(None, pid)
    cleanup_process_artifacts(task_id)


def stop_task_worker(task_id: str, cursor: sqlite3.Cursor | None = None) -> None:
    """Safely terminate any active worker process for a task.

    Checks in-memory workers first, then falls back to `tasks.worker_pid` column or metadata.
    Idempotent and exception-safe.
    """
    proc = _active_workers.pop(task_id, None)
    pid = None
    if proc is not None:
        pid = proc.pid
    elif cursor:
        try:
            try:
                cursor.execute(
                    "SELECT worker_pid, metadata FROM tasks WHERE id = ?", (task_id,)
                )
                row = cursor.fetchone()
                if row:
                    pid = (
                        row["worker_pid"]
                        if hasattr(row, "keys") and "worker_pid" in row.keys()
                        else row[0]
                    )
                    if not pid:
                        raw_meta = (
                            row["metadata"]
                            if hasattr(row, "keys") and "metadata" in row.keys()
                            else (row[1] if len(row) > 1 else None)
                        )
                        meta = json.loads(raw_meta or "{}")
                        pid = meta.get("worker_pid")
            except sqlite3.OperationalError:
                cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                row = cursor.fetchone()
                if row:
                    raw_meta = (
                        row["metadata"]
                        if hasattr(row, "keys") and "metadata" in row.keys()
                        else row[0]
                    )
                    meta = json.loads(raw_meta or "{}")
                    pid = meta.get("worker_pid")
        except Exception:
            pass
    terminate_worker_process(proc, pid)
    cleanup_process_artifacts(task_id)
