"""Tests for bujo.scan's date-based filters — added in 0.9.5.

The pre-0.9.5 filter only checked the inline `[YYYY-MM-DD]` date and
did not exclude already-resolved lines. That meant the daily ritual's
Future Log surface step picked up the same entry every morning forever
— migrated entries kept matching `surfaces_today` and getting
re-migrated, polluting today's note with duplicates.

These tests pin the corrected behavior:
- `surfaces_today` / `due_today` / `overdue` exclude `migrated`,
  `completed`, and dropped lines.
- `scheduled` (`<`) IS included — that's the whole point of the
  scheduled-then-surface Future Log lifecycle.
"""

from __future__ import annotations

from bujo_scribe_mcp.schemas import ScanFilter, ScanInput
from bujo_scribe_mcp.tools import scan


_TODAY = "2026-05-02"
_YESTERDAY = "2026-05-01"


def _scan_status(ctx, status: str, scope=None):
    return scan.execute(
        ScanInput(
            scope=scope or ["sample-note"],
            filter=ScanFilter(status=status, date=_TODAY),
        ),
        ctx=ctx,
    )


def test_surfaces_today_includes_scheduled(make_backend, make_context, render_body, make_bujo_line):
    """A scheduled (`<`) entry with today's date is the canonical
    surfaces_today match — that's what the Future Log uses."""
    body = render_body(
        "sample-note",
        [
            make_bujo_line("scheduled", f"[{_TODAY}] Visit dentist  (from yesterday)"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "surfaces_today")
    assert len(out.items) == 1
    assert "Visit dentist" in out.items[0].text


def test_surfaces_today_includes_open_task(make_backend, make_context, render_body, make_bujo_line):
    """An open task with today's inline date still surfaces — manually
    added Future Log entries (without going through the schedule op)
    typically have signifier task."""
    body = render_body(
        "sample-note",
        [make_bujo_line("task", f"[{_TODAY}] Pick up package")],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "surfaces_today")
    assert len(out.items) == 1
    assert "Pick up package" in out.items[0].text


def test_surfaces_today_excludes_migrated(make_backend, make_context, render_body, make_bujo_line):
    """The bug being fixed: a migrated entry on the Future Log must NOT
    re-surface. Once it's been pulled forward, it's done."""
    body = render_body(
        "sample-note",
        [
            make_bujo_line("migrated", f"[{_TODAY}] Already pulled forward"),
            make_bujo_line("scheduled", f"[{_TODAY}] Still waiting"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "surfaces_today")
    assert len(out.items) == 1
    assert "Still waiting" in out.items[0].text


def test_surfaces_today_excludes_completed(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("completed", f"[{_TODAY}] Already done"),
            make_bujo_line("task", f"[{_TODAY}] Still to do"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "surfaces_today")
    assert len(out.items) == 1
    assert "Still to do" in out.items[0].text


def test_surfaces_today_excludes_dropped(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", f"[{_TODAY}] Cancelled trip", dropped=True),
            make_bujo_line("task", f"[{_TODAY}] Still on"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "surfaces_today")
    assert len(out.items) == 1
    assert "Still on" in out.items[0].text


def test_overdue_excludes_resolved(make_backend, make_context, render_body, make_bujo_line):
    """Same exclusion logic for overdue — once you've migrated yesterday's
    entry, it shouldn't keep showing up as overdue."""
    body = render_body(
        "sample-note",
        [
            make_bujo_line("migrated", f"[{_YESTERDAY}] Pulled forward yesterday"),
            make_bujo_line("scheduled", f"[{_YESTERDAY}] Genuinely overdue"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "overdue")
    assert len(out.items) == 1
    assert "Genuinely overdue" in out.items[0].text


def test_due_today_alias_for_surfaces_today(make_backend, make_context, render_body, make_bujo_line):
    """due_today and surfaces_today share the same filter logic; both
    should exclude resolved entries."""
    body = render_body(
        "sample-note",
        [
            make_bujo_line("migrated", f"[{_TODAY}] Already moved"),
            make_bujo_line("scheduled", f"[{_TODAY}] Live"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = _scan_status(ctx, "due_today")
    assert len(out.items) == 1
    assert "Live" in out.items[0].text
