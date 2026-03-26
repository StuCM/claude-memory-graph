/// Valid node types in the memory graph.
/// These are fixed — the LLM cannot create new node types.
pub const VALID_NODE_TYPES: &[&str] = &[
    // Entities
    "Person",
    "Project",
    "Component",
    "Resource",
    "Technology",
    "Concept",
    // Events
    "Decision",
    "Problem",
    "Change",
    "Conversation",
    // Qualities
    "Preference",
    "Constraint",
    "Pattern",
];

/// Check if a node type is valid.
pub fn is_valid_node_type(node_type: &str) -> bool {
    VALID_NODE_TYPES.contains(&node_type)
}

/// The primary name/label property for a given node type.
/// Most use "name", some use "label".
pub fn name_property_for_type(node_type: &str) -> &'static str {
    match node_type {
        "Concept" | "Decision" | "Problem" | "Change" | "Preference" | "Constraint"
        | "Pattern" => "label",
        _ => "name",
    }
}
