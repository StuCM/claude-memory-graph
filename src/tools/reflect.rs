use oxigraph::sparql::QueryResults;
use rmcp::model::CallToolResult;

use crate::namespaces::GRAPH_KNOWLEDGE;
use crate::store::{MemoryStore, StoreError};

pub fn handle(
    store: &MemoryStore,
    _project: Option<String>,
) -> Result<CallToolResult, StoreError> {
    let mut report = String::new();

    // Node counts by type
    report.push_str("## Node Counts by Type\n\n");
    let sparql = format!(
        r#"SELECT ?type (COUNT(?node) as ?count) WHERE {{
            GRAPH <{GRAPH_KNOWLEDGE}> {{
                ?node rdf:type ?type .
            }}
        }} GROUP BY ?type ORDER BY DESC(?count)"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        for solution in solutions.flatten() {
            let type_val = solution
                .get("type")
                .map(|t| t.to_string())
                .unwrap_or_default();
            let count = solution
                .get("count")
                .map(|c| c.to_string())
                .unwrap_or_default();
            report.push_str(&format!("- {type_val}: {count}\n"));
        }
    }

    // Total relationships
    report.push_str("\n## Relationship Counts\n\n");
    let sparql = format!(
        r#"SELECT ?pred (COUNT(*) as ?count) WHERE {{
            GRAPH <{GRAPH_KNOWLEDGE}> {{
                ?s ?pred ?o .
                FILTER(?pred != rdf:type)
                FILTER(?pred != mem:name)
                FILTER(?pred != mem:label)
                FILTER(?pred != mem:createdAt)
                FILTER(?pred != mem:updatedAt)
                FILTER(?pred != mem:description)
            }}
        }} GROUP BY ?pred ORDER BY DESC(?count)"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        for solution in solutions.flatten() {
            let pred = solution
                .get("pred")
                .map(|p| p.to_string())
                .unwrap_or_default();
            let count = solution
                .get("count")
                .map(|c| c.to_string())
                .unwrap_or_default();
            report.push_str(&format!("- {pred}: {count}\n"));
        }
    }

    // Orphan nodes (no outgoing or incoming relationships beyond type/name/timestamps)
    report.push_str("\n## Orphan Nodes (no relationships)\n\n");
    let sparql = format!(
        r#"SELECT ?node ?type ?name WHERE {{
            GRAPH <{GRAPH_KNOWLEDGE}> {{
                ?node rdf:type ?type .
                OPTIONAL {{ ?node mem:name ?n }}
                OPTIONAL {{ ?node mem:label ?l }}
                BIND(COALESCE(?n, ?l, "unnamed") AS ?name)
                FILTER NOT EXISTS {{
                    GRAPH <{GRAPH_KNOWLEDGE}> {{
                        {{ ?node ?rel ?other . FILTER(?rel != rdf:type && ?rel != mem:name && ?rel != mem:label && ?rel != mem:createdAt && ?rel != mem:updatedAt && ?rel != mem:description) }}
                        UNION
                        {{ ?other ?rel2 ?node . FILTER(?rel2 != rdf:type) }}
                    }}
                }}
            }}
        }} LIMIT 20"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        let mut count = 0;
        for solution in solutions.flatten() {
            let node = solution.get("node").map(|n| n.to_string()).unwrap_or_default();
            let name = solution.get("name").map(|n| n.to_string()).unwrap_or_default();
            report.push_str(&format!("- {name} ({node})\n"));
            count += 1;
        }
        if count == 0 {
            report.push_str("None\n");
        }
    }

    // Recently added (last 10)
    report.push_str("\n## Recently Added\n\n");
    let sparql = format!(
        r#"SELECT ?node ?type ?name ?created WHERE {{
            GRAPH <{GRAPH_KNOWLEDGE}> {{
                ?node rdf:type ?type .
                ?node mem:createdAt ?created .
                OPTIONAL {{ ?node mem:name ?n }}
                OPTIONAL {{ ?node mem:label ?l }}
                BIND(COALESCE(?n, ?l, "unnamed") AS ?name)
            }}
        }} ORDER BY DESC(?created) LIMIT 10"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        for solution in solutions.flatten() {
            let name = solution.get("name").map(|n| n.to_string()).unwrap_or_default();
            let type_val = solution.get("type").map(|t| t.to_string()).unwrap_or_default();
            let created = solution.get("created").map(|c| c.to_string()).unwrap_or_default();
            report.push_str(&format!("- {name} ({type_val}) — {created}\n"));
        }
    }

    if report.is_empty() {
        report = "Memory graph is empty.".to_string();
    }

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        report,
    )]))
}
