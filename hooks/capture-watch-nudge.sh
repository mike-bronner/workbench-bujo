#!/usr/bin/env bash
#
# capture-watch-nudge (workbench-bujo): UserPromptSubmit hook that injects
# a two-line per-turn pointer so proactive auto-capture stays salient as the
# conversation grows. The canonical tier definitions, examples, and throttle
# rules load once at session start (session-warmup.sh) and live in
# skills/bujo-capture.md — this nudge only keeps them active. It is
# re-processed on EVERY user prompt, so it must stay tiny (≤250 bytes).
#
# Emits a context block on stdout. Claude Code injects that into the
# assistant's context for this turn. Exit code is always 0 — a hook
# failure must not block Mike's prompt.

set -u

cat <<'EOF'
🪶 Capture-watch: explicit completion/decision/event → silent `bujo_apply_decisions:add` + 1-line ack; inferred insight → AskUserQuestion (yes/no); routine → skip.
Scaffold `today` first if missing (`bujo_scaffold`: today/daily/merge).
EOF

exit 0
