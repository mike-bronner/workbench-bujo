"""Tests for HeadingLine parsing + rendering — added in 0.10.0.

The parser recognizes Apple Notes' Heading and Subheading paragraph
styles in two forms:

- New native: `<div><b><h2>...</h2></b><h2><br></h2></div>` (h-tags)
- Legacy: `<div><b><span style="font-size: 18px">...</span></b><br></div>`

`level` matches the HTML h-tag number directly: 2 for Heading, 3 for
Subheading. Title (h1 / 24px) is NOT a HeadingLine — it goes into
`ParsedNote.title`.

The renderer always emits the native h-tag form. Re-rendering a legacy
note produces native HTML; this is a one-time format migration that's
acceptable because both forms render identically in Apple Notes.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import (
    BodyLine,
    HeadingLine,
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


def test_h2_heading_parses_as_level_2():
    body = '<div><b><h2>Calendar</h2></b><h2><br></h2></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], HeadingLine)
    assert parsed.lines[0].text == "Calendar"
    assert parsed.lines[0].level == 2


def test_h3_subheading_parses_as_level_3():
    body = '<div><b><h3>Sub-section</h3></b><h3><br></h3></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], HeadingLine)
    assert parsed.lines[0].text == "Sub-section"
    assert parsed.lines[0].level == 3


def test_legacy_18px_span_heading_parses_as_level_2():
    body = '<div><b><span style="font-size: 18px">Tasks</span></b><br></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], HeadingLine)
    assert parsed.lines[0].text == "Tasks"
    assert parsed.lines[0].level == 2


def test_legacy_16px_span_heading_parses_as_level_3():
    body = '<div><b><span style="font-size: 16px">Sub-section</span></b><br></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], HeadingLine)
    assert parsed.lines[0].text == "Sub-section"
    assert parsed.lines[0].level == 3


def test_render_emits_native_h_tag_form():
    line = HeadingLine(text="Tracker", level=2)
    out = _render([line])
    assert "<h2>Tracker</h2>" in out
    assert 'font-size: 18px' not in out


def test_render_subheading_emits_h3():
    line = HeadingLine(text="Notes", level=3)
    out = _render([line])
    assert "<h3>Notes</h3>" in out


def test_legacy_form_round_trips_to_native_form():
    """Reading a legacy heading and re-rendering produces the native form.
    The text content is preserved; only the markup is updated."""
    legacy = '<div><b><span style="font-size: 18px">Tasks</span></b><br></div>'
    parsed = _parse(legacy)
    rendered = _render(parsed.lines)
    # Round-tripped to native h2 form.
    assert "<h2>Tasks</h2>" in rendered
    # Original 18px span is gone.
    assert "font-size: 18px" not in rendered


def test_arbitrary_font_size_is_not_heading():
    """A 14px or 12px span doesn't qualify as a heading. Becomes BodyLine."""
    body = '<div><b><span style="font-size: 14px">Custom</span></b><br></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    # Not a HeadingLine — falls through to BodyLine since it's still styled text.
    assert not isinstance(parsed.lines[0], HeadingLine)
    assert isinstance(parsed.lines[0], BodyLine)


def test_mixed_format_note_with_old_and_new_headings():
    """Real Apple Notes notes can mix old and new heading formats during
    the format-migration transition. Both must parse correctly in the
    same note."""
    body = (
        '<div><b><h2>Calendar</h2></b><h2><br></h2></div>'
        '<div><b><span style="font-size: 18px">Tasks</span></b><br></div>'
        '<div><b><h2>Tracker</h2></b><h2><br></h2></div>'
    )
    parsed = _parse(body)
    headings = [line for line in parsed.lines if isinstance(line, HeadingLine)]
    assert len(headings) == 3
    assert [h.text for h in headings] == ["Calendar", "Tasks", "Tracker"]
    assert all(h.level == 2 for h in headings)
