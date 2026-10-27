"""The matcher comparison at HER scale: 16 real Arches HER models (arches-her),
2,327 searchable nodes, an LLM-built vocabulary per model (her/vocab/), and
held-out questions written blind to it (her/cases.json).

    uv run python packages/ceist/bench/her_compare.py

A case is right when the matcher lands on the expected node — for a date,
either end of the expected event's timespan — AND the expected qualifier
(e.g. role = Architect for "designed by"). Partial: right node, qualifier
missing (broader than asked). Dangerous: wrong node, wrong qualifier, or a
pick where nothing fits.
"""

import json
import os
import re
import time
from pathlib import Path

from compare import Skip, Threshold, WordLlama, describe as _describe, _norm

HER = Path(__file__).parent / "her"
DATE = {"date", "edtf"}


def load():
    models = {json.loads(p.read_text())["name"]: json.loads(p.read_text())
              for p in sorted((HER / "models").glob("*.json"))}
    vocab = {}
    for p in sorted((HER / "vocab").glob("*.json")):
        v = json.loads(p.read_text())
        vocab[v["model"]] = v["entries"]
    cases = json.loads((HER / "cases.json").read_text())["cases"]
    return models, vocab, cases


def kind_of(node: dict) -> str:
    if node["datatype"] in DATE:
        return "date"
    if node["datatype"].startswith("resource-instance"):
        return "link"
    return "property"


def fits(node: dict, slot: str) -> bool:
    if slot == "date":
        return kind_of(node) == "date"
    if slot.startswith("link:"):
        return kind_of(node) == "link" and slot[5:] in node.get("targets", [])
    return kind_of(node) == "property"


def node_text(n: dict) -> str:
    words = [n.get("label") or n["name"], n.get("card", "")]
    return _describe({"name": " ".join(w for w in words if w), "group": ""})


# a matcher returns (node alias, qualifier value | None, end node | None) or None

class NodeNames(WordLlama):
    """WordLlama on the node's own name, label and card — no vocabulary."""
    name = "WordLlama on node names + cards"

    def pick(self, case, nodes, entries):
        p = self.vec(case["phrase"])
        cands = [n for n in nodes if fits(n, case["slot"])]
        scored = [(float(p @ self.vec(node_text(n))), n["alias"]) for n in cands]
        got = self.choose(scored)
        return (got, None, None) if got else None, scored


def _entry_fits(e: dict, nodes_by_alias: dict, slot: str) -> bool:
    n = nodes_by_alias.get(e["node"])
    return n is not None and fits(n, slot)


class VocabExact:
    name = "vocabulary + exact words"

    def pick(self, case, nodes, entries):
        by = {n["alias"]: n for n in nodes}
        p = _norm(case["phrase"])
        hits = {}
        for e in entries:
            if not _entry_fits(e, by, case["slot"]):
                continue
            for ph in e["phrases"]:
                v = _norm(ph)
                if v == p:
                    score = 3
                elif _covers(v, p) or _covers(p, v):
                    score = 1 + (len(v) > 3)
                else:
                    continue
                key = _target(e)
                hits[key] = max(hits.get(key, 0), score)
        if not hits:
            return None, None
        top = max(hits.values())
        winners = [k for k, s in hits.items() if s == top]
        return (winners[0] if len(winners) == 1 else None), None


def _covers(inner: str, outer: str) -> bool:
    """`inner` appears in `outer` as whole words AND is most of it — so a
    vocabulary "metal" doesn't claim "turned up by metal detectorists"."""
    return (f" {inner} " in f" {outer} "
            and len(inner.split()) * 2 >= len(outer.split()))


def _target(e: dict):
    q = e.get("qualifier") or {}
    return (e["node"], q.get("value"), e.get("end_node"))


class VocabWordLlama(WordLlama):
    name = "vocabulary + WordLlama"

    def __init__(self):
        super().__init__()
        self.exact = VocabExact()
        self._cache = {}

    def cvec(self, text):
        if text not in self._cache:
            self._cache[text] = self.vec(text)
        return self._cache[text]

    def pick(self, case, nodes, entries):
        hit, _ = self.exact.pick(case, nodes, entries)
        if hit:
            return hit, None
        by = {n["alias"]: n for n in nodes}
        p = self.vec(case["phrase"])
        best = {}
        for e in entries:
            if not _entry_fits(e, by, case["slot"]):
                continue
            s = max(float(p @ self.cvec(ph)) for ph in e["phrases"])
            k = _target(e)
            best[k] = max(best.get(k, -1), s)
        scored = [(s, k) for k, s in best.items()]
        return self.choose(scored), scored


class Adapted(VocabWordLlama):
    """vocabulary + WordLlama with a trained domain adapter (adapt.py)."""

    def __init__(self, path: str):
        super().__init__()
        import numpy as np
        self.np = np
        z = np.load(path)
        self.kind = str(z["kind"])
        self.name = f"vocabulary + WordLlama + {self.kind} adapter"
        if self.kind == "linear":
            self.A = z["A"].astype(np.float32)
        else:
            self.E = np.asarray(self.enc.weights, dtype=np.float32).copy()
            self.E[z["tokens"]] += z["delta"].astype(np.float32)

    def vec(self, text):
        np = self.np
        if self.kind == "linear":
            v = self.enc.encode([text])[0] @ self.A
        else:
            ids = self.enc._ids(re.findall(r"\w+", text))
            if not ids:
                return np.zeros(self.E.shape[1], dtype=np.float32)
            v = self.E[ids].mean(0)
        return v / (np.linalg.norm(v) or 1)


def judge(case, got) -> str:
    want = case["expect"]
    if want is None:
        return "abstained_ok" if got is None else "false_match"
    if got is None:
        return "missed"
    node, qual, end = got
    want_q = (want.get("qualifier") or {}).get("value")
    if want["node"] not in (node, end):
        return "wrong"
    if want_q and not qual:
        return "partial"
    if (qual or "").lower() != (want_q or "").lower():
        return "wrong"
    return "right"


def main():
    models, vocab, cases = load()
    out = []
    matchers = []
    makers = [NodeNames, VocabExact, VocabWordLlama]
    makers += [lambda p=p: Adapted(p) for p in os.environ.get("CEIST_ADAPTERS", "").split(",") if p]
    for make in makers:
        try:
            matchers.append(make())
        except Skip as why:
            out.append(f"(skipped: {why})")
    n_none = sum(c["expect"] is None for c in cases)
    n_match = len(cases) - n_none
    phrases = sum(len(e["phrases"]) for es in vocab.values() for e in es)
    vbytes = sum((HER / "vocab" / f"{m}.json").stat().st_size for m in vocab)
    lines = ["# HER-scale matcher comparison", "",
             f"{len(models)} models, {sum(len(m['nodes']) for m in models.values())} searchable "
             f"nodes; vocabulary: {sum(len(e) for e in vocab.values())} entries, {phrases} phrasings, "
             f"{vbytes // 1024} KB; {len(cases)} held-out questions ({n_match} where a node fits, "
             f"{n_none} where none does).", "",
             "| matcher | right | partial (qualifier missing) | dangerous | missed | abstained correctly | ms/question |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    details = {}
    for m in matchers:
        tally = dict.fromkeys(["right", "partial", "wrong", "false_match", "missed", "abstained_ok"], 0)
        rows, t0 = [], time.perf_counter()
        for c in cases:
            nodes = models[c["model"]]["nodes"]
            got, scored = m.pick(c, nodes, vocab.get(c["model"], []))
            r = judge(c, got)
            tally[r] += 1
            rows.append({"model": c["model"], "q": c["q"], "phrase": c["phrase"], "expect": c["expect"],
                         "got": got, "result": r,
                         "top": [(round(s, 3), k) for s, k in sorted(scored or [], key=lambda x: -x[0])[:3]]})
        ms = (time.perf_counter() - t0) * 1000 / len(cases)
        lines.append(f"| {m.name} | {tally['right']}/{n_match} | {tally['partial']} | "
                     f"**{tally['wrong'] + tally['false_match']}** | {tally['missed']} | "
                     f"{tally['abstained_ok']}/{n_none} | {ms:.1f} |")
        details[m.name] = rows
    text = "\n".join(lines + [""] + out)
    print(text)
    res = Path(os.environ.get("CEIST_BENCH_OUT", Path(__file__).parent / "results"))
    res.mkdir(parents=True, exist_ok=True)
    (res / "her_report.md").write_text(text)
    (res / "her_details.json").write_text(json.dumps(details, indent=1, default=list))


if __name__ == "__main__":
    main()
