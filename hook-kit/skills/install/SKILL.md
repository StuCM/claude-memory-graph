---
name: install
description: Enable or disable hook-kit extensions (e.g. memory recall auto-prime, context counter). Use when the user says "install the recall hook", "enable the counter hook", "list hook extensions", or "/hook-kit:install <name>".
---

# Install / manage hook-kit extensions

hook-kit dispatches Claude Code hook events to *extensions* — small classes provided by any
installed package (memory-graph ships `memory-recall` and `context-counter`). Discovered
extensions do nothing until enabled.

## Steps

1. **See what's available:**
   ```sh
   uvx --from "${CLAUDE_PLUGIN_ROOT}" claude-hooks list
   ```
   (If this skill runs from the memory-graph plugin, its plugin root works the same — both
   environments contain the `claude-hooks` CLI.)

2. **Enable/disable what the user asked for:**
   ```sh
   uvx --from "${CLAUDE_PLUGIN_ROOT}" claude-hooks enable memory-recall
   uvx --from "${CLAUDE_PLUGIN_ROOT}" claude-hooks disable context-counter
   ```
   An unknown name errors with the discovered list — relay it and let the user pick.

3. **Confirm:** re-run `list` and show the result. Changes apply from the next hook event; no
   restart needed.

Debug: `claude-hooks state [session_id]` dumps the session's core + extension state.
