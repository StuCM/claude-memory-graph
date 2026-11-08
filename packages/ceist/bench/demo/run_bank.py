"""Run the demo question bank through starches-demo's ask.answer and print what changed.

    cd /home/stuart/git/personal/starches-demo/ask
    PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py [--write]

Exits 1 if a question that was right is no longer right, or a new wrong answer appears.

    ... run_bank.py --set <train.json | holdout.json>   # a `ceist questions generate` set

scores each generated question by comparing Ceist's plan with its target, its {Model}
placeholders filled from the demo's own record names. Prints the counts; exits 0.
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
        if not refused and o.get("want") and a.get("understood") != o["want"]:
            return "wrong"      # a record's field and the bare record both total 1
        return "refused" if refused else ("right" if o["count"] is None or got == o["count"] else "wrong")
    if o["expect"] == "refuse":
        return "right" if refused else "wrong"
    if refused:
        return "refused-should-answer"
    return "right" if o["count"] is not None and got == o["count"] else "wrong"


def structural(path):
    from ceist import interpret
    from ceist.questions import fill, score, target_of
    v, _, matcher, _ = ask.startup()
    now = Counter()
    for o in json.loads(Path(path).read_text())["questions"]:
        q = fill(o["q"], v)
        if q is None:
            now["no record to fill"] += 1
            continue
        m = interpret(v, q, matcher=matcher)
        s = score(o, m)
        now[s] += 1
        if s not in ("right", "right refusal"):
            print(f"{s}: {q} | want {o.get('target') or o.get('reason')} | got {target_of(m) or m.refused}")
    print(dict(now))


def main():
    if "--set" in sys.argv:
        return structural(sys.argv[sys.argv.index("--set") + 1])
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
