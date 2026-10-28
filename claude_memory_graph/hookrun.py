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
     "enabled": [extension names; default: memory-recall, context-counter],
     "remote":  {"url", "token", "lookups"} when memory lives on a server
                (optional; lookups "server", the default, asks the server
                to run the gate's graph reads; "replica" downloads the
                graph and reads it here),
     "gate":    gate.json keys set in the plugin's settings menu (optional;
                they win over gate.json for this call)}

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
import os
import sys

from .hookcore import EVENT_METHODS, HookContext, advance_core, log_error

DEFAULT_ENABLED = ("memory-recall", "context-counter")


def _extensions() -> dict:
    from .gate.nudge import ContextCounterExtension
    from .gate.recall import RecallExtension
    from .gate.review import ReviewExtension
    return {cls.name: cls for cls in (RecallExtension, ContextCounterExtension, ReviewExtension)}


def _use_replica(remote: dict, force: bool, errors: list) -> None:
    """Remote mode: the gate reads a local replica of the server's graph
    (remote.py). This process handles one event, so setting the environment
    here scopes it to this call."""
    from . import remote as remote_mod
    os.environ[remote_mod.SERVER_ENV] = str(remote["url"])
    os.environ[remote_mod.TOKEN_ENV] = str(remote.get("token") or "")
    folder = remote_mod.fetch_replica(force=force)
    os.environ["MEMORY_GRAPH_PATH"] = str(folder or remote_mod.replica_dir())
    if folder is None:
        errors.append(f"memory server {remote['url']}: no replica yet (unreachable?)")


# What the memory server runs for a client in server-lookup mode: the
# extension events that read the graph. Everything else stays on the client.
SERVER_EVENTS = {("memory-recall", "SessionStart"), ("memory-recall", "UserPromptSubmit")}


def run_extension(name: str, event: str, payload: dict, core: dict, state: dict,
                  global_state: dict) -> str:
    """One extension's handler for one event; its state dicts are updated in place."""
    cls = _extensions().get(name)
    method = EVENT_METHODS.get(event)
    if cls is None or method is None:
        return ""
    ctx = HookContext(event=event, payload=payload, core=core, state=state,
                      global_state=global_state)
    result = getattr(cls(), method)(ctx)
    return str(result).rstrip() if result else ""


def _on_server(name: str, event: str, payload: dict, core: dict, state: dict,
               global_state: dict, gate: dict) -> str:
    """run_extension, run by the memory server against its own graph
    (/api/hook). Its log lines come back and are written here, so the
    pane and the miss report see them."""
    from . import remote as remote_mod
    from .hookcore import append_jsonl
    reply = remote_mod.run_hook({"extension": name, "event": event, "payload": payload,
                                 "core": core, "state": state, "global": global_state,
                                 "gate": gate})
    state.clear(); state.update(reply.get("state") or {})
    global_state.clear(); global_state.update(reply.get("global") or {})
    for filename, entry in reply.get("logs") or []:
        if filename in ("injections.jsonl", "capture.jsonl"):
            append_jsonl(filename, entry)
    return str(reply.get("output") or "")


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
    remote = request.get("remote") or {}
    gate = request.get("gate") or {}
    if gate:
        from .gate import runtime
        runtime.override(gate)
    on_server = bool(remote.get("url")) and remote.get("lookups", "server") == "server"
    if on_server:
        from . import remote as remote_mod
        from .gate.runtime import SERVER_LOOKUPS_ENV
        os.environ[remote_mod.SERVER_ENV] = str(remote["url"])
        os.environ[remote_mod.TOKEN_ENV] = str(remote.get("token") or "")
        os.environ[SERVER_LOOKUPS_ENV] = "server"
    elif remote.get("url"):
        _use_replica(remote, force=event == "SessionStart", errors=errors)
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
            if name not in available:
                continue
            try:
                args = (name, event, payload, core, state.setdefault(name, {}),
                        global_state.setdefault(name, {}))
                result = (_on_server(*args, gate) if on_server and (name, event) in SERVER_EVENTS
                          else run_extension(*args))
                if result:
                    outputs.append(result)
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
