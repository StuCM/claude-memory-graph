"""ceist — plain-English questions over a graph, without an LLM.

    from ceist import interpret, narrate
    meaning = interpret(vocabulary, "which listed buildings are on Leeds Dock?")
    meaning.plan          # backend-neutral: compile it for SPARQL, Rós Madair, Arches Search
    narrate(meaning.plan) # "Find Buildings whose heritage status is Listed and that site Site 'Leeds Dock'."

The question is grounded against the data source's own vocabulary (its
types, relations, controlled values and record names), so the same planner
serves any graph that implements ceist.Vocabulary. Outputs: ceist.alizarin,
ceist.rosmadair, ceist.arches_search. See packages/ceist/README.md.
"""

from .ground import Grounding, ground, is_question
from .narrate import narrate
from .plan import (Contains, DateRange, EntityRef, HasValue, Interpretation, LinkTo, Mention,
                   Not, Plan, Relaxation, interpret)
from .readback import Check, check
from .text import plurals, terms, terms_pos
from .vocabulary import DateField, Entity, Relation, Value, Vocabulary

__all__ = ["Check", "Contains", "DateField", "DateRange", "Entity", "EntityRef", "Grounding",
           "HasValue", "Interpretation", "LinkTo", "Mention", "Not", "Plan", "Relation",
           "Relaxation", "Value", "Vocabulary", "check", "ground", "interpret", "is_question",
           "narrate", "plurals", "terms", "terms_pos"]
