"""The gate an ontology proposal passes before `ceist vocab ontology --accept` merges it.

    .venv-ceist/bin/python packages/ceist/bench/ontology/gate.py <candidates.json> \\
        [--ontology <dir>] [--base <dir>] [--client <dir>] [--demo <starches-demo/ask> | skip]
        [--her <arches-her pkg> | skip] [name=<graphs dir> ...]

A candidate is {"path", "kind", "phrases"}, an ontology phrasing, or one of
`ceist vocab generate`'s for the base or client layer ({"layer", "key", …}, written by
vocab_rules.apply). On the ontology bench (run.py, the sets in SETS unless given), each
is scored alone against the layers: it passes if it adds a right answer and makes no
template question worse (a right one lost, a wrong reading or a wrong added). A client
candidate, which no bench set reads, goes straight on. Then the passing ones together,
on the bench and on the demo question bank: a question that turns worse rejects the
candidates whose phrases it holds. Then the HER plans, which must not change. A missing
checkout fails the gate unless its option is "skip". Prints the verdict as JSON on its
last line, each candidate as "<kind> <path>" (or its "key"):
{"accepted": [key], "rejected": {key: why}, "checks": [line],
 "bench": {"before"|"after": {set: {mode: [n per score]}}}, "demo": {"before"|"after": tally}}.
"""

import json
import os
import re
import shutil
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
    from ceist.vocab_rules import gate_key
    return gate_key(dict({"layer": "ontology"}, **c))


def _layer(c: dict) -> str:
    return c.get("layer", "ontology")


def layers(d: Path, base: list[dict], cands: list[dict], base_dir: Path, client_dir: Path | None) -> tuple:
    """(ontology dir, base dir, client dir) under d: the ontology `base` entries and the
    candidates applied to copies of the layers."""
    from ceist.vocab_rules import apply
    onto = d / "ontology" / "cidoc-crm"
    onto.mkdir(parents=True)
    (onto / "phrases.json").write_text(json.dumps({"format": "ceist.ontology/1", "entries": base}))
    shutil.copytree(base_dir, d / "base")
    client = None
    if client_dir is not None:
        client = d / "client"
        shutil.copytree(client_dir, client)
    apply([dict({"layer": "ontology"}, **c) for c in cands], onto, d / "base", client)
    return onto, d / "base", client


def scores(name: str, graphs: list[dict], resources: list[dict], vocab, entries: list[dict],
           words: set[str] | None = None, cands: list[dict] = (), base_dir: Path = run.BASE,
           only: set | None = None) -> dict:
    """{(mode, question): score} for the template questions of these layers; with
    `words`, only the questions holding one of them. `only`: the (model, node) pairs
    whose base phrasings get templates too."""
    from ceist.questions import templated
    with tempfile.TemporaryDirectory() as d:
        onto, base, _ = layers(Path(d), entries, list(cands), base_dir, None)
        ontology = run.load_ontology(onto)
        bundles = run.layer_bundles(name, graphs, onto, base)
    out = {}
    for mode, b in bundles.items():
        items = [o for o in templated(vocab, ontology, b, only) if words is None or words & _words(o["q"])]
        out.update({(mode, q): s for _, q, _, s, _ in run.outcomes(graphs, resources, b, items)})
    return out


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


def one_set(name: str, path: str, base: list[dict], cands: list[dict], together: bool,
            base_dir: Path = run.BASE) -> dict:
    """Alone: {key: [gained, worse]} per candidate. Together: {"*": [gained, worse],
    "tally": {"before": counts, "after": counts}}."""
    from ceist.arches import ArchesVocabulary
    graphs = run.graph_docs(path)
    resources = run.synthetic(graphs)
    vocab = ArchesVocabulary(graphs, resources=resources)
    ids = {g["graphid"]: run.name_of(g) for g in graphs}
    only = {(ids[c["graphid"]], c["node"]) for c in cands if _layer(c) == "base" and c.get("node") in
            {n.get("alias") for g in graphs if g["graphid"] == c["graphid"] for n in g["nodes"]}}
    before = scores(name, graphs, resources, vocab, base, base_dir=base_dir, only=only)
    if together:
        after = scores(name, graphs, resources, vocab, base, cands=cands, base_dir=base_dir, only=only)
        return {"*": judge(before, after), "tally": {"before": counts(before), "after": counts(after)}}
    out = {}
    for c in cands:
        # ponytail: only the questions sharing a word with its phrases are re-asked; the together run re-asks all
        after = {**before, **scores(name, graphs, resources, vocab, base, _words(" ".join(c["phrases"])), [c],
                                    base_dir, only)}
        out[key(c)] = judge(before, after)
    return out


def bench(sets: dict, base: list[dict], cands: list[dict], together: bool = False, base_dir: Path = run.BASE) -> dict:
    """one_set over every set, each in its own process (Alizarin registers graphs by id);
    together, also {"tally": {name: tally}}."""
    out = {"tally": {}} if together else {}
    with tempfile.TemporaryDirectory() as d:
        Path(d, "in.json").write_text(json.dumps({"base": base, "cands": cands, "together": together,
                                                  "base_dir": str(base_dir)}))
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


def demo_bank(demo: Path, base_dir: Path, client_dir: Path | None = None) -> str:
    """The demo question bank's report with the vocabulary at base_dir (and its ontology beside it)."""
    env = dict(os.environ, CEIST_BASE=str(base_dir), PYTHONPATH=str(run.REPO / "packages" / "ceist" / "src"))
    if client_dir is not None:
        env["CEIST_CLIENT"] = str(client_dir)
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


def worse_lines(a: str, b: str) -> list[str]:
    """The bank questions that turned worse from report a to report b: "<was> -> <now>: <q> | …"
    lines new in b where a right answer was lost or a wrong one appeared. A question that turns
    right is a gain, not a change to reject."""
    out = []
    for line in sorted(set(b.splitlines()) - set(a.splitlines())):
        m = re.match(r"(\S+) -> (\S+): ", line)
        if m and (m[1] == "right" or m[2] == "wrong"):
            out.append(line)
    return out


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


def gate(cands: list[dict], ontology_dir: Path, sets: dict, demo: Path | None, her: Path | None,
         base_dir: Path = run.BASE, client_dir: Path | None = None) -> dict:
    """demo or her None: that check skipped on purpose; a path that isn't there fails."""
    for what, d in (("demo", demo), ("HER", her)):
        if d is not None and not d.is_dir():
            raise RuntimeError(f"no {what} checkout at {d}: give its path, or skip")
    if not sets:
        raise RuntimeError("no bench graph sets")
    base = run.load_ontology(ontology_dir)["entries"]
    rejected, checks = {}, []
    for k, (gained, worse) in bench(sets, base, cands, base_dir=base_dir).items():
        if k in {key(c) for c in cands if _layer(c) == "client"}:
            continue
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
        _, worse = bench(sets, base, passing, together=True, base_dir=base_dir)["*"]
        if not worse or not drop(worse, "bench, together"):
            break
    checks.append(f"bench: {len(passing)} pass alone and together")
    demo_tally = {}
    if passing and demo:
        with tempfile.TemporaryDirectory() as d:
            _, b, c = layers(Path(d), base, [], base_dir, client_dir)
            was = demo_bank(demo, b, c)
        demo_tally["before"] = demo_tally["after"] = tally_line(was)
        while passing:
            with tempfile.TemporaryDirectory() as d:
                _, b, c = layers(Path(d), base, passing, base_dir, client_dir)
                now = demo_bank(demo, b, c)
            lines = worse_lines(was, now)
            demo_tally["after"] = tally_line(now)
            if not lines or not drop(lines, "demo bank worse"):
                break
        checks.append(f"demo bank: nothing worse with the {len(passing)} passing")
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
    tally = bench(sets, base, passing, together=True, base_dir=base_dir)["tally"]
    return {"accepted": [key(c) for c in passing], "rejected": rejected, "checks": checks,
            "bench": {"before": {n: t["before"] for n, t in tally.items()},
                      "after": {n: t["after"] for n, t in tally.items()}},
            "demo": demo_tally}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--one"]:
        name, path = argv[1].split("=", 1)
        x = json.loads(Path(argv[2]).read_text())
        print(json.dumps(one_set(name, path, x["base"], x["cands"], x["together"], Path(x["base_dir"]))))
        return 0
    opts = {"--ontology": str(run.ONTOLOGY), "--demo": str(DEMO), "--her": str(Path(run.SETS["her"]).parents[1]),
            "--base": str(run.BASE), "--client": ""}
    rest, it = [], iter(argv[1:])
    for a in it:
        if a in opts:
            opts[a] = next(it)
        else:
            rest.append(a)
    sets = dict(a.split("=", 1) for a in rest) or {k: p for k, p in run.SETS.items() if Path(p).is_dir()}
    cands = json.loads(Path(argv[0]).read_text())
    demo, her = (None if opts[o] == "skip" else Path(opts[o]) for o in ("--demo", "--her"))
    verdict = gate(cands, Path(opts["--ontology"]), sets, demo, her, Path(opts["--base"]),
                   Path(opts["--client"]) if opts["--client"] else None)
    print(json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
