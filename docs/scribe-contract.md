# 🖋️ bujo-scribe — Contract

The scribe is a sub-agent dispatched by Hobbes during BuJo rituals. It owns every Apple Notes read/write, every formatting decision, every carry-over and migration. Hobbes owns orchestration and interactivity with Mike; the scribe owns the notebook.

This document defines the **contract between Hobbes and the scribe** — the verbs, inputs, outputs, and invariants. If a ritual skill needs the scribe to do something outside this vocabulary, **extend the contract first** — don't have the skill invent a new verb inline.

---

## Invariants (apply to every verb)

1. **Index-first.** Every mutation re-reads `📓 Journal Index` before proceeding. No cached rules. If the index is missing → error `INDEX_MISSING`.
2. **Folder discipline.** All BuJo notes live in the `📓 Journal` folder (notebook emoji included). Every `add_note` passes `folder: "📓 Journal"`. If the folder is missing → error `FOLDER_MISSING`.
3. **Parallel-edit guard.** Every mutation does `get_note_content` immediately before `update_note_content`. No stale writes.
   - **Cross-process serialization (≥0.9.0):** mutations also acquire a `flock(2)`-based advisory lock on `${SCRIBE_RUN_DIR}/mutation.lock` for the duration of the read→mutate→write critical section. This serializes mutations across multiple Claude Code sessions running concurrently — without it, two scribe processes can both pass their local guard while still racing each other to clobber the same Apple Notes record. The lock file lives inside the plugin tree (set by `BUJO_SCRIBE_RUN_DIR`); the OS releases the lock automatically on process exit, so abandoned locks never strand the system, and plugin uninstall removes the file with the rest of the plugin.
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
    lines:                          # parsed lines; null when exists=false
      # Each line has a `kind` discriminator:
      #
      # kind: "bujo" — a BuJo bullet
      - kind: "bujo"
        text: "..."
        anchor: "<stable bullet reference for apply-decisions>"
        signifier: task | event | note | completed | migrated | scheduled | sub_item | <ext>
        prefix: priority | inspiration | explore | <ext> | null
        depth: 0                    # 0 = top-level, 1+ = nested sub-item
        dropped: true | false       # true iff wrapped in <s>…</s>
      # kind: "heading" — Apple Notes Heading or Subheading
      - kind: "heading"
        text: "Tracker"
        anchor: "Tracker"
        heading_level: 2            # 2 = Heading (h2), 3 = Subheading (h3)
      # kind: "body" — paragraph (italic, bold, mixed inline styling)
      - kind: "body"
        text: "Forward plan for April. Calendar logs events…"
        anchor: "Forward plan for April. Calendar logs events…"
    retrieved_at: "<ISO timestamp>"
```

**Behavior:**
- Always implicitly reads `index` (adds it to packet if not requested).
- Parallel fetches where the MCP permits.
- Missing notes return `exists: false, lines: null` — not an error.
- Raw HTML never crosses the wire. The body is parsed via the scribe's parser
  and three line types cross the wire — `kind: "bujo"`, `kind: "heading"`,
  `kind: "body"` (≥0.10). Blank rows and `UnrecognizedLine` (tables, embedded
  objects) are filtered out of `lines[]`. To surface unrecognized content
  for maintenance, use `scribe.scan` with `filter.status: "unrecognized"`.
- The parser is tag-aware (≥0.10): nested `<div>`s inside table cells are
  handled correctly, so the entire `<div><object><table>…</table></object><br></div>`
  block parses as ONE `UnrecognizedLine` rather than fragmenting.
- Apple Notes paragraph styles parse to specific line types (≥0.10):
  - Title (`<h1>` or legacy 24px-span) → extracted into `note.title`
  - Heading (`<h2>` or legacy 18px-span) → `kind: "heading"`, `heading_level: 2`
  - Subheading (`<h3>` or legacy 16px-span) → `kind: "heading"`, `heading_level: 3`
  - Mono (`<tt>` with or without `<font face="Menlo|Courier">` wrapper) →
    `kind: "bujo"` if signifier matches, else `kind: "body"`
  - Anything else (italic body, etc.) → `kind: "body"`
- The renderer emits Apple Notes' native forms (h-tags, `<tt>` without font
  wrapper) regardless of which form the source used. Old notes migrate to
  the new format gradually as the scribe touches them.

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

  - op: undrop         # reverse a previous drop (clear strikethrough)
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

  - op: combine         # fold into another task as nested sub-item
    bullet: "..."        # source bullet on `note`
    target_note: "..."   # note that holds the parent
    parent_bullet: "..." # parent bullet on target_note

  - op: update_unrecognized   # ≥0.10 — replace an UnrecognizedLine's raw HTML in place
    anchor: "<object><table"  # substring that must appear within the line's raw_html
    new_html: "<full replacement HTML for the line>"
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
- `combine` mutates BOTH notes: source bullet gets `>` (migrated) just like `migrate`, and a new `sub_item` (depth=1) is inserted on `target_note` **immediately after** the `parent_bullet`. Atomic — if `target_note` is missing (`NOT_FOUND`) or `parent_bullet` can't be resolved (`PARENT_NOT_FOUND` / `AMBIGUOUS_PARENT`), the source is NOT mutated and the decision lands in `unmatched`.
- `undrop` is the inverse of `drop`: clears the `dropped` flag (removes strikethrough), preserves the signifier and text. If the matched line isn't currently dropped, returns `NOT_DROPPED` — not a silent no-op. Use when a task was dropped in error and needs to come back (e.g., the ritual misinterpreted "combine into X" as "drop").
- `update_unrecognized` (≥0.10) replaces an `UnrecognizedLine`'s `raw_html` in place. Matches by `anchor` substring within the line's raw_html. 0 matches → `NOT_FOUND`; >1 matches → `AMBIGUOUS_BULLET`. Designed for table mutation (the habit tracker on the monthly note); the standard `update` op operates on `BujoLine.text` and can't reach UnrecognizedLine content.
- Ambiguous matches (bullet text matches >1 bullet) → `AMBIGUOUS_BULLET`, added to `unmatched`. Not applied.
- Missing bullet matches → `NOT_FOUND`, added to `unmatched`. Not applied.

---

### 4. `scribe.scan`

**Purpose:** find items across notes by status. Read-only.

**Input:**
```yaml
scope: [<identifier>, ...]
filter:
  status: open | due_today | overdue | surfaces_today | unrecognized
  type: task | event | note           # optional; ignored when status=unrecognized
  date: "YYYY-MM-DD"                  # optional, defaults today
```

**Output:**
```yaml
items:
  - note: "<title>"
    section: "<section name>"
    signifier: task | event | note | unrecognized
    text: "..."
    anchor: "<stable reference for apply-decisions>"
    due: "YYYY-MM-DD" | null
```

**Behavior:**
- Read-only.
- Uses index rules to classify what "open" means.
- `anchor` is a string Hobbes can pass back in a subsequent `apply-decisions` as the `bullet` field — stable across re-reads.
- `status: "unrecognized"` returns every non-BuJo div in scope as a ScanItem
  with `signifier: "unrecognized"`. The `text`/`anchor` is the de-tagged
  HTML of the div, which round-trips into `apply_decisions:remove` for
  legacy/malformed cleanup. The `type` filter is ignored in this mode.
- `status: "due_today"` / `"surfaces_today"` / `"overdue"` (≥0.9.5) match
  by inline `[YYYY-MM-DD]` date, AND additionally exclude lines whose
  signifier is `migrated` or `completed`, or whose `dropped` flag is
  true. `scheduled` (`<`) is INCLUDED — that's the entire point of the
  Future Log's scheduled-then-surface lifecycle. Without this exclusion,
  the daily Future Log surfacing step picks up the same migrated entry
  every morning forever.

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
| `NOT_DROPPED` | `undrop` targeted a line that wasn't dropped — prevents silent no-ops |

Errors are structured:
```yaml
error:
  code: <code>
  detail: "<human description>"
  context: { ... }     # verb-specific context
```

---

## Runtime / launcher (≥0.9.0)

The scribe MCP is invoked through a launcher script (`scribe/bin/launcher.sh`) rather than `uv run` directly. On first launch (or after a wheel-content change), the launcher installs `scribe/wheels/bujo_scribe_mcp-X.Y.Z-py3-none-any.whl` into a stable venv at `scribe/.venv-stable/`, then `exec`s `scribe/.venv-stable/bin/bujo-scribe-mcp` directly. Steady-state cold start drops from ~1-3s (with `uv run`) to ~50ms.

### Cache key: wheel SHA-256, not version (≥0.9.1)

The launcher caches by the wheel's SHA-256 content hash, **not** by version string. The hash is recorded at `${VENV_DIR}/.installed-wheel-hash` after each install; on next launch, the launcher re-hashes the bundled wheel and reinstalls iff the hash differs.

This matters because `build-wheel.yml` rebuilds the wheel on every push to `main` that touches scribe source — without bumping the version. A version-string cache key would say "0.9.1 == 0.9.1, no reinstall" and silently leave users running stale binaries against newer source. Hashing the wheel bytes catches every real change.

Environment contract:

- `BUJO_SCRIBE_RUN_DIR` — directory for plugin-local runtime state (the mutation lock file). The launcher sets this to `scribe/run/`. When unset (e.g., scribe invoked outside the launcher in tests or ad-hoc), the scribe falls back to `${TMPDIR}/bujo-scribe-run`.

Dev escape hatch: set `BUJO_SCRIBE_DEV=1` to bypass the wheel and run from source via `uv run --project`. Use during scribe development to skip the rebuild loop.

All launcher state lives inside the plugin tree (`.venv-stable/`, `run/`, `wheels/`). Plugin uninstall removes the directory and all state with it — no machine-level remnants.

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
