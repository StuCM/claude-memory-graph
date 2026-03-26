use oxigraph::sparql::QueryResults;
use rmcp::model::{CallToolResult, Content};

use crate::namespaces::{GRAPH_CONCEPTS, GRAPH_LINKS, GRAPH_RESOURCE_BASE};
use crate::store::{MemoryStore, StoreError};

pub fn handle(
    store: &MemoryStore,
    model_filter: Option<String>,
) -> Result<CallToolResult, StoreError> {
    let mut report = String::new();

    // Resource counts by model
    report.push_str("## Resources by Model\n\n");
    let type_filter = model_filter
        .as_deref()
        .map(|m| format!("FILTER(?type = mem:{m})"))
        .unwrap_or_default();
    let sparql = format!(
        r#"SELECT ?type (COUNT(DISTINCT ?node) as ?count) WHERE {{
            GRAPH ?g {{
                ?node rdf:type ?type .
            }}
            FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))
            {type_filter}
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

    // Concept counts
    report.push_str("\n## Concepts\n\n");
    let sparql = format!(
        r#"SELECT ?type (COUNT(?node) as ?count) WHERE {{
            GRAPH <{GRAPH_CONCEPTS}> {{
                ?node rdf:type ?type .
            }}
        }} GROUP BY ?type ORDER BY DESC(?count)"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        let mut any = false;
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
            any = true;
        }
        if !any {
            report.push_str("None\n");
        }
    }

    // Cross-link counts by relation
    report.push_str("\n## Cross-Links by Relation\n\n");
    let sparql = format!(
        r#"SELECT ?rel (COUNT(?link) as ?count) WHERE {{
            GRAPH <{GRAPH_LINKS}> {{
                ?link rdf:type mem:CrossLink .
                ?link mem:linkRelation ?rel .
            }}
        }} GROUP BY ?rel ORDER BY DESC(?count)"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        let mut any = false;
        for solution in solutions.flatten() {
            let rel = solution
                .get("rel")
                .map(|r| r.to_string())
                .unwrap_or_default();
            let count = solution
                .get("count")
                .map(|c| c.to_string())
                .unwrap_or_default();
            report.push_str(&format!("- {rel}: {count}\n"));
            any = true;
        }
        if !any {
            report.push_str("None\n");
        }
    }

    // Recently added resources
    report.push_str("\n## Recently Added Resources\n\n");
    let sparql = format!(
        r#"SELECT ?node ?type ?name ?created WHERE {{
            GRAPH ?g {{
                ?node rdf:type ?type .
                ?node mem:createdAt ?created .
                OPTIONAL {{ ?node mem:name ?n }}
                BIND(COALESCE(?n, "unnamed") AS ?name)
            }}
            FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))
        }} ORDER BY DESC(?created) LIMIT 10"#
    );
    if let Ok(QueryResults::Solutions(solutions)) = store.query(&sparql) {
        let mut any = false;
        for solution in solutions.flatten() {
            let name = solution
                .get("name")
                .map(|n| n.to_string())
                .unwrap_or_default();
            let type_val = solution
                .get("type")
                .map(|t| t.to_string())
                .unwrap_or_default();
            report.push_str(&format!("- {name} ({type_val})\n"));
            any = true;
        }
        if !any {
            report.push_str("None\n");
        }
    }

    if report.is_empty() {
        report = "Memory graph is empty.".to_string();
    }

    Ok(CallToolResult::success(vec![Content::text(report)]))
}
