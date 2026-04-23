"""Slug → note-title resolver.

Turns canonical slugs (`today`, `yesterday`, `monthly_current`, etc.) into
explicit Apple Notes titles using `rules.naming` and the configured
timezone. Explicit titles pass through unchanged.

Date handling uses `zoneinfo` to honor `rules.timezone`. A `today` parameter
lets callers inject a fixed date for deterministic testing.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bujo_scribe_mcp.rules import Rules

# ---------------------------------------------------------------------------
# Slug patterns
# ---------------------------------------------------------------------------

_DAILY_SLUG_RE = re.compile(r"^daily:(\d{4}-\d{2}-\d{2})$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ResolverError(Exception):
    """Raised when a slug can't be resolved to a title."""


def resolve(identifier: str, *, rules: Rules, today: date | None = None) -> str:
    """Resolve an identifier slug (or explicit title) to a concrete note title.

    Explicit titles — anything not matching a known slug pattern — pass
    through unchanged. Missing-date slugs raise `ResolverError`.
    """
    ref_date = today if today is not None else _today_in_tz(rules.timezone)

    if identifier == "index":
        return rules.backends.apple_notes.index_note_title
    if identifier == "future_log":
        return rules.future_log.note_title
    if identifier == "goals":
        return "Goals"  # standing note; not yet in rules schema
    if identifier == "second_brain":
        return "🧠 Claude's Second Brain"
    if identifier == "today":
        return _format_daily(ref_date, rules)
    if identifier == "yesterday":
        return _format_daily(ref_date - timedelta(days=1), rules)
    if identifier == "tomorrow":
        return _format_daily(ref_date + timedelta(days=1), rules)
    if identifier == "monthly_current":
        return _format_monthly(ref_date, rules)
    if identifier == "monthly_prev":
        return _format_monthly(_first_of_prev_month(ref_date), rules)
    if identifier == "weekly_current":
        return _format_weekly(_start_of_week_containing(ref_date, rules), rules)
    if identifier == "yearly_current":
        return _format_yearly(ref_date, rules)

    match = _DAILY_SLUG_RE.match(identifier)
    if match:
        d = date.fromisoformat(match.group(1))
        return _format_daily(d, rules)

    # Not a recognized slug — treat as an explicit title.
    return identifier


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _today_in_tz(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except Exception as exc:
        raise ResolverError(f"Invalid timezone: {tz_name!r}") from exc
    return datetime.now(tz).date()


def _format_daily(d: date, rules: Rules) -> str:
    return d.strftime(rules.naming.daily)


def _format_monthly(d: date, rules: Rules) -> str:
    first = d.replace(day=1)
    return first.strftime(rules.naming.monthly)


def _format_yearly(d: date, rules: Rules) -> str:
    return d.strftime(rules.naming.yearly)


def _format_weekly(start_of_week: date, rules: Rules) -> str:
    return start_of_week.strftime(rules.naming.weekly)


def _start_of_week_containing(d: date, rules: Rules) -> date:
    """Return the date that starts the week containing `d`, honoring
    `rules.naming.week_start_day` (`sunday` or `monday`)."""
    # isoweekday(): Monday=1 … Sunday=7
    iso = d.isoweekday()
    if rules.naming.week_start_day == "sunday":
        # Sunday (iso=7) is offset 0 from itself; other days count back from Sunday.
        offset = 0 if iso == 7 else iso
        return d - timedelta(days=offset)
    # monday-start (ISO): Monday (iso=1) is offset 0; others count back.
    return d - timedelta(days=iso - 1)


def _first_of_prev_month(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)
