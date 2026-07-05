"""The dispatcher: one CLI wired into Claude Code's hooks.json.

    claude-hooks dispatch <EventName>   read hook JSON on stdin, run enabled
                                        extensions, print injected context
    claude-hooks list                   discovered/enabled extensions
    claude-hooks enable <name>
    claude-hooks disable <name>
    claude-hooks state [session_id]     debug: dump session state
    claude-hooks log [file] [-n N] [-f] pretty-print a jsonl log from the
                                        state home (default injections.jsonl)

Contracts (docs/ORCHESTRATION.md):
- fail open: extension errors go to stderr; exit code is always 0
- core state is advanced on every dispatch, whether or not extensions run
- extension output strings are concatenated to stdout (context injection)
"""

import argparse
import json
import sys
import time
import traceback

from .extension import HookContext, EVENT_METHODS
from .state import StateStore, state_home, _read_json, log_error
from . import registry


def _read_payload() -> dict:
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def run_dispatch(event: str, payload: dict) -> str:
    method_name = EVENT_METHODS.get(event)
    if method_name is None:
        return ""

    store = StateStore(payload.get("session_id", "default"))
    store.touch_core(event, payload)

    outputs: list[str] = []
    available = registry.discover()
    for name in registry.enabled_names(available):
        cls = available.get(name)
        if cls is None:
            continue
        try:
            ext = cls()
            ctx = HookContext(
                event=event,
                payload=payload,
                core=store.core,
                state=store.extension(name),
                global_state=store.global_extension(name),
            )
            result = getattr(ext, method_name)(ctx)
            if result:
                outputs.append(str(result).rstrip())
        except Exception as exc:
            # this extension failed; log it and let the others still answer
            log_error(f"extension '{name}' on {event}", exc)
            print(f"[hook-kit] extension '{name}' failed on {event}:", file=sys.stderr)
            traceback.print_exc()

    store.save()
    return "\n\n".join(outputs)


def format_log_entry(line: str) -> str:
    """One jsonl log line -> one readable line. Known keys get a stable
    layout (time, fired marker, scores, nodes, terms); anything else is
    appended key=value, so extension-specific logs stay printable."""
    try:
        entry = dict(json.loads(line))
    except ValueError:
        return line.rstrip()
    ts = entry.pop("ts", None)
    when = time.strftime("%H:%M:%S %d/%m", time.localtime(ts)) if ts else "--:--:--"
    fired = entry.pop("fired", None)
    mark = "  --  " if fired is None else ("INJECT" if fired else "silent")
    parts = []
    for key in ("top", "rest", "project"):
        if key in entry:
            parts.append(f"{key}={entry.pop(key)}")
    if "nodes" in entry:
        parts.append("nodes[" + " | ".join(map(str, entry.pop("nodes"))) + "]")
    if "terms" in entry:
        parts.append("terms(" + " ".join(map(str, entry.pop("terms"))) + ")")
    parts.extend(f"{k}={v}" for k, v in entry.items())
    return f"{when}  {mark}  " + "  ".join(parts)


def print_log(filename: str, lines: int, follow: bool) -> None:
    path = state_home() / filename
    if not path.exists():
        print(f"No log at {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f.readlines()[-lines:]:
            print(format_log_entry(line))
        if not follow:
            return
        try:
            while True:
                line = f.readline()
                if line:
                    print(format_log_entry(line), flush=True)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(prog="claude-hooks")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dispatch", help="run enabled extensions for a hook event")
    p.add_argument("event", help="Claude Code event name, e.g. SessionStart")
    sub.add_parser("list", help="show discovered and enabled extensions")
    p = sub.add_parser("enable", help="enable a discovered extension")
    p.add_argument("name")
    p = sub.add_parser("disable", help="disable an extension")
    p.add_argument("name")
    p = sub.add_parser("state", help="dump session state (debug)")
    p.add_argument("session_id", nargs="?", default="default")
    p = sub.add_parser("log", help="pretty-print a jsonl log from the state home")
    p.add_argument("filename", nargs="?", default="injections.jsonl")
    p.add_argument("-n", "--lines", type=int, default=20, help="show last N entries (default 20)")
    p.add_argument("-f", "--follow", action="store_true", help="keep watching for new entries")
    args = parser.parse_args()

    if args.cmd == "dispatch":
        try:
            out = run_dispatch(args.event, _read_payload())
            if out:
                print(out)
        except Exception as exc:
            log_error("dispatch runtime", exc)
            traceback.print_exc()  # stderr; still exit 0 — fail open
        sys.exit(0)
    elif args.cmd == "list":
        print(registry.status())
    elif args.cmd == "enable":
        print(registry.enable(args.name))
    elif args.cmd == "disable":
        print(registry.disable(args.name))
    elif args.cmd == "state":
        path = state_home() / "sessions" / f"{args.session_id}.json"
        print(json.dumps(_read_json(path), indent=2))
    elif args.cmd == "log":
        print_log(args.filename, args.lines, args.follow)


if __name__ == "__main__":
    main()
