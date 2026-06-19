"""macOS Reminders integration — recurring habit reminders via EventKit.

A habit added with a specific ``@HH:MM`` time gets a macOS Reminder in a
dedicated list (`BuJo Habits`), titled with the habit's canonical
tracker-header text (e.g. ``Meditate (10 min) @08:00 [daily]``) and set to
**recur at the habit's cadence** — daily, weekdays, Mon/Wed/Fri, every N
days, and so on. Habits with no exact time (Anytime / Morning / Afternoon /
Evening) get no Reminder — the session-start habit check remains the
notification mechanism for those.

Why EventKit (and not osascript)
--------------------------------
The Reminders **AppleScript** dictionary exposes no writable recurrence
property — a scripted reminder can only ever be a one-shot timed alert. To
honour "recur at the habit's requested interval" while staying *inside the
Reminders app*, this module drives EventKit directly through PyObjC
(`pyobjc-framework-EventKit`). EventKit's `EKRecurrenceRule` gives true OS
recurrence; the trade is a new (macOS-only) dependency and a one-time
"allow Reminders access" (TCC) prompt for the MCP process on first use.

Testability
-----------
All EventKit I/O lives behind a small backend seam (`_get_backend()` →
``ReminderBackend``). The pure logic — time gating, cadence parsing,
recurrence-rule derivation, and next-fire computation — is platform-agnostic
and unit-tested directly; tests swap a fake backend for the real
`_EventKitBackend`, mirroring how the rest of the suite swaps a FakeBackend
for Apple Notes. The PyObjC framework is imported lazily inside the backend,
so this module imports cleanly on any platform.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol

from bujo_scribe_mcp.backends.base import BackendError

# The dedicated Reminders list for BuJo habit reminders. Created on demand.
REMINDERS_LIST = "BuJo Habits"

# Exact 24-hour HH:MM, anchored — so partial/junk input ("8", "8:00 am",
# "morning") is rejected and treated as "no specific time" → no reminder.
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# The bracketed cadence token in a canonical habit header, e.g. the "mwf" in
# ``Strength @17:00 [mwf]``. Absent brackets mean the default cadence (daily),
# which the header format omits to stay clean for the common case.
_CADENCE_RE = re.compile(r"\[([^\]]+)\]\s*$")
_EVERY_N_DAYS_RE = re.compile(r"^every-(\d+)-days?$")
_N_PER_WEEK_RE = re.compile(r"^(\d+)x-week$")

# Seconds to wait on EventKit's asynchronous access / fetch callbacks before
# giving up. Generous — these resolve in milliseconds once permission exists.
_ACCESS_TIMEOUT_SECONDS = 30.0
_FETCH_TIMEOUT_SECONDS = 30.0

# EventKit weekday integers: 1 = Sunday … 7 = Saturday (the EKWeekday /
# EKRecurrenceDayOfWeek convention).
_SUN, _MON, _TUE, _WED, _THU, _FRI, _SAT = 1, 2, 3, 4, 5, 6, 7
_WEEKDAYS = (_MON, _TUE, _WED, _THU, _FRI)


# ---------------------------------------------------------------------------
# Recurrence model (pure — no EventKit)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecurrenceSpec:
    """A platform-agnostic recurrence rule, derived from a habit's cadence.

    The `_EventKitBackend` translates this into an `EKRecurrenceRule`; the
    derivation and this shape are unit-tested without touching EventKit.

    - `frequency` — "daily" or "weekly".
    - `interval` — repeat every N units of `frequency` (≥ 1).
    - `weekdays` — EventKit weekday ints (1=Sun…7=Sat) the reminder fires on;
      empty for a plain daily rule (no day filter).
    """

    frequency: Literal["daily", "weekly"]
    interval: int = 1
    weekdays: tuple[int, ...] = field(default_factory=tuple)


def parse_cadence(header: str) -> str:
    """Extract the cadence token from a canonical habit header.

    The token is the bracketed suffix (``[mwf]`` → ``"mwf"``). A header with
    no brackets means the default cadence, ``"daily"`` — the header format
    omits ``[daily]`` to keep the common case clean.
    """
    match = _CADENCE_RE.search(header)
    return match.group(1).strip().lower() if match else "daily"


def recurrence_for_cadence(cadence: str) -> RecurrenceSpec:
    """Map a cadence token to a `RecurrenceSpec`.

    Recognised tokens (from the `bujo-habit-add` interview):
      - ``daily``                 → every day
      - ``weekdays`` / ``weekday``→ Mon–Fri
      - ``mwf``                   → Mon, Wed, Fri
      - ``tth``                   → Tue, Thu
      - ``every-N-days``          → daily, interval N
      - ``Nx-week``               → see below

    ``Nx-week`` ("N times per week") names a *count*, not specific days, so it
    has no fixed clock-day pattern. A timed reminder needs concrete days, so
    we fall back to a **daily** nudge — over-reminding (Mike completes it on N
    days of his choosing) is the safe failure mode for a habit prompt; a
    silent miss is not. Any unrecognised token also falls back to daily.
    """
    token = cadence.strip().lower()

    if token in ("daily", ""):
        return RecurrenceSpec(frequency="daily")
    if token in ("weekdays", "weekday"):
        return RecurrenceSpec(frequency="weekly", weekdays=_WEEKDAYS)
    if token == "mwf":
        return RecurrenceSpec(frequency="weekly", weekdays=(_MON, _WED, _FRI))
    if token == "tth":
        return RecurrenceSpec(frequency="weekly", weekdays=(_TUE, _THU))

    every_n = _EVERY_N_DAYS_RE.match(token)
    if every_n:
        return RecurrenceSpec(frequency="daily", interval=max(1, int(every_n.group(1))))

    # Nx-week names a count, not specific days, so it has no fixed clock-day
    # pattern — fall back to a daily nudge (see the docstring). Matched
    # explicitly so this is a deliberate, documented case rather than an
    # accidental fall-through.
    if _N_PER_WEEK_RE.match(token):
        return RecurrenceSpec(frequency="daily")

    # Any unrecognised token → daily.
    return RecurrenceSpec(frequency="daily")


def _py_weekday_to_ek(py_weekday: int) -> int:
    """Convert a Python `date.weekday()` (Mon=0…Sun=6) to an EventKit weekday
    integer (Sun=1…Sat=7)."""
    return ((py_weekday + 1) % 7) + 1


def first_fire(now: datetime, hour: int, minute: int, spec: RecurrenceSpec) -> datetime:
    """The first occurrence at ``hour:minute`` that is **not in the past**.

    Anchoring the reminder's first alarm to a future instant avoids the
    "added after its time today → alarm in the past, never fires" bug: a daily
    reminder set at 08:00 but added at 09:00 fires tomorrow, not in the past;
    a weekly reminder rolls forward to its next allowed weekday.
    """
    today_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if not spec.weekdays:
        # Plain daily / every-N-days: today if still ahead, else tomorrow.
        return today_at if today_at >= now else today_at + timedelta(days=1)

    # Weekly with a day filter: the soonest allowed weekday at hour:minute
    # that is still in the future. A non-empty weekday set always matches
    # within 7 days.
    for offset in range(7):
        candidate = today_at + timedelta(days=offset)
        if _py_weekday_to_ek(candidate.weekday()) in spec.weekdays and candidate >= now:
            return candidate
    # Unreachable for a non-empty weekday set, but stay total.
    return today_at + timedelta(days=7)


def _parse_time(time: str | None) -> tuple[int, int] | None:
    """Parse an exact ``HH:MM`` string into ``(hour, minute)``; None otherwise."""
    if time is None or not _TIME_RE.match(time):
        return None
    hour, minute = time.split(":")
    return int(hour), int(minute)


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
# Backend seam — EventKit I/O isolated behind a Protocol so it is swappable
# in tests. The pure logic above never imports EventKit.
# ---------------------------------------------------------------------------


class ReminderBackend(Protocol):
    """The EventKit operations the public ops depend on. Implemented for real
    by `_EventKitBackend`; replaced by a fake in tests."""

    def reminder_exists(self, title: str) -> bool: ...

    def create_reminder(
        self, title: str, fire_at: datetime, spec: RecurrenceSpec
    ) -> None: ...

    def delete_reminders(self, title: str) -> int: ...


_backend_singleton: ReminderBackend | None = None


def _get_backend() -> ReminderBackend:
    """Return the process-wide EventKit backend, constructing it on first use.

    Lazy so importing this module never imports PyObjC; cached so the EventKit
    access prompt is requested only once per process. Tests monkeypatch this
    function to inject a fake backend.
    """
    global _backend_singleton
    if _backend_singleton is None:
        _backend_singleton = _EventKitBackend()
    return _backend_singleton


class _EventKitBackend:
    """Real EventKit backend. All PyObjC use is confined here and the
    framework is imported lazily, so the module loads on any platform."""

    def __init__(self) -> None:
        try:
            import EventKit
        except ImportError as exc:  # pragma: no cover - exercised only off-macOS
            raise BackendError(
                "EventKit unavailable — habit reminders require macOS with "
                "pyobjc-framework-EventKit installed."
            ) from exc

        self._ek = EventKit
        self._store = EventKit.EKEventStore.alloc().init()
        self._request_access()

    # -- access -----------------------------------------------------------
    def _request_access(self) -> None:
        """Request Reminders access, blocking on EventKit's async callback.

        Uses the macOS 14+ full-access selector when present, falling back to
        the legacy entity-type request on older systems.
        """
        done = threading.Event()
        state: dict[str, object] = {}

        def handler(granted, error):  # noqa: ANN001 - ObjC callback signature
            state["granted"] = bool(granted)
            state["error"] = error
            done.set()

        store = self._store
        if store.respondsToSelector_("requestFullAccessToRemindersWithCompletion:"):
            store.requestFullAccessToRemindersWithCompletion_(handler)
        else:  # pragma: no cover - legacy macOS path
            store.requestAccessToEntityType_completion_(self._ek.EKEntityTypeReminder, handler)

        if not done.wait(timeout=_ACCESS_TIMEOUT_SECONDS):
            raise BackendError("Timed out waiting for Reminders access authorization.")
        if not state.get("granted"):
            raise BackendError(
                "Reminders access was denied — grant it in System Settings › "
                "Privacy & Security › Reminders to enable habit reminders."
            )

    # -- list (calendar) management --------------------------------------
    def _reminder_list(self):  # noqa: ANN202 - ObjC object
        """Find the `BuJo Habits` reminder list, creating it if absent."""
        ek, store = self._ek, self._store
        for cal in store.calendarsForEntityType_(ek.EKEntityTypeReminder):
            if cal.title() == REMINDERS_LIST:
                return cal

        cal = ek.EKCalendar.calendarForEntityType_eventStore_(ek.EKEntityTypeReminder, store)
        cal.setTitle_(REMINDERS_LIST)
        cal.setSource_(self._reminder_source())
        ok, err = store.saveCalendar_commit_error_(cal, True, None)
        if not ok:
            raise BackendError(f"Could not create '{REMINDERS_LIST}' list: {err}")
        return cal

    def _reminder_source(self):  # noqa: ANN202 - ObjC object
        """The source to host a new reminder list — the default reminders
        calendar's source, else the first local source, else any source."""
        store = self._store
        default_cal = store.defaultCalendarForNewReminders()
        if default_cal is not None:
            return default_cal.source()
        ek = self._ek
        sources = list(store.sources())
        for src in sources:
            if src.sourceType() == ek.EKSourceTypeLocal:
                return src
        if sources:
            return sources[0]
        raise BackendError("No Reminders source available to create a list.")

    # -- fetch ------------------------------------------------------------
    def _fetch_matching(self, title: str) -> list:
        """All reminders in `BuJo Habits` whose title equals `title` exactly."""
        store = self._store
        predicate = store.predicateForRemindersInCalendars_([self._reminder_list()])

        done = threading.Event()
        box: dict[str, list] = {"reminders": []}

        def completion(reminders):  # noqa: ANN001 - ObjC callback signature
            box["reminders"] = list(reminders or [])
            done.set()

        store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
        if not done.wait(timeout=_FETCH_TIMEOUT_SECONDS):
            raise BackendError("Timed out fetching reminders.")
        return [r for r in box["reminders"] if r.title() == title]

    # -- recurrence -------------------------------------------------------
    def _recurrence_rule(self, spec: RecurrenceSpec):  # noqa: ANN202 - ObjC object
        ek = self._ek
        frequency = (
            ek.EKRecurrenceFrequencyDaily
            if spec.frequency == "daily"
            else ek.EKRecurrenceFrequencyWeekly
        )
        if spec.weekdays:
            days = [ek.EKRecurrenceDayOfWeek.dayOfWeek_(d) for d in spec.weekdays]
            return ek.EKRecurrenceRule.alloc().initRecurrenceWithFrequency_interval_daysOfTheWeek_daysOfTheMonth_monthsOfTheYear_weeksOfTheYear_daysOfTheYear_setPositions_end_(  # noqa: E501
                frequency, spec.interval, days, None, None, None, None, None, None
            )
        return ek.EKRecurrenceRule.alloc().initRecurrenceWithFrequency_interval_end_(
            frequency, spec.interval, None
        )

    # -- public backend ops ----------------------------------------------
    def reminder_exists(self, title: str) -> bool:
        return len(self._fetch_matching(title)) > 0

    def create_reminder(self, title: str, fire_at: datetime, spec: RecurrenceSpec) -> None:
        ek, store = self._ek, self._store
        from Foundation import NSDate, NSDateComponents

        reminder = ek.EKReminder.reminderWithEventStore_(store)
        reminder.setTitle_(title)
        reminder.setCalendar_(self._reminder_list())

        components = NSDateComponents.alloc().init()
        components.setYear_(fire_at.year)
        components.setMonth_(fire_at.month)
        components.setDay_(fire_at.day)
        components.setHour_(fire_at.hour)
        components.setMinute_(fire_at.minute)
        reminder.setDueDateComponents_(components)

        ns_fire = NSDate.dateWithTimeIntervalSince1970_(fire_at.timestamp())
        reminder.addAlarm_(ek.EKAlarm.alarmWithAbsoluteDate_(ns_fire))
        reminder.setRecurrenceRules_([self._recurrence_rule(spec)])

        ok, err = store.saveReminder_commit_error_(reminder, True, None)
        if not ok:
            raise BackendError(f"Could not save reminder '{title}': {err}")

    def delete_reminders(self, title: str) -> int:
        store = self._store
        matches = self._fetch_matching(title)
        for reminder in matches:
            ok, err = store.removeReminder_commit_error_(reminder, True, None)
            if not ok:
                raise BackendError(f"Could not delete reminder '{title}': {err}")
        return len(matches)


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


def add_reminder(header: str, time: str | None, *, now: datetime | None = None) -> ReminderResult:
    """Create a recurring habit reminder in `BuJo Habits`, idempotently.

    - No exact ``HH:MM`` time → no reminder (`skipped_no_time`).
    - `header` already present in the list → no duplicate (`skipped_exists`).
    - Otherwise → create a reminder recurring at the header's cadence, first
      firing at the next future ``HH:MM``, auto-creating the list if absent
      (`created`).

    `now` is injectable for deterministic tests; defaults to the local clock.
    """
    parsed = _parse_time(time)
    if parsed is None:
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

    hour, minute = parsed
    spec = recurrence_for_cadence(parse_cadence(header))
    fire_at = first_fire(now or datetime.now(), hour, minute, spec)
    _get_backend().create_reminder(header, fire_at, spec)

    return ReminderResult(
        action="created",
        header=header,
        list_name=REMINDERS_LIST,
        detail=f"Reminder created — recurs at {time} ({_describe_cadence(spec)}).",
    )


def remove_reminder(header: str) -> ReminderResult:
    """Delete the habit reminder(s) matching `header` exactly.

    A non-existent reminder is not an error — returns `not_found`.
    """
    deleted = _get_backend().delete_reminders(header)
    if deleted == 0:
        return ReminderResult(
            action="not_found",
            header=header,
            list_name=REMINDERS_LIST,
            detail="No matching reminder — nothing to delete.",
        )
    return ReminderResult(
        action="deleted",
        header=header,
        list_name=REMINDERS_LIST,
        detail="Reminder deleted.",
    )


def reminder_exists(header: str) -> bool:
    """True iff a reminder titled exactly `header` exists in `BuJo Habits`."""
    return _get_backend().reminder_exists(header)


def _describe_cadence(spec: RecurrenceSpec) -> str:
    """A short human phrase for a recurrence spec, for the result `detail`."""
    if spec.weekdays:
        names = {_SUN: "Sun", _MON: "Mon", _TUE: "Tue", _WED: "Wed",
                 _THU: "Thu", _FRI: "Fri", _SAT: "Sat"}
        if tuple(spec.weekdays) == _WEEKDAYS:
            return "weekdays"
        return "/".join(names[d] for d in spec.weekdays)
    if spec.interval > 1:
        return f"every {spec.interval} days"
    return "daily"


__all__ = [
    "REMINDERS_LIST",
    "RecurrenceSpec",
    "ReminderAction",
    "ReminderBackend",
    "ReminderResult",
    "add_reminder",
    "first_fire",
    "parse_cadence",
    "recurrence_for_cadence",
    "remove_reminder",
    "reminder_exists",
]
