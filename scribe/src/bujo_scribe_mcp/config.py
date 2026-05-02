"""Runtime configuration resolved from environment variables."""

from __future__ import annotations

import os
import tempfile
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
    run_dir: Path


def load() -> Config:
    user_rules_raw = os.getenv("BUJO_SCRIBE_USER_RULES_PATH")
    user_rules_path = Path(user_rules_raw).expanduser() if user_rules_raw else None

    run_dir_raw = os.getenv("BUJO_SCRIBE_RUN_DIR")
    if run_dir_raw:
        run_dir = Path(run_dir_raw).expanduser()
    else:
        # Fallback when scribe is launched outside the plugin launcher (tests,
        # ad-hoc dev). Tempdir is per-user so locks still serialize within the
        # session, and it's auto-cleaned when the OS prunes /tmp.
        run_dir = Path(tempfile.gettempdir()) / "bujo-scribe-run"

    return Config(
        backend=os.getenv("BUJO_SCRIBE_BACKEND", "apple_notes"),
        folder=os.getenv("BUJO_SCRIBE_FOLDER", "📓 Journal"),
        index_title=os.getenv("BUJO_SCRIBE_INDEX_TITLE", "📓 Journal Index"),
        timezone=os.getenv("BUJO_SCRIBE_TIMEZONE", "America/Phoenix"),
        server_name=os.getenv("BUJO_SCRIBE_SERVER_NAME", "bujo-scribe"),
        user_rules_path=user_rules_path,
        run_dir=run_dir,
    )
