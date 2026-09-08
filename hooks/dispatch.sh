#!/bin/sh
# Route a Claude Code hook event through hook-kit's dispatcher. Fast and
# fail-open — if python/uv is unavailable, inject nothing and exit 0.
EVENT="${1:?hook event name required}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
PY="$PLUGIN_ROOT/.venv/bin/python"
# A venv can exist but be stale/partial (e.g. a git pull bumped the code past
# what .venv has installed) — then `python -m claude_hook_kit` fails to import
# and every hook silently no-ops. So don't exec blindly: try it, and on ANY
# non-zero exit (dispatch itself is fail-open and always exits 0 when healthy)
# fall through to `uv run`, which re-syncs the venv before running.
if [ -x "$PY" ]; then
  "$PY" -m claude_hook_kit dispatch "$EVENT" && exit 0
fi
command -v uv >/dev/null 2>&1 || exit 0
exec uv run --quiet --project "$PLUGIN_ROOT" python -m claude_hook_kit dispatch "$EVENT"
