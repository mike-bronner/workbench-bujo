# 🖋️ bujo-scribe — Contract

The scribe is a sub-agent dispatched by Hobbes during BuJo rituals. It owns every Apple Notes read/write, every formatting decision, every carry-over and migration. Hobbes owns orchestration and interactivity with Mike; the scribe owns the notebook.

This document defines the **contract between Hobbes and the scribe** — the verbs, inputs, outputs, and invariants. If a ritual skill needs the scribe to do something outside this vocabulary, **extend the contract first** — don't have the skill invent a new verb inline.

---

## Invariants (apply to every verb)

1. **Index-first.** Every mutation re-reads `📓 Journal Index` before proceeding. No cached rules. If the index is missing → error `INDEX_MISSING`.
2. **Folder discipline.** All BuJo notes live in the `📓 Journal` folder (notebook emoji included). Every `add_note` passes `folder: "📓 Journal"`. If the folder is missing → error `FOLDER_MISSING`.
3. **Parallel-edit guard.** Every mutation does `get_note_content` immediately before `update_note_content`. No stale writes.
4. **Verified diffs.** Every mutation verb returns a structured diff — Hobbes can present it to Mike, not a black-box "ok".
5. **No improvisation.** If a bullet doesn't match an index rule, the scribe returns a `RULE_VIOLATION` warning — it does not guess.
6. **Tz-aware.** Dates computed in `America/Phoenix` unless overridden.

---

## Note identifiers

The scribe accepts either a **canonical slug** or an **explicit title string**. Slugs are resolved against today's date.

| Slug | Resolves to |
|---|---|
| `index` | `📓 Journal Index` |
| `daily_data` | `📅 Daily Data` |
| `future_log` | `Future Log` |
| `goals` | `Goals` |
| `second_brain` | `🧠 Claude's Second Brain` |
| `today` | `YYYY-MM-DD — Weekday` for today |
| `yesterday` | `YYYY-MM-DD — Weekday` for yesterday |
| `daily:YYYY-MM-DD` | specific daily entry |
| `monthly_current` | current month's log |
| `monthly_prev` | previous month's log |
| `weekly_current` | current week's log |
| `yearly_current` | current year's log |
| `collection:<name>` | arbitrary named collection |

Explicit titles (e.g. `"2026-04-19 — Sunday"`) are passed through verbatim.

---

## Verbs

### 1. `scribe.read`

**Purpose:** fetch notes for a ritual's context packet. Read-only.

**Input:**
```yaml
notes: [<identifier>, ...]   # required
```

**Output:**
```yaml
packet:
  <identifier>:
    title: "<actual note title>"
    exists: true | false
    content: "<raw note body>" | null
    retrieved_at: "<ISO timestamp>"
```

**Behavior:**
- Always implicitly reads `index` (adds it to packet if not requested).
- Parallel fetches where the MCP permits.
- Missing notes return `exists: false, content: null` — not an error.

---

### 2. `scribe.scaffold`

**Purpose:** create a new ritual entry, or merge new bullets into an existing one.

**Input:**
```yaml
target: <identifier>
ritual: daily | weekly | monthly | yearly
mode: create | merge              # create fails if note exists
sections:
  - name: "Migrated from yesterday"
    bullets:
      - signifier: task | event | note | research
        text: "..."
        priority: "*" | "!" | null
        owner: "<name>" | null       # family-calendar owner if relevant
        source: "<provenance>" | null
```

**Output:**
```yaml
note_id: "<title or Apple Notes id>"
created: true | false
diff: <see Diff format below>
warnings: [ { code, bullet, detail } ]
```

**Behavior:**
- Reads `index` first; applies exact template, writing order, signifier selection, HTML conventions, prefix alignment per index rules.
- `mode: merge` reads fresh, computes diff, writes back.
- `mode: create` uses the index template for `ritual`.
- Bullets that violate index rules are skipped and returned in `warnings` — **never silently normalized**.

---

### 3. `scribe.apply-decisions`

**Purpose:** apply mutations to an existing note — the workhorse for reflection, carry-over, and in-place edits.

**Input:**
```yaml
note: <identifier>
decisions:
  - op: complete       # mark task done per index (e.g. X)
    bullet: "<text match or anchor>"

  - op: migrate        # carry forward with >
    bullet: "..."
    target: today | future_log | monthly_current | weekly_current | <identifier>

  - op: schedule       # schedule forward with <
    bullet: "..."
    date: "YYYY-MM-DD"

  - op: drop           # strike through
    bullet: "..."

  - op: add            # append new bullet to a section
    section: "<section name>"
    bullet: { signifier, text, priority?, owner?, source? }

  - op: update         # edit text in place
    bullet: "..."
    new_text: "..."

  - op: reorder
    section: "<section name>"
    order: ["<bullet text>", ...]
```

**Output:**
```yaml
note_id: "<title>"
diff: <see Diff format below>
unmatched: [ { decision, reason } ]    # decisions that couldn't apply
cross_note_effects:                     # e.g. migrate writes to target too
  - note: "<title>"
    diff: <diff>
```

**Behavior:**
- Reads `index`, then reads `note` fresh, then writes.
- `migrate` mutates BOTH notes (strike/mark `>` in source, append to target) — both appear in `cross_note_effects` and the main `diff`.
- Ambiguous matches (bullet text matches >1 bullet) → `AMBIGUOUS_BULLET`, added to `unmatched`. Not applied.
- Missing bullet matches → `NOT_FOUND`, added to `unmatched`. Not applied.

---

### 4. `scribe.scan`

**Purpose:** find open or due items across notes. Read-only.

**Input:**
```yaml
scope: [<identifier>, ...]
filter:
  status: open | due_today | overdue | surfaces_today
  type: task | event | note           # optional
  date: "YYYY-MM-DD"                  # optional, defaults today
```

**Output:**
```yaml
items:
  - note: "<title>"
    section: "<section name>"
    signifier: task | event | note
    text: "..."
    anchor: "<stable reference for apply-decisions>"
    due: "YYYY-MM-DD" | null
```

**Behavior:**
- Read-only.
- Uses index rules to classify what "open" means.
- `anchor` is a string Hobbes can pass back in a subsequent `apply-decisions` as the `bullet` field — stable across re-reads.

---

### 5. `scribe.summarize`

**Purpose:** produce a formatted summary block (morning summary, weekly retro, etc.). Pure transform — no tool calls.

**Input:**
```yaml
kind: daily_morning | weekly_retro | monthly_retro | yearly_retro
packet:                 # whatever data the summary needs
  yesterday_stats: { completed, migrated, dropped }
  today_schedule: [...]
  migrated: [...]
  future_surfaced: [...]
  # etc. — varies by kind
format: display | note  # display = shown to Mike; note = written into a note
```

**Output:**
```yaml
block: "<formatted string>"
stats: { ...underlying numbers... }
```

**Behavior:**
- Uses the summary template from the index for `kind`.
- No Apple Notes I/O.

---

## Diff format (shared across mutation verbs)

```yaml
added:
  - section: "<name>"
    bullet: "<rendered text>"
changed:
  - before: "<rendered text>"
    after: "<rendered text>"
removed:
  - bullet: "<rendered text>"
moved:
  - from: "<note>#<section>"
    to: "<note>#<section>"
    bullet: "<rendered text>"
```

Empty arrays omitted.

---

## Error codes

| Code | Meaning |
|---|---|
| `INDEX_MISSING` | `📓 Journal Index` not found |
| `FOLDER_MISSING` | `📓 Journal` folder not found |
| `NOTE_NOT_FOUND` | target note doesn't exist (for non-create ops) |
| `RULE_VIOLATION` | input bullet doesn't match any index rule |
| `AMBIGUOUS_BULLET` | decision's bullet matches >1 candidate in target |
| `NOT_FOUND` | decision's bullet doesn't match any candidate |
| `STALE_WRITE_DETECTED` | note changed between read and write — scribe retries once, then errors |

Errors are structured:
```yaml
error:
  code: <code>
  detail: "<human description>"
  context: { ... }     # verb-specific context
```

---

## What the scribe does NOT do

- **No interactivity.** Does not ask Mike questions. If a decision is ambiguous, it returns `unmatched`; Hobbes resolves with Mike and re-dispatches.
- **No ritual orchestration.** Does not decide whether it's a Sunday. Hobbes decides; scribe executes what's asked.
- **No rule invention.** If the index doesn't specify it, the scribe does not choose a default. Returns `RULE_VIOLATION` instead.
- **No summarization of user reflection.** Mike's reflections in Step 4 / Step 8 are for Hobbes to capture. The scribe only applies the resulting decisions.

---

## Open questions (to resolve before building)

- [ ] Does `apply-decisions` need a `dry_run: true` option, so Hobbes can preview the diff before committing? (Probably yes — useful for Step 4 batch applies.)
- [ ] Should `scaffold` accept a `prepend_to_section` hint, or is section order always index-determined?
- [ ] Anchor format for `scan` → `apply-decisions` round-trip. Proposal: `"<section_name>::<first_40_chars_of_bullet>"`. Good enough?
- [ ] Does the `📓 Journal Index` currently cover every rule the scribe will need? (Step 2 of the build plan — audit the index before we trust it.)
