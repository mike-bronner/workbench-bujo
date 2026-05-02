"""Tests for the bujo.scan `unrecognized` status filter — added in 0.8.0.

Surfaces divs the parser couldn't classify into a structured line type,
so callers can clean them up via apply_decisions:remove. Post-0.10.0,
plain body paragraphs parse as BodyLine (not UnrecognizedLine), so the
representative cases for unrecognized are now tables, embedded objects,
and other structured HTML that's not a BuJo line, heading, body, or
blank. The fixtures below use table-shaped HTML to exercise the filter.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import UnrecognizedLine
from bujo_scribe_mcp.schemas import ScanFilter, ScanInput
from bujo_scribe_mcp.tools import scan


_LEGACY_TABLE_1 = (
    "<div><object><table><tbody>"
    "<tr><td><div>legacy free-text paragraph</div></td></tr>"
    "</tbody></table></object><br></div>"
)
_LEGACY_TABLE_2 = (
    "<div><object><table><tbody>"
    "<tr><td><div>another legacy line</div></td></tr>"
    "</tbody></table></object><br></div>"
)
_ORPHAN_TABLE = (
    "<div><object><table><tbody>"
    "<tr><td><div>orphan content</div></td></tr>"
    "</tbody></table></object><br></div>"
)


def test_returns_unrecognized_divs(make_backend, make_context, render_body, make_bujo_line):
    body = render_body(
        "sample-note",
        [
            make_bujo_line("task", "Real BuJo task"),
            UnrecognizedLine(raw_html=_LEGACY_TABLE_1),
            UnrecognizedLine(raw_html=_LEGACY_TABLE_2),
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
            UnrecognizedLine(raw_html=_ORPHAN_TABLE),
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
            UnrecognizedLine(raw_html=_ORPHAN_TABLE),
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
