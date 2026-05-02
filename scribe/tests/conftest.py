"""Shared fixtures for scribe tests.

Provides a `FakeBackend` (in-memory NotebookBackend) and a default-rules
fixture so verb tests can run without macOS / Apple Notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import pytest

from bujo_scribe_mcp.backends.base import BackendError, Note, NoteRef, NotebookBackend
from bujo_scribe_mcp.config import Config
from bujo_scribe_mcp.context import Context
from bujo_scribe_mcp.parsing import (
    BlankLine,
    BujoLine,
    ParsedNote,
    UnrecognizedLine,
    render_note,
)
from bujo_scribe_mcp.rules import Rules
from bujo_scribe_mcp.rules.loader import load_rules


@dataclass
class FakeBackend(NotebookBackend):
    """In-memory notebook backend keyed by exact title.

    Stores raw HTML bodies so tests can either build them with the real
    renderer or write canned HTML directly.
    """

    notes: dict[str, str]

    def list_notes(self) -> list[NoteRef]:
        return [NoteRef(id=title, title=title) for title in self.notes]

    def find_by_title(self, title: str) -> NoteRef | None:
        if title in self.notes:
            return NoteRef(id=title, title=title)
        return None

    def read(self, ref: NoteRef) -> Note:
        if ref.id not in self.notes:
            raise BackendError(f"Note not found: {ref.id}")
        return Note(
            ref=ref,
            content=self.notes[ref.id],
            retrieved_at=datetime.now(timezone.utc),
        )

    def create(self, title: str, content: str) -> NoteRef:
        self.notes[title] = content
        return NoteRef(id=title, title=title)

    def update(self, ref: NoteRef, content: str) -> None:
        if ref.id not in self.notes:
            raise BackendError(f"Note not found: {ref.id}")
        self.notes[ref.id] = content

    def folder_exists(self) -> bool:
        return True


@pytest.fixture
def rules() -> Rules:
    """Default scribe rules — loaded from the shipped YAML."""
    return load_rules()


@pytest.fixture
def make_backend() -> Iterator[callable]:
    """Returns a factory that builds a FakeBackend from {title: html} pairs."""

    def _factory(notes: dict[str, str]) -> FakeBackend:
        return FakeBackend(notes=dict(notes))

    yield _factory


@pytest.fixture
def make_context(rules, tmp_path):
    """Returns a factory: backend -> Context wrapping that backend + default rules.

    Each test gets its own per-test `run_dir` under pytest's tmp_path, so
    mutation locks don't leak across tests and the test suite stays
    parallelizable.
    """

    def _factory(backend: NotebookBackend) -> Context:
        config = Config(
            backend="fake",
            folder="📓 Journal",
            index_title="📓 Journal Index",
            timezone=rules.timezone,
            server_name="bujo-scribe-test",
            user_rules_path=None,
            run_dir=tmp_path / "run",
        )
        return Context(config=config, rules=rules, backend=backend)

    return _factory


@pytest.fixture
def render_body(rules):
    """Returns a factory: list[Line] -> rendered Apple Notes HTML body."""

    def _factory(title: str, lines: list) -> str:
        note = ParsedNote(title=title, title_html="", lines=list(lines))
        return render_note(note, rules)

    return _factory


@pytest.fixture
def make_bujo_line(rules):
    """Returns a factory that builds a BujoLine with a renderer-derived anchor."""

    def _factory(
        signifier: str,
        text: str,
        *,
        prefix: str | None = None,
        depth: int = 0,
        dropped: bool = False,
    ) -> BujoLine:
        return BujoLine(
            signifier=signifier,
            text=text,
            prefix=prefix,
            depth=depth,
            dropped=dropped,
            anchor=text,  # parser sets anchor = text for top-level lines
            raw_html="",
        )

    return _factory


__all__ = [
    "FakeBackend",
    "BlankLine",
    "BujoLine",
    "UnrecognizedLine",
]
