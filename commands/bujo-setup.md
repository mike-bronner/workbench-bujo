---
description: Configure the BuJo plugin — timezone, note names, ritual schedules. Deploys scheduled tasks and offers legacy cleanup. Re-run after a plugin update to sync scheduled task prompts.
---

The user has invoked `/workbench:bujo-setup`. Walk them through configuring and deploying the BuJo ritual system.

## Config location

```
~/.claude/plugins/data/bullet-journal-claude-workbench/config.json
```

This is the plugin system's persistent data directory — it survives plugin version bumps.

## Step 1 — Check Prerequisites

1. **Core plugin:** Check if `~/.claude/plugins/data/workbench-claude-workbench/config.json` exists. If not, warn: "The core workbench plugin must be configured first. Run `/workbench:customize`."
2. **Apple Notes MCP:** Try `mcp__Read_and_Write_Apple_Notes__list_notes` with `folder: "📓 Journal"`. If it fails, warn: "Apple Notes MCP is not available."
3. **Scheduled tasks MCP:** Try `mcp__scheduled-tasks__list_scheduled_tasks`. If it fails, warn: "Scheduled tasks MCP is not available."

If any prerequisite fails, stop and explain what needs to be set up first.

## Step 2 — Read Core Config

Read `~/.claude/plugins/data/workbench-claude-workbench/config.json` for shared values:
- `journal_folder` (default: `📓 Journal`)
- `daily_note_format` (default: `YYYY-MM-DD — Weekday`)

These become the defaults for the BuJo config.

## Step 3 — Collect Config

Read the existing BuJo config file if it exists:

```bash
CONFIG_DIR="$HOME/.claude/plugins/data/bullet-journal-claude-workbench"
CONFIG_FILE="$CONFIG_DIR/config.json"
```

If it exists, parse current values and use them as defaults. If not, use hardcoded defaults.

Present all fields to the user using AskUserQuestion. Show the current value and let them confirm or change it.

### Fields

| Field | Default | Description |
|---|---|---|
| `timezone` | `America/Phoenix` | Timezone for computing dates in rituals |
| `journal_folder` | (from core config) | Apple Notes folder name |
| `daily_note_format` | (from core config) | Daily note title pattern |
| `journal_index_note` | `📓 Journal Index` | Name of the Journal Index note |
| `future_log_note` | `Future Log` | Name of the Future Log note |
| `goals_note` | `Goals` | Name of the Goals note |
| `daily_data_note` | `📅 Daily Data` | Name of the Daily Data note |
| `second_brain_note` | `🧠 Claude's Second Brain` | Name of the Second Brain note |

### Schedule fields

For each ritual, present the cron expression and enabled flag:

| Schedule | Default Cron | Default Enabled |
|---|---|---|
| `daily_ritual` | `0 7 * * *` | true |
| `weekly_ritual` | `50 6 * * 0` | true |
| `monthly_ritual` | `40 6 1 * *` | true |
| `yearly_ritual` | `30 6 1 1 *` | true |

After all fields, show the assembled config JSON and ask "Save this configuration? (yes/no)".

## Step 4 — Write Config

1. Create the config directory if it doesn't exist: `mkdir -p $CONFIG_DIR`
2. Write `config.json` with all collected values.

## Step 5 — Verify Journal Index

Read the Journal Index note via `mcp__Read_and_Write_Apple_Notes__get_note_content` with the configured `journal_index_note` in the configured `journal_folder`.

If missing, warn: "The Journal Index note is the source of truth for all BuJo formatting rules. Please create it in your Apple Notes `📓 Journal` folder before running rituals. The plugin defines the *process*; the Journal Index defines the *rules*."

Do NOT auto-create it — the content is personal and opinionated.

## Step 6 — Deploy Scheduled Tasks

For each enabled schedule in config:

1. Read the skill file from `${CLAUDE_PLUGIN_ROOT}/skills/rituals/{ritual_name}.md`.
2. Read the prompt template from `${CLAUDE_PLUGIN_ROOT}/assets/prompt-templates/{ritual_name}.prompt.md`.
3. Substitute all `{{config_key}}` tokens in the template from config values.
4. Replace `{{skill_content}}` with the full text of the skill file.
5. Call `mcp__scheduled-tasks__create_scheduled_task` with:
   - `taskId`: from config schedules (e.g., `daily-bujo-ritual`)
   - `description`: from the skill's opening line
   - `cronExpression`: from config schedules
   - `prompt`: the fully-resolved prompt template
6. Confirm creation for each task.

If a scheduled task with that ID already exists, use `mcp__scheduled-tasks__update_scheduled_task` instead to sync the prompt and cron from the latest plugin version.

## Step 7 — Offer Legacy Cleanup

Check if deprecated task directories exist in `~/Documents/Claude/Scheduled/`:
- `daily-journal-setup/` — superseded by daily-bujo-ritual
- `daily-journal-review/` — merged into daily-bujo-ritual
- `weekly-bujo-review/` — replaced by weekly-bujo-ritual
- `monthly-bujo-review/` — replaced by monthly-bujo-ritual
- `yearly-bujo-review/` — replaced by yearly-bujo-ritual

If any found, ask: "Found deprecated BuJo tasks: [list]. Remove them?"

On confirmation:
1. Check if matching scheduled tasks are registered; if so, disable them.
2. Delete the deprecated directories.

## Step 8 — Confirm

Tell the user:
- Config saved to `{CONFIG_FILE}`
- Which scheduled tasks were deployed/updated
- Whether any legacy tasks were cleaned up
- Remind: "Run `/workbench:bujo-setup` again after a plugin update to sync scheduled task prompts with the latest ritual definitions."

## Notes

- **Re-running after a plugin update:** Skill files update with the plugin. Re-running `/workbench:bujo-setup` regenerates scheduled task prompts from updated skills + existing user config, then pushes them to the scheduled-tasks system via update.
- **First-time setup:** If no config exists, all fields start at their hardcoded defaults (or core config values where applicable).
- **Disabling a ritual:** Set `enabled: false` in the schedule config. The setup command will skip deploying that task but won't remove an existing one — disable it manually via `mcp__scheduled-tasks__update_scheduled_task` if needed.
