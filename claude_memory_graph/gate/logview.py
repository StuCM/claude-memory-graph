"""`claude-memory-graph log`: the state home's jsonl logs, one readable line
per entry (formerly `claude-hooks log`)."""

import json
import time

from ..hookcore import state_home


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


