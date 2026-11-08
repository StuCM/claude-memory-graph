"""What the CIDOC-CRM ontology layer answers on its own, on graphs it wasn't written against.

    .venv-ceist/bin/python packages/ceist/bench/ontology/run.py [name=<graphs dir> ...]

With no arguments it runs the local checkouts in SETS that exist; CEIST_ONTOLOGY names
another ontology layer to score (a training run's). For each set: how
independent of HER it is (same graph ids, node-alias overlap), the share of link and
date nodes whose CRM path has an ontology phrasing, and a template question set
(`questions.templated`, no LLM) scored with no vocabulary, with the ontology layer
alone, and, for "her", with the ontology layer under HER's base. Each placeholder is
filled with a made-up record name, one per model; no record data is read.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ONTOLOGY = Path(os.environ.get("CEIST_ONTOLOGY") or REPO / "vocabularies" / "ontology" / "cidoc-crm")
BASE = REPO / "vocabularies" / "base"
SETS = {
    "lingo": "/home/stuart/git/fat/arches/arches-lingo/arches_lingo/pkg/graphs/resource_models",
    "catalina": "/home/stuart/git/fat/arches/catalina/catalina-graphs/output/graphs/resource_models",
    "her": "/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models",
}
SCORES = ("right", "wrong reading", "refused", "right refusal", "wrong")
_A = ["Kel", "Dor", "Mav", "Tal", "Ruv", "Sen", "Bryn", "Gol"]
_B = ["drith", "quorn", "zabel", "mirrow", "thane"]


def graph_docs(path: str) -> list[dict]:
    """The graphs, with a null node config as {}: Alizarin refuses null (arches-lingo has it)."""
    from ceist.arches import graph_doc
    out = [graph_doc(p) for p in sorted(Path(path).glob("*.json"))]
    for g in out:
        for n in g["nodes"]:
            if n.get("config") is None:
                n["config"] = {}
    return out


def name_of(g: dict) -> str:
    n = g.get("name") or g["graphid"]
    return n.get("en") or next(iter(n.values())) if isinstance(n, dict) else n


def independence(graphs: list[dict], her: list[dict]) -> dict[str, tuple[bool, str, float]]:
    """{model: (same graph id as a HER graph, the closest HER graph, alias Jaccard with it)}."""
    def aliases(g):
        return {n["alias"] for n in g["nodes"] if n.get("alias")}
    ids, out = {h["graphid"] for h in her}, {}
    for g in graphs:
        a = aliases(g)
        near = max(her, key=lambda h: len(a & aliases(h)) / len(a | aliases(h)))
        out[name_of(g)] = (g["graphid"] in ids, name_of(near), len(a & aliases(near)) / len(a | aliases(near)))
    return out


def synthetic(graphs: list[dict]) -> list[dict]:
    """One made-up record per model, so a {Model} placeholder has a name to anchor on."""
    out = []
    for i, g in enumerate(sorted(graphs, key=name_of)):
        name = _A[i % len(_A)] + _B[i // len(_A) % len(_B)]
        out.append({"resourceinstance": {"graph_id": g["graphid"], "name": name,
                                         "resourceinstanceid": str(uuid.uuid5(uuid.NAMESPACE_URL, name))}})
    return out


def load_ontology(ontology_dir: Path = ONTOLOGY) -> dict:
    return {"entries": [e for p in sorted(Path(ontology_dir).glob("*.json"))
                        for e in json.loads(p.read_text()).get("entries", [])]}


def coverage(graphs: list[dict], ontology: dict, bundle: dict) -> tuple[list[tuple], Counter]:
    """Per model: link+date nodes, those with a CRM property, with an ontology phrasing,
    and with one the layer applied (not dropped as fitting two nodes); and how the CRM
    paths no phrasing reaches end, with how many nodes end so."""
    from ceist import crm
    from ceist.bundle import kind_of
    rows, missed = [], Counter()
    for g in graphs:
        paths = crm.chains(g)
        byalias = {n["alias"]: n for n in g["nodes"] if n.get("alias")}
        nodes = [a for a, n in byalias.items() if kind_of(n) != "property"]
        phrased = {e["node"] for e in crm.ontology_entries(g, ontology)}
        applied = {e["node"] for e in bundle["models"][name_of(g)]["entries"]}
        rows.append((name_of(g), len(nodes), sum(1 for a in nodes if paths[a][-2] != "-"),
                     sum(1 for a in nodes if a in phrased), sum(1 for a in nodes if a in applied)))
        # a date by the event its time-span hangs from, as the ontology keys it
        missed.update(" ".join(paths[a][-7:-3] if kind_of(byalias[a]) == "date" else paths[a][-3:])
                      for a in nodes if a not in phrased)
    return rows, missed


def reason(m, models) -> str:
    """A refusal with its quoted words and model names blanked, so the same cause counts once."""
    out = re.sub(r"(?<![A-Za-z])'[^']*'", "'…'", m.refused)
    for name in sorted(models, key=len, reverse=True):
        out = out.replace(name, "<M>")
    return out


def layer_bundles(name: str, graphs: list[dict], ontology_dir: Path = ONTOLOGY, base_dir: Path = BASE) -> dict:
    """{mode: bundle}: the ontology layer alone and, for "her", under HER's base."""
    from ceist.bundle import layered
    with tempfile.TemporaryDirectory() as empty:
        out = {"ontology": layered(graphs, empty, ontology_dir=ontology_dir)[0]}
    if name == "her":
        out["ontology+base"] = layered(graphs, base_dir, ontology_dir=ontology_dir)[0]
    return out


def outcomes(graphs: list[dict], resources: list[dict], bundle: dict | None, items: list[dict]):
    """(item, filled question, interpretation, score, vocabulary) for each template question."""
    from ceist import interpret
    from ceist.arches import ArchesVocabulary
    from ceist.questions import fill, score
    v = ArchesVocabulary(graphs, resources=resources, bundle=bundle)
    ends = {e["node"]: e["end_node"] for m in (bundle or {"models": {}})["models"].values()
            for e in m["entries"] if e.get("end_node")}
    for o in items:
        q = fill(o["q"], v)
        m = interpret(v, q)
        yield o, q, m, score(o, m, ends), v


def one(name: str, path: str) -> dict:
    from ceist.arches import ArchesVocabulary
    from ceist.questions import target_of, templated
    graphs = graph_docs(path)
    resources = synthetic(graphs)
    bundles = {"none": None, **layer_bundles(name, graphs)}
    ontology = load_ontology()
    items = templated(ArchesVocabulary(graphs, resources=resources), ontology)
    rows, missed = coverage(graphs, ontology, bundles["ontology"])
    out = {"coverage": rows, "unphrased": missed.most_common(10), "items": items, "scores": {}, "misses": {}}
    for mode, bundle in bundles.items():
        counts, misses, example = Counter(), Counter(), {}
        for o, q, m, s, v in outcomes(graphs, resources, bundle, items):
            counts[(o["model"], s)] += 1
            if s == "refused":
                why = reason(m, v.models)
            elif s in ("wrong reading", "wrong"):
                why = f"{s}: want {o.get('target') or o.get('reason')} got {target_of(m)}"
            else:
                continue
            misses[why] += 1
            example.setdefault(why, q)
        out["scores"][mode] = [[k[0], k[1], n] for k, n in counts.items()]
        out["misses"][mode] = [[n, why, example[why]] for why, n in misses.most_common(15)]
    return out


def table(rows: list[tuple]) -> None:
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")


def tally(rows: list, models: set[str]) -> list[int]:
    c = Counter()
    for model, s, n in rows:
        if model in models:
            c[s] += n
    return [c[s] for s in SCORES]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--one"]:
        name, path = argv[1].split("=", 1)
        print(json.dumps(one(name, path)))
        return 0
    sets = dict(a.split("=", 1) for a in argv) or {k: p for k, p in SETS.items() if Path(p).is_dir()}
    her = graph_docs(sets.get("her") or SETS["her"])
    for name, path in sets.items():
        # a process per set: Alizarin registers graphs by id, and Catalina reuses HER's ids
        res = subprocess.run([sys.executable, __file__, "--one", f"{name}={path}"], capture_output=True, text=True)
        if res.returncode:
            print(res.stderr, file=sys.stderr)
            return 1
        r = json.loads(res.stdout.splitlines()[-1])
        ind = independence(graph_docs(path), her)
        alone = {m for m, (same, _, j) in ind.items() if not same and j < 0.5}
        print(f"\n## {name}: {len(ind)} graphs, {sum(s for s, _, _ in ind.values())} with a HER graph id, "
              f"{sum(1 for _, _, j in ind.values() if j >= 0.9)} HER clones (alias overlap ≥ 0.9), "
              f"{len(alone)} independent (< 0.5, own id)\n")
        print("| graph | same id | nearest HER | overlap | link+date | with property | phrased | applied |")
        print("|---|---|---|---|---|---|---|---|")
        cov = {c[0]: c for c in r["coverage"]}
        table([(m, "yes" if s else "", h, f"{j:.2f}", *cov[m][1:]) for m, (s, h, j) in sorted(ind.items())])
        tot = [sum(c[i] for c in r["coverage"]) for i in (1, 2, 3, 4)]
        print(f"\nlink+date nodes {tot[0]}, with a CRM property {tot[1]}, phrased {tot[2]} "
              f"({100 * tot[2] / max(tot[1], 1):.0f}%), applied {tot[3]} ({100 * tot[3] / max(tot[1], 1):.0f}%)")
        print("unphrased paths (most nodes):", ", ".join(f"{p} {n}" for p, n in r["unphrased"]))
        answer = sum(1 for o in r["items"] if o["expect"] == "answer")
        print(f"\n{len(r['items'])} questions ({answer} answer, {len(r['items']) - answer} refuse)\n")
        print("| mode | questions from | " + " | ".join(SCORES) + " |")
        print("|---|---|" + "---|" * len(SCORES))
        for mode, rows in r["scores"].items():
            table([(mode, "all", *tally(rows, set(ind)))])
            if alone and alone != set(ind):
                table([(mode, "independent", *tally(rows, alone))])
        for mode, misses in r["misses"].items():
            if mode != "none":
                print(f"\nmisses, {mode}:")
                for n, why, q in misses:
                    print(f"  {n:4d}  {why[:150]}\n        e.g. {q}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
