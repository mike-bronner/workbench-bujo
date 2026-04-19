---
description: Configure the BuJo plugin — timezone, note names, ritual schedule. Deploys a single unified scheduled task that runs /bujo each morning; the orchestrator decides which tiers fire. Re-run after a plugin update.
---

The user has invoked `/workbench-bujo:bujo-setup`. Walk them through configuring and deploying the BuJo ritual system.

## What setup produces

- **One config file** at `~/.claude/plugins/data/workbench-bujo-claude-workbench/config.json`
- **One scheduled task** — `/workbench-bujo:bujo` fires daily at 7am (configurable). The `bujo-orchestrator` agent determines which tiers (yearly, monthly, weekly, daily) apply and chains them in order.
- **Optional user rules override** at `~/.claude/plugins/data/workbench-bujo-claude-workbench/rules.yaml` — users customize signifiers and extensions here (not set up by this command; see plugin README).

## Step 1 — Check Prerequisites

1. **Core plugin:** Check if `~/.claude/plugins/data/workbench-core-claude-workbench/config.json` exists (fall back to the legacy `workbench-claude-workbench/config.json` if not). If neither, warn: "The workbench-core plugin must be configured first. Run `/workbench-core:customize`."
2. **Scribe MCP:** Try any `mcp__plugin_workbench-bujo_scribe__*` tool (e.g., `bujo_read` with `notes: ["index"]`). If it fails, warn: "The bujo-scribe MCP isn't reachable. Run `uv tool install bujo-scribe-mcp` and reload Claude Code."
3. **Scheduled tasks MCP:** Try `mcp__scheduled-tasks__list_scheduled_tasks`. If it fails, warn: "Scheduled tasks MCP is not available."

If any prerequisite fails, stop and explain what needs to be set up first.

## Step 2 — Read Core Config

Read the workbench-core config for shared values:
- `journal_folder` (default: `📓 Journal`)
- `daily_note_format` (default: `YYYY-MM-DD — Weekday`)

Use these as defaults for the BuJo config below.

## Step 3 — Collect Config

Read the existing BuJo config file if it exists:

```bash
CONFIG_DIR="$HOME/.claude/plugins/data/workbench-bujo-claude-workbench"
CONFIG_FILE="$CONFIG_DIR/config.json"
```

If it exists, parse current values and use them as defaults. If not, use hardcoded defaults.

Present each field via AskUserQuestion. Show the current value and let Mike confirm or change.

### Core fields

| Field | Default | Description |
|---|---|---|
| `timezone` | `America/Phoenix` | Timezone for computing dates in rituals |
| `journal_folder` | (from core config) | Apple Notes folder name |
| `daily_note_format` | (from core config) | Daily note title pattern |
| `journal_index_note` | `📓 Journal Index` | Name of the Journal Index note (optional, human-readable reference) |
| `future_log_note` | `Future Log` | Name of the Future Log note |
| `goals_note` | `Goals` | Name of the Goals note |
| `second_brain_note` | `🧠 Claude's Second Brain` | Name of the Second Brain note |

**Note:** the `daily_data_note` field has been removed — the scribe MCP fetches Calendar and Reminders directly via its DataSource backend, so no staging note is needed.

### Schedule

There is **one scheduled task now** — not four. The `bujo-orchestrator` agent decides which tiers run each day.

| Schedule | Default Cron | Default Enabled | Behavior |
|---|---|---|---|
| `bujo` | `0 7 * * *` | true | Runs daily at 7am. Orchestrator fires any applicable higher tiers (yearly on Jan 1, monthly on the 1st, weekly on Sunday) in strict order before daily. |

After all fields, show the assembled config JSON and ask "Save this configuration? (yes/no)".

## Step 4 — Write Config

1. Create the config directory if it doesn't exist: `mkdir -p $CONFIG_DIR`
2. Write `config.json` with all collected values, including the single `bujo` schedule entry.

## Step 5 — Verify Journal Folder

Call `mcp__plugin_workbench-bujo_scribe__bujo_read` with `notes: ["index"]`. If the response shows `exists: false` for the index, inform Mike:

> "The Journal Index note (`{journal_index_note}`) doesn't exist yet. That's fine — rules now live inside the scribe MCP's `rules.yaml`, not in the note. The Journal Index note can be regenerated later as a human-readable reference of your active rules."

If the journal folder itself is missing, warn: "The `{journal_folder}` folder doesn't exist in Apple Notes. Please create it before running rituals."

Do NOT auto-create the folder or the index note.

## Step 6 — Deploy the Scheduled Task

There's only one scheduled task to deploy:

1. Build the prompt from the template at `${CLAUDE_PLUGIN_ROOT}/assets/prompt-templates/bujo.prompt.md` (fallback: use the inline prompt below if the template file doesn't exist).

   Fallback prompt:

   ```
   It's time for your BuJo ritual. Invoke /workbench-bujo:bujo — the
   orchestrator will determine which tiers apply today and chain them.
   ```

2. Call `mcp__scheduled-tasks__create_scheduled_task` with:
   - `taskId`: `bujo-ritual`
   - `description`: `BuJo daily ritual (orchestrator-routed)`
   - `cronExpression`: from `config.schedules.bujo.cron`
   - `prompt`: the resolved template

3. If a scheduled task with ID `bujo-ritual` already exists, use `mcp__scheduled-tasks__update_scheduled_task` to sync the cron and prompt.

## Step 7 — Offer Legacy Cleanup

The architecture previously used four separate scheduled tasks; the unified `bujo-ritual` task replaces all of them. Check for and offer to remove:

- `daily-bujo-ritual`
- `weekly-bujo-ritual`
- `monthly-bujo-ritual`
- `yearly-bujo-ritual`

Also check `~/Documents/Claude/Scheduled/` for deprecated task directories with matching names, plus the older:

- `daily-journal-setup/`
- `daily-journal-review/`
- `weekly-bujo-review/`
- `monthly-bujo-review/`
- `yearly-bujo-review/`

If any found, ask: "Found deprecated BuJo scheduled tasks: [list]. Remove them? (The new `bujo-ritual` task replaces all of them.)"

On confirmation:
1. For each legacy scheduled task ID, call `mcp__scheduled-tasks__delete_scheduled_task` (or disable if delete isn't available).
2. Delete deprecated directories in `~/Documents/Claude/Scheduled/`.

## Step 8 — Confirm

Tell Mike:
- Config saved to `{CONFIG_FILE}`
- `bujo-ritual` scheduled task deployed/updated (cron: `{cron}`)
- Any legacy tasks cleaned up
- Remind: "Re-run `/workbench-bujo:bujo-setup` after a plugin update to sync the scheduled-task prompt with any changes."
- Point to: "Customize signifiers or add extensions by creating `~/.claude/plugins/data/workbench-bujo-claude-workbench/rules.yaml`. See the plugin README for format."

## Notes

- **One task, not four.** The orchestrator handles tier routing at fire time — no need for separate weekly/monthly/yearly cron entries.
- **Ad-hoc runs:** tier-specific slash commands (`/workbench-bujo:bujo-daily-ritual`, `-weekly-ritual`, `-monthly-ritual`, `-yearly-ritual`) still exist for manual invocation. They run the orchestrator with forced tier.
- **First-time setup:** if no config exists, all fields start at hardcoded defaults (or core config values where applicable).
- **Disabling the ritual:** set `schedules.bujo.enabled: false`. Re-run setup; it'll skip deployment and leave existing task as-is.
