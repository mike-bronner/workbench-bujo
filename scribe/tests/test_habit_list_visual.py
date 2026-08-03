"""Guards the rendered habit dashboard in ``commands/bujo-habit-list.md``.

``/bujo-habit-list`` used to end at an ASCII table in chat. It now builds a
self-contained HTML habit dashboard — completion-rate bar, streak badge, and a
per-day month strip for every habit — and renders it through the interactive
session's ``visualize`` capability, keeping the text table only as the fallback
for sessions where that capability is absent.

An LLM-driven command can't be exercised deterministically in CI, so — exactly
as ``test_ritual_interactivity.py`` and ``test_ritual_daily_opener.py`` do —
these tests assert the *prompt-file invariants that drive the behavior*: the
renderer contract is read before anything is rendered, the template that makes
successive runs comparable still carries its structural parts, every
placeholder it uses is documented, the no-renderer path still degrades to the
text table, and the command stays read-only and non-fabricating.

Every assertion is scoped to the section (or the fenced block) it claims to
pin — never a whole-file substring search, which a passing mention elsewhere in
the prose would satisfy — and section extraction drops the heading line, so a
heading restating its own topic can't satisfy a check meant for the body.
"""

from __future__ import annotations

import re
from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root
REPO = Path(__file__).resolve().parents[2]
COMMAND = REPO / "commands" / "bujo-habit-list.md"

RENDER_STEP = "## Step 4 — Render the habit dashboard"
FALLBACK_STEP = "## Step 5 — Text fallback (no renderer)"
CADENCE_STEP = "## Step 3 — Compute cadence stats"
PARSE_STEP = "## Step 2 — Parse the table"
HARD_RULES = "## Hard rules"

CONTRACT_TOOL = "mcp__visualize__read_me"
RENDER_TOOL = "mcp__visualize__show_widget"


def _text() -> str:
    return COMMAND.read_text()


def _section(heading: str) -> str:
    """Body of a top-level ``## `` section — heading line excluded.

    Dropping the heading matters: a heading that restates the section's own
    topic ("Text fallback (no renderer)") would otherwise satisfy a check meant
    to pin what the body actually instructs.
    """
    text = _text()
    start = text.find(heading)
    assert start != -1, f"{COMMAND.name} has no `{heading}` section."
    body_start = start + len(heading)
    end = text.find("\n## ", body_start)
    return text[body_start : end if end != -1 else len(text)]


def _template() -> str:
    """The fenced ``html`` block holding the dashboard document template."""
    blocks = re.findall(r"```html\n(.*?)```", _section(RENDER_STEP), re.DOTALL)
    docs = [b for b in blocks if "<!DOCTYPE html>" in b]
    assert len(docs) == 1, (
        "Step 4 must carry exactly one full HTML document template; "
        f"found {len(docs)}."
    )
    return docs[0]


def _call_blocks(section: str) -> list[str]:
    """Fenced blocks in a section that hold tool calls, not the HTML template.

    The tool names also appear in Step 4's *prose* (the availability gate), so
    an ordering check run over the whole section would pass even with both
    calls deleted. Only the fenced call sites count.
    """
    blocks: list[str] = []
    info: str | None = None
    body: list[str] = []
    for line in section.splitlines():
        if line.startswith("```"):
            if info is None:
                info = line[3:].strip()
                body = []
            else:
                if info != "html":
                    blocks.append("\n".join(body))
                info = None
        elif info is not None:
            body.append(line)
    assert info is None, "Unbalanced code fence in the section."
    return blocks


def _substitution_table() -> str:
    """The markdown table rows documenting the template's placeholders."""
    rows = [
        line
        for line in _section(RENDER_STEP).splitlines()
        if line.startswith("|") and line.endswith("|")
    ]
    assert rows, "Step 4 must document the template placeholders in a table."
    return "\n".join(rows)


def test_renderer_contract_is_read_before_anything_is_rendered() -> None:
    """``read_me`` first, ``show_widget`` after — never the reverse."""
    blocks = _call_blocks(_section(RENDER_STEP))
    contract_at = next(
        (i for i, b in enumerate(blocks) if CONTRACT_TOOL in b), None
    )
    render_at = next((i for i, b in enumerate(blocks) if RENDER_TOOL in b), None)
    assert contract_at is not None, (
        f"Step 4 must actually call `{CONTRACT_TOOL}` — the payload contract "
        "is read at run time, not assumed. Naming it in prose isn't a call."
    )
    assert render_at is not None, (
        f"Step 4 must actually call `{RENDER_TOOL}` to render."
    )
    assert contract_at < render_at, (
        f"`{CONTRACT_TOOL}` must be instructed before `{RENDER_TOOL}`; the "
        "contract governs how the payload is packaged."
    )


def test_rendering_is_gated_on_the_capability_being_present() -> None:
    """Absent renderer → fall through to the text table, don't fake a visual."""
    gate = _section(RENDER_STEP).split("###", 1)[0]
    assert CONTRACT_TOOL in gate and RENDER_TOOL in gate, (
        "Step 4 must open by naming both visualize tools as the precondition "
        "for rendering."
    )
    assert "Step 5" in gate, (
        "Step 4's gate must route a missing renderer to Step 5's text table "
        "instead of leaving the command with no output path."
    )
    assert "fabricate" in gate.lower(), (
        "Step 4's gate must forbid describing a visual that was never "
        "rendered."
    )


def test_template_themes_light_and_dark_via_custom_properties() -> None:
    """Same light/dark CSS-variable approach as docs/ritual-flow.html."""
    template = _template()
    assert ":root {" in template, "Template must define its palette on :root."
    dark = re.search(
        r"@media \(prefers-color-scheme: dark\) \{(.*?)\n  \}\n",
        template,
        re.DOTALL,
    )
    assert dark, "Template must carry a prefers-color-scheme: dark override."
    for token in ("--bg:", "--panel:", "--text:", "--border:"):
        assert token in dark.group(1), (
            f"The dark override must redefine {token} — a partial override "
            "leaves light-mode values bleeding into dark."
        )


def test_template_carries_every_required_habit_visual() -> None:
    """Bar, streak badge, day strip, and the per-habit repeat block."""
    template = _template()
    for anchor, why in (
        ('class="bar"', "completion-rate bar"),
        ('class="fill ', "rate-tier fill on the bar"),
        ('class="streak ', "streak badge"),
        ('class="strip"', "per-day month strip"),
        ("{DAY_CELLS}", "per-day cells inside the strip"),
        ("repeat per habit", "the per-habit repeat marker"),
        ('class="legend"', "legend decoding the day-strip states"),
    ):
        assert anchor in template, f"Template is missing the {why} ({anchor})."


def test_day_strip_encodes_state_beyond_colour() -> None:
    """Done / missed / not-due / upcoming must differ in shape, not just hue."""
    template = _template()
    for cls in (".d.done", ".d.miss", ".d.off", ".d.fut", ".d.today"):
        assert cls in template, f"Template must style the `{cls}` day state."
    assert "border: 1.5px solid var(--mid)" in template, (
        "The missed state must render as a hollow ring, so the strip stays "
        "readable without colour vision."
    )


def test_every_template_placeholder_is_documented() -> None:
    """No undocumented token — that's what keeps successive runs comparable."""
    table = _substitution_table()
    tokens = set(re.findall(r"\{[A-Z_]+\}", _template()))
    assert tokens, "Template must use {PLACEHOLDER} tokens."
    undocumented = sorted(t for t in tokens if t not in table)
    assert not undocumented, (
        f"Template placeholders missing from the substitution table: "
        f"{undocumented}"
    )


def test_template_is_emitted_verbatim_not_reinvented() -> None:
    """The determinism instruction is the whole point of shipping a template."""
    step = _section(RENDER_STEP)
    assert "verbatim" in step, (
        "Step 4 must instruct emitting the template verbatim; without it the "
        "dashboard is reinvented every run and months stop being comparable."
    )


def test_template_stays_inert() -> None:
    """A report, not an app: no scripts, no network fetches."""
    step = _section(RENDER_STEP)
    assert "<script>" not in _template(), "The template must ship no scripts."
    assert "self-contained" in step and "no `<script>`" in step, (
        "Step 4 must state the inert, self-contained constraint explicitly."
    )


def test_fallback_still_renders_the_text_table() -> None:
    """The no-renderer path keeps the original ASCII summary."""
    blocks = re.findall(r"```\n(.*?)```", _section(FALLBACK_STEP), re.DOTALL)
    assert blocks, "Step 5 must show the text table it falls back to."
    table = blocks[0]
    for column in ("Habit", "Cadence", "Time", "Done", "Streak"):
        assert column in table, (
            f"The fallback table lost its `{column}` column — the text path "
            "must still carry the same facts as the dashboard."
        )


def test_zero_due_days_never_render_as_zero_percent() -> None:
    """A habit that isn't due yet has an undefined rate, not a failed one."""
    step = _section(CADENCE_STEP)
    assert "`due_count` is 0" in step, (
        "Step 3 must handle the zero-due-days case explicitly."
    )
    assert "not due yet" in step, (
        "Step 3 must label the undefined-rate case `not due yet` rather than "
        "showing a 0% Mike didn't earn."
    )
    assert "Never divide by zero" in step, (
        "Step 3 must forbid the division that produces the bogus rate."
    )


def test_unreadable_cells_fail_closed() -> None:
    """An unparseable cell is never silently counted as a completion."""
    step = _section(PARSE_STEP)
    assert "unreadable" in step, (
        "Step 2 must classify cells it cannot parse instead of assuming a "
        "state for them."
    )
    assert "does **not** count as a completion" in step, (
        "Step 2 must state that an unreadable cell is not a completion."
    )
    assert "unreadable_count" in step, (
        "Step 2 must carry an unreadable-cell count forward; without it the "
        "dashboard has nothing to warn from."
    )
    warn_row = [
        row for row in _substitution_table().splitlines() if "{WARN}" in row
    ]
    assert warn_row, "The substitution table must document the {WARN} slot."
    assert "unreadable_count" in warn_row[0], (
        "The {WARN} slot must be wired to Step 2's unreadable_count — a count "
        "nothing renders is a silently swallowed parse failure."
    )


def test_command_stays_read_only_and_honest() -> None:
    """Adding a visual must not add a write path or a fabricated number."""
    rules = _section(HARD_RULES)
    assert "No `apply_decisions` calls" in rules, (
        "The command must stay read-only — the dashboard never writes back."
    )
    assert "Every number in the visual traces to a parsed cell" in rules, (
        "The no-fabrication rule must cover the visual, not just the text "
        "summary — no projected rates or 'on track' verdicts."
    )
    assert "Never claim to have rendered something you didn't" in rules, (
        "The hard rules must forbid narrating a visual that never rendered."
    )
