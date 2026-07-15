"""Guards the "ask the question, don't narrate what you're waiting for" invariant.

Regression test for issue #10: an unattended overnight ``/bujo`` run was
ending with a prose summary of pending steps —

    Awaiting Mike for:
    The check-in, habit check-in, disposition of the open task, ...

— instead of invoking ``AskUserQuestion`` for the first interactive prompt.
That narration asks nothing and leaves the session looking complete, so the
morning ritual never actually starts.

An LLM-driven ritual can't be run deterministically in CI, so — exactly as
``test_session_warmup_drift.py`` does for the warmup hook — these tests assert
the *prompt-file invariant that drives the correct behavior*: the ritual
protocol and the ``/bujo`` entrypoint must instruct the agent to lead with the
``AskUserQuestion`` tool call, and must name the "Awaiting Mike for…"
narration only ever as a forbidden pattern, never as sanctioned output.
"""

from __future__ import annotations

from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root
REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "skills" / "rituals" / "bujo-ritual.md"
ENTRYPOINT = REPO / "commands" / "bujo.md"

# The exact narration shape the bug produced (issue #10). It must appear in the
# prompt files ONLY inside a guardrail that forbids it.
FORBIDDEN_NARRATION = "awaiting mike for"

# A negation must sit next to every occurrence of the forbidden phrase, so the
# phrase can never be reintroduced as legitimate output without tripping this.
PROHIBITIONS = ("forbidden", "never", "not ", "don't", "do not")


def _negation_windows(text: str, needle: str, radius: int = 300) -> list[str]:
    """Return the ±radius context around each occurrence of ``needle``."""
    low = text.lower()
    out: list[str] = []
    start = 0
    while (i := low.find(needle, start)) != -1:
        out.append(low[max(0, i - radius) : i + len(needle) + radius])
        start = i + len(needle)
    return out


def _assert_only_forbidden(path: Path) -> None:
    windows = _negation_windows(path.read_text(), FORBIDDEN_NARRATION)
    assert windows, (
        f"{path.name} must name the 'Awaiting Mike for…' narration so the "
        "guardrail forbidding it stays anchored; the phrase is missing."
    )
    for w in windows:
        assert any(p in w for p in PROHIBITIONS), (
            f"{path.name} mentions 'Awaiting Mike for…' without a nearby "
            "prohibition — it reads as sanctioned output, not a forbidden one."
        )


def test_protocol_forbids_pending_step_narration():
    _assert_only_forbidden(PROTOCOL)


def test_entrypoint_forbids_pending_step_narration():
    _assert_only_forbidden(ENTRYPOINT)


def test_protocol_leads_with_askuserquestion():
    text = PROTOCOL.read_text().lower()
    assert "askuserquestion" in text
    # The first interactive action must be the tool call, stated as such.
    assert "lead with the question" in text


def test_entrypoint_leads_with_askuserquestion():
    text = ENTRYPOINT.read_text().lower()
    assert "askuserquestion" in text
    assert "lead with the question" in text


def test_entrypoint_documents_unattended_block():
    # AC #4: an unattended/overnight run is documented as expected to block at
    # the first interactive prompt, not to auto-complete or summarize.
    text = ENTRYPOINT.read_text().lower()
    assert "unattended" in text
    assert "overnight" in text
    assert "askuserquestion" in text
    assert "block" in text


# ---------------------------------------------------------------------------
# Step 4 A2 — Future Log items are triaged per item, not auto-migrated.
#
# Regression guard for issue #13: the daily ritual was migrating every
# surfacing Future Log entry straight onto today's note with no review.
# The fix makes Step 4 A2 present each surfacing (and overdue) item via
# ``AskUserQuestion`` *before* any ``apply_decisions`` call, offering four
# dispositions — Carry forward / Drop / Reschedule / Mark complete — of which
# only Carry forward reaches today. Same as the sibling tests above, an
# LLM-driven ritual can't run in CI, so these assert the prompt-file
# invariants that drive the behavior, scoped to the A2 section.
# ---------------------------------------------------------------------------


def _a2_section() -> str:
    """The text of Step 4 Part A's A2 block (lowercased).

    Sliced from the A2 heading to the start of Part B so an assertion can't
    accidentally pass on a phrase that lives elsewhere in the protocol.
    """
    text = PROTOCOL.read_text()
    start = text.index("A2. Triage Future Log")
    end = text.index("### Part B", start)
    return text[start:end].lower()


def test_a2_triages_each_item_before_dispatch():
    # AC: no automatic migration — each item is presented via AskUserQuestion
    # BEFORE any apply_decisions call.
    a2 = _a2_section()
    assert "askuserquestion" in a2
    assert "before** any `bujo_apply_decisions`" in a2
    assert "never** carried forward automatically" in a2


def test_a2_offers_four_dispositions():
    # AC: four options per item.
    a2 = _a2_section()
    for option in ("carry forward", "drop", "reschedule", "mark complete"):
        assert option in a2, f"A2 triage is missing the '{option}' option"


def test_a2_preview_shows_text_and_original_date():
    # AC: each prompt shows the item's full text + original scheduled date in
    # the `preview` field so context stays on hover, not in chat.
    a2 = _a2_section()
    assert "preview" in a2
    assert "full text and original scheduled date" in a2
    assert "<scan_item.text> — scheduled <scan_item.due>" in a2


def test_a2_carry_forward_is_the_only_path_to_today():
    # AC: only "Carry forward" lands on today (via the `surface` op's
    # cross-note effect, which removes the source — no `>` stub); the other
    # three mutate the Future Log only.
    a2 = _a2_section()
    assert "surface` (target `today`)" in a2
    assert "only option that lands anything on today" in a2
    assert "mutate the future log only" in a2


def test_a2_drop_path_mutates_future_log_only():
    # AC (all-drop path): Drop strikes the Future Log line; nothing reaches today.
    a2 = _a2_section()
    assert "drop" in a2
    assert "nothing reaches today" in a2


def test_a2_reschedule_prompts_for_date_and_updates_in_place():
    # AC (reschedule with date prompt): ask for a new (future) date, then
    # `update` the date tag in place — NOT `schedule`, which would duplicate.
    a2 = _a2_section()
    assert "reschedule" in a2
    assert "ask mike for the new date" in a2 and "must be future" in a2
    assert "update" in a2
    assert "not** `schedule`" in a2


def test_a2_mark_complete_stamps_future_log_entry():
    # AC: Mark complete resolves the Future Log entry itself (never migrated,
    # so there is no today line to complete).
    a2 = _a2_section()
    assert "complete" in a2
    assert "future log entry itself" in a2


def test_a2_overdue_items_get_same_triage_flagged_overdue():
    # AC: overdue items are triaged per item too (not auto-migrated), shown
    # with an overdue note and their original date.
    a2 = _a2_section()
    assert "overdue" in a2
    assert "frame the question as overdue" in a2
    assert "these the same way" in a2


def test_a2_empty_scan_skips_silently():
    # AC: no items / nothing overdue -> A2 is silently skipped, no prompt.
    a2 = _a2_section()
    assert "if both scans return nothing" in a2
    assert "skip it silently" in a2


def test_a2_batches_dispositions_per_note():
    # AC: decisions are batched — one call to the Future Log, the `surface`
    # op's cross-note effect is the single write to today.
    a2 = _a2_section()
    assert "one future log call" in a2
    assert 'single `bujo_apply_decisions(note: "future_log"' in a2


def test_a2_mixed_dispositions_batch_into_one_call():
    # AC (mixed dispositions): the worked example batches surface + drop +
    # update + complete into a single Future Log apply_decisions call.
    a2 = _a2_section()
    for op in ('op: "surface"', 'op: "drop"', 'op: "update"', 'op: "complete"'):
        assert op in a2, f"A2 batched example is missing {op}"


# ---------------------------------------------------------------------------
# Issue #28 — scheduled/unattended runs strip AskUserQuestion entirely.
#
# Cowork's scheduled-task runner removes the tool from the toolset for
# non-interactive executions, so invoking it throws "No such tool available:
# AskUserQuestion. AskUserQuestion exists but is not enabled in this context"
# instead of leaving a pending prompt. The fix teaches both prompt files an
# availability check plus a plain-text fallback pause that reaches the same
# paused-on-a-question end-state. Same convention as the tests above: an
# LLM-driven ritual can't run in CI, so these assert the prompt-file
# invariants that drive the behavior — the automatable proxy for the issue's
# manual-verification AC.
# ---------------------------------------------------------------------------

STRIPPED_ERROR = "no such tool available"
STRIPPED_ERROR_DETAIL = "not enabled in this context"


def _protocol_stripped_section() -> str:
    """The protocol's 'If AskUserQuestion is stripped' section (lowercased).

    Sliced from its heading to the next heading so an assertion can't
    accidentally pass on a phrase that lives elsewhere in the protocol.
    """
    text = PROTOCOL.read_text()
    start = text.index("If `AskUserQuestion` is stripped — the plain-text fallback pause")
    end = text.index("Lead with the question — never narrate", start)
    return text[start:end].lower()


def _entrypoint_rule_b_section() -> str:
    """Step 2 Rule B of the entrypoint (lowercased), sliced to Rule C."""
    text = ENTRYPOINT.read_text()
    start = text.index("### Rule B")
    end = text.index("### Rule C", start)
    return text[start:end].lower()


def test_protocol_documents_stripped_tool_error():
    # The exact failure a scheduled run hits must be named, so the agent can
    # recognize it instead of dying on it.
    section = _protocol_stripped_section()
    assert STRIPPED_ERROR in section
    assert STRIPPED_ERROR_DETAIL in section


def test_protocol_checks_availability_before_calling():
    # Detection is defined up front (ToolSearch results) — not discovered by
    # crashing on the first interactive step.
    section = _protocol_stripped_section()
    assert "check availability" in section
    assert "toolsearch" in section


def test_protocol_fallback_pauses_without_fabricating():
    # The fallback reaches the same end-state as a normal pause-on-question:
    # the pending question as plain text, then end of turn — with all five
    # guarantees AC #3 requires: no further ritual steps, no unhandled error,
    # no auto-completing, no fabricated answer.
    section = _protocol_stripped_section()
    assert "plain-text chat output" in section
    assert "end your turn" in section
    assert "no further ritual steps" in section
    assert "no unhandled error" in section
    assert "no auto-completing" in section
    assert "no fabricated answer" in section


# Every unattended interactive step the doc enumerates (AC #4's four plus the
# beyond-AC Step 4 A2 triage): each region is sliced from its own heading to
# the next section's, so deleting any single per-step fallback callout fails
# here — a whole-doc match would stay green on the surviving siblings.
UNATTENDED_STEP_REGIONS = {
    "Step 2 check-in": ("## Step 2 —", "## Step 2.5"),
    "Step 2.5 habits": ("## Step 2.5", "## Step 3"),
    "Step 3 disposition": ("## Step 3", "## Step 4"),
    "Step 4 A2 triage": ("A2. Triage Future Log", "### Part B"),
    "Step 5 planning": ("## Step 5", "## Step 6"),
}


def test_every_unattended_interactive_step_references_fallback():
    # AC #4: every interactive step that can run unattended references the
    # same fallback — not just the entry point or the canonical section.
    text = PROTOCOL.read_text()
    for name, (start, end) in UNATTENDED_STEP_REGIONS.items():
        i = text.index(start)
        section = text[i : text.index(end, i)].lower()
        assert (
            "if `askuserquestion` is stripped" in section
            and "plain-text fallback" in section
        ), f"{name} no longer references the stripped-tool fallback pause"


def test_protocol_distinguishes_schema_miss_from_stripped_tool():
    # InputValidationError = deferred schema not loaded (the tool IS
    # available; re-run the ToolSearch). It must never be read as the
    # stripped-tool signal, or a normal interactive run wrongly degrades.
    section = _protocol_stripped_section()
    assert "inputvalidationerror" in section
    assert "schema isn't loaded" in section


def test_protocol_hard_rule_matches_stripped_reality():
    # Hard rule 15: "invoke if available, otherwise pause on the plain-text
    # question" — the documented contract matches what happens when the tool
    # is stripped. Scoped to the Hard-rules section: the same phrase also
    # appears in the "Lead with the question" narrative, so a whole-doc match
    # would stay green even if rule 15 itself regressed.
    text = PROTOCOL.read_text()
    hard_rules = text[text.index("## Hard rules (apply to all tiers") :].lower()
    assert "invoke `askuserquestion` if it's available, otherwise" in hard_rules


def test_entrypoint_documents_stripped_tool_error():
    text = ENTRYPOINT.read_text().lower()
    assert STRIPPED_ERROR in text
    assert STRIPPED_ERROR_DETAIL in text


def test_entrypoint_loads_askuserquestion_up_front():
    # Step 1a batch-loads AskUserQuestion like the sibling habit commands, so
    # Rule B's first invocation never fires against an unloaded schema (which
    # would throw InputValidationError, not the stripped-tool error).
    text = ENTRYPOINT.read_text().lower()
    assert "select:askuserquestion" in text


def test_entrypoint_rule_b_distinguishes_error_shapes():
    rule_b = _entrypoint_rule_b_section()
    assert "inputvalidationerror" in rule_b
    assert STRIPPED_ERROR_DETAIL in rule_b


def test_entrypoint_rule_b_references_canonical_fallback():
    # Rule B points at the protocol's canonical fallback section rather than
    # inlining its own copy, so the two can't drift.
    rule_b = _entrypoint_rule_b_section()
    assert "if `askuserquestion` is stripped" in rule_b


def test_entrypoint_unattended_rule_matches_stripped_reality():
    # Hard rule 6 carries the same "if available, otherwise plain-text"
    # contract as the protocol's hard rule 15.
    text = ENTRYPOINT.read_text().lower()
    assert "invoke `askuserquestion` if it's available, otherwise" in text


def test_yearly_rollover_triages_via_askuserquestion():
    # Review follow-up: the yearly Future Log rollover asks per entry via
    # AskUserQuestion (with the stripped-tool fallback), not blockquote prose.
    text = PROTOCOL.read_text()
    start = text.index("### Yearly-only — Future Log rollover")
    end = text.index("## Step 5", start)
    rollover = text[start:end].lower()
    assert "askuserquestion" in rollover
    assert "if `askuserquestion` is stripped" in rollover
