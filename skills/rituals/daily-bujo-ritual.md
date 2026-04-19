---
description: Run the daily BuJo ritual. Thin wrapper — all mechanics live in the universal `bujo-ritual` protocol.
---

# BuJo Daily Ritual

This ritual follows the universal BuJo protocol defined in `skills/rituals/bujo-ritual.md`. Every BuJo tier (daily, weekly, monthly, yearly) uses the same two-lane retrospective (disposition + reflection) + scaffold + energy-aware planning flow — only the scope, scaffold target, and framing language change per tier.

## How to run this ritual

1. **Read the universal protocol** at `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md`.
2. **Set `tier = daily`** when following the Tier matrix in the protocol.
3. **Expect a plan block** from the `/bujo` router (or run the `bujo-orchestrator` agent yourself if invoked ad-hoc and filter its output to the daily tier only).
4. Follow every step in the universal protocol using the `daily` row of the Tier matrix.

No additional daily-specific rules live here. If you think something needs to, it belongs in the universal protocol.
