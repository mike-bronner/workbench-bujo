#!/usr/bin/env bash
#
# scribe launcher — install bundled wheel into a stable venv on first run
# (or version mismatch), then exec the venv binary directly. This bypasses
# `uv run` overhead per launch (~1-3s → ~300-500ms cold start).
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

# Extract bundled wheel version from filename:
# bujo_scribe_mcp-0.9.0-py3-none-any.whl → 0.9.0
BUNDLED_VERSION="$(basename "${WHEEL}" \
  | sed -E 's/^bujo_scribe_mcp-([^-]+)-py3-none-any\.whl$/\1/')"

# Read installed venv version (empty if venv missing or corrupt).
INSTALLED_VERSION=""
if [ -x "${VENV_DIR}/bin/bujo-scribe-mcp" ]; then
  INSTALLED_VERSION="$("${VENV_DIR}/bin/bujo-scribe-mcp" version 2>/dev/null || true)"
fi

# (Re)install if version doesn't match. uv handles venv creation, Python
# resolution, and dep installation in one call.
if [ "${BUNDLED_VERSION}" != "${INSTALLED_VERSION}" ]; then
  uv venv "${VENV_DIR}" --python ">=3.11" >/dev/null 2>&1
  uv pip install --python "${VENV_DIR}/bin/python" --quiet --force-reinstall "${WHEEL}"
fi

# Hand off to the venv binary. exec replaces the shell so signals
# propagate cleanly — Claude Code's MCP lifecycle stop signal goes
# straight to the Python process.
exec "${VENV_DIR}/bin/bujo-scribe-mcp" "$@"
