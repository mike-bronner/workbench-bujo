"""Tests for ``hooks/session-warmup.sh`` — version drift, payload, skip guard.

The warmup hook warns at session start when the running plugin bundle
(``$CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json``) is behind the newest
version installed in the CLI plugin cache
(``~/.claude/plugins/cache/claude-workbench/workbench-bujo/<version>/``).

This is the early-detection guard for the Cowork stale-bundle bug
(anthropics/claude-code#45810): the desktop app can keep serving an old
plugin bundle while the CLI is already current, silently routing the scribe
MCP to outdated code. The check lives in the hook (bash), so these tests
drive it as a subprocess.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root -> hooks/session-warmup.sh
HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-warmup.sh"
HOOKS_JSON = HOOK.parent / "hooks.json"
DRIFT_MARKER = "version drift"

# Context-payload budget. The warmup re-emits at every session start and
# PostCompact. This ceiling catches payload creep before it lands back in
# per-turn latency (the routing block emitted ~8.8KB before the 2026-06
# trim, ~5.6KB before the hook diet dropped the proactive-capture tiers).
WARMUP_BYTE_BUDGET = 4096


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
    home = tmp_path / "home"
    home.mkdir()
    # 0.6.0 < 0.10.2 — the exact lexical-vs-numeric trap the comparison must
    # get right (plain string sort would rank 0.10.2 below 0.6.0).
    _make_cache(home, ["0.6.0", "0.10.2"])
    bundle = _make_bundle(tmp_path, "0.6.0")
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
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    out = _run(home, plugin_root=None)
    assert DRIFT_MARKER not in out
    # The normal routing block still emits.
    assert "BuJo routing" in out


def test_routing_block_always_emitted(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    assert "BuJo routing" in _run(home, bundle)


def test_warmup_payload_under_budget(tmp_path):
    # No drift fixture — measures the steady-state routing block alone, the
    # payload every session actually pays.
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    payload = _run(home, bundle).encode("utf-8")
    assert len(payload) < WARMUP_BYTE_BUDGET


def test_habit_pointer_resolves_plugin_root(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    out = _run(home, bundle)
    assert f"{bundle}/skills/rituals/bujo-ritual.md" in out
    assert "Step 2.5" in out


def test_pointers_degrade_to_relative_without_plugin_root(tmp_path):
    # `set -u` + unset CLAUDE_PLUGIN_ROOT (manual runs, tests) must not kill
    # the warmup; the pointer falls back to a repo-relative path.
    home = tmp_path / "home"
    home.mkdir()
    out = _run(home, plugin_root=None)
    assert "skills/rituals/bujo-ritual.md" in out


def test_no_stale_proactive_capture_references(tmp_path):
    # The proactive-capture machinery (tiers, threshold dial, per-turn
    # capture-watch nudge) was removed in the 2026-06 hook diet. None of its
    # vocabulary may resurface in the emitted context block.
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    out = _run(home, bundle)
    for stale in ("Proactive capture", "capture-watch", "Threshold dial"):
        assert stale not in out


def test_agent_dispatch_emits_nothing(tmp_path):
    # CLAUDE_CODE_AGENT is set by Claude Code on every --agent dispatch. Those
    # sessions carry self-contained prompts; injecting the routing block wastes
    # tokens and breaks their prompt-cache prefix on every dispatch tick.
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    assert _run(home, bundle, agent="workbench-bujo:bujo-orchestrator") == ""


def test_agent_dispatch_suppresses_drift_warning(tmp_path):
    # The guard sits above the drift check, so even a drifted bundle — the one
    # condition that emits output before the routing block — stays silent.
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.6.0", "0.10.2"])
    bundle = _make_bundle(tmp_path, "0.6.0")
    out = _run(home, bundle, agent="workbench-dev-team:watson")
    assert out == ""
    assert DRIFT_MARKER not in out


def test_agent_dispatch_skip_is_agent_agnostic(tmp_path):
    # Any agent from any plugin, not a hardcoded roster.
    home = tmp_path / "home"
    home.mkdir()
    bundle = _make_bundle(tmp_path, "0.10.2")
    for agent in ("workbench-dev-team:holmes", "some-plugin:some-future-agent"):
        assert _run(home, bundle, agent=agent) == ""


def test_interactive_session_still_emits_routing_block(tmp_path):
    # The other half of the guard: unset CLAUDE_CODE_AGENT must be untouched.
    home = tmp_path / "home"
    home.mkdir()
    _make_cache(home, ["0.10.2"])
    bundle = _make_bundle(tmp_path, "0.10.2")
    out = _run(home, bundle)
    assert "BuJo routing" in out
    assert "Trigger vocabulary" in out


def test_empty_agent_value_treated_as_interactive(tmp_path):
    # An exported-but-empty var is not a dispatch. `-n` must not skip here, or
    # a stray `export CLAUDE_CODE_AGENT=` would silently kill Mike's warmup.
    home = tmp_path / "home"
    home.mkdir()
    bundle = _make_bundle(tmp_path, "0.10.2")
    assert "BuJo routing" in _run(home, bundle, agent="")


def test_capture_watch_nudge_fully_removed():
    # The UserPromptSubmit nudge is gone: no registration in hooks.json and
    # no orphaned script file left behind for a stale registration to find.
    registrations = json.loads(HOOKS_JSON.read_text())
    assert "UserPromptSubmit" not in registrations["hooks"]
    assert not (HOOK.parent / "capture-watch-nudge.sh").exists()
