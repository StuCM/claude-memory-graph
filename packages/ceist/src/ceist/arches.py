"""The vocabulary of Arches resource models — for Rós Madair and Arches Search.

Built from the data folder Alizarin and Rós Madair share, read through
Alizarin (graph shape, datatypes, node configs, reference data):

    <data_dir>/graphs/*.json             resource models (Arches graph exports)
    <data_dir>/resources/**/*.json       business data (for the names questions use)
    <data_dir>/vocabularies/*.xml        controlled lists and thesauri, as SKOS (optional)
    <data_dir>/vocabularies/*.json       the same as Arches/Alizarin collection JSON (optional)

What a question can name, from that:

- **types**: each resource model, by its name ("Building" → "buildings");
- **relations**: each resource-instance node, by its name and alias ("Site",
  "operator"), from its model to the models its config allows;
- **controlled values**: every item of the list a node draws from, by
  preferred and alternative label ("listed" → Heritage status = Listed).
  Controlled lists (`reference` nodes, `config.controlledList`) are the
  primary kind; concept nodes (`concept`, `concept-list`,
  `config.rdmCollection`) are legacy and read the same way. Item ids come
  from Alizarin's RDM cache, so they are exactly the ids Rós Madair interned
  — the planner never re-derives them. Alternative labels are read from the
  SKOS itself (Alizarin's SKOS reader keeps only preferred labels), matched
  to Alizarin's items by URI;
- **a vocabulary bundle** (`bundle=`, built by `ceist vocab assemble`):
  its link and date phrasings join the forms below;
- **dates**: each date node, by its name, and by the words `date_forms`
  adds ("built" → construction date); a model's only date node is the one
  meant when no word picks;
- **records**: resource names, for anchors ("Leeds Dock").

Alizarin (`pip install alizarin`) is required.
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import alizarin

from .index import NameIndex
from .text import plurals
from .vocabulary import DateField, Entity, Relation, Value

LINK_TYPES = {"resource-instance", "resource-instance-list"}
REFERENCE_TYPES = {"reference"}                  # controlled lists: the primary kind
CONCEPT_TYPES = {"concept", "concept-list"}      # SKOS concepts: legacy
CONTROLLED_TYPES = REFERENCE_TYPES | CONCEPT_TYPES
DATE_TYPES = {"date", "edtf"}     # HER keeps event dates (construction, loss) as EDTF
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_SKOS = "{http://www.w3.org/2004/02/skos/core#}"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_BASE_URI = "http://example.org/"


def collection_of(node: dict) -> str | None:
    """The list a controlled node draws from: `controlledList` (reference
    nodes) or `rdmCollection` (concept nodes) — Alizarin's rule."""
    cfg = node.get("config") or {}
    return cfg.get("controlledList") or cfg.get("rdmCollection") or None


def alt_labels(skos_xml: str, language: str) -> dict[str, list[str]]:
    """{concept URI: [altLabel, ...]} in one language. Arches exports may
    write a label as JSON ({"id", "value"}); both forms are read."""
    out: dict[str, list[str]] = {}
    for el in ET.fromstring(skos_xml.encode()).iter(f"{_SKOS}Concept"):
        uri = el.get(f"{_RDF}about")
        for alt in el.iter(f"{_SKOS}altLabel"):
            lang = alt.get(_XML_LANG) or ""
            if uri and (lang == language or lang.split("-")[0] == language) and alt.text:
                text = alt.text.strip()
                if text.startswith("{"):
                    try:
                        text = json.loads(text).get("value", text)
                    except ValueError:
                        pass
                out.setdefault(uri, []).append(text)
    return out


def load_reference_data(paths, language: str = "en"):
    """(RustRdmCache, {URI: alt labels}) from SKOS XML and collection JSON
    files. Collection JSON (Arches `reference_data/collections/*.json`, or
    Alizarin's simplified form) goes through Alizarin's global cache, the
    reader that keeps its hierarchy, then into this cache."""
    rdm, alts = alizarin.RustRdmCache(), {}
    for p in paths:
        p = Path(p)
        text = p.read_text()
        if p.suffix == ".xml":
            rdm.add_from_skos_xml(text, _BASE_URI)
            alts.update(alt_labels(text, language))
        elif p.suffix == ".json":
            shared = alizarin.get_global_rdm_cache() if alizarin.has_global_rdm_cache() else None
            for cid in alizarin.add_from_skos_json_to_global_cache(text):
                shared = shared or alizarin.get_global_rdm_cache()
                rdm.add_collection(shared.get_collection(cid))
    return rdm, alts


def read_resources(business_data_dir: str | Path) -> list[dict]:
    """Every resource in an Arches business data export (business_data.resources)."""
    out = []
    for p in sorted(Path(business_data_dir).rglob("*.json")):
        doc = json.loads(p.read_text())
        out += (doc.get("business_data") or {}).get("resources", [])
    return out


@dataclass
class Model:
    graph_id: str
    name: str
    slug: str
    nodes: list[dict] = field(default_factory=list)
    doc: dict = field(default_factory=dict, repr=False)   # the graph JSON itself
    wrapper: object = field(default=None, repr=False)     # Alizarin's ResourceModelWrapper
    nodegroups: dict = field(default_factory=dict, repr=False)   # id → {cardinality, parent}
    schema: dict = field(default_factory=dict, repr=False)       # alias tree (get_graph_schema)


def slug_of(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _graph_doc(path: Path) -> dict:
    doc = json.loads(path.read_text())
    if isinstance(doc, dict) and isinstance(doc.get("graph"), list):
        return doc["graph"][0]
    return doc


def _model(g: dict, language: str) -> Model:
    """A graph registered with Alizarin and read through its model wrapper."""
    gid = alizarin.register_graph(json.dumps(g)) or g["graphid"]
    wrapper = alizarin.load_model(gid)
    name = g.get("name") or g.get("slug") or gid
    if isinstance(name, dict):                  # localized name
        name = name.get(language) or next(iter(name.values()))
    nodes = [n.to_dict() for n in wrapper.get_node_objects().values()]
    groups = {k: {"cardinality": v.cardinality, "parent": v.parentnodegroup_id}
              for k, v in wrapper.get_nodegroup_objects().items()}
    return Model(gid, name, g.get("slug") or slug_of(name), nodes, g, wrapper, groups,
                 alizarin.get_graph_schema(gid))


class ArchesVocabulary:
    def __init__(self, graphs: list[dict], rdm_cache=None, resources: list[dict] = (),
                 language: str = "en", extra_type_words: dict[str, str] | None = None,
                 alt_labels: dict[str, list[str]] | None = None,
                 relation_forms: dict[str, list[str]] | None = None,
                 date_forms: dict[str, list[str]] | None = None,
                 bundle: str | Path | dict | None = None):
        self.language = language
        self.alt_labels = alt_labels or {}       # item URI → alternative labels
        self.models = {}
        for g in graphs:
            m = _model(g, language)
            self.models[m.name] = m
        self.by_graph = {m.graph_id: m for m in self.models.values()}
        self.rdm = rdm_cache
        self.extra_type_words = extra_type_words or {}
        # extra phrasings per node alias: {"architect": ["designed by"]}
        self.relation_forms = relation_forms or {}
        # words that pick a date node: {"construction_date": ["built", "constructed"]}
        self.date_forms = date_forms or {}
        # a bundle's phrasings, per (model, alias): HER reuses aliases such as
        # start_date and actor across models, each with its own meaning
        self._bundle_forms: dict[tuple[str, str], list[str]] = {}
        self._pending_qualified: list[tuple[str, dict]] = []
        self._qualified: list[Relation] | None = None
        self.skipped: list[str] = []             # bundle entries not used, and why
        self.notes: list[str] = []               # what loading found worth saying
        if bundle is not None:
            self._absorb(bundle)
        self._narrower: dict[str, list[str]] = {}
        self._concept_of: dict[str, str] = {}    # label value id / item URI → item id
        self._labels: dict[str, str] = {}        # item id → label
        self._items: dict[str, dict] = {}        # item id → {collection, uri, labels}
        self.resources = list(resources)
        entities, unnamed = [], {}
        for r in resources:
            e = self._entity(r)
            if e is None:
                continue
            if e.name == e.id:
                unnamed[e.type] = unnamed.get(e.type, 0) + 1
            entities.append(e)
        for t, n in sorted(unnamed.items()):
            self.notes.append(f"{n} {t} record(s) have no name (no descriptors, no "
                              "resourceinstance.name): they can't be found by name")
        self._index = NameIndex(entities)
        self.names = {e.id: e.name for e in self._index.entities}

    @property
    def skipped_qualified(self) -> int:
        if self._qualified is None:
            self.relations()
        return len(self.skipped)

    # ── loading ───────────────────────────────────────────────────────────
    @classmethod
    def from_data_dir(cls, data_dir: str | Path, language: str = "en", **kw) -> "ArchesVocabulary":
        root = Path(data_dir)
        graphs = [_graph_doc(p) for p in sorted((root / "graphs").glob("*.json"))]
        resources = read_resources(root / "resources")
        vocab_dir = root / "vocabularies"
        files = (sorted(vocab_dir.glob("*.xml")) + sorted(vocab_dir.glob("*.json"))
                 if vocab_dir.is_dir() else [])
        rdm, alts = load_reference_data(files, language) if files else (None, {})
        return cls(graphs, rdm, resources, language, alt_labels=alts, **kw)

    def _absorb(self, bundle) -> None:
        """A vocabulary bundle's phrasings (ceist.bundle): unqualified link
        entries become relation phrasings, date entries date phrasings.
        Entries that carry a qualifier ("designed by" → actor + role
        Architect) become qualified relations (relations()); one that can't
        is listed in `skipped`, with the reason."""
        from . import bundle as _bundle
        b = bundle if isinstance(bundle, dict) else _bundle.load(bundle)
        for name, m in b["models"].items():
            if name not in self.models:
                continue
            for e in m["entries"]:
                if e.get("qualifier"):
                    self._pending_qualified.append((name, e))
                    continue
                kind = (m["nodes"].get(e["node"]) or {}).get("kind")
                if kind in ("link", "date"):
                    key = (name, e["node"])
                    self._bundle_forms[key] = list(dict.fromkeys(
                        self._bundle_forms.get(key, []) + e["phrases"]))

    def _entity(self, r: dict) -> Entity | None:
        ri = r.get("resourceinstance") or {}
        model = self.by_graph.get(ri.get("graph_id"))
        if model is None:
            return None
        desc = (ri.get("descriptors") or {}).get(self.language) or {}
        name = desc.get("name") or ri.get("name") or ri.get("resourceinstanceid")
        return NameIndex.entity(model.name, ri["resourceinstanceid"], str(name),
                                desc.get("description", ""), graph_id=model.graph_id)

    # ── the Vocabulary protocol ───────────────────────────────────────────
    def type_words(self) -> dict[str, str]:
        words = {}
        for m in self.models.values():
            for w in plurals(m.name):
                words[w] = m.name
            for w in plurals(m.slug.replace("_", " ")):
                words.setdefault(w, m.name)
        words.update(self.extra_type_words)
        return words

    def relations(self) -> list[Relation]:
        # one Relation per alias: a backend names a link by its alias, and the
        # planner keys relations by name, so the same alias on several models
        # (HER's actor, on most of them) is one relation spanning them all
        by_alias: dict[str, dict] = {}
        for m in self.models.values():
            for n in m.nodes:
                if n.get("datatype") not in LINK_TYPES or not n.get("alias"):
                    continue
                targets = {self.by_graph[g["graphid"]].name
                           for g in (n.get("config") or {}).get("graphs") or []
                           if g.get("graphid") in self.by_graph}
                forms = {str(n.get("name") or "").lower(), n["alias"].replace("_", " ").lower()}
                forms |= {f.lower() for f in self.relation_forms.get(n["alias"], [])}
                forms |= {f.lower() for f in self._bundle_forms.get((m.name, n["alias"]), [])}
                r = by_alias.setdefault(n["alias"], {"forms": set(), "domain": set(), "range": set(),
                                                    "ends": set()})
                r["forms"] |= forms
                r["ends"].add((m.name, frozenset(targets)))
                r["domain"].add(m.name)
                r["range"] |= targets
        out = [Relation(alias, tuple(sorted(f for f in r["forms"] if f)), frozenset(r["domain"]),
                        frozenset(r["range"]), style="field", ends=frozenset(r["ends"]))
               for alias, r in by_alias.items()]
        return out + self._qualified_relations()

    def _qualified_relations(self) -> list[Relation]:
        """Bundle entries that need a value on the same entry as the link:
        "designed by" → actor, with role type = Architect (its concept id)."""
        if self._qualified is not None:
            return self._qualified
        self._qualified = []
        if not self._pending_qualified:
            return self._qualified
        concepts = {(v.field, v.label.lower()): v.value for v in self.values()}
        for model, e in self._pending_qualified:
            m = self.models[model]
            n = next((x for x in m.nodes if x.get("alias") == e["node"]), None)
            q = e["qualifier"]
            cid = concepts.get((q["node"], str(q["value"]).lower()))
            said = f"{model}: '{(e.get('phrases') or ['?'])[0]}' → {e['node']} + {q['node']} = {q['value']}"
            if n is None:
                self.skipped.append(f"{said}: no node '{e['node']}'")
                continue
            if n.get("datatype") not in LINK_TYPES:
                # a qualified date or property needs a tile-scoped condition
                # the plan can't express yet (docs/tasks/ceist-group-grounding.md)
                self.skipped.append(f"{said}: qualified {n.get('datatype')} entries aren't "
                                    "supported yet, only qualified links")
                continue
            if cid is None:
                self.skipped.append(f"{said}: '{q['value']}' isn't a value of {q['node']}")
                continue
            targets = frozenset(self.by_graph[g["graphid"]].name
                                for g in (n.get("config") or {}).get("graphs") or []
                                if g.get("graphid") in self.by_graph)
            self._qualified.append(Relation(
                f"{e['node']}#{q['value']}", tuple(sorted({p.lower() for p in e["phrases"]})),
                frozenset({model}), targets, style="field", path=e["node"],
                qualifier=(q["node"], cid, q["value"])))
        return self._qualified

    def values(self) -> list[Value]:
        """Every item of every controlled list (and legacy concept collection)
        a node draws from, by preferred and alternative label."""
        if self.rdm is None:
            return []
        out = []
        for m in self.models.values():
            for n in m.nodes:
                if n.get("datatype") not in CONTROLLED_TYPES or not n.get("alias"):
                    continue
                cid = collection_of(n)
                coll = self.rdm.get_collection(cid) if cid and self.rdm.has_collection(cid) else None
                if coll is None:
                    continue
                for item_id in coll.get_concept_ids():
                    c = coll.get_concept(item_id)
                    self._index_item(cid, item_id, c)
                    label = self._labels[item_id]
                    alts = list(self.alt_labels.get(getattr(c, "uri", None) or "", []))
                    native = getattr(c, "alt_labels", None) or {}
                    native = native.get(self.language, []) if isinstance(native, dict) else native
                    alts += [native] if isinstance(native, str) else list(native)
                    phrases = {label.lower()} | {str(a).lower() for a in alts}
                    for phrase in phrases:
                        if phrase:
                            out.append(Value(phrase, n["alias"], item_id, label,
                                             frozenset({m.name}), "concept"))
        return out

    def _index_item(self, collection_id: str, item_id: str, c) -> None:
        """What read-back and the backends need about one list item: its
        label, narrower items, label value ids, URI."""
        if item_id in self._items:
            return
        self._narrower[item_id] = list(getattr(c, "narrower", None) or [])
        self._concept_of[item_id] = item_id
        labels = []
        for lang, lab in (c.to_dict().get("pref_label") or {}).items():
            if isinstance(lab, dict):
                if lab.get("id"):
                    self._concept_of[lab["id"]] = item_id
                labels.append({"id": lab.get("id"), "value": lab.get("value"),
                               "language_id": lang, "valuetype_id": "prefLabel"})
        uri = getattr(c, "uri", None) or ""
        if uri:
            self._concept_of[uri] = item_id
        prefs = c.pref_label if isinstance(c.pref_label, dict) else {}
        self._labels[item_id] = (c.get_label(self.language) or prefs.get(self.language)
                                 or next(iter(prefs.values()), item_id))
        self._items[item_id] = {"collection": collection_id, "uri": uri, "labels": labels}

    def date_fields(self) -> list[DateField]:
        out = []
        for m in self.models.values():
            nodes = [n for n in m.nodes if n.get("datatype") in DATE_TYPES and n.get("alias")]
            for n in nodes:
                name = str(n.get("name") or n["alias"]).lower()
                forms = {name, n["alias"].replace("_", " ").lower()}
                forms |= {f.lower() for f in self.date_forms.get(n["alias"], [])}
                forms |= {f.lower() for f in self._bundle_forms.get((m.name, n["alias"]), [])}
                out.append(DateField(n["alias"], name, tuple(sorted(forms, key=len, reverse=True)),
                                     frozenset({m.name}), default=len(nodes) == 1))
        return out

    def descendants(self, concept_id: str) -> list[str]:
        """Every narrower concept, transitively (from Alizarin's hierarchy)."""
        if not self._narrower:
            self.values()
        out, todo = [], list(self._narrower.get(concept_id, []))
        while todo:
            c = todo.pop()
            if c not in out:
                out.append(c)
                todo += self._narrower.get(c, [])
        return out

    # ── lookups for read-back (a compiled query → a plan again) ───────────
    def entity(self, resource_id: str) -> Entity | None:
        return self._index.by_id.get(resource_id)

    def ids_of(self, type_name: str) -> set[str]:
        """Every record of a type (from the business data)."""
        return {e.id for e in self._index.entities if e.type == type_name}

    def concept_label(self, concept_id: str) -> str:
        if not self._labels:
            self.values()
        return self._labels.get(concept_id, concept_id)

    def model_by_slug(self, slug: str) -> Model | None:
        return next((m for m in self.models.values() if m.slug == slug), None)

    def node(self, type_name: str, alias: str) -> dict | None:
        return next((n for n in self.model(type_name).nodes if n.get("alias") == alias), None)

    def date_label(self, type_name: str, alias: str) -> str:
        n = self.node(type_name, alias) or {}
        return str(n.get("name") or alias).lower()

    def concept_of(self, value) -> str | None:
        """The item a tile's stored value names: a concept value's label id
        (or the item's own id), or a controlled-list reference
        ({"labels": [{"list_item_id", "id"}], "uri"})."""
        if not self._concept_of:
            self.values()
        if isinstance(value, dict):
            for lab in value.get("labels") or []:
                for key in ("list_item_id", "id"):
                    hit = self._concept_of.get(lab.get(key) or "")
                    if hit:
                        return hit
            return self._concept_of.get(value.get("uri") or "")
        return self._concept_of.get(value) if isinstance(value, str) else None

    def reference_items(self, item_ids) -> list[dict]:
        """Items as Arches stores a reference value ({"uri", "list_id",
        "labels": [...]}): what an Arches Search reference clause takes."""
        if not self._items:
            self.values()
        out = []
        for i in item_ids:
            it = self._items.get(i)
            if it is None:
                continue
            out.append({"uri": it["uri"], "list_id": it["collection"],
                        "labels": [dict(lab, list_item_id=i) for lab in it["labels"]]})
        return out

    def is_reference(self, type_name: str, alias: str) -> bool:
        """A controlled-list node (`reference`), not a legacy concept node."""
        return (self.node(type_name, alias) or {}).get("datatype") in REFERENCE_TYPES

    def rank_entities(self, terms: set[str]) -> list[tuple[float, Entity]]:
        return self._index.rank(terms)

    def implied_types(self) -> dict[str, str]:
        people = next((m.name for m in self.models.values()
                       if m.name.lower() in ("person", "people", "persons")), None)
        return {"who": people} if people else {}

    def hint_words(self) -> dict[str, str]:
        return {}

    # ── for backends ─────────────────────────────────────────────────────
    def model(self, type_name: str) -> Model:
        return self.models[type_name]
