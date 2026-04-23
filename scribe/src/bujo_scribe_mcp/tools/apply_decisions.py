"""bujo.apply_decisions — apply mutations to an existing note.

Contract invariants:
- Reads the note fresh immediately before writing (parallel-edit guard).
- Cross-note effects (migrate, schedule) mutate both notes atomically from
  the caller's perspective — the primary note's diff plus the target note's
  diff both land before this verb returns.
- Gap 2: `schedule` requires a strictly-future date. Without it, the
  decision is rejected and the task stays as an open task.
- `dry_run=true` computes the diff without writing anything (to any note).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from bujo_scribe_mcp.backends.base import BackendError, NoteRef
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.parsing import BujoLine, ParsedNote, parse_note, render_note
from bujo_scribe_mcp.resolver import resolve
from bujo_scribe_mcp.schemas import (
    ApplyDecisionsInput,
    ApplyDecisionsOutput,
    CrossNoteEffect,
    DecisionAdd,
    DecisionCombine,
    DecisionComplete,
    DecisionDrop,
    DecisionMigrate,
    DecisionRemove,
    DecisionReorder,
    DecisionSchedule,
    DecisionUndrop,
    DecisionUpdate,
    Diff,
    DiffAdded,
    DiffChanged,
    DiffMoved,
    DiffRemoved,
    UnmatchedDecision,
)
from bujo_scribe_mcp.tools._matching import find_matches
from bujo_scribe_mcp.tools._mutations import (
    CrossNoteRequest,
    apply_add,
    apply_combine,
    apply_complete,
    apply_drop,
    apply_migrate,
    apply_remove,
    apply_reorder,
    apply_schedule,
    apply_undrop,
    apply_update,
)


def execute(input: ApplyDecisionsInput, *, ctx: Context) -> ApplyDecisionsOutput:
    title = resolve(input.note, rules=ctx.rules)
    ref = ctx.backend.find_by_title(title)
    if ref is None:
        raise BackendError(f"Note not found: {title}")

    note_data = ctx.backend.read(ref)
    parsed = parse_note(note_data.content, rules=ctx.rules)
    if not parsed.title:
        parsed.title = title

    today = _today_in_tz(ctx.rules.timezone)

    all_diffs: list = []
    unmatched: list[UnmatchedDecision] = []
    cross_requests: list[CrossNoteRequest] = []

    # Pre-flight: validate combine decisions before any mutation.
    # Combine is atomic across two notes — if the target/parent can't be
    # found, we don't want to leave the source half-mutated.
    combine_failures = _preflight_combines(input.decisions, source_title=title, ctx=ctx)

    for decision in input.decisions:
        if isinstance(decision, DecisionCombine):
            failure_reason = combine_failures.get(id(decision))
            if failure_reason is not None:
                unmatched.append(
                    UnmatchedDecision(
                        decision=_decision_to_dict(decision),
                        reason=failure_reason,
                    )
                )
                continue
        diff_entries, reason, cross = _dispatch(decision, parsed, ctx, today=today)
        if reason is not None:
            unmatched.append(
                UnmatchedDecision(
                    decision=_decision_to_dict(decision),
                    reason=reason,
                )
            )
            continue
        all_diffs.extend(diff_entries)
        if cross is not None:
            cross_requests.append(cross)

    # Commit primary note (unless dry run).
    if not input.dry_run:
        body = render_note(parsed, ctx.rules)
        ctx.backend.update(ref, body)

    # Resolve & apply cross-note effects.
    cross_effects: list[CrossNoteEffect] = []
    for req in cross_requests:
        effect = _apply_cross_note(req, ctx=ctx, dry_run=input.dry_run)
        cross_effects.append(effect)

    return ApplyDecisionsOutput(
        note_id=ref.title,
        diff=_build_diff(all_diffs),
        unmatched=unmatched,
        cross_note_effects=cross_effects,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _dispatch(
    decision,
    parsed: ParsedNote,
    ctx: Context,
    *,
    today: date,
) -> tuple[list, str | None, CrossNoteRequest | None]:
    if isinstance(decision, DecisionComplete):
        diffs, reason = apply_complete(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionDrop):
        diffs, reason = apply_drop(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionUndrop):
        diffs, reason = apply_undrop(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionUpdate):
        diffs, reason = apply_update(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionAdd):
        diffs, reason = apply_add(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionReorder):
        diffs, reason = apply_reorder(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionRemove):
        diffs, reason = apply_remove(parsed, decision, ctx.rules)
        return diffs, reason, None
    if isinstance(decision, DecisionMigrate):
        return apply_migrate(parsed, decision, ctx.rules)
    if isinstance(decision, DecisionCombine):
        return apply_combine(parsed, decision, ctx.rules)
    if isinstance(decision, DecisionSchedule):
        return apply_schedule(
            parsed,
            decision,
            ctx.rules,
            today=today,
            future_log_slug="future_log",
        )
    raise TypeError(f"Unknown decision op: {type(decision).__name__}")


# ---------------------------------------------------------------------------
# Combine pre-flight
# ---------------------------------------------------------------------------


def _preflight_combines(
    decisions,
    *,
    source_title: str,
    ctx: Context,
) -> dict[int, str]:
    """Return a map of DecisionCombine id() → failure reason for decisions
    whose target note or parent bullet can't be resolved.

    Decisions NOT in the returned map are valid and safe to dispatch. We
    cache target-note parses keyed by resolved title so multiple combines
    targeting the same note only read it once.
    """
    failures: dict[int, str] = {}
    target_cache: dict[str, ParsedNote | None] = {}

    for decision in decisions:
        if not isinstance(decision, DecisionCombine):
            continue

        target_title = resolve(decision.target_note, rules=ctx.rules)

        # Same-note combines — validate parent against the source note
        # we'll read in execute(). Re-read here to keep pre-flight isolated.
        if target_title == source_title:
            key = source_title
        else:
            key = target_title

        if key not in target_cache:
            tref = ctx.backend.find_by_title(target_title)
            if tref is None:
                target_cache[key] = None
            else:
                tdata = ctx.backend.read(tref)
                tparsed = parse_note(tdata.content, rules=ctx.rules)
                if not tparsed.title:
                    tparsed.title = target_title
                target_cache[key] = tparsed

        parsed_target = target_cache[key]
        if parsed_target is None:
            failures[id(decision)] = "NOT_FOUND"
            continue

        matches = find_matches(parsed_target, decision.parent_bullet)
        if not matches:
            failures[id(decision)] = "PARENT_NOT_FOUND"
        elif len(matches) > 1:
            failures[id(decision)] = "AMBIGUOUS_PARENT"

    return failures


# ---------------------------------------------------------------------------
# Cross-note effects
# ---------------------------------------------------------------------------


def _apply_cross_note(
    req: CrossNoteRequest,
    *,
    ctx: Context,
    dry_run: bool,
) -> CrossNoteEffect:
    title = resolve(req.target_slug, rules=ctx.rules)
    ref = ctx.backend.find_by_title(title)

    # If target note doesn't exist, create it with just the appended lines
    # (unless the request requires the target to exist — combine does).
    if ref is None:
        if req.require_target_exists:
            # Pre-flight should have caught this. Belt-and-suspenders: no-op
            # instead of auto-creating, so a missing target for combine never
            # silently lands a stray sub-item in a new note.
            return CrossNoteEffect(note=title, diff=Diff())
        parsed = ParsedNote(title=title, title_html="", lines=list(req.lines_to_append))
        if not dry_run:
            body = render_note(parsed, ctx.rules)
            ctx.backend.create(title, body)
        return CrossNoteEffect(
            note=title,
            diff=Diff(
                added=[
                    DiffAdded(section="(new note)", bullet=line.text)
                    for line in req.lines_to_append
                ]
            ),
        )

    # Target exists — read fresh, insert, write back.
    note_data = ctx.backend.read(ref)
    parsed = parse_note(note_data.content, rules=ctx.rules)
    if not parsed.title:
        parsed.title = title

    added_lines = list(req.lines_to_append)

    if req.after_anchor is not None:
        # Insert right after the matching parent line. Pre-flight has
        # already verified the parent exists and is unique, but the note
        # may have changed between pre-flight and here — fall back to
        # appending rather than raising (the diff will still show the
        # sub-item landed; the pre-flight contract is best-effort).
        parent_matches = find_matches(parsed, req.after_anchor)
        if parent_matches:
            parent_line = parent_matches[0]
            insert_idx = None
            for idx, line in enumerate(parsed.lines):
                if line is parent_line:
                    insert_idx = idx + 1
                    break
            if insert_idx is not None:
                for offset, new_line in enumerate(added_lines):
                    parsed.lines.insert(insert_idx + offset, new_line)
            else:
                parsed.lines.extend(added_lines)
        else:
            parsed.lines.extend(added_lines)
    else:
        parsed.lines.extend(added_lines)

    if not dry_run:
        body = render_note(parsed, ctx.rules)
        ctx.backend.update(ref, body)

    return CrossNoteEffect(
        note=title,
        diff=Diff(
            added=[DiffAdded(section="", bullet=line.text) for line in added_lines]
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_diff(entries: list) -> Diff:
    added = [e for e in entries if isinstance(e, DiffAdded)]
    changed = [e for e in entries if isinstance(e, DiffChanged)]
    removed = [e for e in entries if isinstance(e, DiffRemoved)]
    moved = [e for e in entries if isinstance(e, DiffMoved)]
    return Diff(added=added, changed=changed, removed=removed, moved=moved)


def _decision_to_dict(decision) -> dict[str, Any]:
    return decision.model_dump(mode="json")


def _today_in_tz(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()
