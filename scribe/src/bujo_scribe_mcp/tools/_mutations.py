"""Per-op mutation helpers — apply a single decision to a ParsedNote in place.

Each function returns a list of `DiffAdded|DiffChanged|DiffRemoved|DiffMoved`
entries describing what changed. Mutations that can't apply (bullet not
found, ambiguous match, constraint failure) return a string reason code
instead — the caller routes it into `unmatched`.

Cross-note effects (migrate, schedule) return side-effect instructions as
well, which the orchestrator resolves against other notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from bujo_scribe_mcp.parsing import BlankLine, BujoLine, ParsedNote, UnrecognizedLine
from bujo_scribe_mcp.parsing.renderer import render_line
from bujo_scribe_mcp.rules import Rules
from bujo_scribe_mcp.schemas import (
    Bullet,
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
    DecisionUpdateUnrecognized,
    DiffAdded,
    DiffChanged,
    DiffMoved,
    DiffRemoved,
)
from bujo_scribe_mcp.tools._matching import find_descendants, find_matches


# ---------------------------------------------------------------------------
# Side-effect request passed back to orchestrator
# ---------------------------------------------------------------------------


@dataclass
class CrossNoteRequest:
    """The mutation wants another note modified, too.

    If `after_anchor` is None, lines are appended at the end. Otherwise,
    the handler finds the matching parent line on the target note and
    inserts immediately after it; if the parent can't be found, the
    request fails (see apply_decisions._apply_cross_note)."""

    target_slug: str  # resolver slug or explicit title
    lines_to_append: list[BujoLine]
    after_anchor: str | None = None
    require_target_exists: bool = False


# ---------------------------------------------------------------------------
# Matching helper — returns (BujoLine | reason-code)
# ---------------------------------------------------------------------------


def _resolve_target(note: ParsedNote, bullet_text: str) -> BujoLine | str:
    """Return the matched line, or an error reason code."""
    matches = find_matches(note, bullet_text)
    if not matches:
        return "NOT_FOUND"
    if len(matches) > 1:
        return "AMBIGUOUS_BULLET"
    return matches[0]


# ---------------------------------------------------------------------------
# Op implementations
# ---------------------------------------------------------------------------


def apply_complete(
    note: ParsedNote,
    decision: DecisionComplete,
    rules: Rules,
) -> tuple[list, str | None]:
    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target)

    before_html = render_line(target, rules)
    target.signifier = "completed"
    target.anchor = target.anchor  # unchanged; completion preserves text
    after_html = render_line(target, rules)

    return (
        [DiffChanged(before=before_html, after=after_html)],
        None,
    )


def apply_drop(
    note: ParsedNote,
    decision: DecisionDrop,
    rules: Rules,
) -> tuple[list, str | None]:
    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target)

    diffs: list = []
    for line in [target, *find_descendants(note, target)]:
        if line.dropped:
            continue
        before_html = render_line(line, rules)
        line.dropped = True
        after_html = render_line(line, rules)
        diffs.append(DiffChanged(before=before_html, after=after_html))

    return (diffs, None)


def apply_undrop(
    note: ParsedNote,
    decision: DecisionUndrop,
    rules: Rules,
) -> tuple[list, str | None]:
    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target)

    if not target.dropped:
        return ([], "NOT_DROPPED")

    diffs: list = []
    for line in [target, *find_descendants(note, target)]:
        if not line.dropped:
            continue
        before_html = render_line(line, rules)
        line.dropped = False
        after_html = render_line(line, rules)
        diffs.append(DiffChanged(before=before_html, after=after_html))

    return (diffs, None)


def apply_update(
    note: ParsedNote,
    decision: DecisionUpdate,
    rules: Rules,
) -> tuple[list, str | None]:
    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target)

    before_html = render_line(target, rules)
    target.text = decision.new_text
    after_html = render_line(target, rules)

    return (
        [DiffChanged(before=before_html, after=after_html)],
        None,
    )


def apply_add(
    note: ParsedNote,
    decision: DecisionAdd,
    rules: Rules,
) -> tuple[list, str | None]:
    bullet: Bullet = decision.bullet
    new_line = BujoLine(
        signifier=bullet.signifier,
        text=bullet.text,
        prefix=_prefix_key(bullet),
        anchor=bullet.text[:60],
    )
    note.lines.append(new_line)
    return (
        [DiffAdded(section=decision.section, bullet=render_line(new_line, rules))],
        None,
    )


def apply_remove(
    note: ParsedNote,
    decision: DecisionRemove,
    rules: Rules,
) -> tuple[list, str | None]:
    """Remove a line from the note — works across BujoLine AND UnrecognizedLine.

    Matching rule (case-sensitive substring):
    - BujoLine: exact text match OR anchor match OR substring of text
    - UnrecognizedLine: substring match against the raw_html's text content
    - BlankLine: never matches

    Ambiguity rules: if >1 line matches, return AMBIGUOUS_BULLET without
    mutating. If 0 match, return NOT_FOUND.
    """
    needle = decision.bullet.strip()
    if not needle:
        return ([], "NOT_FOUND")

    # Collect (index, rendered-representation) pairs for matches.
    matches: list[tuple[int, str]] = []
    for idx, line in enumerate(note.lines):
        if isinstance(line, BujoLine):
            if line.text == needle or line.anchor == needle or needle in line.text:
                matches.append((idx, render_line(line, rules)))
        elif isinstance(line, UnrecognizedLine):
            # Strip tags from raw_html for a best-effort text match.
            import html as _html
            import re as _re

            unwrapped = _re.sub(r"<[^>]+>", "", _html.unescape(line.raw_html)).strip()
            if needle in unwrapped:
                matches.append((idx, line.raw_html))

    if not matches:
        return ([], "NOT_FOUND")
    if len(matches) > 1:
        return ([], "AMBIGUOUS_BULLET")

    idx, rendered = matches[0]
    matched_line = note.lines[idx]

    indices_to_remove = [idx]
    diffs: list = [DiffRemoved(bullet=rendered)]
    if isinstance(matched_line, BujoLine):
        for desc in find_descendants(note, matched_line):
            try:
                desc_idx = note.lines.index(desc)
            except ValueError:
                continue
            indices_to_remove.append(desc_idx)
            diffs.append(DiffRemoved(bullet=render_line(desc, rules)))

    for i in sorted(indices_to_remove, reverse=True):
        del note.lines[i]
    return (diffs, None)


def apply_update_unrecognized(
    note: ParsedNote,
    decision: DecisionUpdateUnrecognized,
    rules: Rules,
) -> tuple[list, str | None]:
    """Replace an UnrecognizedLine's raw_html in place — added in 0.10.0.

    Matches `decision.anchor` as a substring of each UnrecognizedLine's
    raw_html. Use a unique substring (e.g., `<object><table` for a habit
    tracker table) to disambiguate. Reasons:
    - NOT_FOUND: no UnrecognizedLine's raw_html contains the anchor
    - AMBIGUOUS_BULLET: more than one match
    On success: replaces the matched line's raw_html with new_html;
    returns a single DiffChanged.
    """
    matches: list[tuple[int, UnrecognizedLine]] = []
    for idx, line in enumerate(note.lines):
        if isinstance(line, UnrecognizedLine) and decision.anchor in line.raw_html:
            matches.append((idx, line))

    if not matches:
        return ([], "NOT_FOUND")
    if len(matches) > 1:
        return ([], "AMBIGUOUS_BULLET")

    idx, old = matches[0]
    note.lines[idx] = UnrecognizedLine(raw_html=decision.new_html)
    return ([DiffChanged(before=old.raw_html, after=decision.new_html)], None)


def apply_reorder(
    note: ParsedNote,
    decision: DecisionReorder,
    rules: Rules,
) -> tuple[list, str | None]:
    # For single-block tier notes (Gap 5), "section" is advisory — we reorder
    # matching BujoLines globally in the given order. Non-BujoLines (blanks,
    # unrecognized) keep their relative position.
    #
    # Cascade: a top-level (depth=0) BujoLine plus all immediately-following
    # descendant BujoLines form one "unit" and move together. Needles match
    # against the parent's text only.

    units: list[tuple[list[int], BujoLine]] = []
    current_indices: list[int] = []
    current_parent: BujoLine | None = None

    def _flush() -> None:
        nonlocal current_indices, current_parent
        if current_parent is not None:
            units.append((current_indices, current_parent))
            current_indices = []
            current_parent = None

    for i, line in enumerate(note.lines):
        if isinstance(line, BujoLine):
            if line.depth == 0:
                _flush()
                current_indices = [i]
                current_parent = line
            elif current_parent is not None:
                current_indices.append(i)
            else:
                # Orphan depth>0 line (no preceding parent in this run) —
                # treat as its own unit so it remains reorderable.
                units.append(([i], line))
        else:
            _flush()
    _flush()

    new_order: list[tuple[list[int], BujoLine]] = []
    used_ids: set[int] = set()
    for needle in decision.order:
        for unit in units:
            if id(unit[1]) in used_ids:
                continue
            if needle.strip() in unit[1].text:
                new_order.append(unit)
                used_ids.add(id(unit[1]))
                break
    for unit in units:
        if id(unit[1]) not in used_ids:
            new_order.append(unit)

    bujo_slots = sorted(i for unit in units for i in unit[0])
    new_bujo_lines: list[BujoLine] = []
    for indices, _ in new_order:
        for idx in indices:
            line = note.lines[idx]
            assert isinstance(line, BujoLine)
            new_bujo_lines.append(line)

    moves: list = []
    for slot, line in zip(bujo_slots, new_bujo_lines, strict=True):
        if note.lines[slot] is not line:
            moves.append(DiffMoved(**{"from": "bujo", "to": "bujo", "bullet": render_line(line, rules)}))
        note.lines[slot] = line

    return (moves, None)


def apply_migrate(
    note: ParsedNote,
    decision: DecisionMigrate,
    rules: Rules,
) -> tuple[list, str | None, CrossNoteRequest | None]:
    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target, None)

    descendants = find_descendants(note, target)

    # Snapshot the entire branch for the target note.
    # Parent re-emits as an open task by default; descendants preserve
    # signifier (re-opening any that were already migrated).
    carry_lines: list[BujoLine] = [
        BujoLine(
            signifier=target.signifier if target.signifier != "migrated" else "task",
            text=target.text,
            prefix=target.prefix,
            depth=target.depth,
            anchor=target.anchor,
        )
    ]
    for desc in descendants:
        carry_lines.append(
            BujoLine(
                signifier=desc.signifier if desc.signifier != "migrated" else "sub_item",
                text=desc.text,
                prefix=desc.prefix,
                depth=desc.depth,
                anchor=desc.anchor,
            )
        )

    # Mark source: parent + all descendants → migrated
    diffs: list = []
    for line in [target, *descendants]:
        before_html = render_line(line, rules)
        line.signifier = "migrated"
        after_html = render_line(line, rules)
        diffs.append(DiffChanged(before=before_html, after=after_html))

    diffs.append(
        DiffMoved(**{"from": note.title, "to": decision.target, "bullet": render_line(carry_lines[0], rules)})
    )
    return (diffs, None, CrossNoteRequest(target_slug=decision.target, lines_to_append=carry_lines))


def apply_combine(
    note: ParsedNote,
    decision: DecisionCombine,
    rules: Rules,
) -> tuple[list, str | None, CrossNoteRequest | None]:
    """Combine a source bullet into a parent on another note as a sub-item.

    Source: signifier → `migrated` (same visual effect as a regular migrate).
    Target: a new `sub_item` line (depth=1) is inserted right after the
    matching `parent_bullet`, carrying the source text + prefix.

    Parent-validation happens in the cross-note handler; if the parent
    can't be found on the target, the cross-note handler raises
    CombineTargetError and apply_decisions rolls back the source mutation.
    """
    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target, None)

    descendants = find_descendants(note, target)
    base_depth = target.depth
    max_depth = rules.alignment.sub_item_max_depth

    def _clamp(d: int) -> int:
        return max(1, min(d, max_depth))

    carry_lines: list[BujoLine] = [
        BujoLine(
            signifier="sub_item",
            text=target.text,
            prefix=target.prefix,
            depth=1,
            anchor=target.text[:60],
        )
    ]
    for desc in descendants:
        carry_lines.append(
            BujoLine(
                signifier="sub_item",
                text=desc.text,
                prefix=desc.prefix,
                depth=_clamp(1 + (desc.depth - base_depth)),
                anchor=desc.text[:60],
            )
        )

    diffs: list = []
    for line in [target, *descendants]:
        before_html = render_line(line, rules)
        line.signifier = "migrated"
        after_html = render_line(line, rules)
        diffs.append(DiffChanged(before=before_html, after=after_html))

    diffs.append(
        DiffMoved(
            **{
                "from": note.title,
                "to": decision.target_note,
                "bullet": render_line(carry_lines[0], rules),
            }
        )
    )
    return (
        diffs,
        None,
        CrossNoteRequest(
            target_slug=decision.target_note,
            lines_to_append=carry_lines,
            after_anchor=decision.parent_bullet,
            require_target_exists=True,
        ),
    )


def apply_schedule(
    note: ParsedNote,
    decision: DecisionSchedule,
    rules: Rules,
    *,
    today: date,
    future_log_slug: str = "future_log",
) -> tuple[list, str | None, CrossNoteRequest | None]:
    # Gap 2 guard — future date required.
    try:
        scheduled_date = date.fromisoformat(decision.date)
    except ValueError:
        return ([], "SCHEDULE_NEEDS_FUTURE_DATE", None)

    if scheduled_date <= today:
        return ([], "SCHEDULE_NEEDS_FUTURE_DATE", None)

    target = _resolve_target(note, decision.bullet)
    if isinstance(target, str):
        return ([], target, None)

    descendants = find_descendants(note, target)

    # Future Log entry: parent line carries the date prefix + provenance.
    # Descendants follow as sub-items preserving their depth (relative to
    # their original parent), inheriting the date semantics by adjacency.
    fl_lines: list[BujoLine] = [
        BujoLine(
            signifier="scheduled",
            text=f"[{decision.date}] {target.text}  (from {note.title})",
            anchor=f"[{decision.date}] {target.text}"[:60],
        )
    ]
    for desc in descendants:
        fl_lines.append(
            BujoLine(
                signifier=desc.signifier if desc.signifier != "scheduled" else "sub_item",
                text=desc.text,
                prefix=desc.prefix,
                depth=desc.depth,
                anchor=desc.anchor,
            )
        )

    # Mark source: parent + all descendants → scheduled
    diffs: list = []
    for line in [target, *descendants]:
        before_html = render_line(line, rules)
        line.signifier = "scheduled"
        after_html = render_line(line, rules)
        diffs.append(DiffChanged(before=before_html, after=after_html))

    diffs.append(
        DiffMoved(**{"from": note.title, "to": future_log_slug, "bullet": render_line(fl_lines[0], rules)})
    )
    return (diffs, None, CrossNoteRequest(target_slug=future_log_slug, lines_to_append=fl_lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prefix_key(bullet: Bullet):
    """Return the internal prefix key for a Bullet, or None."""
    return bullet.prefix


# ---------------------------------------------------------------------------
# Scaffold helper — build a fresh ParsedNote from Section input
# ---------------------------------------------------------------------------


def build_scaffold_lines(sections, rules: Rules, setup_time: bool) -> list[BujoLine | BlankLine]:
    """Build the line sequence for a scaffold.

    `setup_time=True` triggers Gap-rule ordering: events → tasks → notes,
    regardless of the order sections were provided in.
    Otherwise preserves section order and bullet order exactly.
    """
    all_bullets: list[tuple[str, Bullet]] = []
    for section in sections:
        for bullet in section.bullets:
            all_bullets.append((section.name, bullet))

    if setup_time and rules.entry_style.setup_time_ordering.enabled:
        order = rules.entry_style.setup_time_ordering.order
        bucket_of = _sig_to_bucket(rules)
        bucket_position = {bucket: i for i, bucket in enumerate(order)}
        indexed = list(enumerate(all_bullets))
        indexed.sort(
            key=lambda pair: (
                bucket_position.get(bucket_of.get(pair[1][1].signifier, "tasks"), 999),
                pair[0],
            )
        )
        all_bullets = [b for _, b in indexed]

    lines: list[BujoLine | BlankLine] = []
    for _, bullet in all_bullets:
        lines.append(
            BujoLine(
                signifier=bullet.signifier,
                text=bullet.text,
                prefix=_prefix_key(bullet),
                anchor=bullet.text[:60],
            )
        )
    return lines


def _sig_to_bucket(rules: Rules) -> dict[str, str]:
    """Map signifier keys → setup-time-ordering bucket names (events/tasks/notes).

    Built-in keys are hardcoded; extensions contribute their `class` field.
    Unknown keys default to `tasks` (callers that pass an unknown signifier
    see it sorted with tasks, which is the least-surprising default).
    """
    bucket: dict[str, str] = {
        "task": "tasks",
        "event": "events",
        "note": "notes",
        "completed": "tasks",
        "migrated": "tasks",
        "scheduled": "tasks",
        "sub_item": "notes",
    }
    # `class` is "task" | "event" | "note" — map to "tasks" / "events" / "notes" bucket.
    for ext in rules.signifiers.extensions:
        bucket[ext.key] = f"{ext.class_}s"
    return bucket
