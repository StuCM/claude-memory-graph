import os

from mcp.server import Server
from mcp.types import Tool, TextContent

from ..store import MemoryStore
from . import store_resource, link, recall, search, forget, query, reflect

_TOOLS = [
    Tool(
        name="memory_store_resource",
        description=(
            "Create or update a resource instance (Person, Project, Company, Task, Technology, "
            "Decision, Pattern). Each resource gets its own named graph. If a resource with "
            "matching model+name exists, its properties are updated. The name IS the node's "
            "identity: use a short, specific, stable title (Decision: imperative phrase stating "
            "the choice, e.g. 'Use pyoxigraph over rdflib'; Pattern: the phenomenon itself). "
            "A Decision requires a 'rationale' property and a Pattern a 'description' — "
            "creation is rejected without them. Creating a node whose name is similar to an "
            "existing one errors with the candidates: reuse the exact existing name to update "
            "it, or pass force=true only if it is genuinely a distinct thing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Resource model: Person, Project, Company, Task, Technology, Decision, Pattern",
                },
                "properties": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "Scalar properties as key-value pairs. 'name' is required; any other "
                        "camelCase keys are accepted (e.g. email, role, status, description). "
                        "Recommended shapes — Decision: rationale (required), outcome, date, "
                        "status; Pattern: description (required), example, appliesWhen. When "
                        "distilling from a file, add sourceContext/sourceDocument with its path."
                    ),
                },
                "force": {
                    "type": "boolean",
                    "description": (
                        "Create even though a similar-named node of this model exists. Only "
                        "after the duplicate guard listed candidates and none is the same thing."
                    ),
                    "default": False,
                },
            },
            "required": ["model", "properties"],
        },
    ),
    Tool(
        name="memory_store_concept",
        description=(
            "Create a shared concept node (Skill, Concept, Constraint, Preference). "
            "Concepts are lightweight shared nodes that enable traversal between resource "
            "graphs. Labels are lowercase singular by convention and matched case- and "
            "whitespace-insensitively: storing 'Rust' reuses an existing 'rust'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "concept_type": {
                    "type": "string",
                    "description": "Concept type: Skill, Concept, Constraint, Preference",
                },
                "label": {"type": "string", "description": "Label for this concept"},
                "properties": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Optional properties (e.g. description, proficiency)",
                },
            },
            "required": ["concept_type", "label"],
        },
    ),
    Tool(
        name="memory_link",
        description=(
            "Create a cross-graph relationship between two resources. The relation must "
            "exist in the ontology (core relations: worksOn, employedBy, owns, uses, "
            "madeBy, affects, assignedTo, partOf, relatesTo, supersedes, resolves, "
            "appliesTo, hasSkill, hasConcept, hasConstraint, hasPreference — an unknown "
            "relation errors with the full current list). ALWAYS prefer an existing "
            "relation, even if the fit is loose. Only when none genuinely matches, pass "
            "new_relation_description to extend the ontology with the new relation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source_model": {"type": "string"},
                "source_name": {"type": "string"},
                "target_model": {"type": "string"},
                "target_name": {"type": "string"},
                "relation": {
                    "type": "string",
                    "description": "Relationship type (e.g. worksOn, uses, employedBy, assignedTo)",
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Optional metadata on the link (e.g. since, role)",
                },
                "new_relation_description": {
                    "type": "string",
                    "description": (
                        "Only for defining a NEW relation when no existing one fits: "
                        "a one-line description of what the relation means "
                        "(e.g. 'Person mentors another Person'). Adds it to the ontology permanently."
                    ),
                },
                "new_relation_verb_forms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Required alongside new_relation_description: the natural-language "
                        "phrasings a question would use for the relation (e.g. ['mentors', "
                        "'mentored by', 'mentoring']). These make the relation groundable "
                        "by retrieval — a relation without them is linkable but never "
                        "findable from language."
                    ),
                },
            },
            "required": ["source_model", "source_name", "target_model", "target_name", "relation"],
        },
    ),
    Tool(
        name="memory_unlink",
        description="Remove a cross-graph relationship between two resources.",
        inputSchema={
            "type": "object",
            "properties": {
                "source_model": {"type": "string"},
                "source_name": {"type": "string"},
                "target_model": {"type": "string"},
                "target_name": {"type": "string"},
                "relation": {"type": "string"},
            },
            "required": ["source_model", "source_name", "target_model", "target_name", "relation"],
        },
    ),
    Tool(
        name="memory_search",
        description=(
            "Fuzzy search for graph entry points when you do NOT know a node's exact "
            "name: matches free text against names, concept labels, aliases, and "
            "property text; returns ranked matches. Use before memory_recall whenever "
            "the exact name is uncertain ('the db locking thing', 'that decision about "
            "saving'), or to check whether the graph knows anything about a topic. "
            "Search finds doors; memory_recall explores rooms."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Free-text query"},
                "model": {
                    "type": "string",
                    "description": "Optional filter: a resource model or concept type",
                },
                "limit": {"type": "integer", "description": "Max matches (default 5)", "default": 5},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="memory_recall",
        description=(
            "Recall all relevant context for a resource. Returns the resource's properties, "
            "all linked resources (with their properties), and optionally follows links to "
            "depth 2 for multi-hop context discovery."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Resource model type"},
                "name": {"type": "string", "description": "Resource name"},
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth (1 = direct links, 2 = two hops). Default: 1",
                    "default": 1,
                },
            },
            "required": ["model", "name"],
        },
    ),
    Tool(
        name="memory_forget",
        description="Soft-delete a resource by marking it as invalidated. The data is preserved for provenance.",
        inputSchema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Resource model type"},
                "name": {"type": "string", "description": "Resource name"},
                "reason": {"type": "string", "description": "Reason for forgetting"},
            },
            "required": ["model", "name", "reason"],
        },
    ),
    Tool(
        name="memory_query",
        description=(
            "Execute a SPARQL query against the memory graph. "
            "Prefixes rdf, rdfs, xsd, mem are pre-loaded. "
            "Returns JSON for SELECT, N-Triples for CONSTRUCT, boolean for ASK."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sparql": {
                    "type": "string",
                    "description": "SPARQL query (SELECT, CONSTRUCT, or ASK). Prefixes rdf, rdfs, xsd, mem are pre-loaded.",
                }
            },
            "required": ["sparql"],
        },
    ),
    Tool(
        name="memory_reflect",
        description=(
            "Get diagnostics about the memory graph: resource counts by model, "
            "concept counts, link counts, available relations in the ontology, "
            "and recently added resources."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Optional: filter by resource model type",
                }
            },
        },
    ),
]


_MUTATING = {
    "memory_store_resource",
    "memory_store_concept",
    "memory_link",
    "memory_unlink",
    "memory_forget",
}


def _client_id(server: Server) -> str | None:
    """Identify the writing client for mem:capturedBy provenance —
    the MCP client's declared name/version, or MEMORY_GRAPH_CLIENT."""
    try:
        info = server.request_context.session.client_params.clientInfo
        return f"{info.name}/{info.version}" if info.version else info.name
    except Exception:
        return os.environ.get("MEMORY_GRAPH_CLIENT")


def register(server: Server, mem_store: MemoryStore) -> None:
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            mem_store.capture_client = _client_id(server)
            text = _dispatch(mem_store, name, arguments)
            if name in _MUTATING:
                mem_store.save()
        except Exception as exc:
            text = f"Error: {exc}"
        return [TextContent(type="text", text=text)]


def _dispatch(store: MemoryStore, name: str, args: dict) -> str:
    if name == "memory_store_resource":
        return store_resource.handle_resource(
            store, args["model"], args["properties"], bool(args.get("force"))
        )

    if name == "memory_store_concept":
        return store_resource.handle_concept(
            store,
            args["concept_type"],
            args["label"],
            args.get("properties") or {},
        )

    if name == "memory_link":
        return link.handle_link(
            store,
            args["source_model"],
            args["source_name"],
            args["target_model"],
            args["target_name"],
            args["relation"],
            args.get("metadata") or {},
            args.get("new_relation_description"),
            args.get("new_relation_verb_forms"),
        )

    if name == "memory_unlink":
        return link.handle_unlink(
            store,
            args["source_model"],
            args["source_name"],
            args["target_model"],
            args["target_name"],
            args["relation"],
        )

    if name == "memory_search":
        return search.handle(
            store, args["text"], args.get("model"), args.get("limit") or 5
        )

    if name == "memory_recall":
        return recall.handle(store, args["model"], args["name"], args.get("depth") or 1)

    if name == "memory_forget":
        return forget.handle(store, args["model"], args["name"], args["reason"])

    if name == "memory_query":
        return query.handle(store, args["sparql"])

    if name == "memory_reflect":
        return reflect.handle(store, args.get("model"))

    raise ValueError(f"Unknown tool: {name}")
