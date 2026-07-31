"""Runtime configuration resolved from environment variables."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# --- Output caps -----------------------------------------------------------
#
# Both read-side verbs return a bounded response by default. The numbers
# below are sized against what these tools actually return on a real
# notebook, and against the ~60 KB blunt truncation workbench-core's
# `PostToolUse` hook applies to any MCP response — a semantic cap is only
# useful if it binds *before* that blind byte cut.
#
# DEFAULT_MAX_READ_CHARS (50,000): the whole-packet budget for `bujo_read`,
# counted as estimated wire characters (see `read._line_cost`). Reference
# points: a full daily note is ~30 lines ≈ 5 KB; a monthly note's habit
# tracker is a single `TableLine` whose Apple Notes HTML runs 30–50 KB for
# a 31-day month (every `<td>` carries a ~150-char style attribute). 50,000
# therefore fits one real tracker table, or ~9 dailies, and still leaves
# headroom under the core hook's cut.
#
# DEFAULT_MAX_SCAN_ITEMS (200): `bujo_scan` items serialize at roughly
# 250 bytes each, so 200 items ≈ 50 KB — the same ceiling read aims at.
# A daily `open` scan returns single digits and a monthly sweep across 31
# dailies returns tens, so 200 leaves several times real-world headroom
# while still capping a pathological `unrecognized` scan over legacy notes.
DEFAULT_MAX_READ_CHARS = 50_000
DEFAULT_MAX_SCAN_ITEMS = 200


@dataclass(frozen=True)
class Config:
    backend: str
    folder: str
    index_title: str
    timezone: str
    server_name: str
    user_rules_path: Path | None
    run_dir: Path
    # Defaulted so callers that build a Config directly (tests, embedders)
    # inherit the shipped caps without restating them.
    max_read_chars: int = DEFAULT_MAX_READ_CHARS
    max_scan_items: int = DEFAULT_MAX_SCAN_ITEMS


def _env_positive_int(name: str, default: int) -> int:
    """Read a positive-int env override, failing closed at startup.

    A malformed or non-positive value is a configuration error, not
    something to paper over with the default: silently falling back would
    leave the operator believing they had raised (or lowered) a cap that
    is in fact untouched. Raising here surfaces it at server start rather
    than mid-ritual.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


def load() -> Config:
    user_rules_raw = os.getenv("BUJO_SCRIBE_USER_RULES_PATH")
    user_rules_path = Path(user_rules_raw).expanduser() if user_rules_raw else None

    run_dir_raw = os.getenv("BUJO_SCRIBE_RUN_DIR")
    if run_dir_raw:
        run_dir = Path(run_dir_raw).expanduser()
    else:
        # Fallback when scribe is launched outside the plugin launcher (tests,
        # ad-hoc dev). Tempdir is per-user so locks still serialize within the
        # session, and it's auto-cleaned when the OS prunes /tmp.
        run_dir = Path(tempfile.gettempdir()) / "bujo-scribe-run"

    return Config(
        backend=os.getenv("BUJO_SCRIBE_BACKEND", "apple_notes"),
        folder=os.getenv("BUJO_SCRIBE_FOLDER", "📓 Journal"),
        index_title=os.getenv("BUJO_SCRIBE_INDEX_TITLE", "📓 Journal Index"),
        timezone=os.getenv("BUJO_SCRIBE_TIMEZONE", "America/Phoenix"),
        server_name=os.getenv("BUJO_SCRIBE_SERVER_NAME", "bujo-scribe"),
        user_rules_path=user_rules_path,
        run_dir=run_dir,
        max_read_chars=_env_positive_int("BUJO_SCRIBE_MAX_READ_CHARS", DEFAULT_MAX_READ_CHARS),
        max_scan_items=_env_positive_int("BUJO_SCRIBE_MAX_SCAN_ITEMS", DEFAULT_MAX_SCAN_ITEMS),
    )
