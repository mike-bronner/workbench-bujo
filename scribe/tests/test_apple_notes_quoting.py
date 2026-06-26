"""Tests for `_as_quote` — AppleScript string-literal escaping.

Pure function, no osascript / macOS required. Guards the escaping chokepoint
every value (note titles, bullet text, `target` slugs) passes through before
interpolation into an AppleScript literal — so a stray quote, backslash, or
newline can't break out of, or terminate, the literal.
"""

from __future__ import annotations

from bujo_scribe_mcp.backends.apple_notes import _as_quote


def test_as_quote_wraps_plain_value():
    assert _as_quote("hello world") == '"hello world"'


def test_as_quote_escapes_backslash_and_quote():
    # a\b"c  ->  "a\\b\"c"
    assert _as_quote('a\\b"c') == '"a\\\\b\\"c"'


def test_as_quote_escapes_newline_and_carriage_return():
    out = _as_quote("line1\nline2\rline3")
    # No raw newline/CR survives to terminate the AppleScript literal...
    assert "\n" not in out
    assert "\r" not in out
    # ...and each is present as an AppleScript escape.
    assert "\\n" in out
    assert "\\r" in out


def test_as_quote_backslash_escaped_before_newline():
    # A literal backslash-then-newline must NOT collapse into one `\n` escape:
    # the backslash is doubled first, then the real newline becomes `\n`.
    assert _as_quote("a\\\nb") == '"a\\\\\\nb"'
