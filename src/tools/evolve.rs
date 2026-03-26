use oxigraph::model::{GraphName, Literal, Quad};
use rmcp::model::CallToolResult;

use crate::namespaces::{self, GRAPH_KNOWLEDGE, GRAPH_SCHEMA, MEM, RDF, RDFS};
use crate::ontology;
use crate::store::{MemoryStore, StoreError};
use crate::util;

pub fn handle(
    store: &MemoryStore,
    name: String,
    description: String,
    domain: String,
    range: String,
    apply: bool,
) -> Result<CallToolResult, StoreError> {
    // Validate domain and range are valid node types
    if !ontology::is_valid_node_type(&domain) {
        return Ok(CallToolResult::error(vec![rmcp::model::Content::text(
            format!("Invalid domain type '{}'. Valid types: {:?}", domain, ontology::VALID_NODE_TYPES),
        )]));
    }
    if !ontology::is_valid_node_type(&range) {
        return Ok(CallToolResult::error(vec![rmcp::model::Content::text(
            format!("Invalid range type '{}'. Valid types: {:?}", range, ontology::VALID_NODE_TYPES),
        )]));
    }

    let prop_iri = namespaces::named_node(MEM, &name);
    let knowledge_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_KNOWLEDGE));

    // Record the proposal as a node in knowledge graph
    let proposal_iri = util::new_node_iri();
    let rdf_type = namespaces::named_node(RDF, "type");
    let proposal_type = namespaces::named_node(MEM, "SchemaProposal");
    let name_pred = namespaces::named_node(MEM, "label");
    let desc_pred = namespaces::named_node(MEM, "description");
    let status_pred = namespaces::named_node(MEM, "proposalStatus");
    let created_pred = namespaces::named_node(MEM, "createdAt");
    let def_pred = namespaces::named_node(MEM, "proposedProperty");

    let status = if apply { "accepted" } else { "proposed" };

    store.insert_many(&[
        Quad::new(proposal_iri.clone(), rdf_type.clone(), proposal_type, knowledge_graph.clone()),
        Quad::new(proposal_iri.clone(), name_pred, Literal::new_simple_literal(&name), knowledge_graph.clone()),
        Quad::new(proposal_iri.clone(), desc_pred, Literal::new_simple_literal(&description), knowledge_graph.clone()),
        Quad::new(proposal_iri.clone(), status_pred, Literal::new_simple_literal(status), knowledge_graph.clone()),
        Quad::new(proposal_iri.clone(), created_pred, util::now_literal(), knowledge_graph.clone()),
        Quad::new(proposal_iri.clone(), def_pred, prop_iri.clone(), knowledge_graph),
    ])?;

    if apply {
        // Insert the property definition into the schema graph
        let schema_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_SCHEMA));
        let rdfs_label = namespaces::named_node(RDFS, "label");
        let rdfs_comment = namespaces::named_node(RDFS, "comment");
        let rdfs_domain = namespaces::named_node(RDFS, "domain");
        let rdfs_range = namespaces::named_node(RDFS, "range");
        let domain_node = namespaces::named_node(MEM, &domain);
        let range_node = namespaces::named_node(MEM, &range);

        store.insert_many(&[
            Quad::new(prop_iri.clone(), rdf_type, namespaces::named_node(RDF, "Property"), schema_graph.clone()),
            Quad::new(prop_iri.clone(), rdfs_label, Literal::new_simple_literal(&name), schema_graph.clone()),
            Quad::new(prop_iri.clone(), rdfs_comment, Literal::new_simple_literal(&description), schema_graph.clone()),
            Quad::new(prop_iri.clone(), rdfs_domain, domain_node, schema_graph.clone()),
            Quad::new(prop_iri.clone(), rdfs_range, range_node, schema_graph),
        ])?;

        Ok(CallToolResult::success(vec![rmcp::model::Content::text(
            format!("Edge type '{}' proposed and applied. Property: {}\nProposal: {}", name, prop_iri.as_str(), proposal_iri.as_str()),
        )]))
    } else {
        Ok(CallToolResult::success(vec![rmcp::model::Content::text(
            format!("Edge type '{}' proposed (not yet applied). Proposal: {}", name, proposal_iri.as_str()),
        )]))
    }
}
