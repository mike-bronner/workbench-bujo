"""Cross-process mutation serialization via flock(2).

When multiple Claude Code sessions run concurrently, each spawns its own
scribe process. Without coordination, two processes can both pass their
local parallel-edit guard while still racing each other to write the
same Apple Notes record:

    A: read  → v1
    B: read  → v1
    A: write → v2 (based on v1)
    B: write → v2'(based on v1)   # clobbers A's change

A kernel-level advisory lock around the read→mutate→write critical
section serializes mutations across all scribe processes on the host.
The OS releases the lock automatically on process exit (even on crash),
so abandoned locks never strand the system.

The lock file lives inside the plugin tree (`config.run_dir`), which the
launcher cleans up on plugin uninstall — no remnants outside the plugin.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# Single global mutation lock. Per-note locking would be finer-grained,
# but Apple Notes mutations are individually fast (~100-500ms) and the
# real-world ritual workload doesn't stack mutations densely enough to
# benefit. Simpler is better here — easier to reason about, no chance of
# deadlock from cross-note dependencies (e.g., the cross-note effects of
# a `migrate` decision touching two notes at once).
_LOCK_FILENAME = "mutation.lock"


@contextmanager
def mutation_lock(run_dir: Path) -> Iterator[None]:
    """Acquire the cross-process scribe mutation lock for the duration of
    the `with` block.

    Blocks indefinitely if another process holds the lock. For the actual
    ritual workload that's the right semantics — mutations are fast and
    queueing is cheaper than retry-with-backoff fairness games.

    Args:
        run_dir: Plugin-local runtime state directory. The lock file
            (`mutation.lock`) lives here and is created on first call.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / _LOCK_FILENAME

    # Open in append mode so the file is created if missing without
    # truncating it; multiple processes opening for write don't conflict
    # at the open() layer — the flock() call is what serializes them.
    with open(lock_path, "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            # Explicit unlock isn't strictly required (close() releases),
            # but being explicit matches the read pattern callers expect.
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
