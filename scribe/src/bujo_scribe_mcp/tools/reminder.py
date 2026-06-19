"""bujo.reminder — create/delete a macOS Reminder for a habit.

A habit added with an exact ``@HH:MM`` time gets a reminder in the dedicated
`BuJo Habits` Reminders list (auto-created), titled with the habit's
canonical tracker-header text. Habits with no exact time get none — the
session-start habit check covers those. Removal deletes the matching
reminder if present; a missing reminder is not an error.

Reminders are not notes, so this verb bypasses the `NotebookBackend` and
calls the osascript-backed `reminders` module directly. `ctx` is accepted
for signature parity with the other verbs.
"""

from __future__ import annotations

from bujo_scribe_mcp import reminders
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.schemas import ReminderInput, ReminderOutput


def execute(input: ReminderInput, *, ctx: Context) -> ReminderOutput:
    if input.op == "add":
        result = reminders.add_reminder(input.header, input.time)
    else:
        result = reminders.remove_reminder(input.header)

    return ReminderOutput(
        action=result.action,
        header=result.header,
        list_name=result.list_name,
        detail=result.detail,
    )
