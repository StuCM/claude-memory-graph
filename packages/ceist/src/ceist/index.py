"""A small name index for finding the record a question names ("Leeds Dock")
— for vocabularies that don't bring their own search."""

import math

from .text import marks, terms
from .vocabulary import Entity


class NameIndex:
    def __init__(self, entities: list[Entity]):
        self.entities = entities
        self.by_id = {e.id: e for e in entities}
        self.holders: dict[str, list[int]] = {}
        for i, e in enumerate(entities):
            for t in e.terms:
                self.holders.setdefault(t, []).append(i)
        n = max(1, len(entities))
        self.idf = {t: math.log(1 + n / len(held)) for t, held in self.holders.items()}
        self._ranked: dict[frozenset[str], list[tuple[float, Entity]]] = {}

    @staticmethod
    def entity(type_: str, id_: str, name: str, text: str = "", **extra) -> Entity:
        name_terms = frozenset(terms(name)) | marks(name)
        return Entity(type_, id_, name, name_terms, name_terms | frozenset(terms(text)), extra)

    def rank(self, query: set[str]) -> list[tuple[float, Entity]]:
        """Name hits count double; a record named by every query word ranks first."""
        key = frozenset(query)
        if key not in self._ranked:
            # ponytail: cleared when full, an LRU if question-time traffic ever needs one
            if len(self._ranked) > 100_000:
                self._ranked.clear()
            self._ranked[key] = self._rank(key)
        return list(self._ranked[key])

    def _rank(self, query: frozenset[str]) -> list[tuple[float, Entity]]:
        out = []
        hit = sorted({i for t in query for i in self.holders.get(t, ())})
        for e in (self.entities[i] for i in hit):
            score = sum(self.idf.get(t, 0.0) * (2.0 if t in e.name_terms else 1.0)
                        for t in query & e.terms)
            if score > 0:
                if e.name_terms and e.name_terms <= query:
                    score *= 1.5
                out.append((score, e))
        out.sort(key=lambda x: -x[0])
        return out
