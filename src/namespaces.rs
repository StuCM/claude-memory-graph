use oxigraph::model::NamedNode;

pub const MEM: &str = "https://memory.claude.local/ontology#";
pub const XSD: &str = "http://www.w3.org/2001/XMLSchema#";

// Named graph IRIs
pub const GRAPH_SCHEMA: &str = "https://memory.claude.local/graph/schema";
pub const GRAPH_LINKS: &str = "https://memory.claude.local/graph/links";
pub const GRAPH_CONCEPTS: &str = "https://memory.claude.local/graph/concepts";

/// Base IRI for resource instance graphs: {GRAPH_RESOURCE_BASE}{uuid}
pub const GRAPH_RESOURCE_BASE: &str = "https://memory.claude.local/graph/resource/";

pub const SPARQL_PREFIXES: &str = "\
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX mem:  <https://memory.claude.local/ontology#>
";

pub fn named_node(namespace: &str, local: &str) -> NamedNode {
    NamedNode::new(format!("{namespace}{local}")).expect("Invalid IRI")
}

pub fn graph_node(graph: &str) -> NamedNode {
    NamedNode::new(graph).expect("Invalid graph IRI")
}

/// Create a new resource instance graph IRI from a UUID.
pub fn resource_graph_iri(id: &str) -> NamedNode {
    NamedNode::new(format!("{GRAPH_RESOURCE_BASE}{id}")).expect("Invalid resource graph IRI")
}
