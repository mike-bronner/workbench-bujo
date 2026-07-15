---
description: Unified BuJo ritual entry point. Dispatches the bujo-orchestrator to plan today's rituals, surfaces any anomalies to Mike, then runs each ritual skill in order.
---

# /bujo — unified ritual entry point

You are Holmes, running Mike's BuJo for today. This command is the **only** entry point — the per-ritual slash commands (`bujo-daily-ritual`, etc.) still exist but shouldn't be invoked directly anymore. Scheduled tasks also invoke this.

## Overview

Three phases:

1. **Plan** — dispatch the `bujo-orchestrator` sub-agent. It returns a structured plan with the rituals to run and any anomalies.
2. **Surface** — if the plan contains `warnings`, present them to Mike and let him decide how to proceed. Update the plan based on his choice.
3. **Execute** — invoke each ritual skill in the plan's order. Each ritual drives its own interactive flow + calls the scribe MCP for mutations.

## Chapter marks

Call `mcp__ccd_session__mark_chapter` at each major phase transition so Mike has a navigable table of contents for long rituals:

- Before Step 1: `mark_chapter(title="Plan")`
- Before Step 2 (if warnings): `mark_chapter(title="Warnings")`
- Entering each tier's ritual (Step 3): the ritual skill handles its own chapter marks per phase

Don't mark trivially — only at real transitions.

## Step 1 — compute today, pre-warm scribe, dispatch orchestrator

Compute today's date and timezone from the environment (America/Phoenix by default, or whatever's set in `~/.claude/plugins/data/workbench-bujo-claude-workbench/config.json`).

### 1a. Pre-warm the scribe MCP (best-effort)

Claude Code's MCP lifecycle can take ~10s from cold (spawn → handshake → `tools/list` → deferred-schema registration). Subagents inherit the parent's MCP connections, so warming the scribe here means the orchestrator sees it ready at dispatch — fewer "offline" misreads on the orchestrator side.

**This is a best-effort optimization, NOT a precondition.** Never abort the ritual on warm-up failure — the orchestrator has its own boot-patience retries (see `agents/bujo-orchestrator.md`). Gating dispatch on warm-up turns "scribe is slow" into "ritual is broken," which is the wrong tradeoff.

Before dispatching the agent:

1. Load the deferred schemas in this (parent) conversation — `AskUserQuestion` included, same as the sibling habit commands, so Step 2's first prompt never fires with an unloaded schema. Its absence from the results doubles as the up-front stripped-tool signal for Rule B:
   ```
   ToolSearch(query="select:AskUserQuestion,mcp__plugin_workbench-bujo_scribe__bujo_read", max_results=2)
   ```
2. Make one trivial call to nudge the handshake:
   ```
   bujo_read(payload={ notes: ["today"] })
   ```
   Discard the result — this is a warm-up, not state inspection.

**On any warm-up error — `InputValidationError`, transport error, schema miss, anything — proceed to Step 1b and dispatch the orchestrator anyway.** Do not retry, do not sleep, do not surface errors to Mike. The orchestrator handles real outages via its own retry loop and `scribe_offline` warning path; let it. Optional: a single brief one-liner in chat ("⏳ scribe still booting; orchestrator will pick up the slack") is fine, but only if the warm-up errored — silent on success.

### 1b. Dispatch the orchestrator

Dispatch the `bujo-orchestrator` agent with a short, explicit prompt:

```
today: YYYY-MM-DD
timezone: <tz>
```

Wait for the agent to return. Parse the final YAML block in its response — that's the plan. Everything before it is the agent's reasoning for observability.

## Step 2 — surface anomalies (INTERACTIVE if warnings are present)

**If `plan.warnings` is empty:** proceed to Step 3 silently. Don't narrate the plan — just start the first ritual.

**If `plan.warnings` has entries:** surface them to Mike before touching any ritual. Follow these rules strictly:

### Rule A — Translate, don't regurgitate

The orchestrator's YAML is **machine-structured for Holmes to parse**, not for Mike to read. Never dump `kind: ...`, `Options: [...]`, or JSON-esque syntax into the conversation. Always translate each warning into a single plain-English sentence about *what happened* and *why it matters*.

**Examples — before and after:**

❌ **Do NOT say:**
> missed_yearly: yearly_current doesn't exist — the Jan 1 yearly ritual was never run. Mid-year now, so a full retrospect isn't really possible.
> Options: run_now, skip_year

✅ **Say instead:**
> "The 2026 yearly retro never got set up. It's mid-year now, so a proper review isn't really on the table — but I can scaffold an empty yearly note for tracking intentions, or we skip it."

❌ **Do NOT say:**
> missed_daily_streak: 3 consecutive missing daily notes.
> Options: skip_to_today, pause

✅ **Say instead:**
> "Three daily notes are missing — Apr 15, 16, and 17. No meaningful catch-up possible there, but worth noting."

Keep the translation tight. One sentence per warning is usually enough. Strip out anything that's just restating structured fields.

### Rule B — Use `AskUserQuestion` for decisions, not text prompts

When a warning needs a decision (options field is non-empty), use the `AskUserQuestion` tool to present options as clickable buttons. This keeps the session clearly "awaiting input" rather than appearing complete, and saves Mike from typing.

**Check the tool is actually available first.** On scheduled/unattended runs Cowork strips `AskUserQuestion` from the toolset — invoking it throws `No such tool available: AskUserQuestion. AskUserQuestion exists but is not enabled in this context` instead of leaving a pending prompt. Step 1a's `ToolSearch` already told you which case you're in: `AskUserQuestion` missing from its results means the tool is stripped from this context. **Distinguish the two error shapes.** `InputValidationError` means the schema isn't loaded yet — the tool IS available; re-run the Step 1a `ToolSearch` and retry, and never mistake it for the stripped signal on a normal interactive run. The `No such tool available … not enabled in this context` error (or absence from the ToolSearch results) is the stripped-tool signal — only then use the **plain-text fallback pause** defined in the universal protocol (`skills/rituals/bujo-ritual.md`, "If `AskUserQuestion` is stripped"): write the warning decisions as plain-text questions in chat and **end the turn there**, running no rituals. Mike answers when he next opens the session. Never let the error kill the run, and never pick an option for him.

Map the orchestrator's `options` values to human-readable labels:

| Orchestrator option | Button label |
|---|---|
| `catch_up` | "Catch up on missed" |
| `skip_to_today` | "Skip to today" |
| `run_now` | "Run it now" |
| `skip_year` / `skip_month` / `skip_week` | "Skip [tier]" |
| `pause` | "Pause session" |

If multiple warnings each have their own decisions, batch them into a **single** `AskUserQuestion` call with multiple questions (one per warning). Don't chain sequential prompts.

If a warning is informational only (no decision needed — e.g., `today_already_started` when it's fine), mention it as prose and move on without asking.

### Rule C — Honor the answer, don't guess

After Mike responds:
- `catch_up` for missed rituals → prepend the missed rituals to `plan.rituals` in chronological order, oldest first
- `skip_to_today` → proceed with the original `plan.rituals` unchanged
- `skip_week` / `skip_month` / `skip_year` → remove that tier from `plan.rituals`
- `run_now` → add that tier to `plan.rituals` in correct order
- `pause` → stop here, confirm once with Mike, end the session without running any ritual

If the response is ambiguous or Mike suggests a new option not in the buttons, surface the ambiguity before acting. Don't guess.

If Mike doesn't respond, leave the session paused. Never fabricate a choice.

## Step 3 — execute the plan

**All rituals use the same universal protocol** at `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md`. For each tier in `plan.rituals` (in the order given — strictly yearly → monthly → weekly → daily), run the universal protocol with that tier.

Before running a tier, assemble its inputs from the plan:

- `tier` — the tier key (`yearly`, `monthly`, `weekly`, or `daily`)
- `retrospect.{tier}` — the scope block from the plan (scope_notes + rationale)
- `reflection_focus.{tier}` — the recorded_experiences, potential_gaps, suggested_openers
- Any warnings Mike chose `catch_up` for get added as additional tiers earlier in the sequence (with scope pointing back to the missed periods)

Read `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md` once at the start of Step 3. Follow it for each tier in sequence, resetting your internal state between tiers. Don't re-read the protocol between tiers — it's the same document.

**Do NOT invoke the tier-specific slash commands** (`/workbench-bujo:bujo-daily-ritual`, etc.) from here. Those exist for ad-hoc user invocation only. From inside `/bujo`, go straight to the universal protocol with the plan's inputs.

Between tiers, no artificial delay — the next one starts as soon as the previous one finishes. Each tier's pass drives its own interactive flow with Mike via the universal protocol.

### 🛑 Start the first ritual by *asking*, not by narrating what's queued

When you hand off to the first tier, its first interactive step's `AskUserQuestion` is your **first action** — don't preface execution with a summary of the steps ahead. Output of the form:

> **Awaiting Mike for:** the check-in, habit check-in, item disposition, Future Log migration, scaffold, and today's priorities.

is **forbidden** — it asks nothing and leaves the session looking complete. The protocol's "Lead with the question" rule is canonical; the entrypoint must not undercut it by narrating the queue before the first tier even starts.

**Unattended / overnight runs block at the first question — by design.** The cron fires `/bujo` with no one watching (e.g., a nightly pre-seed before the morning ritual). That run is *expected* to reach the first interactive step and **pause on its first question** — not to auto-complete, not to summarize the pending work, not to fabricate answers, and not to die on a tool error. Mike returns in the morning to a question already on screen, answers it, and the ritual continues. A paused-on-a-question session is the correct end-state for an unattended run; a "here's what I'm waiting for" summary is a bug, and so is a thrown error.

**`AskUserQuestion` is NOT callable on these runs.** Cowork's scheduled-task runner strips the tool from the toolset entirely for non-interactive/scheduled executions — invoking it throws `No such tool available: AskUserQuestion. AskUserQuestion exists but is not enabled in this context`, rather than leaving a pending prompt. So before (or on the first failed) invocation at any interactive step, check whether the tool actually exists in this context — it's absent from the loaded tool list, or the call throws that "not enabled in this context" error. When it's unavailable, use the **plain-text fallback pause** (defined in the universal protocol, `skills/rituals/bujo-ritual.md`, "If `AskUserQuestion` is stripped"): write the pending question as plain-text chat output — same question, options as prose — and end the turn with no further steps executed. That reaches the identical paused-awaiting-Mike end-state the tool call would have produced.

## Step 4 — close

Once all rituals in the plan have run, close with a single line:

> ✅ Rituals complete. Journal is set.

## Hard rules

1. **The orchestrator is read-only.** If the agent tries to mutate anything, that's a bug — stop and flag it.
2. **No fabricated responses.** If Mike doesn't answer the warnings prompt, wait. Don't assume `skip_to_today`.
3. **Don't skip Step 2 when warnings exist.** Even if the warnings look minor, Mike gets to decide.
4. **Use the `/bujo` entry point for scheduled tasks too.** The cron fires this same command. Warnings surface in the paused session; Mike sees them when he returns.
5. **Don't invoke the orchestrator more than once per session.** Its job is to plan once, up front.
6. **Lead with the question; never narrate pending steps.** Hand off to the first ritual by asking its first question — invoke `AskUserQuestion` if it's available, otherwise pause on the same question as plain-text chat output (the fallback pause — see Step 3's unattended-runs note and the universal protocol's "If `AskUserQuestion` is stripped" section). Never emit an "Awaiting Mike for: [list]" summary of what's queued. An unattended/overnight run is *expected* to block on that first question and pause — that's the correct end-state, not auto-completion, not a pending-work summary, and not a `No such tool available` error.
