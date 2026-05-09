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

## Interaction pattern (three tiers)

**Tier 1 — Silent capture (explicit phrasing):** Mike named a completion / decision / event / shipped artifact in his own words. Examples: *"I shipped X"*, *"decided to Y"*, *"had a 1:1 with Z"*, *"finished the migration"*, *"Y is done"*. He gave the signal — dispatch immediately:

```
mcp__plugin_workbench-bujo_scribe__bujo_apply_decisions:add  // or :complete if matching an open task
```

Confirm with one line: *"🪶 Logged: <bullet>"*. Mike can correct via natural language ("drop that", "rename to …") if the wording was wrong — that's cheaper than an interrupting prompt.

**Tier 2 — Propose via `AskUserQuestion` (inferred / ambiguous):** Hobbes notices something potentially capture-worthy that Mike *didn't* explicitly name — a realization that emerged, a possible pivot, a breakthrough, a frustration with stakes. Propose with the proposed bullet text and TWO options only — yes or no:

```jsonc
AskUserQuestion({
  questions: [{
    question: "🪶 Capture this on today's note?\n  `!— Architecture shift: MCP owns invariants, skills get drifty`",
    header: "Capture?",
    multiSelect: false,
    options: [
      { label: "Yes — log it", description: "Adds the bullet to today's note" },
      { label: "No — skip",    description: "Not capture-worthy" }
    ]
  }]
})
```

On **Yes** → dispatch `bujo_apply_decisions:add` (or `:schedule` for future-dated). Confirm one line.
On **No** → skip silently. Don't paraphrase and re-offer the same moment.

**No "edit wording" option.** The question wording IS the bullet. If it's wrong, Mike says no and the agent does better next time (or runs `/bujo-capture <correct text>`).

**Tier 3 — Skip silently:** routine code edits, command runs, file lookups, trivial completions ("installed deps", "fixed typo"), thinking-aloud that hasn't crystallized. Don't propose, don't dispatch.

**Manual via slash command:** Mike invokes `/workbench-bujo:bujo-capture <text>` directly. Dispatch without asking — he already decided.

### Self-throttle on consecutive rejections

If Mike says **No** to **3+ consecutive proposals** in a session, the agent's threshold is too eager for this moment. **Stop proposing for the rest of the session** and acknowledge once: *"Got it — I'll stop proposing captures this session. Run `/bujo-capture <text>` if something specific comes up."*

The user's "no, no, no" is a clear signal that the conversation is in flow that doesn't need narration. Resume proposals next session.

## Hard rules

1. **Signal-to-noise ratio is sacred.** Over-capturing makes the journal useless. Under-capture if uncertain.
2. **Single line.** Multi-line captures belong in a ritual reflection, not mid-conversation.
3. **Mike's voice, not yours.** Write the capture as a neutral observation or in Mike's words. Never editorialize or add your own interpretation.
4. **Tier the consent.** Explicit-phrasing captures dispatch silently with a one-line ack. Inferred / ambiguous captures go through `AskUserQuestion` (yes/no, no edit option, no retry on the same moment). Routine ops are skipped silently. Manual `/bujo-capture` always dispatches.
5. **Never capture private / embarrassing content** without asking, even when the phrasing seems explicit. Sensitive moments default to tier 2 (propose) or skip — and a yes-to-propose still shouldn't go in if the moment is raw.
6. **Respect the day's scaffold.** If today isn't scaffolded yet, scaffold a minimal one; don't refuse to capture.
7. **Setup-time ordering does not apply to captures.** Mid-day additions append chronologically — the MCP's `mode: merge` handles that correctly.
8. **Self-throttle after 3 consecutive nos** (tier-2 only). Stop proposing for the session. Tier-1 silent captures continue; Mike corrects individual ones via natural language ("drop that") if needed.
