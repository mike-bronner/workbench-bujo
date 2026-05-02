"""Tests for the bujo_apply_decisions:update_unrecognized op — added in 0.10.0.

Replaces an UnrecognizedLine's raw_html in place. Used by the habit
tracker to mutate the table that lives on the monthly note (a
`<div><object><table>...</table></object><br></div>` block that the
parser preserves as UnrecognizedLine).

Match by `anchor`: substring of the line's raw_html.
- 0 matches → NOT_FOUND in `unmatched`
- 1 match → replace + DiffChanged
- 2+ matches → AMBIGUOUS_BULLET in `unmatched`
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import UnrecognizedLine
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    DecisionUpdateUnrecognized,
)
from bujo_scribe_mcp.tools import apply_decisions


_TABLE_BEFORE = (
    "<div><object><table cellspacing=\"0\"><tbody>"
    "<tr><td><div><b>Day</b></div></td></tr>"
    "<tr><td><div>1</div></td></tr>"
    "</tbody></table></object><br></div>"
)
_TABLE_AFTER = (
    "<div><object><table cellspacing=\"0\"><tbody>"
    "<tr><td><div><b>Day</b></div></td></tr>"
    "<tr><td><div>1</div></td></tr>"
    "<tr><td><div>2</div></td></tr>"
    "</tbody></table></object><br></div>"
)


def test_update_unrecognized_replaces_raw_html(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Some other task"),
            UnrecognizedLine(raw_html=_TABLE_BEFORE),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateUnrecognized(
                    op="update_unrecognized",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    # The note should now contain the new table HTML.
    backend = ctx.backend
    ref = backend.find_by_title("sample-note")
    note = backend.read(ref)
    assert _TABLE_AFTER in note.content
    assert _TABLE_BEFORE not in note.content


def test_update_unrecognized_returns_diff_changed(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [UnrecognizedLine(raw_html=_TABLE_BEFORE)],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateUnrecognized(
                    op="update_unrecognized",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.diff.changed) == 1
    assert out.diff.changed[0].before == _TABLE_BEFORE
    assert out.diff.changed[0].after == _TABLE_AFTER


def test_update_unrecognized_not_found(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [make_bujo_line("task", "Just a task — no table here")],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateUnrecognized(
                    op="update_unrecognized",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "NOT_FOUND"


def test_update_unrecognized_ambiguous(
    make_backend, make_context, render_body, make_bujo_line
):
    """Two UnrecognizedLines whose raw_html both contain the anchor →
    AMBIGUOUS_BULLET. Caller must pick a more specific anchor."""
    body = render_body(
        "sample-note",
        [
            UnrecognizedLine(raw_html=_TABLE_BEFORE),
            UnrecognizedLine(raw_html=_TABLE_BEFORE.replace("Day", "Date")),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateUnrecognized(
                    op="update_unrecognized",
                    anchor="<object><table",  # matches both
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "AMBIGUOUS_BULLET"


def test_update_unrecognized_round_trips_through_render(
    make_backend, make_context, render_body, make_bujo_line
):
    """After the update, re-reading the note via the standard path should
    return the new HTML as an UnrecognizedLine again — no formatting
    damage on round-trip."""
    body = render_body(
        "sample-note",
        [UnrecognizedLine(raw_html=_TABLE_BEFORE)],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateUnrecognized(
                    op="update_unrecognized",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    # Apply a no-op: a second update with the same anchor + same new_html.
    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateUnrecognized(
                    op="update_unrecognized",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )
    # No unmatched — the table is still findable after the first update's render.
    assert not out.unmatched
