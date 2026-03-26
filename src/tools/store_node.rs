use std::collections::HashMap;

use oxigraph::model::{GraphName, Literal, Quad};
use rmcp::model::CallToolResult;

use crate::namespaces::{self, GRAPH_KNOWLEDGE, MEM};
use crate::ontology;
use crate::store::{MemoryStore, StoreError};
use crate::util;

pub fn handle(
    store: &MemoryStore,
    node_type: String,
    name: String,
    properties: Option<HashMap<String, String>>,
) -> Result<CallToolResult, StoreError> {
    if !ontology::is_valid_node_type(&node_type) {
        return Ok(CallToolResult::error(vec![rmcp::model::Content::text(
            format!(
                "Invalid node type '{}'. Valid types: {:?}",
                node_type,
                ontology::VALID_NODE_TYPES
            ),
        )]));
    }

    let knowledge_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_KNOWLEDGE));
    let name_prop = ontology::name_property_for_type(&node_type);

    // Check if node already exists
    let node_iri = match store.find_node_by_name(&node_type, &name)? {
        Some(existing) => {
            // Update properties on existing node
            if let Some(props) = &properties {
                for (key, value) in props {
                    let pred = namespaces::named_node(MEM, key);
                    // Remove old value if any, then insert new
                    let sparql = format!(
                        r#"DELETE WHERE {{
                            GRAPH <{graph}> {{
                                <{node}> <{pred}> ?old .
                            }}
                        }}"#,
                        graph = GRAPH_KNOWLEDGE,
                        node = existing.as_str(),
                        pred = pred.as_str(),
                    );
                    store.update(&sparql)?;
                    store.insert(&Quad::new(
                        existing.clone(),
                        pred,
                        Literal::new_simple_literal(value),
                        knowledge_graph.clone(),
                    ))?;
                }
                // Update timestamp
                let updated_pred = namespaces::named_node(MEM, "updatedAt");
                let sparql = format!(
                    r#"DELETE WHERE {{
                        GRAPH <{graph}> {{
                            <{node}> <{pred}> ?old .
                        }}
                    }}"#,
                    graph = GRAPH_KNOWLEDGE,
                    node = existing.as_str(),
                    pred = updated_pred.as_str(),
                );
                store.update(&sparql)?;
                store.insert(&Quad::new(
                    existing.clone(),
                    updated_pred,
                    util::now_literal(),
                    knowledge_graph.clone(),
                ))?;
            }
            existing
        }
        None => {
            // Create new node
            let iri = util::new_node_iri();
            let type_node = namespaces::named_node(MEM, &node_type);
            let rdf_type = namespaces::named_node(namespaces::RDF, "type");
            let name_pred = namespaces::named_node(MEM, name_prop);
            let created_pred = namespaces::named_node(MEM, "createdAt");
            let updated_pred = namespaces::named_node(MEM, "updatedAt");
            let now = util::now_literal();

            let mut quads = vec![
                Quad::new(
                    iri.clone(),
                    rdf_type,
                    type_node,
                    knowledge_graph.clone(),
                ),
                Quad::new(
                    iri.clone(),
                    name_pred,
                    Literal::new_simple_literal(&name),
                    knowledge_graph.clone(),
                ),
                Quad::new(
                    iri.clone(),
                    created_pred,
                    now.clone(),
                    knowledge_graph.clone(),
                ),
                Quad::new(
                    iri.clone(),
                    updated_pred,
                    now,
                    knowledge_graph.clone(),
                ),
            ];

            if let Some(props) = &properties {
                for (key, value) in props {
                    let pred = namespaces::named_node(MEM, key);
                    quads.push(Quad::new(
                        iri.clone(),
                        pred,
                        Literal::new_simple_literal(value),
                        knowledge_graph.clone(),
                    ));
                }
            }

            store.insert_many(&quads)?;
            iri
        }
    };

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        format!("Node stored: {}", node_iri.as_str()),
    )]))
}
