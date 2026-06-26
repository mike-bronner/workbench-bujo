"""Tests for the `surface` decision op — Future Log → daily-note surfacing.

`surface` is the inverse of `schedule`: when a Future Log entry comes due it
moves onto the day's note AND is **removed** from the Future Log entirely.
Unlike `migrate`, it leaves no `>` (migrated) stub — the Future Log only ever
holds pending scheduled entries, never historical or resolved ones.

These pin the contract from issue #14:
- Surfacing removes the source branch from the Future Log and appends a fresh
  task to the target note (atomic, single call).
- A `scheduled` (`<`) entry re-opens as a `task` (`•`); an `event` stays an
  `event`; sub-items carry as `sub_item`. Provenance text + prefix preserved.
- The NOT_FOUND path mutates neither note.
- After surfacing, `bujo_scan(surfaces_today)` returns nothing — the entry is
  gone, not merely excluded by the scan filter.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import BujoLine, parse_note
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    DecisionSurface,
    ScanFilter,
    ScanInput,
)
from bujo_scribe_mcp.tools import apply_decisions, scan


FUTURE_LOG_TITLE = "Future Log"  # rules.future_log.note_title default
TODAY = "2026-05-02"


def _bujo_lines(ctx, title: str) -> list[BujoLine]:
    ref = ctx.backend.find_by_title(title)
    assert ref is not None, f"note missing from backend: {title}"
    note = ctx.backend.read(ref)
    parsed = parse_note(note.content, rules=ctx.rules)
    return [line for line in parsed.lines if isinstance(line, BujoLine)]


def _line(lines: list[BujoLine], needle: str) -> BujoLine:
    matches = [line for line in lines if needle in line.text]
    assert len(matches) == 1, f"expected exactly one line matching {needle!r}: {matches}"
    return matches[0]


def _surface(ctx, bullet: str, target: str = "Target Note"):
    return apply_decisions.execute(
        ApplyDecisionsInput(
            note="future_log",
            decisions=[DecisionSurface(op="surface", bullet=bullet, target=target)],
        ),
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Core behaviour — remove from source, append to target
# ---------------------------------------------------------------------------


def test_surface_removes_source_and_appends_task(
    make_backend, make_context, render_body, make_bujo_line
):
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("scheduled", f"[{TODAY}] Renew the passport  (from yesterday)")],
    )
    target_body = render_body("Target Note", [make_bujo_line("task", "Existing task")])
    ctx = make_context(
        make_backend({FUTURE_LOG_TITLE: fl_body, "Target Note": target_body})
    )

    out = _surface(ctx, "Renew the passport")
    assert not out.unmatched

    # Source: the entry is GONE — not marked `>`, fully removed.
    fl_lines = _bujo_lines(ctx, FUTURE_LOG_TITLE)
    assert all("Renew the passport" not in line.text for line in fl_lines)
    assert all(line.signifier != "migrated" for line in fl_lines)

    # Target: a fresh OPEN task landed, carrying the provenance text.
    target_lines = _bujo_lines(ctx, "Target Note")
    carried = _line(target_lines, "Renew the passport")
    assert carried.signifier == "task"
    assert f"[{TODAY}]" in carried.text
    assert _line(target_lines, "Existing task")  # untouched

    # The cross-note effect is reported.
    assert any(eff.note == "Target Note" for eff in out.cross_note_effects)


def test_surface_preserves_prefix(
    make_backend, make_context, render_body, make_bujo_line
):
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("scheduled", f"[{TODAY}] File the taxes", prefix="priority")],
    )
    ctx = make_context(make_backend({FUTURE_LOG_TITLE: fl_body}))

    out = _surface(ctx, "File the taxes")
    assert not out.unmatched

    carried = _line(_bujo_lines(ctx, "Target Note"), "File the taxes")
    assert carried.signifier == "task"
    assert carried.prefix == "priority"


def test_surface_event_stays_event(
    make_backend, make_context, render_body, make_bujo_line
):
    """A Future Log `event` surfaces as an event on the day, not a task."""
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("event", f"[{TODAY}] Dentist appointment")],
    )
    ctx = make_context(make_backend({FUTURE_LOG_TITLE: fl_body}))

    out = _surface(ctx, "Dentist appointment")
    assert not out.unmatched

    carried = _line(_bujo_lines(ctx, "Target Note"), "Dentist appointment")
    assert carried.signifier == "event"


def test_surface_removes_entire_branch_with_subitems(
    make_backend, make_context, render_body, make_bujo_line
):
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [
            make_bujo_line("scheduled", f"[{TODAY}] Plan the launch  (from yesterday)"),
            make_bujo_line("sub_item", "Draft the announcement", depth=1),
            make_bujo_line("sub_item", "Line up reviewers", depth=1),
        ],
    )
    ctx = make_context(make_backend({FUTURE_LOG_TITLE: fl_body}))

    out = _surface(ctx, "Plan the launch")
    assert not out.unmatched

    # Source: parent AND both sub-items removed entirely.
    assert _bujo_lines(ctx, FUTURE_LOG_TITLE) == []

    # Target: parent re-opens as task, sub-items carry as sub_items at depth 1.
    target_lines = _bujo_lines(ctx, "Target Note")
    assert _line(target_lines, "Plan the launch").signifier == "task"
    draft = _line(target_lines, "Draft the announcement")
    assert draft.signifier == "sub_item"
    assert draft.depth == 1
    assert _line(target_lines, "Line up reviewers").signifier == "sub_item"


def test_surface_leaves_other_entries_untouched(
    make_backend, make_context, render_body, make_bujo_line
):
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [
            make_bujo_line("scheduled", f"[{TODAY}] Surface me"),
            make_bujo_line("scheduled", "[2099-01-01] Leave me alone"),
        ],
    )
    ctx = make_context(make_backend({FUTURE_LOG_TITLE: fl_body}))

    out = _surface(ctx, "Surface me")
    assert not out.unmatched

    fl_lines = _bujo_lines(ctx, FUTURE_LOG_TITLE)
    assert len(fl_lines) == 1
    remaining = fl_lines[0]
    assert "Leave me alone" in remaining.text
    assert remaining.signifier == "scheduled"  # still pending, untouched


# ---------------------------------------------------------------------------
# NOT_FOUND — no partial mutation on either note
# ---------------------------------------------------------------------------


def test_surface_not_found_mutates_neither_note(
    make_backend, make_context, render_body, make_bujo_line
):
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("scheduled", f"[{TODAY}] Renew the passport")],
    )
    target_body = render_body("Target Note", [make_bujo_line("task", "Existing task")])
    ctx = make_context(
        make_backend({FUTURE_LOG_TITLE: fl_body, "Target Note": target_body})
    )

    # Bullet text doesn't match anything on the Future Log (e.g. edited after
    # scheduling).
    out = _surface(ctx, "A bullet that does not exist")

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "NOT_FOUND"

    # Source unchanged — entry still present, still scheduled.
    fl_lines = _bujo_lines(ctx, FUTURE_LOG_TITLE)
    assert len(fl_lines) == 1
    assert fl_lines[0].signifier == "scheduled"

    # Target unchanged — nothing appended.
    target_lines = _bujo_lines(ctx, "Target Note")
    assert len(target_lines) == 1
    assert target_lines[0].text == "Existing task"


# ---------------------------------------------------------------------------
# AC #6 — after surfacing, the entry is GONE from the scan, not just filtered
# ---------------------------------------------------------------------------


def test_surface_then_scan_surfaces_today_returns_nothing(
    make_backend, make_context, render_body, make_bujo_line
):
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("scheduled", f"[{TODAY}] Renew the passport")],
    )
    ctx = make_context(make_backend({FUTURE_LOG_TITLE: fl_body}))

    # Before: the entry surfaces.
    before = scan.execute(
        ScanInput(
            scope=["future_log"],
            filter=ScanFilter(status="surfaces_today", date=TODAY),
        ),
        ctx=ctx,
    )
    assert len(before.items) == 1

    _surface(ctx, "Renew the passport")

    # After: the entry is gone — the scan returns nothing for the same day.
    after = scan.execute(
        ScanInput(
            scope=["future_log"],
            filter=ScanFilter(status="surfaces_today", date=TODAY),
        ),
        ctx=ctx,
    )
    assert after.items == []
