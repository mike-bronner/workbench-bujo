---
description: Run the weekly BuJo ritual ad-hoc — orchestrator plans first, then the universal protocol runs for the weekly tier only.
---

The user invoked `/workbench-bujo:bujo-weekly-ritual`. Run the weekly tier of the BuJo ritual on-demand.

## Phase 1 — Plan (orchestrator)

Dispatch the `bujo-orchestrator` sub-agent with:

```
today: <YYYY-MM-DD computed in the configured timezone>
timezone: <tz from ~/.claude/plugins/data/workbench-bujo-claude-workbench/config.json, default America/Phoenix>
```

Parse the orchestrator's final YAML block. **Ad-hoc override:** ignore the orchestrator's `rituals` list and force the execution tier to `weekly`. Keep everything else — `retrospect.weekly`, `reflection_focus.weekly`, `warnings`, `state_inspected`.

## Phase 2 — Surface anomalies

If `warnings` is non-empty, present them to Mike and wait for his decision before proceeding. Same behavior as the `/bujo` router's Step 2.

## Phase 3 — Execute the weekly ritual

Read `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md` — the universal protocol — and follow it with `tier = weekly`. The orchestrator's `retrospect.weekly` and `reflection_focus.weekly` are your inputs.

## Hard rules

- Use only the MCP `mcp__plugin_workbench-bujo_scribe__*` tools for I/O.
- Do not fabricate responses if Mike doesn't answer; pause the session.
- Do not run other tiers — this command is weekly-only.
