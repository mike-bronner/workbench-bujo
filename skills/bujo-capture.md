---
description: Capture a single moment to today's BuJo daily log, mid-conversation, without running a full ritual. Invoked manually via the /workbench-bujo:bujo-capture command, or when Mike explicitly asks to log something.
---

# BuJo Capture — Manual Mid-Day Logging

The manual escape hatch for logging a moment to today's Daily Log outside ritual time. A BuJo Daily Log is meant to be **lived in**, not just retrospectively filled at ritual time — Ryder Carroll's Rapid Logging principle. Mike invokes this via `/workbench-bujo:bujo-capture <text>` (or by explicitly asking to log something); anything he didn't capture mid-day gets picked up by the next morning's harvest step in the daily ritual.

**Mike already decided to capture by invoking this.** Don't ask "should I log this?" — classify, format, dispatch, confirm.

## What to capture (format)

Use BuJo signifiers appropriate to the content type:

- **Insight / aha** → `!—` (inspiration)
- **Priority realization** → `✽` prefix on whatever base
- **Something to research** → `◉` prefix (explore)
- **Completed task** → `×` task
- **Event** → `○` event
- **Plain observation** → `—` note
- **Task that emerged** → `•` task

Keep the entry to a **single line** when possible, per BuJo style. Example:

> `!— Architecture shift: the MCP should own invariants, not the skill — skills get drifty, tools don't`

## How to dispatch

Use the `bujo-scribe` MCP:

```
mcp__plugin_workbench-bujo_scribe__bujo_apply_decisions(payload={
  note: "today",
  decisions: [
    {
      op: "add",
      section: "Captures",   // advisory; daily is a single block so section is cosmetic
      bullet: {
        signifier: "note",     // or task, event, note — match the nature
        text: "<single-line entry>",
        prefix: "inspiration"  // optional; set appropriate to content
      }
    }
  ]
})
```

If today's note doesn't exist yet, this dispatch will fail. Before adding the capture, check that `today` exists via `bujo_read`. If it doesn't, scaffold a minimal one first:

```
mcp__plugin_workbench-bujo_scribe__bujo_scaffold(payload={
  target: "today",
  ritual: "daily",
  mode: "merge",
  sections: []
})
```

Then dispatch the add.

After the dispatch, confirm with one line: *"🪶 Logged: <bullet>"*. Mike can correct via natural language ("drop that", "rename to …") if the wording was wrong.

## Hard rules

1. **Signal-to-noise ratio is sacred.** Over-capturing makes the journal useless. One entry per invocation; multi-item dumps belong in a ritual.
2. **Single line.** Multi-line captures belong in a ritual reflection, not mid-conversation.
3. **Mike's voice, not yours.** Write the capture as a neutral observation or in Mike's words. Never editorialize or add your own interpretation.
4. **Never capture private / embarrassing content** without confirming the exact wording first, even though the invocation itself was explicit. If the moment is raw, check before it lands in the journal.
5. **Respect the day's scaffold.** If today isn't scaffolded yet, scaffold a minimal one; don't refuse to capture.
6. **Setup-time ordering does not apply to captures.** Mid-day additions append chronologically — the MCP's `mode: merge` handles that correctly.
