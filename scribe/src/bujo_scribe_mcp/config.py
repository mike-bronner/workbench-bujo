"""Runtime configuration resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    backend: str
    folder: str
    index_title: str
    timezone: str
    server_name: str
    user_rules_path: Path | None


def load() -> Config:
    user_rules_raw = os.getenv("BUJO_SCRIBE_USER_RULES_PATH")
    user_rules_path = Path(user_rules_raw).expanduser() if user_rules_raw else None

    return Config(
        backend=os.getenv("BUJO_SCRIBE_BACKEND", "apple_notes"),
        folder=os.getenv("BUJO_SCRIBE_FOLDER", "📓 Journal"),
        index_title=os.getenv("BUJO_SCRIBE_INDEX_TITLE", "📓 Journal Index"),
        timezone=os.getenv("BUJO_SCRIBE_TIMEZONE", "America/Phoenix"),
        server_name=os.getenv("BUJO_SCRIBE_SERVER_NAME", "bujo-scribe"),
        user_rules_path=user_rules_path,
    )
