"""Cut a vocabulary down to what one dataset uses (`ceist vocab slice`).

The business data is read here, on this machine; it never goes to an LLM.
Kept:

- the nodegroups that hold tiles, and their ancestors;
- links whose target model has records;
- qualified entries whose value occurs in the data, or is broader than one
  that does ("listed" covers "Grade II"); only checked with reference data.
  A group block's combos are cut the same way, and the block goes with its
  nodegroup.

What was cut is recorded under "sliced", so a refusal can say "this dataset
holds no construction phases" rather than "couldn't place".
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from .arches import CONTROLLED_TYPES, LINK_TYPES, ArchesVocabulary, graph_doc, read_resources
from .bundle import MANIFEST, nodegroups


class Usage:
    """What a dataset uses of its models: records, nodegroups, controlled values."""

    def __init__(self, graphs_dir: str | Path, data_dir: str | Path,
                 reference_dir: str | Path | None = None):
        rdm = None
        if reference_dir:
            from .arches_describe import load_rdm
            rdm = load_rdm(reference_dir)
        self.vocab = ArchesVocabulary([graph_doc(p) for p in sorted(Path(graphs_dir).glob("*.json"))],
                                      rdm)
        self.records: Counter = Counter()
        self.tiles: Counter = Counter()                    # (model, nodegroup alias) → tiles
        self.group_of: dict[str, dict[str, str]] = {}      # model → node alias → nodegroup alias
        self.groups: dict[str, dict[str, dict]] = {}       # model → nodegroup alias → {id, parent}
        self.nodes: dict[str, dict[str, dict]] = {}        # model → node alias → node
        self.used: dict[tuple[str, str], set] | None = defaultdict(set) if rdm else None
        self._items: dict[tuple[str, str, str], set] | None = None   # (model, node, label) → items
        group_by_id, controlled = {}, {}
        for m in self.vocab.models.values():
            self.groups[m.name], self.group_of[m.name] = nodegroups(m.doc)
            self.nodes[m.name] = {n["alias"]: n for n in m.nodes if n.get("alias")}
            group_by_id[m.name] = {g["id"]: a for a, g in self.groups[m.name].items()}
            controlled[m.name] = {n["nodeid"]: n["alias"] for n in m.nodes
                                  if n.get("datatype") in CONTROLLED_TYPES}
        for r in read_resources(data_dir):
            m = self.vocab.by_graph.get((r.get("resourceinstance") or {}).get("graph_id"))
            if m is None:
                continue
            self.records[m.name] += 1
            for t in r.get("tiles") or []:
                self.tiles[(m.name, group_by_id[m.name].get(t.get("nodegroup_id")))] += 1
                if self.used is None:
                    continue
                for nid, value in (t.get("data") or {}).items():
                    alias = controlled[m.name].get(nid)
                    if alias is None:
                        continue
                    for v in value if isinstance(value, list) else [value]:
                        item = self.vocab.concept_of(v)
                        if item:
                            self.used[(m.name, alias)].add(item)
        self.kept: dict[str, set[str]] = {}
        for model, groups in self.groups.items():
            kept = set()
            for a in groups:
                if self.tiles[(model, a)]:
                    while a and a not in kept:
                        kept.add(a)
                        a = groups[a]["parent"]
            self.kept[model] = kept

    def _has_records(self, link: dict) -> bool:
        # a target that isn't one of these models leaves the link open to any, as relations() reads it
        targets = [self.vocab.by_graph[g["graphid"]].name
                   for g in (link.get("config") or {}).get("graphs") or []
                   if g.get("graphid") in self.vocab.by_graph]
        return not targets or any(self.records[t] for t in targets)

    def _value_used(self, model: str, q: dict) -> bool:
        if self._items is None:
            self._items = defaultdict(set)
            for v in self.vocab.values():
                for owner in v.owners:
                    self._items[(owner, v.field, v.label.lower())].add(v.value)
        items = self._items.get((model, q.get("node"), str(q.get("value")).lower()))
        if not items:
            return True                                    # not a value we can look up: keep
        used = self.used[(model, q.get("node"))]
        return any(i in used or used.intersection(self.vocab.descendants(i)) for i in items)

    def cut(self, model: str, entry: dict) -> str | None:
        """Why an entry goes ("group", "link", "value"), or None when it stays."""
        if self.group_of.get(model, {}).get(entry.get("node")) not in self.kept.get(model, ()):
            return "group"
        node = self.nodes[model].get(entry["node"]) or {}
        if node.get("datatype") in LINK_TYPES and not self._has_records(node):
            return "link"
        q = entry.get("qualifier")
        if q and self.used is not None and not self._value_used(model, q):
            return "value"
        return None

    def dropped_groups(self, model: str) -> list[str]:
        return sorted(set(self.groups.get(model, {})) - self.kept.get(model, set()))


def _entries(use: Usage, model: str, entries: list[dict], sliced: dict) -> list[dict]:
    kept = []
    for e in entries:
        why = use.cut(model, e)
        if why is None:
            kept.append(e)
        elif why == "link":
            sliced["links"].setdefault(model, []).append(e["node"])
        elif why == "value":
            q = e["qualifier"]
            sliced["values"].setdefault(model, []).append(f"{q['node']} = {q['value']}")
    return kept


def _group(use: Usage, model: str, block: dict, sliced: dict) -> dict:
    """A group block without the combos `use` cuts, each read as the entries it means."""
    combos = []
    for c in block.get("combos") or []:
        node = c.get("node") or next(iter(c["set"]))
        parts = [{"node": node, "qualifier": {"node": a, "value": v}} for a, v in c["set"].items()]
        if len(_entries(use, model, parts, sliced)) == len(parts):
            combos.append(c)
    return dict(block, combos=combos)


def _record(use: Usage, models: list[str]) -> dict:
    return {"models": [m for m in models if not use.records[m]],
            "groups": {m: use.dropped_groups(m) for m in models
                       if use.records[m] and use.dropped_groups(m)},
            "links": {}, "values": {}}


def slice_bundle(bundle: dict, use: Usage) -> dict:
    """The bundle cut down to `use`, with what was cut under "sliced"."""
    sliced = _record(use, list(bundle["models"]))
    models = {}
    for name, m in bundle["models"].items():
        if not use.records[name]:
            continue
        group_of = use.group_of[name]
        models[name] = dict(m, nodes={a: n for a, n in m["nodes"].items()
                                      if group_of.get(a) in use.kept[name]},
                        entries=_entries(use, name, m["entries"], sliced))
        if "groups" in m:
            models[name]["groups"] = {a: _group(use, name, b, sliced) for a, b in m["groups"].items()
                                      if a in use.kept[name]}
    built = dict(bundle.get("built") or {}, models=len(models),
                 entries=sum(len(m["entries"]) for m in models.values()),
                 phrasings=sum(len(e["phrases"]) for m in models.values() for e in m["entries"]))
    return dict(bundle, built=built, models=models, sliced=sliced)


def slice_vocab(vocab_dir: str | Path, out_dir: str | Path, use: Usage) -> dict:
    """A split vocabulary cut down to `use`, written to `out_dir`; what was cut
    (also recorded in its manifest)."""
    root, out = Path(vocab_dir), Path(out_dir)
    if not (root / MANIFEST).exists():
        raise ValueError(f"{root} is not a split vocabulary (run `ceist vocab split`), nor a bundle")
    manifest = json.loads((root / MANIFEST).read_text())
    models = sorted(p.name for p in root.iterdir() if p.is_dir())
    sliced = _record(use, models)
    for name in models:
        if not use.records[name]:
            continue
        for f in sorted((root / name).glob("*.json")):
            g = json.loads(f.read_text())
            kept = dict(g, entries=_entries(use, name, g["entries"], sliced))
            if g.get("group") and g["nodegroup"] in use.kept[name]:
                kept["group"] = _group(use, name, g["group"], sliced)
            else:
                kept.pop("group", None)
            if kept["entries"] or "group" in kept:
                (out / name).mkdir(parents=True, exist_ok=True)
                (out / name / f.name).write_text(
                    json.dumps(kept, indent=1, ensure_ascii=False) + "\n")
    out.mkdir(parents=True, exist_ok=True)
    (out / MANIFEST).write_text(json.dumps(dict(manifest, sliced=sliced), indent=1) + "\n")
    return sliced
