"""Bullet-matching — find a BujoLine in a parsed note by decision-supplied text.

A decision carries a `bullet: str` that identifies which line to act on.
This module resolves that string to zero, one, or multiple BujoLine entries
in a parsed note. Matching is case-sensitive substring over the normalized
line text — anchors produced by `parsing/parser.py` are already normalized,
so an anchor round-trips exactly.
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing import BujoLine, ParsedNote


def find_matches(note: ParsedNote, needle: str) -> list[BujoLine]:
    """Return every BujoLine in `note` whose text matches `needle`.

    Match priority — if ANY exact match exists, only exact matches are
    returned. Otherwise, fall back to substring matches. This prevents an
    exact-match decision from being flagged ambiguous when a longer line
    happens to contain the same prefix.
    """
    normalized = needle.strip()
    if not normalized:
        return []

    bujo_lines = [line for line in note.lines if isinstance(line, BujoLine)]

    exact = [line for line in bujo_lines if line.text == normalized or line.anchor == normalized]
    if exact:
        return exact

    return [line for line in bujo_lines if normalized in line.text]


def find_descendants(note: ParsedNote, parent: BujoLine) -> list[BujoLine]:
    """Return every BujoLine that's a descendant of `parent` in `note.lines`.

    A line is a descendant iff it appears after `parent` AND every line back
    to `parent` is itself a BujoLine with depth > parent.depth. The first
    non-BujoLine (BlankLine, UnrecognizedLine) or the first BujoLine with
    depth ≤ parent.depth ends the subtree.
    """
    try:
        parent_idx = note.lines.index(parent)
    except ValueError:
        return []
    descendants: list[BujoLine] = []
    for line in note.lines[parent_idx + 1 :]:
        if not isinstance(line, BujoLine):
            break
        if line.depth <= parent.depth:
            break
        descendants.append(line)
    return descendants
