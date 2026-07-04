#!/bin/sh
# Per-prompt gate: ambient recall + context nudge. Fast and fail-open —
# if python/uv/the store is unavailable, inject nothing and exit 0.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
PY="$PLUGIN_ROOT/.venv/bin/python"
if [ -x "$PY" ]; then
  exec "$PY" -m claude_memory_graph.gate
fi
command -v uv >/dev/null 2>&1 || exit 0
exec uv run --quiet --project "$PLUGIN_ROOT" python -m claude_memory_graph.gate
