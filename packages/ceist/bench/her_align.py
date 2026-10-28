"""Align the matcher with the graph set itself, with no new model: each signal
alone, then all together, on the 120 blind HER questions.

    uv run --with simplemma python packages/ceist/bench/her_align.py

Signals (all from files the project already has):
- crm: each node's CIDOC-CRM property and the classes of the events it sits
  in ("begin of the begin", "carried out by", "production"), as extra
  phrasings. Labels on more than 5% of a model's nodes ("has type") are noise
  and dropped;
- values: a small concept collection's own labels as phrasings for its
  node ("listed building" → designation type);
- lemma: compare word roots in the exact pass (built / build / building);
- direction: a phrase saying "from" doesn't match a phrasing saying "to"
  (or the reverse) — static vectors can't tell them apart.

Data-presence priors (prefer nodes that hold values in real records) need
business data, which the HER package doesn't ship; not tested here.
"""

import itertools
import json
import re
from collections import Counter

import compare as c
from her_compare import _covers, _entry_fits, _target, judge, load, VocabWordLlama

FROM = {"from", "leaving", "departing", "departed", "left", "out"}
TO = {"to", "towards", "toward", "into", "bound", "arriving", "arrived", "reaching"}
GENERIC = {"has type", "has note", "time span", "appellation", "is identified by"}


class Aligned(VocabWordLlama):
    def __init__(self, crm=False, values=False, lemma=False, direction=False):
        super().__init__()
        self.flags = dict(crm=crm, values=values, lemma=lemma, direction=direction)
        on = [k for k, v in self.flags.items() if v]
        self.name = "vocabulary + WordLlama" + ("".join(f" + {k}" for k in on) or " (baseline)")
        self._enriched = {}
        if lemma:
            import simplemma
            self._lem = lambda w: simplemma.lemmatize(w, lang="en")

    def norm(self, text):
        words = re.findall(r"[a-z0-9]+", text.lower())
        if self.flags["lemma"]:
            words = [self._lem(w) for w in words]
        return " ".join(words)

    def enrich(self, model, nodes, entries):
        if model in self._enriched:
            return self._enriched[model]
        by = {n["alias"]: n for n in nodes}
        freq = Counter(x for n in nodes for x in n.get("crm", []))
        common = {x for x, k in freq.items() if k > 0.05 * len(nodes)} | GENERIC
        out = []
        for e in entries:
            extra = []
            n = by.get(e["node"], {})
            if self.flags["crm"]:
                extra += [x for x in n.get("crm", []) if x not in common]
            if self.flags["values"] and isinstance(n.get("values"), list) and not e.get("qualifier"):
                extra += [re.sub(r"\s*\(.*?\)", "", v).lower() for v in n["values"]]
            out.append(dict(e, phrases=list(dict.fromkeys(e["phrases"] + extra))))
        self._enriched[model] = out
        return out

    def clash(self, phrase_words: set, phrasing: str) -> bool:
        if not self.flags["direction"]:
            return False
        w = set(phrasing.split())
        return bool((phrase_words & FROM and w & TO and not w & FROM)
                    or (phrase_words & TO and w & FROM and not w & TO))

    def pick(self, case, nodes, entries):
        entries = self.enrich(case["model"], nodes, entries)
        by = {n["alias"]: n for n in nodes}
        p = self.norm(case["phrase"])
        pw = set(case["phrase"].lower().split())
        # exact pass (word roots when lemma is on)
        hits = {}
        for e in entries:
            if not _entry_fits(e, by, case["slot"]):
                continue
            for ph in e["phrases"]:
                v = self.norm(ph)
                if self.clash(pw, ph.lower()):
                    continue
                if v == p:
                    score = 3
                elif _covers(v, p) or _covers(p, v):
                    score = 1 + (len(v) > 3)
                else:
                    continue
                k = _target(e)
                hits[k] = max(hits.get(k, 0), score)
        if hits:
            top = max(hits.values())
            winners = [k for k, s in hits.items() if s == top]
            if len(winners) == 1:
                return winners[0], [(1.0, winners[0])]
        # meaning pass
        pv = self.vec(case["phrase"])
        best = {}
        for e in entries:
            if not _entry_fits(e, by, case["slot"]):
                continue
            s = max(float(pv @ self.cvec(ph)) - (0.3 if self.clash(pw, ph.lower()) else 0)
                    for ph in e["phrases"])
            k = _target(e)
            best[k] = max(best.get(k, -1), s)
        scored = [(s, k) for k, s in best.items()]
        return self.choose(scored), scored


def one_click(case, got, scored) -> bool:
    """Right outright, or abstained with the expected node in the top three."""
    if judge(case, got) == "right":
        return True
    want = case["expect"]
    if got is not None or want is None:
        return False
    top = sorted(scored or [], key=lambda x: -x[0])[:3]
    return any(want["node"] in (k[0], k[2]) for _, k in top)


def main():
    models, vocab, cases = load()
    n_none = sum(x["expect"] is None for x in cases)
    n_match = len(cases) - n_none
    names = ["crm", "values", "lemma", "direction"]
    configs = [{}] + [{k: True} for k in names] + [dict.fromkeys(names, True)]
    lines = ["# Graph-alignment signals on the blind HER questions", "",
             f"{n_match} questions where a node fits, {n_none} where none does.", ""]
    for low in (0.4, 0.6, 0.7):
        c.Threshold.low = low
        lines += [f"## threshold {low}", "",
                  "| variant | right | dangerous | missed | refused correctly | right within one click |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for cfg in configs:
            m = Aligned(**cfg)
            t = Counter()
            click = 0
            for case in cases:
                nodes = models[case["model"]]["nodes"]
                got, scored = m.pick(case, nodes, vocab.get(case["model"], []))
                t[judge(case, got)] += 1
                click += one_click(case, got, scored)
            lines.append(f"| {m.name} | {t['right']}/{n_match} | **{t['wrong'] + t['false_match']}** | "
                         f"{t['missed']} | {t['abstained_ok']}/{n_none} | {click}/{n_match} |")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    (c.HERE / "results").mkdir(exist_ok=True)
    (c.HERE / "results" / "her_align.md").write_text(text)


if __name__ == "__main__":
    main()
