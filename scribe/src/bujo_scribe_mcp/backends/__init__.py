"""Notebook backends — pluggable storage implementations."""

from __future__ import annotations

from bujo_scribe_mcp.backends.base import BackendError, NotebookBackend


def get_backend(name: str, *, folder: str) -> NotebookBackend:
    """Resolve and instantiate a backend by name.

    New backends register themselves here. Keep this map small and explicit —
    one line per backend, no auto-discovery.
    """
    if name == "apple_notes":
        from bujo_scribe_mcp.backends.apple_notes import AppleNotesBackend

        return AppleNotesBackend(folder=folder)

    raise BackendError(f"Unknown backend: {name!r}")


__all__ = ["NotebookBackend", "BackendError", "get_backend"]
