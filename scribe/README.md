# 🖋️ bujo-scribe-mcp

MCP server that executes Bullet Journal rituals against a pluggable notebook backend.
Implements the scribe vocabulary (`read`, `scaffold`, `apply-decisions`, `scan`, `summarize`)
defined in the [scribe contract](../docs/scribe-contract.md).

Ships with an Apple Notes backend for macOS. Backend layer is abstract — Obsidian, plain
markdown, Notion, etc. can be added without changing tool-level logic.

## Source-in-repo

This MCP lives **inside** the `workbench-bujo` plugin. Sessions launch it via:

```
uv run --project ${CLAUDE_PLUGIN_ROOT}/scribe bujo-scribe-mcp serve
```

`uv` resolves dependencies from this `pyproject.toml`, creates a cached venv on first
run, and reuses it on every subsequent session. No build step, no wheel ship.

## Local dev

```bash
cd scribe
uv run bujo-scribe-mcp --version    # smoke test
uv run pytest                       # if tests are present
```

Edit anything under `src/bujo_scribe_mcp/`, restart the Claude Code session, and the
changes are live.
