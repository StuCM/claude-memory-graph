"""Schema assembly (ceist.assemble): pieces put together by the schema, not word order."""

from test_ceist import Toy

from ceist import Relation, interpret, narrate


def schema(vocab, text):
    return interpret(vocab, text, assembly="schema")


class Nested(Toy):
    """Toy, with sites inside sites: a link whose two ends are the same type."""

    def relations(self):
        return super().relations() + [Relation("parent_site", ("part of",), frozenset({"Site"}),
                                               frozenset({"Site"}))]


LISTED_ON_DOCK = ("Find Buildings that on site Site 'Leeds Dock' and whose heritage status "
                  "is Listed.")


def test_a_reordered_question_reads_as_the_plain_one():
    plain = interpret(Toy(), "which listed buildings are on site Leeds Dock?")
    assert narrate(plain.plan) == LISTED_ON_DOCK
    q = "on site Leeds Dock, which buildings are listed?"
    assert interpret(Toy(), q).plan is None
    assert narrate(schema(Toy(), q).plan) == LISTED_ON_DOCK


def test_a_fragment_is_a_question_once_it_names_a_subject():
    assert interpret(Toy(), "listed buildings on site Leeds Dock").statement
    assert narrate(schema(Toy(), "listed buildings on site Leeds Dock").plan) == LISTED_ON_DOCK


def test_a_filler_word_is_ignored():
    q = "which of these listed buildings are on site Leeds Dock?"
    assert interpret(Toy(), q).refused.startswith("couldn't place 'these'")
    assert narrate(schema(Toy(), q).plan) == LISTED_ON_DOCK


def test_two_readings_ask_which():
    m = schema(Nested(), "which sites are part of Salts Mill?")
    assert m.plan is None
    assert m.refused.startswith("2 readings fit; did you mean")
    assert m.grounding.suggestions == [("the question", [
        "Find Sites that parent_site Site 'Salts Mill'.",
        "Find Sites that Site 'Salts Mill' parent_site."])]


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
