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

# Self-heal uv. uv is a per-machine tool (not synced via iCloud), so on a
# fresh machine — or after a toolchain wipe — it can be missing, and every
# path below shells out to it (`uv run`, `uv venv`, `uv pip install`). Prepend
# ~/.local/bin first so an existing install is found on the lean hook PATH;
# only when it's still absent do we bootstrap via the official astral
# installer, which lands in that same ~/.local/bin. We deliberately avoid
# Homebrew: its bin dir may not be on the hook PATH, and it's a heavier
# dependency than the thing being bootstrapped.
#
# stdout is the MCP stdio channel, so every byte of installer output goes to
# stderr (`1>&2`) — matching the wheel-install convention below. The `|| true`
# keeps `set -e` from aborting before the re-check, so an offline failure
# surfaces as our actionable error rather than a bare pipe-failure exit. The
# curl timeouts bound the "no hang" guarantee to more than a fast-failing DNS
# error: a stalled connect (captive portal, black-holed 443) would otherwise
# block on the OS SYN-retry timeout (~1-2 min) and read as a hang during the
# MCP handshake.
export PATH="${HOME}/.local/bin:${PATH}"
if ! command -v uv >/dev/null 2>&1; then
  echo "scribe: uv not found; installing to ~/.local/bin" 1>&2
  curl --connect-timeout 15 --max-time 120 -LsSf https://astral.sh/uv/install.sh | sh 1>&2 || true
  if ! command -v uv >/dev/null 2>&1; then
    echo "scribe: uv install failed — is the machine online? Install uv manually (https://astral.sh/uv), then retry." 1>&2
    exit 1
  fi
fi

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

# Guard against a foreign venv carried over from another machine (e.g. the
# vault synced via iCloud but the venv came along too). Its bin/python can be
# a *present-but-dead* symlink pointing at the other box's uv-managed
# interpreter, absent here. Such a venv passes the `-x` check below yet can't
# run, and the hash guard alone would never rebuild it. `-e` follows the
# symlink, so the test is false exactly when the interpreter target is
# missing — healthy venv kept, dangling or absent bin/python wiped so the
# rebuild proceeds. No-op when the venv doesn't exist yet.
#
# Deliberately readlink-free: `readlink -f` is a GNU / modern-macOS extension,
# and on a macOS whose readlink lacks `-f` the old form
# `[ ! -e "$(readlink -f ... 2>/dev/null)" ]` degraded to `[ ! -e "" ]` —
# always true — wiping a *healthy* venv on every launch.
if [ -d "${VENV_DIR}" ] && [ ! -e "${VENV_DIR}/bin/python" ]; then
  rm -rf "${VENV_DIR}"
fi

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
  # stdout is the MCP stdio channel: keep it clean structurally (>/dev/null,
  # matching `uv venv` above) rather than trusting --quiet alone; stderr stays
  # visible for diagnostics.
  uv pip install --python "${VENV_DIR}/bin/python" --quiet --force-reinstall "${WHEEL}" >/dev/null
  echo "${WHEEL_HASH}" > "${HASH_MARKER}"
fi

# Hand off to the venv binary. exec replaces the shell so signals
# propagate cleanly — Claude Code's MCP lifecycle stop signal goes
# straight to the Python process.
exec "${VENV_DIR}/bin/bujo-scribe-mcp" "$@"
