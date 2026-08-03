---
description: List the habits on this month's tracker with cadence, time, and current progress (completion rate, streak) — rendered as an inline HTML habit dashboard, with a text table as fallback. Read-only — doesn't modify the note.
---

The user invoked `/workbench-bujo:bujo-habit-list`. Read the current monthly note's habit tracker, parse the table, and render a habit-progress dashboard in the conversation.

## Pre-warm

```
ToolSearch(query="select:mcp__plugin_workbench-bujo_scribe__bujo_read,mcp__visualize__read_me,mcp__visualize__show_widget", max_results=3)
```

The `visualize` tools may or may not exist in this session — this command runs interactively in the main conversation, where they usually do, but never assume. Note which of them ToolSearch actually returned; Step 4 branches on it.

## Step 1 — Read the monthly note

```
bujo_read(notes: ["monthly_current"])
```

Find the habit table (anchor: `<object><table` in raw_html of an UnrecognizedLine; or fall through to scanning content if older read shape).

If no Tracker section or table → tell Mike: *"No habit tracker on this month's note yet. Use /bujo-habit-add to start one."* and stop. Don't render an empty dashboard.

## Step 2 — Parse the table

For each habit column (columns 3+):

1. Extract column header text → the canonical habit name (e.g., `Meditate (10 min) @08:00 [daily]`).
2. Parse metadata from the header text:
   - Quantity: `\((\d+(?:\.\d+)?)\s+(\w+)\)`
   - Time: `@(\d{2}:\d{2}|morning|afternoon|evening|anytime)`
   - Cadence: `\[([\w-]+)\]`
   - Name: everything else (with metadata markers stripped)
3. Walk down the column, classifying **every** day-row of the month into exactly one of four states. Keep this per-day list — Step 4's month strip is built from it, and it can't be reconstructed from the totals:
   - `done` — cell carries `✅`. Capture the number after `✅` if quantitative.
   - `missed` — day is on/before today, the cadence made it due, and the cell is empty (`<br>`, `<div></div>`).
   - `off` — day is on/before today but the cadence didn't make it due.
   - `future` — day is after today (due or not — the month hasn't got there yet).
4. Count any cell that is **neither empty nor `✅`-marked** as `unreadable`: it does **not** count as a completion (never infer one), it does not count toward `due_count`, and its day renders in the `off` state. Track `unreadable_count` per habit so Step 4 can surface it — an unparseable cell is reported, never silently swallowed.
5. Compute `done_count` and `streak_current` (consecutive recent completions ending today or yesterday; `off` days don't break a streak, `missed` days do).

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

**If `due_count` is 0** (habit added today, or its first due day hasn't arrived) → the rate is *undefined*, not 0%. Render `—` for the percentage, an empty bar, and the label `not due yet`. Never divide by zero and never show a 0% that reads as a failure Mike didn't earn.

Overall rate for the header = `sum(done_count) / sum(due_count)` across all habits, subject to the same zero guard.

## Step 4 — Render the habit dashboard

**Only if both `mcp__visualize__read_me` and `mcp__visualize__show_widget` came back from the pre-warm.** If either is missing, skip straight to Step 5 — don't retry, don't fabricate a rendered view, and don't describe a visual you didn't render.

### 4a — Read the renderer contract first

```
mcp__visualize__read_me()
```

Call it **every run, before building the HTML** — it defines how `show_widget` wants the payload (full document vs. fragment, size caps, sandbox rules). If its contract conflicts with anything below, **the contract wins for packaging** (how the markup is wrapped and handed over); the spec below still governs **content** (what the view shows and how it looks).

### 4b — Build the document

Emit the template below **verbatim**, substituting only the `{PLACEHOLDER}` tokens and repeating the block marked `repeat per habit`. Don't restyle it, don't reorder sections, don't add or drop panels run to run — the point of a template is that October's dashboard is comparable to March's at a glance. The palette is the same light/dark CSS-custom-property scheme as `docs/ritual-flow.html`, so the plugin's visuals read as one system.

Substitution table:

| Token | Value |
|---|---|
| `{MONTH} {YEAR}` | Month and year of `monthly_current` (e.g. `May 2026`) |
| `{THROUGH}` | Today in the configured timezone, as `Sat 16 May` |
| `{HABIT_COUNT}` | Number of habit columns |
| `{OVERALL}` | Overall rate as a whole number **with the `%` sign** (`68%`), or bare `—` when total due is 0 |
| `{NAME}` | Habit name with metadata markers stripped |
| `{QTY}` | ` (10 min)` — the quantity suffix, or an empty string |
| `{CADENCE}` | Cadence as written in the header (`daily`, `mwf`, `every-3-days`) |
| `{TIME}` | `08:00` / `morning` / `anytime` |
| `{PCT}` | Completion rate as a whole number **with the `%` sign** (`68%`), or bare `—` when `due_count` is 0 — never `—%` |
| `{PCT_WIDTH}` | The same number for the bar width; `0` when the rate is `—` |
| `{TIER}` | `good` when rate ≥ 80, `mid` when 50–79, `low` below 50, `none` when the rate is `—` |
| `{DONE}` / `{DUE}` | Raw counts behind the percentage |
| `{COUNT_LABEL}` | `{DONE}/{DUE} due days`, or `not due yet` when `due_count` is 0 |
| `{STREAK}` | Current streak in days |
| `{STREAK_CLASS}` | `hot` when streak ≥ 1, else `cold` |
| `{DAY_CELLS}` | One `<span>` per day of the month, in order — see below |
| `{WARN}` | Only when `unreadable_count` > 0: `<p class="warn">⚠️ {N} cell(s) couldn't be read — not counted.</p>`. Omit the element entirely otherwise. |

`{DAY_CELLS}` — one span per day-of-month, in calendar order, class by the Step 2 state, plus `today` on today's cell:

```html
<span class="d done" title="3 May — done"></span>
<span class="d miss" title="4 May — missed"></span>
<span class="d off"  title="5 May — not due"></span>
<span class="d fut today" title="16 May — today"></span>
```

State is carried by **shape and fill as well as color** (filled disc / hollow ring / small dot / faint outline), so the strip survives a color-blind read; the numeric percentage and counts are always printed alongside the bar for the same reason.

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Habits — {MONTH} {YEAR}</title>
<style>
  :root {
    --bg: #fafaf7; --panel: #ffffff; --text: #1a1a1f; --muted: #6b6b75;
    --border: #e3e3e0; --track: #eeeeea; --accent: #2f5bdc;
    --good: #2e8c4a; --good-bg: #d5ecdc;
    --mid:  #c77a2a; --mid-bg:  #ffe8cc;
    --low:  #b4453a; --low-bg:  #f6dcd9;
    --off:  #c9c9c4;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14161b; --panel: #1b1e25; --text: #ebebee; --muted: #8f94a0;
      --border: #2a2e38; --track: #2a2e38; --accent: #8cb4ff;
      --good: #9fe0b0; --good-bg: rgba(80, 180, 110, 0.18);
      --mid:  #ffc58a; --mid-bg:  rgba(230, 150, 70, 0.18);
      --low:  #f0a09a; --low-bg:  rgba(200, 80, 70, 0.18);
      --off:  #3a3f4a;
    }
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
    line-height: 1.5;
  }
  main { max-width: 760px; margin: 0 auto; padding: 20px; }
  header { margin-bottom: 16px; }
  header h1 { margin: 0 0 4px; font-size: 19px; font-weight: 600; letter-spacing: -0.01em; }
  header p { margin: 0; color: var(--muted); font-size: 13px; }
  .habit {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; padding: 13px 15px; margin-bottom: 10px;
  }
  .row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .name { font-size: 14.5px; font-weight: 600; }
  .qty { color: var(--muted); font-weight: 500; }
  .chips { display: flex; gap: 6px; flex: 1 1 auto; }
  .chip {
    font-size: 11px; color: var(--muted);
    border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px;
    font-family: "SF Mono", ui-monospace, Menlo, monospace;
  }
  .streak { font-size: 12.5px; font-weight: 600; border-radius: 999px; padding: 1px 9px; }
  .streak.hot { color: var(--good); background: var(--good-bg); }
  .streak.cold { color: var(--muted); background: var(--track); }
  .bar { height: 8px; border-radius: 999px; background: var(--track); margin: 10px 0 6px; overflow: hidden; }
  .fill { height: 100%; border-radius: 999px; }
  .fill.good { background: var(--good); }
  .fill.mid  { background: var(--mid); }
  .fill.low  { background: var(--low); }
  .fill.none { background: transparent; }
  .meta { display: flex; gap: 10px; align-items: baseline; font-size: 12.5px; }
  .pct { font-weight: 600; }
  .count { color: var(--muted); }
  .strip { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 10px; }
  .d { width: 10px; height: 10px; border-radius: 50%; }
  .d.done { background: var(--good); }
  .d.miss { background: transparent; border: 1.5px solid var(--mid); }
  .d.off  { width: 4px; height: 4px; margin: 3px; background: var(--off); }
  .d.fut  { background: transparent; border: 1px dashed var(--off); }
  .d.today { outline: 2px solid var(--accent); outline-offset: 1px; }
  .warn { margin: 8px 0 0; font-size: 12px; color: var(--mid); }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 11.5px; margin-top: 4px; }
  .legend span { display: flex; align-items: center; gap: 5px; }
</style>
</head>
<body>
<main>
  <header>
    <h1>🌱 Habits — {MONTH} {YEAR}</h1>
    <p>Month-to-date through {THROUGH} · {HABIT_COUNT} habits · {OVERALL} overall</p>
  </header>

  <!-- repeat per habit, in tracker column order -->
  <section class="habit">
    <div class="row">
      <div class="name">{NAME}<span class="qty">{QTY}</span></div>
      <div class="chips"><span class="chip">{CADENCE}</span><span class="chip">{TIME}</span></div>
      <div class="streak {STREAK_CLASS}">🔥 {STREAK}d</div>
    </div>
    <div class="bar" role="img" aria-label="{DONE} of {DUE} due days completed">
      <div class="fill {TIER}" style="width: {PCT_WIDTH}%"></div>
    </div>
    <div class="meta"><span class="pct">{PCT}</span><span class="count">{COUNT_LABEL}</span></div>
    <div class="strip">{DAY_CELLS}</div>
    {WARN}
  </section>
  <!-- end repeat -->

  <div class="legend">
    <span><i class="d done"></i> done</span>
    <span><i class="d miss"></i> missed</span>
    <span><i class="d off"></i> not due</span>
    <span><i class="d fut"></i> upcoming</span>
  </div>
</main>
</body>
</html>
```

Keep the document **self-contained and inert**: inline CSS only, no `<script>`, no external fonts, images, or network requests. It's a report, not an app.

### 4c — Render it

```
mcp__visualize__show_widget(<the document, packaged as read_me's contract specifies>)
```

Then add **one** line of text under it — the numbers survive in the transcript even when the widget doesn't:

> *"🌱 4 habits · 68% month-to-date · longest streak 6d (Bible Study)."*

Don't restate the whole table in prose. The dashboard is the report.

## Step 5 — Text fallback (no renderer)

When the `visualize` tools weren't available in Step 4 — or `show_widget` errored — say so in one line (*"Visual renderer unavailable — text summary below."*) and render the same data as a compact ASCII table (do NOT write to the note):

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

## Step 6 — End

Stop. Don't ask follow-ups; this is a status read. The dashboard is a snapshot of the moment it ran — to see fresher numbers, run `/bujo-habit-list` again.

## Hard rules

- **Read-only.** No `apply_decisions` calls. The dashboard never writes back to the note.
- **No fabrication.** If a habit has no completions, show `0/N`. Don't infer or add data. Every number in the visual traces to a parsed cell — no smoothing, no projected rates, no "on track" verdicts the table doesn't support.
- **Fail closed on unreadable input.** A cell that is neither empty nor `✅`-marked is not a completion and not a due day; surface it via `{WARN}` rather than guessing which way it should count.
- **No renderer, no visual.** If the `visualize` tools are absent or erroring, fall through to the Step 5 text table. Never claim to have rendered something you didn't.
- **Today's date in user's configured timezone** when computing "due as of today."
