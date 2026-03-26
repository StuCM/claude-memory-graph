use chrono::Utc;
use oxigraph::model::{Literal, NamedNode};
use uuid::Uuid;

use crate::namespaces::{self, MEM, XSD};

/// Generate a new UUID-based IRI for a resource instance root node.
pub fn new_resource_iri() -> (String, NamedNode) {
    let id = Uuid::new_v4().to_string();
    let iri = NamedNode::new(format!("{MEM}resource/{id}")).expect("Invalid IRI");
    (id, iri)
}

/// Generate a new UUID-based IRI for a concept node.
pub fn new_concept_iri() -> NamedNode {
    let id = Uuid::new_v4();
    NamedNode::new(format!("{MEM}concept/{id}")).expect("Invalid IRI")
}

/// Generate a new UUID-based IRI for a cross-link.
pub fn new_link_iri() -> NamedNode {
    let id = Uuid::new_v4();
    NamedNode::new(format!("{MEM}link/{id}")).expect("Invalid IRI")
}

/// Get the resource graph IRI for a given resource ID.
pub fn resource_graph(id: &str) -> NamedNode {
    namespaces::resource_graph_iri(id)
}

pub fn now_literal() -> Literal {
    let now = Utc::now().to_rfc3339();
    Literal::new_typed_literal(now, NamedNode::new(format!("{XSD}dateTime")).unwrap())
}
