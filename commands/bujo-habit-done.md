---
description: Mark a habit as done for today. Updates the cell in the current monthly note's habit tracker. For quantitative habits, asks "how much?" before dispatching.
---

The user invoked `/workbench-bujo:bujo-habit-done` — typically with a habit name inline (e.g. `/workbench-bujo:bujo-habit-done meditate`). Find the matching column in the current monthly note's habit tracker, set today's cell to ✅ (or ✅ <n> for quantitative), and dispatch.

## Pre-warm

```
ToolSearch(query="select:AskUserQuestion,mcp__plugin_workbench-bujo_scribe__bujo_read,mcp__plugin_workbench-bujo_scribe__bujo_apply_decisions", max_results=3)
```

## Step 1 — Resolve habit by name

Read `monthly_current` and identify the habit table (see bujo-habit-add for anchoring rules).

Parse the table's header row to extract column names. The first two columns are always `Day` and `Weekday`; columns 3+ are habits.

Substring-match the user's argument against habit column header texts (case-insensitive). If:
- 0 matches → tell Mike *"No habit matching '<arg>' on this month's tracker. Available: <list>."*
- 1 match → proceed.
- 2+ matches → ask via `AskUserQuestion` which one.

## Step 2 — Quantitative? Ask for amount.

Parse the matched column's header text. If it contains `(<n> <unit>)` (regex `\(\d+\s+\w+\)` after the name), it's quantitative.

Quantitative → ask: *"How much today?"* Free-text answer parsed as a number. Validate it's a positive integer (or float for some units like minutes).

Boolean → skip directly to Step 3.

## Step 3 — Compute today's row

Today's day-of-month → row index in the table.

Compute today's date in the user's configured timezone (read config or rules.timezone). Day-of-month = current day (1-31).

If today is in a different month than the monthly_current note (e.g., user runs this on May 1 but monthly_current resolves to April), abort and tell Mike: *"`monthly_current` doesn't include today's date. Run /bujo-habit-done after the monthly ritual scaffolds the new month."* (This shouldn't happen if the monthly ritual ran on the 1st.)

## Step 4 — Construct cell HTML

Boolean cell:
```html
<div><font face=".AppleColorEmojiUI">✅</font></div>
```

Quantitative cell:
```html
<div><font face=".AppleColorEmojiUI">✅</font>&nbsp;<n></div>
```

Replace `<n>` with the user's reported number.

## Step 5 — Regenerate the table HTML

Find today's row in the table (row index = day-of-month). Replace the cell at the matched habit's column index with the new cell HTML. Leave all other cells unchanged.

## Step 6 — Dispatch

```
bujo_apply_decisions(payload={
  note: "monthly_current",
  decisions: [{
    op: "update_unrecognized",
    anchor: "<object><table",
    new_html: "<full regenerated table HTML>"
  }]
})
```

## Step 7 — Confirm

Single line:
- Boolean: *"🌱 Done: `<habit name>` ✅"*
- Quantitative: *"🌱 Done: `<habit name>` ✅ <n>"*

## Edge cases

- **Cell already filled:** if today's cell already has a `✅` (Mike already did it), tell him *"Already marked done today."* — don't re-dispatch.
- **Cadence mismatch:** if the habit's cadence says today isn't a "due" day (e.g., `[mwf]` and today is Tuesday), confirm: *"This habit is normally Mon/Wed/Fri — log anyway?"* yes/no via AskUserQuestion. If yes, dispatch; if no, abort.
- **No tracker table on monthly_current:** tell Mike to add a habit first via `/bujo-habit-add`.

## Hard rules

- **Only update today's cell** for the matched habit. Never touch other rows or columns.
- **Use the SCRIBE MCP only.**
- **The cell `<td>` style attribute stays verbatim** — read the existing cell's style, don't regenerate it. Only the inner `<div>` content changes.
