"""bujo.read — fetch notes for a ritual's context packet.

Resolves every identifier (slug or explicit title) to a concrete title via
`resolver.resolve`, then fetches each note from the backend and parses the
body into structured `ParsedLine` entries. Missing notes come back with
`exists=False, lines=None` — never an error.

Lines exposed on the wire: BuJo bullets (`kind="bujo"`), Headings/
Subheadings (`kind="heading"`), Body paragraphs (`kind="body"`), and
Tables (`kind="table"`, with raw_html populated for cell-level access).
Blank rows and `UnrecognizedLine` (true catch-all) are filtered — use
`bujo_scan` with `status="unrecognized"` to surface them for cleanup.

**Bounded output.** The packet as a whole is capped at
`BUJO_SCRIBE_MAX_READ_CHARS` estimated wire characters (default 50,000).
Notes are filled in the order they were requested, and any note that lost
lines carries a `truncated` record with the exact omitted-line count and
how to recover the rest. Nothing is ever dropped silently.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bujo_scribe_mcp.backends.base import BackendError
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.parsing import (
    BodyLine,
    BujoLine,
    HeadingLine,
    TableLine,
    parse_note,
)
from bujo_scribe_mcp.resolver import ResolverError, resolve
from bujo_scribe_mcp.schemas import NoteContent, ParsedLine, ReadInput, ReadOutput, Truncation

# Per-line allowance for the JSON envelope every ParsedLine carries on the
# wire — the field names (`kind`, `anchor`, `signifier`, `prefix`, `depth`,
# `dropped`, …) plus quoting and punctuation. Without it the budget would
# badly under-count a note of many short lines, where the envelope, not the
# text, is most of the payload.
_LINE_ENVELOPE_CHARS = 120


def execute(input: ReadInput, *, ctx: Context) -> ReadOutput:
    packet: dict[str, NoteContent] = {}
    limit = ctx.config.max_read_chars
    remaining = limit

    for identifier in input.notes:
        content, spent = _read_one(identifier, ctx=ctx, remaining=remaining, limit=limit)
        packet[identifier] = content
        remaining -= spent

    return ReadOutput(packet=packet)


def _read_one(
    identifier: str, *, ctx: Context, remaining: int, limit: int
) -> tuple[NoteContent, int]:
    """Read one note, spending at most `remaining` of the packet budget.

    Returns the note plus the budget it consumed.
    """
    try:
        title = resolve(identifier, rules=ctx.rules)
    except ResolverError as exc:
        return _missing(identifier, detail=str(exc)), 0

    ref = ctx.backend.find_by_title(title)
    if ref is None:
        return (
            NoteContent(
                title=title,
                exists=False,
                lines=None,
                retrieved_at=_now(),
            ),
            0,
        )

    try:
        note = ctx.backend.read(ref)
    except BackendError:
        return (
            NoteContent(
                title=ref.title,
                exists=False,
                lines=None,
                retrieved_at=_now(),
            ),
            0,
        )

    parsed = parse_note(note.content, rules=ctx.rules)
    lines: list[ParsedLine] = []
    omitted = 0
    spent = 0
    for line in parsed.lines:
        wire = _to_parsed_line(line)
        if wire is None:
            continue
        cost = _line_cost(wire)
        # A line wider than the *entire* budget is emitted regardless: no
        # narrower request could ever retrieve it, and refusing it would make
        # it permanently unreachable. This is the monthly habit tracker — one
        # TableLine whose raw_html can rival the whole budget, and which must
        # round-trip byte-exact or `update_table` corrupts the note. Splitting
        # it is not an option, so it goes out whole and the packet runs over.
        if cost <= remaining - spent or cost > limit:
            lines.append(wire)
            spent += cost
        else:
            omitted += 1

    return (
        NoteContent(
            title=ref.title,
            exists=True,
            lines=lines,
            retrieved_at=note.retrieved_at.isoformat(),
            truncated=_truncation(omitted, limit) if omitted else None,
        ),
        spent,
    )


def _line_cost(line: ParsedLine) -> int:
    """Estimated wire size of one line, in characters."""
    return len(line.text) + len(line.raw_html or "") + _LINE_ENVELOPE_CHARS


def _truncation(omitted: int, limit: int) -> Truncation:
    return Truncation(
        omitted=omitted,
        limit=limit,
        detail=(
            f"{omitted} line(s) omitted from this note — the packet's "
            f"{limit}-character budget was exhausted. Lines are returned in "
            f"document order, so the tail is what is missing. Re-request this "
            f"note in a follow-up bujo_read call with fewer notes, or raise "
            f"BUJO_SCRIBE_MAX_READ_CHARS."
        ),
    )


def _to_parsed_line(line) -> ParsedLine | None:
    """Project an internal Line to its wire-side ParsedLine, or None to filter."""
    if isinstance(line, BujoLine):
        return ParsedLine(
            kind="bujo",
            text=line.text,
            anchor=line.anchor,
            signifier=line.signifier,
            prefix=line.prefix,
            depth=line.depth,
            dropped=line.dropped,
        )
    if isinstance(line, HeadingLine):
        return ParsedLine(
            kind="heading",
            text=line.text,
            anchor=line.text,
            heading_level=line.level,
        )
    if isinstance(line, BodyLine):
        return ParsedLine(
            kind="body",
            text=line.text,
            anchor=line.text,
        )
    if isinstance(line, TableLine):
        return ParsedLine(
            kind="table",
            text="",
            # `<object><table` is a stable substring for the standard
            # `update_table` / `add_table` anchor pattern.
            anchor="<object><table",
            raw_html=line.raw_html,
        )
    # BlankLine and UnrecognizedLine are filtered out.
    return None


def _missing(identifier: str, *, detail: str) -> NoteContent:
    return NoteContent(
        title=f"<unresolved:{identifier}>",
        exists=False,
        lines=None,
        retrieved_at=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
