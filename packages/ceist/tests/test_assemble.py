"""Schema assembly (ceist.assemble): pieces put together by the schema, not word order."""

from test_ceist import Toy

from ceist import Relation, Value, interpret, narrate


def schema(vocab, text):
    return interpret(vocab, text, assembly="schema")


def strict(vocab, text):
    return interpret(vocab, text, assembly="strict")


class Nested(Toy):
    """Toy, with sites inside sites: a link whose two ends are the same type."""

    def relations(self):
        return super().relations() + [Relation("parent_site", ("part of",), frozenset({"Site"}),
                                               frozenset({"Site"}))]


LISTED_ON_DOCK = ("Find Buildings that on site Site 'Leeds Dock' and whose heritage status "
                  "is Listed.")


def test_a_reordered_question_reads_as_the_plain_one():
    plain = strict(Toy(), "which listed buildings are on site Leeds Dock?")
    assert narrate(plain.plan) == LISTED_ON_DOCK
    q = "on site Leeds Dock, which buildings are listed?"
    assert strict(Toy(), q).plan is None
    assert narrate(schema(Toy(), q).plan) == LISTED_ON_DOCK


def test_a_fragment_is_a_question_once_it_names_a_subject():
    assert strict(Toy(), "listed buildings on site Leeds Dock").statement
    assert narrate(schema(Toy(), "listed buildings on site Leeds Dock").plan) == LISTED_ON_DOCK


def test_a_filler_word_is_ignored():
    q = "which of these listed buildings are on site Leeds Dock?"
    assert strict(Toy(), q).refused.startswith("couldn't place 'these'")
    assert narrate(schema(Toy(), q).plan) == LISTED_ON_DOCK


def test_word_order_decides_a_same_type_link_either_way():
    for q, want in (("which sites are part of Salts Mill?",
                     "Find Sites that parent_site Site 'Salts Mill'."),
                    ("which sites is Salts Mill part of?",
                     "Find Sites that Site 'Salts Mill' parent_site.")):
        assert narrate(strict(Nested(), q).plan, forms=False) == want
        assert narrate(schema(Nested(), q).plan, forms=False) == want


class Owned(Toy):
    """Toy, with a second link from buildings to people said the same way."""

    def relations(self):
        return super().relations() + [Relation("owner", ("designed by",), frozenset({"Building"}),
                                               frozenset({"Person"}))]


def test_two_readings_ask_which():
    m = schema(Owned(), "which buildings are designed by Ada Lovelace?")
    assert m.plan is None
    assert m.refused.startswith("2 readings fit; did you mean")
    assert sorted(m.grounding.suggestions[0][1]) == [
        "Find Buildings that architect Person 'Ada Lovelace'.",
        "Find Buildings that owner Person 'Ada Lovelace'."]


class Designated(Toy):
    """Toy, where 'listed' is also a value of a second field on buildings."""

    def values(self):
        return super().values() + [Value("listed", "designation", "d-listed", "Listed",
                                         frozenset({"Building"}))]


def test_a_value_in_two_fields_means_either():
    for mode in ("strict", "schema"):
        m = interpret(Designated(), "which listed buildings are on site Leeds Dock?", assembly=mode)
        assert narrate(m.plan) == ("Find Buildings that on site Site 'Leeds Dock' and whose "
                                   "heritage status or designation is Listed.")


def test_no_reading_refuses():
    # 'designed by' joins a building to its architect, never a site
    m = schema(Toy(), "which sites are designed by Ada Lovelace?")
    assert m.plan is None
    assert m.refused == ("no reading fits the schema: 'designed by' can't join "
                         "Person and Site")


def test_an_unknown_content_word_still_refuses():
    m = schema(Toy(), "which buildings on site Leeds Dock are wonky?")
    assert m.plan is None
    assert m.refused.startswith("couldn't place 'wonky'")
