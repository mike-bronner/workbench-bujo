"""Tests for the cross-process mutation lock — added in 0.9.0.

These exercise the file-lock primitive itself, not the verbs that wrap
it. The verbs delegate to `mutation_lock(run_dir)`, so verifying the
primitive plus a single end-to-end check that it's actually held during
apply_decisions covers the contract.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

from bujo_scribe_mcp.locking import mutation_lock
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    DecisionComplete,
)
from bujo_scribe_mcp.tools import apply_decisions


def test_lock_file_created_on_acquire(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    with mutation_lock(run_dir):
        assert (run_dir / "mutation.lock").exists()


def test_lock_serializes_within_process(tmp_path: Path) -> None:
    """Re-entering the lock from the same process queues — flock is
    per-fd, so a fresh open() within an existing critical section will
    block. We only verify the basic acquire/release contract here."""
    run_dir = tmp_path / "run"
    # Sequential acquire+release should be a fast path.
    for _ in range(5):
        with mutation_lock(run_dir):
            pass


def _hold_lock_for(run_dir_str: str, hold_seconds: float, ready_path: str, done_path: str) -> None:
    """Subprocess helper: acquire the lock, signal ready, sleep, signal done."""
    with mutation_lock(Path(run_dir_str)):
        Path(ready_path).touch()
        time.sleep(hold_seconds)
        Path(done_path).touch()


def test_lock_blocks_across_processes(tmp_path: Path) -> None:
    """The whole point of the lock — process B must wait for process A."""
    run_dir = tmp_path / "run"
    ready = tmp_path / "a-ready"
    done = tmp_path / "a-done"

    # mp.Process uses fork on macOS/Linux for the test fixture's lifetime,
    # which is fine — we want a separate process holding the same
    # advisory lock on the same path.
    proc_a = mp.Process(target=_hold_lock_for, args=(str(run_dir), 0.5, str(ready), str(done)))
    proc_a.start()

    # Wait until A signals it has the lock.
    deadline = time.time() + 5.0
    while not ready.exists() and time.time() < deadline:
        time.sleep(0.01)
    assert ready.exists(), "process A failed to acquire lock within 5s"
    assert not done.exists(), "process A finished before B even tried — racy test"

    # B tries to acquire. Should block until A releases (~500ms after ready).
    t_start = time.time()
    with mutation_lock(run_dir):
        elapsed = time.time() - t_start
        # By the time B got the lock, A must have released → done file exists.
        assert done.exists(), "process B got the lock before A released"

    proc_a.join(timeout=2.0)
    assert not proc_a.is_alive()
    # B waited at least ~400ms (some scheduling slack from the 500ms hold).
    assert elapsed > 0.3, f"B acquired suspiciously fast ({elapsed:.3f}s) — lock not blocking"


def test_apply_decisions_holds_the_lock_during_mutation(
    make_backend, make_context, render_body, make_bujo_line, monkeypatch
) -> None:
    """End-to-end: a real verb call should pass through the lock path.

    We verify by spying on the lock context manager. If the verb routes
    around the lock (regression), the spy never fires.
    """
    body = render_body(
        "sample-note",
        [make_bujo_line("task", "Do the thing")],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    spy_calls: list[Path] = []

    real_lock = mutation_lock

    def spy_lock(run_dir):
        spy_calls.append(run_dir)
        return real_lock(run_dir)

    monkeypatch.setattr(apply_decisions, "mutation_lock", spy_lock)

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[DecisionComplete(op="complete", bullet="Do the thing")],
        ),
        ctx=ctx,
    )

    assert spy_calls == [ctx.config.run_dir]
    assert not out.unmatched
