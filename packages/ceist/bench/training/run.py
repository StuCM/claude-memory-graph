"""Vocabulary training experiments: what each choice costs, and what it buys.

    .venv-ceist/bin/python packages/ceist/bench/training/run.py --estimate   # the budget, before any spend
    .venv-ceist/bin/python packages/ceist/bench/training/run.py --run baseline,rounds-1 [--llm-cmd CMD]
    .venv-ceist/bin/python packages/ceist/bench/training/run.py --report     # → report.md

A run builds, in order: the ontology layer (when "first": every proposal marked reviewed
and put through the accept gate), HER's base layer, the training questions (only when it
refines), and the demo's client layer with its refine rounds. Each stage writes to
<work>/<run>/<stage>/ and shares one LLM cache across runs, so a prompt two runs both send
is paid once. Every run is scored on the same benchmark: 026's fresh-graph bench, the demo
question bank, HER's plans and 022's held-out set. Scores, calls, tokens and dollars go to
results.jsonl.
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from ast import literal_eval
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CEIST = HERE.parents[1]
REPO = HERE.parents[3]
MATRIX, RESULTS, REPORT = HERE / "matrix.toml", HERE / "results.jsonl", HERE / "report.md"
CLI = [str(Path(sys.executable).parent / "ceist")]
ONTOLOGY, BASE = REPO / "vocabularies" / "ontology" / "cidoc-crm", REPO / "vocabularies" / "base"
COLUMNS = ("ontology", "base", "questions", "data", "refine")
UNITS = {"ontology": ("unphrased CRM path", 1), "base": ("nodegroup", 1), "questions": ("model", 1),
         "data": ("100 labels", 100)}


def load(path=MATRIX) -> tuple[dict, dict, list[dict]]:
    """(paths, baseline, runs), each run the baseline with its own choices over it."""
    doc = tomllib.loads(Path(path).read_text())
    return doc["paths"], doc["baseline"], [dict(doc["baseline"], **r) for r in doc["run"]]


def varies(run: dict, baseline: dict) -> str:
    return ", ".join(f"{k} {run[k]}" for k in baseline if run[k] != baseline[k]) or "baseline"


def demo_ref(paths: dict) -> Path:
    """The demo's SKOS file in a concepts/ dir, as --reference reads it."""
    ref = Path(paths["work"]) / "demo-ref"
    (ref / "concepts").mkdir(parents=True, exist_ok=True)
    link = ref / "concepts" / "smr.xml"
    if not link.is_symlink():
        link.symlink_to(Path(paths["demo"]) / "data" / "vocabularies" / "smr.xml")
    return ref


def graphs_of(paths: dict) -> tuple[Path, Path]:
    return (Path(paths["her"]) / "graphs" / "resource_models", Path(paths["demo"]) / "data" / "graphs")


def estimate_args(run: dict, paths: dict) -> list[tuple[Path, list[str]]]:
    """(graphs, `ceist vocab estimate` options) for each stage the run builds."""
    her, demo = graphs_of(paths)
    out = []
    if run["ontology"] == "first":
        out.append((her, ["--stages", "ontology", "--model", run["ontology_model"], "--ontology", str(ONTOLOGY)]))
    seeds = ["--base", str(BASE), "--seed", str(CEIST / "bench/her/vocab")] if run["seeds"] else []
    out.append((her, ["--stages", "base", "--model", run["base_model"],
                      "--reference", str(Path(paths["her"]) / "reference_data")] + seeds))
    if run["rounds"]:
        out.append((demo, ["--stages", "questions", "--model", run["questions_model"],
                           "--reference", str(demo_ref(paths))]))
    client = ["--client", str(CEIST / "bench/demo/vocab")] if run["seeds"] else []
    out.append((demo, ["--stages", "data", "--model", run["data_model"], "--reference", str(demo_ref(paths)),
                       "--rounds", str(run["rounds"])] + client))
    return out


def ledgers(paths: dict) -> list[str]:
    return [str(p.parent) for p in sorted(Path(paths["work"]).glob("*/*/audit.jsonl"))]


def ceist_estimate(paths: dict):
    """`ceist vocab estimate --json`, once per distinct stage and options."""
    done = {}

    def est(graphs: Path, args: list[str]) -> dict:
        key = (str(graphs), tuple(args))
        if key not in done:
            led = [a for d in ledgers(paths) for a in ("--ledger", d)]
            res = subprocess.run(CLI + ["vocab", "estimate", str(graphs), "--json"] + args + led,
                                 capture_output=True, text=True, check=True)
            done[key] = json.loads(res.stdout.splitlines()[-1])
        return done[key]
    return est


def estimate_matrix(runs: list[dict], baseline: dict, paths: dict, est) -> list[str]:
    """Each run's estimated calls and dollars per stage, and the matrix total, where a prompt
    two runs send (same stage, model and text) is paid once: the cache answers the second."""
    lines = ["| run | varies | " + " | ".join(COLUMNS) + " | calls | dollars |", "| --- " * (len(COLUMNS) + 4) + "|"]
    seen, alone, once = set(), 0.0, 0.0
    for run in runs:
        stages = {}
        for graphs, args in estimate_args(run, paths):
            e = est(graphs, args)
            stages.update(e["stages"])
            for stage, model, sha, dollars in e["calls"]:
                if sha is None or (stage, model, sha) not in seen:
                    once += dollars
                    seen.add((stage, model, sha))
        dollars = sum(s["dollars"] for s in stages.values())
        alone += dollars
        cells = [f"${stages[c]['dollars']:.2f}" if c in stages else "" for c in COLUMNS]
        lines.append(f"| {run['name']} | {varies(run, baseline)} | " + " | ".join(cells)
                     + f" | {sum(s['calls'] for s in stages.values())} | ${dollars:.2f} |")
    lines += ["", f"Total, each run on its own: ${alone:.2f}. With the shared cache (a prompt sent twice is "
                  f"paid once): **${once:.2f}**.",
              "Refine rounds are counted at their most; collision passes and retries are not counted.",
              "Dollars are API list prices; on a Claude subscription they are usage, not a bill."]
    return lines


def setup(run: dict, w: Path) -> Path:
    """<work>/<run>/: vocabularies/{base, ontology/cidoc-crm} and client/, seeded or empty."""
    if w.exists():
        shutil.rmtree(w)
    vocab = w / "vocabularies"
    shutil.copytree(ONTOLOGY, vocab / "ontology" / "cidoc-crm", ignore=shutil.ignore_patterns("proposed.json"))
    if run["seeds"]:
        shutil.copytree(BASE, vocab / "base")
        shutil.copytree(CEIST / "bench/demo/vocab", w / "client")
    else:
        (vocab / "base").mkdir()
        (w / "client").mkdir()
    return vocab


def commands(run: dict, paths: dict, w: Path, llm: list[str]) -> list[tuple[str, list[str]]]:
    her, demo = graphs_of(paths)
    vocab, onto = w / "vocabularies", w / "vocabularies" / "ontology" / "cidoc-crm"
    out = []
    if run["ontology"] == "first":
        out.append(("ontology", CLI + ["vocab", "ontology", str(her), "-o", str(w / "ontology"), "--ontology", str(onto),
                                       "--model", run["ontology_model"]] + llm))
        out.append(("accept", CLI + ["vocab", "ontology", "--accept", "--ontology", str(onto)]))
    out.append(("base", CLI + ["vocab", "pipeline", str(her), "-o", str(w / "base"), "--reference",
                               str(Path(paths["her"]) / "reference_data"), "--layer", "base", "--base",
                               str(vocab / "base"), "--model", run["base_model"]]
                + (["--seed", str(CEIST / "bench/her/vocab")] if run["seeds"] else []) + llm))
    if run["rounds"]:
        out.append(("questions", CLI + ["questions", "generate", str(demo), "-o", str(w / "questions"), "--reference",
                                        str(demo_ref(paths)), "--model", run["questions_model"]] + llm))
    out.append(("data", CLI + ["vocab", "pipeline", str(demo), "-o", str(w / "data"), "--reference", str(demo_ref(paths)),
                               "--layer", "data", "--client", str(w / "client"), "--base", str(vocab / "base"),
                               "--model", run["data_model"], "--rounds", str(run["rounds"]),
                               "--holdout", str(CEIST / "bench/demo/questions.json"),
                               "--records", str(Path(paths["demo"]) / "data" / "resources")]
                + (["--questions", str(w / "questions" / "train.json")] if run["rounds"] else []) + llm))
    return out


def review_all(onto: Path) -> None:
    """Every proposal marked reviewed: the experiment lets the accept gate alone decide."""
    p = onto / "proposed.json"
    if p.exists():
        doc = json.loads(p.read_text())
        for x in doc.get("proposals", []):
            x["reviewed"] = True
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def fresh(onto: Path) -> dict:
    """026's bench: template questions right with this ontology layer, over its graph sets."""
    spec = importlib.util.spec_from_file_location("fresh_bench", CEIST / "bench/ontology/run.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    got = Counter()
    for name, path in bench.SETS.items():
        if not Path(path).is_dir():
            continue
        res = subprocess.run([sys.executable, spec.origin, "--one", f"{name}={path}"], capture_output=True, text=True,
                             check=True, env=dict(os.environ, CEIST_ONTOLOGY=str(onto)))
        for _, outcome, n in json.loads(res.stdout.splitlines()[-1])["scores"]["ontology"]:
            got[outcome] += n
    return {"right": got["right"] + got["right refusal"], "of": sum(got.values()), "wrong": got["wrong"]}


def _tally_line(stdout: str) -> dict:
    return literal_eval(next(x for x in reversed(stdout.splitlines()) if x.startswith("{")))


def demo_bank(paths: dict, w: Path, *more: str) -> dict:
    env = dict(os.environ, CEIST_BASE=str(w / "vocabularies" / "base"), CEIST_CLIENT=str(w / "client"),
               PYTHONPATH=str(CEIST / "src"))
    res = subprocess.run(["uv", "run", "python", str(CEIST / "bench/demo/run_bank.py"), *more], cwd=paths["demo"],
                         env=env, capture_output=True, text=True)
    return _tally_line(res.stdout)


def bank_score(paths: dict, w: Path) -> dict:
    t = demo_bank(paths, w)
    return {"right": sum(n for (_, s), n in t.items() if s == "right"), "of": sum(t.values()),
            "wrong": sum(n for (_, s), n in t.items() if s == "wrong")}


def holdout_score(paths: dict, w: Path) -> dict:
    t = demo_bank(paths, w, "--set", paths["holdout"])
    return {"right": t.get("right", 0) + t.get("right refusal", 0), "of": sum(t.values()),
            "wrong": t.get("wrong", 0) + t.get("wrong reading", 0)}


def her_score(paths: dict, w: Path) -> dict:
    """HER's planner answers, read through this run's base and ontology layers, against plans-2.0.json."""
    from ceist.arches import graph_doc
    from ceist.bundle import layered
    her, _ = graphs_of(paths)
    bundle, _ = layered([graph_doc(p) for p in sorted(her.glob("*.json"))], w / "vocabularies" / "base")
    (w / "her.bundle.json").write_text(json.dumps(bundle))
    res = subprocess.run([sys.executable, str(CEIST / "bench/her_plans.py"), paths["her"], str(w / "her.bundle.json"),
                          str(CEIST / "bench/her/plans-2.0.json")], capture_output=True, text=True)
    right, of = res.stdout.split()[0].split("/") if res.stdout else ("0", "0")
    return {"right": int(right), "of": int(of)}


def sizes(paths: dict) -> dict:
    """The profile measures each stage's cost scales with."""
    her, demo = graphs_of(paths)

    def prof(graphs, ref):
        res = subprocess.run(CLI + ["vocab", "profile", str(graphs), "--reference", str(ref), "--json",
                                    "--ontology", str(ONTOLOGY)], capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    h, d = prof(her, Path(paths["her"]) / "reference_data"), prof(demo, demo_ref(paths))
    return {"ontology": h["ontology"].get("unphrased", 0), "base": sum(r["nodegroups"] for r in h["graphs"]),
            "questions": len(d["graphs"]), "data": sum(r["labels"] for r in d["graphs"])}


def run_one(run: dict, baseline: dict, paths: dict, llm: list[str], size: dict, log=print) -> dict:
    from ceist import cost
    w = Path(paths["work"]) / run["name"]
    setup(run, w)
    shared = Path(paths["work"]) / "cache"
    shared.mkdir(parents=True, exist_ok=True)
    exits = {}
    for stage, argv in commands(run, paths, w, llm):
        if stage != "accept":
            (w / stage).mkdir(parents=True, exist_ok=True)
            (w / stage / "cache").symlink_to(shared)
        log(f"{run['name']}: {stage}")
        exits[stage] = subprocess.run(argv, capture_output=True, text=True).returncode
        if stage == "ontology":
            review_all(w / "vocabularies" / "ontology" / "cidoc-crm")
    scores = {}
    for name, score in (("fresh graphs", lambda: fresh(w / "vocabularies" / "ontology" / "cidoc-crm")),
                        ("demo bank", lambda: bank_score(paths, w)), ("HER plans", lambda: her_score(paths, w)),
                        ("hold-out", lambda: holdout_score(paths, w) if paths.get("holdout") else None)):
        try:
            scores[name] = score()
        except Exception as e:   # a scorer that fails is a result to read, not a reason to lose the run's spend
            scores[name] = {"error": str(e)[-300:]}
    spent = [r for p in sorted(w.glob("*/audit.jsonl")) for r in cost.read_runs([p])[0]["spent"]]
    return {"run": run["name"], "varies": varies(run, baseline), "choices": run, "exits": exits, "scores": scores,
            "cost": {s: dict(t) for s, t in cost.tally(spent).items()}, "size": size}


def _score(s) -> str:
    if not s:
        return ""
    return s["error"][:40] if "error" in s else f"{s['right']}/{s['of']}" + (f" ({s['wrong']} wrong)" if s.get("wrong")
                                                                             else "")


def report(results: list[dict]) -> list[str]:
    """Score against cost per run, then cost against size per stage, so a new graph set can be
    priced from its profile alone."""
    names = ("fresh graphs", "demo bank", "HER plans", "hold-out")
    lines = ["# Vocabulary training experiments", "", "| run | varies | " + " | ".join(names) + " | calls | dollars |",
             "| --- " * (len(names) + 4) + "|"]
    for r in results:
        paid = sum(t["calls"] - t["cached"] for t in r["cost"].values())
        lines.append(f"| {r['run']} | {r['varies']} | " + " | ".join(_score(r["scores"].get(n)) for n in names)
                     + f" | {paid} | ${sum(t['dollars'] for t in r['cost'].values()):.2f} |")
    lines += ["", "## Cost against size", "", "Calls from the cache cost nothing, so a stage another run "
              "already paid for shows 0 here.", "",
              "| run | stage | calls | dollars | size | calls per unit | dollars per unit |", "| --- " * 7 + "|"]
    for r in results:
        for stage, t in r["cost"].items():
            unit, per = UNITS.get(stage, ("round", 1))
            n = (r["choices"]["rounds"] if stage == "refine" else r["size"].get(stage, 0)) / per
            paid = t["calls"] - t["cached"]
            lines.append(f"| {r['run']} | {stage} | {paid} | ${t['dollars']:.2f} | {n:g} {unit} | "
                         + (f"{paid / n:.2f} | ${t['dollars'] / n:.3f} |" if n else "| |"))
    return lines + ["", "Dollars are API list prices; on a Claude subscription they are usage, not a bill."]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default=str(MATRIX))
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--run", help="run names, comma-separated")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--llm-cmd", help="passed to every stage (a stub; default claude -p)")
    a = ap.parse_args(argv)
    paths, baseline, runs = load(a.matrix)
    if a.estimate:
        print("\n".join(estimate_matrix(runs, baseline, paths, ceist_estimate(paths))))
    if a.run:
        want = a.run.split(",")
        unknown = set(want) - {r["name"] for r in runs}
        if unknown:
            print(f"no such run: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        size = sizes(paths)
        for run in runs:
            if run["name"] in want:
                res = run_one(run, baseline, paths, ["--llm-cmd", a.llm_cmd] if a.llm_cmd else [], size)
                with open(RESULTS, "a") as f:
                    f.write(json.dumps(res) + "\n")
    if a.report:
        results = [json.loads(x) for x in RESULTS.read_text().splitlines()] if RESULTS.exists() else []
        text = "\n".join(report(results)) + "\n"
        REPORT.write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
