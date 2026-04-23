"""MCP server wiring.

Exposes the five scribe verbs as MCP tools over stdio. Rules are loaded once
at startup (default + user override merged & validated); the same immutable
`Context` is threaded to every tool invocation.
"""

from __future__ import annotations

import threading

from mcp.server.fastmcp import FastMCP

from bujo_scribe_mcp.backends import get_backend
from bujo_scribe_mcp.config import Config, load as load_config
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.rules import load_rules
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    ApplyDecisionsOutput,
    ReadInput,
    ReadOutput,
    ScaffoldInput,
    ScaffoldOutput,
    ScanInput,
    ScanOutput,
    SummarizeInput,
    SummarizeOutput,
)
from bujo_scribe_mcp.tools import apply_decisions, read, scaffold, scan, summarize


def build_context(config: Config | None = None) -> Context:
    """Assemble the runtime context — rules, backend, config."""
    cfg = config or load_config()
    rules = load_rules(user_path=cfg.user_rules_path)
    backend = get_backend(cfg.backend, folder=cfg.folder)
    return Context(config=cfg, rules=rules, backend=backend)


def build_server(context: Context | None = None) -> FastMCP:
    ctx = context or build_context()
    mcp = FastMCP(ctx.config.server_name)

    # Wake the backend in the background so the first real tool call doesn't
    # pay the cold-spawn cost (Apple Notes' AppleScript subsystem can take
    # several seconds the first time it's poked). Daemon thread — never
    # blocks shutdown, never fails the server.
    def _warm_backend() -> None:
        try:
            ctx.backend.folder_exists()
        except Exception:
            pass

    threading.Thread(target=_warm_backend, daemon=True, name="scribe-warmup").start()

    @mcp.tool(
        name="bujo_read",
        description=(
            "Fetch notes for a ritual's context packet. Read-only. Accepts "
            "canonical slugs (today, yesterday, index, future_log, etc.) or "
            "explicit note titles. Missing notes return exists=false."
        ),
    )
    def bujo_read(payload: ReadInput) -> ReadOutput:
        return read.execute(payload, ctx=ctx)

    @mcp.tool(
        name="bujo_scaffold",
        description=(
            "Create or merge a ritual entry. mode=create fails if the note "
            "exists; mode=merge reads fresh and diff-merges. Applies exact "
            "template, writing order, and signifier rules from the active "
            "rules.yaml. Rule-violating bullets are returned as warnings, "
            "never silently normalized."
        ),
    )
    def bujo_scaffold(payload: ScaffoldInput) -> ScaffoldOutput:
        return scaffold.execute(payload, ctx=ctx)

    @mcp.tool(
        name="bujo_apply_decisions",
        description=(
            "Apply mutations to an existing note: complete, migrate, "
            "schedule, drop, add, update, reorder. Reads the target note "
            "fresh immediately before writing. Ambiguous or missing bullet "
            "matches are returned in 'unmatched' and not applied. "
            "dry_run=true previews the diff without writing. Scheduling "
            "without a future date is rejected."
        ),
    )
    def bujo_apply_decisions(payload: ApplyDecisionsInput) -> ApplyDecisionsOutput:
        return apply_decisions.execute(payload, ctx=ctx)

    @mcp.tool(
        name="bujo_scan",
        description=(
            "Find open or due items across notes. Read-only. Returns items "
            "with stable anchors that can be passed back to bujo_apply_decisions."
        ),
    )
    def bujo_scan(payload: ScanInput) -> ScanOutput:
        return scan.execute(payload, ctx=ctx)

    @mcp.tool(
        name="bujo_summarize",
        description=(
            "Produce a formatted summary block (morning summary, weekly retro, "
            "etc.) from a packet. Pure transform — no storage I/O. Uses the "
            "summary template from the active rules for the given kind."
        ),
    )
    def bujo_summarize(payload: SummarizeInput) -> SummarizeOutput:
        return summarize.execute(payload, ctx=ctx)

    return mcp


def run_stdio() -> None:
    build_server().run()
