use rmcp::model::{CallToolResult, Content};
use serde_json::json;

use crate::store::{MemoryStore, StoreError};

pub fn handle(
    store: &MemoryStore,
    model: String,
    name: String,
    depth: u32,
) -> Result<CallToolResult, StoreError> {
    let (graph_id, iri) = store
        .find_resource(&model, &name)?
        .ok_or_else(|| StoreError::Other(format!("{model} '{name}' not found")))?;

    let result = store.recall(&iri, &graph_id, depth)?;

    let linked: Vec<_> = result
        .linked
        .iter()
        .map(|lr| {
            json!({
                "model": lr.model,
                "relation": lr.relation,
                "direction": lr.direction,
                "properties": lr.properties,
            })
        })
        .collect();

    let output = json!({
        "iri": result.iri.as_str(),
        "model": result.model,
        "properties": result.properties,
        "linked_resources": linked,
    });

    Ok(CallToolResult::success(vec![Content::text(
        serde_json::to_string_pretty(&output)
            .unwrap_or_else(|_| format!("{output:?}")),
    )]))
}
