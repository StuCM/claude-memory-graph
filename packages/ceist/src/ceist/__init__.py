"""ceist — plain-English questions over a graph, without an LLM.

    from ceist import interpret, narrate
    meaning = interpret(vocabulary, "which listed buildings are on Leeds Dock?")
    meaning.plan          # backend-neutral: compile it for SPARQL, Rós Madair, Arches Search
    narrate(meaning.plan) # "Find Buildings whose heritage status is Listed and that site Site 'Leeds Dock'."

The question is grounded against the data source's own vocabulary (its
types, relations, controlled values and record names), so the same planner
serves any graph that implements ceist.Vocabulary. See README.md.
"""

from .ground import Grounding, ground, is_question
from .narrate import narrate
from .plan import (Contains, EntityRef, HasValue, Interpretation, LinkTo, Mention, Plan,
                   Relaxation, interpret)
from .text import plurals, terms, terms_pos
from .vocabulary import Entity, Relation, Value, Vocabulary

__all__ = ["Contains", "Entity", "EntityRef", "Grounding", "HasValue", "Interpretation",
           "LinkTo", "Mention", "Plan", "Relation", "Relaxation", "Value", "Vocabulary",
           "ground", "interpret", "is_question", "narrate", "plurals", "terms", "terms_pos"]
