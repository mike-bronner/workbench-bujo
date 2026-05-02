"""BuJo HTML parser + renderer — translate between Apple Notes HTML and an
internal structured model.

Split into three modules:
- `model`    — plain dataclasses for parsed lines and notes
- `parser`   — HTML → model (lenient: best-effort on malformed input)
- `renderer` — model → HTML (strict: follows rules.yaml exactly)
"""

from __future__ import annotations

from bujo_scribe_mcp.parsing.model import (
    BaseSignifier,
    BlankLine,
    BodyLine,
    BujoLine,
    HeadingLine,
    Line,
    ParsedNote,
    PrefixSignifier,
    UnrecognizedLine,
)
from bujo_scribe_mcp.parsing.parser import parse_note
from bujo_scribe_mcp.parsing.renderer import render_note

__all__ = [
    "BaseSignifier",
    "PrefixSignifier",
    "BujoLine",
    "BlankLine",
    "HeadingLine",
    "BodyLine",
    "UnrecognizedLine",
    "Line",
    "ParsedNote",
    "parse_note",
    "render_note",
]
