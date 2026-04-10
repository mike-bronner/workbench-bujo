# bullet-journal

BuJo ritual plugin for Claude Code. Part of the [`claude-workbench`](https://github.com/mike-bronner/claude-workbench) marketplace.

## What this is

An interactive Bullet Journal system that runs daily, weekly, monthly, and yearly reflection rituals in Apple Notes. Inspired by Ryder Carroll's BuJo method — adapted for a persistent AI collaborator.

Rituals run on schedule via Claude Code's scheduled tasks system, or on-demand via slash commands. Every ritual is interactive: it prompts for reflection, waits for real answers, and pushes back on shallow responses.

## Prerequisites

- **`core@claude-workbench`** — provides the memory vault MCP and session infrastructure
- **Apple Notes MCP** — reads and writes BuJo notes in the `📓 Journal` folder
- **Scheduled tasks MCP** — registers and triggers ritual schedules

## Installation

```
claude plugin marketplace add mike-bronner/claude-workbench
claude plugin install bullet-journal@claude-workbench
```

Then run the setup command:

```
/workbench:bujo-setup
```

This walks through configuration, deploys scheduled tasks, and offers to clean up legacy tasks.

## Commands

| Command | Description |
|---|---|
| `/workbench:bujo-setup` | Configure the plugin, deploy scheduled tasks, clean up legacy tasks |
| `/workbench:bujo-daily-ritual` | Run the daily ritual on-demand |
| `/workbench:bujo-weekly-ritual` | Run the weekly ritual on-demand |
| `/workbench:bujo-monthly-ritual` | Run the monthly ritual on-demand |
| `/workbench:bujo-yearly-ritual` | Run the yearly ritual on-demand |

## Ritual schedule

| Ritual | Default Schedule | Prerequisite |
|---|---|---|
| Yearly | Jan 1, 6:30am | None |
| Monthly | 1st of month, 6:40am | Yearly (if Jan 1) |
| Weekly | Sunday, 6:50am | Monthly (if 1st) |
| Daily | Every day, 7:00am | Weekly (if Sunday), Monthly (if 1st), Yearly (if Jan 1) |

When multiple rituals fall on the same day, they cascade top-down. Each ritual checks that its prerequisite higher-level ritual has run.

## Configuration

Config lives at `~/.claude/plugins/data/bullet-journal-claude-workbench/config.json`:

```json
{
  "timezone": "America/Phoenix",
  "journal_folder": "📓 Journal",
  "daily_note_format": "YYYY-MM-DD — Weekday",
  "journal_index_note": "📓 Journal Index",
  "future_log_note": "Future Log",
  "goals_note": "Goals",
  "daily_data_note": "📅 Daily Data",
  "second_brain_note": "🧠 Claude's Second Brain",
  "schedules": {
    "daily_ritual":   { "enabled": true, "cron": "0 7 * * *",   "task_id": "daily-bujo-ritual" },
    "weekly_ritual":  { "enabled": true, "cron": "50 6 * * 0",  "task_id": "weekly-bujo-ritual" },
    "monthly_ritual": { "enabled": true, "cron": "40 6 1 * *",  "task_id": "monthly-bujo-ritual" },
    "yearly_ritual":  { "enabled": true, "cron": "30 6 1 1 *",  "task_id": "yearly-bujo-ritual" }
  }
}
```

## Journal Index

The plugin defines the *process* (when to run, what steps to follow). The `📓 Journal Index` Apple Note defines the *rules* (signifiers, formatting, section layouts, migration logic). You must create this note yourself — the plugin does not auto-generate it.

## Design philosophy

- **Interactivity is the point.** Rituals prompt for reflection and wait. They never auto-complete or fabricate answers. A blank Reflections section is better than an invented one.
- **Dig deeper.** Shallow answers get pushback. The whole value of a BuJo review is the friction of reconsideration.
- **Infrastructure, not persona.** The plugin is generic. Mike's specific BuJo rules live in his Journal Index, not in the plugin code.

## Updating

After running `claude plugin update bullet-journal@claude-workbench`, re-run `/workbench:bujo-setup` to sync updated ritual definitions into your scheduled tasks.
