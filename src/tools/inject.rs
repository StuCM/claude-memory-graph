use oxigraph::model::{GraphName, Literal, NamedNode, Quad};
use rmcp::model::CallToolResult;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::namespaces::{self, GRAPH_INJECTED, GRAPH_PROVENANCE, MEM, PROV, RDF};
use crate::store::{MemoryStore, StoreError};
use crate::util;

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct TripleInput {
    /// Subject IRI
    pub subject: String,
    /// Predicate IRI
    pub predicate: String,
    /// Object (IRI or literal value)
    pub object: String,
    /// If true, object is a literal string. If false, it's an IRI.
    #[serde(default = "default_true")]
    pub object_is_literal: bool,
}

fn default_true() -> bool {
    true
}

pub fn handle(
    store: &MemoryStore,
    source_label: String,
    triples: Vec<TripleInput>,
) -> Result<CallToolResult, StoreError> {
    let injected_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_INJECTED));
    let provenance_graph = GraphName::NamedNode(namespaces::graph_node(GRAPH_PROVENANCE));

    // Create injection provenance node
    let injection_iri = util::new_node_iri();
    let rdf_type = namespaces::named_node(RDF, "type");
    let injection_type = namespaces::named_node(MEM, "Injection");
    let source_pred = namespaces::named_node(MEM, "source");
    let created_pred = namespaces::named_node(MEM, "createdAt");

    store.insert_many(&[
        Quad::new(injection_iri.clone(), rdf_type, injection_type, provenance_graph.clone()),
        Quad::new(
            injection_iri.clone(),
            source_pred,
            Literal::new_simple_literal(&source_label),
            provenance_graph.clone(),
        ),
        Quad::new(injection_iri.clone(), created_pred, util::now_literal(), provenance_graph),
    ])?;

    let mut count = 0;
    let prov_generated = namespaces::named_node(PROV, "wasGeneratedBy");

    for triple in &triples {
        let subject =
            NamedNode::new(&triple.subject).map_err(|e| StoreError::Other(e.to_string()))?;
        let predicate =
            NamedNode::new(&triple.predicate).map_err(|e| StoreError::Other(e.to_string()))?;

        let quad = if triple.object_is_literal {
            Quad::new(
                subject.clone(),
                predicate,
                Literal::new_simple_literal(&triple.object),
                injected_graph.clone(),
            )
        } else {
            let object =
                NamedNode::new(&triple.object).map_err(|e| StoreError::Other(e.to_string()))?;
            Quad::new(subject.clone(), predicate, object, injected_graph.clone())
        };

        store.insert(&quad)?;

        // Link to provenance
        store.insert(&Quad::new(
            subject,
            prov_generated.clone(),
            injection_iri.clone(),
            injected_graph.clone(),
        ))?;

        count += 1;
    }

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        format!(
            "Injected {count} triples from '{source_label}'. Provenance: {}",
            injection_iri.as_str()
        ),
    )]))
}
