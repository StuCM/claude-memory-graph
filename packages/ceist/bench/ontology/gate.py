"""The gate an ontology proposal passes before `ceist vocab ontology --accept` merges it.

    .venv-ceist/bin/python packages/ceist/bench/ontology/gate.py <candidates.json> \\
        [--ontology <dir>] [--demo <starches-demo/ask> | skip] [--her <arches-her pkg> | skip] [name=<graphs dir> ...]

A candidate is {"path", "kind", "phrases"}. On the ontology bench (run.py, the sets in
SETS unless given), each is scored alone against phrases.json: it passes if it adds a
right answer and makes no template question worse (a right one lost, a wrong reading or
a wrong added). Then the passing ones together, on the bench and on the demo question
bank: a question that changes rejects the candidates whose phrases it holds. Then the
HER plans, which must not change. A missing checkout fails the gate unless its option
is "skip". Prints the verdict as JSON on its last line, each candidate as "<kind> <path>":
{"accepted": [key], "rejected": {key: why}, "checks": [line],
 "bench": {"before"|"after": {set: {mode: [n per score]}}}, "demo": {"before"|"after": tally}}.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run  # noqa: E402

BAD = ("wrong reading", "wrong")
DEMO = Path("/home/stuart/git/personal/starches-demo/ask")
HER_PLANS = run.REPO / "packages" / "ceist" / "bench" / "her_plans.py"


def key(c: dict) -> str:
    return f"{c['kind']} {c['path']}"


def scores(name: str, graphs: list[dict], resources: list[dict], vocab, entries: list[dict],
           words: set[str] | None = None) -> dict:
    """{(mode, question): score} for the template questions of this ontology; with
    `words`, only the questions holding one of them."""
    from ceist.questions import templated
    ontology = {"format": "ceist.ontology/1", "entries": entries}
    items = [o for o in templated(vocab, ontology) if words is None or words & _words(o["q"])]
    with tempfile.TemporaryDirectory() as d:
        Path(d, "phrases.json").write_text(json.dumps(ontology))
        bundles = run.layer_bundles(name, graphs, Path(d))
    return {(mode, q): s for mode, b in bundles.items()
            for _, q, _, s, _ in run.outcomes(graphs, resources, b, items)}


_SMALL = {"the", "and", "for", "with", "from", "was", "were", "has", "have", "are", "who", "its"}


def _words(text: str) -> set[str]:
    """Its words' first four letters: a phrase can only change a question that has one."""
    return {w[:4] for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _SMALL}


def judge(before: dict, after: dict) -> tuple[int, list[str]]:
    """(right answers added, questions made worse): a right answer or right refusal
    lost, or a wrong reading or wrong that was not there before."""
    gained = sum(1 for k, s in after.items() if s == "right" and before.get(k) != "right")
    worse = [q for (mode, q), s in after.items()
             if (s in BAD and before.get((mode, q)) not in BAD)]
    worse += [q for (mode, q), s in before.items()
              if s in ("right", "right refusal") and after.get((mode, q)) != s]
    return gained, sorted(set(worse))


def counts(scored: dict) -> dict:
    """{mode: [n per run.SCORES]}."""
    out = {}
    for (mode, _), s in scored.items():
        out.setdefault(mode, [0] * len(run.SCORES))[run.SCORES.index(s)] += 1
    return out


def one_set(name: str, path: str, base: list[dict], cands: list[dict], together: bool) -> dict:
    """Alone: {key: [gained, worse]} per candidate. Together: {"*": [gained, worse],
    "tally": {"before": counts, "after": counts}}."""
    from ceist.arches import ArchesVocabulary
    graphs = run.graph_docs(path)
    resources = run.synthetic(graphs)
    vocab = ArchesVocabulary(graphs, resources=resources)
    before = scores(name, graphs, resources, vocab, base)
    if together:
        after = scores(name, graphs, resources, vocab, base + cands)
        return {"*": judge(before, after), "tally": {"before": counts(before), "after": counts(after)}}
    out = {}
    for c in cands:
        # ponytail: only the questions sharing a word with its phrases are re-asked; the together run re-asks all
        after = {**before, **scores(name, graphs, resources, vocab, base + [c], _words(" ".join(c["phrases"])))}
        out[key(c)] = judge(before, after)
    return out


def bench(sets: dict, base: list[dict], cands: list[dict], together: bool = False) -> dict:
    """one_set over every set, each in its own process (Alizarin registers graphs by id);
    together, also {"tally": {name: tally}}."""
    out = {"tally": {}} if together else {}
    with tempfile.TemporaryDirectory() as d:
        Path(d, "in.json").write_text(json.dumps({"base": base, "cands": cands, "together": together}))
        for name, path in sets.items():
            res = subprocess.run([sys.executable, __file__, "--one", f"{name}={path}", str(Path(d, "in.json"))],
                                 capture_output=True, text=True)
            if res.returncode:
                raise RuntimeError(f"{name}: {res.stderr[-2000:]}")
            got = json.loads(res.stdout.splitlines()[-1])
            if together:
                out["tally"][name] = got.pop("tally")
            for k, (gained, worse) in got.items():
                g, w = out.get(k, (0, []))
                out[k] = (g + gained, w + [f"{name}: {q}" for q in worse])
    return out


def holding(cands: list[dict], questions: list[str]) -> list[dict]:
    """The candidates with a phrase in one of these questions."""
    text = " ".join(f" {q.lower()} " for q in questions)
    return [c for c in cands if any(f" {p} " in text for p in c["phrases"])]


def demo_bank(demo: Path, base_dir: Path) -> str:
    """The demo question bank's report with the vocabulary at base_dir (and its ontology beside it)."""
    env = dict(os.environ, CEIST_BASE=str(base_dir), PYTHONPATH=str(run.REPO / "packages" / "ceist" / "src"))
    res = subprocess.run(["uv", "run", "python", str(run.REPO / "packages/ceist/bench/demo/run_bank.py")],
                         cwd=demo, env=env, capture_output=True, text=True)
    # run_bank exits 1 on a regression, which is a result; anything else, or no tally line, is a failed run
    if res.returncode not in (0, 1) or not any(line.startswith("{") for line in res.stdout.splitlines()):
        raise RuntimeError(f"demo bank failed (exit {res.returncode}): {(res.stderr or res.stdout)[-1000:]}")
    return res.stdout


def tally_line(report: str) -> str:
    return next(line for line in report.splitlines() if line.startswith("{"))


def changed_lines(a: str, b: str) -> list[str]:
    return sorted(set(a.splitlines()) ^ set(b.splitlines()))


def her_plans(pkg: Path, out: Path) -> tuple[bool, str]:
    """HER's planner answers against plans-2.0.json, as CI checks them."""
    ceist = [str(Path(sys.executable).parent / "ceist")]
    graphs, models, bundle = pkg / "graphs" / "resource_models", out / "her-models", out / "her.bundle.json"
    for cmd in (ceist + ["vocab", "describe", str(graphs), str(models), "--reference", str(pkg / "reference_data")],
                ceist + ["vocab", "assemble", str(models), str(run.REPO / "packages/ceist/bench/her/vocab"),
                         "-o", str(bundle), "--graphs", str(graphs)],
                [sys.executable, str(HER_PLANS), str(pkg), str(bundle),
                 str(run.REPO / "packages/ceist/bench/her/plans-2.0.json")]):
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode:
            return False, (res.stderr or res.stdout).strip()[-500:]
    return True, res.stdout.strip()


def gate(cands: list[dict], ontology_dir: Path, sets: dict, demo: Path | None, her: Path | None) -> dict:
    """demo or her None: that check skipped on purpose; a path that isn't there fails."""
    for what, d in (("demo", demo), ("HER", her)):
        if d is not None and not d.is_dir():
            raise RuntimeError(f"no {what} checkout at {d}: give its path, or skip")
    if not sets:
        raise RuntimeError("no bench graph sets")
    base = run.load_ontology(ontology_dir)["entries"]
    rejected, checks = {}, []
    for k, (gained, worse) in bench(sets, base, cands).items():
        if worse:
            rejected[k] = f"bench: worse on {len(worse)}, e.g. {worse[0]}"
        elif not gained:
            rejected[k] = "bench: adds no right answer"
    passing = [c for c in cands if key(c) not in rejected]

    def drop(questions: list[str], why: str) -> bool:
        """Reject the passing candidates these questions hold; all of them if none."""
        hit = holding(passing, questions) or list(passing)
        for c in hit:
            rejected[key(c)] = f"{why}: {questions[0]}"
            passing.remove(c)
        return bool(passing)

    while passing:
        _, worse = bench(sets, base, passing, together=True)["*"]
        if not worse or not drop(worse, "bench, together"):
            break
    checks.append(f"bench: {len(passing)} pass alone and together")
    demo_tally = {}
    if passing and demo:
        was = demo_bank(demo, run.BASE)
        # what passes leaves the bank unchanged, so after is before
        demo_tally["before"] = demo_tally["after"] = tally_line(was)
        while passing:
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "ontology" / "cidoc-crm").mkdir(parents=True)
                (Path(d) / "base").symlink_to(run.BASE)
                Path(d, "ontology", "cidoc-crm", "phrases.json").write_text(
                    json.dumps({"format": "ceist.ontology/1", "entries": base + passing}))
                lines = changed_lines(was, demo_bank(demo, Path(d) / "base"))
            if not lines or not drop(lines, "demo bank changed"):
                break
        checks.append(f"demo bank: unchanged with the {len(passing)} passing")
    else:
        checks.append("demo bank: not run (skipped, or nothing passed)")
    if passing and her:
        with tempfile.TemporaryDirectory() as d:
            ok, said = her_plans(her, Path(d))
        if not ok:
            for c in passing:
                rejected[key(c)] = f"HER plans changed: {said[:200]}"
            passing = []
        checks.append(f"HER plans: {said.splitlines()[-1] if said else ''}")
    else:
        checks.append("HER plans: not run (skipped, or nothing passed)")
    tally = bench(sets, base, passing, together=True)["tally"]
    return {"accepted": [key(c) for c in passing], "rejected": rejected, "checks": checks,
            "bench": {"before": {n: t["before"] for n, t in tally.items()},
                      "after": {n: t["after"] for n, t in tally.items()}},
            "demo": demo_tally}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--one"]:
        name, path = argv[1].split("=", 1)
        x = json.loads(Path(argv[2]).read_text())
        print(json.dumps(one_set(name, path, x["base"], x["cands"], x["together"])))
        return 0
    opts = {"--ontology": str(run.ONTOLOGY), "--demo": str(DEMO), "--her": str(Path(run.SETS["her"]).parents[1])}
    rest, it = [], iter(argv[1:])
    for a in it:
        if a in opts:
            opts[a] = next(it)
        else:
            rest.append(a)
    sets = dict(a.split("=", 1) for a in rest) or {k: p for k, p in run.SETS.items() if Path(p).is_dir()}
    cands = json.loads(Path(argv[0]).read_text())
    demo, her = (None if opts[o] == "skip" else Path(opts[o]) for o in ("--demo", "--her"))
    verdict = gate(cands, Path(opts["--ontology"]), sets, demo, her)
    print(json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
