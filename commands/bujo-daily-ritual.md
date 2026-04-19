---
description: Run the daily BuJo ritual ad-hoc — orchestrator plans first, then the universal protocol runs for the daily tier only.
---

The user invoked `/workbench-bujo:bujo-daily-ritual`. Run the daily tier of the BuJo ritual on-demand.

## Phase 1 — Plan (orchestrator)

Dispatch the `bujo-orchestrator` sub-agent with:

```
today: <YYYY-MM-DD computed in the configured timezone>
timezone: <tz from ~/.claude/plugins/data/workbench-bujo-claude-workbench/config.json, default America/Phoenix>
```

Parse the orchestrator's final YAML block. **Ad-hoc override:** ignore the orchestrator's `rituals` list and force the execution tier to `daily`. Keep everything else — `retrospect.daily`, `reflection_focus.daily`, `warnings`, `state_inspected`.

## Phase 2 — Surface anomalies

If `warnings` is non-empty, present them to Mike and wait for his decision before proceeding. Same behavior as the `/bujo` router's Step 2.

## Phase 3 — Execute the daily ritual

Read `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md` — the universal protocol — and follow it with `tier = daily`. The orchestrator's `retrospect.daily` and `reflection_focus.daily` are your inputs.

## Hard rules

- Use only the MCP `mcp__plugin_workbench-bujo_scribe__*` tools for I/O.
- Do not fabricate responses if Mike doesn't answer; pause the session.
- Do not run other tiers — this command is daily-only.
