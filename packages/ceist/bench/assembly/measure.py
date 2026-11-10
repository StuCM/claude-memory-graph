"""Strict wiring against schema assembly (task 049): the tally, tractable % and time per
question in each mode, then every question whose result moved.

    cd /home/stuart/git/personal/starches-demo/ask
    PYTHONPATH=<worktree>/packages/ceist/src .venv/bin/python \\
        <worktree>/packages/ceist/bench/assembly/measure.py bank | reorder | <generated set.json>

Tractable: the question's pieces have exactly one consistent reading (PRECISE's measure).
Under strict word rules that is a question by the is-question gate with no filler ignored.
"""
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import ask  # noqa: E402  (the demo's ask.py, from the current directory)

from ceist import interpret, narrate  # noqa: E402
from ceist.assemble import FILLER, assemble  # noqa: E402
from ceist.ground import is_question  # noqa: E402
from ceist.questions import fill, score, target_of  # noqa: E402

HERE = Path(__file__).parent
BANKS = {"bank": HERE.parent / "demo" / "questions.json", "reorder": HERE / "reorder.json"}
MODES = ("strict", "schema")


def status(o, a):
    """bench/demo/run_bank.py's status: the bank's own scoring of an answer."""
    got = a.get("total")
    refused = bool(a.get("refused")) or got is None
    if o["expect"] == "answer":
        if not refused and o.get("want") and a.get("understood") != o["want"]:
            return "wrong"
        return "refused" if refused else ("right" if o["count"] is None or got == o["count"] else "wrong")
    if o["expect"] == "refuse":
        return "right" if refused else "wrong"
    if refused:
        return "refused-should-answer"
    return "right" if o["count"] is not None and got == o["count"] else "wrong"


def canonical(m) -> str:
    meaning = m.plan or m.detail
    return narrate(meaning, canonical=True) if meaning else ""


def run(items, mode, bank, v, r, matcher, rec):
    os.environ["CEIST_ASSEMBLY"] = mode
    out = []
    for o in items:
        q = o["q"] if bank else fill(o["q"], v)
        if q is None:
            continue
        start = time.perf_counter()
        m = interpret(v, q, matcher=matcher)
        took = time.perf_counter() - start
        if "from" in o:
            a = ask.answer(q, v, r, matcher, rec)
            want = canonical(interpret(v, o["from"], matcher=matcher, assembly="strict"))
            s = ("refused" if a.get("refused") else
                 "right" if canonical(m) == want and a.get("total") == o["count"] else "wrong")
            said = a.get("understood") or a.get("refused")
        elif bank:
            a = ask.answer(q, v, r, matcher, rec)
            s, said = status(o, a), a.get("understood") or a.get("refused")
        else:
            s, said = score(o, m), target_of(m) or m.refused
        filler = FILLER if mode == "schema" else frozenset()
        _s, answers, _o = assemble(v, q, None, matcher, filler)
        tractable = len(answers) == 1 and (mode == "schema" or is_question(q))
        out.append({"q": q, "status": s, "said": said, "ms": took * 1000, "tractable": tractable})
    return out


def main():
    which = sys.argv[1]
    path = BANKS.get(which, Path(which))
    items = json.loads(path.read_text())["questions"]
    bank = which in BANKS
    v, r, matcher, rec = ask.startup()
    rows = {mode: run(items, mode, bank, v, r, matcher, rec) for mode in MODES}
    print(f"\n{which}: {len(rows['strict'])} questions\n")
    kinds = sorted({x["status"] for mode in MODES for x in rows[mode]})
    print("| mode | " + " | ".join(kinds) + " | tractable | median ms | worst ms |")
    print("|---" * (len(kinds) + 4) + "|")
    for mode in MODES:
        got = Counter(x["status"] for x in rows[mode])
        ms = [x["ms"] for x in rows[mode]]
        tractable = sum(x["tractable"] for x in rows[mode]) / len(ms)
        print(f"| {mode} | " + " | ".join(str(got[k]) for k in kinds)
              + f" | {tractable:.0%} | {statistics.median(ms):.1f} | {max(ms):.1f} |")
    print("\nmoved (strict → schema):")
    for a, b in zip(rows["strict"], rows["schema"]):
        if a["status"] != b["status"]:
            print(f"- {a['status']} → {b['status']}: {a['q']}\n    strict: {a['said']}\n"
                  f"    schema: {b['said']}")


main()
