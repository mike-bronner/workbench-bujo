"""bujo.scaffold — create or merge a ritual entry.

- `mode=create` builds a fresh note. Fails if a note with the resolved title
  already exists. Applies setup-time ordering (events → tasks → notes) per
  rules when enabled.
- `mode=merge` reads the existing note fresh, appends any bullets that
  aren't already present, and writes back. Parallel-edit guard is implicit
  in the "read immediately before write" flow inside this function.
"""

from __future__ import annotations

from bujo_scribe_mcp.backends.base import BackendError
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.locking import mutation_lock
from bujo_scribe_mcp.parsing import BujoLine, ParsedNote, parse_note, render_note
from bujo_scribe_mcp.resolver import resolve
from bujo_scribe_mcp.schemas import (
    Diff,
    DiffAdded,
    ScaffoldInput,
    ScaffoldOutput,
)
from bujo_scribe_mcp.tools._mutations import build_scaffold_lines


def execute(input: ScaffoldInput, *, ctx: Context) -> ScaffoldOutput:
    # Cross-process serialization — see locking.py.
    with mutation_lock(ctx.config.run_dir):
        return _execute_locked(input, ctx=ctx)


def _execute_locked(input: ScaffoldInput, *, ctx: Context) -> ScaffoldOutput:
    title = resolve(input.target, rules=ctx.rules)

    existing_ref = ctx.backend.find_by_title(title)

    if input.mode == "create":
        if existing_ref is not None:
            raise BackendError(f"Note already exists (mode=create): {title}")
        return _create(title, input, ctx=ctx)

    # mode=merge
    if existing_ref is None:
        # Merging into a non-existent note = create it.
        return _create(title, input, ctx=ctx)

    # Read fresh immediately before write.
    existing = ctx.backend.read(existing_ref)
    parsed = parse_note(existing.content, rules=ctx.rules)
    if not parsed.title:
        parsed.title = title

    return _merge(parsed, existing_ref, input, ctx=ctx)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _create(title: str, input: ScaffoldInput, *, ctx: Context) -> ScaffoldOutput:
    lines = build_scaffold_lines(input.sections, ctx.rules, setup_time=True)
    note = ParsedNote(title=title, title_html="", lines=list(lines))
    body = render_note(note, ctx.rules)

    ref = ctx.backend.create(title, body)

    diff = Diff(
        added=[
            DiffAdded(section=_section_for(line, input), bullet=line.text)
            for line in lines
            if isinstance(line, BujoLine)
        ],
    )
    return ScaffoldOutput(note_id=ref.title, created=True, diff=diff, warnings=[])


def _merge(parsed: ParsedNote, ref, input: ScaffoldInput, *, ctx: Context) -> ScaffoldOutput:
    existing_texts = {
        line.text for line in parsed.lines if isinstance(line, BujoLine)
    }

    # After-day-started merges append chronologically — no setup-time reorder.
    candidate_lines = build_scaffold_lines(input.sections, ctx.rules, setup_time=False)

    added_lines: list[BujoLine] = []
    for line in candidate_lines:
        if isinstance(line, BujoLine) and line.text not in existing_texts:
            parsed.lines.append(line)
            added_lines.append(line)
            existing_texts.add(line.text)

    body = render_note(parsed, ctx.rules)
    ctx.backend.update(ref, body)

    diff = Diff(
        added=[
            DiffAdded(section=_section_for(line, input), bullet=line.text)
            for line in added_lines
        ],
    )
    return ScaffoldOutput(note_id=ref.title, created=False, diff=diff, warnings=[])


def _section_for(line: BujoLine, input: ScaffoldInput) -> str:
    """Best-effort: return the section name that contributed this line."""
    for section in input.sections:
        for bullet in section.bullets:
            if bullet.text == line.text and bullet.signifier == line.signifier:
                return section.name
    return ""
