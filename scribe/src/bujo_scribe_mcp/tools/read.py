"""bujo.read — fetch notes for a ritual's context packet.

Resolves every identifier (slug or explicit title) to a concrete title via
`resolver.resolve`, then fetches each note from the backend and parses the
body into structured `ParsedLine` entries. Missing notes come back with
`exists=False, lines=None` — never an error.

Only `BujoLine` entries cross the wire — blank rows and unrecognized
(non-BuJo) divs are filtered. To surface unrecognized content for
maintenance, callers use `bujo_scan` with `status="unrecognized"`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bujo_scribe_mcp.backends.base import BackendError
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.parsing import BujoLine, parse_note
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
    lines = [_to_parsed_line(line) for line in parsed.lines if isinstance(line, BujoLine)]

    return NoteContent(
        title=ref.title,
        exists=True,
        lines=lines,
        retrieved_at=note.retrieved_at.isoformat(),
    )


def _to_parsed_line(line: BujoLine) -> ParsedLine:
    return ParsedLine(
        signifier=line.signifier,
        prefix=line.prefix,
        text=line.text,
        depth=line.depth,
        dropped=line.dropped,
        anchor=line.anchor,
    )


def _missing(identifier: str, *, detail: str) -> NoteContent:
    return NoteContent(
        title=f"<unresolved:{identifier}>",
        exists=False,
        lines=None,
        retrieved_at=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
