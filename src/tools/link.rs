use std::collections::HashMap;

use oxigraph::model::{GraphName, Literal, NamedNode, Quad};
use rmcp::model::CallToolResult;

use crate::namespaces::{self, GRAPH_KNOWLEDGE, MEM, RDF};
use crate::store::{MemoryStore, StoreError};
use crate::util;

fn resolve_relation(relation: &str) -> NamedNode {
    if relation.starts_with("http://") || relation.starts_with("https://") {
        NamedNode::new(relation).expect("Invalid relation IRI")
    } else {
        namespaces::named_node(MEM, relation)
    }
}

pub fn handle_link(
    store: &MemoryStore,
    source_iri: String,
    target_iri: String,
    relation: String,
    reify: bool,
    metadata: Option<HashMap<String, String>>,
) -> Result<CallToolResult, StoreError> {
    let source = NamedNode::new(&source_iri).map_err(|e| StoreError::Other(e.to_string()))?;
    let target = NamedNode::new(&target_iri).map_err(|e| StoreError::Other(e.to_string()))?;
    let pred = resolve_relation(&relation);
    let knowledge_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_KNOWLEDGE));

    if !store.node_exists(&source)? {
        return Ok(CallToolResult::error(vec![rmcp::model::Content::text(
            format!("Source node not found: {source_iri}"),
        )]));
    }
    if !store.node_exists(&target)? {
        return Ok(CallToolResult::error(vec![rmcp::model::Content::text(
            format!("Target node not found: {target_iri}"),
        )]));
    }

    // Insert the direct triple
    store.insert(&Quad::new(
        source.clone(),
        pred.clone(),
        target.clone(),
        knowledge_graph.clone(),
    ))?;

    let mut result_text = format!("Linked: {} --{}--> {}", source_iri, relation, target_iri);

    // Optionally reify
    if reify {
        let reif_iri = util::new_reification_iri();
        let rdf_subject = namespaces::named_node(RDF, "subject");
        let rdf_predicate = namespaces::named_node(RDF, "predicate");
        let rdf_object = namespaces::named_node(RDF, "object");
        let rdf_type = namespaces::named_node(RDF, "type");
        let reified_type = namespaces::named_node(MEM, "ReifiedRelation");
        let created_pred = namespaces::named_node(MEM, "createdAt");

        let mut quads = vec![
            Quad::new(reif_iri.clone(), rdf_type, reified_type, knowledge_graph.clone()),
            Quad::new(reif_iri.clone(), rdf_subject, source, knowledge_graph.clone()),
            Quad::new(reif_iri.clone(), rdf_predicate, pred, knowledge_graph.clone()),
            Quad::new(reif_iri.clone(), rdf_object, target, knowledge_graph.clone()),
            Quad::new(reif_iri.clone(), created_pred, util::now_literal(), knowledge_graph.clone()),
        ];

        if let Some(meta) = metadata {
            for (key, value) in meta {
                let meta_pred = namespaces::named_node(MEM, &key);
                quads.push(Quad::new(
                    reif_iri.clone(),
                    meta_pred,
                    Literal::new_simple_literal(&value),
                    knowledge_graph.clone(),
                ));
            }
        }

        store.insert_many(&quads)?;
        result_text.push_str(&format!("\nReified as: {}", reif_iri.as_str()));
    }

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        result_text,
    )]))
}

pub fn handle_unlink(
    store: &MemoryStore,
    source_iri: String,
    target_iri: String,
    relation: String,
) -> Result<CallToolResult, StoreError> {
    let source = NamedNode::new(&source_iri).map_err(|e| StoreError::Other(e.to_string()))?;
    let target = NamedNode::new(&target_iri).map_err(|e| StoreError::Other(e.to_string()))?;
    let pred = resolve_relation(&relation);
    let knowledge_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_KNOWLEDGE));

    store.remove(&Quad::new(source, pred, target, knowledge_graph))?;

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        format!("Unlinked: {} --{}--> {}", source_iri, relation, target_iri),
    )]))
}
