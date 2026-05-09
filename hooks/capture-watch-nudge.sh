#!/usr/bin/env bash
#
# capture-watch-nudge (workbench-bujo): UserPromptSubmit hook that injects
# a terse per-turn reminder so proactive auto-capture stays salient as the
# conversation grows. Without this, the SessionStart guidance recedes from
# active context and the agent drifts back to reactive-only routing.
#
# Emits a context block on stdout. Claude Code injects that into the
# assistant's context for this turn. Exit code is always 0 — a hook
# failure must not block Mike's prompt.

set -u

cat <<'EOF'
# 🪶 BuJo capture-watch (per-turn reminder)

Categorize Mike's message before responding:

- **Explicit completion / decision / event** ("I shipped X", "decided to Y", "had a 1:1 with Z", "finished Q")
  → Silent dispatch via `bujo_apply_decisions:add` onto `today`. Confirm in one line: *"🪶 Logged: <bullet>"*. No `AskUserQuestion`.
- **Inferred insight / pivot / breakthrough** (worth marking, not explicitly named — "it hit me…", a realization that emerged, a clear approach-change)
  → Propose via `AskUserQuestion` (yes/no, two options). The wording IS the bullet — no edit option.
- **Routine code / file / lookup ops, trivial completions, thinking-aloud**
  → Skip silently. Don't propose, don't dispatch.

Self-throttle: 3+ consecutive `AskUserQuestion` nos this session → stop proposing for the rest of the session and acknowledge once. Manual `/bujo-capture <text>` always dispatches without asking.

If today's note doesn't exist yet, scaffold it before the first capture (`bujo_scaffold` with `target: "today"`, `ritual: "daily"`, `mode: "merge"`).
EOF

exit 0
