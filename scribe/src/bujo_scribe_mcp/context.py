"""Runtime context bundled from config, rules, and backend.

Every scribe verb receives a `Context` — rather than taking `config`,
`rules`, and `backend` as separate parameters. Keeps verb signatures stable
as the context grows (e.g., when the `DataSourceBackend` lands).
"""

from __future__ import annotations

from dataclasses import dataclass

from bujo_scribe_mcp.backends.base import NotebookBackend
from bujo_scribe_mcp.config import Config
from bujo_scribe_mcp.rules import Rules


@dataclass(frozen=True)
class Context:
    config: Config
    rules: Rules
    backend: NotebookBackend
