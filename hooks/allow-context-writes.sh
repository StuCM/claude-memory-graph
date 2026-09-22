#!/bin/sh
# PreToolUse: pre-approve writes to the session context log.
#
# The context protocol asks the model to append after every few exchanges,
# and the Stop hook blocks the turn until it does. In manual approval mode
# that means a permission prompt every few turns for a file the user has
# already opted into by installing the plugin — enough friction that the
# capture loop stops being used. So Write/Edit calls whose target is inside
# the context directory are allowed here; every other call gets no decision
# and falls through to the normal permission flow.
#
# Scope is deliberately narrow: the containment check is on the resolved
# real path (a symlink or ../ escape does not count), and Bash is NOT
# covered — auto-approving a shell command because it mentions a path is
# not the same trade.
#
# Fail open: no python, bad JSON, odd payload -> no output -> normal prompt.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -c '
import json, os, sys

try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
if data.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
    raise SystemExit(0)
target = (data.get("tool_input") or {}).get("file_path") or ""
context_dir = os.environ.get("CLAUDE_CONTEXT_DIR") or os.path.expanduser("~/.claude/context")
try:
    context_dir = os.path.realpath(context_dir)
    inside = os.path.commonpath([context_dir, os.path.realpath(target)]) == context_dir
except (OSError, ValueError):
    raise SystemExit(0)
if inside:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "memory-graph: session context log",
    }}))
'
