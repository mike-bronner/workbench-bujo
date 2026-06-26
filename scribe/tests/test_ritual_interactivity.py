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
