use rmcp::model::{CallToolResult, Content};

use crate::store::{MemoryStore, StoreError};

pub fn handle(
    store: &MemoryStore,
    model: String,
    name: String,
    reason: String,
) -> Result<CallToolResult, StoreError> {
    let (graph_id, iri) = store
        .find_resource(&model, &name)?
        .ok_or_else(|| StoreError::Other(format!("{model} '{name}' not found")))?;

    store.forget_resource(&iri, &graph_id, &reason)?;

    Ok(CallToolResult::success(vec![Content::text(format!(
        "Invalidated {model} '{name}' — reason: {reason}"
    ))]))
}
