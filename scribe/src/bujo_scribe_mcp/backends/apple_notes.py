"""Apple Notes backend — macOS, via AppleScript through `osascript`.

All I/O is shell-invoked: every method constructs an AppleScript, runs it
via `osascript -e`, and parses stdout. Errors from osascript (non-zero exit
or empty AppleScript error) raise `BackendError`.

AppleScript quoting model:
    - Strings are wrapped in `"…"`.
    - Backslashes and double quotes inside them are escaped (`\\`, `\"`).
    - Unicode characters (including the notebook emoji in `📓 Journal`) pass
      through as UTF-8.

Note-ID model:
    Apple Notes exposes an `id` that is a stable x-coredata:// URL for each
    note. We use it as `NoteRef.id`. The display title is stored in
    `NoteRef.title` — titles can be renamed by the user, IDs cannot.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from bujo_scribe_mcp.backends.base import BackendError, Note, NoteRef, NotebookBackend

# Record/field delimiters chosen to be vanishingly unlikely in note titles/content.
# U+001F = INFORMATION SEPARATOR ONE (field), U+001E = INFORMATION SEPARATOR TWO (record).
_FS = "\x1f"
_RS = "\x1e"

_OSASCRIPT_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------


def _as_quote(value: str) -> str:
    """Quote a Python string for safe interpolation into an AppleScript literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _run_applescript(script: str, *, timeout: float = _OSASCRIPT_TIMEOUT_SECONDS) -> str:
    """Run an AppleScript source block via `osascript -e` and return its stdout.

    Raises BackendError on non-zero exit, including the stderr text so the
    caller can see the AppleScript error reason.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BackendError(
            "osascript not found — Apple Notes backend requires macOS."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendError(f"AppleScript timed out after {timeout}s") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or "(no stderr)"
        raise BackendError(f"AppleScript failed (exit {result.returncode}): {stderr}")

    # osascript appends a trailing newline; strip only that one newline.
    return result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class AppleNotesBackend(NotebookBackend):
    def __init__(self, *, folder: str) -> None:
        self.folder = folder

    # --- folder

    def folder_exists(self) -> bool:
        script = f"""
            tell application "Notes"
                try
                    get folder {_as_quote(self.folder)}
                    return "true"
                on error
                    return "false"
                end try
            end tell
        """
        return _run_applescript(script).strip() == "true"

    # --- list

    def list_notes(self) -> list[NoteRef]:
        script = f"""
            set outText to ""
            set FS to (ASCII character 31)
            set RS to (ASCII character 30)
            tell application "Notes"
                set folderRef to folder {_as_quote(self.folder)}
                repeat with n in (notes of folderRef)
                    set outText to outText & (id of n) & FS & (name of n) & RS
                end repeat
            end tell
            return outText
        """
        raw = _run_applescript(script)
        return list(self._parse_records(raw))

    # --- find

    def find_by_title(self, title: str) -> NoteRef | None:
        script = f"""
            set FS to (ASCII character 31)
            tell application "Notes"
                try
                    set matches to notes of folder {_as_quote(self.folder)} whose name is {_as_quote(title)}
                    if (count of matches) is 0 then
                        return ""
                    end if
                    set n to item 1 of matches
                    return (id of n) & FS & (name of n)
                on error
                    return ""
                end try
            end tell
        """
        raw = _run_applescript(script).strip()
        if not raw:
            return None
        parts = raw.split(_FS, 1)
        if len(parts) != 2:
            raise BackendError(f"Unexpected find_by_title output: {raw!r}")
        return NoteRef(id=parts[0], title=parts[1])

    # --- read

    def read(self, ref: NoteRef) -> Note:
        script = f"""
            tell application "Notes"
                try
                    set n to first note of folder {_as_quote(self.folder)} whose id is {_as_quote(ref.id)}
                    return body of n
                on error
                    return ""
                end try
            end tell
        """
        body = _run_applescript(script)
        if not body:
            # Distinguish "exists but empty" (rare) from "not found".
            if self._note_exists_by_id(ref.id):
                body = ""
            else:
                raise BackendError(f"Note not found: {ref.id}")
        return Note(ref=ref, content=body, retrieved_at=datetime.now(timezone.utc))

    # --- create

    def create(self, title: str, content: str) -> NoteRef:
        if not self.folder_exists():
            raise BackendError(f"Folder missing: {self.folder}")

        script = f"""
            set FS to (ASCII character 31)
            tell application "Notes"
                set folderRef to folder {_as_quote(self.folder)}
                set newNote to make new note at folderRef with properties {{body:{_as_quote(content)}}}
                return (id of newNote) & FS & (name of newNote)
            end tell
        """
        # Note: `name:` is intentionally NOT set. Apple Notes auto-derives the
        # displayed title from the first line of the body. Passing both
        # `name:` and a title-shaped first line causes Apple Notes to inject
        # a plain-div duplicate of the title into stored HTML — which then
        # compounds on every subsequent write. Skipping `name:` avoids that.
        raw = _run_applescript(script).strip()
        parts = raw.split(_FS, 1)
        if len(parts) != 2:
            raise BackendError(f"Unexpected create output: {raw!r}")
        return NoteRef(id=parts[0], title=parts[1])

    # --- update

    def update(self, ref: NoteRef, content: str) -> None:
        script = f"""
            tell application "Notes"
                try
                    set n to first note of folder {_as_quote(self.folder)} whose id is {_as_quote(ref.id)}
                    set body of n to {_as_quote(content)}
                    return "ok"
                on error errMsg
                    return "err:" & errMsg
                end try
            end tell
        """
        raw = _run_applescript(script).strip()
        if raw != "ok":
            raise BackendError(f"update failed: {raw}")

    # --- helpers

    def _note_exists_by_id(self, note_id: str) -> bool:
        script = f"""
            tell application "Notes"
                try
                    get first note of folder {_as_quote(self.folder)} whose id is {_as_quote(note_id)}
                    return "true"
                on error
                    return "false"
                end try
            end tell
        """
        return _run_applescript(script).strip() == "true"

    @staticmethod
    def _parse_records(raw: str) -> list[NoteRef]:
        if not raw:
            return []
        records = raw.split(_RS)
        out: list[NoteRef] = []
        for rec in records:
            if not rec:
                continue
            parts = rec.split(_FS, 1)
            if len(parts) != 2:
                raise BackendError(f"Malformed record from AppleScript: {rec!r}")
            out.append(NoteRef(id=parts[0], title=parts[1]))
        return out


__all__ = ["AppleNotesBackend", "BackendError"]
