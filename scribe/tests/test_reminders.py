"""Tests for the macOS Reminders integration (`reminders` module + tool).

No real `osascript` runs here — the `_run_applescript` seam and the
`reminder_exists` probe are monkeypatched so the AppleScript-building and
branching logic is exercised on any platform, mirroring how the rest of the
suite swaps a FakeBackend for Apple Notes.
"""

from __future__ import annotations

import pytest

from bujo_scribe_mcp import reminders
from bujo_scribe_mcp.backends.base import BackendError
from bujo_scribe_mcp.schemas import ReminderInput
from bujo_scribe_mcp.tools import reminder as reminder_tool


class _Recorder:
    """Captures every AppleScript handed to `_run_applescript` and returns a
    canned stdout. Lets tests both assert "was/ wasn't called" and inspect the
    generated script."""

    def __init__(self, returns: str = "ok") -> None:
        self.scripts: list[str] = []
        self.returns = returns

    def __call__(self, script: str, *, timeout: float = 30) -> str:
        self.scripts.append(script)
        return self.returns


def _no_run(*_args, **_kwargs):  # pragma: no cover - only the assertion matters
    raise AssertionError("_run_applescript should not have been called")


# ---------------------------------------------------------------------------
# add_reminder
# ---------------------------------------------------------------------------


def test_add_with_time_creates_reminder(monkeypatch):
    monkeypatch.setattr(reminders, "reminder_exists", lambda header: False)
    rec = _Recorder()
    monkeypatch.setattr(reminders, "_run_applescript", rec)

    result = reminders.add_reminder("Meditate (10 min) @08:00 [daily]", "08:00")

    assert result.action == "created"
    assert result.list_name == "BuJo Habits"
    assert len(rec.scripts) == 1
    script = rec.scripts[0]
    # List auto-create guard, the habit title, and the alert time are all present.
    assert 'exists list "BuJo Habits"' in script
    assert "make new list" in script
    assert "Meditate (10 min) @08:00 [daily]" in script
    assert "set hours of remindDate to 8" in script
    assert "set minutes of remindDate to 0" in script


def test_add_without_time_creates_nothing(monkeypatch):
    # Probe must never run, and no AppleScript may be dispatched.
    monkeypatch.setattr(reminders, "reminder_exists", _no_run)
    monkeypatch.setattr(reminders, "_run_applescript", _no_run)

    result = reminders.add_reminder("Bible Study", None)

    assert result.action == "skipped_no_time"


@pytest.mark.parametrize("bad_time", ["morning", "8", "8:00 am", "24:00", "07:60", ""])
def test_add_with_non_hhmm_time_creates_nothing(monkeypatch, bad_time):
    monkeypatch.setattr(reminders, "reminder_exists", _no_run)
    monkeypatch.setattr(reminders, "_run_applescript", _no_run)

    result = reminders.add_reminder("Stretch", bad_time)

    assert result.action == "skipped_no_time"


def test_re_add_existing_header_skips_duplicate(monkeypatch):
    monkeypatch.setattr(reminders, "reminder_exists", lambda header: True)
    # If a create script were dispatched, this would raise.
    monkeypatch.setattr(reminders, "_run_applescript", _no_run)

    result = reminders.add_reminder("Meditate (10 min) @08:00 [daily]", "08:00")

    assert result.action == "skipped_exists"
    assert result.detail == "Reminder already exists"


# ---------------------------------------------------------------------------
# remove_reminder
# ---------------------------------------------------------------------------


def test_remove_existing_reminder_deletes(monkeypatch):
    monkeypatch.setattr(reminders, "reminder_exists", lambda header: True)
    rec = _Recorder()
    monkeypatch.setattr(reminders, "_run_applescript", rec)

    result = reminders.remove_reminder("Meditate (10 min) @08:00 [daily]")

    assert result.action == "deleted"
    assert len(rec.scripts) == 1
    script = rec.scripts[0]
    assert "delete (every reminder" in script
    assert "Meditate (10 min) @08:00 [daily]" in script


def test_remove_missing_reminder_does_not_error(monkeypatch):
    monkeypatch.setattr(reminders, "reminder_exists", lambda header: False)
    # No delete script may be dispatched for a missing reminder.
    monkeypatch.setattr(reminders, "_run_applescript", _no_run)

    result = reminders.remove_reminder("Never Existed")

    assert result.action == "not_found"


# ---------------------------------------------------------------------------
# reminder_exists + helpers
# ---------------------------------------------------------------------------


def test_reminder_exists_reads_probe_output(monkeypatch):
    monkeypatch.setattr(reminders, "_run_applescript", _Recorder(returns="true"))
    assert reminders.reminder_exists("Meditate") is True

    monkeypatch.setattr(reminders, "_run_applescript", _Recorder(returns="false"))
    assert reminders.reminder_exists("Meditate") is False


def test_as_quote_escapes_quotes_and_backslashes():
    assert reminders._as_quote('a "b" c') == '"a \\"b\\" c"'
    assert reminders._as_quote("path\\to") == '"path\\\\to"'


def test_quotes_in_header_are_escaped_in_script(monkeypatch):
    monkeypatch.setattr(reminders, "reminder_exists", lambda header: False)
    rec = _Recorder()
    monkeypatch.setattr(reminders, "_run_applescript", rec)

    reminders.add_reminder('Read "Atomic Habits" @20:00', "20:00")

    # The embedded double-quotes are backslash-escaped, not left raw.
    assert '\\"Atomic Habits\\"' in rec.scripts[0]


def test_run_applescript_missing_osascript_raises_backend_error(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(reminders.subprocess, "run", _boom)
    with pytest.raises(BackendError):
        reminders._run_applescript('return "ok"')


# ---------------------------------------------------------------------------
# tool wrapper
# ---------------------------------------------------------------------------


def test_tool_add_maps_result_to_output(monkeypatch):
    monkeypatch.setattr(
        reminders, "add_reminder",
        lambda header, time: reminders.ReminderResult("created", header, "BuJo Habits", "ok"),
    )
    out = reminder_tool.execute(
        ReminderInput(op="add", header="Meditate @08:00", time="08:00"), ctx=None
    )
    assert out.action == "created"
    assert out.header == "Meditate @08:00"
    assert out.list_name == "BuJo Habits"


def test_tool_remove_dispatches_remove(monkeypatch):
    seen = {}

    def _fake_remove(header):
        seen["header"] = header
        return reminders.ReminderResult("deleted", header, "BuJo Habits", "Reminder deleted.")

    monkeypatch.setattr(reminders, "remove_reminder", _fake_remove)
    out = reminder_tool.execute(ReminderInput(op="remove", header="Stretch"), ctx=None)

    assert out.action == "deleted"
    assert seen["header"] == "Stretch"
