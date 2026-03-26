/// Resource models — each instance becomes its own named graph.
pub const RESOURCE_MODELS: &[&str] = &[
    "Person",
    "Project",
    "Company",
    "Task",
    "Technology",
    "Decision",
    "Pattern",
];

/// Concept types — shared lightweight nodes that enable traversal.
pub const CONCEPT_TYPES: &[&str] = &["Skill", "Concept", "Constraint", "Preference"];

/// Valid cross-graph relationship names.
pub const VALID_RELATIONS: &[&str] = &[
    "worksOn",
    "employedBy",
    "owns",
    "uses",
    "madeBy",
    "affects",
    "assignedTo",
    "partOf",
    "relatesTo",
    "supersedes",
    "resolves",
    "appliesTo",
    "hasSkill",
    "hasConcept",
    "hasConstraint",
    "hasPreference",
];

pub fn is_resource_model(model: &str) -> bool {
    RESOURCE_MODELS.contains(&model)
}

pub fn is_concept_type(concept_type: &str) -> bool {
    CONCEPT_TYPES.contains(&concept_type)
}

pub fn is_valid_relation(relation: &str) -> bool {
    VALID_RELATIONS.contains(&relation)
}

/// Scalar properties allowed per resource model.
/// Returns None if the model is unknown.
pub fn scalar_properties(model: &str) -> Option<&'static [&'static str]> {
    match model {
        "Person" => Some(&["name", "email", "role", "address", "description"]),
        "Project" => Some(&[
            "name",
            "projectType",
            "startDate",
            "status",
            "progress",
            "path",
            "url",
            "description",
        ]),
        "Company" => Some(&["name", "industry", "website", "address", "description"]),
        "Task" => Some(&[
            "name",
            "status",
            "deadline",
            "priority",
            "description",
        ]),
        "Technology" => Some(&["name", "version", "category", "url", "description"]),
        "Decision" => Some(&["name", "rationale", "outcome", "date", "description"]),
        "Pattern" => Some(&["name", "example", "description"]),
        // Concept types
        "Skill" => Some(&["label", "description", "proficiency"]),
        "Concept" => Some(&["label", "description"]),
        "Constraint" => Some(&["label", "description"]),
        "Preference" => Some(&["label", "description"]),
        _ => None,
    }
}

/// The primary name property for a given type.
pub fn name_property(type_name: &str) -> &'static str {
    match type_name {
        "Skill" | "Concept" | "Constraint" | "Preference" => "label",
        _ => "name",
    }
}
