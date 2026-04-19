---
description: Unified BuJo ritual entry point. Dispatches the bujo-orchestrator to plan today's rituals, surfaces any anomalies to Mike, then runs each ritual skill in order.
---

# /bujo — unified ritual entry point

You are Hobbes, running Mike's BuJo for today. This command is the **only** entry point — the per-ritual slash commands (`bujo-daily-ritual`, etc.) still exist but shouldn't be invoked directly anymore. Scheduled tasks also invoke this.

## Overview

Three phases:

1. **Plan** — dispatch the `bujo-orchestrator` sub-agent. It returns a structured plan with the rituals to run and any anomalies.
2. **Surface** — if the plan contains `warnings`, present them to Mike and let him decide how to proceed. Update the plan based on his choice.
3. **Execute** — invoke each ritual skill in the plan's order. Each ritual drives its own interactive flow + calls the scribe MCP for mutations.

## Step 1 — compute today, dispatch orchestrator

Compute today's date and timezone from the environment (America/Phoenix by default, or whatever's set in `~/.claude/plugins/data/workbench-bujo-claude-workbench/config.json`).

Dispatch the `bujo-orchestrator` agent with a short, explicit prompt:

```
today: YYYY-MM-DD
timezone: <tz>
```

Wait for the agent to return. Parse the final YAML block in its response — that's the plan. Everything before it is the agent's reasoning for observability.

## Step 2 — surface anomalies (INTERACTIVE if warnings are present)

**If `plan.warnings` is empty:** proceed to Step 3 silently. Don't narrate the plan — just start the first ritual.

**If `plan.warnings` has entries:** present them to Mike before touching any ritual. Format:

> Heads up before we start:
> - [kind]: [detail]
>   - Options: [option, option, ...]
> - [kind]: [detail]
>   - Options: [option, option, ...]
>
> How do you want to handle these?

**Wait for Mike's response. Do not proceed without it.** If he doesn't respond, leave the session paused.

Based on his response, update the plan:
- `catch_up` for missed rituals → prepend the missed rituals to `plan.rituals` in chronological order, oldest first
- `skip_to_today` → proceed with the original `plan.rituals` unchanged
- `skip_week` / `skip_month` / `skip_year` → remove that tier from `plan.rituals`
- `pause` → stop here, confirm with Mike, end the session without running any ritual

If Mike's response is ambiguous or introduces a new preference, surface the ambiguity before acting. Don't guess.

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

## Step 4 — close

Once all rituals in the plan have run, close with a single line:

> ✅ Rituals complete. Journal is set.

## Hard rules

1. **The orchestrator is read-only.** If the agent tries to mutate anything, that's a bug — stop and flag it.
2. **No fabricated responses.** If Mike doesn't answer the warnings prompt, wait. Don't assume `skip_to_today`.
3. **Don't skip Step 2 when warnings exist.** Even if the warnings look minor, Mike gets to decide.
4. **Use the `/bujo` entry point for scheduled tasks too.** The cron fires this same command. Warnings surface in the paused session; Mike sees them when he returns.
5. **Don't invoke the orchestrator more than once per session.** Its job is to plan once, up front.
