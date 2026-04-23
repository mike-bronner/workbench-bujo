"""Abstract notebook backend.

A backend is the only place that knows how to read and write notes in a specific
storage system (Apple Notes, Obsidian, plain markdown, Notion, etc.). All
scribe verbs call through this interface — they never touch storage directly.

New backends must implement every method. The contract intentionally stays
small: read, write, create, list. Higher-level BuJo semantics (signifiers,
sections, index rules) live in the verb implementations, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class BackendError(Exception):
    """Raised for any storage-level failure the backend cannot recover from."""


@dataclass(frozen=True)
class NoteRef:
    """Opaque identifier for a note in the backend's storage.

    The string representation is backend-specific — for Apple Notes it may be
    a Notes-assigned ID or the title; for a file backend it's a path. Scribe
    verbs treat it as opaque and pass it back to the backend unchanged.
    """

    id: str
    title: str


@dataclass(frozen=True)
class Note:
    ref: NoteRef
    content: str
    retrieved_at: datetime


class NotebookBackend(ABC):
    """Storage-agnostic note access."""

    @abstractmethod
    def list_notes(self) -> list[NoteRef]:
        """Return all notes in the configured folder."""

    @abstractmethod
    def find_by_title(self, title: str) -> NoteRef | None:
        """Return a note reference by exact title match, or None if absent."""

    @abstractmethod
    def read(self, ref: NoteRef) -> Note:
        """Read note content. Must raise BackendError if not found."""

    @abstractmethod
    def create(self, title: str, content: str) -> NoteRef:
        """Create a new note with the given title and body. Returns its ref."""

    @abstractmethod
    def update(self, ref: NoteRef, content: str) -> None:
        """Overwrite note body. Must raise BackendError if not found."""

    @abstractmethod
    def folder_exists(self) -> bool:
        """Return True if the configured folder exists."""
