"""Tests for the bujo.scan `unrecognized` status filter — added in 0.8.0.

Surfaces non-BuJo divs that the parser couldn't classify, so callers can
clean them up via apply_decisions:remove. The returned ScanItem.text /
.anchor is the de-tagged HTML, which is exactly what apply_remove
substring-matches against on UnrecognizedLine.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import UnrecognizedLine
from bujo_scribe_mcp.schemas import ScanFilter, ScanInput
from bujo_scribe_mcp.tools import scan


def test_returns_unrecognized_divs(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Real BuJo task"),
            UnrecognizedLine(raw_html="<div>legacy free-text paragraph</div>"),
            UnrecognizedLine(raw_html="<div>another legacy line</div>"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = scan.execute(
        ScanInput(scope=["sample-note"], filter=ScanFilter(status="unrecognized")),
        ctx=ctx,
    )

    assert len(out.items) == 2
    assert all(item.signifier == "unrecognized" for item in out.items)
    texts = {item.text for item in out.items}
    assert "legacy free-text paragraph" in texts
    assert "another legacy line" in texts


def test_anchor_matches_text_for_remove_round_trip(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "BuJo task"),
            UnrecognizedLine(raw_html="<div>orphan content</div>"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = scan.execute(
        ScanInput(scope=["sample-note"], filter=ScanFilter(status="unrecognized")),
        ctx=ctx,
    )

    item = out.items[0]
    assert item.anchor == item.text == "orphan content"


def test_skips_bujo_lines(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Real task"),
            make_bujo_line("event", "Real event"),
            make_bujo_line("note", "Real note", prefix="inspiration"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = scan.execute(
        ScanInput(scope=["sample-note"], filter=ScanFilter(status="unrecognized")),
        ctx=ctx,
    )

    assert out.items == []


def test_open_status_still_skips_unrecognized(make_backend, make_context, render_body, make_bujo_line):
    """Unrecognized lines must NOT leak into open scans — that's a separate concern."""
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Open task"),
            UnrecognizedLine(raw_html="<div>orphan content</div>"),
        ],
    )
    ctx = make_context(make_backend({"sample-note": body}))

    out = scan.execute(
        ScanInput(scope=["sample-note"], filter=ScanFilter(status="open")),
        ctx=ctx,
    )

    assert len(out.items) == 1
    assert out.items[0].signifier == "task"
    assert out.items[0].text == "Open task"
