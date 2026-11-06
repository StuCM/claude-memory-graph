"""Run the demo question bank through starches-demo's ask.answer and print what changed.

    cd /home/stuart/git/personal/starches-demo/ask
    PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py [--write]

Exits 1 if a question that was right is no longer right, or a new wrong answer appears.
"""
import json
import sys
from collections import Counter
from pathlib import Path

BANK = Path(__file__).with_name("questions.json")
sys.path.insert(0, str(Path.cwd()))
import ask  # noqa: E402  (the demo's ask.py, from the current directory)


def status(o, a):
    got = a.get("total")
    refused = bool(a.get("refused")) or got is None
    if o["expect"] == "answer":
        return "refused" if refused else ("right" if o["count"] is None or got == o["count"] else "wrong")
    if o["expect"] == "refuse":
        return "right" if refused else "wrong"
    if refused:
        return "refused-should-answer"
    return "right" if o["count"] is not None and got == o["count"] else "wrong"


def main():
    doc = json.loads(BANK.read_text())
    v, r, m, rec = ask.startup()
    regressions, now = [], Counter()
    for o in doc["questions"]:
        a = ask.answer(o["q"], v, r, m, rec)
        s = status(o, a)
        now[(o["expect"], s)] += 1
        if s != o["status"]:
            print(f"{o['status']} -> {s}: {o['q']} | {a.get('understood')} | {a.get('total')} | {(a.get('refused') or '')[:90]}")
            if o["status"] == "right" or s == "wrong":
                regressions.append(o["q"])
        if "--write" in sys.argv:
            o.update(status=s, understood=a.get("understood"), got=a.get("total"), refused=a.get("refused"))
    print(dict(now))
    if "--write" in sys.argv:
        BANK.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    if regressions:
        print("REGRESSIONS:", *regressions, sep="\n  ")
        sys.exit(1)


main()
