"""The starches-demo questions through the demo's own `ask.answer`, once with its
hand-tuned vocabulary (the HER bundle, re-keyed) and once with a bundle from
`ceist vocab pipeline`; a markdown table of what changed.

    PYTHONPATH=<worktree>/packages/ceist/src CEIST_HER=<worktree>/packages/ceist/bench/her \\
      <worktree>/.venv-ceist/bin/python packages/ceist/bench/demo_compare.py \\
      /home/stuart/git/personal/starches-demo/ask <out>/bundle.json [--questions more.txt] > compare.md

The questions are the README's (demo, counties, extras, known gaps); add
paraphrases one per line with --questions.
"""

import argparse
import json
import sys
from pathlib import Path

README = [
    "which tales feature Cú Chulainn?", "which tales belong to the Ulster Cycle?",
    "how many tales belong to the Fenian Cycle?", "which figures are associated with Conchobar mac Nessa?",
    "which monuments are at Emain Macha?", "which tales mention the Gáe Bulg?",
    "which tales are not about Cú Chulainn?", "how many monuments are in County Down?",
    "which monuments are in County Antrim?", "which monuments are located in County Down?",
    "how many monuments are in County Armagh?", "how many monuments are in County Tyrone?",
    "how many monuments are in County Fermanagh?", "how many monuments are in County Londonderry?",
    "which site is Navan Fort at?", "which place is Navan Fort at?", "which figures are in Táin Bó Cúailnge?",
    "which tales are part of the Ulster Cycle?", "which monuments are in County Nowhere?",
    "which tales have figures associated with Conchobar mac Nessa?", "how many monuments are there?",
    "which monuments are there?", "how many tales are in the Fenian Cycle?",
    "how many monuments are in Down?", "what is related to Navan Fort?",
    "which mythical place is related to Navan Fort?"]


def answers(ask, questions: list[str]) -> dict:
    ctx = ask.startup()
    return {q: ask.answer(q, *ctx) for q in questions}


def cell(r: dict) -> str:
    if r.get("refused"):
        return f"refused: {r['refused']}"
    return f"{r.get('understood', '')} → {r.get('total')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ask_dir", help="starches-demo/ask")
    ap.add_argument("bundle", help="a bundle from `ceist vocab pipeline` (the demo's model names)")
    ap.add_argument("--questions", help="more questions, one per line")
    a = ap.parse_args()
    questions = list(README)
    if a.questions:
        questions += [q.strip() for q in Path(a.questions).read_text().splitlines()
                      if q.strip() and not q.lstrip().startswith("#")]
    sys.path.insert(0, a.ask_dir)
    import ask
    hand = answers(ask, questions)
    generated = json.loads(Path(a.bundle).read_text())
    ask.her_bundle = lambda _graphs: generated
    gen = answers(ask, questions)
    same = sum(1 for q in questions if cell(hand[q]) == cell(gen[q]))
    print(f"{same}/{len(questions)} answers the same; "
          f"answered: hand-tuned {sum(1 for q in questions if not hand[q].get('refused'))}, "
          f"generated {sum(1 for q in questions if not gen[q].get('refused'))}\n")
    print("| question | hand-tuned | generated |\n| --- | --- | --- |")
    for q in questions:
        if cell(hand[q]) != cell(gen[q]):
            print(f"| {q} | {cell(hand[q])} | {cell(gen[q])} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
