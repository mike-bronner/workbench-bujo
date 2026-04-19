# 📋 Open issues — bujo-scribe-mcp

Deferred decisions and implementation choices tracked here so they aren't lost. Each becomes an actionable task when its blocking verb or layer is implemented.

---

## Calendar / Reminders integration approach

**Gap 6 result:** we're doing direct macOS Calendar + Reminders fetch via a new `DataSourceBackend` abstraction. Deferred: *how* the native integration is implemented.

**Candidates:**
- **EventKit via pyobjc-framework-EventKit** — direct native framework access, first-class permission handling, typed event data. Heaviest dep; best API.
- **`osascript` AppleScript shim** — consistent with Apple Notes backend pattern; no extra Python deps; moderate fragility (AppleScript quirks).
- **Third-party CLI** (e.g. `icalBuddy`) — simplest to shell out to; introduces external install requirement.

**Decision trigger:** when we implement `DataSourceBackend`'s Apple variant. Likely slot in the build order: after `bujo.read` works on notes, before the daily ritual skill is rewritten.

---

## Sub-item indent unit (Gap 4)

Defaults locked as **2 `&nbsp;` per depth level, max depth 2**. Tune if real usage shows misalignment (too narrow → hard to see nesting) or excessive depth (>2 levels needed).

---

## Apple Notes HTML-formatting exact values (Gap 7)

`rules.yaml` under `backends.apple_notes.html` gets filled in during the Apple Notes backend implementation. Values to discover via round-trip testing:
- Exact heading size-to-tag mappings (title 24px, h2 18px, h3 ?px)
- Which entities Apple Notes mangles vs preserves
- Max note size / truncation behavior
- Behavior around `<s>`, `<ul>`, `<pre>`, and other non-trivial tags inside `<tt>` blocks

---

## `📓 Journal Index` re-render

Current note has outdated content (Gap 5 sections table, Gap 7 orphan reference). **Do not hand-edit.** The MCP will regenerate the note from `rules.yaml` at scaffold time (via a new `bujo.render_index` verb or a built-in scaffold step).

**Decision trigger:** after `rules.yaml` schema is stable and `bujo.scaffold` is implemented.

---

## `rules.yaml` schema

The default + user-override pattern needs a concrete schema:
- Root-level sections: `signifiers`, `prefixes`, `classification_rules`, `carry_forward`, `run_order`, `naming`, `backends.<name>.*`
- Merge strategy for user overrides (deep merge? replace-at-key?)
- Validation via pydantic model when the MCP starts up

**Decision trigger:** before implementing any verb — it's the substrate every verb reads.
