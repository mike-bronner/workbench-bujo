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
from bujo_scribe_mcp.schemas import NoteContent, ParsedLine, ReadInput, ReadOutput


def execute(input: ReadInput, *, ctx: Context) -> ReadOutput:
    packet: dict[str, NoteContent] = {}

    for identifier in input.notes:
        packet[identifier] = _read_one(identifier, ctx=ctx)

    return ReadOutput(packet=packet)


def _read_one(identifier: str, *, ctx: Context) -> NoteContent:
    try:
        title = resolve(identifier, rules=ctx.rules)
    except ResolverError as exc:
        return _missing(identifier, detail=str(exc))

    ref = ctx.backend.find_by_title(title)
    if ref is None:
        return NoteContent(
            title=title,
            exists=False,
            lines=None,
            retrieved_at=_now(),
        )

    try:
        note = ctx.backend.read(ref)
    except BackendError:
        return NoteContent(
            title=ref.title,
            exists=False,
            lines=None,
            retrieved_at=_now(),
        )

    parsed = parse_note(note.content, rules=ctx.rules)
    lines: list[ParsedLine] = []
    for line in parsed.lines:
        wire = _to_parsed_line(line)
        if wire is not None:
            lines.append(wire)

    return NoteContent(
        title=ref.title,
        exists=True,
        lines=lines,
        retrieved_at=note.retrieved_at.isoformat(),
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
