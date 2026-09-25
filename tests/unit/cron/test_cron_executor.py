"""Unit tests for cron/executor.py."""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import builtin_cron
from cron import config, executor
from cron.config import reap_active_cron_runs
from cron.executor import trigger_builtin_job


class TestCronExecutorUnit(unittest.TestCase):
    """Test job execution, zombie prevention, output draining, and process reaping."""

    def test_trigger_builtin_job_source_has_no_undrained_pipe(self):
        """trigger_builtin_job must never spawn with an un-drained PIPE."""
        src = inspect.getsource(executor.trigger_builtin_job)
        self.assertNotIn("subprocess.PIPE", src)
        self.assertIn("stderr=subprocess.STDOUT", src)
        self.assertIn("stdin=subprocess.DEVNULL", src)
        self.assertIn("_active_cron_runs[", src)
        self.assertIn("proc.wait(", src)

    def test_reap_active_cron_runs_reaps_finished_children(self):
        """reap_active_cron_runs reaps exited children and preserves running ones."""
        def make_proc(retcode):
            p = mock.Mock()
            p.returncode = retcode
            p.poll.return_value = retcode
            return p

        done_a = make_proc(0)
        done_b = make_proc(1)
        still_running = make_proc(None)

        reg = {"job-a": done_a, "job-b": done_b, "job-c": still_running}
        with mock.patch.object(builtin_cron, "_active_cron_runs", reg), \
             mock.patch.object(config, "_active_cron_runs", reg):
            reaped = reap_active_cron_runs()
        self.assertEqual(reaped, 2)
        self.assertNotIn("job-a", reg)
        self.assertNotIn("job-b", reg)
        self.assertIn("job-c", reg)
        done_a.poll.assert_called()
        done_b.poll.assert_called()
        still_running.poll.assert_called()

    def test_trigger_builtin_job_large_output_no_deadlock(self):
        """A child process writing >64KB to stdout/stderr does not deadlock and returns exit status."""
        job_id = "zero-factory-task-queue-check"
        fake_dir = tempfile.mkdtemp(prefix="fake_hermes_")
        fake_hermes = str(Path(fake_dir) / "hermes")
        path_was_prepended = False
        try:
            with open(fake_hermes, "w") as f:
                f.write(
                    "#!/bin/sh\n"
                    "head -c 204800 /dev/zero | tr '\\0' 'A'\n"
                    "head -c 204800 /dev/zero | tr '\\0' 'B' 1>&2\n"
                    "echo 'BOOM-SENTINEL'\n"
                    "exit 3\n"
                )
            os.chmod(fake_hermes, 0o755)

            real = shutil.which("hermes")
            if real is None or Path(real).parent.resolve() != Path(fake_dir).resolve():
                os.environ["PATH"] = fake_dir + os.pathsep + os.environ.get("PATH", "")
                path_was_prepended = True

            start = time.monotonic()
            res = trigger_builtin_job(job_id)
            elapsed = time.monotonic() - start

            self.assertLess(elapsed, 120)
            self.assertNotIn(job_id, executor._active_cron_runs)
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("returncode"), 3)
            self.assertIn("exited with code 3", res.get("message", ""))
            self.assertIn("BOOM-SENTINEL", res.get("output_tail", ""))
        finally:
            shutil.rmtree(fake_dir, ignore_errors=True)
            if path_was_prepended:
                parts = os.environ["PATH"].split(os.pathsep)
                if parts and Path(parts[0]).resolve() == Path(fake_dir).resolve():
                    parts.pop(0)
                os.environ["PATH"] = os.pathsep.join(parts)


if __name__ == "__main__":
    unittest.main()
