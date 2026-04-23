"""bujo.summarize — produce a formatted summary block.

Pure transform — no storage I/O. Accepts a packet of pre-fetched data and
renders it into either a display-format string (tight, human-readable) or
a note-format string (Apple Notes HTML-safe).

Supported kinds:
- `daily_morning`  morning summary shown to Mike at the end of the daily ritual
- `weekly_retro`   weekly-summary block (post-roll-up)
- `monthly_retro`  monthly-summary block
- `yearly_retro`   yearly-summary block

Unknown packet keys are ignored. Missing keys degrade gracefully.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.schemas import SummarizeInput, SummarizeOutput


def execute(input: SummarizeInput, *, ctx: Context) -> SummarizeOutput:
    if input.kind == "daily_morning":
        return _daily_morning(input, ctx=ctx)
    if input.kind == "weekly_retro":
        return _retro(input, ctx=ctx, label="Weekly Retrospective")
    if input.kind == "monthly_retro":
        return _retro(input, ctx=ctx, label="Monthly Retrospective")
    if input.kind == "yearly_retro":
        return _retro(input, ctx=ctx, label="Yearly Retrospective")
    raise ValueError(f"Unknown summary kind: {input.kind}")


# ---------------------------------------------------------------------------
# daily_morning
# ---------------------------------------------------------------------------


def _daily_morning(input: SummarizeInput, *, ctx: Context) -> SummarizeOutput:
    packet = input.packet
    reference_date = _resolve_date(packet.get("date"), ctx.rules.timezone)
    weekday = packet.get("weekday") or reference_date.strftime("%A")
    date_str = reference_date.isoformat()

    yesterday_stats = packet.get("yesterday_stats") or {}
    completed = int(yesterday_stats.get("completed", 0))
    migrated = int(yesterday_stats.get("migrated", 0))
    dropped = int(yesterday_stats.get("dropped", 0))

    today_schedule = _as_list(packet.get("today_schedule"))
    migrated_items = _as_list(packet.get("migrated"))
    future_surfaced = _as_list(packet.get("future_surfaced"))

    stats: dict[str, Any] = {
        "date": date_str,
        "weekday": weekday,
        "yesterday": {"completed": completed, "migrated": migrated, "dropped": dropped},
        "counts": {
            "schedule": len(today_schedule),
            "migrated": len(migrated_items),
            "future_surfaced": len(future_surfaced),
        },
    }

    block_lines: list[str] = []
    block_lines.append(f"📅 {weekday}, {date_str}")
    block_lines.append("")
    block_lines.append(f"Yesterday: {completed} completed, {migrated} migrated, {dropped} dropped")
    block_lines.append("")
    block_lines.append("Today's schedule:")
    block_lines.extend(_bulleted(today_schedule, empty_msg="Nothing on the calendar"))
    block_lines.append("")
    block_lines.append("Migrated from yesterday:")
    block_lines.extend(_bulleted(migrated_items, empty_msg="Nothing carried forward"))
    block_lines.append("")
    block_lines.append("Future Log surfaced:")
    block_lines.extend(_bulleted(future_surfaced, empty_msg="None"))

    block = _render(block_lines, input.format)
    return SummarizeOutput(block=block, stats=stats)


# ---------------------------------------------------------------------------
# weekly / monthly / yearly retros
# ---------------------------------------------------------------------------


def _retro(input: SummarizeInput, *, ctx: Context, label: str) -> SummarizeOutput:
    packet = input.packet
    highlights = _as_list(packet.get("highlights"))
    insights = _as_list(packet.get("insights"))
    completed = _as_list(packet.get("completed"))
    open_items = _as_list(packet.get("open") or packet.get("open_items"))
    goals = _as_list(packet.get("goals"))
    future_log = _as_list(packet.get("future_log"))
    period = packet.get("period") or ""

    block_lines: list[str] = []
    head = f"{label}"
    if period:
        head += f" — {period}"
    block_lines.append(head)
    block_lines.append("")

    for heading, items in [
        ("Highlights", highlights),
        ("Completed", completed),
        ("Insights", insights),
        ("Open items", open_items),
        ("Goals", goals),
        ("Future Log", future_log),
    ]:
        if not items:
            continue
        block_lines.append(f"{heading}:")
        block_lines.extend(_bulleted(items, empty_msg=""))
        block_lines.append("")

    block = _render(block_lines, input.format)
    stats: dict[str, Any] = {
        "label": label,
        "period": period,
        "counts": {
            "highlights": len(highlights),
            "completed": len(completed),
            "insights": len(insights),
            "open": len(open_items),
            "goals": len(goals),
            "future_log": len(future_log),
        },
    }
    return SummarizeOutput(block=block.rstrip() + "\n", stats=stats)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _bulleted(items: list[str], *, empty_msg: str) -> list[str]:
    if not items:
        return [f"- {empty_msg}"] if empty_msg else []
    return [f"- {item}" for item in items]


def _render(block_lines: list[str], format: str) -> str:
    if format == "display":
        return "\n".join(block_lines).rstrip() + "\n"
    # format == "note" — Apple Notes HTML-safe rendering
    return "\n".join(
        _wrap_html_line(line) for line in block_lines
    )


def _wrap_html_line(line: str) -> str:
    if line == "":
        return "<div><br></div>"
    return f"<div>{html.escape(line)}</div>"


def _resolve_date(iso: str | None, tz_name: str) -> date:
    if iso is not None:
        return date.fromisoformat(iso)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()
