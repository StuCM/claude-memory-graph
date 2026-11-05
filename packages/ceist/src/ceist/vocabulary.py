"""What a question can name: the interface every data source implements.

The planner knows nothing about any particular graph. A Vocabulary tells it:

- the **types** a question can ask for, and the everyday words for them
  ("buildings", "gotchas" → Pattern);
- the **relations** between types, with the phrases that express them
  ("works on", "affects", "site") and which types sit at each end;
- the **controlled values** a field can take, with the phrases that name them
  ("listed" → Heritage status = Listed; "active" → status = active);
- the **date fields** a type has, and the words that pick one ("built" →
  construction date) — optional;
- how to **find a named thing** ("quartz", "Leeds Dock") among the records.

Implementations: the memory graph (its schema graph and gate index), and
Arches resource models (ceist.arches) for Rós Madair and Arches Search.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Relation:
    name: str                                   # what a backend calls it (relation, node path)
    forms: tuple[str, ...]                      # phrases that express it, lowercase
    domain: frozenset[str] = frozenset()        # types at the source end
    range: frozenset[str] = frozenset()         # types at the target end
    style: str = "verb"                         # how it reads: "verb" ("affects X") or
                                                # "field" ("whose site is X")
    path: str = ""                              # what a backend calls the link, when `name`
                                                # is a variant of it ("actor#Architect")
    qualifier: tuple[str, str, str] | None = None   # (field, value, label) that must hold
                                                # on the same record entry (tile) as the link:
                                                # designed by → actor with role Architect
    ends: frozenset[tuple[str, frozenset[str]]] = frozenset()   # (a type holding the link, the
                                                # types it may target; empty = any), when
                                                # domain × range is coarser than the truth

    def joins(self, source: str, target: str) -> bool:
        """Whether this link can run from a `source` record to a `target` one."""
        if self.ends:
            return any(m == source and (not t or target in t) for m, t in self.ends)
        return ((not self.domain or source in self.domain)
                and (not self.range or target in self.range))


@dataclass(frozen=True)
class Value:
    """A controlled value a question can name: a concept in a thesaurus, or a
    fixed status word."""
    phrase: str                                 # how it's said, lowercase ("listed")
    field: str                                  # the field that holds it
    value: str                                  # what the backend matches (concept id, literal)
    label: str                                  # display label ("Listed")
    owners: frozenset[str] = frozenset()        # types that have the field; empty = any
    kind: str = "concept"                       # "concept" (has a hierarchy) | "literal"


@dataclass(frozen=True)
class DateField:
    """A date a question can constrain ("built before 1900")."""
    field: str                                  # what the backend calls it
    label: str                                  # how it reads ("construction date")
    forms: tuple[str, ...] = ()                 # words that pick it ("built", "constructed")
    owners: frozenset[str] = frozenset()        # types that have it; empty = any
    default: bool = False                       # the one meant when no word picks


@dataclass
class Entity:
    """A named record the question may anchor on."""
    type: str
    id: str                                     # backend identity (IRI, resource UUID)
    name: str
    name_terms: frozenset[str] = frozenset()
    terms: frozenset[str] = frozenset()
    extra: dict = field(default_factory=dict)   # backend-specific (graph id, gid, …)
    aliases: tuple[frozenset[str], ...] = ()    # the terms of each other name it goes by

    def named_by(self, words: set[str]) -> bool:
        """The words hold its whole name, or a whole alias: "County Carn" is not
        named by "county"."""
        return any(n and n <= words for n in (self.name_terms, *self.aliases))


class Vocabulary(Protocol):
    def type_words(self) -> dict[str, str]:
        """Word → type ("decisions" → "Decision", "buildings" → "Building")."""

    def relations(self) -> list[Relation]:
        """Every relation a question can traverse, with its phrases."""

    def values(self) -> list[Value]:
        """Every controlled value a question can name (may be empty)."""

    def rank_entities(self, terms: set[str]) -> list[tuple[float, Entity]]:
        """Records ranked by how well their names/text match `terms`, best
        first. Only candidates with a score above zero.
        A record binds only when the question holds its whole name or an
        alias; a vocabulary with `partial_names = True` lets any name word bind."""

    def implied_types(self) -> dict[str, str]:
        """Question words that imply a type ("who" → "Person"). May be empty."""

    def hint_words(self) -> dict[str, str]:
        """Verbs that imply a type without naming it ("chose" → "Decision")."""

    # optional: def date_fields(self) -> list[DateField]
    #   Without it, years and dates in a question are ordinary words.
