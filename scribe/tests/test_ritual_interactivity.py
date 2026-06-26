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
    assert "never** migrated automatically" in a2


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
    # AC: only "Carry forward" lands on today (via migrate's cross-note
    # effect); the other three mutate the Future Log only.
    a2 = _a2_section()
    assert "migrate" in a2 and 'target `today`' in a2
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
    # AC: decisions are batched — one call to the Future Log, the migrate's
    # cross-note effect is the single write to today.
    a2 = _a2_section()
    assert "one future log call" in a2
    assert 'single `bujo_apply_decisions(note: "future_log"' in a2


def test_a2_mixed_dispositions_batch_into_one_call():
    # AC (mixed dispositions): the worked example batches migrate + drop +
    # update + complete into a single Future Log apply_decisions call.
    a2 = _a2_section()
    for op in ('op: "migrate"', 'op: "drop"', 'op: "update"', 'op: "complete"'):
        assert op in a2, f"A2 batched example is missing {op}"
