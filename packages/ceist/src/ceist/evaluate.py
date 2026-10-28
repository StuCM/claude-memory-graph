"""Acceptance scoring: a bundle and a matching config against questions with
agreed answers — what a project ships is exactly what is measured.

A question file:

    {"cases": [{"model": "Monument", "q": "which monuments were put up before 1900?",
                "phrase": "put up", "slot": "date" | "link:<Model>" | "property",
                "expect": null | {"node": "<alias>", "qualifier": {"node", "value"}}}]}

Outcomes:
    right       the expected node (either end of a date's timespan) and qualifier
    partial     the right node, the qualifier missing (broader than asked)
    dangerous   a wrong node or qualifier, or an answer where none fits
    missed      no answer where one fits (the planner asks or refuses)
    refused     no answer where none fits (correct)
    one click   right, or missed with the expected node among the "did you mean" options
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import bundle as _bundle
from . import config as _config
from .matching import Item


def fits(node: dict, slot: str) -> bool:
    if slot == "date":
        return node.get("kind") == "date"
    if slot.startswith("link:"):
        return node.get("kind") == "link" and slot[5:] in (node.get("targets") or [])
    return node.get("kind") == "property"


def items_for(model: dict, slot: str) -> list[Item]:
    """The shortlist: the model's entries whose node fits the slot."""
    out = []
    for e in model["entries"]:
        n = model["nodes"].get(e["node"])
        if n is None or not fits(n, slot):
            continue
        q = (e.get("qualifier") or {}).get("value")
        label = n.get("label", e["node"]) + (f" ({q})" if q else "")
        out.append(Item((e["node"], q, e.get("end_node")), tuple(e["phrases"]), label, e))
    return out


def judge(expect: dict | None, key) -> str:
    if expect is None:
        return "refused" if key is None else "dangerous"
    if key is None:
        return "missed"
    node, qual, end = key
    want_q = (expect.get("qualifier") or {}).get("value")
    if expect["node"] not in (node, end):
        return "dangerous"
    if want_q and not qual:
        return "partial"
    if (qual or "").lower() != (want_q or "").lower():
        return "dangerous"
    return "right"


@dataclass
class Result:
    config: _config.Config
    counts: dict = field(default_factory=dict)
    one_click: int = 0
    n_match: int = 0
    n_none: int = 0
    ms: float = 0.0
    rows: list = field(default_factory=list)
    built: dict = field(default_factory=dict)


def evaluate(bundle_path, questions_path, cfg: _config.Config | None = None, encoder=None) -> Result:
    cfg = cfg or _config.load(None)
    b = _bundle.load(bundle_path)
    cases = json.loads(Path(questions_path).read_text())["cases"]
    chain = _config.chain(cfg, encoder=encoder)
    res = Result(cfg, dict.fromkeys(["right", "partial", "dangerous", "missed", "refused"], 0),
                 built=b.get("built", {}))
    t0 = time.perf_counter()
    for c in cases:
        model = b["models"].get(c["model"])
        items = items_for(model, c["slot"]) if model else []
        r = chain.resolve(c["phrase"], items, c["q"])
        key = r.match.item.key if r.match else None
        outcome = judge(c["expect"], key)
        res.counts[outcome] += 1
        if c["expect"] is not None:
            res.n_match += 1
            want = c["expect"]["node"]
            if outcome == "right" or (key is None and any(want in (o.key[0], o.key[2])
                                                          for o in r.options)):
                res.one_click += 1
        else:
            res.n_none += 1
        res.rows.append({"q": c["q"], "phrase": c["phrase"], "expect": c["expect"],
                         "got": list(key) if key else None, "outcome": outcome,
                         "layer": r.match.layer if r.match else None,
                         "options": [o.label for o in r.options], "notes": r.notes})
    res.ms = (time.perf_counter() - t0) * 1000 / max(len(cases), 1)
    return res


def report(r: Result) -> str:
    c, cfg = r.counts, r.config
    lines = [
        "# ceist acceptance report", "",
        f"Bundle: {r.built.get('models')} models, {r.built.get('entries')} entries, "
        f"{r.built.get('phrasings')} phrasings.",
        f"Matching: layers {', '.join(cfg.layers) or 'none'}; roots {cfg.roots}, direction "
        f"{cfg.direction}; vectors min {cfg.low}, gap {cfg.gap}; chooser {cfg.chooser}."
        + (" " + " ".join(cfg.notes) if cfg.notes else ""), "",
        "| right | partial | dangerous | missed | refused correctly | right within one click | ms/question |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        f"| {c['right']}/{r.n_match} | {c['partial']} | **{c['dangerous']}** | {c['missed']} | "
        f"{c['refused']}/{r.n_none} | {r.one_click}/{r.n_match} | {r.ms:.1f} |", ""]
    bad = [x for x in r.rows if x["outcome"] == "dangerous"]
    if bad:
        lines += ["Dangerous answers:", ""]
        for x in bad:
            want = x["expect"]["node"] if x["expect"] else "nothing"
            lines.append(f"- \"{x['phrase']}\" ({x['q']}): expected {want}, got "
                         f"{x['got'][0] if x['got'] else '?'} ({x['layer']})")
        lines.append("")
    return "\n".join(lines)
