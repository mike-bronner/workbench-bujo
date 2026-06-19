"""macOS Reminders integration — habit reminders via AppleScript.

Mirrors the Apple Notes backend pattern (`backends/apple_notes.py`): every
operation builds an AppleScript source block, runs it via `osascript -e`,
and parses stdout. Failures (osascript missing, timeout, non-zero exit)
raise `BackendError`.

Reminders are NOT notes, so this lives outside the `NotebookBackend`
abstraction — but it reuses the same osascript mechanics (string quoting,
subprocess invocation, BackendError on failure). No new third-party
dependencies: stdlib `subprocess` + `osascript`, same as the notes backend.

Scope — habit reminders only:
    A habit added with a specific ``@HH:MM`` time gets a macOS Reminder in a
    dedicated list (`BuJo Habits`), titled with the habit's canonical
    tracker-header text (e.g. ``Meditate (10 min) @08:00 [daily]``). Habits
    with no exact time (Anytime / Morning / Afternoon / Evening) get no
    Reminder — the session-start habit check remains the notification
    mechanism for those.

macOS limitation — recurrence:
    The Reminders AppleScript dictionary exposes no writable recurrence /
    repeat property, so the reminder is created as a timed alert at the
    requested time (``remind me date``). The habit's cadence (e.g.
    ``[daily]``) is carried in the reminder title, not as a system
    recurrence rule.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Literal

from bujo_scribe_mcp.backends.base import BackendError

# The dedicated Reminders list for BuJo habit reminders. Created on demand.
REMINDERS_LIST = "BuJo Habits"

# Exact 24-hour HH:MM, anchored — so partial/junk input ("8", "8:00 am",
# "morning") is rejected and treated as "no specific time" → no reminder.
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_OSASCRIPT_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# AppleScript helpers (mirrors backends/apple_notes.py)
# ---------------------------------------------------------------------------


def _as_quote(value: str) -> str:
    """Quote a Python string for safe interpolation into an AppleScript literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _run_applescript(script: str, *, timeout: float = _OSASCRIPT_TIMEOUT_SECONDS) -> str:
    """Run an AppleScript source block via `osascript -e` and return its stdout.

    Raises BackendError on non-zero exit (including the stderr text), a
    missing `osascript` binary, or timeout.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BackendError(
            "osascript not found — Reminders integration requires macOS."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendError(f"AppleScript timed out after {timeout}s") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or "(no stderr)"
        raise BackendError(f"AppleScript failed (exit {result.returncode}): {stderr}")

    # osascript appends a trailing newline; strip only that one newline.
    return result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

ReminderAction = Literal[
    "created",
    "skipped_no_time",
    "skipped_exists",
    "deleted",
    "not_found",
]


@dataclass(frozen=True)
class ReminderResult:
    """Outcome of an add/remove operation. `action` is the machine-readable
    branch the agent surfaces to Mike; `detail` is the human one-liner."""

    action: ReminderAction
    header: str
    list_name: str
    detail: str


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


def add_reminder(header: str, time: str | None) -> ReminderResult:
    """Create a habit reminder in the `BuJo Habits` list, idempotently.

    - No exact ``HH:MM`` time → no reminder (`skipped_no_time`).
    - `header` already present in the list → no duplicate (`skipped_exists`).
    - Otherwise → create the reminder, auto-creating the list if absent
      (`created`).
    """
    if time is None or not _TIME_RE.match(time):
        return ReminderResult(
            action="skipped_no_time",
            header=header,
            list_name=REMINDERS_LIST,
            detail="No specific @HH:MM time — no reminder created.",
        )

    if reminder_exists(header):
        return ReminderResult(
            action="skipped_exists",
            header=header,
            list_name=REMINDERS_LIST,
            detail="Reminder already exists",
        )

    hour, minute = time.split(":")
    script = f"""
        tell application "Reminders"
            if not (exists list {_as_quote(REMINDERS_LIST)}) then
                make new list with properties {{name:{_as_quote(REMINDERS_LIST)}}}
            end if
            set theList to list {_as_quote(REMINDERS_LIST)}
            set remindDate to (current date)
            set hours of remindDate to {int(hour)}
            set minutes of remindDate to {int(minute)}
            set seconds of remindDate to 0
            make new reminder at end of theList with properties ¬
                {{name:{_as_quote(header)}, remind me date:remindDate}}
            return "ok"
        end tell
    """
    _run_applescript(script)
    return ReminderResult(
        action="created",
        header=header,
        list_name=REMINDERS_LIST,
        detail=f"Reminder created, alerts at {time}.",
    )


def remove_reminder(header: str) -> ReminderResult:
    """Delete the habit reminder matching `header` exactly.

    A non-existent reminder is not an error — returns `not_found`.
    """
    if not reminder_exists(header):
        return ReminderResult(
            action="not_found",
            header=header,
            list_name=REMINDERS_LIST,
            detail="No matching reminder — nothing to delete.",
        )

    script = f"""
        tell application "Reminders"
            if not (exists list {_as_quote(REMINDERS_LIST)}) then
                return "ok"
            end if
            set theList to list {_as_quote(REMINDERS_LIST)}
            delete (every reminder of theList whose name is {_as_quote(header)})
            return "ok"
        end tell
    """
    _run_applescript(script)
    return ReminderResult(
        action="deleted",
        header=header,
        list_name=REMINDERS_LIST,
        detail="Reminder deleted.",
    )


def reminder_exists(header: str) -> bool:
    """True iff a reminder titled exactly `header` exists in `BuJo Habits`.

    A missing list counts as "does not exist" (returns False) rather than an
    error — the list is created lazily on the first add.
    """
    script = f"""
        tell application "Reminders"
            if not (exists list {_as_quote(REMINDERS_LIST)}) then
                return "false"
            end if
            set theList to list {_as_quote(REMINDERS_LIST)}
            if (count of (reminders of theList whose name is {_as_quote(header)})) > 0 then
                return "true"
            else
                return "false"
            end if
        end tell
    """
    return _run_applescript(script).strip() == "true"


__all__ = [
    "REMINDERS_LIST",
    "ReminderAction",
    "ReminderResult",
    "add_reminder",
    "remove_reminder",
    "reminder_exists",
]
