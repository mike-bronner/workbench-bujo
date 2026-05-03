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
2. The next `lines[]` entry with `kind: "table"` is the habit tracker. Its `raw_html` field carries the full table HTML for parsing.

If the Tracker heading doesn't exist yet, scaffold a minimal one (see "Bootstrap" below).
If the heading exists but the table doesn't, scaffold the initial empty table (see "Initial table" below).

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

## Step 5 — Dispatch the update (or add)

If a table already exists, replace it:

```
bujo_apply_decisions(payload={
  note: "monthly_current",
  decisions: [{
    op: "update_table",
    anchor: "<object><table",
    new_html: "<the regenerated table HTML>"
  }]
})
```

If the table doesn't exist yet (no TableLine after the Tracker heading), scaffold it via `add_table` anchored on the Tracker heading. See "Initial table" below.

## Step 6 — Confirm

Single line: *"🪶 Added habit: `<header text>`"*

## Bootstrap (if Tracker section absent)

If the monthly note has no Tracker heading, the MCP creates everything for Mike — no manual setup. Confirm with `AskUserQuestion`:

```jsonc
AskUserQuestion({
  questions: [{
    question: "No Tracker section on this month's note. Add one with the new habit?",
    header: "Tracker",
    multiSelect: false,
    options: [
      { label: "Yes — create Tracker + table", description: "Scaffolds heading, description, and initial habit table" },
      { label: "No — cancel",                  description: "Abort habit-add" }
    ]
  }]
})
```

On Yes, scaffold both the heading and the initial table:

1. Use `bujo_scaffold` (mode: merge) to add the Tracker heading + a body description line, OR add them via individual `apply_decisions` ops if scaffold isn't suited.
2. Then dispatch `add_table` (see below) anchored on the new Tracker heading.

## Initial table generation (no table yet)

When the Tracker heading exists but no table follows, scaffold the table directly via `add_table`:

1. Compute current month's day count (28, 29, 30, or 31) using today's date in the configured timezone.
2. For each day-of-month, compute the 2-letter weekday code (`Mo`/`Tu`/`We`/`Th`/`Fr`/`Sa`/`Su`).
3. Generate the full table HTML using the Apple Notes table format:

```html
<div><object><table cellspacing="0" cellpadding="0" style="border-collapse: collapse; direction: ltr">
<tbody>
<tr>
  <td valign="top" style="border-style: solid; border-width: 1.0px 1.0px 1.0px 1.0px; border-color: #ccc; padding: 3.0px 5.0px 3.0px 5.0px; min-width: 70px"><div><b>Day</b></div></td>
  <td valign="top" style="..."><div><b>Weekday</b></div></td>
  <td valign="top" style="..."><div><b><HABIT-HEADER></b></div></td>
</tr>
<tr>
  <td valign="top" style="..."><div>1</div></td>
  <td valign="top" style="..."><div>We</div></td>
  <td valign="top" style="..."><div><br></div></td>
</tr>
<!-- repeat for days 2..N -->
</tbody>
</table></object><br></div>
```

4. Dispatch:

```jsonc
bujo_apply_decisions({
  note: "monthly_current",
  decisions: [{
    op: "add_table",
    after_anchor: "Tracker",
    new_html: "<full table HTML>"
  }]
})
```

`add_table` matches the Tracker heading by text substring and inserts the new TableLine immediately after it. **The MCP creates the table — Mike never has to set it up manually in Apple Notes.**

If `after_anchor: "Tracker"` returns NOT_FOUND (no heading) or AMBIGUOUS_BULLET (multiple match), surface the error or scaffold the heading first.

## Hard rules

- **Never** modify rows/columns Mike didn't intend. Habit-add only adds a new rightmost column.
- **Confirm before dispatch** if Mike's metadata choices produced an unusual header (e.g., empty cadence, malformed time) — show the constructed header for sanity check before writing.
- **Use the SCRIBE MCP only.** No direct Apple Notes calls.
- **Idempotent on no-op:** if the column header text already exists in the current table, refuse to add duplicate. Tell Mike *"Habit already on the tracker."*
