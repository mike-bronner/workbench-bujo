"""Tests for ``session-warmup.md`` — the plugin's static warmup contribution.

The BuJo routing block used to be emitted live by ``hooks/session-warmup.sh``
on every session start. It now lives in ``session-warmup.md`` at the plugin
root, where workbench-core's SessionStart hook
(``collect_session_warmup_contributions()``) concatenates it with every other
installed ``workbench-*`` plugin's contribution into a single block baked into
``~/.claude/CLAUDE.md``.

Why it matters: Anthropic prompt caching matches on an exact request prefix.
Each plugin firing its own hook adds another distinct ``additionalContext``
block, and one byte of drift in any of them invalidates the cache for
everything after it. One shared, byte-stable block fixes that for every
plugin. The contract is documented in workbench-core's
``docs/session-warmup-contributions.md``; these tests pin the parts of it this
plugin can break on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

# scribe/tests/ -> scribe/ -> repo root
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CONTRIBUTION = PLUGIN_ROOT / "session-warmup.md"

# Context-payload budget. The aggregated block is re-sent on every session and
# every PostCompact, for the life of the install. This ceiling catches payload
# creep before it lands back in per-turn latency (the routing block emitted
# ~8.8KB before the 2026-06 trim, ~5.6KB before the hook diet dropped the
# proactive-capture tiers). workbench-core's contribution guide suggests 2KB;
# this block is ~3.3KB and was moved verbatim, so the repo's own established
# 4KB ceiling stands until the content is deliberately trimmed.
WARMUP_BYTE_BUDGET = 4096


def _text() -> str:
    return CONTRIBUTION.read_text(encoding="utf-8")


def test_contribution_file_exists_at_plugin_root():
    # Core discovers it by exact name at the plugin root; anywhere else and it
    # is silently skipped, with no error path to notice.
    assert CONTRIBUTION.is_file()
    assert CONTRIBUTION.parent == PLUGIN_ROOT
    assert (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").is_file()


def test_routing_content_moved_verbatim():
    # The migration was structural, not a rewrite. Every section heading and
    # every trigger-vocabulary row that the hook used to emit must still be
    # here, wording intact.
    text = _text()
    for section in (
        "📓 BuJo routing",
        "Trigger vocabulary → scribe action",
        "Habit tracker (≥0.10) — surface what's due today",
        "Rules of the road",
        "Not in scope for routing",
    ):
        assert section in text

    for row in (
        '`bujo_apply_decisions` with `op: "add"` onto `today`, signifier `task`',
        "don't bounce through today",
        "Signifier `event`.",
        '`op: "add"` with signifier `note` onto `today`',
        '`bujo_read(notes: ["today"])` first, answer from fresh state',
        "**auto-capture** as `× X` on today",
        '`op: "drop"` on the matching bullet',
        '`op: "undrop"` on the matching bullet',
        'NEVER interpret "combine" as "drop"',
    ):
        assert row in text

    for rule in (
        "**Always pre-warm the scribe.**",
        "**Single items don't need the `/bujo` ritual.**",
        "never invent a task list in local memory",
        "Code-level TODOs and comments in source files — those stay in code.",
        "the `TodoWrite` tool",
    ):
        assert rule in text


def test_ritual_pointer_resolves_to_a_real_file():
    # The pointer used to be `${CLAUDE_PLUGIN_ROOT}/skills/rituals/...`,
    # interpolated by the hook at run time. A static file gets no
    # interpolation, so the path is plugin-root-relative — and must actually
    # exist, or the habit check-in silently points at nothing.
    text = _text()
    assert "Step 2.5 (Habit check-in)" in text
    assert "`workbench-bujo` plugin's `skills/rituals/bujo-ritual.md`" in text
    assert (PLUGIN_ROOT / "skills" / "rituals" / "bujo-ritual.md").is_file()


def test_no_unexpanded_shell_interpolation():
    # A `${...}` left behind would render literally in ~/.claude/CLAUDE.md.
    # Nothing expands variables in this file.
    assert "${" not in _text()


def test_starts_at_heading_level_two_with_no_frontmatter():
    # Core's aggregator owns level 1; contributions start at `##`. Frontmatter
    # is not stripped — it would render as raw text in CLAUDE.md.
    text = _text()
    assert not text.startswith("---")
    assert text.startswith("## ")
    # No stray level-1 heading anywhere in the body either.
    assert not re.search(r"^# ", text, flags=re.MULTILINE)


def test_ends_with_exactly_one_trailing_newline():
    # The collector inserts the blank line between contributions; a trailing
    # blank line here would double it and shift every later plugin's bytes.
    text = _text()
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_contains_no_volatile_content():
    # Byte-stability is the entire reason this file exists. Nothing derived
    # from live state may appear — the version-drift banner in particular
    # stays in the hook, where it belongs.
    text = _text()
    for volatile in ("version drift", "v0.", "available in your CLI plugin cache"):
        assert volatile not in text
    # No date- or time-stamped text.
    assert not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text.replace("[YYYY-MM-DD]", ""))


def test_contribution_under_budget():
    assert len(_text().encode("utf-8")) < WARMUP_BYTE_BUDGET


def test_no_stale_proactive_capture_references():
    # The proactive-capture machinery (tiers, threshold dial, per-turn
    # capture-watch nudge) was removed in the 2026-06 hook diet. None of its
    # vocabulary may resurface in the contributed block.
    text = _text()
    for stale in ("Proactive capture", "capture-watch", "Threshold dial"):
        assert stale not in text
