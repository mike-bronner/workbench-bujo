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

cat <<'EOF'
# 📓 BuJo routing

The `workbench-bujo` plugin is active. Mike's bullet journal lives in Apple Notes under the `📓 Journal` folder and is managed via the `scribe` MCP (tools prefixed `mcp__plugin_workbench-bujo_scribe__bujo_*`).

**The journal is the source of truth for tasks, events, notes, and schedules — not local memory.** When Mike mentions any of these in free conversation (outside of an explicit `/bujo` ritual), route through the scribe rather than inventing a side list.

## Trigger vocabulary → scribe action

| Mike says something like… | Default action |
|---|---|
| "I need to…", "add a task", "don't forget to…", "todo:" | `bujo_apply_decisions` with `op: "add"` onto `today`, signifier `task` |
| "meeting at…", "appointment on…", "I have X on [date]" | Same pattern with signifier `event`; if the date is future, use `op: "schedule"` to land it in the Future Log instead |
| "FYI…", "worth noting…", "insight:", "remember that…" | `op: "add"` with signifier `note` onto `today` |
| "what's on today?", "did I have X?", "is Y on the list?" | `bujo_read(notes: ["today"])` first, answer from fresh state |
| "I finished X", "done with Y", "shipped Z" | `op: "complete"` on the matching bullet |
| "drop X", "skip X", "not doing X" | `op: "drop"` on the matching bullet |
| "bring back X", "restore X", "I shouldn't have dropped X" | `op: "undrop"` on the matching bullet |
| "combine X into Y", "fold X under Y", "nest X under Y" | `op: "combine"` — source gets `>`, target gets a sub-item under the parent. NEVER interpret "combine" as "drop" |

## Rules of the road

1. **Never invent a task list in memory.** If Mike mentions work to do, it belongs in the journal.
2. **Always pre-warm the scribe.** If the deferred tool list shows `mcp__plugin_workbench-bujo_scribe__*`, load schemas via `ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read,...")` before first use. The MCP may take ~10s to boot — retry with brief sleeps before concluding it's offline.
3. **Confirm before adding, when ambiguous.** If it's not obvious whether a mention is a real capture vs. incidental discussion, ask: *"Add that to today's journal?"* Single-sentence confirm, then dispatch.
4. **Single items don't need the `/bujo` ritual.** Just dispatch one `add` decision and confirm the diff. The ritual is for periodic reflection (daily/weekly/etc.), not capture.
5. **Respect existing signifiers and prefixes.** Priority (`✽`), inspiration (`!`), and explore (`◉`) are Mike's — inherit his choice if he mentions it, don't impose one.

## Not in scope for routing

- Code-level TODOs and comments in source files — those stay in code.
- Claude Code session-scoped todos (the `TodoWrite` tool) — those are for tracking the *current turn's work*, not durable tasks.
- Items Mike is clearly thinking-aloud about, not committing to ("maybe I should X"). Confirm before capturing.

EOF

exit 0
