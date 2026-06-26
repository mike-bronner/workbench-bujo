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

import pytest

from bujo_scribe_mcp.backends.base import BackendError
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


# ---------------------------------------------------------------------------
# AC #3 — the source deletion must not commit before the target append
# ---------------------------------------------------------------------------


def test_surface_target_write_failure_keeps_source_entry(
    make_backend, make_context, render_body, make_bujo_line
):
    """If the target-note append fails, the Future Log entry must survive.

    `surface` physically deletes its source branch, so committing the source
    before the target append is durable would lose the entry from *both* notes
    on a mid-sequence failure — the *"…or neither"* state AC #3 prohibits. The
    target append is made durable first, so a failure here leaves the source
    entry intact (a recoverable duplicate-or-nothing, never a lost task).
    """
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("scheduled", f"[{TODAY}] Renew the passport")],
    )
    target_body = render_body("Target Note", [make_bujo_line("task", "Existing task")])
    backend = make_backend({FUTURE_LOG_TITLE: fl_body, "Target Note": target_body})
    ctx = make_context(backend)

    # Make the target-note write fail; the Future Log write stays reachable.
    real_update = backend.update

    def failing_update(ref, content):
        if ref.id == "Target Note":
            raise BackendError("simulated target write failure")
        return real_update(ref, content)

    backend.update = failing_update  # type: ignore[method-assign]

    with pytest.raises(BackendError, match="simulated target write failure"):
        _surface(ctx, "Renew the passport")

    # Source survived — the entry is still on the Future Log, still scheduled,
    # NOT deleted. Better a stuck-but-present entry than a vanished task.
    fl_lines = _bujo_lines(ctx, FUTURE_LOG_TITLE)
    assert len(fl_lines) == 1
    assert "Renew the passport" in fl_lines[0].text
    assert fl_lines[0].signifier == "scheduled"


# ---------------------------------------------------------------------------
# AC #4 — overdue Future Log items surface the same way as due-today ones
# ---------------------------------------------------------------------------


def test_surface_overdue_entry_removed_and_tasked(
    make_backend, make_context, render_body, make_bujo_line
):
    """An OVERDUE entry (inline date in the past) surfaces identically: removed
    from the Future Log, appended to the target as a `task` — never a `>`."""
    overdue_date = "2020-01-01"
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [make_bujo_line("scheduled", f"[{overdue_date}] Pay the overdue invoice")],
    )
    ctx = make_context(make_backend({FUTURE_LOG_TITLE: fl_body}))

    # The `overdue` scan surfaces it (date < today).
    before = scan.execute(
        ScanInput(scope=["future_log"], filter=ScanFilter(status="overdue", date=TODAY)),
        ctx=ctx,
    )
    assert len(before.items) == 1

    out = _surface(ctx, "Pay the overdue invoice")
    assert not out.unmatched

    # Source: gone entirely (not marked `>`).
    assert _bujo_lines(ctx, FUTURE_LOG_TITLE) == []

    # Target: a fresh open task, not a migrated stub.
    carried = _line(_bujo_lines(ctx, "Target Note"), "Pay the overdue invoice")
    assert carried.signifier == "task"

    # The overdue scan now returns nothing — the entry is gone, not filtered.
    after = scan.execute(
        ScanInput(scope=["future_log"], filter=ScanFilter(status="overdue", date=TODAY)),
        ctx=ctx,
    )
    assert after.items == []


# ---------------------------------------------------------------------------
# AMBIGUOUS_BULLET — no partial mutation on either note
# ---------------------------------------------------------------------------


def test_surface_ambiguous_bullet_mutates_neither_note(
    make_backend, make_context, render_body, make_bujo_line
):
    """The contract promises NOT_FOUND *and* AMBIGUOUS_BULLET both mutate
    neither note. Two Future Log entries sharing a text substring make the
    match ambiguous — `surface` must no-op on both notes."""
    fl_body = render_body(
        FUTURE_LOG_TITLE,
        [
            make_bujo_line("scheduled", f"[{TODAY}] Call the dentist about a cleaning"),
            make_bujo_line("scheduled", f"[{TODAY}] Call the dentist again"),
        ],
    )
    target_body = render_body("Target Note", [make_bujo_line("task", "Existing task")])
    ctx = make_context(
        make_backend({FUTURE_LOG_TITLE: fl_body, "Target Note": target_body})
    )

    # "Call the dentist" is a substring of BOTH entries, an exact match of
    # neither → ambiguous.
    out = _surface(ctx, "Call the dentist")

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "AMBIGUOUS_BULLET"

    # Source: both entries still present, still scheduled.
    fl_lines = _bujo_lines(ctx, FUTURE_LOG_TITLE)
    assert len(fl_lines) == 2
    assert all(line.signifier == "scheduled" for line in fl_lines)

    # Target: nothing appended.
    target_lines = _bujo_lines(ctx, "Target Note")
    assert len(target_lines) == 1
    assert target_lines[0].text == "Existing task"
