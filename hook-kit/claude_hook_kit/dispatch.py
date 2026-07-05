"""The dispatcher: one CLI wired into Claude Code's hooks.json.

    claude-hooks dispatch <EventName>   read hook JSON on stdin, run enabled
                                        extensions, print injected context
    claude-hooks list                   discovered/enabled extensions
    claude-hooks enable <name>
    claude-hooks disable <name>
    claude-hooks state [session_id]     debug: dump session state

Contracts (docs/ORCHESTRATION.md):
- fail open: extension errors go to stderr; exit code is always 0
- core state is advanced on every dispatch, whether or not extensions run
- extension output strings are concatenated to stdout (context injection)
"""

import argparse
import json
import sys
import traceback

from .extension import HookContext, EVENT_METHODS
from .state import StateStore, state_home, _read_json
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
    for name in registry.enabled_names():
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
        except Exception:
            print(f"[hook-kit] extension '{name}' failed on {event}:", file=sys.stderr)
            traceback.print_exc()

    store.save()
    return "\n\n".join(outputs)


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
    args = parser.parse_args()

    if args.cmd == "dispatch":
        try:
            out = run_dispatch(args.event, _read_payload())
            if out:
                print(out)
        except Exception:
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


if __name__ == "__main__":
    main()
