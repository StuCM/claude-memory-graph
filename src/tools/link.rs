use std::collections::HashMap;

use oxigraph::model::NamedNode;
use rmcp::model::{CallToolResult, Content};

use crate::store::{MemoryStore, StoreError};

pub fn handle_link(
    store: &MemoryStore,
    source_model: &str,
    source_name: &str,
    target_model: &str,
    target_name: &str,
    relation: &str,
    metadata: &HashMap<String, String>,
) -> Result<CallToolResult, StoreError> {
    let source = find_any(store, source_model, source_name)?;
    let target = find_any(store, target_model, target_name)?;

    let link_iri = store.create_link(&source, &target, relation, metadata)?;

    Ok(CallToolResult::success(vec![Content::text(format!(
        "Linked {source_model}:'{source_name}' --{relation}--> {target_model}:'{target_name}'\nLink IRI: {}",
        link_iri.as_str()
    ))]))
}

pub fn handle_unlink(
    store: &MemoryStore,
    source_model: &str,
    source_name: &str,
    target_model: &str,
    target_name: &str,
    relation: &str,
) -> Result<CallToolResult, StoreError> {
    let source = find_any(store, source_model, source_name)?;
    let target = find_any(store, target_model, target_name)?;

    let removed = store.remove_link(&source, &target, relation)?;

    if removed {
        Ok(CallToolResult::success(vec![Content::text(format!(
            "Removed link: {source_model}:'{source_name}' --{relation}--> {target_model}:'{target_name}'"
        ))]))
    } else {
        Ok(CallToolResult::success(vec![Content::text(
            "No matching link found to remove.".to_string(),
        )]))
    }
}

/// Look up a resource or concept by model/type + name/label.
fn find_any(store: &MemoryStore, model: &str, name: &str) -> Result<NamedNode, StoreError> {
    if let Some((_, iri)) = store.find_resource(model, name)? {
        return Ok(iri);
    }
    if let Some(iri) = store.find_concept(model, name)? {
        return Ok(iri);
    }
    Err(StoreError::Other(format!(
        "{model} '{name}' not found. Create it first with memory_store_resource or memory_store_concept."
    )))
}
