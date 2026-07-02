import pyoxigraph as ox

MEM = "https://memory.claude.local/ontology#"
XSD = "http://www.w3.org/2001/XMLSchema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"

GRAPH_SCHEMA = "https://memory.claude.local/graph/schema"
GRAPH_LINKS = "https://memory.claude.local/graph/links"
GRAPH_CONCEPTS = "https://memory.claude.local/graph/concepts"
GRAPH_RESOURCE_BASE = "https://memory.claude.local/graph/resource/"

SPARQL_PREFIXES = (
    "PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>\n"
    "PREFIX mem:  <https://memory.claude.local/ontology#>\n"
)

RDF_TYPE = ox.NamedNode(f"{RDF}type")
XSD_STRING = ox.NamedNode(f"{XSD}string")
XSD_DATETIME = ox.NamedNode(f"{XSD}dateTime")
XSD_BOOLEAN = ox.NamedNode(f"{XSD}boolean")


def mem_node(local: str) -> ox.NamedNode:
    return ox.NamedNode(f"{MEM}{local}")


def resource_graph_node(uuid_str: str) -> ox.NamedNode:
    return ox.NamedNode(f"{GRAPH_RESOURCE_BASE}{uuid_str}")
