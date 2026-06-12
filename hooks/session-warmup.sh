#!/usr/bin/env bash
#
# session-warmup (workbench-bujo): inject BuJo routing guidance at session
# start so the agent defaults to the scribe MCP whenever Mike mentions
# tasks / events / notes / bullets in free conversation — not just during
# an explicit `/bujo` ritual.
#
# Emits a context block on stdout. Claude Code injects that into the
# assistant's context. Exit code is always 0 — a warmup failure must not
# break the session.

set -u

# Pre-warm Apple Notes so the scribe MCP's first AppleScript call is fast.
# Backgrounded + double-forked; never blocks session start, no output.
# Idempotent — if Notes is already running, this is a no-op.
( osascript -e 'tell application "Notes" to launch' >/dev/null 2>&1 & ) &

# ---------------------------------------------------------------------------
# Version-drift warning. The desktop app can keep serving a stale plugin
# bundle while the CLI plugin cache is already current
# (anthropics/claude-code#45810) — the scribe MCP then silently runs an old
# version against the live journal. Surface it loudly at warmup.
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

# Skill-file paths for the pointer sections below. Guarded expansion — under
# `set -u` an unset CLAUDE_PLUGIN_ROOT (manual runs, tests) must not kill the
# warmup; it degrades to repo-relative paths.
_bujo_root="${CLAUDE_PLUGIN_ROOT:-}"
_capture_skill="${_bujo_root:+$_bujo_root/}skills/bujo-capture.md"
_ritual_skill="${_bujo_root:+$_bujo_root/}skills/rituals/bujo-ritual.md"

cat <<'EOF'
# 📓 BuJo routing

The `workbench-bujo` plugin is active. Mike's bullet journal lives in Apple Notes under the `📓 Journal` folder and is managed via the `scribe` MCP (tools prefixed `mcp__plugin_workbench-bujo_scribe__bujo_*`).

**The journal is the source of truth for tasks, events, notes, and schedules — not local memory.** When Mike mentions any of these in free conversation (outside of an explicit `/bujo` ritual), route through the scribe rather than inventing a side list.

## Trigger vocabulary → scribe action

| Mike says something like… | Default action |
|---|---|
| "I need to…", "add a task", "don't forget to…", "todo:" | `bujo_apply_decisions` with `op: "add"` onto `today`, signifier `task` |
| "I need to X next week / on [future date]" | Add directly to `future_log` with text `[YYYY-MM-DD] X` and signifier `task` (use `add` op with `note: "future_log"`) — don't bounce through today |
| "meeting at…", "appointment on…", "I have X on [date]" | Signifier `event`. Today/no-date → `add` onto `today`. Future date → add to `future_log` with `[YYYY-MM-DD]` prefix. |
| "FYI…", "worth noting…", "insight:", "remember that…" | `op: "add"` with signifier `note` onto `today` |
| "what's on today?", "did I have X?", "is Y on the list?" | `bujo_read(notes: ["today"])` first, answer from fresh state |
| "I finished X", "done with Y", "shipped Z" | `op: "complete"` on the matching bullet IF an open task matches; else **auto-capture** as `× X` on today (the work happened, record it) |
| "drop X", "skip X", "not doing X" | `op: "drop"` on the matching bullet |
| "bring back X", "restore X", "I shouldn't have dropped X" | `op: "undrop"` on the matching bullet |
| "combine X into Y", "fold X under Y", "nest X under Y" | `op: "combine"` — source gets `>`, target gets a sub-item under the parent. NEVER interpret "combine" as "drop" |

## Proactive capture — be the day's scribe

Beyond reactive routing: **across every session, capture genuinely meaningful moments to today's note as they happen.** The journal becomes a sparse, signal-rich highlight reel. The per-turn `UserPromptSubmit` nudge reinforces this between turns.

Triage every user message into three tiers: **explicit completion / decision / event** → silent `bujo_apply_decisions:add` (or `:complete`) + one-line ack, no `AskUserQuestion`; **inferred / ambiguous capture-worthy moment** → propose via `AskUserQuestion` (yes/no, two options — the wording IS the bullet, no edit option); **routine code / file / lookup ops** → skip silently. Self-throttle: 3+ consecutive tier-2 nos → stop proposing for the session.
EOF

cat <<EOF
**Canonical tier definitions, examples, and the AskUserQuestion template:** read \`${_capture_skill}\` before the first tier-2 proposal.
EOF

cat <<'EOF'
### Threshold dial

Calibrated to err toward fewer-but-stronger captures. Mike adjusts mid-session via natural language: *"be more selective with captures"* moves triggers from tier-1/tier-2 toward skip; *"capture more eagerly"* loosens the bar. Carry the adjustment forward in the same session.

### Where this runs

Plugin-loading clients only — Claude Code and Claude Cowork (Mac desktop app). Claude Chat doesn't run plugins; captures from there are out of scope.

## Habit tracker (≥0.10) — surface what's due today

Mike's monthly note has a habit-tracker table under the Tracker heading. Each column is a habit; column headers carry metadata (`Meditate (10 min) @08:00 [daily]`). Cells filled with `✅` are completions for that day-row.
EOF

cat <<EOF
At session start, if \`today\` exists: read **Step 2.5 (Habit check-in)** in \`${_ritual_skill}\` and run that check now — parse the tracker on \`monthly_current\`, surface due-and-unmarked habits via one batched \`AskUserQuestion\` (≤4, yes/no), update cells on yes. No habit table on \`monthly_current\` → skip silently (habit tracking isn't set up).
EOF

cat <<'EOF'
## Rules of the road

1. **Never invent a task list in memory.** If Mike mentions work to do, it belongs in the journal.
2. **Always pre-warm the scribe.** If the deferred tool list shows `mcp__plugin_workbench-bujo_scribe__*`, load schemas via `ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read,...")` before first use. The MCP may take ~10s to boot — retry with brief sleeps before concluding it's offline.
3. **Three capture tiers, not one.** (a) Reactive-routing matches and explicit-phrasing captures dispatch silently — Mike gave the signal. (b) Inferred / ambiguous capture-worthy moments go through `AskUserQuestion` (yes/no). (c) Routine code / file / lookup ops are skipped silently. See *Proactive capture* above for the categorization rule.
4. **Single items don't need the `/bujo` ritual.** Just dispatch one `add` (or capture) decision and confirm the diff in one line. The ritual is for periodic reflection (daily/weekly/etc.), not capture.
5. **Respect existing signifiers and prefixes.** Priority (`✽`), inspiration (`!`), and explore (`◉`) are Mike's — inherit his choice if he mentions it, don't impose one.
6. **Signal-to-noise is sacred.** Better to under-capture than to flood the log. The "skip silently" list above is the floor; everything trivial stays out.

## Not in scope for routing

- Code-level TODOs and comments in source files — those stay in code.
- Claude Code session-scoped todos (the `TodoWrite` tool) — those are for tracking the *current turn's work*, not durable tasks.
- Items Mike is clearly thinking-aloud about, not committing to ("maybe I should X"). Confirm before capturing OR skip.

EOF

exit 0
