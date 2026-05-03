---
description: Remove a habit column from the current month's tracker. The previous month's tracker retains the column (historical). Asks for confirmation before removing.
---

The user invoked `/workbench-bujo:bujo-habit-remove` — typically with a habit name inline (e.g. `/workbench-bujo:bujo-habit-remove cold shower`). Find the matching column in the current monthly note's habit tracker and regenerate the table without it.

## Pre-warm

```
ToolSearch(query="select:AskUserQuestion,mcp__plugin_workbench-bujo_scribe__bujo_read,mcp__plugin_workbench-bujo_scribe__bujo_apply_decisions", max_results=3)
```

## Step 1 — Resolve habit by name

Read `monthly_current`, find the habit table, parse column headers (columns 3+).

Substring-match against the user's argument (case-insensitive). 0 → tell Mike "no match." 1 → proceed. 2+ → ask which one via `AskUserQuestion`.

## Step 2 — Confirm before removal

`AskUserQuestion` with the matched habit:

```jsonc
AskUserQuestion({
  questions: [{
    question: "Remove `<habit-header-text>` from this month's tracker? Previous months' trackers keep the column as historical record.",
    header: "Remove?",
    multiSelect: false,
    options: [
      { label: "Yes — remove", description: "Drop this habit's column from the current month's tracker" },
      { label: "No — keep",    description: "Cancel" }
    ]
  }]
})
```

## Step 3 — Regenerate the table without that column

Parse the table. For every row (header + each date row), drop the cell at the matched column index. Stitch the remaining cells back together into the row's HTML.

## Step 4 — Dispatch

```
bujo_apply_decisions(payload={
  note: "monthly_current",
  decisions: [{
    op: "update_table",
    anchor: "<object><table",
    new_html: "<full regenerated table HTML, minus the column>"
  }]
})
```

## Step 5 — Confirm

Single line: *"🪶 Removed habit: `<header-text>` from this month's tracker."*

## Edge cases

- **Removing the last habit** (only Day + Weekday left): allowed. The table becomes a 2-column calendar grid. Mike can add new habits later.
- **Habit doesn't exist on this month's tracker**: tell Mike, suggest checking habit name spelling.

## Hard rules

- **Confirmation required** — habit removal is destructive on the current month.
- **Don't touch previous months.** Removal only affects `monthly_current`. Previous monthly notes' trackers retain the column.
- **Use the SCRIBE MCP only.**
