"""`ceist vocab crm-first`: move each base- and client-layer phrasing that a CIDOC-CRM path can
carry into the ontology layer, through the gate, and give every phrasing left behind its reason.

    classify  per phrasing: promotable (on the shortest CRM path that reaches at most one node
              in every model of every graph set), ambiguous path, non-CRM, site-specific,
              clash, or already in the ontology layer (CRM-FIRST-CHECK.md §7)
    gate      the promotable ones, one candidate per (path, kind), through bench/ontology/gate.py
    move      what the gate accepts into phrases.json; a base or client copy is removed only
              when the layered bundles still give its node that phrase from the ontology
    ledger    <out>/crm-first.json: every phrasing left in a graph or client layer, with its reason
"""

import json
import re
from collections import Counter
from pathlib import Path

from . import bundle as _bundle
from . import crm, ontology_vocab
from .arches import graph_doc

STANDARD = re.compile(r"^(E|P|O|S|SP|L|D|Q|R|F)\d+[a-z]?i?$")
CLASSES = ("promotable", "promotable longer path", "ambiguous path", "non-CRM", "site-specific",
           "clash", "gate-rejected", "not applied", "already in ontology")
LEFT = ("ambiguous path", "non-CRM", "site-specific", "clash", "gate-rejected", "not applied")
LEDGER = "crm-first.json"
# local administrative terms that a CRM path would carry everywhere (the check's §2, by hand)
LOCAL = {"county", "counties"}


def _custom(token: str) -> bool:
    return token == "-" or not STANDARD.match(token) or bool(re.match(r"^P0\d", token))


def _norm(phrase: str) -> str:
    return " ".join(w[:-1] if w.endswith("s") and len(w) > 3 else w for w in phrase.strip().lower().split())


def _name(g: dict) -> str:
    n = g.get("name") or g["graphid"]
    return (n.get("en") or next(iter(n.values()))) if isinstance(n, dict) else n


class Sets:
    """The graph sets a CRM path must mean one thing in: {(set index, graph id): {alias: (kind, tokens)}}."""

    def __init__(self, graph_dirs):
        self.graphs = [(i, graph_doc(p)) for i, d in enumerate(graph_dirs) for p in sorted(Path(d).glob("*.json"))]
        self.keys = {(i, g["graphid"]): crm.keyed(g) for i, g in self.graphs}

    def graph(self, graphid: str) -> dict | None:
        """The first set's graph with this id: the base layer's graphs come first."""
        return next((g for _, g in self.graphs if g["graphid"] == graphid), None)

    def keyed(self, graphid: str) -> dict:
        return next((self.keys[(i, gid)] for i, gid in self.keys if gid == graphid), {})

    def reach(self, path: str, kind: str) -> dict[tuple, int]:
        """{(set, graph id): nodes of this kind the path reaches}, as crm.ontology_entries matches."""
        want = ("property", "field") if kind in ("property", "field") else (kind,)
        p, out = path.split(), {}
        for k, keys in self.keys.items():
            n = sum(1 for kd, tokens in keys.values() if kd in want and crm._ends_with(tokens, p))
            if n:
                out[k] = n
        return out


def _choose(sets: Sets, kind: str, tokens: list[str]) -> tuple[str | None, bool, dict]:
    """(path, longer, reach): from the 3-token key up, without then with the node class, the
    first path that reaches at most one node in every model. Never under 3 tokens: "E5 P4" was
    unique and carried "inhabited" onto every E5 time-span."""
    keyed, cls = (tokens, None) if kind == "date" else (tokens[:-1], tokens[-1])
    short, last = min(3, len(keyed)), {}
    for n in range(short, len(keyed) + 1):
        tail = keyed[-n:]
        if any(_custom(t) for t in tail):
            break
        for path in [tail] + ([tail + [cls]] if cls else []):
            reach = sets.reach(" ".join(path), kind)
            if reach and max(reach.values()) == 1:
                return " ".join(path), n > short or path[-1] == cls, reach
            last = reach
    return None, False, last


def phrasings(base_dir: Path, client_dir: Path | None) -> list[dict]:
    """Every phrase in the base and client group files: an entry's, a nodegroup's or a combo's."""
    out = []
    dirs = [("base", d, d.name) for d in sorted(Path(base_dir).iterdir()) if d.is_dir()]
    if client_dir:
        listed = _bundle._manifest(Path(client_dir)).get("models") or {}
        dirs += [("client", d, (listed.get(d.name) or {}).get("graphid"))
                 for d in sorted(Path(client_dir).iterdir()) if d.is_dir()]
    for layer, d, gid in dirs:
        for f in sorted(d.glob("*.json")):
            if f.name == _bundle.MANIFEST:
                continue
            doc = json.loads(f.read_text())
            at = dict(layer=layer, graphid=gid, model=d.name if layer == "client" else doc["model"], file=str(f))
            for e in doc["entries"]:
                where = "qualified" if e.get("qualifier") else "entry"
                rest = {k: v for k, v in e.items() if k != "phrases"}
                out += [dict(at, where=where, node=e["node"], kind=e["kind"], phrase=p, entry=rest) for p in e["phrases"]]
            block = doc.get("group") or {}
            out += [dict(at, where="group", node=doc["nodegroup"], kind="group", phrase=p)
                    for p in block.get("phrases") or []]
            out += [dict(at, where="combo", node=",".join(c["set"]), kind="combo", phrase=p)
                    for c in block.get("combos") or [] for p in c["phrases"]]
    return out


def classify(units: list[dict], sets: Sets, ontology: dict, generic: set[str]) -> None:
    """Set "class" and "why" on each phrasing, and "path" and "kind" (the ontology entry's) on
    the promotable ones."""
    on_path: dict[str, set] = {}
    for e in ontology["entries"]:
        for p in e["phrases"]:
            on_path.setdefault(p.strip().lower(), set()).add(e["path"])
    applied, chosen = {}, {}
    for u in units:
        if u["where"] in ("combo", "qualified"):
            u.update({"class": "site-specific", "why": "value-qualified"})
            continue
        if u["where"] == "group":
            u.update({"class": "non-CRM", "why": "a nodegroup phrase: the ontology layer has no group kind"})
            continue
        g = sets.graph(u["graphid"] or "")
        keys = sets.keyed(u["graphid"] or "")
        if u["node"] not in keys:
            u.update({"class": "non-CRM", "why": "no CRM path the ontology layer keys (a date with no "
                                                 "time-span begin or end, or a node outside the graph)"})
            continue
        kind, tokens = keys[u["node"]]
        if _custom(tokens[-1] if kind == "date" else tokens[-2]):
            u.update({"class": "non-CRM", "why": "the property into it is not standard CRM"})
            continue
        ph = u["phrase"].strip().lower()
        if ph in LOCAL:
            u.update({"class": "site-specific", "why": "a local term"})
            continue
        if g["graphid"] not in applied:
            applied[g["graphid"]] = {(e["node"], p.strip().lower()) for e in crm.ontology_entries(g, ontology)
                                     for p in e["phrases"]}
        if (u["node"], ph) in applied[g["graphid"]]:
            u.update({"class": "already in ontology", "why": "applied today"})
            continue
        key = (g["graphid"], u["node"])
        if key not in chosen:
            chosen[key] = _choose(sets, kind, tokens)
        path, longer, reach = chosen[key]
        if path is None:
            many = sum(1 for n in reach.values() if n > 1)
            u.update({"class": "ambiguous path", "why": f"every CRM path reaches 2+ nodes in {many} models"})
            continue
        clash = sorted(q for q in on_path.get(ph, ()) if not ontology_vocab._extends(path, q))
        if ph in generic:
            u.update({"class": "clash", "why": "generic.json"})
        elif clash:
            u.update({"class": "clash", "why": f"already on {', '.join(clash)}"})
        else:
            u.update({"class": "promotable longer path" if longer else "promotable", "path": path, "kind": kind,
                      "reach": sum(reach.values()), "why": path})
    _split(units)
    _siblings(units)


def _promotable(units: list[dict]) -> list[dict]:
    return [u for u in units if u["class"].startswith("promotable")]


def _split(units: list[dict]) -> None:
    """A path whose source nodes share no phrasing and no alias across graphs means two things: ambiguous."""
    by_path: dict[tuple, list[dict]] = {}
    for u in _promotable(units):
        by_path.setdefault((u["path"], u["kind"]), []).append(u)
    for (path, _), us in by_path.items():
        said: dict[tuple, set] = {}
        for u in us:
            said.setdefault((u["graphid"], u["node"]), set()).add(_norm(u["phrase"]))
        group = {s: s for s in said}

        def root(s):
            while group[s] != s:
                s = group[s]
            return s
        nodes = list(said)
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                if said[a] & said[b] or a[1] == b[1]:
                    group[root(a)] = root(b)
        parts = {root(s) for s in nodes}
        if len(parts) > 1:
            for u in us:
                u.update({"class": "ambiguous path",
                          "why": f"cross-graph: {path} holds {len(parts)} unrelated sets of phrasings"})


def _siblings(units: list[dict]) -> None:
    """A phrase promoted on two paths that neither extends keeps the one that reaches most nodes."""
    by_phrase: dict[tuple, list[dict]] = {}
    for u in _promotable(units):
        by_phrase.setdefault((u["phrase"].strip().lower(), u["kind"]), []).append(u)
    for us in by_phrase.values():
        reach = {u["path"]: u["reach"] for u in us}
        if len(reach) < 2:
            continue
        keep = max(reach, key=lambda p: (reach[p], p))
        for u in us:
            if u["path"] != keep and not ontology_vocab._extends(u["path"], keep) \
                    and not ontology_vocab._extends(keep, u["path"]):
                u.update({"class": "clash", "why": f"promoted on {keep} too, which reaches more nodes"})


def candidates(units: list[dict]) -> list[dict]:
    """One ontology candidate per (path, kind) of the promotable phrasings."""
    out: dict[tuple, dict] = {}
    for u in _promotable(units):
        c = out.setdefault((u["path"], u["kind"]), {"layer": "ontology", "path": u["path"], "kind": u["kind"],
                                                     "phrases": []})
        ph = u["phrase"].strip().lower()
        if ph not in c["phrases"]:
            c["phrases"].append(ph)
    return list(out.values())


def _bundle_phrases(sets: Sets, base_dir: Path, client_dir: Path | None, ontology_dir: Path) -> dict[tuple, set]:
    """{(graph id, model, node): phrases} the layered bundles give: the base's graphs over the
    base, the client's over base and client."""
    out: dict[tuple, set] = {}
    base_graphs = [sets.graph(d.name) for d in sorted(Path(base_dir).iterdir()) if d.is_dir()]
    runs = [([g for g in base_graphs if g], None)]
    if client_dir:
        listed = _bundle._manifest(Path(client_dir)).get("models") or {}
        runs.append(([g for m in listed.values() if (g := sets.graph(m["graphid"]))], client_dir))
    for graphs, client in runs:
        b, _ = _bundle.layered(graphs, base_dir, client, ontology_dir=ontology_dir)
        ids = {_name(g): g["graphid"] for g in graphs}
        for model, m in b["models"].items():
            for e in m["entries"]:
                out.setdefault((ids.get(model), model, e["node"]), set()).update(p.strip().lower() for p in e["phrases"])
    return out


def _remove(units: list[dict]) -> None:
    """Take these phrasings out of their group files; an entry left with no phrase goes."""
    by_file: dict[str, set] = {}
    for u in units:
        by_file.setdefault(u["file"], set()).add((u["node"], u["kind"], u["phrase"]))
    for f, gone in by_file.items():
        doc = json.loads(Path(f).read_text())
        entries = []
        for e in doc["entries"]:
            if not e.get("qualifier"):
                e["phrases"] = [p for p in e["phrases"] if (e["node"], e["kind"], p) not in gone]
            if e["phrases"]:
                entries.append(e)
        doc["entries"] = entries
        Path(f).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def move(units: list[dict], sets: Sets, base_dir: Path, client_dir: Path | None, ontology_dir: Path) -> list[dict]:
    """Remove the moved phrasings from their layer; put back any whose node the bundles no longer
    give that phrase (the ontology layer dropped it as fitting two nodes, or the base holds it for
    another node). The ones put back."""
    before = _bundle_phrases(sets, base_dir, client_dir, ontology_dir)
    moved = [u for u in units if u["class"] in ("promotable", "promotable longer path", "already in ontology")]
    _remove(moved)
    # a client model's base is another graph id: a lost phrase there names its base's phrasings too
    listed = _bundle._manifest(Path(client_dir)).get("models") or {} if client_dir else {}
    back: list[dict] = []
    while True:
        after = _bundle_phrases(sets, base_dir, client_dir, ontology_dir)
        lost = {(k[0], ph) for k, ps in before.items() for ph in ps - after.get(k, set())}
        lost |= {(m["base"], ph) for gid, ph in set(lost) for m in listed.values() if m["graphid"] == gid}
        more = [u for u in moved if u not in back and (u["graphid"], u["phrase"].strip().lower()) in lost]
        if not more:
            return back
        back += more
        _restore(more)


def _restore(units: list[dict]) -> None:
    by_file: dict[str, list[dict]] = {}
    for u in units:
        by_file.setdefault(u["file"], []).append(u)
    for f, us in by_file.items():
        doc = json.loads(Path(f).read_text())
        for u in us:
            e = next((e for e in doc["entries"] if e["node"] == u["node"] and e["kind"] == u["kind"]
                      and not e.get("qualifier")), None)
            if e is None:
                doc["entries"].append(dict({"phrases": [u["phrase"]]}, **u["entry"]))
            elif u["phrase"] not in e["phrases"]:
                e["phrases"].append(u["phrase"])
        Path(f).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def ledger(units: list[dict]) -> dict:
    """{"summary": {layer: {class: n}}, "graphs": {layer: {model: {class: n}}},
    "left": {layer: {model: {node: {phrase: "class: why"}}}}}."""
    out = {"format": "ceist.crm-first/1", "summary": {}, "graphs": {}, "left": {}}
    for u in units:
        out["summary"].setdefault(u["layer"], Counter())[u["class"]] += 1
        out["graphs"].setdefault(u["layer"], {}).setdefault(u["model"], Counter())[u["class"]] += 1
        if u["class"] in LEFT:
            node = out["left"].setdefault(u["layer"], {}).setdefault(u["model"], {}).setdefault(u["node"], {})
            node[u["phrase"]] = f"{u['class']}: {u['why']}"
    return out


def run(graph_dirs, base_dir: Path, client_dir: Path | None, ontology_dir: Path, out: Path,
        review_only: bool = False, skip=(), gate_cmd: list[str] | None = None, log=print) -> int:
    """classify → gate → move → ledger, and <out>/crm-first.md."""
    from . import vocab_rules
    base_dir, ontology_dir, out = Path(base_dir), Path(ontology_dir), Path(out)
    client_dir = Path(client_dir) if client_dir else None
    sets = Sets(graph_dirs)
    ontology = ontology_vocab.load(ontology_dir)
    generic = set(json.loads((ontology_dir / ontology_vocab.GENERIC).read_text())["phrases"])
    units = phrasings(base_dir, client_dir)
    classify(units, sets, ontology, generic)
    before = Counter(u["class"] for u in units)
    log("classified: " + ", ".join(f"{n} {k}" for k, n in before.most_common()))
    cands = candidates(units)
    log(f"{len(cands)} candidates (path, kind) to the gate")
    verdict = {}
    if review_only:
        for u in _promotable(units):
            u.update({"class": "gate-rejected", "why": "not gated (review only)"})
    elif cands:
        layers = vocab_rules.Layers([], base_dir, client_dir, ontology_dir)
        verdict = vocab_rules.run_gate(cands, layers, skip, gate_cmd)
        if verdict is None:
            return 1
        passed = set(verdict["accepted"])
        vocab_rules.apply([dict(c, phrases=[p for p in c["phrases"] if p not in vocab_rules.gate_cut(c, verdict)])
                           for c in cands if f"{c['kind']} {c['path']}" in passed], ontology_dir, base_dir, client_dir)
        for u in _promotable(units):
            k = f"{u['kind']} {u['path']}"
            cut = vocab_rules.gate_cut(dict(u, layer="ontology"), verdict)
            if k not in passed:
                u.update({"class": "gate-rejected", "why": verdict["rejected"].get(k, "?")})
            elif u["phrase"].strip().lower() in cut:
                u.update({"class": "gate-rejected", "why": cut[u["phrase"].strip().lower()]})
    back = [] if review_only else move(units, sets, base_dir, client_dir, ontology_dir)
    for u in back:
        u.update({"class": "not applied", "why": "the layered bundle would no longer give its node this phrase"})
    doc = ledger(units)
    doc["gate"] = verdict or None
    out.mkdir(parents=True, exist_ok=True)
    (out / LEDGER).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    (out / "crm-first.md").write_text(report_md(doc, cands, verdict))
    if not review_only:
        moved = sum(1 for u in units if u["class"].startswith("promotable") or u["class"] == "already in ontology")
        log(f"{moved} phrasings now come from the ontology layer; {len(back)} put back")
    log(f"ledger → {out / LEDGER}")
    return 0


def report_md(doc: dict, cands: list[dict], verdict: dict) -> str:
    lines = ["# CRM-first: where each phrasing lives", "",
             "Moved: promotable (and promotable on a longer path) phrasings the gate accepted, and copies of "
             "phrasings the ontology layer already gave; each is now in phrases.json only. Every other "
             "phrasing stays in its layer with the reason below.", ""]
    lines += ["| layer | " + " | ".join(CLASSES) + " |", "| --- " * (len(CLASSES) + 1) + "|"]
    lines += [f"| {layer} | " + " | ".join(str(n.get(c, 0)) for c in CLASSES) + " |"
              for layer, n in doc["summary"].items()]
    lines += ["", "## Per graph", "", "| layer | graph | " + " | ".join(CLASSES) + " |", "| --- " * (len(CLASSES) + 2) + "|"]
    lines += [f"| {layer} | {m} | " + " | ".join(str(n.get(c, 0)) for c in CLASSES) + " |"
              for layer, ms in doc["graphs"].items() for m, n in sorted(ms.items())]
    if verdict:
        passed = set(verdict["accepted"])
        lines += ["", f"## Gate: {len(passed)} of {len(cands)} accepted", "", "| kind | path | phrases | verdict |",
                  "| --- " * 4 + "|"]
        for c in cands:
            k = f"{c['kind']} {c['path']}"
            said = "accepted" if k in passed else verdict["rejected"].get(k, "?")
            lines.append(f"| {c['kind']} | {c['path']} | {', '.join(c['phrases'])} | {said} |")
        lines += ["", "## Gate checks", ""] + [f"- {c}" for c in verdict.get("checks", [])]
        lines += ["", "Bench counts: right / wrong reading / refused / right refusal / wrong.", ""]
        lines += ontology_vocab._tally_rows(verdict)
    return "\n".join(lines) + "\n"
