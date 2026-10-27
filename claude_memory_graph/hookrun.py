"""One hook event, as a stateless call: JSON in on stdin, JSON out on stdout.

The plugin's mod (hooks/register.js) owns routing and session state. For
each event that needs Python — the graph, the context files, the logs — it
runs `python -m claude_memory_graph.hookrun` with:

    {"event":   "SessionStart" | "UserPromptSubmit" | "PostToolUse" |
                "Stop" | "PreCompact" | "SessionEnd",
     "payload": the classic hook input (session_id, cwd, prompt,
                transcript_path, stop_hook_active, tool_name, ...),
     "core":    the session's core state as last returned,
     "state":   {extension name: its per-session dict},
     "global":  {extension name: its cross-session dict},
     "enabled": [extension names; default: memory-recall, context-counter]}

and gets back {"output", "core", "state", "global", "errors"}. The mod
stores what comes back and hands `output` to Claude Code (additionalContext,
or a Stop block). Nothing is persisted here except the append-only logs.

Frequent events never reach this process: the mod counts digs and approves
context-file writes itself, in-process. That is the point of the split —
a Python start costs ~100ms, too much to pay on every Read and Grep.

Fail open: any error yields empty output with the error named in
`errors`, and the exit code is 0 — a broken memory layer must never break
a session.
"""

import json
import sys

from .hookcore import EVENT_METHODS, HookContext, advance_core, log_error

DEFAULT_ENABLED = ("memory-recall", "context-counter")


def _extensions() -> dict:
    from .gate.nudge import ContextCounterExtension
    from .gate.recall import RecallExtension
    from .gate.review import ReviewExtension
    return {cls.name: cls for cls in (RecallExtension, ContextCounterExtension, ReviewExtension)}


def run(request: dict) -> dict:
    event = request.get("event", "")
    payload = request.get("payload") or {}
    core = dict(request.get("core") or {})
    state = {k: dict(v) for k, v in (request.get("state") or {}).items()}
    global_state = {k: dict(v) for k, v in (request.get("global") or {}).items()}
    enabled = request.get("enabled") or list(DEFAULT_ENABLED)
    errors: list[str] = []
    outputs: list[str] = []

    method = EVENT_METHODS.get(event)
    if event == "SessionStart":
        try:  # the context protocol writes here; the archive receives distilled files
            from .gate.nudge import _context_dir
            (_context_dir() / "archive").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"context dir: {exc}")
    if method is not None:
        advance_core(core, event, payload)
        available = _extensions()
        for name in enabled:
            cls = available.get(name)
            if cls is None:
                continue
            try:
                ctx = HookContext(
                    event=event, payload=payload, core=core,
                    state=state.setdefault(name, {}),
                    global_state=global_state.setdefault(name, {}),
                )
                result = getattr(cls(), method)(ctx)
                if result:
                    outputs.append(str(result).rstrip())
            except Exception as exc:  # one extension failing never silences the rest
                log_error(f"extension '{name}' on {event}", exc)
                errors.append(f"{name}: {type(exc).__name__}: {exc}")

    return {"output": "\n\n".join(outputs), "core": core, "state": state,
            "global": global_state, "errors": errors}


def main() -> None:
    try:
        raw = sys.stdin.read()
        request = json.loads(raw) if raw.strip() else {}
        response = run(request if isinstance(request, dict) else {})
    except Exception as exc:
        log_error("hookrun", exc)
        response = {"output": "", "errors": [f"hookrun: {type(exc).__name__}: {exc}"]}
    sys.stdout.write(json.dumps(response))


if __name__ == "__main__":
    main()
