"""Tests for the monospace-wrapper parsing change — 0.10.0.

Apple Notes' native Monospaced paragraph style emits plain
`<div><tt>...</tt></div>` (no `<font>` wrapper). Older Apple Notes
builds and pre-0.10 scribe wrote `<font face="Menlo-Regular">` (or
Courier) around the `<tt>`. Post-0.10 the parser accepts both forms;
the renderer always emits the native (no-font) form.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import (
    BodyLine,
    BujoLine,
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


def test_native_mono_parses_as_bujo_line():
    """`<div><tt>...</tt></div>` (no font wrapper) parses as BujoLine."""
    body = "<div><tt>&nbsp;• Pay the electric bill</tt></div>"
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], BujoLine)
    assert parsed.lines[0].signifier == "task"
    assert parsed.lines[0].text == "Pay the electric bill"


def test_legacy_menlo_mono_still_parses():
    """Backward compat: pre-0.10 notes with `<font face="Menlo-Regular">`
    wrapping `<tt>` still parse as BujoLine."""
    body = '<div><font face="Menlo-Regular"><tt>&nbsp;• Pay the electric bill</tt></font></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    assert isinstance(parsed.lines[0], BujoLine)
    assert parsed.lines[0].text == "Pay the electric bill"


def test_legacy_courier_mono_still_parses():
    """Same backward compat for Courier-wrapped mono."""
    body = '<div><font face="Courier"><tt>1 We Calendar entry</tt></font></div>'
    parsed = _parse(body)
    assert len(parsed.lines) == 1
    # Not a BuJo line (no signifier prefix), but IS a body-class line.
    # Mono div whose content doesn't match BuJo signifiers falls through
    # to BodyLine since it's still user-written paragraph content.
    assert isinstance(parsed.lines[0], BodyLine)


def test_renderer_emits_native_mono_form():
    """The renderer drops the legacy <font> wrapper; new writes are
    plain `<div><tt>...</tt></div>`."""
    line = BujoLine(
        signifier="task",
        text="Pay the bill",
        anchor="Pay the bill",
    )
    out = _render([line])
    # Native form: no font wrapper.
    assert '<font face="Menlo' not in out
    assert '<font face="Courier' not in out
    # Has the <tt> wrapper directly inside <div>.
    assert "<tt>" in out and "</tt>" in out


def test_legacy_format_round_trips_to_native():
    """Reading a legacy Menlo-wrapped BuJo line and re-rendering produces
    native (no-font) form. This is the migration mechanism — old notes
    gradually convert to native format on each scribe-touched line."""
    legacy = '<div><font face="Menlo-Regular"><tt>&nbsp;• Old format task</tt></font></div>'
    parsed = _parse(legacy)
    rendered = _render(parsed.lines)
    # Round-trip dropped the font wrapper.
    assert '<font face="Menlo' not in rendered
    # Content survives.
    assert "Old format task" in rendered
