#!/bin/sh
# Ensure the context + memory dirs exist, then inject the context-writing
# protocol into the session context via stdout.
mkdir -p "$HOME/.claude/context/archive"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
cat "$PLUGIN_ROOT/hooks/context-protocol.md"
