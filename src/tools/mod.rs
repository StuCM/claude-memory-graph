use std::collections::HashMap;
use std::sync::Arc;

use rmcp::handler::server::tool::ToolRouter;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ServerCapabilities, ServerInfo};
use rmcp::{tool, tool_handler, tool_router, ErrorData as McpError, ServerHandler};
use schemars::JsonSchema;
use serde::Deserialize;

use crate::store::MemoryStore;

pub mod evolve;
pub mod forget;
pub mod inject;
pub mod link;
pub mod query;
pub mod reflect;
pub mod store_node;

#[derive(Clone)]
pub struct MemoryGraphServer {
    store: Arc<MemoryStore>,
    tool_router: ToolRouter<Self>,
}

impl MemoryGraphServer {
    pub fn new(store: Arc<MemoryStore>) -> Self {
        Self {
            store,
            tool_router: Self::tool_router(),
        }
    }
}

// --- Parameter structs ---

#[derive(Debug, Deserialize, JsonSchema)]
pub struct StoreNodeParams {
    /// Node type: Person, Project, Component, Resource, Technology, Concept, Decision, Problem, Change, Preference, Constraint, Pattern
    pub node_type: String,
    /// The name/label for this node
    pub name: String,
    /// Optional properties as key-value pairs (e.g. description, path, url, role, etc.)
    pub properties: Option<HashMap<String, String>>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct QueryParams {
    /// SPARQL query (SELECT, CONSTRUCT, or ASK)
    pub sparql: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct LinkParams {
    /// IRI of the source node
    pub source_iri: String,
    /// IRI of the target node
    pub target_iri: String,
    /// Relationship name (e.g. 'partOf') or full IRI
    pub relation: String,
    /// Whether to reify this relationship with metadata
    pub reify: Option<bool>,
    /// Optional metadata for reified relationships (e.g. rationale, confidence)
    pub metadata: Option<HashMap<String, String>>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct UnlinkParams {
    /// IRI of the source node
    pub source_iri: String,
    /// IRI of the target node
    pub target_iri: String,
    /// Relationship name or full IRI
    pub relation: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ForgetParams {
    /// IRI of the node to invalidate
    pub node_iri: String,
    /// Reason for invalidation
    pub reason: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ReflectParams {
    /// Optional project path to filter results
    pub project: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct EvolveEdgeParams {
    /// Name for the new relationship (e.g. 'blockedBy')
    pub name: String,
    /// Description of what this relationship means
    pub description: String,
    /// Domain node type (e.g. 'Problem')
    pub domain: String,
    /// Range node type (e.g. 'Constraint')
    pub range: String,
    /// Whether to apply immediately (true) or just record as proposal (false)
    pub apply: Option<bool>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct InjectParams {
    /// Source label (e.g. 'README.md', 'architecture doc')
    pub source_label: String,
    /// Triples to insert, each with subject, predicate, object IRIs/literals
    pub triples: Vec<inject::TripleInput>,
}

// --- Tool implementations ---

#[tool_router]
impl MemoryGraphServer {
    #[tool(
        name = "memory_store_node",
        description = "Insert or update a node in the memory graph. If a node with matching type+name already exists, its properties are updated. Returns the node IRI."
    )]
    async fn memory_store_node(
        &self,
        params: Parameters<StoreNodeParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        store_node::handle(&self.store, p.node_type, p.name, p.properties)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_query",
        description = "Execute a SPARQL query against the memory graph. Standard prefixes (rdf, rdfs, xsd, skos, prov, foaf, dc, dct, doap, mem) are pre-loaded. Returns JSON for SELECT, Turtle for CONSTRUCT, boolean for ASK."
    )]
    async fn memory_query(
        &self,
        params: Parameters<QueryParams>,
    ) -> Result<CallToolResult, McpError> {
        query::handle(&self.store, params.0.sparql)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_link",
        description = "Create a relationship between two nodes. Use built-in relations (partOf, contains, uses, responsibleFor, worksOn, prefers, madeBy, resolves, causes, implements, supersedes, affects, relatesTo, about, appliesTo, instanceOf, documentedIn) or any custom relation IRI."
    )]
    async fn memory_link(
        &self,
        params: Parameters<LinkParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        link::handle_link(
            &self.store,
            p.source_iri,
            p.target_iri,
            p.relation,
            p.reify.unwrap_or(false),
            p.metadata,
        )
        .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_unlink",
        description = "Remove a relationship between two nodes."
    )]
    async fn memory_unlink(
        &self,
        params: Parameters<UnlinkParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        link::handle_unlink(&self.store, p.source_iri, p.target_iri, p.relation)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_forget",
        description = "Soft-delete a node by marking it as invalidated. The node and its triples are preserved for provenance."
    )]
    async fn memory_forget(
        &self,
        params: Parameters<ForgetParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        forget::handle(&self.store, p.node_iri, p.reason)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_reflect",
        description = "Get diagnostics about the memory graph: node counts by type, relationship counts, orphan nodes, stale nodes, recently added, and suggested missing links."
    )]
    async fn memory_reflect(
        &self,
        params: Parameters<ReflectParams>,
    ) -> Result<CallToolResult, McpError> {
        reflect::handle(&self.store, params.0.project)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_evolve_edge",
        description = "Propose a new relationship type for the memory graph. Node types are fixed, but new edge types can be added."
    )]
    async fn memory_evolve_edge(
        &self,
        params: Parameters<EvolveEdgeParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        evolve::handle(
            &self.store,
            p.name,
            p.description,
            p.domain,
            p.range,
            p.apply.unwrap_or(false),
        )
        .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_inject",
        description = "Bulk-insert structured triples from external content into the injected knowledge graph."
    )]
    async fn memory_inject(
        &self,
        params: Parameters<InjectParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        inject::handle(&self.store, p.source_label, p.triples)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }
}

#[tool_handler]
impl ServerHandler for MemoryGraphServer {
    fn get_info(&self) -> ServerInfo {
        let mut info = ServerInfo::default();
        info.instructions = Some(
            "RDF-based long-term memory graph for Claude Code. \
            Stores granular knowledge nodes (Person, Project, Component, Resource, Technology, Concept, \
            Decision, Problem, Change, Preference, Constraint, Pattern) connected by typed relationships. \
            Use memory_store_node to create/update nodes, memory_link to connect them, \
            memory_query with SPARQL to search, memory_reflect for diagnostics, \
            memory_evolve_edge to add new relationship types, and memory_inject for external knowledge."
                .into(),
        );
        info.capabilities = ServerCapabilities::builder().enable_tools().build();
        info
    }
}
