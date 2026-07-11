"""Guards the "scheduled task is local-only" invariant in bujo-setup.

The scheduled task is a local construct (``~/Documents/Claude/Scheduled/``, run
by the desktop app's scheduler) and the ritual reads/writes Apple Notes on the
Mac. Deploying it from a cloud session plants a task that can never fire. So
``/workbench-bujo:bujo-setup`` must:

  * probe the scheduled-tasks MCP in Step 1.3 and set a ``SCHEDULING_AVAILABLE``
    flag *without* making the probe a hard prerequisite that stops setup, and
  * gate the deploy (Step 6) and legacy-cleanup (Step 7) steps on that flag,

so a cloud run still writes config but skips the task, and a local run
(desktop app / Cowork / CLI) deploys it as before.

An LLM-driven setup can't be run deterministically in CI, so — exactly as
``test_ritual_interactivity.py`` does for the ritual protocol — these tests
assert the *prompt-file invariant that drives the correct behavior*.
"""

from __future__ import annotations

from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root
REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "commands" / "bujo-setup.md"

# The flag name the probe sets and the gated steps read.
FLAG = "scheduling_available"


def _text() -> str:
    return SETUP.read_text().lower()


def _section(heading_needle: str) -> str:
    """Return the text of the ``## Step ...`` section whose heading contains
    ``heading_needle`` (case-insensitive), up to the next ``## `` heading."""
    text = SETUP.read_text()
    lines = text.splitlines()
    start = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("## ") and heading_needle.lower() in ln.lower()
    )
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).lower()


def test_probe_sets_flag_and_never_stops_setup():
    # Step 1.3 probes the scheduled-tasks MCP, sets SCHEDULING_AVAILABLE both
    # ways, and explicitly does not treat it as a blocker.
    prereqs = _section("Check Prerequisites")
    assert "list_scheduled_tasks" in prereqs
    assert f"{FLAG} = true" in prereqs
    assert f"{FLAG} = false" in prereqs
    # The probe must be described as non-blocking, so a cloud run continues.
    assert "not a blocker" in prereqs
    assert "do not stop" in prereqs
    assert "never stops setup" in prereqs


def test_deploy_step_is_gated_on_the_flag():
    # Step 6 must only deploy when SCHEDULING_AVAILABLE is true and must skip
    # otherwise — never deploy unconditionally.
    deploy = _section("Deploy the Scheduled Task")
    assert f"{FLAG} == true" in deploy
    assert "skip" in deploy
    assert "local only" in deploy


def test_cleanup_step_is_gated_on_the_flag():
    # Step 7 (legacy cleanup) touches the local scheduler + local filesystem,
    # so it must be gated on the same flag.
    cleanup = _section("Legacy Cleanup")
    assert f"{FLAG} == true" in cleanup
    assert "skip" in cleanup


def test_scheduled_tasks_mcp_is_not_a_hard_prerequisite():
    # Only the core plugin and the scribe MCP block setup. The scheduled-tasks
    # MCP must not be listed among the hard blockers.
    prereqs = _section("Check Prerequisites")
    assert "only prerequisites 1 and 2 are blockers" in prereqs
