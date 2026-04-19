---
description: Run the yearly BuJo ritual. Thin wrapper — all mechanics live in the universal `bujo-ritual` protocol.
---

# BuJo Yearly Ritual

This ritual follows the universal BuJo protocol defined in `skills/rituals/bujo-ritual.md`. Every BuJo tier (daily, weekly, monthly, yearly) uses the same two-lane retrospective (disposition + reflection) + scaffold + energy-aware planning flow — only the scope, scaffold target, and framing language change per tier.

## How to run this ritual

1. **Read the universal protocol** at `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md`.
2. **Set `tier = yearly`** when following the Tier matrix in the protocol.
3. **Expect a plan block** from the `/bujo` router (or run the `bujo-orchestrator` agent yourself if invoked ad-hoc and filter its output to the yearly tier only).
4. Follow every step in the universal protocol using the `yearly` row of the Tier matrix.

The yearly ritual is the biggest of the year — it deserves the most care. Take your time. Don't rush Lane B.
