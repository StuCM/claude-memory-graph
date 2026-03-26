use std::collections::HashMap;

use rmcp::model::{CallToolResult, Content};

use crate::ontology;
use crate::store::{MemoryStore, StoreError};

pub fn handle_resource(
    store: &MemoryStore,
    model: String,
    properties: HashMap<String, String>,
) -> Result<CallToolResult, StoreError> {
    let name_prop = ontology::name_property(&model);
    let name = properties
        .get(name_prop)
        .ok_or_else(|| StoreError::Other(format!("Missing required property: {name_prop}")))?
        .clone();

    // Check if resource already exists
    if let Some((graph_id, iri)) = store.find_resource(&model, &name)? {
        store.update_resource(&iri, &graph_id, &properties)?;
        Ok(CallToolResult::success(vec![Content::text(format!(
            "Updated {model} '{name}'\nIRI: {}\nGraph: {}",
            iri.as_str(),
            crate::namespaces::GRAPH_RESOURCE_BASE.to_owned() + &graph_id
        ))]))
    } else {
        let (id, iri) = store.create_resource(&model, &properties)?;
        Ok(CallToolResult::success(vec![Content::text(format!(
            "Created {model} '{name}'\nIRI: {}\nGraph: {}",
            iri.as_str(),
            crate::namespaces::GRAPH_RESOURCE_BASE.to_owned() + &id
        ))]))
    }
}

pub fn handle_concept(
    store: &MemoryStore,
    concept_type: String,
    label: String,
    properties: HashMap<String, String>,
) -> Result<CallToolResult, StoreError> {
    let iri = store.store_concept(&concept_type, &label, &properties)?;
    Ok(CallToolResult::success(vec![Content::text(format!(
        "Stored {concept_type} concept '{label}'\nIRI: {}",
        iri.as_str()
    ))]))
}
