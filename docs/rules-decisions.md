# 📐 BuJo Rules — Gap Decisions

Working log of the decisions Mike and Hobbes make while closing the 7 audit gaps. Once all gaps are resolved, these decisions become the default `rules.yaml` shipped with `bujo-scribe-mcp`.

---

## Gap 1 — Dropped-task signifier ✅

**Decision:** Strikethrough the whole line (Ryder Carroll canonical).

**Rendering:**
```html
<div><font face="Menlo-Regular"><tt><s>• Call insurance about the claim</s></tt></font></div>
```

**Notes:**
- Original signifier and text preserved inside `<s>`
- Parser detects `<s>…</s>` within a BuJo line as the "dropped" state
- MCP needs to verify Apple Notes renders `<s>` cleanly inside `<font><tt>…</tt></font>` — fix if it doesn't

---

## Gap 2 — `<` scheduled signifier + semantics ✅

**Decision:** `<` replaces the base signifier on the daily entry, AND the scribe auto-creates a Future Log entry. Cross-note effect — same contract pattern as `migrate`.

**Guard (hard rule):** A `schedule` decision requires a **future date** (strictly greater than today in the configured timezone).
- Date is today, in the past, or missing → decision is **rejected**, returned in `unmatched` with reason `SCHEDULE_NEEDS_FUTURE_DATE`
- Rejected decisions **do not mutate** — the task remains as an open task (`•`), not marked with `<`

**Rendering on the daily:**
```html
<div><font face="Menlo-Regular"><tt>< Call dentist</tt></font></div>
```

**Future Log entry** (populated as cross-note effect):
- Contains the scheduled date, task text, and provenance back to the originating daily.
- Exact Future Log row format — TBD when we resolve the Future Log schema gap.

**Notes:**
- Matches the `>` migrated pattern (signifier replacement)
- Decision schema: `{ op: "schedule", bullet: "<text>", date: "YYYY-MM-DD" }`
- Validation happens before any mutation — the scribe refuses to write `<` unless a valid future date is in hand

---

## Gap 3 — Non-breaking space encoding ✅

**Decision:** Use the HTML entity **`&nbsp;`** (literal 6-character ASCII string). This is **Apple-Notes-specific** — other NBSP encodings (literal U+00A0, figure space, etc.) break when round-tripped through the Apple Notes MCP.

**Architectural consequence:** NBSP handling lives in the **backend layer**, not the rules layer.

- **Rules layer (backend-agnostic):** "regular items begin with a single non-breaking space glyph"
- **Apple Notes backend (render):** emit literal `&nbsp;` in the note HTML
- **Apple Notes backend (parse):** recognize `&nbsp;` in raw HTML, normalize to an internal NBSP token
- **Future backends** (markdown, Obsidian, etc.): choose their own NBSP encoding — U+00A0, two ASCII spaces, whatever survives the round-trip

**Implementation placement:** constants / helpers in `backends/apple_notes.py`. The parser and renderer in the Apple Notes backend translate `&nbsp;` ↔ internal NBSP token on the way in and out.

---

## Gap 4 — Sub-item nesting ✅

**Decision:** Leading `&nbsp;` per depth level inside the existing flat `<div>` structure — the BuJo daily log stays a single continuous block. HTML lists with custom BuJo decorators don't work in Apple Notes (limited HTML subset, signifiers are content characters not list markers, and `<ul>` styling doesn't survive round-trip).

**Parameters:**
- **Indent unit:** `&nbsp;&nbsp;` (2 NBSPs) per depth level
- **Max depth:** 2 levels below top (depths 0, 1, 2 — three total)
- **Signifier:** `-` at the start of every sub-item (after the indent), always treated as a note
- **Type inheritance:** sub-items inherit their parent's type (task/event/note)

**Rendering:**
```html
<div><font face="Menlo-Regular"><tt>• Parent task with complex detail</tt></font></div>
<div><font face="Menlo-Regular"><tt>&nbsp;&nbsp;- Sub-note under the parent</tt></font></div>
<div><font face="Menlo-Regular"><tt>&nbsp;&nbsp;&nbsp;&nbsp;- Sub-sub-note</tt></font></div>
```

**Parser:** count leading `&nbsp;` pairs to derive depth. `(count of leading &nbsp;) / 2 = depth`. If depth > max_depth → `RULE_VIOLATION` warning.

---

## Gap 5 — Weekly/Monthly/Yearly note HTML format ✅

**Decision:** All tier notes — daily, weekly, monthly, yearly — are a **single continuous monospace BuJo block**. No section headers, no categorized segments. Same structure as the daily log.

**⚠️ This OVERRIDES the existing index content.** The `📓 Journal Index` currently documents "Summary-note section layouts" listing sections (Completed, Open TODOs, Insights, Goals, Future Log, Reflections, etc.). **That guidance is wrong — it describes a drift state Mike has been actively trying to fix.** When we render the authoritative rules-as-index note from the MCP, this section gets deleted.

**Rendering:** identical to daily format.
```html
<div><font face="Menlo-Regular"><tt>× Ship the MCP scaffold</tt></font></div>
<div><font face="Menlo-Regular"><tt>!— Parser pressure-tests the rules better than design docs</tt></font></div>
<div><font face="Menlo-Regular"><tt>• Finish Apple Notes backend</tt></font></div>
<div><font face="Menlo-Regular"><tt>> Revisit scribe anchor format next week</tt></font></div>
```

**How content is organized without sections:** BuJo signifiers carry the semantics, not headers.
- Completed items are `×` lines
- Open tasks are `•` lines (carried forward from dailies via carry-forward rules)
- Insights are `!—` lines
- Migrated items are `>` lines
- Scheduled items are `<` lines
- Events are `○` lines
- Notes / reflections are `—` lines (or `!—` if they're genuine insights)

**Implication for carry-forward:** the carry-forward rules (what gets pulled into weekly from daily, etc.) still apply — but rolled-up content is **inlined as BuJo lines**, not sectioned.

**Setup-time ordering** (if applicable to summary notes — TBD): same as daily — events, tasks, notes at scaffold time; chronological/append-only once in progress.

---

## Gap 6 — `📅 Daily Data` note format ✅ (reframed)

**Decision:** The `📅 Daily Data` note is **removed from the system**. The scribe fetches calendar events and reminders **directly** from macOS Calendar and Reminders — no intermediate staging note.

**Why:** the staging-note pattern had two failure modes: (a) tight coupling to whatever upstream automation populated it, and (b) drift between what the automation produced and what the scribe expected. Direct fetching puts the scribe in control of the data pipeline end-to-end.

**Architectural implication — new abstraction:**

Alongside `NotebookBackend`, the MCP now needs a **`DataSourceBackend`** abstraction:

```
NotebookBackend     — read/write notes (Apple Notes today)
DataSourceBackend   — fetch calendar events, reminders, etc. (Apple Calendar + Reminders today)
```

Both are pluggable. Apple Notes backend doesn't grow tentacles into Calendar/Reminders — those get their own implementation.

**Scribe surface changes:**

`bujo.read` gains new identifier slugs served by the DataSource:
- `calendar_today` — today's calendar events, pre-classified as BuJo events (`○`) with family-calendar owner detection applied
- `reminders_due_today` — reminders due today, pre-classified as BuJo tasks (`•`)
- `reminders_overdue` — overdue reminders, pre-classified as BuJo tasks
- `calendar:YYYY-MM-DD` — arbitrary-date calendar fetch

The DataSource layer applies the **task-vs-event + family-calendar owner detection rules** at fetch time — so results come back as BuJo-ready bullets, not raw data.

**HOW the integration is implemented** (EventKit via pyobjc vs `osascript` AppleScript shim vs third-party CLI) — deferred to a dedicated design pass once we finish gap review. Noted as a follow-up in `docs/open-issues.md`.

**No rules-layer impact:** the YAML rules still describe BuJo signifiers and classification logic; the Apple DataSource applies those rules when producing pre-classified bullets.

---

## Gap 7 — Orphan reference in index ✅

**Decision:** Delete the orphan reference. The "Apple Notes HTML Formatting" note in Second Brain was a leftover from a different refactoring/optimization process that never completed — it's dead.

**Replacement:** HTML formatting rules (Apple-Notes-specific) live in the MCP as a sub-section of `rules.yaml`, under a backend-scoped namespace (e.g. `backends.apple_notes.html`). Captured values:

- Heading tag mapping (title 24px, h2 18px, etc.)
- Entity handling (`&nbsp;`, `&lt;`, `&gt;`, `&quot;`)
- Title rule (first `<div>` with 24px span = title)
- Monospace wrapper: `<div><font face="Menlo-Regular"><tt>…</tt></font></div>`
- API limits (max note size, timeout behavior)

**Discovery strategy:** specific values get filled in during the parser/renderer implementation — we write the structure now, fill in exact numbers as round-trips tell us what works.

**When we render the authoritative `📓 Journal Index` note from the MCP, the reference to Second Brain is simply omitted.** Rules live in the MCP, the index note is their rendered view.

---

# 📋 Summary — all 7 gaps resolved

| # | Gap | Decision |
|---|---|---|
| 1 | Dropped-task signifier | `<s>…</s>` strikethrough wrap |
| 2 | `<` scheduled + semantics | Replace base signifier + auto Future Log; requires future date |
| 3 | NBSP encoding | `&nbsp;` HTML entity (Apple-Notes-backend-specific) |
| 4 | Sub-item nesting | 2 `&nbsp;` per level, max depth 2, single `<div>` block |
| 5 | W/M/Y HTML format | Single mono BuJo block — overrides outdated index content |
| 6 | Daily Data note | Removed; direct Calendar/Reminders fetch via new `DataSourceBackend` |
| 7 | Orphan HTML-formatting reference | Delete; rules live in MCP's `rules.yaml` under backend namespace |

**Scope changes from the original build plan:**
- ➕ Add `DataSourceBackend` abstraction alongside `NotebookBackend`
- ➕ Add `rules.yaml` (shipped defaults + user override merge)
- ➕ Apple Notes HTML-formatting constants/values discovered during parser implementation
- ➖ No `📅 Daily Data` note dependency
- ⚠️ The current `📓 Journal Index` in Apple Notes contains outdated guidance (Gap 5 sections, Gap 7 orphan ref) — we do **not** edit it by hand. The MCP regenerates it as a rendered view of `rules.yaml` at scaffold time.

