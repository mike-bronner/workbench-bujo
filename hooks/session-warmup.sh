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

Beyond reactive routing on phrasings: **across every session, watch for genuinely capture-worthy moments and propose them to Mike via `AskUserQuestion`.** The journal becomes a highlight reel — but only of moments Mike confirms are interesting. Triage is the agent's job; the decision to log is Mike's.

### How to propose (always `AskUserQuestion`, never silent dispatch)

For any moment that might be capture-worthy, propose via `AskUserQuestion` with the proposed bullet text in the question and **two options only**: yes or no. The wording in the question IS the bullet that lands on yes — there's no edit option. If the wording is wrong, Mike says no and the agent does better next time (or Mike runs `/bujo-capture` manually with the right text).

```jsonc
AskUserQuestion({
  questions: [{
    question: "🪶 Capture this on today's note?\n  `!— Architecture shift: MCP owns invariants, skills get drifty`",
    header: "Capture?",
    multiSelect: false,
    options: [
      { label: "Yes — log it", description: "Adds the bullet to today's note" },
      { label: "No — skip",    description: "Not capture-worthy" }
    ]
  }]
})
```

On **Yes** → dispatch `bujo_apply_decisions:add` immediately. Confirm with one line: *"🪶 Logged."*
On **No** → skip silently, do not retry, do not paraphrase and re-offer.

**No silent auto-capture.** Even unambiguous moments (just shipped a release, named a clear decision) go through this prompt. The point is for Mike to keep the journal sparse — every entry should be one he actively picked.

### What to propose (triage candidates)

- Concrete completions Mike just announced ("I shipped X", "Y is done")
- Work the agent just completed at Mike's direction that produced a real artifact (release, PR merge, deployment)
- Decisions Mike named explicitly ("decided to X", "going with Y")
- Insights/realizations Mike voiced ("I realized X", "the insight is…")
- Real-world events Mike mentioned ("had a 1:1 with Y about Z")
- Pivots or approach-changes that might be capture-worthy
- Frustrations or breakthroughs with potential stakes
- Future-dated tasks Mike implied (also offer to schedule to Future Log)

### Skip silently — never propose

- Routine code edits, file changes, command runs
- Trivial completions ("installed deps", "fixed typo", "ran tests")
- Anything reconstructable from git history or tool transcripts
- Thinking-aloud that hasn't crystallized
- Work-in-progress checkpoints that haven't landed

### Self-throttle on rejection

If Mike says **No** to **3 or more consecutive capture proposals** in a session, the agent's threshold is too eager. Stop proposing for the rest of the session and acknowledge it once: *"Got it — I'll stop proposing captures this session. Run `/bujo-capture <text>` if something specific comes up."*

This self-correction prevents the failure mode where the agent floods the conversation with prompts that Mike doesn't want.

### Trial threshold — adjustable

This is calibrated to err on the side of *fewer prompts, higher signal* — better to miss a capture than to bury Mike in offers. If the trial feels:

- **Too eager** (asking about routine stuff): Mike says *"be more selective with captures"* → agent moves more triggers from "propose" to "skip silently."
- **Too quiet** (missing things Mike cared about): Mike says *"propose captures more eagerly"* → agent loosens the bar.

The dial exists. Mike turns it via natural-language feedback during sessions; the agent carries that adjustment forward in the same session.

### Cross-Claude

Proactive capture runs wherever this plugin loads — Claude Code and Claude Cowork (both local Mac features of the Claude desktop app). Claude Chat doesn't run plugins, so captures don't happen from there.

## Habit tracker (≥0.10) — surface what's due today

Mike's monthly note has a habit-tracker table under the Tracker heading. Each column is a habit; column headers carry metadata (`Meditate (10 min) @08:00 [daily]`). Cells filled with `✅` are completions for that day-row.

At session start, if `today` exists, check the tracker for habits due today that haven't been marked done:

1. `bujo_read(notes: ["monthly_current"])` — find the heading `text="Tracker"` and the next line with `kind="table"`. Its `raw_html` field carries the table HTML.
2. Parse column headers (skip Day + Weekday — habits are columns 3+).
3. For each habit:
   - Parse cadence from `[<cadence>]`. Default to `daily` if unspecified.
   - Determine if today is a "due day" (cadence matches today's weekday or interval).
   - Find today's row in the table (day-of-month).
   - Find the habit's cell in that row.
   - If the cell is empty (no `✅`), it's an open habit-due signal.

For each due-and-empty habit, surface via `AskUserQuestion` (yes/no, natural language). Batch up to 4 in a single call:

```jsonc
AskUserQuestion({
  questions: [
    {
      question: "🌱 Habit due: `Bible Study` — done today?",
      header: "Habit?",
      multiSelect: false,
      options: [
        { label: "Yes — log it", description: "Mark today's cell ✅" },
        { label: "Not today",    description: "Skip" }
      ]
    }
    // up to 4 questions per call
  ]
})
```

On Yes:
- Boolean habit → dispatch `bujo_apply_decisions:update_table` with the table HTML regenerated (today's cell flipped to `✅`). Confirm with one line.
- Quantitative habit → follow up in plain text *"How much?"* → then dispatch with `✅ <n>`.

On No → skip silently. Don't re-prompt the same habit later in the session.

Self-throttle: same as proactive capture — 3+ consecutive nos this session → stop proposing habits for the rest of the session and acknowledge once.

**Don't propose habits Mike has already marked done today** — check today's cell content first. **Don't propose habits whose cadence excludes today** (e.g., `[mwf]` on Tuesday).

**No habit table on `monthly_current`?** Skip silently. The user hasn't set up habit tracking yet.

## Rules of the road

1. **Never invent a task list in memory.** If Mike mentions work to do, it belongs in the journal.
2. **Always pre-warm the scribe.** If the deferred tool list shows `mcp__plugin_workbench-bujo_scribe__*`, load schemas via `ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read,...")` before first use. The MCP may take ~10s to boot — retry with brief sleeps before concluding it's offline.
3. **Reactive routing dispatches without confirmation; proactive capture always asks via `AskUserQuestion`.** Two different rules for two different paths: (a) when Mike says something matching the trigger vocabulary table above, route directly without re-asking — he gave the instruction. (b) When the agent notices something potentially capture-worthy outside an explicit instruction, propose via `AskUserQuestion` (yes/no), never silently dispatch. See Proactive Capture above.
4. **Single items don't need the `/bujo` ritual.** Just dispatch one `add` (or capture) decision and confirm the diff in one line. The ritual is for periodic reflection (daily/weekly/etc.), not capture.
5. **Respect existing signifiers and prefixes.** Priority (`✽`), inspiration (`!`), and explore (`◉`) are Mike's — inherit his choice if he mentions it, don't impose one.
6. **Signal-to-noise is sacred.** Better to under-capture than to flood the log. The "skip silently" list above is the floor; everything trivial stays out.

## Not in scope for routing

- Code-level TODOs and comments in source files — those stay in code.
- Claude Code session-scoped todos (the `TodoWrite` tool) — those are for tracking the *current turn's work*, not durable tasks.
- Items Mike is clearly thinking-aloud about, not committing to ("maybe I should X"). Confirm before capturing OR skip.

EOF

exit 0
