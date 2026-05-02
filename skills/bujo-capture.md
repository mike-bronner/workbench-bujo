---
description: Capture an experientially-significant moment to today's BuJo daily log, mid-conversation, without running a full ritual. Invoked proactively by Hobbes when something noteworthy happens in a session, OR manually via the /workbench-bujo:bujo-capture command.
---

# BuJo Capture — Experiential Logging

Mid-conversation logging for experientially-significant moments that happen outside ritual time. A BuJo Daily Log is meant to be **lived in**, not just retrospectively filled at ritual time — Ryder Carroll's Rapid Logging principle. This skill is how Hobbes (or Mike) drops a meaningful moment into today's log as it happens.

## When to invoke proactively

As Hobbes, watch for **experientially significant** moments during any session (coding, conversation, work, whatever Mike is doing) and invoke this skill when one lands. The signal is:

**✅ Capture-worthy:**
- 💡 A realization, insight, or "aha" Mike voices or that emerges from work together
- 🎯 A meaningful decision made outside of a ritual (architecture pivot, direction change, project pause, stopping a pattern)
- 🚧 A moment of real friction or breakthrough (something was stuck for days, it just shipped; something keeps going wrong in the same way)
- 💬 A significant conversation or connection (a 1:1 with outcome, a moment of clarity, a hard talk)
- 🌱 An emotionally-notable moment (a win that lands, a frustration that matters, a grief or gratitude beat)
- 🧭 A pivot in focus, energy, or mood that Mike might want to reflect on later
- 🔑 A question or uncertainty Mike is wrestling with — worth marking for future research/thought

**❌ NOT capture-worthy** (filter these OUT):
- Every file edited, every command run, routine code changes
- Minor tool calls, lookups, checks
- Trivial task completions ("installed dependencies")
- Anything Mike can reconstruct from git history or tool transcripts
- Things that belong in scratch/working memory, not in his journaled life

**Heuristic:** if Mike retrospectively looked at today's journal, would this entry *mean something to him* — or would it be noise? Only capture the former. Better to under-capture than to flood the log with small stuff.

**When in doubt, ask:** *"That landed — worth capturing in today's log?"* Let Mike decide. A 5-second check is better than cluttering the journal or missing something important.

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

## Interaction pattern

**Auto-dispatch (default for unambiguous moments):** when the trigger is unambiguous (see the SessionStart hook's "Auto-capture" list — concrete completions, named decisions, voiced insights, real-world events, agent-completed work that produced an artifact), **dispatch without asking**. Confirm with one line:

> "🪶 Logged: `!— Architecture shift: MCP owns invariants, skills get drifty`"

The whole point of mid-conversation capture is that it shouldn't add friction. Each "should I capture this?" prompt at an unambiguous moment is a tax on Mike's flow — the journal is supposed to *follow* his work, not interrupt it.

**Ask-first (only for ambiguous moments):** when it's not clear whether something lands as capture-worthy (a pivot that might be exploration, a frustration without clear stakes, a thinking-aloud moment), offer one line:

> "🪶 Worth capturing: `! Pivot: ...`?"

One offer, then drop it if Mike doesn't engage. Don't pile up.

**Manual via slash command:** Mike invokes `/workbench-bujo:bujo-capture` with content. Dispatch without asking — he already decided.

## Hard rules

1. **Signal-to-noise ratio is sacred.** Over-capturing makes the journal useless. Under-capture if uncertain.
2. **Single line.** Multi-line captures belong in a ritual reflection, not mid-conversation.
3. **Mike's voice, not yours.** Write the capture as a neutral observation or in Mike's words. Never editorialize or add your own interpretation.
4. **Auto-dispatch unambiguous captures; ask-first only for ambiguous ones.** The hook's "Auto-capture" list defines which category each trigger falls into. Confirming a clear capture wastes Mike's attention; skipping a confirmation on an ambiguous one risks a bad write. Use judgment per the hook categories — don't treat every capture as needing confirmation, and don't skip confirmation when the moment isn't crystal clear.
5. **Never capture private/embarrassing content** that Mike wouldn't want in a note he might re-read. If a moment is raw, ask first regardless of whether it'd otherwise auto-dispatch.
6. **Respect the day's scaffold.** If today isn't scaffolded yet, scaffold a minimal one; don't refuse to capture.
7. **Setup-time ordering does not apply to captures.** Mid-day additions append chronologically — the MCP's `mode: merge` handles that correctly.
