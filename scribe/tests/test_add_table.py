"""Tests for the bujo_apply_decisions:add_table op — added in 0.10.

Inserts a fresh TableLine into a note. Used to scaffold the habit-tracker
table when it doesn't yet exist on the monthly note. Paired with
update_table for in-place edits afterward.

Anchoring:
- Empty after_anchor → append at end of note.
- Non-empty → substring match against the searchable text of any line
  (BujoLine.text, HeadingLine.text, BodyLine.text, TableLine.raw_html,
  or UnrecognizedLine.raw_html). 0 → NOT_FOUND. 2+ → AMBIGUOUS_BULLET.
  1 → insert immediately after the matched line.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import HeadingLine
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    DecisionAddTable,
    DecisionUpdateTable,
)
from bujo_scribe_mcp.tools import apply_decisions


_TABLE = (
    "<div><object><table cellspacing=\"0\"><tbody>"
    "<tr><td><div><b>Day</b></div></td></tr>"
    "</tbody></table></object><br></div>"
)


def test_add_table_appends_at_end_when_no_anchor(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [make_bujo_line("task", "First")],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAddTable(
                    op="add_table",
                    after_anchor="",
                    new_html=_TABLE,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    backend = ctx.backend
    ref = backend.find_by_title("sample-note")
    note_data = backend.read(ref)
    assert _TABLE in note_data.content


def test_add_table_inserts_after_matched_anchor(
    make_backend, make_context, render_body, make_bujo_line
):
    """With a non-empty after_anchor, the table lands AFTER the matched
    line. Use a heading anchor (text='Tracker') to land the table right
    after the section header — the canonical bujo-habit-add path."""
    body = render_body(
        "sample-note",
        [
            HeadingLine(text="Tracker", level=2),
            make_bujo_line("task", "Some task after"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAddTable(
                    op="add_table",
                    after_anchor="Tracker",
                    new_html=_TABLE,
                ),
            ],
        ),
        ctx=ctx,
    )

    backend = ctx.backend
    ref = backend.find_by_title("sample-note")
    note_data = backend.read(ref)
    content = note_data.content
    # Table should appear AFTER the Tracker heading and BEFORE the task.
    tracker_pos = content.find("<h2>Tracker</h2>")
    table_pos = content.find(_TABLE)
    task_pos = content.find("Some task after")
    assert tracker_pos < table_pos < task_pos


def test_add_table_not_found(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [make_bujo_line("task", "A task")],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAddTable(
                    op="add_table",
                    after_anchor="NonexistentHeading",
                    new_html=_TABLE,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "NOT_FOUND"


def test_add_table_ambiguous(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body(
        "sample-note",
        [
            HeadingLine(text="Tracker", level=2),
            HeadingLine(text="Tracker", level=2),  # duplicate — ambiguous anchor
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAddTable(
                    op="add_table",
                    after_anchor="Tracker",
                    new_html=_TABLE,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert len(out.unmatched) == 1
    assert out.unmatched[0].reason == "AMBIGUOUS_BULLET"


def test_add_then_update_round_trip(
    make_backend, make_context, render_body, make_bujo_line
):
    """End-to-end: scaffold a table via add_table, then update it via
    update_table. This is the bootstrap-then-mutate flow bujo-habit-add
    uses for fresh months."""
    body = render_body(
        "sample-note",
        [HeadingLine(text="Tracker", level=2)],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    # 1. Scaffold the table.
    apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionAddTable(
                    op="add_table",
                    after_anchor="Tracker",
                    new_html=_TABLE,
                ),
            ],
        ),
        ctx=ctx,
    )

    # 2. Update the table.
    new_table = _TABLE.replace("<b>Day</b>", "<b>Day</b></div></td><td><div><b>NewCol</b>")
    out = apply_decisions.execute(
        ApplyDecisionsInput(
            note="sample-note",
            decisions=[
                DecisionUpdateTable(
                    op="update_table",
                    anchor="<object><table",
                    new_html=new_table,
                ),
            ],
        ),
        ctx=ctx,
    )

    assert not out.unmatched
    backend = ctx.backend
    ref = backend.find_by_title("sample-note")
    note_data = backend.read(ref)
    assert "NewCol" in note_data.content
