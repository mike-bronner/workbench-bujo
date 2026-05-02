"""HTML → structured model parser.

Lenient: Apple Notes' HTML varies slightly across edits (tag order,
whitespace), so the parser tolerates variation. Strict only on what's
semantically load-bearing: signifier characters, depth encoding, and the
`<s>` strikethrough marker for dropped tasks.

Signifier resolution: if `rules` is provided, the parser honors custom
characters (e.g. rules.signifiers.base.task = "*") and user-defined
extensions (e.g. `$` for expenses) in addition to the built-ins. Without
rules, it falls back to the module-level built-in char tables — useful
for tests and anywhere a rules object isn't available.
"""

from __future__ import annotations

import html
import re

from bujo_scribe_mcp.parsing.model import (
    BASE_CHAR_TO_KEY,
    PREFIX_CHAR_TO_KEY,
    BlankLine,
    BodyLine,
    BujoLine,
    HeadingLine,
    Line,
    ParsedNote,
    UnrecognizedLine,
)
from bujo_scribe_mcp.rules import Rules

# ---------------------------------------------------------------------------
# Internal NBSP token
# ---------------------------------------------------------------------------
# The parser normalizes Apple Notes' `&nbsp;` entity into a single U+00A0
# character during parsing. All depth / leading-space logic works against
# U+00A0. The renderer translates back to `&nbsp;` on emit.

NBSP = "\u00a0"

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Match each top-level <div>...</div> block. Non-greedy, DOTALL to cross
# newlines inside a div.
_DIV_RE = re.compile(r"<div\b[^>]*>(.*?)</div>", re.IGNORECASE | re.DOTALL)

# --- Title (note title — h1 OR legacy 24px span)
# New native: <b><h1>...</h1></b>
_TITLE_H1_RE = re.compile(
    r"""<b\b[^>]*>\s*<h1\b[^>]*>(.*?)</h1>\s*</b>""",
    re.IGNORECASE | re.DOTALL,
)
# Legacy (pre-0.10): <b><span style="font-size: 24px">...</span></b>
_TITLE_SPAN_RE = re.compile(
    r"""<b\b[^>]*>\s*<span\b[^>]*font-size:\s*24px[^>]*>(.*?)</span>\s*</b>""",
    re.IGNORECASE | re.DOTALL,
)

# --- Heading and Subheading (h2/h3 OR legacy 18px/16px spans)
# New native: <b><h2>...</h2></b> or <b><h3>...</h3></b>
_HEADING_HN_RE = re.compile(
    r"""<b\b[^>]*>\s*<h([23])\b[^>]*>(.*?)</h\1>\s*</b>""",
    re.IGNORECASE | re.DOTALL,
)
# Legacy: <b><span style="font-size: 18px|16px">...</span></b>
_HEADING_SPAN_RE = re.compile(
    r"""<b\b[^>]*>\s*<span\b[^>]*font-size:\s*(\d+)px[^>]*>(.*?)</span>\s*</b>""",
    re.IGNORECASE | re.DOTALL,
)
# Map legacy px → HeadingLine.level (matches h-tag numbers).
_HEADING_LEGACY_SIZES: dict[int, int] = {18: 2, 16: 3}

# Match a bare <br> (possibly self-closing) with optional whitespace.
_BARE_BR_RE = re.compile(r"^\s*<br\s*/?>\s*$", re.IGNORECASE)

# The BuJo monospace wrapper. Apple Notes' native Monospaced paragraph
# style is just `<div><tt>...</tt></div>` — no <font> wrapper. Older
# versions of the scribe (and older Apple Notes builds) wrapped <tt> in
# <font face="Menlo-Regular"> or `Courier`. The font wrapper is now
# OPTIONAL — both formats parse to the same BujoLine.
_MONOSPACE_INNER_RE = re.compile(
    r"""(?:<font\b[^>]*face=["']?(?:Menlo[^"'>]*|Courier[^"'>]*)["']?[^>]*>)?\s*<tt\b[^>]*>(.*?)</tt>\s*(?:</font>)?""",
    re.IGNORECASE | re.DOTALL,
)

# The <s>...</s> wrapper for dropped tasks.
_STRIKETHROUGH_RE = re.compile(r"<s\b[^>]*>(.*?)</s>", re.IGNORECASE | re.DOTALL)

# Detect tables/objects — these stay as UnrecognizedLine for raw_html
# preservation (and for the new update_unrecognized op).
_TABLE_RE = re.compile(r"<(?:table|object)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_note(body_html: str, rules: Rules | None = None) -> ParsedNote:
    """Parse an Apple Notes note body into a structured ParsedNote.

    When `rules` is supplied, the parser respects user-overridden signifier
    characters and user-defined extensions. Without rules, uses built-in
    character tables.
    """
    base_map, prefix_map = _resolve_signifier_maps(rules)

    divs = _extract_divs(body_html)

    title = ""
    title_html = ""
    start_idx = 0
    if divs:
        head_inner, head_raw = divs[0]
        extracted = _match_title(head_inner)
        if extracted is not None:
            title = extracted
            title_html = head_raw
            start_idx = 1

            # Apple Notes quirk tolerance: when both `name:` and `body:` are
            # set on create, Apple Notes can inject duplicate-title divs
            # (plain or re-wrapped) into the body. Without tolerance, each
            # round-trip compounds them. Loop over and discard ANY subsequent
            # div whose text content equals the title — plain or bold.
            while start_idx < len(divs):
                next_inner, _ = divs[start_idx]
                next_text = _decode_and_strip_tags(next_inner).strip(" \t\r\n")
                if next_text == title:
                    start_idx += 1
                else:
                    break

    max_depth = rules.alignment.sub_item_max_depth if rules is not None else 2

    lines: list[Line] = []
    for inner, raw in divs[start_idx:]:
        lines.append(
            _parse_div(
                inner,
                raw,
                base_map=base_map,
                prefix_map=prefix_map,
                max_depth=max_depth,
            )
        )

    return ParsedNote(title=title, title_html=title_html, lines=lines)


def _resolve_signifier_maps(rules: Rules | None) -> tuple[dict[str, str], dict[str, str]]:
    """Build char→key maps, optionally honoring user overrides and extensions."""
    if rules is None:
        return dict(BASE_CHAR_TO_KEY), dict(PREFIX_CHAR_TO_KEY)

    base = rules.signifiers.base
    prefix = rules.signifiers.prefix
    base_map: dict[str, str] = {
        base.task: "task",
        base.event: "event",
        base.note: "note",
        base.completed: "completed",
        base.migrated: "migrated",
        base.scheduled: "scheduled",
        base.sub_item: "sub_item",
    }
    # Legacy alias: when `completed` resolves to ASCII `x` (the canonical),
    # also accept U+00D7 `×` so notes from before 0.7.0 still parse cleanly.
    if base.completed == "x" and "×" not in base_map:
        base_map["×"] = "completed"

    # User extensions append. Schema-level validation already prevents
    # collisions with built-ins, so we can overlay safely.
    for ext in rules.signifiers.extensions:
        base_map[ext.char] = ext.key

    prefix_map: dict[str, str] = {
        prefix.priority: "priority",
        prefix.inspiration: "inspiration",
        prefix.explore: "explore",
    }
    for ext in rules.signifiers.prefix_extensions:
        prefix_map[ext.char] = ext.key
    return base_map, prefix_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DIV_OPEN_RE = re.compile(r"<div\b[^>]*>", re.IGNORECASE)
_DIV_CLOSE_RE = re.compile(r"</div\s*>", re.IGNORECASE)
_OBJECT_OPEN_RE = re.compile(r"<object\b[^>]*>", re.IGNORECASE)
_OBJECT_CLOSE_RE = re.compile(r"</object\s*>", re.IGNORECASE)


def _extract_divs(body_html: str) -> list[tuple[str, str]]:
    """Return (inner_html, full_div_html) for every top-level <div>.

    Tag-aware extraction: properly tracks `<div>` nesting and treats
    `<object>...</object>` blocks as opaque (so nested `</div>` inside
    table cells don't prematurely close the outer div). Real Apple Notes
    tables embed `<div>` inside each `<td>`; without this awareness, the
    naive `<div\b[^>]*>(.*?)</div>` regex would split the table across
    many fragments.
    """
    results: list[tuple[str, str]] = []
    pos = 0
    n = len(body_html)
    while pos < n:
        m = _DIV_OPEN_RE.search(body_html, pos)
        if m is None:
            break
        div_start = m.start()
        content_start = m.end()
        scan = content_start
        depth = 1
        end_pos: int | None = None
        while scan < n:
            obj = _OBJECT_OPEN_RE.match(body_html, scan)
            if obj is not None:
                # Skip the entire <object>...</object> block as opaque.
                obj_close = _OBJECT_CLOSE_RE.search(body_html, obj.end())
                if obj_close is None:
                    # Malformed — bail out of the div hunt entirely.
                    scan = n
                    break
                scan = obj_close.end()
                continue

            div_open = _DIV_OPEN_RE.match(body_html, scan)
            if div_open is not None:
                depth += 1
                scan = div_open.end()
                continue

            div_close = _DIV_CLOSE_RE.match(body_html, scan)
            if div_close is not None:
                depth -= 1
                if depth == 0:
                    end_pos = div_close.start()
                    after_close = div_close.end()
                    break
                scan = div_close.end()
                continue

            # Otherwise advance one character.
            scan += 1

        if end_pos is None:
            # Couldn't close this div — give up to avoid infinite loops.
            break

        inner = body_html[content_start:end_pos]
        full = body_html[div_start:after_close]
        results.append((inner, full))
        pos = after_close
    return results


def _match_title(inner_html: str) -> str | None:
    # Try new native h1 form first, then legacy 24px-span form.
    m = _TITLE_H1_RE.search(inner_html) or _TITLE_SPAN_RE.search(inner_html)
    if not m:
        return None
    # Titles don't carry BuJo whitespace semantics — safe to trim both sides.
    return _decode_and_strip_tags(m.group(1)).strip(" \t\r\n")


def _match_heading(inner_html: str) -> tuple[int, str] | None:
    """Detect Apple Notes Heading (h2/legacy 18px) or Subheading (h3/legacy 16px).

    Returns (level, text) or None. `level` matches the HTML h-tag number
    directly: 2 for Heading, 3 for Subheading. Legacy 18px → 2, 16px → 3.
    """
    # New native: h2 / h3
    m = _HEADING_HN_RE.search(inner_html)
    if m is not None:
        level = int(m.group(1))
        text = _decode_and_strip_tags(m.group(2)).strip(" \t\r\n")
        return (level, text)

    # Legacy: bold + font-size span. Only sizes we map to heading levels
    # qualify (18px → 2, 16px → 3); other sizes (24px = title; arbitrary
    # = body styling) fall through.
    m = _HEADING_SPAN_RE.search(inner_html)
    if m is not None:
        try:
            px = int(m.group(1))
        except ValueError:
            return None
        level = _HEADING_LEGACY_SIZES.get(px)
        if level is None:
            return None
        text = _decode_and_strip_tags(m.group(2)).strip(" \t\r\n")
        return (level, text)

    return None


def _parse_div(
    inner_html: str,
    raw_html: str,
    *,
    base_map: dict[str, str],
    prefix_map: dict[str, str],
    max_depth: int = 2,
) -> Line:
    # Blank line — a div containing only <br> (or whitespace-only).
    if _BARE_BR_RE.match(inner_html) or inner_html.strip() == "":
        return BlankLine(raw_html=raw_html)

    # Heading / Subheading — h2/h3 or legacy 18px/16px font-size span.
    heading = _match_heading(inner_html)
    if heading is not None:
        level, text = heading
        return HeadingLine(text=text, level=level, raw_html=raw_html)

    # Tables and other <object>-wrapped structures stay as UnrecognizedLine
    # so the raw_html survives round-trip and the new update_unrecognized
    # op can mutate them. We check this BEFORE the body-line catch-all.
    if _TABLE_RE.search(inner_html):
        return UnrecognizedLine(raw_html=raw_html)

    # Unwrap the monospace wrapper if present (font-wrap optional ≥0.10).
    mono = _MONOSPACE_INNER_RE.search(inner_html)
    if mono is not None:
        content = mono.group(1)

        # Detect strikethrough (dropped state).
        dropped = False
        strike = _STRIKETHROUGH_RE.search(content)
        if strike is not None:
            dropped = True
            content = strike.group(1)

        # Decode entities and strip residual tags — but preserve ALL whitespace,
        # because leading whitespace is semantically load-bearing (depth encoding).
        # Only trim trailing whitespace so CRLFs from osascript output don't leak.
        text_line = _decode_and_strip_tags(content).rstrip(" \t\r\n")

        parsed = _parse_bujo_line(
            text_line, base_map=base_map, prefix_map=prefix_map, max_depth=max_depth
        )
        if parsed is not None:
            base_key, prefix_key, depth, text = parsed
            return BujoLine(
                signifier=base_key,
                prefix=prefix_key,
                depth=depth,
                text=text,
                dropped=dropped,
                anchor=_make_anchor(text),
                raw_html=raw_html,
            )
        # Mono div whose content doesn't match a BuJo signifier — falls
        # through to BodyLine since it's still "user-written paragraph
        # content," just not a BuJo line. Examples: monospace calendar
        # entries like `<tt>1 We</tt>` that the user types into a
        # Monospaced paragraph but aren't bullets.

    # Body line — any non-blank, non-heading, non-table div that the
    # parser didn't claim as a BujoLine. Preserve raw_html for round-trip
    # since body content can carry arbitrary inline styling (italic, bold,
    # mixed, embedded fonts/emoji).
    body_text = _decode_and_strip_tags(inner_html).strip(" \t\r\n")
    # If the de-tagged text is empty (e.g., `<div><i><br></i></div>`),
    # treat as blank — a body line with no text content is functionally
    # a spacer.
    if not body_text:
        return BlankLine(raw_html=raw_html)
    return BodyLine(text=body_text, raw_html=raw_html)


def _decode_and_strip_tags(s: str) -> str:
    """Decode HTML entities and strip any remaining inline tags.

    **Does NOT strip whitespace.** Callers are responsible for whitespace
    handling because leading whitespace encodes sub-item depth — we can't
    throw it away at this layer.
    """
    decoded = html.unescape(s)
    return re.sub(r"<[^>]+>", "", decoded)


def _parse_bujo_line(
    text: str,
    *,
    base_map: dict[str, str],
    prefix_map: dict[str, str],
    max_depth: int = 2,
) -> tuple[str, str | None, int, str] | None:
    """Parse one BuJo-line's plain text. Returns (base_key, prefix_key, depth, body_text).

    Returns None if the line doesn't start with a recognized signifier.

    **Self-heal contract:** Apple Notes sometimes normalizes `&nbsp;` to a
    plain ASCII space on round-trip. The parser counts ALL leading
    whitespace (NBSP or ASCII space) as a single "indent bucket" and
    derives depth from that bucket. Combined with the renderer always
    emitting `&nbsp;`, this means a damaged line is quietly healed on the
    next write — even if Apple Notes ate the NBSPs between read and write.
    """
    if not text:
        return None

    # Count ALL leading whitespace — NBSP or ASCII space — as the indent bucket.
    leading_count = 0
    i = 0
    while i < len(text) and text[i] in (NBSP, " "):
        leading_count += 1
        i += 1

    remainder = text[i:]
    if not remainder:
        return None

    # Detect prefix (single character).
    prefix_key: str | None = None
    if remainder[0] in prefix_map:
        prefix_key = prefix_map[remainder[0]]
        remainder = remainder[1:]
        if not remainder:
            return None

    # Detect base signifier.
    first = remainder[0]
    if first not in base_map:
        return None
    base_key = base_map[first]
    remainder = remainder[1:]

    # Skip a single separating space between signifier and text (ASCII or NBSP).
    if remainder and remainder[0] in (" ", NBSP):
        remainder = remainder[1:]

    # Preserve NBSPs inside the text body; only trim ASCII whitespace at edges.
    body_text = remainder.strip(" \t\r\n")

    # Depth derivation:
    # - sub_item: canonical leading is 1 (alignment NBSP) + 2*depth.
    #   Inverted: depth = (leading_count - 1) / 2. Always at least 1 (nested
    #   under a top-level item). Self-heals when Apple Notes ate NBSPs —
    #   any count ≤ 2 still reads as depth 1.
    # - other signifiers: 2 NBSPs per depth level on top of the standard
    #   single alignment NBSP. So leading_count of 0/1 = depth 0, 2/3 = depth
    #   1, 4/5 = depth 2, etc. This lets cascade-migrated sub-trees survive
    #   round-trips with their parent without collapsing flat.
    if base_key == "sub_item":
        depth_val = max(1, (leading_count - 1) // 2)
    elif leading_count >= 2:
        depth_val = leading_count // 2
    else:
        depth_val = 0

    if depth_val > max_depth:
        depth_val = max_depth

    return (base_key, prefix_key, depth_val, body_text)


def _make_anchor(text: str) -> str:
    """Stable anchor for apply-decisions round-trip.

    Uses the first 60 normalized chars of the line text. Apply-decisions
    matches by substring; ambiguity is surfaced as AMBIGUOUS_BULLET.
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[:60]
