"""bujo.scan — find open, due, or unrecognized items across notes.

Read-only. Resolves each scope identifier, fetches the note, parses, and
returns every line that passes the requested filter. Stable `anchor`
fields let callers pass the items back into `bujo.apply_decisions` as
bullet targets.

Status definitions:
- `open`            signifier ∈ (task, event, note, sub_item) AND NOT dropped
                    AND signifier NOT ∈ (completed, migrated, scheduled)
- `due_today`       item's inline date tag == today (e.g. Future Log `[YYYY-MM-DD]`)
- `overdue`         item's inline date tag < today
- `surfaces_today`  alias for `due_today` — semantic sugar for Future Log sweeps
- `unrecognized`    surfaces every UnrecognizedLine — non-BuJo content (legacy
                    or malformed divs). Returned as ScanItem with
                    signifier='unrecognized'; the `text`/`anchor` is the
                    de-tagged HTML which round-trips to apply_decisions:remove.
"""

from __future__ import annotations

import html as _html
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bujo_scribe_mcp.backends.base import BackendError
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.parsing import BujoLine, UnrecognizedLine, parse_note
from bujo_scribe_mcp.resolver import resolve
from bujo_scribe_mcp.schemas import ScanInput, ScanItem, ScanOutput

_INLINE_DATE_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2})\]")
_TAG_RE = re.compile(r"<[^>]+>")


def execute(input: ScanInput, *, ctx: Context) -> ScanOutput:
    reference_date = _resolve_date(input.filter.date, ctx.rules.timezone)
    items: list[ScanItem] = []

    for identifier in input.scope:
        title = resolve(identifier, rules=ctx.rules)
        ref = ctx.backend.find_by_title(title)
        if ref is None:
            continue
        try:
            note = ctx.backend.read(ref)
        except BackendError:
            continue
        parsed = parse_note(note.content, rules=ctx.rules)

        if input.filter.status == "unrecognized":
            for line in parsed.lines:
                if isinstance(line, UnrecognizedLine):
                    items.append(_to_unrecognized_item(ref.title, line))
            continue

        for line in parsed.lines:
            if not isinstance(line, BujoLine):
                continue
            if not _passes_filter(line, input.filter, reference_date=reference_date, rules=ctx.rules):
                continue
            items.append(_to_scan_item(ref.title, line))

    return ScanOutput(items=items)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


_OPEN_SIGS = {"task", "event", "note", "sub_item"}
_TERMINAL_SIGS = {"completed", "migrated", "scheduled"}
_BUILTIN_TYPE_MAP = {"task": {"task"}, "event": {"event"}, "note": {"note", "sub_item"}}


def _passes_filter(line: BujoLine, f, *, reference_date: date, rules=None) -> bool:
    # Type filter
    if f.type is not None:
        type_map = _resolve_type_map(rules) if rules is not None else _BUILTIN_TYPE_MAP
        if line.signifier not in type_map[f.type]:
            return False

    # Status filter
    if f.status is None:
        return True

    if f.status == "open":
        terminal = _TERMINAL_SIGS
        return line.signifier not in terminal and not line.dropped

    inline_date = _inline_date(line)
    if f.status == "due_today" or f.status == "surfaces_today":
        return inline_date == reference_date
    if f.status == "overdue":
        return inline_date is not None and inline_date < reference_date

    return True


def _inline_date(line: BujoLine) -> date | None:
    match = _INLINE_DATE_RE.search(line.text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_scan_item(note_title: str, line: BujoLine) -> ScanItem:
    inline = _inline_date(line)
    return ScanItem(
        note=note_title,
        section="",  # single-block tier notes — no sections
        signifier=line.signifier,  # may be built-in key OR user-defined extension key
        text=line.text,
        anchor=line.anchor,
        due=inline.isoformat() if inline else None,
    )


def _to_unrecognized_item(note_title: str, line: UnrecognizedLine) -> ScanItem:
    """Project an UnrecognizedLine into a ScanItem suitable for hygiene flows.

    `text` and `anchor` carry the de-tagged HTML — that's what
    `apply_decisions:remove` substring-matches against on UnrecognizedLine.
    """
    stripped = _TAG_RE.sub("", _html.unescape(line.raw_html)).strip()
    return ScanItem(
        note=note_title,
        section="",
        signifier="unrecognized",
        text=stripped,
        anchor=stripped,
        due=None,
    )


def _resolve_type_map(rules) -> dict[str, set[str]]:
    """Build {task: {keys}, event: {keys}, note: {keys}} including extensions."""
    result: dict[str, set[str]] = {
        "task": {"task"},
        "event": {"event"},
        "note": {"note", "sub_item"},
    }
    for ext in rules.signifiers.extensions:
        result[ext.class_].add(ext.key)
    return result


def _resolve_date(iso: str | None, tz_name: str) -> date:
    if iso is not None:
        return date.fromisoformat(iso)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()
