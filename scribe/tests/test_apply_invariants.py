"""Invariant tests for ``bujo_apply_decisions`` mutation ops.

These pin the signifier/prefix-preservation contract across the mutation
surface — the properties the ritual skill relies on but that no single
op-specific test asserted before:

(a) ``update`` rewrites text only — signifier and prefix survive.
(b) ``complete`` / ``migrate`` / ``schedule`` / ``combine`` preserve the
    source bullet's prefix on the source line AND on every carried line
    (migrate's target copy, schedule's Future Log entry, combine's
    sub-item). The schedule case pins the 0.11.x bug where the Future Log
    entry was built without ``prefix=target.prefix`` and silently lost a
    ``✽`` priority on schedule-forward.
(c) ``add`` never invents a prefix — an unset ``Bullet.prefix`` stays None.
(d) combine semantics — the source becomes ``migrated`` (never dropped or
    removed) and the carried copy nests as a depth-1 sub-item directly
    under the target parent, prefix preserved.

All assertions run against re-parsed backend state (``parse_note`` on what
the FakeBackend stored), so they cover the full mutate → render → parse
round-trip, not just the in-memory mutation.
"""

from __future__ import annotations

import pytest

from bujo_scribe_mcp.parsing import BujoLine, parse_note
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    Bullet,
    DecisionAdd,
    DecisionCombine,
    DecisionComplete,
    DecisionMigrate,
    DecisionSchedule,
    DecisionUpdate,
)
from bujo_scribe_mcp.tools import apply_decisions


FUTURE_LOG_TITLE = "Future Log"  # rules.future_log.note_title default
FAR_FUTURE = "2999-01-01"  # always strictly future — schedule's Gap-2 guard


def _bujo_lines(ctx, title: str) -> list[BujoLine]:
    """Re-read a note from the backend and return its parsed BujoLines."""
    ref = ctx.backend.find_by_title(title)
    assert ref is not None, f"note missing from backend: {title}"
    note = ctx.backend.read(ref)
    parsed = parse_note(note.content, rules=ctx.rules)
    return [line for line in parsed.lines if isinstance(line, BujoLine)]


def _line(lines: list[BujoLine], needle: str) -> BujoLine:
    matches = [line for line in lines if needle in line.text]
    assert len(matches) == 1, f"expected exactly one line matching {needle!r}: {matches}"
    return matches[0]


# ---------------------------------------------------------------------------
# (a) update preserves signifier + prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("signifier", "prefix"),
    [("task", "priority"), ("note", "inspiration"), ("event", None)],
)
def test_update_preserves_signifier_and_prefix(
    make_backend, make_context, render_body, make_bujo_line, signifier, prefix
):
    body = render_body(
        "sample-note",
        [make_bujo_line(signifier, "Ship the launcher", prefix=prefix)],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdate(
                    op="update",
                    bullet="Ship the launcher",
                    new_text="Ship the launcher v2",
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    line = _line(_bujo_lines(ctx, "sample-note"), "Ship the launcher v2")
    assert line.signifier == signifier
    assert line.prefix == prefix


# ---------------------------------------------------------------------------
# (b) complete / migrate / schedule / combine preserve prefixes
# ---------------------------------------------------------------------------


def test_complete_preserves_prefix(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [make_bujo_line("task", "Pay the electric bill", prefix="priority")],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[DecisionComplete(op="complete", bullet="Pay the electric bill")],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    line = _line(_bujo_lines(ctx, "sample-note"), "Pay the electric bill")
    assert line.signifier == "completed"
    assert line.prefix == "priority"


def test_migrate_preserves_prefix_on_source_and_carried_lines(
    make_backend, make_context, render_body, make_bujo_line
):
    source_body = render_body(
        "source-note",
        [
            make_bujo_line("task", "Ship the orchestrator", prefix="priority"),
            make_bujo_line("sub_item", "Wire up the resolver", prefix="explore", depth=1),
        ],
    )
    target_body = render_body("target-note", [make_bujo_line("task", "Existing task")])
    ctx = make_context(
        make_backend({"source-note": source_body, "target-note": target_body})
    )

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="source-note",
            decisions=[
                DecisionMigrate(
                    op="migrate", bullet="Ship the orchestrator", target="target-note"
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched

    source_lines = _bujo_lines(ctx, "source-note")
    parent = _line(source_lines, "Ship the orchestrator")
    child = _line(source_lines, "Wire up the resolver")
    assert parent.signifier == "migrated"
    assert parent.prefix == "priority"
    assert child.signifier == "migrated"
    assert child.prefix == "explore"

    target_lines = _bujo_lines(ctx, "target-note")
    carried_parent = _line(target_lines, "Ship the orchestrator")
    carried_child = _line(target_lines, "Wire up the resolver")
    assert carried_parent.signifier == "task"  # re-opens on the target
    assert carried_parent.prefix == "priority"
    assert carried_child.signifier == "sub_item"
    assert carried_child.prefix == "explore"
    assert carried_child.depth == 1


def test_schedule_preserves_prefix_on_source_and_future_log_entry(
    make_backend, make_context, render_body, make_bujo_line
):
    """Schedule-forward must not lose a ✽ priority — pins the bug where
    apply_schedule built the Future Log entry without the source bullet's
    prefix (unlike migrate/combine, which carried it)."""
    body = render_body(
        "source-note",
        [make_bujo_line("task", "Renew the passport", prefix="priority")],
    )
    ctx = make_context(make_backend({"source-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="source-note",
            decisions=[
                DecisionSchedule(op="schedule", bullet="Renew the passport", date=FAR_FUTURE),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched

    source_line = _line(_bujo_lines(ctx, "source-note"), "Renew the passport")
    assert source_line.signifier == "scheduled"
    assert source_line.prefix == "priority"

    fl_entry = _line(_bujo_lines(ctx, FUTURE_LOG_TITLE), "Renew the passport")
    assert f"[{FAR_FUTURE}]" in fl_entry.text
    assert fl_entry.signifier == "scheduled"
    assert fl_entry.prefix == "priority"


# ---------------------------------------------------------------------------
# (c) add ops never receive a default prefix
# ---------------------------------------------------------------------------


def test_add_without_prefix_stays_unprefixed(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body("sample-note", [make_bujo_line("task", "Existing task")])
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAdd(
                    op="add",
                    section="Captures",
                    bullet=Bullet(signifier="task", text="A plain new task"),
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    line = _line(_bujo_lines(ctx, "sample-note"), "A plain new task")
    assert line.prefix is None


def test_add_with_explicit_prefix_round_trips(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body("sample-note", [make_bujo_line("task", "Existing task")])
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAdd(
                    op="add",
                    section="Captures",
                    bullet=Bullet(
                        signifier="note",
                        text="Contract tests are the proving ground",
                        prefix="inspiration",
                    ),
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    line = _line(_bujo_lines(ctx, "sample-note"), "Contract tests are the proving ground")
    assert line.signifier == "note"
    assert line.prefix == "inspiration"


# ---------------------------------------------------------------------------
# (d) combine semantics — source migrated, sub-item nested under parent
# ---------------------------------------------------------------------------


def test_combine_source_becomes_migrated_never_dropped_or_removed(
    make_backend, make_context, render_body, make_bujo_line
):
    source_body = render_body(
        "source-note",
        [
            make_bujo_line("task", "Narrow implementation detail", prefix="priority"),
            make_bujo_line("task", "Unrelated other task"),
        ],
    )
    target_body = render_body("target-note", [make_bujo_line("task", "Umbrella task")])
    ctx = make_context(
        make_backend({"source-note": source_body, "target-note": target_body})
    )

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="source-note",
            decisions=[
                DecisionCombine(
                    op="combine",
                    bullet="Narrow implementation detail",
                    target_note="target-note",
                    parent_bullet="Umbrella task",
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched

    source_lines = _bujo_lines(ctx, "source-note")
    # Never removed: both source lines still present.
    assert len(source_lines) == 2
    source_line = _line(source_lines, "Narrow implementation detail")
    # Migrated — combine is "keep it, as a child elsewhere", NOT "let it go".
    assert source_line.signifier == "migrated"
    assert source_line.dropped is False
    assert source_line.prefix == "priority"


def test_combine_nests_sub_item_directly_under_parent_with_prefix(
    make_backend, make_context, render_body, make_bujo_line
):
    source_body = render_body(
        "source-note",
        [make_bujo_line("task", "Narrow implementation detail", prefix="priority")],
    )
    target_body = render_body(
        "target-note",
        [
            make_bujo_line("task", "Umbrella task"),
            make_bujo_line("task", "Later sibling task"),
        ],
    )
    ctx = make_context(
        make_backend({"source-note": source_body, "target-note": target_body})
    )

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="source-note",
            decisions=[
                DecisionCombine(
                    op="combine",
                    bullet="Narrow implementation detail",
                    target_note="target-note",
                    parent_bullet="Umbrella task",
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched

    target_lines = _bujo_lines(ctx, "target-note")
    parent_idx = target_lines.index(_line(target_lines, "Umbrella task"))
    sub_item = target_lines[parent_idx + 1]
    # Inserted immediately after the parent, before the later sibling.
    assert "Narrow implementation detail" in sub_item.text
    assert sub_item.signifier == "sub_item"
    assert sub_item.depth == 1
    assert sub_item.prefix == "priority"
    assert "Later sibling task" in target_lines[parent_idx + 2].text
