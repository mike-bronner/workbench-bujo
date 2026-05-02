"""Tests for BodyLine parsing + rendering — added in 0.10.0.

A BodyLine is any non-blank, non-heading, non-mono, non-table div. Body
content can carry arbitrary inline styling (italic, bold, mixed, embedded
fonts/emoji). The line type carries `raw_html` for byte-preserving
round-trip and `text` (de-tagged) for matching/display.

The renderer emits raw_html verbatim — body content is never reconstructed
from `text`, because flattening inline styling into bool flags would lose
fidelity.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import (
    BlankLine,
    BodyLine,
    parse_note,
    render_note,
)
from bujo_scribe_mcp.parsing.model import ParsedNote
from bujo_scribe_mcp.rules.loader import load_rules


_RULES = load_rules()


def _parse(body: str):
    return parse_note(body, rules=_RULES)


def _render(lines):
    note = ParsedNote(title="", title_html="", lines=list(lines))
    return render_note(note, _RULES)


def test_plain_body_div_parses_as_body_line():
    body = "<div>plain body text</div>"
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], BodyLine)
    assert parsed.lines[0].text == "plain body text"


def test_italic_body_parses_with_text_de_tagged():
    body = "<div><i>Forward plan for April</i><br></div>"
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], BodyLine)
    assert parsed.lines[0].text == "Forward plan for April"
    assert parsed.lines[0].raw_html == body


def test_mixed_inline_styling_body_preserves_raw_html():
    """Body lines with mixed styling (italic broken by emoji, bold spans,
    etc.) must round-trip raw_html exactly — we don't model styling flags."""
    body = '<div><i>Mark </i>✅<i> for each day a habit is completed.</i><br></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], BodyLine)
    # text strips tags but keeps content.
    assert parsed.lines[0].text == "Mark ✅ for each day a habit is completed."
    # raw_html is preserved verbatim.
    assert parsed.lines[0].raw_html == body


def test_body_renders_raw_html_verbatim():
    body = '<div><i>some italic text</i><br></div>'
    line = BodyLine(text="some italic text", raw_html=body)
    rendered = _render([line])
    assert body in rendered


def test_body_round_trip_byte_preserved():
    body = "<div><b>Bold body</b><br></div>"
    parsed = _parse(body)
    rendered = _render(parsed.lines)
    # The body line itself round-trips byte-equivalent.
    assert body in rendered


def test_empty_body_div_becomes_blank():
    """A div whose de-tagged content is empty (e.g. just inline tags
    around a <br>) is functionally a spacer — treat as BlankLine, not
    a BodyLine with empty text."""
    body = "<div><i><br></i></div>"
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], BlankLine)
