"""Tests for the tool-level output caps on bujo_read and bujo_scan.

Both verbs used to return whatever the notebook held — a wide `scan` scope
or a fat monthly note came back unbounded, and the only thing standing
between that and the model's context was workbench-core's blunt
`PostToolUse` byte truncation, which cuts mid-JSON with no idea what it
dropped. These tests pin the semantic replacement: a documented cap, a
prefix of the results in a deterministic order, and a `truncated` record
carrying the exact count of what was left out.

The two invariants worth stating outright:

- A response under the cap is byte-identical to the old behavior and
  `truncated` is None. Null means "that is everything."
- Over the cap, nothing is dropped silently — `omitted` is exact, not a
  floor, and `detail` names the env var that raises the cap.
"""

from __future__ import annotations

import pytest

from bujo_scribe_mcp import config as config_module
from bujo_scribe_mcp.parsing import HeadingLine, TableLine, UnrecognizedLine
from bujo_scribe_mcp.schemas import ReadInput, ScanFilter, ScanInput
from bujo_scribe_mcp.tools import read, scan


def _table_html(padding: int) -> str:
    """A parseable Apple Notes table whose raw_html is `padding`-ish chars."""
    cells = "<td><div>" + ("x" * padding) + "</div></td>"
    return (
        '<div><object><table cellspacing="0"><tbody>'
        f"<tr>{cells}</tr>"
        "</tbody></table></object><br></div>"
    )


# ---------------------------------------------------------------------------
# bujo_read
# ---------------------------------------------------------------------------


def test_small_read_is_completely_unaffected(
    make_backend, make_context, render_body, make_bujo_line
):
    """The common case — a normal note under the shipped default cap — comes
    back whole, with no truncation signal at all."""
    body = render_body(
        "note-one",
        [make_bujo_line("task", f"Task {n}") for n in range(3)],
    )
    ctx = make_context(make_backend({"note-one": body}))

    out = read.execute(ReadInput(notes=["note-one"]), ctx=ctx)

    note = out.packet["note-one"]
    assert note.truncated is None
    assert [line.text for line in note.lines] == ["Task 0", "Task 1", "Task 2"]


def test_read_caps_lines_and_reports_exact_omitted_count(
    make_backend, make_context, render_body, make_bujo_line
):
    """Over budget: a document-order prefix comes back, and `truncated`
    carries the exact number of lines left behind plus the env var to raise."""
    body = render_body(
        "note-one",
        [make_bujo_line("task", f"Task {n:02d}") for n in range(12)],
    )
    # Each line costs len("Task NN") + the 120-char envelope allowance = 127,
    # so a 1,000-char budget fits exactly 7 lines (7 × 127 = 889; an 8th would
    # reach 1,016).
    ctx = make_context(make_backend({"note-one": body}), max_read_chars=1_000)

    out = read.execute(ReadInput(notes=["note-one"]), ctx=ctx)

    note = out.packet["note-one"]
    assert [line.text for line in note.lines] == [f"Task {n:02d}" for n in range(7)]
    assert note.truncated is not None
    assert note.truncated.omitted == 5
    assert note.truncated.limit == 1_000
    assert "BUJO_SCRIBE_MAX_READ_CHARS" in note.truncated.detail


def test_read_budget_spans_the_whole_packet_in_request_order(
    make_backend, make_context, render_body, make_bujo_line
):
    """The cap is packet-wide, not per-note: a first note that eats the budget
    leaves the second empty — but flagged, never silently blank."""
    first = render_body("note-one", [make_bujo_line("task", f"Task {n:02d}") for n in range(8)])
    second = render_body("note-two", [make_bujo_line("task", f"Old {n:02d}") for n in range(3)])
    ctx = make_context(
        make_backend({"note-one": first, "note-two": second}),
        max_read_chars=1_000,
    )

    out = read.execute(ReadInput(notes=["note-one", "note-two"]), ctx=ctx)

    assert len(out.packet["note-one"].lines) == 7
    starved = out.packet["note-two"]
    assert starved.exists is True
    assert starved.lines == []
    assert starved.truncated is not None
    assert starved.truncated.omitted == 3


def test_read_returns_a_line_wider_than_the_entire_budget(
    make_backend, make_context, render_body, make_bujo_line
):
    """A single line bigger than the whole budget is emitted anyway.

    This is the monthly habit tracker: one TableLine whose raw_html can rival
    the budget, that must round-trip byte-exact or `update_table` corrupts the
    note. Refusing it would make it unreachable at any request size — no
    narrowing helps — so it goes out whole. Lines after it still report as
    omitted, so the overrun is never hidden.
    """
    table = _table_html(2_000)
    body = render_body(
        "tracker-note",
        [
            HeadingLine(text="Tracker", level=2),
            TableLine(raw_html=table),
            make_bujo_line("task", "Trailing task"),
        ],
    )
    ctx = make_context(make_backend({"tracker-note": body}), max_read_chars=1_000)

    out = read.execute(ReadInput(notes=["tracker-note"]), ctx=ctx)

    note = out.packet["tracker-note"]
    kinds = [line.kind for line in note.lines]
    assert kinds == ["heading", "table"]
    assert note.lines[1].raw_html == table
    assert note.truncated is not None
    assert note.truncated.omitted == 1


def test_read_ignores_filtered_lines_when_spending_budget(
    make_backend, make_context, render_body, make_bujo_line
):
    """Blank/unrecognized rows never reach the wire, so they must not consume
    budget or inflate the omitted count."""
    body = render_body(
        "note-one",
        [
            UnrecognizedLine(raw_html="<div><object><attachment>" + "z" * 5_000 + "</attachment></object><br></div>"),
            make_bujo_line("task", "Task 00"),
        ],
    )
    ctx = make_context(make_backend({"note-one": body}), max_read_chars=1_000)

    out = read.execute(ReadInput(notes=["note-one"]), ctx=ctx)

    note = out.packet["note-one"]
    assert [line.text for line in note.lines] == ["Task 00"]
    assert note.truncated is None


def test_missing_note_carries_no_truncation(make_backend, make_context):
    ctx = make_context(make_backend({}))

    out = read.execute(ReadInput(notes=["note-one"]), ctx=ctx)

    note = out.packet["note-one"]
    assert note.exists is False
    assert note.truncated is None


def test_shipped_read_default_actually_binds(
    make_backend, make_context, render_body, make_bujo_line
):
    """Guards the default itself: with no override, a runaway note is capped.

    Without this, someone could set DEFAULT_MAX_READ_CHARS to a billion and
    every override-based test above would still pass.
    """
    body = render_body(
        "note-one",
        [make_bujo_line("task", f"Task {n:04d}") for n in range(600)],
    )
    ctx = make_context(make_backend({"note-one": body}))

    out = read.execute(ReadInput(notes=["note-one"]), ctx=ctx)

    note = out.packet["note-one"]
    assert len(note.lines) < 600
    assert note.truncated is not None
    assert note.truncated.omitted == 600 - len(note.lines)
    assert note.truncated.limit == config_module.DEFAULT_MAX_READ_CHARS


# ---------------------------------------------------------------------------
# bujo_scan
# ---------------------------------------------------------------------------


def test_small_scan_is_completely_unaffected(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body("note-one", [make_bujo_line("task", f"Task {n}") for n in range(3)])
    ctx = make_context(make_backend({"note-one": body}))

    out = scan.execute(
        ScanInput(scope=["note-one"], filter=ScanFilter(status="open")), ctx=ctx
    )

    assert len(out.items) == 3
    assert out.truncated is None


def test_scan_caps_items_and_reports_exact_omitted_count(
    make_backend, make_context, render_body, make_bujo_line
):
    body = render_body("note-one", [make_bujo_line("task", f"Task {n:02d}") for n in range(12)])
    ctx = make_context(make_backend({"note-one": body}), max_scan_items=5)

    out = scan.execute(
        ScanInput(scope=["note-one"], filter=ScanFilter(status="open")), ctx=ctx
    )

    assert [item.text for item in out.items] == [f"Task {n:02d}" for n in range(5)]
    assert out.truncated is not None
    assert out.truncated.omitted == 7
    assert out.truncated.limit == 5
    assert "BUJO_SCRIBE_MAX_SCAN_ITEMS" in out.truncated.detail
    assert "scope" in out.truncated.detail


def test_scan_cap_spans_the_whole_scope_in_order(
    make_backend, make_context, render_body, make_bujo_line
):
    """Multi-note scope truncates at the scope boundary it reaches, in the
    order the caller listed — deterministic, so the same call returns the
    same bytes."""
    first = render_body("note-one", [make_bujo_line("task", f"A{n}") for n in range(4)])
    second = render_body("note-two", [make_bujo_line("task", f"B{n}") for n in range(4)])
    ctx = make_context(
        make_backend({"note-one": first, "note-two": second}), max_scan_items=5
    )

    out = scan.execute(
        ScanInput(scope=["note-one", "note-two"], filter=ScanFilter(status="open")), ctx=ctx
    )

    assert [item.text for item in out.items] == ["A0", "A1", "A2", "A3", "B0"]
    assert out.truncated is not None
    assert out.truncated.omitted == 3


def test_unrecognized_scan_is_capped_too(
    make_backend, make_context, render_body, make_bujo_line
):
    """The `unrecognized` filter is a separate branch in scan — and the one
    most likely to match broadly across legacy notes, so it needs its own
    guard."""
    body = render_body(
        "note-one",
        [
            UnrecognizedLine(
                raw_html=f"<div><object><attachment>legacy {n}</attachment></object><br></div>"
            )
            for n in range(12)
        ],
    )
    ctx = make_context(make_backend({"note-one": body}), max_scan_items=5)

    out = scan.execute(
        ScanInput(scope=["note-one"], filter=ScanFilter(status="unrecognized")), ctx=ctx
    )

    assert len(out.items) == 5
    assert all(item.signifier == "unrecognized" for item in out.items)
    assert out.truncated is not None
    assert out.truncated.omitted == 7


def test_shipped_scan_default_actually_binds(
    make_backend, make_context, render_body, make_bujo_line
):
    """Guards the default itself — see the read equivalent above."""
    count = config_module.DEFAULT_MAX_SCAN_ITEMS + 25
    body = render_body("note-one", [make_bujo_line("task", f"Task {n:04d}") for n in range(count)])
    ctx = make_context(make_backend({"note-one": body}))

    out = scan.execute(
        ScanInput(scope=["note-one"], filter=ScanFilter(status="open")), ctx=ctx
    )

    assert len(out.items) == config_module.DEFAULT_MAX_SCAN_ITEMS
    assert out.truncated is not None
    assert out.truncated.omitted == 25


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


_CAP_ENV_VARS = ("BUJO_SCRIBE_MAX_READ_CHARS", "BUJO_SCRIBE_MAX_SCAN_ITEMS")


@pytest.fixture
def clean_cap_env(monkeypatch):
    for name in _CAP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_caps_default_to_the_documented_values(clean_cap_env):
    cfg = config_module.load()

    assert cfg.max_read_chars == 50_000
    assert cfg.max_scan_items == 200


def test_caps_are_env_configurable(clean_cap_env):
    clean_cap_env.setenv("BUJO_SCRIBE_MAX_READ_CHARS", "1234")
    clean_cap_env.setenv("BUJO_SCRIBE_MAX_SCAN_ITEMS", "7")

    cfg = config_module.load()

    assert cfg.max_read_chars == 1234
    assert cfg.max_scan_items == 7


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "12.5"])
def test_malformed_cap_env_fails_closed_at_startup(clean_cap_env, bad):
    """A typo'd or nonsensical cap raises at load time rather than silently
    falling back to the default — an operator who thinks they raised a cap
    must not be left believing it while the default is still in force."""
    clean_cap_env.setenv("BUJO_SCRIBE_MAX_SCAN_ITEMS", bad)

    with pytest.raises(ValueError, match="BUJO_SCRIBE_MAX_SCAN_ITEMS"):
        config_module.load()
