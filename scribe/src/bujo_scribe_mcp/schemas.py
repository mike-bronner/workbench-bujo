"""Pydantic schemas for every scribe verb.

These are the authoritative input/output shapes — they mirror
`docs/scribe-contract.md` in workbench-bujo. Changing anything here is a
contract change; bump the package version and update dependents.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

# `Signifier` is intentionally a free-form string. Built-in keys — task,
# event, note, research — are recognized by every backend. Additional keys
# are validated at the verb-execution layer against
# `rules.signifiers.extensions`. A Literal here would prevent user-defined
# extensions from crossing the MCP boundary.
Signifier = str
# `Prefix` is a prefix-key string — built-ins are "priority", "inspiration",
# "explore"; users may add more via `rules.signifiers.prefix_extensions`.
Prefix = str
Ritual = Literal["daily", "weekly", "monthly", "yearly"]


class Bullet(BaseModel):
    signifier: Signifier
    text: str
    prefix: Prefix | None = Field(
        default=None,
        description=(
            "Optional prefix signifier — a built-in key "
            "(priority | inspiration | explore) or a user-defined key from "
            "rules.signifiers.prefix_extensions."
        ),
    )
    owner: str | None = Field(default=None, description="Owner, e.g. for family-calendar items.")
    source: str | None = Field(default=None, description="Provenance string the scribe may note inline.")


class Section(BaseModel):
    name: str
    bullets: list[Bullet] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Diff format (shared across mutation verbs)
# ---------------------------------------------------------------------------

class DiffAdded(BaseModel):
    section: str
    bullet: str


class DiffChanged(BaseModel):
    before: str
    after: str


class DiffRemoved(BaseModel):
    bullet: str


class DiffMoved(BaseModel):
    from_: str = Field(alias="from")
    to: str
    bullet: str

    model_config = {"populate_by_name": True}


class Diff(BaseModel):
    added: list[DiffAdded] = Field(default_factory=list)
    changed: list[DiffChanged] = Field(default_factory=list)
    removed: list[DiffRemoved] = Field(default_factory=list)
    moved: list[DiffMoved] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

ErrorCode = Literal[
    "INDEX_MISSING",
    "FOLDER_MISSING",
    "NOTE_NOT_FOUND",
    "RULE_VIOLATION",
    "AMBIGUOUS_BULLET",
    "NOT_FOUND",
    "STALE_WRITE_DETECTED",
    "BACKEND_ERROR",
    "PARENT_NOT_FOUND",
    "AMBIGUOUS_PARENT",
    "NOT_DROPPED",
]


class ScribeError(BaseModel):
    code: ErrorCode
    detail: str
    context: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Verb: read
# ---------------------------------------------------------------------------

class ReadInput(BaseModel):
    notes: list[str] = Field(description="Canonical slugs or explicit note titles.")


class ParsedLine(BaseModel):
    """A single semantic BuJo line as it appears on a note.

    The wire-side projection of the internal `parsing.BujoLine` — the raw
    HTML form is intentionally NOT exposed. Callers reason over signifier,
    prefix, text, depth, dropped, and anchor only. `anchor` round-trips
    back into `apply_decisions` as the `bullet` field.
    """

    signifier: Signifier = Field(
        description=(
            "Built-in key (task | event | note | completed | migrated | "
            "scheduled | sub_item) or a user-defined extension key."
        )
    )
    prefix: Prefix | None = Field(
        default=None,
        description="priority | inspiration | explore, or a user-defined extension key.",
    )
    text: str
    depth: int = Field(default=0, description="0 = top-level, 1+ = nested sub-item.")
    dropped: bool = Field(default=False, description="True iff line is wrapped in <s>…</s>.")
    anchor: str = Field(
        description="Stable identifier — pass back as `bullet` in apply_decisions."
    )


class NoteContent(BaseModel):
    title: str
    exists: bool
    lines: list[ParsedLine] | None = Field(
        default=None,
        description=(
            "Parsed BuJo lines from the note body. None when exists=False. "
            "Blank lines and unrecognized (non-BuJo) divs are filtered out — "
            "use bujo_scan with status='unrecognized' to surface non-BuJo "
            "content for maintenance."
        ),
    )
    retrieved_at: str


class ReadOutput(BaseModel):
    packet: dict[str, NoteContent]


# ---------------------------------------------------------------------------
# Verb: scaffold
# ---------------------------------------------------------------------------

class ScaffoldInput(BaseModel):
    target: str
    ritual: Ritual
    mode: Literal["create", "merge"]
    sections: list[Section] = Field(default_factory=list)


class ScaffoldWarning(BaseModel):
    code: ErrorCode
    bullet: str
    detail: str


class ScaffoldOutput(BaseModel):
    note_id: str
    created: bool
    diff: Diff
    warnings: list[ScaffoldWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verb: apply-decisions
# ---------------------------------------------------------------------------

class DecisionComplete(BaseModel):
    op: Literal["complete"]
    bullet: str


class DecisionMigrate(BaseModel):
    op: Literal["migrate"]
    bullet: str
    target: str


class DecisionSchedule(BaseModel):
    op: Literal["schedule"]
    bullet: str
    date: str  # YYYY-MM-DD


class DecisionDrop(BaseModel):
    op: Literal["drop"]
    bullet: str


class DecisionUndrop(BaseModel):
    """Reverse a previous `drop` — remove strikethrough, restore the line to
    its original active state (signifier is preserved; only the `dropped`
    flag is cleared).

    Use when a task was dropped in error and needs to come back. Fails with
    `NOT_DROPPED` if the matched line isn't currently dropped (prevents
    silent no-ops when the caller's mental model is wrong)."""

    op: Literal["undrop"]
    bullet: str


class DecisionAdd(BaseModel):
    op: Literal["add"]
    section: str
    bullet: Bullet


class DecisionUpdate(BaseModel):
    op: Literal["update"]
    bullet: str
    new_text: str


class DecisionReorder(BaseModel):
    op: Literal["reorder"]
    section: str
    order: list[str]


class DecisionRemove(BaseModel):
    """Delete a line from a note entirely — matching across BuJo lines AND
    UnrecognizedLines. Unlike `drop` (which strike-throughs a BuJo task),
    `remove` fully deletes. Use to clean malformed/legacy content that
    predates the scribe."""

    op: Literal["remove"]
    bullet: str


class DecisionCombine(BaseModel):
    """Combine a source bullet into another task as a nested sub-item.

    Source bullet on `note` gets `migrated` signifier (same as a normal
    migrate). On `target_note`, a new `sub_item` (depth=1) is inserted
    immediately after the matching `parent_bullet`, carrying the source
    text and prefix. Use this when a task belongs underneath another
    task — e.g., a narrow implementation detail being folded into a
    broader umbrella task.

    Fails atomically if `target_note` does not exist or `parent_bullet`
    does not match a single line on it (reasons: NOT_FOUND,
    PARENT_NOT_FOUND, AMBIGUOUS_PARENT). When it fails, the source note
    is NOT mutated."""

    op: Literal["combine"]
    bullet: str
    target_note: str
    parent_bullet: str


Decision = (
    DecisionComplete
    | DecisionMigrate
    | DecisionSchedule
    | DecisionDrop
    | DecisionUndrop
    | DecisionAdd
    | DecisionUpdate
    | DecisionReorder
    | DecisionRemove
    | DecisionCombine
)


class ApplyDecisionsInput(BaseModel):
    note: str
    decisions: list[Decision]
    dry_run: bool = Field(default=False, description="Compute diff without writing.")


class UnmatchedDecision(BaseModel):
    decision: dict[str, Any]
    reason: str


class CrossNoteEffect(BaseModel):
    note: str
    diff: Diff


class ApplyDecisionsOutput(BaseModel):
    note_id: str
    diff: Diff
    unmatched: list[UnmatchedDecision] = Field(default_factory=list)
    cross_note_effects: list[CrossNoteEffect] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verb: scan
# ---------------------------------------------------------------------------

class ScanFilter(BaseModel):
    status: Literal["open", "due_today", "overdue", "surfaces_today", "unrecognized"] | None = None
    type: Literal["task", "event", "note"] | None = None
    date: str | None = None  # YYYY-MM-DD, defaults to today


class ScanInput(BaseModel):
    scope: list[str]
    filter: ScanFilter = Field(default_factory=ScanFilter)


class ScanItem(BaseModel):
    note: str
    section: str
    signifier: Signifier
    text: str
    anchor: str
    due: str | None = None


class ScanOutput(BaseModel):
    items: list[ScanItem]


# ---------------------------------------------------------------------------
# Verb: summarize
# ---------------------------------------------------------------------------

SummaryKind = Literal["daily_morning", "weekly_retro", "monthly_retro", "yearly_retro"]


class SummarizeInput(BaseModel):
    kind: SummaryKind
    packet: dict[str, Any]
    format: Literal["display", "note"]


class SummarizeOutput(BaseModel):
    block: str
    stats: dict[str, Any] = Field(default_factory=dict)
