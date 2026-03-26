use std::collections::HashMap;
use std::sync::Arc;

use rmcp::handler::server::tool::ToolRouter;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ServerCapabilities, ServerInfo};
use rmcp::{tool, tool_handler, tool_router, ErrorData as McpError, ServerHandler};
use schemars::JsonSchema;
use serde::Deserialize;

use crate::store::MemoryStore;

pub mod forget;
pub mod link;
pub mod query;
pub mod recall;
pub mod reflect;
pub mod store_resource;

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
pub struct StoreResourceParams {
    /// Resource model: Person, Project, Company, Task, Technology, Decision, Pattern
    pub model: String,
    /// Scalar properties as key-value pairs (e.g. name, email, role, description)
    pub properties: HashMap<String, String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct StoreConceptParams {
    /// Concept type: Skill, Concept, Constraint, Preference
    pub concept_type: String,
    /// Label for this concept
    pub label: String,
    /// Optional properties (e.g. description, proficiency)
    pub properties: Option<HashMap<String, String>>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct LinkParams {
    /// Name of the source resource (looked up by model+name)
    pub source_model: String,
    pub source_name: String,
    /// Name of the target resource (looked up by model+name)
    pub target_model: String,
    pub target_name: String,
    /// Relationship type (e.g. worksOn, uses, employedBy, assignedTo)
    pub relation: String,
    /// Optional metadata on the link (e.g. since, role)
    pub metadata: Option<HashMap<String, String>>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct UnlinkParams {
    pub source_model: String,
    pub source_name: String,
    pub target_model: String,
    pub target_name: String,
    pub relation: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct RecallParams {
    /// Resource model type
    pub model: String,
    /// Resource name
    pub name: String,
    /// Traversal depth (1 = direct links, 2 = two hops). Default: 1
    pub depth: Option<u32>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ForgetParams {
    /// Resource model type
    pub model: String,
    /// Resource name
    pub name: String,
    /// Reason for forgetting
    pub reason: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct QueryParams {
    /// SPARQL query (SELECT, CONSTRUCT, or ASK). Prefixes rdf, rdfs, xsd, mem are pre-loaded.
    pub sparql: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ReflectParams {
    /// Optional: filter by resource model type
    pub model: Option<String>,
}

// --- Tool implementations ---

#[tool_router]
impl MemoryGraphServer {
    #[tool(
        name = "memory_store_resource",
        description = "Create or update a resource instance (Person, Project, Company, Task, Technology, Decision, Pattern). Each resource gets its own named graph. If a resource with matching model+name exists, its properties are updated."
    )]
    async fn memory_store_resource(
        &self,
        params: Parameters<StoreResourceParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        store_resource::handle_resource(&self.store, p.model, p.properties)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_store_concept",
        description = "Create a shared concept node (Skill, Concept, Constraint, Preference). Concepts are lightweight shared nodes that enable traversal between resource graphs."
    )]
    async fn memory_store_concept(
        &self,
        params: Parameters<StoreConceptParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        store_resource::handle_concept(
            &self.store,
            p.concept_type,
            p.label,
            p.properties.unwrap_or_default(),
        )
        .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_link",
        description = "Create a cross-graph relationship between two resources. Valid relations: worksOn, employedBy, owns, uses, madeBy, affects, assignedTo, partOf, relatesTo, supersedes, resolves, appliesTo, hasSkill, hasConcept, hasConstraint, hasPreference."
    )]
    async fn memory_link(
        &self,
        params: Parameters<LinkParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        link::handle_link(
            &self.store,
            &p.source_model,
            &p.source_name,
            &p.target_model,
            &p.target_name,
            &p.relation,
            &p.metadata.unwrap_or_default(),
        )
        .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_unlink",
        description = "Remove a cross-graph relationship between two resources."
    )]
    async fn memory_unlink(
        &self,
        params: Parameters<UnlinkParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        link::handle_unlink(
            &self.store,
            &p.source_model,
            &p.source_name,
            &p.target_model,
            &p.target_name,
            &p.relation,
        )
        .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_recall",
        description = "Recall all relevant context for a resource. Returns the resource's properties, all linked resources (with their properties), and optionally follows links to depth 2 for multi-hop context discovery."
    )]
    async fn memory_recall(
        &self,
        params: Parameters<RecallParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        recall::handle(&self.store, p.model, p.name, p.depth.unwrap_or(1))
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_forget",
        description = "Soft-delete a resource by marking it as invalidated. The data is preserved for provenance."
    )]
    async fn memory_forget(
        &self,
        params: Parameters<ForgetParams>,
    ) -> Result<CallToolResult, McpError> {
        let p = params.0;
        forget::handle(&self.store, p.model, p.name, p.reason)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_query",
        description = "Execute a SPARQL query against the memory graph. Prefixes rdf, rdfs, xsd, mem are pre-loaded. Returns JSON for SELECT, N-Triples for CONSTRUCT, boolean for ASK."
    )]
    async fn memory_query(
        &self,
        params: Parameters<QueryParams>,
    ) -> Result<CallToolResult, McpError> {
        query::handle(&self.store, params.0.sparql)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }

    #[tool(
        name = "memory_reflect",
        description = "Get diagnostics about the memory graph: resource counts by model, concept counts, link counts, and recently added resources."
    )]
    async fn memory_reflect(
        &self,
        params: Parameters<ReflectParams>,
    ) -> Result<CallToolResult, McpError> {
        reflect::handle(&self.store, params.0.model)
            .map_err(|e| McpError::internal_error(e.to_string(), None))
    }
}

#[tool_handler]
impl ServerHandler for MemoryGraphServer {
    fn get_info(&self) -> ServerInfo {
        let mut info = ServerInfo::default();
        info.instructions = Some(
            "Arches-inspired knowledge graph for Claude Code long-term memory. \
            Each resource (Person, Project, Company, Task, Technology, Decision, Pattern) \
            is its own named graph with scalar properties. Shared concepts (Skill, Concept, \
            Constraint, Preference) enable multi-hop traversal between resources. \
            Use memory_store_resource to create entities, memory_link to connect them, \
            memory_recall to retrieve context with traversal, and memory_query for SPARQL."
                .into(),
        );
        info.capabilities = ServerCapabilities::builder().enable_tools().build();
        info
    }
}
