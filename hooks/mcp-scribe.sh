#!/usr/bin/env bash
#
# mcp-scribe: launcher for the bujo-scribe-mcp server.
#
# Resolves env vars from config.json at server-start time, so plugin updates
# never clobber MCP configuration. config.json is the single source of truth;
# plugin.json just points at this wrapper.
#
# Auto-install + auto-update:
#   The plugin bundles a matching version of bujo-scribe-mcp as a .whl at
#   $CLAUDE_PLUGIN_ROOT/assets/scribe/bujo_scribe_mcp-X.Y.Z-py3-none-any.whl.
#   On every MCP launch we compare the bundled wheel's version to the
#   installed binary's version and reinstall if they differ (or if the
#   binary is missing). This means plugin updates automatically update the
#   MCP — users don't need to run any setup step after a plugin upgrade.

set -u

PLUGIN_DATA_DIR="$HOME/.claude/plugins/data/workbench-bujo-claude-workbench"
CONFIG_FILE="$PLUGIN_DATA_DIR/config.json"
USER_RULES_FILE="$PLUGIN_DATA_DIR/rules.yaml"

_cfg() {
  [ -f "$CONFIG_FILE" ] && command -v jq >/dev/null 2>&1 \
    && jq -r "$1 // empty" "$CONFIG_FILE" 2>/dev/null
}

BACKEND=$(_cfg '.backend')
FOLDER=$(_cfg '.folder')
INDEX_TITLE=$(_cfg '.index_title')
TIMEZONE=$(_cfg '.timezone')
MCP_NAME=$(_cfg '.mcp_server_name')

export BUJO_SCRIBE_BACKEND="${BACKEND:-apple_notes}"
export BUJO_SCRIBE_FOLDER="${FOLDER:-📓 Journal}"
export BUJO_SCRIBE_INDEX_TITLE="${INDEX_TITLE:-📓 Journal Index}"
export BUJO_SCRIBE_TIMEZONE="${TIMEZONE:-America/Phoenix}"
export BUJO_SCRIBE_SERVER_NAME="${MCP_NAME:-bujo-scribe}"

if [ -f "$USER_RULES_FILE" ]; then
  export BUJO_SCRIBE_USER_RULES_PATH="$USER_RULES_FILE"
fi

# ----------------------------------------------------------------------------
# Resolve the scribe binary location.
# Cowork (and some Claude Code contexts) spawn MCP launchers with a narrower
# PATH than the login shell, so `~/.local/bin` may not be reachable via
# plain PATH lookup. Check common install locations by absolute path first.
# ----------------------------------------------------------------------------

_find_binary() {
  for _candidate in \
    "$HOME/.local/bin/bujo-scribe-mcp" \
    "$HOME/.cargo/bin/bujo-scribe-mcp" \
    "/opt/homebrew/bin/bujo-scribe-mcp" \
    "/usr/local/bin/bujo-scribe-mcp" \
    "/usr/bin/bujo-scribe-mcp"; do
    if [ -x "$_candidate" ]; then
      echo "$_candidate"
      return 0
    fi
  done
  if command -v bujo-scribe-mcp >/dev/null 2>&1; then
    command -v bujo-scribe-mcp
    return 0
  fi
  return 1
}

# ----------------------------------------------------------------------------
# Bundled wheel lookup + version compare.
# Filename format: bujo_scribe_mcp-X.Y.Z-py3-none-any.whl
# ----------------------------------------------------------------------------

_bundled_wheel() {
  local _wheel
  _wheel=$(ls "${CLAUDE_PLUGIN_ROOT:-}"/assets/scribe/bujo_scribe_mcp-*.whl 2>/dev/null | head -n 1)
  if [ -n "$_wheel" ] && [ -f "$_wheel" ]; then
    echo "$_wheel"
    return 0
  fi
  return 1
}

_wheel_version() {
  # Extract "X.Y.Z" from "bujo_scribe_mcp-X.Y.Z-py3-none-any.whl"
  local _wheel="$1"
  basename "$_wheel" | sed -E 's/^bujo_scribe_mcp-([^-]+)-.*$/\1/'
}

_installed_version() {
  local _bin="$1"
  "$_bin" --version 2>/dev/null | head -n 1 | tr -d '[:space:]'
}

_auto_install() {
  local _wheel="$1"
  if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not found on PATH — cannot auto-install bujo-scribe-mcp." >&2
    echo "  Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
    return 1
  fi
  echo "bujo-scribe-mcp: installing from bundled wheel → $(basename "$_wheel") ..." >&2
  if ! uv tool install --from "$_wheel" bujo-scribe-mcp --force --reinstall >&2; then
    echo "ERROR: uv tool install failed for bundled wheel." >&2
    return 1
  fi
}

WHEEL=""
WHEEL_VER=""
if WHEEL=$(_bundled_wheel); then
  WHEEL_VER=$(_wheel_version "$WHEEL")
fi

SCRIBE_BIN=""
if SCRIBE_BIN=$(_find_binary); then :; else SCRIBE_BIN=""; fi

INSTALLED_VER=""
if [ -n "$SCRIBE_BIN" ]; then
  INSTALLED_VER=$(_installed_version "$SCRIBE_BIN")
fi

# Decide whether to (re)install from the bundled wheel.
_should_install=false
if [ -z "$SCRIBE_BIN" ]; then
  # Not installed at all.
  _should_install=true
elif [ -n "$WHEEL_VER" ] && [ -n "$INSTALLED_VER" ] && [ "$WHEEL_VER" != "$INSTALLED_VER" ]; then
  # Installed, but version differs from bundled wheel.
  echo "bujo-scribe-mcp: version mismatch — installed=$INSTALLED_VER bundled=$WHEEL_VER" >&2
  _should_install=true
elif [ -n "$WHEEL_VER" ] && [ -z "$INSTALLED_VER" ]; then
  # Binary exists but --version didn't respond — likely a pre-0.4.0 install. Refresh.
  echo "bujo-scribe-mcp: installed binary doesn't report a version; refreshing from bundled wheel." >&2
  _should_install=true
fi

if $_should_install; then
  if [ -z "$WHEEL" ]; then
    echo "ERROR: bujo-scribe-mcp not installed and no bundled wheel found at \$CLAUDE_PLUGIN_ROOT/assets/scribe/." >&2
    echo "  Install manually: uv tool install bujo-scribe-mcp" >&2
    exit 1
  fi
  if ! _auto_install "$WHEEL"; then
    exit 1
  fi
  # Re-resolve binary after install.
  if ! SCRIBE_BIN=$(_find_binary); then
    echo "ERROR: bujo-scribe-mcp not found on disk after install attempt." >&2
    exit 1
  fi
fi

exec "$SCRIBE_BIN" serve
