#!/usr/bin/env bash
#
# session-warmup (workbench-bujo): the live half of BuJo's session start —
# pre-warm Apple Notes, and warn when the running plugin bundle has drifted
# behind the CLI plugin cache. Both read live machine state, so both have to
# run per session.
#
# The *static* half — the BuJo routing block (trigger vocabulary, habit-check
# pointer, rules of the road) — is no longer emitted here. It lives in
# `session-warmup.md` at the plugin root, which workbench-core's SessionStart
# hook aggregates with every other workbench-* plugin's contribution into one
# block baked into ~/.claude/CLAUDE.md. One shared, byte-stable block instead
# of one live `additionalContext` block per plugin keeps the prompt-cache
# prefix intact for scheduled tasks. See workbench-core's
# `docs/session-warmup-contributions.md`.
#
# Emits on stdout only when drift is detected; silent otherwise. Exit code is
# always 0 — a warmup failure must not break the session.

set -u

# Pre-warm Apple Notes so the scribe MCP's first AppleScript call is fast.
# Backgrounded + double-forked; never blocks session start, no output.
# Idempotent — if Notes is already running, this is a no-op.
( osascript -e 'tell application "Notes" to launch' >/dev/null 2>&1 & ) &

# Skip guard: Claude Code sets this env var on every sub-agent dispatch
# (bujo-orchestrator — and Watson, Holmes, Lestrade, or any future agent
# from any plugin). Those runs carry self-contained system prompts and must
# not inherit interactive-session content: the drift warning below is a
# heads-up for Mike, not something a dispatched agent can act on. Injected
# into every dispatch it burns tokens and breaks the agent's prompt-cache
# prefix. Mike's own interactive sessions and the orchestrator/Dispatch runs
# that spawn those agents have no --agent, leave this unset, and are
# unaffected.
# Placed after the Notes pre-warm on purpose — that is a silent, idempotent
# side effect worth keeping for agents that do hit the journal.
if [ -n "${CLAUDE_CODE_AGENT:-}" ]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Version-drift warning. The desktop app can keep serving a stale plugin
# bundle while the CLI plugin cache is already current
# (anthropics/claude-code#45810) — the scribe MCP then silently runs an old
# version against the live journal. Surface it loudly at warmup.
#
# This is deliberately NOT part of `session-warmup.md`: it flips on every
# upgrade, and the aggregated block must be byte-identical across runs to stay
# cacheable. Volatile state stays in the live hook.
#
# Best-effort and dependency-free: extract versions with sed (no jq — the
# hook PATH is narrow under Cowork), compare numerically with BSD `sort`
# (no GNU-only `-V`), and stay silent on any missing input. Fires only when
# the running bundle is STRICTLY behind the newest version in the CLI cache.
# A Cowork-only setup with no CLI cache has nothing to compare against, so
# the check no-ops there.
# ---------------------------------------------------------------------------

_bujo_plugin_version() {
  # Echo the "version" field from a plugin.json, or nothing.
  [ -f "$1" ] || return 1
  sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -n 1
}

_bujo_newest_cached_version() {
  # Echo the highest semver dir name under the CLI plugin cache, or nothing.
  local cache_dir="$HOME/.claude/plugins/cache/claude-workbench/workbench-bujo"
  [ -d "$cache_dir" ] || return 1
  ls -1 "$cache_dir" 2>/dev/null \
    | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' \
    | sort -t. -k1,1n -k2,2n -k3,3n \
    | tail -n 1
}

_bujo_version_lt() {
  # True (0) iff $1 is strictly lower than $2 (both X.Y.Z).
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -n 1)" = "$1" ]
}

_bujo_emit_drift_warning() {
  local root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$root" ] || return 0
  local bundle newest
  bundle=$(_bujo_plugin_version "$root/.claude-plugin/plugin.json") || return 0
  [ -n "$bundle" ] || return 0
  newest=$(_bujo_newest_cached_version) || return 0
  [ -n "$newest" ] || return 0
  _bujo_version_lt "$bundle" "$newest" || return 0
  cat <<DRIFT
# ⚠️ BuJo plugin version drift — running v${bundle}, v${newest} available

The active **workbench-bujo** bundle is **v${bundle}**, but **v${newest}** is installed in your CLI plugin cache. The desktop app may be serving a stale plugin (known issue — anthropics/claude-code#45810), which silently routes the scribe MCP to outdated code against your live journal.

**Realign:** run \`claude plugin marketplace update claude-workbench\` in a terminal, then fully quit (Cmd-Q) and relaunch the desktop app. This warning clears once the running bundle matches the cache.

---

DRIFT
}

_bujo_emit_drift_warning

exit 0
