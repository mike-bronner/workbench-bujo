## 📓 BuJo routing

The `workbench-bujo` plugin is active. Mike's bullet journal lives in Apple Notes under the `📓 Journal` folder and is managed via the `scribe` MCP (tools prefixed `mcp__plugin_workbench-bujo_scribe__bujo_*`).

**The journal is the source of truth for tasks, events, notes, and schedules — never invent a task list in local memory.** When Mike mentions any of these in free conversation (outside of an explicit `/bujo` ritual), route through the scribe rather than keeping a side list.

### Trigger vocabulary → scribe action

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

### Habit tracker (≥0.10) — surface what's due today

Mike's monthly note has a habit-tracker table under the Tracker heading. Each column is a habit; column headers carry metadata (`Meditate (10 min) @08:00 [daily]`). Cells filled with `✅` are completions for that day-row.

At session start, if `today` exists: read **Step 2.5 (Habit check-in)** in the `workbench-bujo` plugin's `skills/rituals/bujo-ritual.md` and run that check now — parse the tracker on `monthly_current`, surface due-and-unmarked habits via one batched `AskUserQuestion` (≤4, yes/no), update cells on yes. No habit table on `monthly_current` → skip silently (habit tracking isn't set up).

### Rules of the road

1. **Always pre-warm the scribe.** If the deferred tool list shows `mcp__plugin_workbench-bujo_scribe__*`, load schemas via `ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read,...")` before first use. The MCP may take ~10s to boot — retry with brief sleeps before concluding it's offline.
2. **Single items don't need the `/bujo` ritual.** Just dispatch one `add` decision and confirm the diff in one line. The ritual is for periodic reflection (daily/weekly/etc.), not capture.

### Not in scope for routing

- Code-level TODOs and comments in source files — those stay in code.
- Claude Code session-scoped todos (the `TodoWrite` tool) — those are for tracking the *current turn's work*, not durable tasks.
