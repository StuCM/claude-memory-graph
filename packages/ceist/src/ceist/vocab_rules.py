"""The vocabulary checklist, and the rules that fill it without an LLM (`ceist vocab coverage`,
`ceist vocab generate`, `ceist vocab fill`).

Each element of the three layers has a list of items it should hold:

    ontology  class words for each CIDOC-CRM class the graphs use; the CRM label of each property
              into a link, and "who" + its inverse's label where the link points at an actor; a
              phrasing for each CRM path (no rule makes one: the LLM route does)
    base      per model its type words (plus the base graph's name, when the graph is renamed);
              per link its label, verb, noun and inverse forms; per date its label's forms
    client    per controlled value its plural and its alternative labels

An item is present, missing, or set aside with a recorded reason. The rules (CRM labels,
morphology, base graph names, label splitting) write the missing items they can derive as
candidates; a review drops any phrase that could name two elements, and the gate
(bench/ontology/gate.py) decides what merges. Nothing here reads a question set.
"""

import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from . import bundle as _bundle
from . import crm, ontology_vocab
from .text import PAST, terms_pos

IRREGULAR = {"person": "people", "child": "children", "man": "men", "woman": "women", "foot": "feet",
             "mouse": "mice", "goose": "geese", "datum": "data", "criterion": "criteria",
             "phenomenon": "phenomena", "medium": "media", "analysis": "analyses", "thesis": "theses"}
# ponytail: agent nouns by list, not by suffix ("mother", "actor" aren't agents of a verb); add as graphs need
AGENTS = {"holder": "hold", "owner": "own", "maker": "make", "builder": "build", "writer": "write",
          "designer": "design", "founder": "found", "creator": "create", "producer": "produce",
          "publisher": "publish", "recorder": "record", "compiler": "compile", "manager": "manage",
          "keeper": "keep", "leader": "lead", "painter": "paint", "carver": "carve", "surveyor": "survey",
          "excavator": "excavate", "donor": "donate", "lender": "lend", "funder": "fund", "editor": "edit",
          "commissioner": "commission", "illustrator": "illustrate", "photographer": "photograph",
          "translator": "translate", "collector": "collect", "investigator": "investigate",
          "assessor": "assess", "occupier": "occupy", "operator": "operate", "inventor": "invent",
          "engraver": "engrave", "printer": "print", "seller": "sell", "buyer": "buy", "user": "use"}
# a value's last word that marks it as no count noun: "listed", "neolithic", "bronze age"
NOT_COUNT = ("ed", "ic", "al", "ian", "ish", "ive", "ous", "ern", "ary", "ing")
NOT_COUNT_WORDS = {"age", "period", "era", "care", "uncertain", "unknown", "other", "none", "urban", "rural",
                   "heritage", "education", "health", "healthcare", "agriculture", "retail", "transport",
                   "finance", "construction", "manufacturing", "hospitality", "energy", "research"}
# ponytail: count nouns that end like an adjective, by list; add as sites need
COUNT_NOUNS = {"hospital", "animal", "canal", "festival", "memorial", "cathedral", "terminal", "arsenal",
               "tribunal", "portal", "building", "dwelling"}
# an event noun in a date's label → the verbs a question uses for it
EVENTS = {"death": ["died", "die"], "birth": ["born"], "construction": ["built", "constructed"],
          "production": ["made", "produced"], "creation": ["created"], "formation": ["formed"],
          "foundation": ["founded"], "dissolution": ["dissolved"], "destruction": ["destroyed"],
          "discovery": ["discovered"], "publication": ["published"], "excavation": ["excavated"],
          "demolition": ["demolished"], "acquisition": ["acquired"], "designation": ["designated"],
          "compilation": ["compiled"], "modification": ["modified"], "recording": ["recorded"],
          "survey": ["surveyed"], "update": ["updated"],
          "loss": ["lost"], "repair": ["repaired"], "restoration": ["restored"], "burial": ["buried"],
          "transformation": ["transformed"], "assessment": ["assessed"], "move": ["moved"],
          "measurement": ["measured"], "transfer": ["transferred"]}
AUX = ("is ", "was ", "were ", "are ")
LAYERS = ("ontology", "base", "client")
NO_INVERSE = ("a link's phrasings read both ways in Ceist, so an inverse phrasing would read backwards "
              "on the same link; only an actor's \"who …\" form is safe")
GATE = ontology_vocab.GATE
AUDIT = "audit metadata: a date about the record, which an event's words would read as the thing's own"


# ── morphology ───────────────────────────────────────────────────────────────
def plural(noun: str) -> str:
    """A noun phrase's plural: its last word's, with a small irregulars list."""
    words = noun.split()
    last = words[-1]
    if last in IRREGULAR:
        last = IRREGULAR[last]
    elif last.endswith("y") and len(last) > 2 and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    elif last.endswith(("s", "x", "ch", "sh", "z")):
        last += "es"
    else:
        last += "s"
    return " ".join(words[:-1] + [last])


def word_like(label: str) -> bool:
    """A label short and plain enough to be said as a word ("hospital", not "F — construction" or "CR/LFM")."""
    return not re.search(r"[^\w\s'-]|\d", label) and len(label.split()) <= 3


def count_noun(label: str) -> bool:
    """Whether a value's label can be counted ("hospital", not "listed", "heritage", "peri-urban")."""
    last = re.split(r"[\s-]+", label.lower().strip())[-1]
    return last in COUNT_NOUNS or not (last.endswith(NOT_COUNT) or last in NOT_COUNT_WORDS)


def noun_forms(label: str) -> list[str]:
    """A noun phrase and its plural."""
    low = label.lower().strip()
    return [low] if not low or low.endswith("s") else [low, plural(low)]


def head(label: str) -> str | None:
    """A multi-word label's last word ("Human-Made Object" → "object"): label splitting."""
    words = re.split(r"[\s-]+", label.lower().strip())
    return words[-1] if len(words) > 1 else None


def unaux(label: str) -> str:
    """A CRM label as a question says it: no leading auxiliary ("is possessed by" → "possessed by",
    "has former or current keeper" → "former or current keeper")."""
    low = label.lower().strip()
    for a in AUX + ("has ",):
        if low.startswith(a):
            return low[len(a):]
    return low


def sayable(label: str) -> str:
    """Why a CRM label can't be said in a question as it stands, or ""."""
    words = unaux(label).split()
    if len(words) > 4:
        return "a CRM label too long to be said in a question"
    return ""


def agent_verbs(label: str) -> list[str]:
    """An agent noun's verb forms: "copyright holder" → "holds copyright", "hold copyright",
    "copyright held by"; "owner" → "owns", "own", "owned by"."""
    words = label.lower().split()
    verb = AGENTS.get(words[-1]) if words and len(words) <= 3 else None
    if verb is None:
        return []
    obj = " ".join(words[:-1])
    if verb.endswith("y") and verb[-2] not in "aeiou":
        past, third = verb[:-1] + "ied", verb[:-1] + "ies"
    else:
        past = PAST.get(verb) or (verb + "d" if verb.endswith("e") else verb + "ed")
        third = verb + ("es" if verb.endswith(("s", "sh", "ch", "x")) else "s")
    return [f"{third} {obj}".strip(), f"{verb} {obj}".strip(), f"{obj} {past} by".strip()]


def of_forms(label: str) -> list[str]:
    """"part of" → "parts of": a noun before "of", made plural."""
    words = label.lower().split()
    if len(words) == 2 and words[1] == "of" and not words[0].endswith(("s", "ed", "en")) \
            and words[0] not in PAST.values():
        return [f"{plural(words[0])} of"]
    return []


def date_forms(label: str) -> tuple[list[str], list[str]]:
    """(the label's other order, the event's verbs): "date of death" → (["death date"], ["died", "die"])."""
    low = label.lower().strip()
    m = re.fullmatch(r"date of (.+)", low) or re.fullmatch(r"(.+?) date", low)
    if not m:
        return [], []
    event = m.group(1)
    if event.split()[-1] not in EVENTS:
        return [], []
    swap = f"{event} date" if low.startswith("date of") else f"date of {event}"
    return [swap], list(EVENTS.get(event) or EVENTS.get(event.split()[-1]) or [])


def composed(path: str, kind: str, defs: dict) -> list[str]:
    """A path's base meaning from its CRM labels, when it ends in an event EVENTS knows:
    "P108i E12 P4" → "made", "date of production", "production date"; "… E12 P14" → "made by";
    "… E12 P7" → "place of production"; "… E12 P2" → "production type"."""
    t = path.split()
    if len(t) < 3 or not defs.get(t[-2]):
        return []
    event = defs[t[-2]]["label"].lower().strip()
    verbs = EVENTS.get(event.split()[-1])
    if not verbs:
        return []
    if kind == "date" and t[-1] == "P4":
        return verbs[:1] + [f"date of {event}", f"{event} date"]
    if kind == "link" and t[-1] == "P14":
        return [f"{verbs[0]} by"]
    if kind == "link" and t[-1] == "P7":
        return [f"place of {event}"]
    if kind == "property" and t[-1] == "P2":
        return [f"{event} type", f"type of {event}"]
    return []


# ── the layers, read once ────────────────────────────────────────────────────
class Layers:
    """A graph set with its three layers: the bundle `layered` builds, and the vocabulary over it."""

    def __init__(self, graph_dirs, base_dir, client_dir=None, ontology_dir=None, reference=None):
        from .arches import graph_doc
        self.graph_dirs = [Path(d) for d in graph_dirs]
        self.graphs = [graph_doc(p) for d in self.graph_dirs for p in sorted(d.glob("*.json"))]
        self.base_dir = Path(base_dir)
        self.client_dir = Path(client_dir) if client_dir else None
        self.ontology_dir = Path(ontology_dir) if ontology_dir else self.base_dir.parent / "ontology" / "cidoc-crm"
        self.reference = Path(reference) if reference else None
        self.listed = ((_bundle._manifest(self.client_dir).get("models") or {}) if self.client_dir else {})
        self.defs = ontology_vocab.definitions(self.ontology_dir / "source")
        self._vocab = None

    def name(self, g: dict) -> str:
        n = g.get("name") or g["graphid"]
        return (n.get("en") or next(iter(n.values()))) if isinstance(n, dict) else n

    def base_id(self, g: dict) -> str:
        return (self.listed.get(self.name(g)) or {}).get("base") or g["graphid"]

    def vocab(self):
        if self._vocab is None:
            from .arches import ArchesVocabulary, load_reference_data
            bundle, _ = _bundle.layered(self.graphs, self.base_dir, self.client_dir, ontology_dir=self.ontology_dir)
            files = sorted(p for p in self.reference.rglob("*") if p.suffix in (".xml", ".json")) if self.reference else []
            rdm, alts = load_reference_data(files) if files else (None, {})
            self._vocab = ArchesVocabulary(self.graphs, rdm, alt_labels=alts, bundle=bundle)
            self.bundle = bundle
        return self._vocab


# ── the checklist ────────────────────────────────────────────────────────────
def _item(aspect: str, phrase: str | None, present: bool, reason: str = "") -> dict:
    out = {"aspect": aspect, "phrase": phrase, "status": "present" if present else "missing"}
    if reason and not present:
        out.update(status="set aside", reason=reason)
    return out


def _phrase_index(v) -> dict[str, set[tuple[str, str]]]:
    """{phrase: the (slot, element key) pairs it already names}. Slots: type words, link and date
    phrasings (scoped by their model, as grounding scopes them), values. A phrase in two slots is
    grounding's to order, so only a slot's own count."""
    out: dict[str, set] = {}
    for w, m in v.type_words().items():
        out.setdefault(w, set()).add(("type", f"type {m}"))
    for r in v.relations():
        owners = dict(r.form_owners)
        for f in r.forms:
            for m in owners.get(f, r.domain):
                out.setdefault(f, set()).add(("phrase", f"link {m}.{r.name.split('#')[0]}"))
    for d in v.date_fields():
        for f in d.forms:
            out.setdefault(f, set()).update(("phrase", f"date {m}.{d.field}") for m in d.owners)
    for x in v.values():
        out.setdefault(x.phrase, set()).update(("value", f"value {m}.{x.field}={x.label.lower()}") for m in x.owners)
    return out


def _slot(c: dict) -> str:
    return {"type": "type", "class": "type", "value": "value"}.get(c.get("kind") if c["layer"] != "client" else "value",
                                                                  "phrase")


def _scope(key: str) -> str:
    """The model an element key belongs to ("link Monument.actor" → "Monument"), "" for the ontology's."""
    rest = key.split(" ", 1)[1]
    return rest.split(".")[0] if " " in key and key.split()[0] in ("link", "date", "value") else (
        rest if key.startswith("type ") else "")


def _ontology_elements(L: Layers) -> list[dict]:
    ont = ontology_vocab.load(L.ontology_dir)
    proposed = ontology_vocab.read_proposed(L.ontology_dir)
    why_path = {f"{s['kind']} {s['path']}": "the LLM skipped it: " + s["skip"] for s in proposed.get("skipped", [])}
    why_path.update({f"{p['kind']} {p['path']}": "the gate " + p["gate"] for p in proposed.get("proposals", [])
                     if str(p.get("gate", "")).startswith("rejected")})
    classes, props, actor_range, paths, phrased = Counter(), Counter(), {}, Counter(), Counter()
    for g in L.graphs:
        chains = crm.chains(g)
        ranges = crm.link_ranges(g)
        edge_prop = {e["rangenode_id"]: e.get("ontologyproperty") for e in g.get("edges", [])}
        done = {e["node"] for e in crm.ontology_entries(g, ont)}
        for n in g["nodes"]:
            c = crm.crm_code(n.get("ontologyclass"))
            if c:
                classes[c] += 1
            alias, kind = n.get("alias"), _bundle.kind_of(n)
            if not alias or n["datatype"] == "semantic":
                continue
            if kind == "link":
                p = crm.crm_code(n.get("parentproperty") or edge_prop.get(n["nodeid"]))
                if p:
                    props[p] += 1
                    actor_range[p] = actor_range.get(p, False) or crm.is_a(ranges.get(alias, ""), "E39")
            if kind == "property" and not crm.is_controlled(n):
                continue
            path = ontology_vocab.path_of(chains[alias], kind)
            if path:
                paths[(path, kind)] += 1
                phrased[(path, kind)] += alias in done
    have: dict[str, set] = {}
    for e in ont["entries"]:
        have.setdefault(f"{e['kind']} {e['path']}", set()).update(e["phrases"])
    by_prop: dict[str, set] = {}
    for e in ont["entries"]:
        if e["kind"] == "link":
            by_prop.setdefault(e["path"].split()[-1], set()).update(e["phrases"])
    roots: dict[str, list[str]] = {}
    for g in L.graphs:
        roots.setdefault(crm.root_class(g), []).append(L.name(g))
    heads: dict[str, list[str]] = {}
    for c, d in L.defs.items():
        if c[0] in "ES" and head(d["label"]):
            heads.setdefault(head(d["label"]), []).append(c)
    out = []
    for c, n in classes.most_common():
        label = (L.defs.get(c) or {}).get("label")
        if not label:
            out.append({"layer": "ontology", "key": f"class {c}", "weight": n,
                        "items": [_item("class word", None, False, "outside CIDOC-CRM and CRMsci: no label")]})
            continue
        why = ("no model's root is this class: a class word names a model" if c not in roots else
               f"could name two models: {', '.join(roots[c])}" if len(roots[c]) > 1 else "")
        h = head(label)
        split = (f"label splitting: '{h}' ends {len(heads[h])} CRM class labels" if h and len(heads.get(h, ())) > 1
                 else why)
        items = [_item("class word", w, w in have.get(f"class {c}", ()), why) for w in noun_forms(label)]
        items += [_item("class word", w, w in have.get(f"class {c}", ()), split) for w in (noun_forms(h) if h else [])]
        out.append({"layer": "ontology", "key": f"class {c}", "weight": n, "label": label,
                    "target": {"layer": "ontology", "path": c, "kind": "class"}, "items": items})
    for p, n in props.most_common():
        label = (L.defs.get(p) or {}).get("label")
        inv = p[:-1] if p.endswith("i") else p + "i"
        if not label:
            out.append({"layer": "ontology", "key": f"property {p}", "weight": n,
                        "items": [_item("forward", None, False, "outside CIDOC-CRM and CRMsci: no label")]})
            continue
        items = [_item("forward", unaux(label), unaux(label) in by_prop.get(p, ()), sayable(label))]
        inv_label = (L.defs.get(inv) or {}).get("label") or ""
        verb = not re.match(r"(has|is|was) ", inv_label) and unaux(inv_label).split()[-1:] != ["for"]
        if actor_range.get(p) and inv_label and verb:
            w = "who " + unaux(inv_label)
            items.append(_item("inverse", w, w in by_prop.get(p, ()), sayable(inv_label)))
        else:
            items.append(_item("inverse", None, False, NO_INVERSE if not actor_range.get(p) else
                               "the inverse's CRM label is not a plain verb"))
        out.append({"layer": "ontology", "key": f"property {p}", "weight": n, "label": label,
                    "target": {"layer": "ontology", "path": p, "kind": "link"}, "items": items})
    known = set(L.defs)
    for (path, kind), n in paths.most_common():
        key = f"{kind} {path}"
        outside = any(t not in known for t in path.split() if t != "^")
        why = "outside CIDOC-CRM and CRMsci" if outside else why_path.get(key, "")
        items = [_item("phrasing", None, phrased[(path, kind)] > 0, why)]
        # a path the LLM skipped or the gate turned down can still take its CRM labels' meaning
        items += [_item("composed", p, p in have.get(key, ()), "outside CIDOC-CRM and CRMsci" if outside else "")
                  for p in composed(path, kind, L.defs)]
        out.append({"layer": "ontology", "key": f"path {key}", "weight": n,
                    "target": {"layer": "ontology", "path": path, "kind": kind}, "items": items})
    return out


def _base_elements(L: Layers) -> list[dict]:
    v = L.vocab()
    types = v.type_words()
    rel = {r.name: r for r in v.relations()}
    dates = {(d.field, m): d for d in v.date_fields() for m in d.owners}
    out = []
    for g in L.graphs:
        name, gid = L.name(g), L.base_id(g)
        base_name = _bundle._manifest(L.base_dir / gid).get("model") or name
        words = noun_forms(name) + (noun_forms(base_name) if base_name.lower() != name.lower() else [])
        out.append({"layer": "base", "key": f"type {name}", "weight": 1,
                    "target": {"layer": "base", "graphid": gid, "kind": "type", "model": name},
                    "items": [_item("type word", w, types.get(w) == name) for w in dict.fromkeys(words)]})
        _, group_of = _bundle.nodegroups(g)
        ranges = crm.link_ranges(g)
        for n in g["nodes"]:
            alias, kind = n.get("alias"), _bundle.kind_of(n)
            if not alias or kind == "property":
                continue
            label = str(n.get("name") or alias).lower()
            plain = {label, alias.replace("_", " ")}
            target = {"layer": "base", "graphid": gid, "nodegroup": group_of.get(alias, ""), "node": alias,
                      "kind": kind, "model": name}
            if kind == "link":
                r = rel.get(alias)
                forms = set(r.forms) if r and name in r.domain else set()
                more = bool(forms - plain)
                verbs = agent_verbs(label)
                is_verb = label.endswith((" by", " of", " to", " with", " in", " within"))
                items = [_item("label", label, label in forms)]
                items += ([_item("verb", p, p in forms) for p in verbs] if verbs else
                          [_item("verb", label if is_verb else None, is_verb or more)])
                nouns = of_forms(label)
                items += ([_item("noun", p, p in forms) for p in nouns] if nouns else
                          [_item("noun", label if not is_verb else None, not is_verb or more)])
                if crm.is_a(ranges.get(alias, ""), "E39") and verbs:
                    items.append(_item("inverse", f"who {verbs[0]}", f"who {verbs[0]}" in forms))
                else:
                    items.append(_item("inverse", None, False, NO_INVERSE if not crm.is_a(ranges.get(alias, ""), "E39")
                                       else ""))
            else:
                d = dates.get((alias, name))
                forms = set(d.forms) if d else set()
                swap, verbs = date_forms(label)
                # "created" on a record's audit date would read as when the thing itself was made
                audit = AUDIT if "audit" in group_of.get(alias, "") and "update" not in label else ""
                items = [_item("label", label, label in forms)]
                items += [_item("other order", p, p in forms, audit) for p in swap]
                items += ([_item("verb", p, p in forms, audit) for p in verbs] if verbs else
                          [_item("verb", None, bool(forms - plain - set(swap)))])
            out.append({"layer": "base", "key": f"{kind} {name}.{alias}", "weight": 1, "label": label,
                        "target": target, "items": items})
    return out


def _client_elements(L: Layers) -> list[dict]:
    if L.client_dir is None:
        return []
    v = L.vocab()
    said: dict[tuple, set] = {}
    for model, m in L.bundle["models"].items():
        for b in (m.get("groups") or {}).values():
            for c in b.get("combos") or []:
                if len(c["set"]) == 1 and not c.get("node"):
                    (a, label), = c["set"].items()
                    said.setdefault((model, a, str(label).lower()), set()).update(p.lower() for p in c["phrases"])
    values: dict[tuple, set] = {}
    for x in v.values():
        for m in x.owners:
            values.setdefault((m, x.field, x.label), set()).add(x.phrase)
    out = []
    for (m, alias, label), phrases in sorted(values.items()):
        low = label.lower()
        have = phrases | said.get((m, alias, low), set())
        items = [_item("alternative label", p, True) for p in sorted(phrases - {low})]
        if word_like(low) and not low.endswith("s"):
            items.append(_item("plural", plural(low), plural(low) in have,
                               "" if count_noun(low) else "not a count noun"))
        if items:
            group = v.group_of(m, alias)
            out.append({"layer": "client", "key": f"value {m}.{alias}={low}", "weight": 1, "label": label,
                        "target": {"layer": "client", "model": m, "nodegroup": group, "node": alias, "value": label},
                        "items": items})
    return out


def checklist(L: Layers, reasons: dict | None = None) -> list[dict]:
    """Every element of the three layers with its items, each present, missing or set aside;
    `reasons` ({element key: {phrase: why}}, from a generate run) sets aside what review or the gate turned down."""
    out = _ontology_elements(L) + _base_elements(L) + _client_elements(L)
    for e in out:
        for it in e["items"]:
            why = (reasons or {}).get(e["key"], {}).get(it["phrase"] or "")
            if why and it["status"] == "missing":
                it.update(status="set aside", reason=why)
    return out


def summary(elements: list[dict]) -> dict:
    """{layer: {"items", "present", "set aside", "missing", "percent", "explained"}}, weighted by
    each element's weight (CRM node counts for the ontology, 1 elsewhere), plus "overall" unweighted."""
    out = {}
    for layer in LAYERS + ("overall",):
        n = Counter()
        for e in elements:
            if layer not in (e["layer"], "overall"):
                continue
            w = e["weight"] if layer != "overall" else 1
            for it in e["items"]:
                n["items"] += 1
                n["weight"] += w
                n[it["status"]] += w
        if n["items"]:
            out[layer] = {"items": n["items"], "present": n["present"], "set aside": n["set aside"],
                          "missing": n["missing"], "percent": round(100 * n["present"] / n["weight"], 1),
                          "explained": round(100 * (n["present"] + n["set aside"]) / n["weight"], 1)}
    return out


def report_md(elements: list[dict], title: str, limit: int = 40) -> str:
    s = summary(elements)
    lines = [f"# Vocabulary coverage: {title}", "",
             "Present: the vocabulary holds the item. Set aside: it doesn't, with a recorded reason. "
             "Explained = present + set aside. The ontology is weighted by CRM node counts; overall counts items.", "",
             "| layer | items | present % | explained % |", "| --- | --- | --- | --- |"]
    lines += [f"| {k} | {x['items']} | {x['percent']} | {x['explained']} |" for k, x in s.items()]
    for layer in LAYERS:
        mine = [e for e in elements if e["layer"] == layer]
        if not mine:
            continue
        aspects = Counter((e["key"].split()[0], it["aspect"], it["status"]) for e in mine for it in e["items"])
        lines += ["", f"## {layer}", "", "| element | item | present | set aside | missing |", "| --- " * 5 + "|"]
        for kind, aspect in dict.fromkeys((k, a) for k, a, _ in sorted(aspects)):
            lines.append(f"| {kind} | {aspect} | " + " | ".join(str(aspects[(kind, aspect, st)])
                                                                 for st in ("present", "set aside", "missing")) + " |")
        missing = [(e, it) for e in sorted(mine, key=lambda e: -e["weight"]) for it in e["items"]
                   if it["status"] == "missing"]
        if missing:
            lines += ["", f"Missing ({len(missing)}, heaviest first; the first {min(limit, len(missing))}):", ""]
            lines += [f"- {e['key']} ({e['weight']}): {it['aspect']}" + (f" '{it['phrase']}'" if it["phrase"] else "")
                      for e, it in missing[:limit]]
        aside = Counter(it["reason"].split(":")[0] for e in mine for it in e["items"] if it["status"] == "set aside")
        if aside:
            lines += ["", "Set aside, by reason:", ""] + [f"- {n}: {r}" for r, n in aside.most_common()]
    return "\n".join(lines) + "\n"


def where(L: Layers) -> dict[str, Counter]:
    """{model: {"ontology": n, "own": n}}: the phrasings the layered bundle gives each graph from the
    ontology layer (its paths' base meaning) and from its own base and client layers (the delta)."""
    L.vocab()
    out = {}
    for model, m in L.bundle["models"].items():
        n = Counter()
        for e in m["entries"]:
            n["ontology" if e.get("layer") == "ontology" else "own"] += len(e["phrases"])
        for b in m["groups"].values():
            n["own"] += len(b.get("phrases") or []) + sum(len(c["phrases"]) for c in b.get("combos") or [])
        out[model] = n
    return out


def where_md(L: Layers, ledger_path: Path | None) -> str:
    """Where the phrasings live: per graph, base meaning (ontology) against delta (own layers); and,
    from a `vocab crm-first` ledger, per layer, why each phrasing left in a graph or client layer is there."""
    from .crm_first import CLASSES
    lines = ["", "## Where the phrasings live", "",
             "Per graph: phrasings the bundle takes from the ontology layer (the CRM path's base meaning) "
             "and from the graph's own base and client layers (the delta its node names add).", "",
             "| graph | ontology | own | ontology % |", "| --- | --- | --- | --- |"]
    for model, n in sorted(where(L).items()):
        total = n["ontology"] + n["own"]
        lines.append(f"| {model} | {n['ontology']} | {n['own']} | {round(100 * n['ontology'] / total, 1) if total else 0} |")
    if ledger_path and ledger_path.exists():
        doc = json.loads(ledger_path.read_text())
        lines += ["", f"Every base and client phrasing, by where `vocab crm-first` left it ({ledger_path.name}):", "",
                  "| layer | " + " | ".join(CLASSES) + " |", "| --- " * (len(CLASSES) + 1) + "|"]
        lines += [f"| {layer} | " + " | ".join(str(n.get(c, 0)) for c in CLASSES) + " |"
                  for layer, n in doc["summary"].items()]
    return "\n".join(lines) + "\n"


def write_report(elements: list[dict], out: Path, name: str, title: str, tail: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.md").write_text(report_md(elements, title) + tail)
    (out / f"{name}.json").write_text(json.dumps({"summary": summary(elements), "elements": elements},
                                                 ensure_ascii=False, indent=1) + "\n")


def read_reasons(path: Path) -> dict:
    return json.loads(path.read_text()).get("reasons", {}) if path.exists() else {}


# ── the generators: what the checklist misses and a rule can say ─────────────
def candidates(elements: list[dict]) -> list[dict]:
    """One candidate per element: its missing items that have a phrase."""
    out = []
    for e in elements:
        phrases = [it["phrase"] for it in e["items"] if it["status"] == "missing" and it["phrase"]]
        if phrases and e.get("target"):
            out.append(dict(e["target"], key=e["key"], phrases=list(dict.fromkeys(phrases)),
                            rule=sorted({it["aspect"] for it in e["items"] if it["phrase"] in phrases})))
    return out


def review(cands: list[dict], v, generic: set[str]) -> dict[str, dict[str, str]]:
    """{element key: {phrase: why dropped}}: generic, no content word, or a phrase that could
    name two elements of one slot (already said of another, or proposed for two). CRM-first: a
    phrase proposed both for a base node and for an ontology path that reaches it is the path's."""
    index = _phrase_index(v)
    by_key = {c["key"]: c for c in cands}

    keys: dict[str, dict] = {}

    def carries(o: dict, c: dict) -> bool:
        if o["layer"] != "ontology" or c["layer"] != "base" or not c.get("node") or c["model"] not in v.models:
            return False
        if c["model"] not in keys:
            keys[c["model"]] = crm.keyed(v.models[c["model"]].doc)
        kind, tokens = keys[c["model"]].get(c["node"], (None, []))
        return kind == o["kind"] and crm._ends_with(tokens, o["path"].split())

    def said_of(key: str) -> dict:
        """An index key ("date Monument.built") as the base element it names."""
        kind, _, rest = key.partition(" ")
        model, _, node = rest.partition(".")
        return {"layer": "base", "kind": kind, "model": model, "node": node}
    roots = {}
    for name, (root, _) in v._crm.items():
        roots.setdefault(root, []).append(name)

    def near(c: dict, key: str) -> bool:
        """Two elements compete when a question could reach both: within one model, anywhere for a
        type word or an ontology phrasing, which reaches every graph; a class word names its root model."""
        if c.get("kind") == "class":
            return key not in {f"type {m}" for m in roots.get(c["path"], [])}
        if key.startswith("class "):
            return c.get("model") not in roots.get(key.split()[1], [])
        return c["layer"] == "ontology" or _slot(c) == "type" or _scope(key) in ("", _scope(c["key"]))

    proposed: dict[tuple, set] = {}
    for c in cands:
        for p in c["phrases"]:
            proposed.setdefault((p, _slot(c)), set()).add(c["key"])
    dropped: dict[str, dict[str, str]] = {}
    for c in cands:
        mine = dropped.setdefault(c["key"], {})
        for p in c["phrases"]:
            others = sorted(k for s_, k in index.get(p, ()) if s_ == _slot(c) and k != c["key"] and near(c, k)
                            and not carries(c, said_of(k)))
            twice = sorted(k for k in proposed[(p, _slot(c))] - {c["key"]} if near(c, k)
                           and not carries(c, by_key[k]))
            path = next((k for k in twice if carries(by_key[k], c)), None)
            if path:
                mine[p] = f"CRM-first: {path} carries it"
            elif p in generic:
                mine[p] = "too generic"
            elif not terms_pos(p):
                mine[p] = "no content word"
            elif others:
                mine[p] = f"could name two elements: already {', '.join(others[:3])}"
            elif twice:
                mine[p] = f"could name two elements: also proposed for {', '.join(twice[:3])}"
    return {k: d for k, d in dropped.items() if d}


def gate_key(c: dict) -> str:
    """How the gate names a candidate (ontology ones as gate.py always has)."""
    if c["layer"] == "ontology":
        return f"{c['kind']} {c['path']}"
    return c["key"]


def apply(cands: list[dict], ontology_dir: Path, base_dir: Path, client_dir: Path | None) -> None:
    """Write candidates into their layers: ontology entries into phrases.json, type words into
    the base graph's manifest, link and date phrasings into its nodegroup file, value
    variants into the client's group block as one-value combos."""
    onto = [c for c in cands if c["layer"] == "ontology"]
    if onto:
        ontology_vocab.write_phrases(ontology_dir, ontology_vocab.merge(ontology_vocab.load(ontology_dir), onto))
    for c in cands:
        if c["layer"] == "base" and c["kind"] == "type":
            path = Path(base_dir) / c["graphid"] / _bundle.MANIFEST
            doc = json.loads(path.read_text()) if path.exists() else {"format": _bundle.LAYOUT, "model": c["model"]}
            doc["type_words"] = list(dict.fromkeys((doc.get("type_words") or []) + c["phrases"]))
            _dump(path, doc)
        elif c["layer"] == "base":
            path = Path(base_dir) / c["graphid"] / f"{c['nodegroup']}.json"
            doc = json.loads(path.read_text()) if path.exists() else {
                "model": c["model"], "nodegroup": c["nodegroup"], "entries": []}
            e = next((e for e in doc["entries"] if e["node"] == c["node"] and not e.get("qualifier")), None)
            if e is None:
                doc["entries"].append({"phrases": list(c["phrases"]), "kind": c["kind"], "node": c["node"]})
            else:
                e["phrases"] = list(dict.fromkeys(e["phrases"] + c["phrases"]))
            _dump(path, doc)
        elif c["layer"] == "client" and client_dir is not None:
            if not (Path(client_dir) / _bundle.MANIFEST).exists():
                _dump(Path(client_dir) / _bundle.MANIFEST, {"format": _bundle.LAYOUT, "models": {}})
            path = Path(client_dir) / c["model"] / f"{c['nodegroup']}.json"
            doc = json.loads(path.read_text()) if path.exists() else {
                "model": c["model"], "nodegroup": c["nodegroup"], "entries": []}
            block = doc.setdefault("group", {"phrases": [], "nodes": {}, "combos": []})
            combos = block.setdefault("combos", [])
            same = next((x for x in combos if x["set"] == {c["node"]: c["value"]} and not x.get("node")), None)
            if same is None:
                combos.append({"phrases": list(c["phrases"]), "set": {c["node"]: c["value"]}})
            else:
                same["phrases"] = list(dict.fromkeys(same["phrases"] + c["phrases"]))
            _dump(path, doc)


def _dump(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def run_gate(cands: list[dict], L: Layers, skip=(), gate_cmd: list[str] | None = None) -> dict | None:
    """The candidates through bench/ontology/gate.py; its verdict, or None if it failed."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "candidates.json"
        path.write_text(json.dumps(cands, ensure_ascii=False))
        cmd = (gate_cmd or [sys.executable, str(GATE)]) + [str(path), "--ontology", str(L.ontology_dir),
                                                         "--base", str(L.base_dir)]
        if L.client_dir:
            cmd += ["--client", str(L.client_dir)]
        cmd += [a for s in skip for a in (f"--{s}", "skip")]
        res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        print(f"the gate failed (exit {res.returncode})\n{res.stderr[-2000:]}", file=sys.stderr)
        return None
    return json.loads(res.stdout.strip().splitlines()[-1])


def generate(L: Layers, out: Path, name: str, review_only: bool = False, skip=(),
             gate_cmd: list[str] | None = None, extra: list[dict] | None = None, log=print) -> int:
    """checklist → rule candidates (plus `extra`, the LLM fill's) → review → gate → the layers;
    out/rules-<name>.md lists what was accepted and what was not, and why, and
    out/rules-<name>.json keeps the reasons for the coverage report."""
    out = Path(out)
    elements = checklist(L, read_reasons(out / f"rules-{name}.json"))
    cands = candidates(elements) + list(extra or [])
    generic = set(json.loads((L.ontology_dir / ontology_vocab.GENERIC).read_text())["phrases"])
    dropped = review(cands, L.vocab(), generic)
    for c in cands:
        c["phrases"] = [p for p in c["phrases"] if p not in dropped.get(c["key"], {})]
    todo = [c for c in cands if c["phrases"]]
    log(f"{len(cands)} candidates, {sum(len(d) for d in dropped.values())} phrases dropped by review; "
        f"{len(todo)} to the gate")
    reasons = {k: {p: "review: " + why for p, why in d.items()} for k, d in dropped.items()}
    accepted, verdict = [], {}
    if todo and not review_only:
        verdict = run_gate(todo, L, skip, gate_cmd)
        if verdict is None:
            return 1
        passed = set(verdict["accepted"])
        accepted = [c for c in todo if gate_key(c) in passed]
        for c in todo:
            if gate_key(c) not in passed:
                why = "gate: " + verdict["rejected"].get(gate_key(c), "?")
                reasons.setdefault(c["key"], {}).update({p: why for p in c["phrases"]})
        apply(accepted, L.ontology_dir, L.base_dir, L.client_dir)
    old = read_reasons(out / f"rules-{name}.json")
    for k, d in reasons.items():
        old.setdefault(k, {}).update(d)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"rules-{name}.json").write_text(json.dumps(
        {"format": "ceist.vocab-rules/1", "graphs": [str(d) for d in L.graph_dirs], "reasons": old,
         "accepted": [{k: c[k] for k in ("key", "layer", "phrases", "rule")} for c in accepted]},
        ensure_ascii=False, indent=1) + "\n")
    (out / f"rules-{name}.md").write_text(_build_report(name, L, cands, dropped, todo, accepted, verdict, review_only))
    log(f"{len(accepted)} of {len(todo)} accepted → {out / f'rules-{name}.md'}")
    return 0


def _build_report(name, L, cands, dropped, todo, accepted, verdict, review_only) -> str:
    lines = [f"# Rule-based vocabulary build: {name}", "",
             f"Graphs: {', '.join(str(d) for d in L.graph_dirs)}. No LLM.", "",
             f"{len(cands)} elements with a missing item a rule can phrase; review dropped "
             f"{sum(len(d) for d in dropped.values())} phrases; {len(todo)} went to the gate; "
             f"{'the gate was not run (review only)' if review_only else f'{len(accepted)} accepted'}.", "",
             "## Accepted", "", "| layer | element | rule | phrases |", "| --- " * 4 + "|"]
    lines += [f"| {c['layer']} | {c['key']} | {', '.join(c['rule'])} | {', '.join(c['phrases'])} |" for c in accepted]
    passed = {gate_key(c) for c in accepted}
    lines += ["", "## Rejected by the gate", "", "| layer | element | phrases | why |", "| --- " * 4 + "|"]
    lines += [f"| {c['layer']} | {c['key']} | {', '.join(c['phrases'])} | "
              f"{(verdict.get('rejected') or {}).get(gate_key(c), 'not gated')} |"
              for c in todo if gate_key(c) not in passed and not review_only]
    lines += ["", "## Dropped by review", "", "| element | phrase | why |", "| --- " * 3 + "|"]
    lines += [f"| {k} | {p} | {why} |" for k, d in sorted(dropped.items()) for p, why in d.items()]
    if verdict:
        lines += ["", "## Gate checks", ""] + [f"- {c}" for c in verdict.get("checks", [])]
        lines += ["", "Bench counts: right / wrong reading / refused / right refusal / wrong.", ""]
        lines += ontology_vocab._tally_rows(verdict)
        demo = verdict.get("demo") or {}
        lines += ["", f"Demo bank before: {demo.get('before', 'not run')}", "",
                  f"Demo bank after: {demo.get('after', 'not run')}"]
    return "\n".join(lines) + "\n"


# ── the directed LLM fill: only what the checklist still misses ───────────────
FILL_BATCH = 20
FILL_VERSION = "1"
FILL_PROMPT = """You fill gaps in the vocabulary of an offline, no-LLM natural-language search over \
cultural-heritage records (Arches). Each element below is a part of a resource model (a link to \
another record, a date, a type of record) or a CIDOC-CRM class, with its label and the kinds of \
phrasing it still lacks:
- "verb": a verb phrase a question uses for the link or date ("built by", "holds copyright", "died");
- "noun": a noun people use for it ("builder", "date of death");
- "inverse": for a link to a person or organisation, "who <verb>" read from the other end ("who owns");
- "class word" / "type word": the everyday noun for that kind of record, singular and plural.

For each element give either "phrases": 1 to 4 short lowercase phrasings of the kinds it lacks, \
fitting "which monuments were <p> X?", "when was X <p>?" or "how many <p> are there?" (no question \
words other than a leading "who", no names), or "skip": why nobody asks about it.

ELEMENTS:
{elements}

Reply with JSON only:
{{"elements": [{{"key": "<as given>", "phrases": ["..."]}} | {{"key": "<as given>", "skip": "..."}}]}}
"""


def fill_gaps(elements: list[dict]) -> list[dict]:
    """The base and client elements with a missing item no rule could phrase."""
    return [e for e in elements if e["layer"] != "ontology" and e.get("target")
            and any(it["status"] == "missing" and not it["phrase"] for it in e["items"])]


def _fill_check(reply, batch: list[dict]) -> list[str]:
    if not isinstance(reply, dict) or not isinstance(reply.get("elements"), list):
        return ['the reply must be {"elements": [...]}']
    want = {e["key"] for e in batch}
    errors = []
    for x in reply["elements"]:
        k = x.get("key") if isinstance(x, dict) else None
        if k not in want:
            errors.append(f"unknown element {k!r}")
        elif "skip" not in x and not (isinstance(x.get("phrases"), list) and x["phrases"]
                                      and all(isinstance(p, str) and 0 < len(p.split()) <= 5 for p in x["phrases"])):
            errors.append(f"{k}: phrases must be 1 to 4 short strings, or give skip")
    return errors


def fill(L: Layers, out: Path, name: str, llm_cmd: str | None = None, model: str | None = None,
         max_calls: int = ontology_vocab.MAX_CALLS, estimate: bool = False, skip=(),
         gate_cmd: list[str] | None = None, log=print) -> int:
    """The gaps the checklist still lists after the rules, and only those: CRM paths through
    `vocab ontology build`, base and client elements through FILL_PROMPT, then generate's
    review and gate. Prints the estimate and stops with `estimate`, or over `max_calls`."""
    from . import cost, prices
    from .pipeline import Runner, _key
    out = Path(out)
    elements = checklist(L, read_reasons(out / f"rules-{name}.json"))
    gaps = fill_gaps(elements)
    paths = sum(1 for e in elements if e["key"].startswith("path ")
                and any(it["status"] == "missing" for it in e["items"]))
    batches = [gaps[i:i + FILL_BATCH] for i in range(0, len(gaps), FILL_BATCH)]
    texts = [FILL_PROMPT.format(elements=json.dumps([_ask(e) for e in b], ensure_ascii=False, indent=1))
             for b in batches]
    dollars = sum(prices.cost({"input_tokens": cost.by_chars(t), "output_tokens": cost.DEFAULT_OUTPUT},
                              model or "opus") for t in texts)
    log(f"{len(gaps)} base and client elements in {len(batches)} calls, about ${dollars:.2f}; "
        f"{paths} CRM paths go to `vocab ontology build`, which prints its own estimate (--max-calls {max_calls})")
    if estimate or len(batches) > max_calls:
        if not estimate:
            log(f"over --max-calls {max_calls}: nothing sent")
        return 0 if estimate else 2
    if paths:
        rc = ontology_vocab.build(L.graph_dirs, L.ontology_dir, out / "ontology", llm_cmd, model, max_calls,
                                  skip=skip, gate_cmd=gate_cmd, log=log)
        if rc:
            return rc
    run = Runner(out / "llm", llm_cmd, model)
    extra, reasons = [], {}
    for batch, text in zip(batches, texts):
        reply = run.ask(_key("fill", FILL_VERSION, text), text, lambda r, b=batch: _fill_check(r, b),
                        {"kind": "fill", "elements": len(batch)})
        by_key = {e["key"]: e for e in batch}
        for x in (reply or {}).get("elements", []):
            e = by_key[x["key"]]
            if "skip" in x:
                reasons.setdefault(e["key"], {})[""] = "the LLM skipped it: " + x["skip"]
                continue
            extra.append(dict(e["target"], key=e["key"], phrases=[p.strip().lower() for p in x["phrases"]],
                              rule=["llm"]))
    if reasons:
        path = out / f"rules-{name}.json"
        doc = json.loads(path.read_text()) if path.exists() else {"format": "ceist.vocab-rules/1", "reasons": {}}
        for k, d in reasons.items():
            doc["reasons"].setdefault(k, {}).update(d)
        out.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    log(f"LLM calls {run.calls}; {len(extra)} elements phrased, {len(reasons)} skipped; {len(run.failures)} failed")
    return generate(L, out, name, skip=skip, gate_cmd=gate_cmd, extra=extra, log=log) or (1 if run.failures else 0)


def _ask(e: dict) -> dict:
    """What the prompt says of an element: schema only, never a record."""
    return {"key": e["key"], "label": e.get("label", ""),
            "lacks": sorted({it["aspect"] for it in e["items"] if it["status"] == "missing" and not it["phrase"]}),
            "has": [it["phrase"] for it in e["items"] if it["status"] == "present" and it["phrase"]]}
