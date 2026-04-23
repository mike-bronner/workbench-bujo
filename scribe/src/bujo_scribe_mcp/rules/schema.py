"""Rules schema — pydantic models for the YAML rules file.

The schema is the authoritative spec for the rules layer. Every field is
backed by a decision in `docs/rules-decisions.md` (in workbench-bujo) or by
the Ryder Carroll BuJo methodology. Reading this file should tell a future
reader what the scribe enforces.

`extra = "forbid"` on every model — typos in the YAML surface immediately
rather than being silently ignored.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


# ---------------------------------------------------------------------------
# Signifiers
# ---------------------------------------------------------------------------


class BaseSignifiers(_StrictModel):
    """Base signifiers — appear at the start of every BuJo line.

    A line starts with either a base signifier alone (`• Task`) or a prefix
    followed by a base signifier (`✽• Priority task`). `sub_item` is a
    special case — it replaces the base signifier entirely for nested items
    and is always treated as a note.
    """

    task: str = Field(default="•", description="Open task — active effort expected.")
    event: str = Field(default="○", description="Event — outside agency or passive attendance.")
    note: str = Field(default="—", description="Plain note — observation or context.")
    completed: str = Field(default="x", description="Task completed.")
    migrated: str = Field(default=">", description="Migrated forward (typically to today).")
    scheduled: str = Field(default="<", description="Scheduled forward to a specific future date.")
    sub_item: str = Field(default="-", description="Nested sub-item; always a note; inherits parent type.")


class PrefixSignifiers(_StrictModel):
    """Optional prefixes that modify base signifiers.

    Placement: prefix REPLACES the leading alignment space. A prefixed line
    does not have a leading NBSP; its prefix character serves as alignment.
    """

    priority: str = Field(default="✽", description="Priority — this matters more right now.")
    inspiration: str = Field(
        default="!",
        description="Inspiration — realization or aha-moment discovered by reflection.",
    )
    explore: str = Field(
        default="◉",
        description="Explore — needs more research before it can be acted on.",
    )


class DroppedStyle(_StrictModel):
    """How dropped tasks are visually rendered (Gap 1)."""

    method: Literal["strikethrough_html"] = Field(
        default="strikethrough_html",
        description="Wrap the line content in <s>…</s>. Preserves the original signifier and text.",
    )


class ScheduledBehavior(_StrictModel):
    """Rules for the `<` scheduled signifier (Gap 2)."""

    requires_future_date: bool = Field(
        default=True,
        description=(
            "Scheduling requires a strictly-future date (> today in configured timezone). "
            "Without one, the decision is rejected and the task remains open."
        ),
    )
    auto_populate_future_log: bool = Field(
        default=True,
        description="When a task is scheduled, the scribe creates a Future Log entry as a cross-note effect.",
    )


SignifierClass = Literal["task", "event", "note"]


class SignifierExtension(_StrictModel):
    """User-defined custom base signifier (bullet type).

    BuJo encourages personalization — common extensions include `$` for
    expenses, `?` for questions, `♥` for wins. Extensions add new base
    signifiers without replacing the built-ins.

    `class` determines:
    - which setup-time ordering bucket the extension falls into (task/event/note)
    - how `bujo_scan` classifies the extension when filtering by type
    """

    key: str = Field(description="Stable identifier used in schemas and the parser's output.")
    char: str = Field(min_length=1, description="The single-character glyph displayed in the note.")
    class_: SignifierClass = Field(
        default="task",
        alias="class",
        description="Semantic class: how the extension participates in ordering and filters.",
    )
    description: str = Field(default="", description="Human-readable explanation.")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PrefixExtension(_StrictModel):
    """User-defined custom prefix signifier (Ryder Carroll's "signifier" sense).

    Prefixes decorate base bullets — in the built-ins: `✽` priority,
    `!` inspiration, `◉` explore. Common user additions:
    - `→` delegated
    - `…` waiting-on-external
    - `★` highlight

    Prefixes don't have a class — they're modifiers, not categories.
    """

    key: str = Field(description="Stable identifier used in schemas and the parser's output.")
    char: str = Field(min_length=1, description="The single-character glyph displayed in the note.")
    description: str = Field(default="", description="Human-readable explanation.")


class SignifiersConfig(_StrictModel):
    base: BaseSignifiers = Field(default_factory=BaseSignifiers)
    prefix: PrefixSignifiers = Field(default_factory=PrefixSignifiers)
    extensions: list[SignifierExtension] = Field(
        default_factory=list,
        description="User-defined custom base signifiers (bullet types). Must not collide with built-in keys or chars.",
    )
    prefix_extensions: list[PrefixExtension] = Field(
        default_factory=list,
        description="User-defined custom prefix signifiers. Must not collide with built-in keys or chars.",
    )
    dropped: DroppedStyle = Field(default_factory=DroppedStyle)
    scheduled: ScheduledBehavior = Field(default_factory=ScheduledBehavior)


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


LeadingGlyph = Literal["nbsp_single", "nbsp_pair", "none"]


class AlignmentConfig(_StrictModel):
    """Whitespace alignment rules (Gaps 3 & 4).

    The rules layer speaks in terms of abstract glyphs (nbsp_single,
    nbsp_pair). The backend layer translates those into concrete encodings
    (e.g. `&nbsp;` for Apple Notes, U+00A0 for Obsidian).
    """

    nonprefixed_leading: LeadingGlyph = Field(
        default="nbsp_single",
        description="Leading glyph for non-prefixed items so they align with prefixed lines.",
    )
    sub_item_indent_per_depth: Literal["nbsp_pair"] = Field(
        default="nbsp_pair",
        description="How much indent each depth level adds before the sub-item signifier.",
    )
    sub_item_max_depth: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum nesting depth (0 = no nesting allowed; 2 = up to two levels below top).",
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class AgencyRules(_StrictModel):
    task_definition: str = Field(
        default="Coordinates, executes, or runs; active effort beyond showing up.",
    )
    event_definition: str = Field(
        default="Happens outside agency OR passive participation.",
    )


class FamilyCalendarDetection(_StrictModel):
    """Owner detection for shared-calendar items (user-customized).

    Off by default. When enabled, the scribe inspects incoming calendar
    event titles and classifies ownership. Others' items are included only
    when they affect the self-user's day.
    """

    enabled: bool = Field(default=False)
    self_markers: list[str] = Field(
        default_factory=list,
        description="Substrings that mark an event as belonging to the self user.",
    )
    other_markers: list[str] = Field(
        default_factory=list,
        description="Substrings that mark an event as belonging to another household member.",
    )


class ClassificationConfig(_StrictModel):
    agency: AgencyRules = Field(default_factory=AgencyRules)
    family_calendar: FamilyCalendarDetection = Field(default_factory=FamilyCalendarDetection)


# ---------------------------------------------------------------------------
# Prefix discipline
# ---------------------------------------------------------------------------


class PrefixDisciplineConfig(_StrictModel):
    strip_action_test_enabled: bool = Field(
        default=True,
        description=(
            "Before classifying a bullet, strip its action-verb tail "
            "(track closely, watch for, follow up) and classify by the remainder."
        ),
    )
    inspiration_plus_action: Literal["two_entries"] = Field(
        default="two_entries",
        description="When an insight has a follow-up, emit the !— note AND a separate • task; never collapse.",
    )


# ---------------------------------------------------------------------------
# Entry style
# ---------------------------------------------------------------------------


class SetupTimeOrdering(_StrictModel):
    """Morning-scaffold-only ordering rule. After scaffold, items append chronologically."""

    enabled: bool = Field(default=True)
    order: list[Literal["events", "tasks", "notes"]] = Field(
        default_factory=lambda: ["events", "tasks", "notes"],
    )


class EntryStyleConfig(_StrictModel):
    prefer_single_line: bool = Field(default=True)
    single_block: bool = Field(
        default=True,
        description="Daily log is one continuous block — no headers, no blank lines between groups.",
    )
    setup_time_ordering: SetupTimeOrdering = Field(default_factory=SetupTimeOrdering)


# ---------------------------------------------------------------------------
# Tiers — all single block (Gap 5)
# ---------------------------------------------------------------------------


class TiersConfig(_StrictModel):
    """Tier structure (daily / weekly / monthly / yearly).

    All tiers use the same single-mono-block format — overrides the outdated
    'Summary-note section layouts' in the current Apple Notes index.
    """

    all_single_block: bool = Field(
        default=True,
        description="Every tier note is a single continuous mono BuJo block — no section headers.",
    )


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


WeekStartDay = Literal["sunday", "monday"]


class NamingConfig(_StrictModel):
    """Note naming conventions per tier. Use strftime-style tokens."""

    daily: str = Field(default="%Y-%m-%d — %A", description="e.g. 2026-04-19 — Sunday")
    weekly: str = Field(
        default="%Y-%m-%d - Week %U",
        description=(
            "Weekly note title pattern. Anchored to the start of the week "
            "containing today. Use %U for Sunday-based week numbers (weeks "
            "start Sunday); use %V for ISO/Monday-based numbers."
        ),
    )
    monthly: str = Field(default="%Y-%m - %B", description="e.g. 2026-04 - April")
    yearly: str = Field(default="%Y - Yearly Review", description="e.g. 2026 - Yearly Review")
    week_start_day: WeekStartDay = Field(
        default="sunday",
        description=(
            "Which day starts the week. Drives the resolver's `weekly_current` "
            "slug: the weekly note is anchored to this day of the week "
            "containing today. Defaults to 'sunday' per Mike's practice; "
            "ISO/business convention uses 'monday'."
        ),
    )


# ---------------------------------------------------------------------------
# Run order & prerequisites
# ---------------------------------------------------------------------------


class PrerequisiteMap(_StrictModel):
    """Which tiers must exist before running each tier on boundary days."""

    daily: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "sunday": ["weekly"],
            "month_start": ["monthly"],
            "year_start": ["yearly"],
        }
    )
    weekly: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "month_start": ["monthly"],
            "year_start": ["yearly"],
        }
    )
    monthly: dict[str, list[str]] = Field(
        default_factory=lambda: {"year_start": ["yearly"]}
    )
    yearly: dict[str, list[str]] = Field(default_factory=dict)


class RunOrderConfig(_StrictModel):
    sequence: list[Literal["yearly", "monthly", "weekly", "daily"]] = Field(
        default_factory=lambda: ["yearly", "monthly", "weekly", "daily"],
        description="Strict ordering when multiple tiers fall on the same day.",
    )
    prerequisites: PrerequisiteMap = Field(default_factory=PrerequisiteMap)


# ---------------------------------------------------------------------------
# Carry-forward
# ---------------------------------------------------------------------------


class CarryForwardConfig(_StrictModel):
    """What each summary tier pulls from lower tiers when it runs."""

    weekly: list[str] = Field(
        default_factory=lambda: [
            "all incomplete tasks from the most recent daily log",
            "insights (!—) from daily entries since the previous weekly log",
            "significant items from the past week",
            "Future Log items scheduled for the upcoming week",
        ]
    )
    monthly: list[str] = Field(
        default_factory=lambda: [
            "all incomplete tasks from the most recent daily log",
            "insights or significant items from weekly logs of the past month",
            "Future Log items occurring in the upcoming month",
        ]
    )
    yearly: list[str] = Field(
        default_factory=lambda: [
            "all incomplete tasks from the most recent daily log",
            "insights or significant items from monthly logs of the past year",
            "Future Log items for the upcoming year",
        ]
    )


# ---------------------------------------------------------------------------
# Harvest routing tags — prevent double-harvesting across tiers
# ---------------------------------------------------------------------------


class HarvestTags(_StrictModel):
    daily_to_weekly: str = Field(default="→ Routed to weekly")
    weekly_to_monthly: str = Field(default="→ Routed to monthly")
    monthly_to_yearly: str = Field(default="→ Routed to yearly")


class HarvestRoutingConfig(_StrictModel):
    enabled: bool = Field(default=True)
    tags: HarvestTags = Field(default_factory=HarvestTags)
    terminal_tier: Literal["yearly"] = Field(
        default="yearly",
        description="Final tier — insights that reach here stay here.",
    )


# ---------------------------------------------------------------------------
# Future Log
# ---------------------------------------------------------------------------


class FutureLogConfig(_StrictModel):
    enabled: bool = Field(default=True)
    note_title: str = Field(default="Future Log")
    on_schedule_day_behavior: Literal["pull_and_remove"] = Field(
        default="pull_and_remove",
        description=(
            "When a Future Log item's scheduled day arrives, pull it into the daily "
            "AND remove from the Future Log. From that point forward it lives in the daily."
        ),
    )


# ---------------------------------------------------------------------------
# Backends — backend-specific rendering constants
# ---------------------------------------------------------------------------


class AppleNotesHtmlConfig(_StrictModel):
    """Apple Notes HTML rendering (Gap 7).

    These are Apple-Notes-specific — other backends define their own formatting.
    Exact values settle during parser/renderer implementation; the structure is
    stable now so callers have a contract to rely on.
    """

    monospace_wrapper: str = Field(
        default='<div><font face="Menlo-Regular"><tt>{content}</tt></font></div>',
        description="Line template — {content} is substituted with the rendered BuJo line text.",
    )
    blank_line: str = Field(default="<div><br></div>")
    nbsp_encoding: str = Field(
        default="&nbsp;",
        description="Apple Notes demands the HTML entity literal — U+00A0 and friends break on round-trip.",
    )
    strikethrough_open: str = Field(default="<s>")
    strikethrough_close: str = Field(default="</s>")
    title_open: str = Field(default='<div><b><span style="font-size: 24px">')
    title_close: str = Field(default="</span></b><br></div>")
    heading_h2_size_px: int = Field(default=18)


class AppleNotesBackendConfig(_StrictModel):
    folder: str = Field(default="📓 Journal")
    index_note_title: str = Field(default="📓 Journal Index")
    html: AppleNotesHtmlConfig = Field(default_factory=AppleNotesHtmlConfig)


class BackendsConfig(_StrictModel):
    apple_notes: AppleNotesBackendConfig = Field(default_factory=AppleNotesBackendConfig)


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class Rules(_StrictModel):
    """Root rules model — loaded from YAML, validated at startup."""

    version: int = Field(default=1, description="Rules schema version for forward compat.")
    timezone: str = Field(default="America/Phoenix")

    signifiers: SignifiersConfig = Field(default_factory=SignifiersConfig)
    alignment: AlignmentConfig = Field(default_factory=AlignmentConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    prefix_discipline: PrefixDisciplineConfig = Field(default_factory=PrefixDisciplineConfig)
    entry_style: EntryStyleConfig = Field(default_factory=EntryStyleConfig)
    tiers: TiersConfig = Field(default_factory=TiersConfig)
    naming: NamingConfig = Field(default_factory=NamingConfig)
    run_order: RunOrderConfig = Field(default_factory=RunOrderConfig)
    carry_forward: CarryForwardConfig = Field(default_factory=CarryForwardConfig)
    harvest_routing: HarvestRoutingConfig = Field(default_factory=HarvestRoutingConfig)
    future_log: FutureLogConfig = Field(default_factory=FutureLogConfig)
    backends: BackendsConfig = Field(default_factory=BackendsConfig)

    @model_validator(mode="after")
    def _check_extension_collisions(self) -> "Rules":
        """User extensions may not reuse built-in signifier keys or chars."""
        base = self.signifiers.base
        prefix = self.signifiers.prefix

        base_builtin_keys = {
            "task", "event", "note", "completed", "migrated", "scheduled", "sub_item",
        }
        prefix_builtin_keys = {"priority", "inspiration", "explore"}

        # All built-in chars share a single "reserved chars" set — extensions of
        # EITHER kind can't reuse any built-in char, because the parser scans
        # the same input character stream for both prefix and base detection.
        builtin_chars = {
            base.task, base.event, base.note, base.completed,
            base.migrated, base.scheduled, base.sub_item,
            prefix.priority, prefix.inspiration, prefix.explore,
        }

        seen_base_keys: set[str] = set()
        seen_prefix_keys: set[str] = set()
        seen_chars: set[str] = set()

        for ext in self.signifiers.extensions:
            if ext.key in base_builtin_keys:
                raise ValueError(f"Base extension key {ext.key!r} collides with a built-in.")
            if ext.char in builtin_chars:
                raise ValueError(f"Base extension char {ext.char!r} collides with a built-in.")
            if ext.key in seen_base_keys:
                raise ValueError(f"Duplicate base extension key: {ext.key!r}")
            if ext.char in seen_chars:
                raise ValueError(f"Duplicate extension char: {ext.char!r}")
            seen_base_keys.add(ext.key)
            seen_chars.add(ext.char)

        for ext in self.signifiers.prefix_extensions:
            if ext.key in prefix_builtin_keys:
                raise ValueError(f"Prefix extension key {ext.key!r} collides with a built-in.")
            if ext.char in builtin_chars:
                raise ValueError(f"Prefix extension char {ext.char!r} collides with a built-in.")
            if ext.key in seen_prefix_keys:
                raise ValueError(f"Duplicate prefix extension key: {ext.key!r}")
            if ext.char in seen_chars:
                raise ValueError(f"Duplicate extension char: {ext.char!r}")
            seen_prefix_keys.add(ext.key)
            seen_chars.add(ext.char)

        return self
