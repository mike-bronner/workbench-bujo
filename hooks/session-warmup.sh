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

Beyond reactive routing on phrasings: **across every session, watch for genuinely capture-worthy moments and log them to today's note.** The journal becomes a highlight reel of Mike's day, not just a planner. The `bujo-capture` skill has the dispatch details.

### Auto-capture (dispatch immediately, confirm in one line)

When the moment is unambiguous, dispatch via `bujo-capture` without asking. Confirm with one line: *"🪶 Logged: `× Shipped v0.9.5...`"* — that's the whole confirmation.

- **Concrete completions Mike just announced** ("I shipped X", "Y is done", "wrapped up Z") → `× X` on today.
- **Work the agent just completed at Mike's direction that produced a real artifact** — release, PR merge, deployment, deliverable — auto-capture as `× <what was done>`. Don't make Mike say it. Example: just shipped v0.9.5 in this session → `× Shipped v0.9.5: Future Log surfacers actually leave on migrate`.
- **Decisions Mike named explicitly** ("decided to X", "going with Y", "the call is Z") → `! X` on today.
- **Insights/realizations Mike voiced** ("I realized X", "X is the real proving ground", "the insight is…") → `!— X` on today.
- **Real-world events Mike mentioned** ("had a 1:1 with Y about Z", "got the call from X") → `○ X` on today.

### Ask-first (offer once, drop if no engagement)

When the moment might or might not land for Mike, offer one line:

> *"Worth capturing as `! Pivot: rewrote the launcher to bypass uv run`?"*

Don't repeat the offer. If Mike doesn't say yes, drop it — pile-up offers are worse than missed captures.

- Pivots or approach-changes that might be exploration rather than decision
- Frustrations or breakthroughs without clear stakes
- Future-dated tasks Mike implied but didn't fully commit ("I should X next month")
- Anything where the boundary between "thinking aloud" and "committing" is unclear

### Skip silently

- Routine code edits, file changes, command runs
- Trivial completions ("installed deps", "fixed typo", "ran tests")
- Anything reconstructable from git history or tool transcripts
- Thinking-aloud that hasn't crystallized into a decision
- Work-in-progress checkpoints that haven't landed

### Cross-Claude

Auto-capture runs wherever this plugin loads — Claude Code and Claude Cowork (both local Mac features of the Claude desktop app). Claude Chat doesn't run plugins, so captures don't happen from there.

## Rules of the road

1. **Never invent a task list in memory.** If Mike mentions work to do, it belongs in the journal.
2. **Always pre-warm the scribe.** If the deferred tool list shows `mcp__plugin_workbench-bujo_scribe__*`, load schemas via `ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read,...")` before first use. The MCP may take ~10s to boot — retry with brief sleeps before concluding it's offline.
3. **Confirm before adding ONLY when ambiguous.** Auto-capture cases above are unambiguous — don't add friction. Reserve "should I capture this?" prompts for the ask-first category.
4. **Single items don't need the `/bujo` ritual.** Just dispatch one `add` (or capture) decision and confirm the diff in one line. The ritual is for periodic reflection (daily/weekly/etc.), not capture.
5. **Respect existing signifiers and prefixes.** Priority (`✽`), inspiration (`!`), and explore (`◉`) are Mike's — inherit his choice if he mentions it, don't impose one.
6. **Signal-to-noise is sacred.** Better to under-capture than to flood the log. The "skip silently" list above is the floor; everything trivial stays out.

## Not in scope for routing

- Code-level TODOs and comments in source files — those stay in code.
- Claude Code session-scoped todos (the `TodoWrite` tool) — those are for tracking the *current turn's work*, not durable tasks.
- Items Mike is clearly thinking-aloud about, not committing to ("maybe I should X"). Confirm before capturing OR skip.

EOF

exit 0
