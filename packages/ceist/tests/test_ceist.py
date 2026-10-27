"""ceist on its own: a toy Arches-shaped vocabulary, no memory graph."""

import pytest

from ceist import (Contains, Entity, EntityRef, HasValue, LinkTo, Plan, Relation, Value,
                   interpret, narrate, plurals, terms)


def entity(type_, id_, name):
    t = frozenset(terms(name))
    return Entity(type_, id_, name, t, t)


class Toy:
    """Buildings on sites, with a heritage status from a thesaurus."""

    records = [entity("Site", "s-dock", "Leeds Dock"),
               entity("Site", "s-mill", "Salts Mill"),
               entity("Building", "b-1", "Clock Tower"),
               entity("Person", "p-1", "Ada Lovelace")]

    def type_words(self):
        words = {}
        for t in ("Building", "Site", "Person"):
            for w in plurals(t):
                words[w] = t
        return words

    def relations(self):
        return [Relation("site", ("site", "on site", "at site"), frozenset({"Building"}),
                         frozenset({"Site"})),
                Relation("architect", ("designed by", "architect"), frozenset({"Building"}),
                         frozenset({"Person"}))]

    def values(self):
        return [Value("listed", "heritage_status", "c-listed", "Listed",
                      frozenset({"Building"})),
                Value("candidate", "heritage_status", "c-cand", "Candidate",
                      frozenset({"Building"}))]

    def rank_entities(self, q):
        scored = [(len(q & e.name_terms), e) for e in self.records]
        return sorted([x for x in scored if x[0] > 0], key=lambda x: -x[0])

    def implied_types(self):
        return {"who": "Person"}

    def hint_words(self):
        return {}


def test_value_and_link():
    m = interpret(Toy(), "which listed buildings are on site Leeds Dock?")
    assert m.plan.type == "Building"
    link = next(c for c in m.plan.where if isinstance(c, LinkTo))
    assert link.relation == "site" and isinstance(link.target, EntityRef)
    assert link.target.entity.id == "s-dock"
    value = next(c for c in m.plan.where if isinstance(c, HasValue))
    assert value.value == "c-listed"
    assert narrate(m.plan) == ("Find Buildings that on site Site 'Leeds Dock' "
                               "and whose heritage status is Listed.")


def test_nested_hop():
    m = interpret(Toy(), "which sites have buildings designed by Ada Lovelace?")
    assert m.plan.type == "Site"
    hop = m.plan.where[0]
    assert hop.relation == "site" and hop.direction == "in"
    assert isinstance(hop.target, Plan) and hop.target.type == "Building"
    inner = hop.target.where[0]
    assert inner.relation == "architect" and inner.target.entity.id == "p-1"


def test_count():
    m = interpret(Toy(), "how many candidate buildings are there?")
    assert m.plan.count and m.plan.type == "Building"
    assert m.plan.where == [HasValue("heritage_status", "c-cand", "Candidate", "concept")]


def test_value_only_applies_where_a_type_has_the_field():
    m = interpret(Toy(), "which listed sites are there?")
    assert m.plan.type == "Site" and not m.plan.where
    assert "listed" in m.grounding.uncovered


def test_leftover_word_gets_a_relaxation_without_it():
    m = interpret(Toy(), "which buildings on site Leeds Dock are wonky?")
    assert any(isinstance(c, Contains) and c.term == "wonky" for c in m.plan.where)
    relaxed = m.relaxations[-1]
    assert relaxed.drops == "wonky"
    assert not any(isinstance(c, Contains) for c in relaxed.plan.where)


def test_statement_and_thin_grounding_refuse():
    assert interpret(Toy(), "Refactor the loader").statement
    m = interpret(Toy(), "what colour is the bikeshed?")
    assert m.plan is None and "coverage" in m.refused


def test_about_goes_straight_to_the_record():
    m = interpret(Toy(), "what do we know about Salts Mill?")
    assert m.direct is not None and m.direct.id == "s-mill"


@pytest.mark.parametrize("word, forms", [("site", {"site", "sites"}),
                                         ("property", {"property", "properties"}),
                                         ("box", {"box", "boxes"})])
def test_plurals(word, forms):
    assert forms <= plurals(word)
