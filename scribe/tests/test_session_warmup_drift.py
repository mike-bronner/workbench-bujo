"""Tests for ``hooks/session-warmup.sh`` — version drift, skip guard, pre-warm.

The warmup hook warns at session start when the running plugin bundle
(``$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json``) is behind the newest
version installed in the CLI plugin cache
(``~/.claude/plugins/cache/claude-workbench/workbench-bujo/<version>/``).

This is the early-detection guard for the Cowork stale-bundle bug
(anthropics/claude-code#45810): the desktop app can keep serving an old
plugin bundle while the CLI is already current, silently routing the scribe
MCP to outdated code. The check lives in the hook (bash), so these tests
drive it as a subprocess.

The hook used to also emit the static BuJo routing block. That moved to
``session-warmup.md`` at the plugin root, aggregated by workbench-core — see
``test_session_warmup_contribution.py``. What remains here is the live half:
the Apple Notes pre-warm, the ``--agent`` skip guard, and the drift check.

Because the routing block is gone, the drift warning is now the hook's ONLY
observable output. Every skip-guard test therefore uses a *drifted* fixture:
against a current bundle the hook is silent anyway, so asserting on empty
output would pass whether or not the guard works.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root -> hooks/session-warmup.sh
HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-warmup.sh"
HOOKS_JSON = HOOK.parent / "hooks.json"
DRIFT_MARKER = "version drift"


def _make_bundle(root: Path, version: str) -> Path:
    bundle = root / "bundle"
    (bundle / ".claude-plugin").mkdir(parents=True)
    (bundle / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "workbench-bujo", "version": version})
    )
    return bundle


def _make_cache(home: Path, versions: list[str]) -> None:
    cache = (
        home / ".claude" / "plugins" / "cache" / "claude-workbench" / "workbench-bujo"
    )
    for version in versions:
        (cache / version).mkdir(parents=True)


def _make_drifted(tmp_path: Path) -> tuple[Path, Path]:
    """Home + bundle fixture guaranteed to emit the drift warning."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    _make_cache(home, ["0.6.0", "0.10.2"])
    return home, _make_bundle(tmp_path, "0.6.0")


def _make_current(tmp_path: Path) -> tuple[Path, Path]:
    """Home + bundle fixture matching the cache — the silent steady state."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    _make_cache(home, ["0.10.2"])
    return home, _make_bundle(tmp_path, "0.10.2")


def _run(home: Path, plugin_root: Path | None, agent: str | None = None) -> str:
    # Minimal env: real PATH so coreutils (sed/grep/sort) resolve, controlled
    # HOME so the cache lookup hits our fixture, optional CLAUDE_PLUGIN_ROOT.
    # The env dict is built from scratch, so CLAUDE_CODE_AGENT is unset unless
    # a test opts in — an --agent dispatch running this suite cannot leak it in
    # and silently turn every other test into a skip-guard assertion.
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    if agent is not None:
        env["CLAUDE_CODE_AGENT"] = agent
    result = subprocess.run(
        ["/bin/bash", str(HOOK)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Warmup must never fail the session, regardless of drift state.
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_warns_when_bundle_behind_cache(tmp_path):
    # 0.6.0 < 0.10.2 — the exact lexical-vs-numeric trap the comparison must
    # get right (plain string sort would rank 0.10.2 below 0.6.0).
    home, bundle = _make_drifted(tmp_path)
    out = _run(home, bundle)
    assert DRIFT_MARKER in out
    assert "v0.6.0" in out
    assert "v0.10.2" in out


def test_silent_when_bundle_current(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.6.0", "0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    assert DRIFT_MARKER not in _run(home, bundle)


def test_silent_when_bundle_ahead(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.11.0")
    assert DRIFT_MARKER not in _run(home, bundle)


def test_silent_when_no_cache(tmp_path):
    # Cowork-only setup: no CLI cache dir -> nothing to compare -> no warning.
    home = tmp_path / "home"
    home.mkdir()
    bundle = _make_bundle(tmp_path, "0.6.0")
    assert DRIFT_MARKER not in _run(home, bundle)


def test_silent_when_plugin_root_unset(tmp_path):
    # No bundle to read a version from -> the drift check no-ops rather than
    # dying under `set -u`.
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    assert _run(home, plugin_root=None) == ""


def test_emits_nothing_in_steady_state(tmp_path):
    # The whole point of the migration: with the routing block moved to
    # session-warmup.md, an undrifted session start injects NO context at all.
    # Any regression that re-adds a static block here shows up as output.
    home, bundle = _make_current(tmp_path)
    assert _run(home, bundle) == ""


def test_routing_block_no_longer_emitted_by_hook(tmp_path):
    # Explicit regression guard against the pre-migration payload coming back
    # into the hook, in either the drifted or the current state.
    for home, bundle in (
        _make_drifted(tmp_path / "drifted"),
        _make_current(tmp_path / "current"),
    ):
        out = _run(home, bundle)
        for moved in ("BuJo routing", "Trigger vocabulary", "Rules of the road"):
            assert moved not in out


def test_agent_dispatch_suppresses_drift_warning(tmp_path):
    # The guard sits above the drift check, so even a drifted bundle — the one
    # condition that produces output at all — stays silent.
    home, bundle = _make_drifted(tmp_path)
    assert _run(home, bundle, agent="workbench-dev-team:watson") == ""


def test_agent_dispatch_skip_is_agent_agnostic(tmp_path):
    # Any agent from any plugin, not a hardcoded roster. Drifted fixture, so
    # the assertion discriminates: without the guard each of these would warn.
    for agent in ("workbench-dev-team:holmes", "some-plugin:some-future-agent"):
        home, bundle = _make_drifted(tmp_path / agent.replace(":", "_"))
        assert _run(home, bundle, agent=agent) == ""


def test_interactive_session_still_warns_on_drift(tmp_path):
    # The other half of the guard: unset CLAUDE_CODE_AGENT must be untouched.
    home, bundle = _make_drifted(tmp_path)
    assert DRIFT_MARKER in _run(home, bundle)


def test_empty_agent_value_treated_as_interactive(tmp_path):
    # An exported-but-empty var is not a dispatch. `-n` must not skip here, or
    # a stray `export CLAUDE_CODE_AGENT=` would silently kill Mike's warmup.
    home, bundle = _make_drifted(tmp_path)
    assert DRIFT_MARKER in _run(home, bundle, agent="")


def test_notes_prewarm_runs_before_the_agent_guard():
    # Placement is deliberate: the Apple Notes launch is a silent, idempotent
    # side effect worth keeping for sub-agents that DO hit the journal, so it
    # must sit above the `CLAUDE_CODE_AGENT` early exit. Asserted on source
    # order — actually launching Notes is a side effect a test shouldn't have,
    # and it is unobservable on the Linux half of the CI matrix.
    lines = HOOK.read_text().splitlines()
    prewarm = next(i for i, line in enumerate(lines) if "osascript" in line)
    guard = next(i for i, line in enumerate(lines) if "CLAUDE_CODE_AGENT" in line)
    assert prewarm < guard


def test_hook_still_registered_for_session_start_and_compact():
    # The live half (pre-warm + drift) still needs a hook; only the static
    # routing block moved out to session-warmup.md.
    registrations = json.loads(HOOKS_JSON.read_text())["hooks"]
    assert "SessionStart" in registrations
    assert "PostCompact" in registrations


def test_capture_watch_nudge_fully_removed():
    # The UserPromptSubmit nudge is gone: no registration in hooks.json and
    # no orphaned script file left behind for a stale registration to find.
    registrations = json.loads(HOOKS_JSON.read_text())
    assert "UserPromptSubmit" not in registrations["hooks"]
    assert not (HOOK.parent / "capture-watch-nudge.sh").exists()
