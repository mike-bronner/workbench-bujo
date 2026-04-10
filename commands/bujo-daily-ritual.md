---
description: Run the daily BuJo ritual right now — review yesterday, migrate tasks, create today's entry, set priorities. Interactive.
---

The user has invoked `/workbench:bujo-daily-ritual`. Execute the daily BuJo ritual on-demand.

## Setup

1. Read the BuJo config at `~/.claude/plugins/data/bullet-journal-claude-workbench/config.json`.
   - If it doesn't exist, tell the user to run `/workbench:bujo-setup` first.
2. Read the skill definition at `${CLAUDE_PLUGIN_ROOT}/skills/rituals/daily-bujo-ritual.md`.

## Execution

Follow the skill definition step by step. Use the config values for:
- **Timezone** → from `config.timezone`
- **Journal folder** → from `config.journal_folder`
- **Note names** → `journal_index_note`, `future_log_note`, `goals_note`, `daily_data_note`, `second_brain_note` from config

This is an interactive ritual — all interactive steps (Steps 3, 4, 8) are mandatory. Do not skip them.
