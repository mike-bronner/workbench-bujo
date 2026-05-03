"""Tests for the bujo_apply_decisions:update_table op — added in 0.10.

Replaces a TableLine's raw_html in place. Used by the habit tracker to
mutate the table on the monthly note (a `<div><object><table>…</table></object><br></div>`
block that parses as TableLine).

Match by `anchor`: substring of the line's raw_html.
- 0 matches → NOT_FOUND in `unmatched`
- 1 match → replace + DiffChanged
- 2+ matches → AMBIGUOUS_BULLET in `unmatched`
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import TableLine
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    DecisionUpdateTable,
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


def test_update_table_replaces_raw_html(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Some other task"),
            TableLine(raw_html=_TABLE_BEFORE),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateTable(
                    op="update_table",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    backend = ctx.backend
    ref = backend.find_by_title("sample-note")
    note = backend.read(ref)
    assert _TABLE_AFTER in note.content
    assert _TABLE_BEFORE not in note.content


def test_update_table_returns_diff_changed(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [TableLine(raw_html=_TABLE_BEFORE)],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateTable(
                    op="update_table",
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


def test_update_table_not_found(
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
                DecisionUpdateTable(
                    op="update_table",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "NOT_FOUND"


def test_update_table_ambiguous(
    make_backend, make_context, render_body, make_bujo_line
):
    """Two TableLines whose raw_html both contain the anchor →
    AMBIGUOUS_BULLET. Caller must pick a more specific anchor."""
    body = render_body(
        "sample-note",
        [
            TableLine(raw_html=_TABLE_BEFORE),
            TableLine(raw_html=_TABLE_BEFORE.replace("Day", "Date")),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateTable(
                    op="update_table",
                    anchor="<object><table",  # matches both
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "AMBIGUOUS_BULLET"


def test_update_table_round_trips_through_render(
    make_backend, make_context, render_body, make_bujo_line
):
    """After the update, re-reading the note via the standard path should
    still find the table — no formatting damage on round-trip."""
    body = render_body(
        "sample-note",
        [TableLine(raw_html=_TABLE_BEFORE)],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateTable(
                    op="update_table",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateTable(
                    op="update_table",
                    anchor="<object><table",
                    new_html=_TABLE_AFTER,
                ),
            ],
        ),
        ctx=ctx,
    )
    assert not out.unmatched
