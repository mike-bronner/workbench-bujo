---
description: Run the yearly BuJo ritual right now — review the year's monthlies, create yearly note, set goals for the new year. Interactive.
---

The user has invoked `/workbench:bujo-yearly-ritual`. Execute the yearly BuJo ritual on-demand.

## Setup

1. Read the BuJo config at `~/.claude/plugins/data/bullet-journal-claude-workbench/config.json`.
   - If it doesn't exist, tell the user to run `/workbench:bujo-setup` first.
2. Read the skill definition at `${CLAUDE_PLUGIN_ROOT}/skills/rituals/yearly-bujo-ritual.md`.

## Execution

Follow the skill definition step by step. Use the config values for:
- **Timezone** → from `config.timezone`
- **Journal folder** → from `config.journal_folder`
- **Note names** → `journal_index_note`, `future_log_note`, `goals_note` from config

This is an interactive ritual — all interactive steps (Steps 4, 5, 6) are mandatory. Do not skip them.
