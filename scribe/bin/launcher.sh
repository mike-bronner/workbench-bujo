#!/usr/bin/env bash
#
# scribe launcher — install bundled wheel into a stable venv on first run
# (or wheel-content change), then exec the venv binary directly. This
# bypasses `uv run` overhead per launch (~1-3s → ~50ms cold start).
#
# Cache key is the wheel's SHA-256 content hash, NOT the version string.
# This matters because `build-wheel.yml` rebuilds the wheel on every
# scribe-source push to main — without bumping the version. A version
# string alone would say "0.9.0 == 0.9.0, no reinstall" and silently
# leave users running stale binaries against newer source. Hashing the
# wheel bytes catches every real change.
#
# All state stays inside ${SCRIBE_DIR} so plugin uninstall is clean —
# no launchd plists, no shared system state, no remnants outside the
# plugin tree.
#
# Dev escape hatch: set BUJO_SCRIBE_DEV=1 to bypass the wheel and run
# from source via `uv run --project`. Use this when iterating on scribe
# code without rebuilding the wheel.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIBE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${SCRIBE_DIR}/.venv-stable"
WHEELS_DIR="${SCRIBE_DIR}/wheels"
RUN_DIR="${SCRIBE_DIR}/run"
HASH_MARKER="${VENV_DIR}/.installed-wheel-hash"

# Tell the scribe where to put lock files / runtime state.
export BUJO_SCRIBE_RUN_DIR="${RUN_DIR}"
mkdir -p "${RUN_DIR}"

# Dev mode: skip the wheel, run from source. No venv management.
if [ "${BUJO_SCRIBE_DEV:-0}" = "1" ]; then
  exec uv run --project "${SCRIBE_DIR}" bujo-scribe-mcp "$@"
fi

# Find the latest wheel in wheels/. There should normally be exactly one
# at the version of this commit, but if multiple are present we take the
# most recently modified.
WHEEL=""
if [ -d "${WHEELS_DIR}" ]; then
  WHEEL="$(ls -t "${WHEELS_DIR}"/bujo_scribe_mcp-*.whl 2>/dev/null | head -n 1 || true)"
fi

# No wheel committed (e.g., fresh checkout from a dev branch). Fall back
# to `uv run` so the user still has a working scribe.
if [ -z "${WHEEL}" ]; then
  exec uv run --project "${SCRIBE_DIR}" bujo-scribe-mcp "$@"
fi

# Hash the wheel bytes. shasum is part of macOS base; works on Linux too.
WHEEL_HASH="$(shasum -a 256 "${WHEEL}" | cut -d' ' -f1)"

# Read previously-installed wheel's hash (empty if venv missing).
INSTALLED_HASH=""
if [ -f "${HASH_MARKER}" ]; then
  INSTALLED_HASH="$(cat "${HASH_MARKER}")"
fi

# Reinstall iff the wheel's actual content has changed. Catches both
# version bumps (different filename) and same-version mid-cycle rebuilds
# (same filename, different bytes).
if [ "${WHEEL_HASH}" != "${INSTALLED_HASH}" ] || [ ! -x "${VENV_DIR}/bin/bujo-scribe-mcp" ]; then
  if [ ! -d "${VENV_DIR}" ]; then
    uv venv "${VENV_DIR}" --python ">=3.11" >/dev/null 2>&1
  fi
  uv pip install --python "${VENV_DIR}/bin/python" --quiet --force-reinstall "${WHEEL}"
  echo "${WHEEL_HASH}" > "${HASH_MARKER}"
fi

# Hand off to the venv binary. exec replaces the shell so signals
# propagate cleanly — Claude Code's MCP lifecycle stop signal goes
# straight to the Python process.
exec "${VENV_DIR}/bin/bujo-scribe-mcp" "$@"
