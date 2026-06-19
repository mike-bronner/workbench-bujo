"""Tests for the macOS Reminders integration (`reminders` module + tool).

No real EventKit runs here — the PyObjC backend is swapped for a `FakeBackend`
via the `_get_backend()` seam, so the pure logic (time gating, cadence
parsing, recurrence derivation, next-fire computation, and add/remove
branching) is exercised on any platform, mirroring how the rest of the suite
swaps a FakeBackend for Apple Notes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from bujo_scribe_mcp import reminders
from bujo_scribe_mcp.reminders import RecurrenceSpec
from bujo_scribe_mcp.schemas import ReminderInput
from bujo_scribe_mcp.tools import reminder as reminder_tool


class FakeBackend:
    """Records create/delete calls and answers `reminder_exists` from a fixed
    flag, so tests can both assert "was/wasn't called" and inspect arguments."""

    def __init__(self, *, exists: bool = False, delete_count: int | None = None) -> None:
        self._exists = exists
        self._delete_count = delete_count if delete_count is not None else (1 if exists else 0)
        self.created: list[tuple[str, datetime, RecurrenceSpec]] = []
        self.deleted: list[str] = []

    def reminder_exists(self, title: str) -> bool:
        return self._exists

    def create_reminder(self, title: str, fire_at: datetime, spec: RecurrenceSpec) -> None:
        self.created.append((title, fire_at, spec))

    def delete_reminders(self, title: str) -> int:
        self.deleted.append(title)
        return self._delete_count


@pytest.fixture
def fake_backend(monkeypatch):
    """Install a FakeBackend behind `_get_backend()` and return it."""
    backend = FakeBackend()

    def _install(**kwargs):
        nonlocal backend
        backend = FakeBackend(**kwargs)
        monkeypatch.setattr(reminders, "_get_backend", lambda: backend)
        return backend

    _install()
    return _install


def _next_weekday(target_py_weekday: int, *, hour: int = 8) -> datetime:
    """A concrete datetime on the next occurrence of a Python weekday
    (Mon=0…Sun=6), at `hour:00` — keeps weekly tests calendar-independent."""
    base = datetime(2026, 6, 1, hour, 0, 0, 0)
    while base.weekday() != target_py_weekday:
        base += timedelta(days=1)
    return base


# ---------------------------------------------------------------------------
# parse_cadence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Meditate (10 min) @08:00 [daily]", "daily"),
        ("Strength @17:00 [mwf]", "mwf"),
        ("Stretch @07:00 [tth]", "tth"),
        ("Walk @12:00 [weekdays]", "weekdays"),
        ("Cold shower @06:00 [every-3-days]", "every-3-days"),
        ("Journal @21:00 [3x-week]", "3x-week"),
        ("Bible Study @08:00", "daily"),  # no brackets → default daily
        ("Read @20:00 [MWF]", "mwf"),  # case-insensitive
    ],
)
def test_parse_cadence(header, expected):
    assert reminders.parse_cadence(header) == expected


# ---------------------------------------------------------------------------
# recurrence_for_cadence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cadence,expected",
    [
        ("daily", RecurrenceSpec(frequency="daily")),
        ("weekdays", RecurrenceSpec(frequency="weekly", weekdays=(2, 3, 4, 5, 6))),
        ("weekday", RecurrenceSpec(frequency="weekly", weekdays=(2, 3, 4, 5, 6))),
        ("mwf", RecurrenceSpec(frequency="weekly", weekdays=(2, 4, 6))),
        ("tth", RecurrenceSpec(frequency="weekly", weekdays=(3, 5))),
        ("every-3-days", RecurrenceSpec(frequency="daily", interval=3)),
        ("every-1-day", RecurrenceSpec(frequency="daily", interval=1)),
        # count cadence has no fixed day pattern → daily fallback
        ("3x-week", RecurrenceSpec(frequency="daily")),
        ("nonsense", RecurrenceSpec(frequency="daily")),
    ],
)
def test_recurrence_for_cadence(cadence, expected):
    assert reminders.recurrence_for_cadence(cadence) == expected


# ---------------------------------------------------------------------------
# first_fire  (the "no alarm in the past" guard)
# ---------------------------------------------------------------------------


def test_first_fire_daily_time_still_ahead_today():
    now = datetime(2026, 6, 19, 8, 0)
    spec = RecurrenceSpec(frequency="daily")
    assert reminders.first_fire(now, 9, 0, spec) == datetime(2026, 6, 19, 9, 0)


def test_first_fire_daily_time_already_passed_rolls_to_tomorrow():
    now = datetime(2026, 6, 19, 10, 0)
    spec = RecurrenceSpec(frequency="daily")
    assert reminders.first_fire(now, 9, 0, spec) == datetime(2026, 6, 20, 9, 0)


def test_first_fire_daily_exact_now_is_not_in_the_past():
    now = datetime(2026, 6, 19, 9, 0, 0)
    spec = RecurrenceSpec(frequency="daily")
    # Equal to now counts as "not in the past" → fires today.
    assert reminders.first_fire(now, 9, 0, spec) == datetime(2026, 6, 19, 9, 0)


def test_first_fire_weekly_today_allowed_and_ahead_fires_today():
    spec = RecurrenceSpec(frequency="weekly", weekdays=(2, 4, 6))  # mwf
    now = _next_weekday(2, hour=8)  # a Wednesday, 08:00 — Wed is allowed, 09:00 ahead
    result = reminders.first_fire(now, 9, 0, spec)
    assert result.date() == now.date()
    assert (result.hour, result.minute) == (9, 0)


def test_first_fire_weekly_today_allowed_but_passed_rolls_forward():
    spec = RecurrenceSpec(frequency="weekly", weekdays=(2, 4, 6))  # mwf
    now = _next_weekday(2, hour=10)  # Wednesday 10:00 — past the 09:00 slot
    result = reminders.first_fire(now, 9, 0, spec)
    assert result > now
    assert result.date() != now.date()
    assert reminders._py_weekday_to_ek(result.weekday()) in spec.weekdays


def test_first_fire_weekly_today_not_allowed_picks_next_allowed_day():
    spec = RecurrenceSpec(frequency="weekly", weekdays=(3, 5))  # tth (Tue, Thu)
    now = _next_weekday(0, hour=8)  # a Monday — not in {Tue, Thu}
    result = reminders.first_fire(now, 9, 0, spec)
    assert result > now
    assert reminders._py_weekday_to_ek(result.weekday()) in spec.weekdays


# ---------------------------------------------------------------------------
# add_reminder
# ---------------------------------------------------------------------------


def test_add_with_time_creates_recurring_reminder(fake_backend):
    backend = fake_backend(exists=False)
    now = datetime(2026, 6, 19, 7, 0)

    result = reminders.add_reminder("Meditate (10 min) @08:00 [daily]", "08:00", now=now)

    assert result.action == "created"
    assert result.list_name == "BuJo Habits"
    assert len(backend.created) == 1
    title, fire_at, spec = backend.created[0]
    assert title == "Meditate (10 min) @08:00 [daily]"
    assert fire_at == datetime(2026, 6, 19, 8, 0)
    assert spec == RecurrenceSpec(frequency="daily")


def test_add_derives_recurrence_from_header_cadence(fake_backend):
    backend = fake_backend(exists=False)

    reminders.add_reminder("Strength @17:00 [mwf]", "17:00", now=datetime(2026, 6, 19, 7, 0))

    _, _, spec = backend.created[0]
    assert spec == RecurrenceSpec(frequency="weekly", weekdays=(2, 4, 6))


def test_add_without_time_creates_nothing(fake_backend):
    backend = fake_backend(exists=False)

    result = reminders.add_reminder("Bible Study", None)

    assert result.action == "skipped_no_time"
    assert backend.created == []


@pytest.mark.parametrize("bad_time", ["morning", "8", "8:00 am", "24:00", "07:60", ""])
def test_add_with_non_hhmm_time_creates_nothing(fake_backend, bad_time):
    backend = fake_backend(exists=False)

    result = reminders.add_reminder("Stretch", bad_time)

    assert result.action == "skipped_no_time"
    assert backend.created == []


def test_re_add_existing_header_skips_duplicate(fake_backend):
    backend = fake_backend(exists=True)

    result = reminders.add_reminder("Meditate (10 min) @08:00 [daily]", "08:00")

    assert result.action == "skipped_exists"
    assert result.detail == "Reminder already exists"
    assert backend.created == []  # no create dispatched


# ---------------------------------------------------------------------------
# remove_reminder
# ---------------------------------------------------------------------------


def test_remove_existing_reminder_deletes(fake_backend):
    backend = fake_backend(exists=True)

    result = reminders.remove_reminder("Meditate (10 min) @08:00 [daily]")

    assert result.action == "deleted"
    assert backend.deleted == ["Meditate (10 min) @08:00 [daily]"]


def test_remove_missing_reminder_does_not_error(fake_backend):
    fake_backend(exists=False)  # delete_reminders returns 0

    result = reminders.remove_reminder("Never Existed")

    assert result.action == "not_found"


# ---------------------------------------------------------------------------
# reminder_exists
# ---------------------------------------------------------------------------


def test_reminder_exists_delegates_to_backend(fake_backend):
    fake_backend(exists=True)
    assert reminders.reminder_exists("Meditate") is True

    fake_backend(exists=False)
    assert reminders.reminder_exists("Meditate") is False


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
