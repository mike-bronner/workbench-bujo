"""Tests for the version-drift warning in ``hooks/session-warmup.sh``.

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


def _run(home: Path, plugin_root: Path | None) -> str:
    # Minimal env: real PATH so coreutils (sed/grep/sort) resolve, controlled
    # HOME so the cache lookup hits our fixture, optional CLAUDE_PLUGIN_ROOT.
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
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
