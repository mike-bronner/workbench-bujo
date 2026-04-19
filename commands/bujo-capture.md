---
description: Capture a single experientially-significant moment to today's BuJo daily log. Fast — no ritual, no prompts, just logs it.
---

The user invoked `/workbench-bujo:bujo-capture` — typically with content inline in the message (e.g. "/workbench-bujo:bujo-capture shipped the scribe MCP end-to-end — it felt great").

## Execution

1. Read the `bujo-capture` skill at `${CLAUDE_PLUGIN_ROOT}/skills/bujo-capture.md` for format and dispatch details.
2. Extract the capture content from Mike's message (whatever came after the command).
3. Classify the entry's BuJo type (task / event / note / insight / priority / explore).
4. Dispatch via `mcp__plugin_workbench-bujo_scribe__bujo_apply_decisions` with an `add` op on `today`.
5. Confirm in one line: "🪶 Logged: `[signifier][text]`"

If Mike's invocation is ambiguous about the content type (e.g., just "/bujo-capture the architecture shift matters"), ask once for classification — otherwise infer from the phrasing and confirm after dispatch.

## Hard rules

- **Mike already confirmed** by invoking the slash command; don't ask "should I log this?"
- **Use `bujo-scribe` MCP** — no direct Apple Notes calls.
- **Scaffold today first if needed.** If `today` doesn't exist, run `bujo_scaffold` with empty sections first, then the add.
- **One entry per invocation.** If Mike wants multiple, he invokes multiple times (or adds them during a ritual instead).
