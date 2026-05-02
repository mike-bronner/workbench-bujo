---
description: List the habits on this month's tracker with cadence, time, and current progress (completion rate, streak). Read-only — renders to chat, doesn't modify the note.
---

The user invoked `/workbench-bujo:bujo-habit-list`. Read the current monthly note's habit tracker, parse the table, and render a tight summary in chat.

## Pre-warm

```
ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read", max_results=1)
```

## Step 1 — Read the monthly note

```
bujo_read(notes: ["monthly_current"])
```

Find the habit table (anchor: `<object><table` in raw_html of an UnrecognizedLine; or fall through to scanning content if older read shape).

If no Tracker section or table → tell Mike: *"No habit tracker on this month's note yet. Use /bujo-habit-add to start one."*

## Step 2 — Parse the table

For each habit column (columns 3+):

1. Extract column header text → the canonical habit name (e.g., `Meditate (10 min) @08:00 [daily]`).
2. Parse metadata from the header text:
   - Quantity: `\((\d+(?:\.\d+)?)\s+(\w+)\)`
   - Time: `@(\d{2}:\d{2}|morning|afternoon|evening|anytime)`
   - Cadence: `\[([\w-]+)\]`
   - Name: everything else (with metadata markers stripped)
3. Walk down the column counting cells:
   - **Empty cells** (`<br>`, `<div></div>`) → not done that day.
   - **Filled cells** with `✅` → done. Capture the number after `✅` if quantitative.
4. Compute `done_count` and `streak_current` (consecutive recent completions ending today or yesterday).

## Step 3 — Compute cadence stats

Parse the cadence:
- `daily` → days due = total days in month (1-N).
- `weekdays` → days due = Mon–Fri count.
- `weekends` → days due = Sat/Sun count.
- Day codes (`mwf`, `tth`, etc.) → compute matching days.
- `every-N-days` → estimate based on month start; precise math: floor((days_in_month + N - 1) / N).
- `Nx-week` → N × 4 (approximation for a 4-week month).

`due_count` = number of days the habit was supposed to be done by today (within the cadence and current month-to-date).

`completion_rate` = `done_count / due_count` for the current month.

## Step 4 — Render the summary

Format as a compact ASCII table in chat (do NOT write to the note):

```
🌱 Habits — May 2026

Habit                          Cadence       Time      Done   Streak
─────────────────────────────  ────────────  ────────  ─────  ──────
Bible Study                    daily         anytime   2/2    2
Meditate (10 min)              daily         08:00     1/2    1
Strength                       mwf           17:00     0/0    0
Cold shower                    every-3-days  anytime   1/1    1
```

Column widths can adapt to content. Use a monospace block (single triple-backtick code block) so it renders correctly.

## Step 5 — End

Stop. Don't ask follow-ups; this is a status read.

## Hard rules

- **Read-only.** No `apply_decisions` calls.
- **No fabrication.** If a habit has no completions, show `0/N`. Don't infer or add data.
- **Today's date in user's configured timezone** when computing "due as of today."
