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


# ── dates and negation ─────────────────────────────────────────────────────

from datetime import date  # noqa: E402

from ceist import DateField, DateRange, Not  # noqa: E402
from ceist import dates  # noqa: E402
from ceist.readback import check  # noqa: E402

TODAY = date(2026, 10, 27)


class Dated(Toy):
    def date_fields(self):
        return [DateField("construction_date", "construction date", ("built", "constructed"),
                          frozenset({"Building"}), default=True),
                DateField("demolition_date", "demolition date", ("demolished",),
                          frozenset({"Building"}))]


class TwoDates(Toy):
    def date_fields(self):
        return [DateField("construction_date", "construction date", ("built",),
                          frozenset({"Building"})),
                DateField("demolition_date", "demolition date", ("demolished",),
                          frozenset({"Building"}))]


@pytest.mark.parametrize("phrase, lo, hi, label", [
    ("in 1850", "1850-01-01", "1850-12-31", "in 1850"),
    ("before 1900", None, "1899-12-31", "before 1900"),
    ("after 1900", "1901-01-01", None, "after 1900"),
    ("since 1900", "1900-01-01", None, "after 1899"),
    ("between 1800 and 1850", "1800-01-01", "1850-12-31", "between 1800 and 1850"),
    ("in the 1890s", "1890-01-01", "1899-12-31", "in the 1890s"),
    ("in the 19th century", "1800-01-01", "1899-12-31", "in the 19th century"),
    ("in the 1800s", "1800-01-01", "1899-12-31", "in the 19th century"),
    ("in may 2020", "2020-05-01", "2020-05-31", "in May 2020"),
    ("on 2020-05-01", "2020-05-01", "2020-05-01", "on 2020-05-01"),
    ("last year", "2025-01-01", "2025-12-31", "in 2025"),
    ("in the last 3 months", "2026-07-27", "2026-10-27", "between 2026-07-27 and 2026-10-27"),
])
def test_date_phrases(phrase, lo, hi, label):
    (m,) = dates.find(phrase, [], TODAY)
    assert (m.lo, m.hi) == (lo, hi)
    assert dates.label(m.lo, m.hi) == label


def test_days_is_alizarins_quantize():
    # quantize_date: signed days since 1970-01-01, bare year = 1 January
    assert dates.days("1970-01-01") == 0 and dates.days("1970-01-02") == 1
    assert dates.days("1969-12-31") == -1 and dates.days("2020") == dates.days("2020-01-01")
    assert dates.from_days(dates.days("1845-06-01")) == "1845-06-01"
    assert dates.from_days(dates.OPEN) is None


def test_date_picks_the_field_by_word_or_default():
    m = interpret(Dated(), "which buildings were built before 1900?", today=TODAY)
    assert m.plan.where == [DateRange("construction_date", None, "1899-12-31",
                                      "construction date")]
    m = interpret(Dated(), "which buildings were demolished in the 1960s?", today=TODAY)
    assert m.plan.where[0].field == "demolition_date"
    m = interpret(Dated(), "which buildings date from 1850?", today=TODAY)
    assert m.plan.where[0].field == "construction_date"           # the default
    assert narrate(m.plan) == "Find Buildings whose construction date is in 1850."


def test_ambiguous_date_refuses():
    m = interpret(TwoDates(), "which buildings date from 1850?", today=TODAY)
    assert m.plan is None and "construction date or the demolition date" in m.refused


def test_years_are_words_without_date_fields():
    m = interpret(Toy(), "which buildings are on site Leeds Dock in 1850?")
    assert not any(isinstance(c, DateRange) for c in (m.plan.where if m.plan else []))


def test_negated_value_and_link():
    m = interpret(Toy(), "which buildings are not listed?")
    assert m.plan.where == [Not(HasValue("heritage_status", "c-listed", "Listed", "concept"))]
    assert narrate(m.plan) == "Find Buildings whose heritage status is not Listed."
    m = interpret(Toy(), "which non-listed buildings are on site Leeds Dock?")
    assert Not(HasValue("heritage_status", "c-listed", "Listed", "concept")) in m.plan.where
    m = interpret(Toy(), "which buildings were not designed by Ada Lovelace?")
    (c,) = m.plan.where
    assert isinstance(c, Not) and c.condition.relation == "architect"
    assert narrate(m.plan) == "Find Buildings that do not designed by Person 'Ada Lovelace'."


def test_negation_scopes_to_the_hop():
    m = interpret(Toy(), "which sites have no buildings designed by Ada Lovelace?")
    (c,) = m.plan.where
    assert isinstance(c, Not) and c.condition.relation == "site"
    assert c.condition.direction == "in"
    inner = c.condition.target.where[0]
    assert isinstance(inner, LinkTo) and inner.relation == "architect"   # not negated


def test_negated_date():
    m = interpret(Dated(), "which buildings were not built in the 19th century?", today=TODAY)
    assert m.plan.where == [Not(DateRange("construction_date", "1800-01-01", "1899-12-31",
                                          "construction date"))]


def test_dangling_negation_refuses():
    m = interpret(Toy(), "which buildings are not?")
    assert m.plan is None and "couldn't tell what it negates" in m.refused


def test_readback_check():
    m = interpret(Toy(), "which listed buildings are not on site Leeds Dock?")
    assert check(m.plan, m.plan).ok
    flipped = Plan(m.plan.type, [c.condition if isinstance(c, Not) else c
                                 for c in m.plan.where])
    verdict = check(m.plan, flipped)
    assert not verdict.ok and "✗" in "\n".join(verdict.lines())
    # order doesn't matter
    assert check(m.plan, Plan(m.plan.type, list(reversed(m.plan.where)))).ok


# ── leftover words, matched by the configured chain ─────────────────────────

from ceist.matching import Chain, Exact, Vectors  # noqa: E402
from fakes import FakeEncoder  # noqa: E402

FakeEncoder.SAME.update({"drawn": "designed", "sketched": "designed"})


def chain():
    return Chain([Exact(), Vectors(FakeEncoder(), low=0.6)], clarify_top=3, clarify_min=0.0)


@pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")
def test_leftover_relation_by_meaning():
    q = "which buildings were drawn by Ada Lovelace?"
    without = interpret(Toy(), q)
    assert not any(isinstance(c, LinkTo) and c.relation == "architect"
                   for c in without.plan.where)                  # a loose link, before
    m = interpret(Toy(), q, matcher=chain())
    (c,) = m.plan.where
    assert c.relation == "architect" and c.target.entity.id == "p-1"
    assert any("(vectors" in n for n in m.grounding.notes)


@pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")
def test_leftover_date_field_by_meaning():
    assert interpret(TwoDates(), "which buildings were erected in 1850?", today=TODAY).plan is None
    m = interpret(TwoDates(), "which buildings were erected in 1850?", today=TODAY, matcher=chain())
    assert m.plan.where[0].field == "construction_date"


@pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")
def test_unsure_suggests_instead_of_guessing():
    m = interpret(TwoDates(), "which buildings were painted in 1850?", today=TODAY, matcher=chain())
    assert m.plan is None and "did you mean" in m.refused
    assert m.grounding.suggestions[0][0] == "painted"
