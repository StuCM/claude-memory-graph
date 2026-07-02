RESOURCE_MODELS = [
    "Person",
    "Project",
    "Company",
    "Task",
    "Technology",
    "Decision",
    "Pattern",
]

CONCEPT_TYPES = ["Skill", "Concept", "Constraint", "Preference"]


def is_resource_model(model: str) -> bool:
    return model in RESOURCE_MODELS


def is_concept_type(concept_type: str) -> bool:
    return concept_type in CONCEPT_TYPES


def name_property(type_name: str) -> str:
    if type_name in CONCEPT_TYPES:
        return "label"
    return "name"
