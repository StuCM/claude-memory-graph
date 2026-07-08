import re
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pyoxigraph as ox

from .namespaces import (
    MEM, RDF, RDFS, GRAPH_SCHEMA, GRAPH_LINKS, GRAPH_CONCEPTS, GRAPH_RESOURCE_BASE,
    SPARQL_PREFIXES, RDF_TYPE, XSD_DATETIME, XSD_BOOLEAN,
    mem_node, resource_graph_node,
)
from . import ontology
from .capture_rules import names_similar, normalize_name

log = logging.getLogger(__name__)

# Inside the package so wheel installs (pipx/uvx) ship it too.
_BASE_TTL_PATH = Path(__file__).parent / "base.ttl"

# Property keys and relation names become IRI local names — keep them sane.
_LOCAL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# The ontology's version marker: subject is the mem: namespace itself.
_ONTOLOGY_IRI = ox.NamedNode(MEM)
_OWL_VERSION_INFO = ox.NamedNode("http://www.w3.org/2002/07/owl#versionInfo")
_TTL_VERSION_RE = re.compile(r'owl:versionInfo\s+"([^"]+)"')


@dataclass
class LinkedResource:
    iri: ox.NamedNode
    model: str
    relation: str
    direction: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class RecallResult:
    iri: ox.NamedNode
    model: str
    properties: dict[str, str]
    linked: list[LinkedResource]


class MemoryStore:
    def __init__(self, store: ox.Store, data_path: Optional[Path] = None):
        self._store = store
        self._data_path = data_path
        # Set per-request by the MCP layer (client name/version); stamped as
        # mem:capturedBy provenance on every node created while set.
        self.capture_client: Optional[str] = None

    @classmethod
    def open_or_create(cls, data_dir: Path) -> "MemoryStore":
        data_dir.mkdir(parents=True, exist_ok=True)
        nq_path = data_dir / "graph.nq"
        store = ox.Store()

        if nq_path.exists():
            log.info("Loading persisted data from %s", nq_path)
            with open(nq_path, "rb") as f:
                store.load(f, ox.RdfFormat.N_QUADS)
            log.info("Persisted data loaded")

        ms = cls(store, nq_path)
        ms._ensure_base_ontology()
        return ms

    def save(self) -> None:
        if self._data_path is None:
            return
        # ponytail: full dump + atomic rename on every write; switch to the
        # RocksDB-backed Store if the graph outgrows a few MB (loses
        # multi-session safety: RocksDB holds an exclusive lock per process).
        tmp = self._data_path.with_name(self._data_path.name + ".tmp")
        with open(tmp, "wb") as f:
            self._store.dump(f, ox.RdfFormat.N_QUADS)
        tmp.replace(self._data_path)

    def _ensure_base_ontology(self) -> None:
        # Keyed on owl:versionInfo: a store persisted under an older base.ttl
        # gets the current one re-loaded on open (bump the version in base.ttl
        # and every store upgrades — no loader edits per feature). Loading is
        # set-semantics, so re-loading over an existing schema graph is safe
        # and never touches LLM-added relations; only the stale version
        # marker is removed first so the check stays single-valued.
        schema_node = ox.NamedNode(GRAPH_SCHEMA)
        ttl = _BASE_TTL_PATH.read_text(encoding="utf-8")
        match = _TTL_VERSION_RE.search(ttl)
        current = match.group(1) if match else ""
        stored = None
        for quad in self._store.quads_for_pattern(
            _ONTOLOGY_IRI, _OWL_VERSION_INFO, None, schema_node
        ):
            if isinstance(quad.object, ox.Literal):
                stored = quad.object.value
        if stored != current:
            log.info("Loading base ontology %s into schema graph", current)
            for quad in list(self._store.quads_for_pattern(
                _ONTOLOGY_IRI, _OWL_VERSION_INFO, None, schema_node
            )):
                self._store.remove(quad)
            self._store.load(ttl.encode(), ox.RdfFormat.TURTLE, to_graph=schema_node)
            log.info("Base ontology loaded")

    # ================================================================
    # Helpers
    # ================================================================

    def _now(self) -> ox.Literal:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return ox.Literal(ts, datatype=XSD_DATETIME)

    def _new_resource_iri(self) -> tuple[str, ox.NamedNode]:
        uid = str(uuid.uuid4())
        return uid, ox.NamedNode(f"{MEM}resource/{uid}")

    def _new_concept_iri(self) -> ox.NamedNode:
        return ox.NamedNode(f"{MEM}concept/{uuid.uuid4()}")

    def _new_link_iri(self) -> ox.NamedNode:
        return ox.NamedNode(f"{MEM}link/{uuid.uuid4()}")

    def _query(self, sparql: str):
        return self._store.query(f"{SPARQL_PREFIXES}\n{sparql}")

    def _add(self, s: ox.NamedNode, p: ox.NamedNode, o, g: ox.NamedNode) -> None:
        self._store.add(ox.Quad(s, p, o, g))

    def _check_key(self, key: str) -> None:
        if not _LOCAL_NAME_RE.match(key):
            raise ValueError(
                f"Invalid property key '{key}': use a camelCase identifier "
                "(letters, digits, underscores; must start with a letter)"
            )

    # ================================================================
    # Resource operations
    # ================================================================

    def create_resource(
        self, model: str, properties: dict[str, str]
    ) -> tuple[str, ox.NamedNode]:
        if not ontology.is_resource_model(model):
            raise ValueError(f"Unknown resource model: {model}")

        uid, iri = self._new_resource_iri()
        graph = resource_graph_node(uid)
        now = self._now()

        self._add(iri, RDF_TYPE, mem_node(model), graph)
        self._add(iri, mem_node("createdAt"), now, graph)
        self._add(iri, mem_node("updatedAt"), now, graph)
        if self.capture_client:
            self._add(iri, mem_node("capturedBy"), ox.Literal(self.capture_client), graph)

        for key, value in properties.items():
            self._check_key(key)
            self._add(iri, mem_node(key), ox.Literal(value), graph)

        return uid, iri

    def update_resource(
        self, resource_iri: ox.NamedNode, graph_id: str, properties: dict[str, str]
    ) -> None:
        graph = resource_graph_node(graph_id)

        for key, value in properties.items():
            self._check_key(key)
            pred = mem_node(key)
            for quad in list(self._store.quads_for_pattern(resource_iri, pred, None, graph)):
                self._store.remove(quad)
            self._add(resource_iri, pred, ox.Literal(value), graph)

        updated_pred = mem_node("updatedAt")
        for quad in list(self._store.quads_for_pattern(resource_iri, updated_pred, None, graph)):
            self._store.remove(quad)
        self._add(resource_iri, updated_pred, self._now(), graph)

    def find_resource(
        self, model: str, name: str
    ) -> Optional[tuple[str, ox.NamedNode]]:
        name_prop = ontology.name_property(model)
        sparql = (
            f'SELECT ?node ?g WHERE {{\n'
            f'    GRAPH ?g {{\n'
            f'        ?node rdf:type mem:{model} .\n'
            f'        ?node mem:{name_prop} "{name}" .\n'
            f'        FILTER NOT EXISTS {{ ?node mem:invalidated ?inv }}\n'
            f'    }}\n'
            f'    FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))\n'
            f'}} LIMIT 1'
        )
        results = self._query(sparql)
        if isinstance(results, ox.QuerySolutions):
            for solution in results:
                node = solution["node"]
                g = solution["g"]
                if isinstance(node, ox.NamedNode) and isinstance(g, ox.NamedNode):
                    graph_id = g.value.removeprefix(GRAPH_RESOURCE_BASE)
                    return graph_id, node
        return None

    def resource_names(self, model: str) -> list[str]:
        """Names of all live (non-invalidated) resources of a model."""
        name_prop = ontology.name_property(model)
        sparql = (
            f'SELECT ?name WHERE {{\n'
            f'    GRAPH ?g {{\n'
            f'        ?node rdf:type mem:{model} .\n'
            f'        ?node mem:{name_prop} ?name .\n'
            f'        FILTER NOT EXISTS {{ ?node mem:invalidated ?inv }}\n'
            f'    }}\n'
            f'    FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))\n'
            f'}}'
        )
        names = []
        for solution in self._query(sparql):
            name = solution["name"]
            if isinstance(name, ox.Literal):
                names.append(name.value)
        return names

    def find_similar_resources(self, model: str, name: str) -> list[str]:
        """Names of live resources of `model` whose names are near-duplicates
        of `name` (used by the write-time duplicate guard)."""
        return [n for n in self.resource_names(model) if names_similar(n, name)]

    def get_resource_properties(
        self, resource_iri: ox.NamedNode, graph_id: str
    ) -> dict[str, str]:
        graph = resource_graph_node(graph_id)
        props: dict[str, str] = {}
        for quad in self._store.quads_for_pattern(resource_iri, None, None, graph):
            pred_str = quad.predicate.value
            if pred_str.startswith(MEM):
                key = pred_str[len(MEM):]
                obj = quad.object
                if isinstance(obj, ox.Literal):
                    props[key] = obj.value
                elif isinstance(obj, ox.NamedNode):
                    props[key] = obj.value
        return props

    def _get_resource_type(
        self, resource_iri: ox.NamedNode, graph: ox.NamedNode
    ) -> str:
        for quad in self._store.quads_for_pattern(resource_iri, RDF_TYPE, None, graph):
            obj = quad.object
            if isinstance(obj, ox.NamedNode) and obj.value.startswith(MEM):
                return obj.value[len(MEM):]
        raise ValueError("Resource type not found")

    # ================================================================
    # Concept operations
    # ================================================================

    def store_concept(
        self, concept_type: str, label: str, properties: dict[str, str]
    ) -> ox.NamedNode:
        if not ontology.is_concept_type(concept_type):
            raise ValueError(f"Unknown concept type: {concept_type}")

        existing = self.find_concept(concept_type, label)
        if existing is not None:
            return existing

        iri = self._new_concept_iri()
        graph = ox.NamedNode(GRAPH_CONCEPTS)

        self._add(iri, RDF_TYPE, mem_node(concept_type), graph)
        self._add(iri, mem_node("label"), ox.Literal(label), graph)
        self._add(iri, mem_node("createdAt"), self._now(), graph)

        for key, value in properties.items():
            if key == "label":
                continue
            self._check_key(key)
            self._add(iri, mem_node(key), ox.Literal(value), graph)

        return iri

    def find_concept(
        self, concept_type: str, label: str
    ) -> Optional[ox.NamedNode]:
        """Find a concept by label. Concept identity is case- and
        whitespace-insensitive: an exact match wins, otherwise a normalized
        match ('Rust' finds 'rust') — so store and link resolve consistently
        and near-duplicate concept nodes don't accumulate."""
        sparql = (
            f'SELECT ?node WHERE {{\n'
            f'    GRAPH <{GRAPH_CONCEPTS}> {{\n'
            f'        ?node rdf:type mem:{concept_type} .\n'
            f'        ?node mem:label "{label}" .\n'
            f'    }}\n'
            f'}} LIMIT 1'
        )
        results = self._query(sparql)
        if isinstance(results, ox.QuerySolutions):
            for solution in results:
                node = solution["node"]
                if isinstance(node, ox.NamedNode):
                    return node

        wanted = normalize_name(label).casefold()
        sparql = (
            f'SELECT ?node ?label WHERE {{\n'
            f'    GRAPH <{GRAPH_CONCEPTS}> {{\n'
            f'        ?node rdf:type mem:{concept_type} .\n'
            f'        ?node mem:label ?label .\n'
            f'    }}\n'
            f'}}'
        )
        for solution in self._query(sparql):
            node, existing = solution["node"], solution["label"]
            if (
                isinstance(node, ox.NamedNode)
                and isinstance(existing, ox.Literal)
                and normalize_name(existing.value).casefold() == wanted
            ):
                return node
        return None

    # ================================================================
    # Relation ontology (schema graph is the source of truth)
    # ================================================================

    def valid_relations(self) -> dict[str, str]:
        """All relation names usable in links, mapped to their descriptions."""
        sparql = (
            f'SELECT ?r ?comment WHERE {{\n'
            f'    GRAPH <{GRAPH_SCHEMA}> {{\n'
            f'        ?r rdf:type mem:RelationType .\n'
            f'        OPTIONAL {{ ?r rdfs:comment ?comment }}\n'
            f'    }}\n'
            f'}}'
        )
        relations: dict[str, str] = {}
        for solution in self._query(sparql):
            r = solution["r"]
            if isinstance(r, ox.NamedNode) and r.value.startswith(MEM):
                comment = solution["comment"]
                desc = comment.value if isinstance(comment, ox.Literal) else ""
                relations[r.value[len(MEM):]] = desc
        return relations

    def relation_lexicon(self) -> dict[str, dict]:
        """The schema graph as the query planner's lexicon: every relation
        with its description, natural-language verb forms, and (union-
        semantics, hint-only) domain/range types."""
        sparql = (
            f'SELECT ?r ?comment ?vf ?dom ?rng WHERE {{\n'
            f'    GRAPH <{GRAPH_SCHEMA}> {{\n'
            f'        ?r rdf:type mem:RelationType .\n'
            f'        OPTIONAL {{ ?r rdfs:comment ?comment }}\n'
            f'        OPTIONAL {{ ?r mem:verbForms ?vf }}\n'
            f'        OPTIONAL {{ ?r mem:domainIncludes ?dom }}\n'
            f'        OPTIONAL {{ ?r mem:rangeIncludes ?rng }}\n'
            f'    }}\n'
            f'}}'
        )
        lexicon: dict[str, dict] = {}
        for solution in self._query(sparql):
            r = solution["r"]
            if not (isinstance(r, ox.NamedNode) and r.value.startswith(MEM)):
                continue
            entry = lexicon.setdefault(r.value[len(MEM):], {
                "description": "", "verbForms": set(), "domain": set(), "range": set(),
            })
            comment = solution["comment"]
            if isinstance(comment, ox.Literal):
                entry["description"] = comment.value
            vf = solution["vf"]
            if isinstance(vf, ox.Literal):
                entry["verbForms"].add(vf.value)
            for key, var in (("domain", "dom"), ("range", "rng")):
                node = solution[var]
                if isinstance(node, ox.NamedNode) and node.value.startswith(MEM):
                    entry[key].add(node.value[len(MEM):])
        return {name: {"description": e["description"],
                       "verbForms": sorted(e["verbForms"]),
                       "domain": sorted(e["domain"]),
                       "range": sorted(e["range"])}
                for name, e in lexicon.items()}

    def add_relation(self, relation: str, description: str,
                     verb_forms: list[str]) -> None:
        """Extend the ontology with a new relation type (persisted in the
        schema graph). Verb forms are mandatory: the schema graph is the
        query planner's lexicon, so a relation without phrasings would be
        linkable but never groundable from language."""
        self._check_key(relation)
        forms = [f.strip() for f in verb_forms if f and f.strip()]
        if not forms:
            raise ValueError(
                f"New relation '{relation}' needs verb forms: the natural-language "
                "phrasings a question would use for it (e.g. 'mentors', 'mentored by'). "
                "Pass new_relation_verb_forms alongside the description."
            )
        graph = ox.NamedNode(GRAPH_SCHEMA)
        node = mem_node(relation)
        self._add(node, RDF_TYPE, ox.NamedNode(f"{RDF}Property"), graph)
        self._add(node, RDF_TYPE, mem_node("RelationType"), graph)
        self._add(node, ox.NamedNode(f"{RDFS}comment"), ox.Literal(description), graph)
        self._add(node, mem_node("definedAt"), self._now(), graph)
        for form in forms:
            self._add(node, mem_node("verbForms"), ox.Literal(form), graph)

    def amend_relation(
        self, relation: str, add_forms: list[str], remove_forms: list[str]
    ) -> tuple[list[str], list[str]]:
        """Curate a relation's verb-form lexicon in place. Adding works on any
        relation (base.ttl reloads are set-semantics, so added forms survive
        ontology upgrades). Removing only works on LLM-added relations: a
        base-ontology form removed from the store would silently resurrect on
        the next base.ttl version bump — edit base.ttl instead.
        Returns (added, removed)."""
        if relation not in self.valid_relations():
            raise ValueError(
                f"Unknown relation '{relation}'. Existing: "
                f"{', '.join(sorted(self.valid_relations()))}"
            )
        adds = [f.strip() for f in add_forms if f and f.strip()]
        removes = [f.strip() for f in remove_forms if f and f.strip()]
        if not adds and not removes:
            raise ValueError("Nothing to amend: pass verb forms to add and/or remove.")
        graph = ox.NamedNode(GRAPH_SCHEMA)
        node = mem_node(relation)
        if removes:
            llm_added = any(self._store.quads_for_pattern(
                node, mem_node("definedAt"), None, graph))
            if not llm_added:
                raise ValueError(
                    f"'{relation}' is a base-ontology relation: a form removed from "
                    "the store would silently resurrect on the next base.ttl "
                    "upgrade. Edit base.ttl (and bump owl:versionInfo) instead. "
                    "Adding forms to it is fine."
                )
        removed = []
        for form in removes:
            for quad in list(self._store.quads_for_pattern(
                    node, mem_node("verbForms"), ox.Literal(form), graph)):
                self._store.remove(quad)
                removed.append(form)
        for form in adds:
            self._add(node, mem_node("verbForms"), ox.Literal(form), graph)
        return adds, removed

    # ================================================================
    # Cross-link operations (bi-temporal: two clocks per edge)
    # ================================================================

    def single_valued_relations(self) -> set[str]:
        """Relations marked mem:singleValued in the schema: one current
        target per source — the contradiction-closure rule applies."""
        sparql = (
            f'SELECT ?r WHERE {{\n'
            f'    GRAPH <{GRAPH_SCHEMA}> {{ ?r mem:singleValued true }}\n'
            f'}}'
        )
        found = set()
        for solution in self._query(sparql):
            r = solution["r"]
            if isinstance(r, ox.NamedNode) and r.value.startswith(MEM):
                found.add(r.value[len(MEM):])
        return found

    def _close_conflicting_links(
        self, source_iri: ox.NamedNode, target_iri: ox.NamedNode, relation: str
    ) -> int:
        """Contradiction closure: bound the valid time of open edges with the
        same source and single-valued relation but a DIFFERENT target. The old
        fact was true and stopped being (worldChange) — never deleted."""
        sparql = (
            f'SELECT ?link WHERE {{\n'
            f'    GRAPH <{GRAPH_LINKS}> {{\n'
            f'        ?link rdf:type mem:CrossLink ;\n'
            f'              mem:linkSource <{source_iri.value}> ;\n'
            f'              mem:linkRelation "{relation}" ;\n'
            f'              mem:linkTarget ?t .\n'
            f'        FILTER(?t != <{target_iri.value}>)\n'
            f'        FILTER NOT EXISTS {{ ?link mem:linkValidUntil ?end }}\n'
            f'        FILTER NOT EXISTS {{ ?link mem:linkInvalidatedAt ?inv }}\n'
            f'    }}\n'
            f'}}'
        )
        graph = ox.NamedNode(GRAPH_LINKS)
        now = self._now()
        closed = 0
        for solution in self._query(sparql):
            link = solution["link"]
            if not isinstance(link, ox.NamedNode):
                continue
            self._add(link, mem_node("linkValidUntil"), now, graph)
            self._add(link, mem_node("linkInvalidatedAt"), now, graph)
            self._add(link, mem_node("invalidationKind"), ox.Literal("worldChange"), graph)
            closed += 1
        return closed

    def create_link(
        self,
        source_iri: ox.NamedNode,
        target_iri: ox.NamedNode,
        relation: str,
        metadata: dict[str, str],
    ) -> tuple[ox.NamedNode, int]:
        """Create an edge; returns (link_iri, closed) where closed is how many
        conflicting open edges the contradiction-closure rule bounded."""
        closed = 0
        if relation in self.single_valued_relations():
            closed = self._close_conflicting_links(source_iri, target_iri, relation)

        link_iri = self._new_link_iri()
        graph = ox.NamedNode(GRAPH_LINKS)

        self._add(link_iri, RDF_TYPE, mem_node("CrossLink"), graph)
        self._add(link_iri, mem_node("linkSource"), source_iri, graph)
        self._add(link_iri, mem_node("linkTarget"), target_iri, graph)
        self._add(link_iri, mem_node("linkRelation"), ox.Literal(relation), graph)
        self._add(link_iri, mem_node("linkCreatedAt"), self._now(), graph)
        # World clock: defaults to recording time; a caller-supplied
        # linkValidFrom in metadata backdates it ("since 2019") instead.
        if "linkValidFrom" not in metadata:
            self._add(link_iri, mem_node("linkValidFrom"), self._now(), graph)

        for key, value in metadata.items():
            self._check_key(key)
            self._add(link_iri, mem_node(key), ox.Literal(value), graph)

        return link_iri, closed

    def close_link(
        self,
        source_iri: ox.NamedNode,
        target_iri: ox.NamedNode,
        relation: str,
        kind: str = "worldChange",
    ) -> bool:
        """Bound an open edge instead of deleting it. worldChange also closes
        the world clock (was true, stopped being); a correction only revises
        belief (never was true) so point-in-time queries can exclude it."""
        if kind not in ("worldChange", "correction"):
            raise ValueError(
                f"Unknown invalidation kind '{kind}': use 'worldChange' "
                "(was true, no longer) or 'correction' (never was true)."
            )
        sparql = (
            f'SELECT ?link WHERE {{\n'
            f'    GRAPH <{GRAPH_LINKS}> {{\n'
            f'        ?link rdf:type mem:CrossLink ;\n'
            f'              mem:linkSource <{source_iri.value}> ;\n'
            f'              mem:linkTarget <{target_iri.value}> ;\n'
            f'              mem:linkRelation "{relation}" .\n'
            f'        FILTER NOT EXISTS {{ ?link mem:linkValidUntil ?end }}\n'
            f'        FILTER NOT EXISTS {{ ?link mem:linkInvalidatedAt ?inv }}\n'
            f'    }}\n'
            f'}} LIMIT 1'
        )
        link_iri = None
        for solution in self._query(sparql):
            node = solution["link"]
            if isinstance(node, ox.NamedNode):
                link_iri = node
        if link_iri is None:
            return False

        graph = ox.NamedNode(GRAPH_LINKS)
        now = self._now()
        if kind == "worldChange":
            self._add(link_iri, mem_node("linkValidUntil"), now, graph)
        self._add(link_iri, mem_node("linkInvalidatedAt"), now, graph)
        self._add(link_iri, mem_node("invalidationKind"), ox.Literal(kind), graph)
        return True

    def remove_link(
        self,
        source_iri: ox.NamedNode,
        target_iri: ox.NamedNode,
        relation: str,
    ) -> bool:
        sparql = (
            f'SELECT ?link WHERE {{\n'
            f'    GRAPH <{GRAPH_LINKS}> {{\n'
            f'        ?link rdf:type mem:CrossLink .\n'
            f'        ?link mem:linkSource <{source_iri.value}> .\n'
            f'        ?link mem:linkTarget <{target_iri.value}> .\n'
            f'        ?link mem:linkRelation "{relation}" .\n'
            f'    }}\n'
            f'}} LIMIT 1'
        )
        link_iri = None
        results = self._query(sparql)
        if isinstance(results, ox.QuerySolutions):
            for solution in results:
                node = solution["link"]
                if isinstance(node, ox.NamedNode):
                    link_iri = node

        if link_iri is None:
            return False

        graph = ox.NamedNode(GRAPH_LINKS)
        for quad in list(self._store.quads_for_pattern(link_iri, None, None, graph)):
            self._store.remove(quad)
        return True

    # ================================================================
    # Recall
    # ================================================================

    def _neighbours(
        self, iris: list[ox.NamedNode]
    ) -> list[tuple[str, LinkedResource]]:
        """One query: every OPEN link touching `iris`, with the other node's
        full properties — covers both resource graphs and the concepts graph.
        Closed/invalidated edges (bi-temporal bounds) are excluded: retrieval
        defaults to "true now"; point-in-time questions go through SPARQL.
        Returns (touched_iri_value, linked_resource) pairs."""
        values = " ".join(f"<{i.value}>" for i in iris)
        # FILTER/BIND referencing ?me must sit at the top level: inside the
        # GRAPH group, VALUES-bound ?me is out of scope (SPARQL bottom-up eval).
        sparql = (
            f'SELECT ?me ?other ?dir ?rel ?p ?o WHERE {{\n'
            f'    VALUES ?me {{ {values} }}\n'
            f'    GRAPH <{GRAPH_LINKS}> {{\n'
            f'        ?link rdf:type mem:CrossLink ;\n'
            f'              mem:linkSource ?s ;\n'
            f'              mem:linkTarget ?t ;\n'
            f'              mem:linkRelation ?rel .\n'
            f'        FILTER NOT EXISTS {{ ?link mem:linkValidUntil ?closedAt }}\n'
            f'        FILTER NOT EXISTS {{ ?link mem:linkInvalidatedAt ?invAt }}\n'
            f'    }}\n'
            f'    FILTER(?s = ?me || ?t = ?me)\n'
            f'    BIND(IF(?s = ?me, ?t, ?s) AS ?other)\n'
            f'    BIND(IF(?s = ?me, "outgoing", "incoming") AS ?dir)\n'
            f'    GRAPH ?g {{ ?other ?p ?o }}\n'
            f'    FILTER(?g != <{GRAPH_LINKS}> && ?g != <{GRAPH_SCHEMA}>)\n'
            f'}}'
        )
        groups: dict[tuple[str, str, str, str], LinkedResource] = {}
        for solution in self._query(sparql):
            me, other = solution["me"], solution["other"]
            rel, dir_ = solution["rel"], solution["dir"]
            p, o = solution["p"], solution["o"]
            if not (isinstance(other, ox.NamedNode) and isinstance(rel, ox.Literal)):
                continue
            key = (me.value, other.value, rel.value, dir_.value)
            lr = groups.setdefault(key, LinkedResource(
                iri=other, model="", relation=rel.value, direction=dir_.value,
            ))
            if p == RDF_TYPE and isinstance(o, ox.NamedNode) and o.value.startswith(MEM):
                lr.model = o.value[len(MEM):]
            elif p.value.startswith(MEM) and isinstance(o, ox.Literal):
                lr.properties[p.value[len(MEM):]] = o.value
        return [(key[0], lr) for key, lr in groups.items()]

    def recall(
        self, resource_iri: ox.NamedNode, graph_id: str, depth: int
    ) -> RecallResult:
        props = self.get_resource_properties(resource_iri, graph_id)
        graph = resource_graph_node(graph_id)
        model = self._get_resource_type(resource_iri, graph)

        seen = {resource_iri.value}
        linked: list[LinkedResource] = []
        frontier = [resource_iri]

        for hop in range(max(depth, 1)):
            if not frontier:
                break
            via_name = {
                lr.iri.value: lr.properties.get("name") or lr.properties.get("label", "")
                for lr in linked
            }
            next_frontier: list[ox.NamedNode] = []
            for me_value, lr in self._neighbours(frontier):
                if lr.iri.value in seen or lr.properties.get("invalidated") == "true":
                    continue
                seen.add(lr.iri.value)
                if hop > 0:
                    lr.direction = f"via {via_name.get(me_value) or me_value}"
                linked.append(lr)
                next_frontier.append(lr.iri)
            frontier = next_frontier

        return RecallResult(iri=resource_iri, model=model, properties=props, linked=linked)

    # ================================================================
    # Soft delete
    # ================================================================

    def forget_resource(
        self, resource_iri: ox.NamedNode, graph_id: str, reason: str
    ) -> None:
        graph = resource_graph_node(graph_id)
        self._add(resource_iri, mem_node("invalidated"), ox.Literal("true", datatype=XSD_BOOLEAN), graph)
        self._add(resource_iri, mem_node("invalidatedAt"), self._now(), graph)
        self._add(resource_iri, mem_node("invalidationReason"), ox.Literal(reason), graph)

    # ================================================================
    # SPARQL passthrough
    # ================================================================

    def query(self, sparql: str):
        return self._query(sparql)
