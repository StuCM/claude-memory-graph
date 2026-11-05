"""ceist on its own: a toy Arches-shaped vocabulary, no memory graph."""

import pytest

from ceist import (Contains, Entity, EntityRef, HasValue, LinkTo, Plan, Relation, Value,
                   interpret, narrate, plurals, terms)
from ceist.vocabulary import Group


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
    # Sites have no heritage status: answering "every site" would drop the
    # word that constrains the question, so it refuses and says why
    m = interpret(Toy(), "which listed sites are there?")
    assert m.plan is None and "'listed' is a value of heritage_status" in m.refused
    assert "listed" in m.grounding.uncovered


def test_unplaced_words_refuse_instead_of_widening_the_answer():
    # one grounded word ("candidate") lifts coverage over the threshold; the
    # words that actually constrain the question must not be dropped silently
    m = interpret(Toy(), "which candidate buildings were damaged in a fire?")
    assert m.plan is None
    assert "couldn't place" in m.refused and "'damaged'" in m.refused and "'fire'" in m.refused


class FreeText(Toy):
    free_text = True

    def relations(self):
        return super().relations() + [Relation("part_of", ("part of",), frozenset({"Building"}),
                                               frozenset({"Building"}))]


def test_an_unplaced_word_refuses_unless_the_vocabulary_has_free_text():
    m = interpret(Toy(), "which buildings on site Leeds Dock are wonky?")
    assert m.plan is None and m.relaxations == []
    assert "couldn't place 'wonky'" in m.refused
    # a relation with nowhere to go: listing every Building instead widens it just the same
    loose = interpret(FreeText(), "which buildings are part of?")
    assert narrate(loose.plan) == "Find Buildings." and loose.grounding.loose == "'part of'"
    strict = FreeText()
    strict.free_text = False
    m = interpret(strict, "which buildings are part of?")
    assert m.plan is None and "cannot resolve both ends of relation part_of" in m.refused
    # the end it couldn't find may be a word nothing placed ("in Down"): that is named
    m = interpret(strict, "which buildings are part of wonkyville?")
    assert m.plan is None and "couldn't place 'wonkyville'" in m.refused


def test_leftover_word_gets_a_relaxation_without_it():
    m = interpret(FreeText(), "which buildings on site Leeds Dock are wonky?")
    assert any(isinstance(c, Contains) and c.term == "wonky" for c in m.plan.where)
    relaxed = m.relaxations[-1]
    assert relaxed.drops == "wonky"
    assert not any(isinstance(c, Contains) for c in relaxed.plan.where)


def test_statement_and_thin_grounding_refuse():
    assert interpret(Toy(), "Refactor the loader").statement
    m = interpret(Toy(), "what colour is the bikeshed?")
    assert m.plan is None and "couldn't place 'bikeshed', 'colour'" in m.refused
    m = interpret(Toy(), "what is it?")
    assert m.plan is None and "nothing in it names anything" in m.refused


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
    assert without.plan is None and "couldn't place 'drawn'" in without.refused
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


def test_two_relations_between_the_same_two_things_refuse_not_recurse():
    # HER: "Who owned the barge?" grounded 'who' → actor and 'owned' →
    # actor#Owner, both Person–Organization; building the plan looped forever
    class Owners(Toy):
        def type_words(self):
            return {"person": "Person", "organization": "Organization", "barge": "Organization"}

        def relations(self):
            return [Relation("actor", ("who",), frozenset({"Person"}), frozenset({"Organization"})),
                    Relation("actor#Owner", ("owned",), frozenset({"Person"}),
                             frozenset({"Organization"}))]
    m = interpret(Owners(), "who owned the barge?")
    assert m.plan is None and "both join" in m.refused


def test_only_a_whole_name_binds_a_record():
    # "county" is a word of 'County Carn' but not its name
    toy = Toy()
    toy.records = Toy.records + [entity("Building", "b-carn", "County Carn")]
    m = interpret(toy, "which buildings are on site County Nowhere?")
    assert m.direct is None
    assert not any(isinstance(c, LinkTo) and isinstance(c.target, EntityRef)
                   for c in (m.plan.where if m.plan else []))
    toy.records.append(Entity("Site", "s-down", "County Down", frozenset({"county", "down"}),
                              frozenset({"county", "down"}), aliases=(frozenset({"dún"}),)))
    m = interpret(toy, "which buildings are on site County Down?")
    assert m.plan.where[0].target.entity.id == "s-down"


class Counties(Toy):
    """'county' is also a group phrase, a value and a relation phrase."""
    records = Toy.records + [entity("Site", "s-down", "County Down")]
    county = ""

    def relations(self):
        extra = [Relation("district", ("county",), frozenset({"Building"}),
                          frozenset({"Site"}))] if self.county == "relation" else []
        return Toy.relations(self) + extra

    def values(self):
        extra = [Value("county", "area_type", "c-county", "County",
                       frozenset({"Building"}))] if self.county == "value" else []
        return Toy.values(self) + extra

    def groups(self):
        return [Group("area", "Building", (("county", ()),))] if self.county == "group" else []


@pytest.mark.parametrize("kind", ["group", "value", "relation"])
def test_a_record_name_beats_a_shorter_phrase_inside_it(kind):
    toy = Counties()
    toy.county = kind
    m = interpret(toy, "which buildings are on site County Down?")
    assert [(c.relation, c.target.entity.id) for c in m.plan.where] == [("site", "s-down")]
    assert m.grounding.coverage == 1.0


def test_a_phrase_outside_the_record_name_still_grounds():
    toy = Counties()
    toy.county = "value"
    m = interpret(toy, "which county buildings are on site County Down?")
    assert [v.phrase for v in m.grounding.values] == ["county"]
    assert m.grounding.anchor.entity.id == "s-down"


def test_a_vocabulary_may_let_part_of_a_name_bind():
    toy = Toy()
    toy.partial_names = True
    assert interpret(toy, "what do we know about Ada?").direct.id == "p-1"
    assert interpret(Toy(), "what do we know about Ada?").direct is None


def test_a_named_thing_left_unjoined_refuses_instead_of_dropping():
    # the Person var is joined to Ada, but nothing joins either to the Sites asked for
    m = interpret(Toy(), "which sites is Ada Lovelace the architect of?")
    assert m.plan is None and "'architect' (architect) can't join Person and Site" in m.refused


def test_a_shared_phrasing_goes_to_the_relation_joining_the_named_types():
    class Parts(Toy):
        def relations(self):
            return [Relation("parent_group", ("part of",), frozenset({"Group"}), frozenset({"Group"})),
                    Relation("parent_site", ("part of",), frozenset({"Site"}), frozenset({"Site"}))]
    m = interpret(Parts(), "which sites are part of Salts Mill?")
    assert m.plan.where[0].relation == "parent_site"


class In(Toy):
    """'in' names two relations; the architect one is listed first, so word
    order alone would pick it."""
    def relations(self):
        return [Relation("architect", ("in",), frozenset({"Building"}), frozenset({"Person"})),
                Relation("site", ("in", "on site"), ends=frozenset({("Building", frozenset())})),
                Relation("parent_site", ("in",), frozenset({"Site"}), frozenset({"Site"}))]


def test_a_shared_phrase_binds_the_relation_that_joins_the_anchor():
    m = interpret(In(), "which buildings are in Leeds Dock?")
    assert [(c.relation, c.target.entity.id) for c in m.plan.where] == [("site", "s-dock")]
    m = interpret(In(), "which sites are in Salts Mill?")
    assert m.plan.where[0].relation == "parent_site"


def test_a_shared_phrase_no_relation_fits_falls_back_to_a_loose_link():
    m = interpret(In(), "which person is in Salts Mill?")
    assert m.plan.where == [LinkTo(None, EntityRef(m.grounding.anchor.entity), "any")]
    assert narrate(m.plan) == "Find Persons linked to or from Site 'Salts Mill'."
    assert any("'in' set aside" in n for n in m.grounding.notes)
    assert m.grounding.coverage == 1.0


class At(Toy):
    """'at' names one relation, an Object's repository owner, which can't join a Building and a Site."""
    def relations(self):
        return [Relation("repository_owner", ("at", "kept by"), frozenset({"Object"}),
                         frozenset({"Person"}))]


def test_one_relation_that_cant_join_what_is_named_is_never_bound():
    # was "Find Buildings whose repository owner is Site 'Leeds Dock'", which Rós Madair can't compile
    m = interpret(At(), "which buildings are at Leeds Dock?")
    assert narrate(m.plan) == "Find Buildings linked to or from Site 'Leeds Dock'."   # "at", as if unlisted
    m = interpret(At(), "which buildings are kept by Leeds Dock?")
    assert m.plan is None and "'kept by' (repository_owner) can't join Building and Site" in m.refused


def test_a_set_aside_phrase_keeps_its_negation():
    m = interpret(In(), "which person is not in Salts Mill?")
    assert m.plan is None and "'not'" in m.refused


def test_a_phrase_with_one_fitting_relation_is_unchanged():
    m = interpret(Toy(), "which buildings are on site Leeds Dock?")
    assert m.plan.where[0].relation == "site"
    assert not any("set aside" in n or "instead" in n for n in m.grounding.notes)



class Fleet(Toy):
    """HER-shaped labels: a one-letter altLabel ('S' for Statutory), the unit
    inch as 'in', and the evidence type 'Find'."""
    records = Toy.records + [entity("Person", "p-brunel", "Brunel")]

    def type_words(self):
        return {"aircraft": "Aircraft", "airmen": "Person", "people": "Person"}

    def relations(self):
        return [Relation("flew", ("flew",), frozenset({"Person"}), frozenset({"Aircraft"}))]

    def values(self):
        return [Value("lancaster", "aircraft_function", "c-lanc", "Lancaster",
                      frozenset({"Aircraft"})),
                Value("in", "measurement_unit", "c-inch", "inch", frozenset({"Aircraft"})),
                Value("s", "name_use_type", "c-stat", "Statutory", frozenset({"Aircraft"})),
                Value("find", "evidence_type", "c-find", "Find", frozenset({"Aircraft"}))]


def _values(plan):
    from ceist.plan import _plans
    return [c.label for p in _plans(plan) for c in p.where if isinstance(c, HasValue)]


def test_a_label_with_no_content_word_never_matches():
    m = interpret(Fleet(), "what's the Lancaster's name?")
    assert [v.phrase for v in m.grounding.values] == ["lancaster"]


def test_flew_in_the_lancaster_is_not_measured_in_inches():
    m = interpret(Fleet(), "Which airmen flew in the Lancaster?")
    assert narrate(m.plan) == "Find Persons that flew any Aircraft whose aircraft function is Lancaster."
    assert _values(m.plan) == ["Lancaster"]


def test_find_leading_a_question_is_the_command_not_a_value():
    m = interpret(Fleet(), "Find people with the surname Brunel")
    assert [v.phrase for v in m.grounding.values] == []
    assert "evidence_type" not in m.refused
    # "surname" is no field it knows: Brunel alone could be the wrong Brunel
    assert m.direct is None and "couldn't place 'surname'" in m.refused
