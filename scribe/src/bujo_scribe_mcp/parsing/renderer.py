"""Structured model → HTML renderer.

Strict: follows `rules.yaml` exactly. User-configured signifier characters,
NBSP encoding, monospace wrapper, and title wrapper are honored on every
emit — so if a user customizes any of those, the renderer produces the
right thing automatically.

**Self-heal contract (Apple Notes backend):** the renderer builds HTML
purely from the semantic model. Any incidental whitespace damage Apple
Notes introduced between read and re-read is discarded — the next write
emits clean `&nbsp;` entities in the exact positions the rules prescribe.
The renderer never round-trips raw bytes of a BujoLine; it always
regenerates from (signifier, prefix, depth, text, dropped).
"""

from __future__ import annotations

import html

from bujo_scribe_mcp.parsing.model import (
    BlankLine,
    BujoLine,
    Line,
    ParsedNote,
    UnrecognizedLine,
)
from bujo_scribe_mcp.rules import Rules


def render_note(note: ParsedNote, rules: Rules) -> str:
    """Render a ParsedNote back to Apple Notes HTML string."""
    parts: list[str] = []
    parts.append(_render_title(note.title, rules))
    for line in note.lines:
        parts.append(_render_line(line, rules))
    return "".join(parts)


def render_line(line: Line, rules: Rules) -> str:
    """Render a single line to its HTML form."""
    return _render_line(line, rules)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _render_title(title: str, rules: Rules) -> str:
    cfg = rules.backends.apple_notes.html
    return f"{cfg.title_open}{html.escape(title)}{cfg.title_close}"


def _render_line(line: Line, rules: Rules) -> str:
    if isinstance(line, BlankLine):
        return rules.backends.apple_notes.html.blank_line
    if isinstance(line, UnrecognizedLine):
        return line.raw_html
    if isinstance(line, BujoLine):
        return _render_bujo(line, rules)
    raise TypeError(f"Unknown line type: {type(line).__name__}")


def _render_bujo(line: BujoLine, rules: Rules) -> str:
    cfg = rules.backends.apple_notes.html
    nbsp = cfg.nbsp_encoding
    sig = rules.signifiers
    body = rules.backends.apple_notes.html.monospace_wrapper

    # Build leading indent.
    # EVERY non-prefixed base signifier (including sub_item's `-`) gets one
    # leading alignment NBSP so all signifier characters line up. Sub-items
    # stack an additional 2 NBSPs per depth level on top of that.
    # Other signifiers also indent 2 NBSPs per depth level when nested under
    # a parent — keeps cascade-migrated sub-trees visually aligned.
    # Prefixed items skip the leading alignment NBSP (their prefix provides it).
    if line.signifier == "sub_item":
        indent = nbsp * (1 + 2 * line.depth)
    elif line.depth > 0:
        indent = nbsp * (2 * line.depth)
    elif line.prefix is None:
        indent = nbsp
    else:
        indent = ""

    # Resolve signifier characters from rules (user overrides win).
    sig_char_map = {
        "task": sig.base.task,
        "event": sig.base.event,
        "note": sig.base.note,
        "completed": sig.base.completed,
        "migrated": sig.base.migrated,
        "scheduled": sig.base.scheduled,
        "sub_item": sig.base.sub_item,
    }
    # Overlay user extensions (schema validator prevents key/char collisions).
    for ext in sig.extensions:
        sig_char_map[ext.key] = ext.char

    prefix_char_map = {
        "priority": sig.prefix.priority,
        "inspiration": sig.prefix.inspiration,
        "explore": sig.prefix.explore,
    }
    for ext in sig.prefix_extensions:
        prefix_char_map[ext.key] = ext.char

    if line.prefix is not None and line.prefix not in prefix_char_map:
        raise ValueError(
            f"Unknown prefix key {line.prefix!r}. "
            "Built-in keys (priority/inspiration/explore) or a "
            "user-defined extension in rules.signifiers.prefix_extensions required."
        )
    prefix_char = prefix_char_map[line.prefix] if line.prefix else ""
    if line.signifier not in sig_char_map:
        raise ValueError(
            f"Unknown signifier key {line.signifier!r}. "
            "Built-in keys or a user-defined extension in rules.signifiers.extensions required."
        )
    base_char = sig_char_map[line.signifier]

    # Separating space between signifier and text. ASCII space is fine here —
    # Apple Notes only strips LEADING ASCII spaces; mid-line ones are preserved.
    sep = " "

    escaped_text = html.escape(line.text)
    inner = f"{indent}{prefix_char}{base_char}{sep}{escaped_text}"

    if line.dropped:
        inner = f"{cfg.strikethrough_open}{inner}{cfg.strikethrough_close}"

    return body.replace("{content}", inner)
