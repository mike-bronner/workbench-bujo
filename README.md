# workbench-bujo

BuJo ritual plugin for Claude Code. Part of the [`claude-workbench`](https://github.com/mike-bronner/claude-workbench) marketplace.

## What this is

An interactive Bullet Journal system that runs daily, weekly, monthly, and yearly rituals against Apple Notes. Inspired by Ryder Carroll's BuJo method — adapted for a persistent AI collaborator.

Every ritual is interactive: it prompts for reflection, waits for real answers, and processes experiences (not just tasks). Every unfinished or dropped item gets individually inspected — Ryder's "friction of reconsideration" principle, preserved in a digital context. Mid-day, Claude watches for experientially-significant moments and can capture them to today's log on the fly.

## Architecture

```
                      ┌──────────────────────────┐
                      │  /bujo  (or scheduled)   │  ← single entry point
                      └────────────┬─────────────┘
                                   │ spawns
                                   ▼
                      ┌──────────────────────────┐
                      │  bujo-orchestrator       │  ← sub-agent
                      │  • picks tiers by date   │     returns structured plan:
                      │  • scope per tier        │     scope + reflection_focus
                      │  • identifies experiences│     + warnings
                      │  • flags gaps            │
                      └────────────┬─────────────┘
                                   │ plan
                                   ▼
      You  ↔  Hobbes (main)  ◁──── drives interactive ritual protocol
              │                    (check-in, item review, reflection,
              │                     scaffold, planning)
              │
              │   dispatches verbs
              ▼
      ┌───────────────────────┐
      │   bujo-scribe MCP     │   Apple Notes I/O, parser, renderer,
      │                       │   rules.yaml enforcement, backends
      └──────────┬────────────┘
                 │
                 ▼
         📝  Apple Notes
              📓 Journal/
```

**Three layers, three responsibilities:**

| Layer | Owns |
|---|---|
| 🎯 **Orchestrator** (sub-agent) | Date math, which tiers run, scope, experience identification, gap detection, warnings |
| 📜 **Ritual skills** (main conversation) | Interactive protocol — check-in, item-by-item review, reflection, planning |
| 🖋️ **bujo-scribe MCP** (tool server) | All Apple Notes I/O, BuJo parser/renderer, signifier rules, invariants |

Swap backends (Obsidian, plain markdown, Notion, etc.) by adding a new `NotebookBackend` to the MCP. The interactive ritual protocol doesn't change.

## Prerequisites

- **`workbench-core@claude-workbench`** — memory vault, session infrastructure, execution-aware learnings
- **`bujo-scribe-mcp`** (bundled) — the MCP server the plugin launches for all BuJo storage work
- **Scheduled tasks MCP** — registers and triggers the ritual schedule
- **macOS** — the shipping `apple_notes` backend uses AppleScript via `osascript`. Other OSes unblocked by adding a new backend.

## Installation

### 1. Install the plugin

**Once the marketplace is published** (includes `workbench-bujo` in its manifest):

```
claude plugin marketplace add mike-bronner/claude-workbench
claude plugin install workbench-bujo@claude-workbench
```

**Currently — pre-publication / local development:** the `claude-workbench` marketplace still references the older `bullet-journal` name, and `workbench-bujo` hasn't been added to its manifest yet. Install the plugin locally by pointing Claude Code at your clone:

```
# Clone if you haven't
git clone https://github.com/mike-bronner/workbench-bujo
cd workbench-bujo

# Install from your local checkout
claude plugin install /absolute/path/to/workbench-bujo
```

After installation, restart Claude Code so the plugin's agents, skills, commands, and MCP server are picked up.

### 2. Install the scribe MCP

The scribe MCP is distributed as a separate Python package so non-plugin users can pull it too.

**Once published to PyPI:**

```
uv tool install bujo-scribe-mcp
```

**Currently — pre-publication:** `bujo-scribe-mcp` is not yet on PyPI. The package lives as source only on the author's machine (no public remote yet). If you're Mike (or someone Mike has given the source to), install from the local directory:

```
uv tool install --from /absolute/path/to/bujo-scribe-mcp bujo-scribe-mcp
```

Verify it's on your PATH:

```
which bujo-scribe-mcp
# /Users/you/.local/bin/bujo-scribe-mcp
```

When the package source changes, reinstall:

```
uv tool install --from /absolute/path/to/bujo-scribe-mcp bujo-scribe-mcp --force --reinstall
```

**Publication roadmap:** once `bujo-scribe-mcp` is pushed to a public GitHub repo and tagged, it will be publishable to PyPI. Until then, `uv tool install bujo-scribe-mcp` (bare name) won't work.

### 3. Run setup

Inside Claude Code:

```
/workbench-bujo:bujo-setup
```

Walks configuration, deploys the single scheduled task, offers legacy cleanup.

## Commands

| Command | Description |
|---|---|
| `/workbench-bujo:bujo` | **Primary entry point.** Orchestrator plans, interactive ritual protocol runs for each applicable tier. |
| `/workbench-bujo:bujo-capture` | Capture a single experientially-significant moment to today's daily log, mid-session. Fast. |
| `/workbench-bujo:bujo-setup` | Configure the plugin, deploy the scheduled task, clean up legacy per-tier tasks. |
| `/workbench-bujo:bujo-daily-ritual` | Ad-hoc daily only (forces tier=daily). |
| `/workbench-bujo:bujo-weekly-ritual` | Ad-hoc weekly only. |
| `/workbench-bujo:bujo-monthly-ritual` | Ad-hoc monthly only. |
| `/workbench-bujo:bujo-yearly-ritual` | Ad-hoc yearly only. |

Hobbes also **proactively** invokes the capture skill when he notices a significant moment during conversation — a realization, a meaningful decision, a breakthrough, an emotionally-notable beat. He checks with you before logging ("Worth capturing: … Adding to today?"). Routine tool calls and small code edits are filtered out.

## Ritual schedule

**One scheduled task** — not four. The orchestrator decides what runs each day.

| Task | Default Cron | Behavior |
|---|---|---|
| `bujo-ritual` | `0 7 * * *` | Runs daily at 7am. Orchestrator fires any applicable higher tiers in strict order: yearly (Jan 1) → monthly (1st of month) → weekly (Sunday) → daily (always). |

No prerequisite chain is needed because the unified flow always runs tiers in the correct order.

## How rituals work

### Tier modes

Not every tier does the same thing.

| Tier | Mode | Check-in (how did it go?) | Item review depth | Energy check | Extra |
|---|---|---|---|---|---|
| daily | **full** | ✅ | 🔬 reflective (feelings-aware) | ✅ | — |
| weekly | **light** | ❌ skipped | 📋 disposition-only (no feelings) | ❌ skipped | — |
| monthly | **full** | ✅ | 🔬 reflective | ✅ | — |
| yearly | **full** | ✅ | 🔬 reflective | ✅ | Future Log rollover |

Weekly is deliberately lighter — it's a BuJo community extension (not in Ryder's canonical method), kept for planning value but without the introspection layer.

### The universal protocol

Every tier follows the same six steps — the mode matrix above dictates which steps are full vs. skipped.

1. **Read scope** — orchestrator tells Hobbes which notes to fetch (`yesterday`, last week's dailies, last month's dailies, last year's monthlies).
2. **Check-in + capture missing** *(full tiers only)* — "How did [period] go? And anything you want to add?" Both the reflection on how the period landed AND late-arriving captures fold into a single step.
3. **Item-by-item review** — every unfinished or dropped item from the scope gets inspected individually. **No batching.** Full tiers probe for feelings and meaning; weekly is disposition-only (carry / drop / schedule / complete).
4. **Scaffold the new period** — create today/this-week/this-month/this-year entry with migrated items, events, Future Log surfaces. For **yearly**, a Future Log rollover step follows — stale entries get walked with you and migrated/dropped.
5. **Planning + intention** *(full tiers: energy-aware; light tier: straight planning)* — full tiers start with an energy/feeling check ("How are you arriving into today?") before priorities. Weekly skips the check and asks directly: "What's the shape of this week?"
6. **Close** — one line. The note is the artifact.

### Reflection is about processing experiences

Reflection isn't about completing a task-review checklist. It's about *processing experiences* — noticing what carried weight, surfacing feelings (when they're there), tracing what they point at, and deciding what to do with that.

The orchestrator does **experience identification** before Hobbes talks to you: it reads the scoped notes and picks out salient items (insights, completed-after-friction, migrated 3+ times, dropped items, pattern shifts) plus cross-references calendar events for **gaps** — things that happened but weren't captured. It returns these as `reflection_focus` with neutral opener questions ("what opened up for you?" / "anything to say about this?").

During the ritual, Hobbes uses those openers. If you respond with feelings, he digs. If you respond factually and move on, he accepts that. **"No feeling here" is a complete and respected answer** — feelings aren't forced.

## Configuration

Config lives at `~/.claude/plugins/data/workbench-bujo-claude-workbench/config.json`:

```json
{
  "timezone": "America/Phoenix",
  "journal_folder": "📓 Journal",
  "daily_note_format": "YYYY-MM-DD — Weekday",
  "journal_index_note": "📓 Journal Index",
  "future_log_note": "Future Log",
  "goals_note": "Goals",
  "second_brain_note": "🧠 Claude's Second Brain",
  "schedules": {
    "bujo": {
      "enabled": true,
      "cron": "0 7 * * *",
      "task_id": "bujo-ritual"
    }
  }
}
```

Calendar and Reminders data is fetched directly by the scribe MCP via a pluggable `DataSourceBackend` — no staging note required.

## Customizing your BuJo vocabulary

Ryder Carroll's method draws a deliberate line between two kinds of markers, and they're customized differently:

- **Signifiers** (prefixes like `✽` priority, `!` inspiration, `◉` explore) — decorate an existing task/event/note with emphasis, discovery, or uncertainty. Ryder *explicitly encourages* inventing your own. **This is the primary personalization surface.**
- **Bullet types** (base markers like `•` task, `○` event, `—` note) — describe what *kind* of thing the entry is. Ryder is more cautious here: start with the core six and add only when your information genuinely doesn't fit.

**Heuristic:**

| You want to express... | Use |
|---|---|
| "A task that's *also* X" (urgent, financial, delegated, waiting, etc.) | **Prefix extension** |
| "Not a task/event/note — a genuinely new *kind* of thing" | **Base extension** |

Nine times out of ten, a prefix extension does the job. Reach for a base extension only when a prefix won't capture it.

### Where custom rules live

Drop a file at `~/.claude/plugins/data/workbench-bujo-claude-workbench/rules.yaml` with only the keys you want to override. The MCP deep-merges it onto the shipped defaults at startup. Missing file = defaults only.

```yaml
# ~/.claude/plugins/data/workbench-bujo-claude-workbench/rules.yaml

signifiers:
  # 🎯 Prefix extensions — prefer these (Ryder's "signifiers" sense)
  prefix_extensions:
    - key: delegated
      char: "→"
      description: "Delegated to someone else"
    - key: waiting
      char: "…"
      description: "Waiting on external"

  # 📐 Base extensions — use sparingly
  extensions:
    - key: expense
      char: "$"
      class: task         # bucket for setup-time ordering + type filters
      description: "Financial entry"
    - key: question
      char: "?"
      class: note
```

Validation runs at MCP startup — typos, key/char collisions with built-ins, or duplicate entries surface as clear errors, not silent drift.

## Journal Index

The plugin defines the *process* (when to run, what steps to follow). BuJo *rules* (signifiers, formatting, setup-time ordering, carry-forward, naming, migration logic) live in the MCP's `rules.yaml` — shipped defaults plus your optional override. The `📓 Journal Index` Apple Note is transitioning into a human-readable *render* of the active rules; for now it can exist as a manual reference, but it's no longer the source of truth.

## Design philosophy

- **Interactivity is the point.** Rituals prompt for reflection and wait. They never auto-complete or fabricate answers. A blank reflection is better than an invented one.
- **Reflection is experience processing, not task auditing.** Feelings surface when they're there; they're not forced. "No feeling here" is a complete answer.
- **Friction for every item.** Every unfinished or dropped item gets individually inspected. Ryder's "friction of reconsideration" principle — digital version. No batching.
- **Mechanical work is offloaded.** Apple Notes reads/writes, BuJo formatting, migration logic — all owned by the scribe MCP. The plugin's skills orchestrate; they don't format.
- **Write prescriptive, read lenient.** The scribe emits one canonical HTML form; it tolerates Apple Notes' variations on read. See [`docs/apple-notes-quirks.md`](https://github.com/mike-bronner/bujo-scribe-mcp/blob/main/docs/apple-notes-quirks.md) for quirks and mitigations.
- **Live in the Daily Log.** Rapid Logging is a core BuJo principle — you're meant to capture meaningful moments throughout the day, not just at ritual time. Hobbes assists by proactively noticing and asking to log experientially-significant moments mid-conversation.

## Further reading

- [`docs/scribe-contract.md`](docs/scribe-contract.md) — MCP verb vocabulary and invariants
- [`docs/ritual-flow.html`](docs/ritual-flow.html) — swimlane diagram of the ritual flow
- [`docs/rules-decisions.md`](docs/rules-decisions.md) — 7-gap audit + resulting rules
- [`docs/open-issues.md`](docs/open-issues.md) — deferred implementation items (Calendar/Reminders backend, etc.)

## Versioning

**The plugin and its scribe MCP use lockstep versioning.** `workbench-bujo@X.Y.Z` always expects `bujo-scribe-mcp@X.Y.Z` — never mix versions. When one bumps, the other bumps to match, even if the change was one-sided. This avoids the compatibility-matrix confusion of two independent version numbers for a bundled system.

## Updating

**Once published** — from the marketplace:

```
claude plugin update workbench-bujo@claude-workbench
```

**Pre-publication / local install:** re-install from your clone:

```
cd /path/to/workbench-bujo && git pull
claude plugin install /absolute/path/to/workbench-bujo  # re-installs fresh
```

Either way, re-run `/workbench-bujo:bujo-setup` to sync the scheduled-task prompt with the updated ritual definitions.

Update the scribe MCP when it changes:

```
# Once on PyPI:
uv tool install --upgrade bujo-scribe-mcp

# Pre-publication (from your local clone):
cd /path/to/bujo-scribe-mcp && git pull
uv tool install --from /absolute/path/to/bujo-scribe-mcp bujo-scribe-mcp --force --reinstall
```
