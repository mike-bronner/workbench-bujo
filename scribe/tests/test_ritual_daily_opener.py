"""Guards the structured daily check-in opener (issue #12).

The daily ritual used to open Step 2 with a single generic question — "How did
yesterday go?" — which is too vague to land a real reflection. Issue #12 replaces
it with a structured opener that anchors on wins first, draws out the day's
lessons, makes space for a brain dump, and prunes still-open tasks during the
check-in rather than deferring that judgment to the Step 3 disposition pass.

An LLM-driven ritual can't be exercised deterministically in CI, so — exactly as
``test_ritual_interactivity.py`` and ``test_session_warmup_drift.py`` do — these
tests assert the *prompt-file invariant that drives the behavior*: the daily
Tier-matrix opener and Step 2's three-angle protocol must carry the structured
opener, not the old generic question.
"""

from __future__ import annotations

import re
from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root
REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "skills" / "rituals" / "bujo-ritual.md"

OLD_GENERIC_OPENER = "how did yesterday go"
NEW_OPENER_CUE = "what went well yesterday"
ESCAPE_HATCHES = ("pass — skip today", "come back to this")


def _daily_matrix_row(text: str) -> str:
    """Return the Tier-matrix table row whose first cell is ``daily``."""
    for line in text.splitlines():
        if line.lstrip().startswith("| daily |"):
            return line.lower()
    raise AssertionError("Tier matrix has no `daily` row to check the opener against.")


def _step2(text: str) -> str:
    """Return the Step 2 (check-in) section, lowercased."""
    low = text.lower()
    start = low.find("## step 2 — check-in")
    assert start != -1, "Step 2 check-in heading is missing."
    end = low.find("## step 2.5", start)
    assert end != -1, "Step 2.5 heading is missing — can't bound Step 2."
    return low[start:end]


def _checkin_opener_blocks(text: str) -> list[str]:
    """Return the ``AskUserQuestion`` code blocks whose header is ``Check-in``.

    These are the tool-invocation blocks that actually surface the opener to
    Mike — the literal surface AC #1/#9 are about. They sit ~170 lines *before*
    Step 2, so they fall outside both ``_daily_matrix_row`` and ``_step2``; the
    other tests never reach them. The fence pattern tolerates indented fences so
    a relocated example block is still caught."""
    blocks = re.findall(r"```jsonc[^\n]*\n(.*?)\n[ \t]*```", text, re.DOTALL)
    checkin = [b for b in blocks if "AskUserQuestion(" in b and 'header: "Check-in"' in b]
    assert checkin, "No AskUserQuestion 'Check-in' opener blocks found to guard."
    return checkin


def test_daily_matrix_opener_is_structured_not_generic():
    """AC #1, #6: the daily Tier-matrix opener cell carries the structured
    wins → lessons → brain dump opener, not the old generic question."""
    row = _daily_matrix_row(PROTOCOL.read_text())
    assert OLD_GENERIC_OPENER not in row, (
        "daily Tier-matrix opener still uses the generic 'How did yesterday go?' "
        "— it must be the structured opener."
    )
    for cue in ("wins", "lessons", "brain dump"):
        assert cue in row, f"daily opener cell is missing the '{cue}' component."


def test_step2_leads_with_wins_then_lessons():
    """AC #2, #3: angle 1 anchors on wins before critique, then draws out lessons."""
    step2 = _step2(PROTOCOL.read_text())
    assert "lead with wins" in step2, "Step 2 must instruct leading with wins."
    assert "positive anchor" in step2, "Step 2 must frame the win as the positive anchor."
    assert "lesson" in step2, "Step 2 must invite the day's lessons/insights."


def test_step2_includes_brain_dump():
    """AC #5, #8: the brain dump is part of the opener sequence and feeds angle 2."""
    step2 = _step2(PROTOCOL.read_text())
    assert "brain dump" in step2, "Step 2 must include the brain dump component."


def test_step2_prunes_open_tasks_during_checkin():
    """AC #4, #8: the necessity/eliminate prune happens in the check-in (angle 3),
    explicitly not deferred to the Step 3 disposition pass."""
    step2 = _step2(PROTOCOL.read_text())
    assert "eliminat" in step2, "Step 2 must ask whether an open task should be eliminated."
    assert "not in step 3" in step2, (
        "Step 2 must state the prune is done in the check-in, not deferred to Step 3."
    )


def test_step2_angles_in_canonical_order():
    """AC #8: the three angles stay aligned in order — wins/lessons (angle 1)
    before the brain dump (angle 2) before the open-task prune (angle 3). The
    presence tests above would all stay green if the angles were reordered, so
    this positional guard protects the alignment the AC explicitly names."""
    step2 = _step2(PROTOCOL.read_text())
    wins = step2.index("lead with wins")
    brain_dump = step2.index("brain dump")
    prune = step2.index("eliminat")
    assert wins < brain_dump < prune, (
        "Step 2 angles are out of order — expected wins/lessons → brain dump → "
        f"prune, got positions wins={wins}, brain dump={brain_dump}, prune={prune}."
    )


def test_escape_hatches_preserved():
    """AC #7: the skip/defer escape hatches survive on each AskUserQuestion
    ``Check-in`` opener block — not merely somewhere in the document. Both labels
    also appear in the prose 'INCORRECT' counter-example (``:53-54``) and in Step 5
    planning (``:640`` onward), so a whole-file check would still pass even if the
    ``options`` arrays were stripped from the opener blocks themselves — exactly
    the AC #7 regression this test exists to catch."""
    for block in _checkin_opener_blocks(PROTOCOL.read_text()):
        low = block.lower()
        for hatch in ESCAPE_HATCHES:
            assert hatch in low, (
                f"A Check-in AskUserQuestion block is missing the '{hatch}' escape hatch."
            )


def test_checkin_askuserquestion_blocks_carry_structured_opener():
    """AC #1, #9: the opener Mike actually sees — the ``AskUserQuestion``
    ``Check-in`` blocks — must carry the structured wins-first question and never
    the old generic one. These blocks live outside the Tier-matrix row and the
    Step 2 narrative, so without this the question on those blocks could be
    reverted to 'How did yesterday go?' with every other test still green."""
    for block in _checkin_opener_blocks(PROTOCOL.read_text()):
        low = block.lower()
        assert NEW_OPENER_CUE in low, (
            "A Check-in AskUserQuestion block is missing the structured opener "
            f"('{NEW_OPENER_CUE}')."
        )
        assert OLD_GENERIC_OPENER not in low, (
            "A Check-in AskUserQuestion block still uses the generic "
            "'How did yesterday go?' opener."
        )


def test_generic_opener_absent_everywhere():
    """AC #1: the old generic question must not survive anywhere in the protocol
    — Tier-matrix row, Step 2 narrative, or the AskUserQuestion opener blocks."""
    assert OLD_GENERIC_OPENER not in PROTOCOL.read_text().lower(), (
        "The old generic 'How did yesterday go?' opener still appears in the "
        "protocol — it must be fully replaced by the structured opener."
    )
