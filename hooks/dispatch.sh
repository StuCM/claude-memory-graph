#!/bin/sh
# Route a Claude Code hook event through hook-kit's dispatcher. Fast and
# fail-open — if python/uv is unavailable, inject nothing and exit 0.
EVENT="${1:?hook event name required}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
PY="$PLUGIN_ROOT/.venv/bin/python"
if [ -x "$PY" ]; then
  exec "$PY" -m claude_hook_kit dispatch "$EVENT"
fi
command -v uv >/dev/null 2>&1 || exit 0
exec uv run --quiet --project "$PLUGIN_ROOT" python -m claude_hook_kit dispatch "$EVENT"
