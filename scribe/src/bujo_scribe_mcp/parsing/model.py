"""Internal structured model for BuJo notes.

Used by the parser, renderer, and verb logic. Not exposed over the MCP wire
— cross-boundary types live in `schemas.py` and are built from these.

Plain dataclasses (not pydantic) — simpler, and we don't need validation on
internal types that stay inside the MCP process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BUILTIN_BASE_SIGNIFIERS = (
    "task",       # •
    "event",      # ○
    "note",       # —
    "completed",  # ×
    "migrated",   # >
    "scheduled",  # <
    "sub_item",   # -  (always treated as a note; inherits parent type)
)

# BaseSignifier is a string — the value matches either a built-in key from
# BUILTIN_BASE_SIGNIFIERS, or a user-defined extension key from
# `rules.signifiers.extensions`. We use `str` rather than `Literal` so that
# user extensions flow through the parser/renderer without code changes.
BaseSignifier = str

# PrefixSignifier is also a free-form string — matches a built-in key
# (priority | inspiration | explore) OR a user-defined prefix extension key
# from `rules.signifiers.prefix_extensions`.
PrefixSignifier = str


@dataclass
class BujoLine:
    """A parsed BuJo line with semantic structure."""

    signifier: BaseSignifier
    text: str
    depth: int = 0
    prefix: PrefixSignifier | None = None
    dropped: bool = False
    anchor: str = ""
    raw_html: str = ""  # original div HTML for preservation + exact matching


@dataclass
class BlankLine:
    """An intentionally blank row inside a note."""

    raw_html: str = ""


@dataclass
class HeadingLine:
    """An Apple Notes Heading or Subheading paragraph.

    `level` matches the HTML h-tag number directly:
    - 2 → Heading (h2 / legacy 18px-span)
    - 3 → Subheading (h3 / legacy 16px-span)

    The note title (h1 / legacy 24px-span) is NOT a HeadingLine — it's
    extracted into `ParsedNote.title` via the title-detection path.
    """

    text: str
    level: int
    raw_html: str = ""


@dataclass
class BodyLine:
    """A non-heading, non-mono paragraph.

    Body lines can carry any inline styling (italic, bold, embedded
    fonts/emoji, mixed). We preserve the original HTML and expose a
    de-tagged plain-text view for matching/display — we do NOT model
    individual style flags because the styling space is too varied to
    flatten without losing fidelity.
    """

    text: str        # de-tagged plain-text view (for search/display)
    raw_html: str    # canonical full HTML for round-trip rendering


@dataclass
class TableLine:
    """An Apple Notes table — `<div><object><table>…</table></object><br></div>`.

    Tables can't be cleanly represented as structured fields (rows,
    columns, cells with arbitrary inline styling), so we preserve the
    raw HTML for round-trip and let callers parse/regenerate the HTML
    when they need to mutate cells.

    Used most heavily by the habit tracker on the monthly note. Mutate
    via the `update_table` / `add_table` decision ops.
    """

    raw_html: str


@dataclass
class UnrecognizedLine:
    """A div the parser couldn't classify into a known line type.

    Preserved verbatim so we can round-trip it through the renderer
    without mutating content we don't understand. Reserved for true
    catch-all cases — tables have their own `TableLine` type, headings
    have `HeadingLine`, etc.
    """

    raw_html: str


Line = BujoLine | BlankLine | HeadingLine | BodyLine | TableLine | UnrecognizedLine


@dataclass
class ParsedNote:
    title: str
    title_html: str
    lines: list[Line] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base / prefix character tables
# ---------------------------------------------------------------------------
#
# Duplicated from the defaults in `rules.yaml`. Kept here so the parser can
# resolve characters → enum keys without depending on the rules layer at
# parse-time. The renderer DOES consult the rules layer (so user overrides
# affect emitted HTML).


BASE_CHAR_TO_KEY: dict[str, BaseSignifier] = {
    "•": "task",
    "○": "event",
    "—": "note",
    "x": "completed",   # canonical (classic Ryder Carroll)
    "×": "completed",   # legacy alias — older notes wrote U+00D7
    ">": "migrated",
    "<": "scheduled",
    "-": "sub_item",
}

PREFIX_CHAR_TO_KEY: dict[str, PrefixSignifier] = {
    "✽": "priority",
    "!": "inspiration",
    "◉": "explore",
}
