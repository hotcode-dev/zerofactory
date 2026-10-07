"""Unit tests for dispatcher/config.py step logging: paired STEP markers and rate-limited gate states."""

import logging

from dispatcher.config import (
    StepTracker,
    _step_state_last,
    log_step_end,
    log_step_start,
    log_step_state,
)


def _messages(caplog):
    return [r.getMessage() for r in caplog.records]


def test_log_step_start_end_pair_logs_markers_and_duration(caplog):
    """start/end emit grep-able STEP lines carrying task id and duration."""
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        t0 = log_step_start("package.push", "zf-hdz-4dc03cee", "branch=task/x")
        log_step_end("package.push", t0, "zf-hdz-4dc03cee", "ok", "pushed")

    msgs = _messages(caplog)
    assert any(
        m.startswith("STEP package.push start | task=zf-hdz-4dc03cee | branch=task/x")
        for m in msgs
    )
    end = next(m for m in msgs if m.startswith("STEP package.push end"))
    assert "task=zf-hdz-4dc03cee" in end
    assert "| ok |" in end
    assert "pushed" in end
    # duration is always reported (>= 0.0s)
    assert "0.0s" <= end.split(" | ")[3] or end.split(" | ")[3].endswith("s")


def test_step_tracker_pairs_start_end_across_phases(caplog):
    """Starting a new phase implicitly ends the previous one (outcome=ok)."""
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        steps = StepTracker("t-1")
        steps.start("package.precheck")
        steps.start("package.precommit")
        steps.end("fail", "exit=1")

    msgs = _messages(caplog)
    starts = [m for m in msgs if " start | " in m]
    ends = [m for m in msgs if " end | " in m]
    assert [s.split(" ")[1] for s in starts] == [
        "package.precheck",
        "package.precommit",
    ]
    assert [e.split(" ")[1] for e in ends] == [
        "package.precheck",
        "package.precommit",
    ]
    # precheck ended implicitly ok; precommit ended explicitly fail
    assert "| ok |" in ends[0]
    assert "| fail |" in ends[1]
    assert "exit=1" in ends[1]


def test_step_tracker_end_without_start_is_noop(caplog):
    """Ending with no active step must not emit a bogus end line."""
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        StepTracker("t-1").end("fail", "nothing running")
    assert not any(" end | " in m for m in _messages(caplog))


def test_step_tracker_records_error_on_exception(caplog):
    """An exception inside a step still emits the end line with outcome=error."""
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        steps = StepTracker("t-err")
        steps.start("package.push")
        try:
            raise RuntimeError("git exploded")
        except RuntimeError:
            steps.end("error", "RuntimeError: git exploded")

    end = next(m for m in _messages(caplog) if " end | " in m)
    assert "| error |" in end
    assert "git exploded" in end


def test_log_step_state_dedupes_repeats_and_relogs_on_change(caplog, monkeypatch):
    """Identical gate states are suppressed; any change logs immediately."""
    _step_state_last.clear()
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        log_step_state("pr_poll", "t-2", "skip", "assignee=human owns task")
        log_step_state("pr_poll", "t-2", "skip", "assignee=human owns task")
        log_step_state("pr_poll", "t-2", "skip", "assignee=human owns task")
        # state or detail change -> new line
        log_step_state("pr_poll", "t-2", "approved", "parked for human merge")

    msgs = [m for m in _messages(caplog) if m.startswith("STEP pr_poll |")]
    assert len(msgs) == 2
    assert "skip" in msgs[0] and "assignee=human owns task" in msgs[0]
    assert "approved" in msgs[1]


def test_log_step_state_relogs_after_interval(caplog, monkeypatch):
    """A persistent state re-reports at most once per interval (staleness heartbeat)."""
    _step_state_last.clear()
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        log_step_state("package", "t-3", "skip", "no candidate")
        log_step_state("package", "t-3", "skip", "no candidate")
        assert (
            len([m for m in _messages(caplog) if m.startswith("STEP package |")]) == 1
        )

        # simulate interval elapsed
        key = "package:t-3"
        sig, _ = _step_state_last[key]
        monkeypatch.setitem(_step_state_last, key, (sig, 0.0))
        log_step_state("package", "t-3", "skip", "no candidate")

    assert len([m for m in _messages(caplog) if m.startswith("STEP package |")]) == 2


def test_log_step_state_isolates_tasks(caplog):
    """State dedupe is per (step, task): other tasks log independently."""
    _step_state_last.clear()
    with caplog.at_level(logging.INFO, logger="zerofactory.kanban.dispatcher"):
        log_step_state("pr_poll", "t-a", "skip", "same reason")
        log_step_state("pr_poll", "t-b", "skip", "same reason")

    assert len([m for m in _messages(caplog) if m.startswith("STEP pr_poll |")]) == 2
