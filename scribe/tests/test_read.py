"""Tests for bujo.read — verifies the post-0.8.0 ParsedLine wire shape.

The previous read verb returned the raw Apple Notes HTML body in
`NoteContent.content`, which forced agents to parse HTML by eye and
caused hallucinated journal entries. From 0.8.0, read returns a parsed
`lines: ParsedLine[]` projection instead, with raw HTML strictly absent.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import BlankLine, UnrecognizedLine
from bujo_scribe_mcp.schemas import ReadInput
from bujo_scribe_mcp.tools import read


def test_existing_note_emits_parsed_lines(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "2026-04-19 — Sunday",
        [
            make_bujo_line("task", "Ship the orchestrator agent"),
            make_bujo_line("event", "1:1 with Calvin", prefix="priority"),
            make_bujo_line("note", "Insight about contract tests", prefix="inspiration"),
        ],
    )
    ctx = make_context(make_backend({"2026-04-19 — Sunday": body}))

    out = read.execute(ReadInput(notes=["2026-04-19 — Sunday"]), ctx=ctx)

    note = out.packet["2026-04-19 — Sunday"]
    assert note.exists is True
    assert note.lines is not None
    assert len(note.lines) == 3
    assert note.lines[0].signifier == "task"
    assert note.lines[0].text == "Ship the orchestrator agent"
    assert note.lines[0].prefix is None
    assert note.lines[1].signifier == "event"
    assert note.lines[1].prefix == "priority"
    assert note.lines[2].signifier == "note"
    assert note.lines[2].prefix == "inspiration"


def test_response_carries_no_raw_html_field(make_backend, make_context, render_body, make_bujo_line):
    """Regression guard: the wire DTO must not expose `content` or any HTML."""
    body = render_body("daily", [make_bujo_line("task", "x")])
    ctx = make_context(make_backend({"daily": body}))

    out = read.execute(ReadInput(notes=["daily"]), ctx=ctx)
    serialized = out.packet["daily"].model_dump()

    assert "content" not in serialized
    assert "raw_html" not in serialized
    for line in serialized["lines"]:
        assert "raw_html" not in line


def test_dropped_lines_preserve_dropped_flag(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Active task"),
            make_bujo_line("task", "Dropped task", dropped=True),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = read.execute(ReadInput(notes=["sample-note"]), ctx=ctx)
    lines = out.packet["sample-note"].lines

    assert lines[0].dropped is False
    assert lines[1].dropped is True
    assert lines[1].text == "Dropped task"


def test_nested_sub_items_preserve_depth(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Parent task"),
            make_bujo_line("sub_item", "Nested detail", depth=1),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = read.execute(ReadInput(notes=["sample-note"]), ctx=ctx)
    lines = out.packet["sample-note"].lines

    assert lines[0].depth == 0
    assert lines[1].depth == 1
    assert lines[1].signifier == "sub_item"


def test_blank_lines_are_filtered(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "First"),
            BlankLine(),
            make_bujo_line("task", "Second"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = read.execute(ReadInput(notes=["sample-note"]), ctx=ctx)
    lines = out.packet["sample-note"].lines

    assert len(lines) == 2
    assert [line.text for line in lines] == ["First", "Second"]


def test_unrecognized_lines_are_filtered(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Real BuJo task"),
            UnrecognizedLine(raw_html="<div>legacy free-text content</div>"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = read.execute(ReadInput(notes=["sample-note"]), ctx=ctx)
    lines = out.packet["sample-note"].lines

    assert len(lines) == 1
    assert lines[0].text == "Real BuJo task"


def test_missing_note_returns_lines_none(make_backend, make_context):
    ctx = make_context(make_backend({}))
    out = read.execute(ReadInput(notes=["2026-04-19 — Sunday"]), ctx=ctx)

    note = out.packet["2026-04-19 — Sunday"]
    assert note.exists is False
    assert note.lines is None


def test_anchor_round_trips_with_text(make_backend, make_context, render_body, make_bujo_line):
    """Anchor should be stable enough to feed back into apply_decisions."""
    body = render_body("sample-note", [make_bujo_line("task", "Pay the electric bill")])
    ctx = make_context(make_backend({"sample-note": body}))

    out = read.execute(ReadInput(notes=["sample-note"]), ctx=ctx)
    line = out.packet["sample-note"].lines[0]

    assert line.anchor == "Pay the electric bill"
