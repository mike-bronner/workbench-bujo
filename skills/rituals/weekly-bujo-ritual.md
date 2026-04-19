---
description: Run the weekly BuJo ritual. Thin wrapper — weekly runs the universal `bujo-ritual` protocol in LIGHT mode (no check-in, no feelings reflection — disposition + scaffold + intention only).
---

# BuJo Weekly Ritual

This ritual follows the universal BuJo protocol defined in `skills/rituals/bujo-ritual.md`, specifically its **light mode**. Weekly exists as a planning/migration cadence (a BuJo community extension, not in Ryder Carroll's canonical method); we keep the planning value but skip the introspection layer that daily, monthly, and yearly rituals carry.

## How weekly differs from full tiers

| Step | Full tiers (daily/monthly/yearly) | Weekly (light) |
|---|---|---|
| 2 — Check-in | "How did it go? Anything missing?" (INTERACTIVE) | **Skipped entirely** |
| 3 — Item review | Each item + feelings probe | Each item, disposition-only — no feelings layer |
| 5 — Planning | Energy check first, then planning | Straight to "what's the shape of the week?" |

Weekly still follows Ryder's friction principle — **every unfinished or dropped item from the past week gets inspected individually**, no batching. The difference is depth, not coverage.

## How to run this ritual

1. **Read the universal protocol** at `${CLAUDE_PLUGIN_ROOT}/skills/rituals/bujo-ritual.md`.
2. **Set `tier = weekly`** when following the Tier matrix in the protocol.
3. **Expect a plan block** from the `/bujo` router (or run the `bujo-orchestrator` agent yourself if invoked ad-hoc and filter its output to the weekly tier only).
4. Follow the protocol using the `weekly` row of the Tier matrix — honoring the **light mode** rules above (skip Step 2, skip feelings layer in Step 3, skip energy check in Step 5).

No additional weekly-specific rules live here. If something feels like it should, it belongs in the universal protocol.
