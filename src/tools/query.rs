use oxigraph::sparql::QueryResults;
use rmcp::model::CallToolResult;
use serde_json::{json, Value};

use crate::store::{MemoryStore, StoreError};

pub fn handle(store: &MemoryStore, sparql: String) -> Result<CallToolResult, StoreError> {
    let results = store.query(&sparql)?;

    let output = match results {
        QueryResults::Solutions(solutions) => {
            let variables: Vec<String> = solutions
                .variables()
                .iter()
                .map(|v| v.as_str().to_string())
                .collect();

            let mut rows: Vec<Value> = Vec::new();
            for solution in solutions {
                let solution = solution.map_err(|e| StoreError::Other(e.to_string()))?;
                let mut row = serde_json::Map::new();
                for var in &variables {
                    if let Some(term) = solution.get(var.as_str()) {
                        row.insert(var.clone(), json!(term.to_string()));
                    }
                }
                rows.push(Value::Object(row));
            }
            serde_json::to_string_pretty(&rows).unwrap_or_else(|_| "[]".to_string())
        }
        QueryResults::Boolean(b) => format!("{b}"),
        QueryResults::Graph(triples) => {
            let mut lines = Vec::new();
            for triple in triples {
                let triple = triple.map_err(|e| StoreError::Other(e.to_string()))?;
                lines.push(format!(
                    "{} {} {} .",
                    triple.subject, triple.predicate, triple.object
                ));
            }
            lines.join("\n")
        }
    };

    Ok(CallToolResult::success(vec![rmcp::model::Content::text(
        output,
    )]))
}
