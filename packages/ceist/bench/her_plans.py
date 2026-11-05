"""The planner over the HER questions, against its reviewed answers.

    python packages/ceist/bench/her_plans.py <package dir> <bundle> <answers.json> [--write]

Every question in her/cases.json goes through `interpret` with the shipping
config (her/ceist.toml). The answers file holds each question's narrated
plan, or "refused". Any difference fails: a condition nobody asked for, or
an answer where a refusal was expected, changes a line that has to be
reviewed. `--write` records the current answers instead.
"""

import json
import sys
from pathlib import Path

from ceist import bundle as _bundle
from ceist import config
from ceist.pipeline import planner_run

HERE = Path(__file__).parent / "her"


def answers(pkg: Path, bundle: Path) -> dict[str, str]:
    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    _, rows = planner_run(pkg / "graphs" / "resource_models", pkg / "reference_data",
                          _bundle.load(bundle), cases, config.load(HERE / "ceist.toml"))
    return {r["q"]: "refused" if r["refused"] else r["plan"] for r in rows}


def main(argv: list[str]) -> int:
    pkg, bundle, path = Path(argv[0]), Path(argv[1]), Path(argv[2])
    got = answers(pkg, bundle)
    if "--write" in argv:
        path.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n")
        return 0
    want = json.loads(path.read_text())
    changed = [q for q in want.keys() | got.keys() if want.get(q) != got.get(q)]
    for q in sorted(changed):
        print(f"{q}\n  was: {want.get(q)}\n  now: {got.get(q)}", file=sys.stderr)
    print(f"{len(got) - len(changed)}/{len(got)} answers as reviewed")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
