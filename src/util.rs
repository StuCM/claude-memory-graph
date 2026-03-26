use chrono::Utc;
use oxigraph::model::{Literal, NamedNode};
use uuid::Uuid;

use crate::namespaces::{MEM, XSD};

pub fn new_node_iri() -> NamedNode {
    let id = Uuid::new_v4();
    NamedNode::new(format!("{MEM}node/{id}")).expect("Invalid IRI")
}

pub fn new_reification_iri() -> NamedNode {
    let id = Uuid::new_v4();
    NamedNode::new(format!("{MEM}reification/{id}")).expect("Invalid IRI")
}

pub fn now_literal() -> Literal {
    let now = Utc::now().to_rfc3339();
    Literal::new_typed_literal(now, NamedNode::new(format!("{XSD}dateTime")).unwrap())
}
