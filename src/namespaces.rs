use oxigraph::model::NamedNode;

pub const MEM: &str = "https://memory.claude.local/ontology#";
pub const RDF: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
pub const RDFS: &str = "http://www.w3.org/2000/01/rdf-schema#";
pub const XSD: &str = "http://www.w3.org/2001/XMLSchema#";
pub const PROV: &str = "http://www.w3.org/ns/prov#";

#[allow(dead_code)]
pub const SKOS: &str = "http://www.w3.org/2004/02/skos/core#";
#[allow(dead_code)]
pub const FOAF: &str = "http://xmlns.com/foaf/0.1/";
#[allow(dead_code)]
pub const DC: &str = "http://purl.org/dc/elements/1.1/";
#[allow(dead_code)]
pub const DCT: &str = "http://purl.org/dc/terms/";
#[allow(dead_code)]
pub const DOAP: &str = "http://usefulinc.com/ns/doap#";

// Named graph IRIs
pub const GRAPH_SCHEMA: &str = "https://memory.claude.local/graph/schema";
pub const GRAPH_KNOWLEDGE: &str = "https://memory.claude.local/graph/knowledge";
pub const GRAPH_PROVENANCE: &str = "https://memory.claude.local/graph/provenance";
pub const GRAPH_INJECTED: &str = "https://memory.claude.local/graph/injected";

pub const SPARQL_PREFIXES: &str = "\
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX dc:   <http://purl.org/dc/elements/1.1/>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX doap: <http://usefulinc.com/ns/doap#>
PREFIX mem:  <https://memory.claude.local/ontology#>
";

pub fn named_node(namespace: &str, local: &str) -> NamedNode {
    NamedNode::new(format!("{namespace}{local}")).expect("Invalid IRI")
}

pub fn graph_node(graph: &str) -> NamedNode {
    NamedNode::new(graph).expect("Invalid graph IRI")
}
