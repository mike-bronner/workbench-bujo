#!/usr/bin/env bash
#
# mcp-scribe: launcher for the bujo-scribe-mcp server.
#
# Resolves env vars from config.json at server-start time, so plugin updates
# never clobber MCP configuration. config.json is the single source of truth;
# plugin.json just points at this wrapper. Pattern mirrors workbench-core's
# mcp-memory.sh launcher.

set -u

PLUGIN_DATA_DIR="$HOME/.claude/plugins/data/workbench-bujo-claude-workbench"
CONFIG_FILE="$PLUGIN_DATA_DIR/config.json"
# User rules override — optional. If this file exists, the MCP deep-merges
# it on top of the shipped defaults. Users edit this to customize signifiers,
# add extensions, change timezone, etc., without touching plugin code.
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

exec bujo-scribe-mcp serve
