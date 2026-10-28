"""The vocabulary of Arches resource models — for Rós Madair and Arches Search.

Built from the data folder Alizarin and Rós Madair share:

    <data_dir>/graphs/*.json             resource models (Arches graph exports)
    <data_dir>/resources/**/*.json       business data (for the names questions use)
    <data_dir>/vocabularies/*.xml        SKOS thesauri (optional)

What a question can name, from that:

- **types**: each resource model, by its name ("Building" → "buildings");
- **relations**: each resource-instance node, by its name and alias ("Site",
  "operator"), from its model to the models its config allows;
- **controlled values**: every concept in the collection a concept node draws
  from, by preferred and alternative label ("listed" → Heritage status =
  Listed). Concept ids come from Alizarin's RDM cache, so they are exactly
  the ids Rós Madair interned — the planner never re-derives them.
  Alternative labels are read from the SKOS itself (Alizarin keeps only
  preferred labels on concepts), matched to Alizarin's concepts by URI;
- **a vocabulary bundle** (`bundle=`, built by `ceist vocab assemble`):
  its link and date phrasings join the forms below;
- **dates**: each date node, by its name, and by the words `date_forms`
  adds ("built" → construction date); a model's only date node is the one
  meant when no word picks;
- **records**: resource names, for anchors ("Leeds Dock").

Alizarin (`pip install alizarin`) is needed only for SKOS; without it,
questions can still name types, relations and records.
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .index import NameIndex
from .text import plurals
from .vocabulary import DateField, Entity, Relation, Value

LINK_TYPES = {"resource-instance", "resource-instance-list"}
CONCEPT_TYPES = {"concept", "concept-list"}
DATE_TYPES = {"date"}
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_SKOS = "{http://www.w3.org/2004/02/skos/core#}"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


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


@dataclass
class Model:
    graph_id: str
    name: str
    slug: str
    nodes: list[dict] = field(default_factory=list)
    doc: dict = field(default_factory=dict, repr=False)   # the graph JSON itself


def slug_of(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _graph_doc(path: Path) -> dict:
    doc = json.loads(path.read_text())
    if isinstance(doc, dict) and isinstance(doc.get("graph"), list):
        return doc["graph"][0]
    return doc


class ArchesVocabulary:
    def __init__(self, graphs: list[dict], rdm_cache=None, resources: list[dict] = (),
                 language: str = "en", extra_type_words: dict[str, str] | None = None,
                 alt_labels: dict[str, list[str]] | None = None,
                 relation_forms: dict[str, list[str]] | None = None,
                 date_forms: dict[str, list[str]] | None = None,
                 bundle: str | Path | dict | None = None):
        self.language = language
        self.alt_labels = alt_labels or {}       # concept URI → alternative labels
        self.models = {}
        for g in graphs:
            name = g.get("name") or g.get("slug") or g["graphid"]
            if isinstance(name, dict):                  # localized name
                name = name.get(language) or next(iter(name.values()))
            self.models[name] = Model(g["graphid"], name, g.get("slug") or slug_of(name),
                                      g.get("nodes", []), g)
        self.by_graph = {m.graph_id: m for m in self.models.values()}
        self.rdm = rdm_cache
        self.extra_type_words = extra_type_words or {}
        # extra phrasings per node alias: {"architect": ["designed by"]}
        self.relation_forms = relation_forms or {}
        # words that pick a date node: {"construction_date": ["built", "constructed"]}
        self.date_forms = date_forms or {}
        self._pending_qualified: list[tuple[str, dict]] = []
        self._qualified: list[Relation] | None = None
        self.skipped_qualified = 0
        if bundle is not None:
            self._absorb(bundle)
        self._narrower: dict[str, list[str]] = {}
        self._concept_of: dict[str, str] = {}    # label value id → concept id
        self._labels: dict[str, str] = {}        # concept id → label
        self.resources = list(resources)
        self._index = NameIndex([self._entity(r) for r in resources if self._entity(r)])
        self.names = {e.id: e.name for e in self._index.entities}

    # ── loading ───────────────────────────────────────────────────────────
    @classmethod
    def from_data_dir(cls, data_dir: str | Path, language: str = "en", **kw) -> "ArchesVocabulary":
        root = Path(data_dir)
        graphs = [_graph_doc(p) for p in sorted((root / "graphs").glob("*.json"))]
        resources = []
        for p in sorted((root / "resources").rglob("*.json")):
            doc = json.loads(p.read_text())
            resources += (doc.get("business_data") or {}).get("resources", [])
        rdm, alts = None, {}
        skos = sorted((root / "vocabularies").glob("*.xml")) if (root / "vocabularies").is_dir() else []
        if skos:
            import alizarin                              # the ids Rós Madair interned
            rdm = alizarin.RustRdmCache()
            for p in skos:
                xml = p.read_text()
                rdm.add_from_skos_xml(xml, "http://example.org/")
                alts.update(alt_labels(xml, language))
        return cls(graphs, rdm, resources, language, alt_labels=alts, **kw)

    def _absorb(self, bundle) -> None:
        """A vocabulary bundle's phrasings (ceist.bundle): unqualified link
        entries become relation phrasings, date entries date phrasings.
        Entries that carry a qualifier ("designed by" → actor + role
        Architect) become qualified relations (relations()); one whose
        value isn't in its node's collection is counted in skipped_qualified."""
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
                target = {"link": self.relation_forms, "date": self.date_forms}.get(kind)
                if target is not None:
                    target.setdefault(e["node"], [])
                    target[e["node"]] = list(dict.fromkeys(target[e["node"]] + e["phrases"]))

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
        out = []
        for m in self.models.values():
            for n in m.nodes:
                if n.get("datatype") not in LINK_TYPES or not n.get("alias"):
                    continue
                targets = frozenset(self.by_graph[g["graphid"]].name
                                    for g in (n.get("config") or {}).get("graphs") or []
                                    if g.get("graphid") in self.by_graph)
                forms = {str(n.get("name") or "").lower(), n["alias"].replace("_", " ").lower()}
                forms |= {f.lower() for f in self.relation_forms.get(n["alias"], [])}
                out.append(Relation(n["alias"], tuple(sorted(f for f in forms if f)),
                                    frozenset({m.name}), targets, style="field"))
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
            if n is None or n.get("datatype") not in LINK_TYPES or cid is None:
                self.skipped_qualified += 1
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
        if self.rdm is None:
            return []
        out = []
        for m in self.models.values():
            for n in m.nodes:
                if n.get("datatype") not in CONCEPT_TYPES or not n.get("alias"):
                    continue
                cid = (n.get("config") or {}).get("rdmCollection")
                coll = self.rdm.get_collection(cid) if cid and self.rdm.has_collection(cid) else None
                if coll is None:
                    continue
                for concept_id in coll.get_concept_ids():
                    c = coll.get_concept(concept_id)
                    self._narrower[concept_id] = list(getattr(c, "narrower", None) or [])
                    self._concept_of[concept_id] = concept_id
                    for lab in (c.to_dict().get("pref_label") or {}).values():
                        if isinstance(lab, dict) and lab.get("id"):
                            self._concept_of[lab["id"]] = concept_id
                    prefs = c.pref_label if isinstance(c.pref_label, dict) else {}
                    label = (c.get_label(self.language) or prefs.get(self.language)
                             or next(iter(prefs.values()), concept_id))
                    alts = list(self.alt_labels.get(getattr(c, "uri", None) or "", []))
                    native = getattr(c, "alt_labels", None) or {}
                    native = native.get(self.language, []) if isinstance(native, dict) else native
                    alts += [native] if isinstance(native, str) else list(native)
                    self._labels[concept_id] = label
                    phrases = {label.lower()} | {str(a).lower() for a in alts}
                    for phrase in phrases:
                        if phrase:
                            out.append(Value(phrase, n["alias"], concept_id, label,
                                             frozenset({m.name}), "concept"))
        return out

    def date_fields(self) -> list[DateField]:
        out = []
        for m in self.models.values():
            nodes = [n for n in m.nodes if n.get("datatype") in DATE_TYPES and n.get("alias")]
            for n in nodes:
                name = str(n.get("name") or n["alias"]).lower()
                forms = {name, n["alias"].replace("_", " ").lower()}
                forms |= {f.lower() for f in self.date_forms.get(n["alias"], [])}
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

    def concept_of(self, value_id: str) -> str | None:
        """The concept a tile's stored value id (a label's id, or the concept's own) names."""
        if not self._concept_of:
            self.values()
        return self._concept_of.get(value_id)

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
