"""A small name index for finding the record a question names ("Leeds Dock")
— for vocabularies that don't bring their own search."""

import math

from .text import terms
from .vocabulary import Entity


class NameIndex:
    def __init__(self, entities: list[Entity]):
        self.entities = entities
        df: dict[str, int] = {}
        for e in entities:
            for t in e.terms:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(entities))
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}

    @staticmethod
    def entity(type_: str, id_: str, name: str, text: str = "", **extra) -> Entity:
        name_terms = frozenset(terms(name))
        return Entity(type_, id_, name, name_terms, name_terms | frozenset(terms(text)), extra)

    def rank(self, query: set[str]) -> list[tuple[float, Entity]]:
        """Name hits count double; a record named by every query word ranks first."""
        out = []
        for e in self.entities:
            score = sum(self.idf.get(t, 0.0) * (2.0 if t in e.name_terms else 1.0)
                        for t in query & e.terms)
            if score > 0:
                if e.name_terms and e.name_terms <= query:
                    score *= 1.5
                out.append((score, e))
        out.sort(key=lambda x: -x[0])
        return out
