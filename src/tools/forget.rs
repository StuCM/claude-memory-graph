use oxigraph::model::{GraphName, Literal, NamedNode, Quad};
use rmcp::model::CallToolResult;

use crate::namespaces::{self, GRAPH_KNOWLEDGE, MEM, XSD};
use crate::store::{MemoryStore, StoreError};
use crate::util;

pub fn handle(
    store: &MemoryStore,
    node_iri: String,
    reason: String,
) -> Result<CallToolResult, StoreError> {
    let node = NamedNode::new(&node_iri).map_err(|e| StoreError::Other(e.to_string()))?;
    let knowledge_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_KNOWLEDGE));

    if !store.node_exists(&node)? {
        return Ok(CallToolResult::error(vec![rmcp::model::Content::text(
            format!("Node not found: {node_iri}"),
        )]));
    }

    let invalidated_pred = namespaces::named_node(MEM, "invalidated");
    let invalidated_at_pred = namespaces::named_node(MEM, "invalidatedAt");
    let reason_pred = namespaces::named_node(MEM, "invalidationReason");
    let xsd_boolean = NamedNode::new(format!("{XSD}boolean")).unwrap();

    // Remove any existing invalidated triple
    let sparql = format!(
        r#"DELETE WHERE {{
            GRAPH <{graph}> {{
                <{node}> <{pred}> ?old .
            }}
        }}"#,
        graph = GRAPH_KNOWLEDGE,
        node = node_iri,
        pred = invalidated_pred.as_str(),
    );
    store.update(&sparql)?;

    store.insert_many(&[
        Quad::new(
            node.clone(),
            invalidated_pred,
            Literal::new_typed_literal("true", xsd_boolean),
            knowledge_graph.clone(),
        ),
        Quad::new(
            node.clone(),
            invalidated_at_pred,
            util::now_literal(),
            knowledge_graph.clone(),
        ),
        Quad::new(
            node,
            reason_pred,
            Literal::new_simple_literal(&reason),
            knowledge_graph,
        ),
    ])?;

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        format!("Node invalidated: {node_iri}"),
    )]))
}
