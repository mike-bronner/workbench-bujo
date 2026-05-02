---
description: Add a habit to the current month's tracker. Walks an interactive interview (name → quantity? → time → cadence) via AskUserQuestion, then adds the column to the monthly note's habit-tracker table.
---

The user invoked `/workbench-bujo:bujo-habit-add` — possibly with a name inline (e.g. `/workbench-bujo:bujo-habit-add Meditate`), possibly bare. Walk an interactive interview via `AskUserQuestion`, construct the canonical column header text, then add the column to the monthly note's habit tracker.

## Pre-warm

Load deferred tool schemas at the very start:

```
ToolSearch(query="select:AskUserQuestion,mcp__plugin_workbench-bujo_scribe__bujo_read,mcp__plugin_workbench-bujo_scribe__bujo_apply_decisions", max_results=3)
```

## Step 1 — Collect the habit definition

Use `AskUserQuestion` (multiple questions in one call where natural). If the user typed a name with the slash command, prefill it as Question 1's "Other" and skip question 1.

### Question 1: Name

Open text. *"What's the habit?"* — anything Mike provides (e.g., "Meditate", "Bible Study", "Cold shower").

### Question 2: Quantitative target?

```jsonc
AskUserQuestion({
  questions: [{
    question: "Is this a count-something habit (minutes, glasses, reps), or just yes/no?",
    header: "Type",
    multiSelect: false,
    options: [
      { label: "Yes/no — boolean", description: "Did I do it today?" },
      { label: "Count or amount",   description: "Tracks a number — e.g., 10 min, 8 glasses, 30 push-ups" }
    ]
  }]
})
```

If "count" → follow up: *"How much, with what unit?"* (free text → parsed as `<n> <unit>`, e.g., `10 min`, `8 glasses`).

### Question 3: Time of day

```jsonc
AskUserQuestion({
  questions: [{
    question: "When during the day?",
    header: "Time",
    multiSelect: false,
    options: [
      { label: "Anytime",   description: "No specific window" },
      { label: "Morning",   description: "Before noon" },
      { label: "Afternoon", description: "Noon to evening" },
      { label: "Evening",   description: "After dinner" },
      { label: "Specific time…", description: "I'll give you HH:MM" }
    ]
  }]
})
```

If "Specific time…" → follow up for `HH:MM` (24h). Validate format (`/^[0-2]\d:[0-5]\d$/`).

### Question 4: Cadence

```jsonc
AskUserQuestion({
  questions: [{
    question: "How often?",
    header: "Cadence",
    multiSelect: false,
    options: [
      { label: "Every day",        description: "daily" },
      { label: "Weekdays only",    description: "Mon–Fri" },
      { label: "Mon/Wed/Fri",      description: "mwf" },
      { label: "Tue/Thu",          description: "tth" },
      { label: "Every N days…",    description: "I'll give you a number" },
      { label: "N times per week…", description: "I'll give you a number" }
    ]
  }]
})
```

For "Every N days…" → follow up: *"Every how many days?"* → produces `every-3-days` etc.
For "N times per week…" → *"How many times per week?"* → produces `3x-week` etc.

## Step 2 — Construct the column header text

Format: `<name> [(qty unit)] [@time] [<cadence>]`

Rules:
- Name first.
- If quantitative: append `(<n> <unit>)` after name.
- If time: append `@HH:MM` (or `@morning`/`@afternoon`/`@evening`; omit for `@anytime`).
- Append `[<cadence>]` (omit for `[daily]` since it's the default — keeps headers clean for the common case).

Examples:
- `Bible Study` (daily, no quantity, anytime)
- `Meditate (10 min) @08:00 [daily]`
- `Strength @17:00 [mwf]`
- `Cold shower [every-3-days]`
- `Water (8 glasses)` (daily quantitative, anytime)

Confirm the constructed header in chat (one line) — Mike sees what's about to be added before dispatch.

## Step 3 — Read the monthly note

```
bujo_read(notes: ["monthly_current"])
```

Find the existing habit tracker:
1. Look for `lines[]` entry with `kind: "heading"` and `text: "Tracker"`.
2. The next `UnrecognizedLine` (filtered out of `lines[]` but visible in raw response — fall back to scanning the raw `content` for `<object><table` if needed).

If the Tracker heading doesn't exist yet, scaffold a minimal one (see "Bootstrap" below).
If the table doesn't exist yet, generate the initial empty table for the current month (see "Initial table" below).

## Step 4 — Regenerate the table HTML with the new column added

You're going to read the existing table's raw HTML, parse it, and emit a new version with the new column inserted as the rightmost column.

### Cell HTML formats

```html
<!-- Header cell (habit) -->
<td valign="top" style="border-style: solid; border-width: 1.0px 1.0px 1.0px 1.0px; border-color: #ccc; padding: 3.0px 5.0px 3.0px 5.0px; min-width: 70px"><div><b><HEADER-TEXT-ESCAPED></b></div></td>

<!-- Empty cell (past or future days) -->
<td valign="top" style="border-style: solid; border-width: 1.0px 1.0px 1.0px 1.0px; border-color: #ccc; padding: 3.0px 5.0px 3.0px 5.0px; min-width: 70px"><div><br></div></td>
```

For mid-month adds, ALL existing date rows get an empty cell appended (past days too) — the table stays rectangular.

### Wrapper

```html
<div><object><table cellspacing="0" cellpadding="0" style="border-collapse: collapse; direction: ltr">
<tbody>
<HEADER-ROW>
<DATE-ROW-1>
<DATE-ROW-2>
…
<DATE-ROW-N>
</tbody>
</table></object><br></div>
```

## Step 5 — Dispatch the update

```
bujo_apply_decisions(payload={
  note: "monthly_current",
  decisions: [{
    op: "update_unrecognized",
    anchor: "<object><table",
    new_html: "<the regenerated table HTML>"
  }]
})
```

If the response includes `unmatched` for this op, surface it to Mike — it likely means the Tracker section / table needs scaffolding (see "Bootstrap" / "Initial table" below).

## Step 6 — Confirm

Single line: *"🪶 Added habit: `<header text>`"*

## Bootstrap (if Tracker section absent)

If the monthly note has no Tracker heading:
1. Add the heading + description body line via `bujo_apply_decisions:add` with appropriate signifier (or scaffold if needed).
2. Then proceed to the table.

For v1: if the Tracker section is missing on the current monthly note, ask Mike: *"No habit tracker on this month's note yet. Add a Tracker section?"* Yes → scaffold the heading + description + initial table. No → abort the habit-add.

## Initial table generation (no table yet)

If Tracker section exists but table doesn't, generate the full table for the current month:
1. Compute current month's day count (28-31).
2. Compute weekday for each day-of-month using a date library or simple math.
3. Header row: `Day | Weekday | <new habit header>`
4. Date rows: one per day-of-month, with day number, 2-letter weekday code, and one empty cell for the new habit.

Then dispatch `bujo_apply_decisions:add` with section "" or anchored after the Tracker heading. Since `add` works on `BujoLine` only, use a fallback approach:
- Scaffold the table as part of a fresh `bujo_scaffold` call with `mode: merge`.

For v1, simplest: if no table exists, fall back to manually creating it via `bujo_apply_decisions:add` with a sentinel BujoLine + an immediate `update_unrecognized` to replace it. Or: punt to scribe-side support for `add_unrecognized` in a later release.

**v1 simplification:** if the table doesn't exist, surface to Mike: *"There's no habit tracker table on this month's note yet. Create one in Apple Notes (Tracker → Insert → Table with columns Day / Weekday) then re-run /bujo-habit-add."* Defer initial-table-generation to v2 once `add_unrecognized` exists.

## Hard rules

- **Never** modify rows/columns Mike didn't intend. Habit-add only adds a new rightmost column.
- **Confirm before dispatch** if Mike's metadata choices produced an unusual header (e.g., empty cadence, malformed time) — show the constructed header for sanity check before writing.
- **Use the SCRIBE MCP only.** No direct Apple Notes calls.
- **Idempotent on no-op:** if the column header text already exists in the current table, refuse to add duplicate. Tell Mike *"Habit already on the tracker."*
