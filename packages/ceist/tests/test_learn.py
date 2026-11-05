"""The learning loop: phrases ceist couldn't place, and "did you mean" picks,
become proposals; the approved ones join the vocabulary; the next build
places them. The held-out questions never feed it."""

import json

from ceist import bundle as _bundle
from ceist import learn
from ceist.matching import Item

BUNDLE = {"format": "ceist.vocab/1", "models": {"Building": {
    "nodes": {"architect": {"kind": "link", "label": "Architect", "targets": ["Person"]},
              "actor": {"kind": "link", "label": "Actor", "targets": ["Person"]},
              "construction_date": {"kind": "date", "label": "Construction Date"},
              "heritage_status": {"kind": "property", "label": "Heritage status"}},
    "entries": [
        {"phrases": ["designed by"], "kind": "link", "node": "architect"},
        {"phrases": ["built by"], "kind": "link", "node": "actor",
         "qualifier": {"node": "actor_role", "value": "Builder"}},
        {"phrases": ["built", "erected"], "kind": "date", "node": "construction_date"}]}}}


def _log(path, *events):
    for ev in events:
        learn.record(path, **ev)


def test_picks_are_confirmed_and_the_rest_are_to_assign(tmp_path):
    log = tmp_path / "learn.jsonl"
    architect = Item(("architect", None, None), ("designed by",), "Architect")
    _log(log,
         dict(model="Building", question="which buildings were drafted by Ada?",
              phrase="drafted by", slot="link:Person", options=[architect], chosen=architect),
         dict(model="Building", question="buildings drafted by Wren?", phrase="Drafted  by",
              slot="link:Person", options=[architect], chosen=architect),
         dict(model="Building", question="which buildings were knocked about?",
              phrase="knocked about", slot="property"),
         dict(model="Building", question="buildings erected before 1900?", phrase="erected",
              slot="date"))                                   # already in the vocabulary
    props = learn.proposals(log, BUNDLE)
    (c,) = props["confirmed"]
    assert (c["phrase"], c["node"], c["seen"], c["approve"]) == ("drafted by", "architect", 2, True)
    (u,) = props["to_assign"]
    assert u["phrase"] == "knocked about" and u["approve"] is False and u["assign"] is None
    assert u["candidates"] == ["heritage_status"]            # what fits a property slot
    assert props["skipped"]["known"] == 1
    assert "drafted by" in learn.summary(props)


def test_the_held_out_questions_never_feed_the_vocabulary(tmp_path):
    log, cases = tmp_path / "learn.jsonl", tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{"model": "Building", "q": "x", "phrase": "Knocked About",
                                            "slot": "property", "expect": None}]}))
    _log(log, dict(model="Building", question="q", phrase="knocked about", slot="property"))
    props = learn.proposals(log, BUNDLE, exclude=cases)
    assert props["to_assign"] == [] and props["skipped"]["held_out"] == 1


def test_one_phrase_picked_as_two_things_waits_for_a_person(tmp_path):
    log = tmp_path / "learn.jsonl"
    a = {"node": "architect", "qualifier": None, "end_node": None, "label": "Architect"}
    b = {"node": "actor", "qualifier": "Builder", "end_node": None, "label": "Actor (Builder)"}
    _log(log, dict(model="Building", question="q1", phrase="done by", slot="link:Person", chosen=a),
         dict(model="Building", question="q2", phrase="done by", slot="link:Person", chosen=b))
    props = learn.proposals(log, BUNDLE)
    assert len(props["confirmed"]) == 2
    assert all(p["approve"] is False and p["conflict"] for p in props["confirmed"])


def test_merge_adds_approved_phrasings_to_the_right_entries(tmp_path):
    vocab = tmp_path / "vocab"
    vocab.mkdir()
    (vocab / "Building.json").write_text(json.dumps(
        {"model": "Building", "entries": BUNDLE["models"]["Building"]["entries"]}))
    props = {"format": learn.PROPOSALS, "skipped": {},
             "confirmed": [{"model": "Building", "phrase": "drafted by", "node": "architect",
                            "qualifier": None, "end_node": None, "approve": True},
                           {"model": "Building", "phrase": "put up by", "node": "actor",
                            "qualifier": "Builder", "end_node": None, "approve": True},
                           {"model": "Building", "phrase": "ignored", "node": "architect",
                            "approve": False}],
             "to_assign": [{"model": "Building", "phrase": "listing", "slot": "property",
                            "assign": {"node": "heritage_status"}, "approve": True},
                           {"model": "Building", "phrase": "repainted", "slot": "date",
                            "assign": "none", "approve": True},
                           {"model": "Building", "phrase": "bogus", "slot": "property",
                            "assign": {"node": "no_such_node"}, "approve": True}]}
    p = tmp_path / "proposals.json"
    p.write_text(json.dumps(props))
    done = learn.merge(p, vocab, BUNDLE)
    assert done["added"] == 3 and done["new_entries"] == 1
    assert done["errors"] == ["Building: no node 'no_such_node' (for 'bogus')"]
    entries = json.loads((vocab / "Building.json").read_text())["entries"]
    by = {(e["node"], (e.get("qualifier") or {}).get("value")): e for e in entries}
    assert "drafted by" in by[("architect", None)]["phrases"]
    assert "put up by" in by[("actor", "Builder")]["phrases"]   # beside "built by", same role
    assert by[("heritage_status", None)] == {"phrases": ["listing"], "kind": "property",
                                             "node": "heritage_status"}
    assert not any("ignored" in e["phrases"] or "repainted" in e["phrases"] for e in entries)
    again = learn.merge(p, vocab, BUNDLE)
    assert again["added"] == 0 and again["already"] == 3      # merging twice changes nothing


def test_the_loop_end_to_end_on_arches_data(tmp_path):
    """try → log → learn → approve → merge → the next build places the phrase."""
    import arches_fixture as fx
    from ceist import config
    from ceist.arches import ArchesVocabulary
    from ceist.plan import interpret

    data = tmp_path / "data"
    data.mkdir()
    fx.write(data)
    shipped = {"format": "ceist.vocab/1", "models": {"Building": {
        "nodes": {"architect": {"kind": "link", "label": "Architect", "targets": ["Person"]}},
        "entries": [{"phrases": ["designed by"], "kind": "link", "node": "architect"}]}}}
    exact = config.chain(config.load(None, layers=["exact"]))
    q = "which buildings were drafted by Ada Lovelace?"
    m = interpret(ArchesVocabulary.from_data_dir(data, bundle=shipped), q, matcher=exact)
    log = tmp_path / "learn.jsonl"
    assert learn.from_grounding(log, q, m.grounding) == 1
    logged = log.read_text()
    assert "Ada" not in logged and "Lovelace" not in logged          # the record is masked
    assert "drafted by <Person>" in logged
    props = learn.proposals(log, shipped)
    (u,) = props["to_assign"]
    assert u["phrase"] == "drafted by" and u["slot"] == "link:Person" and "architect" in u["candidates"]
    u["assign"], u["approve"] = {"node": "architect"}, True  # the LLM proposes, a person approves
    p = tmp_path / "proposals.json"
    p.write_text(json.dumps(props))
    vocab = tmp_path / "vocab"
    vocab.mkdir()
    (vocab / "Building.json").write_text(json.dumps({"model": "Building",
                                                     "entries": shipped["models"]["Building"]["entries"]}))
    assert learn.merge(p, vocab, shipped)["added"] == 1
    rebuilt = json.loads(json.dumps(shipped))
    rebuilt["models"]["Building"]["entries"] = json.loads((vocab / "Building.json").read_text())["entries"]
    m = interpret(ArchesVocabulary.from_data_dir(data, bundle=rebuilt), q, matcher=exact)
    assert m.plan is not None and m.plan.where[0].relation == "architect"
    assert m.grounding.unplaced == []


def test_record_never_breaks_a_search(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("")
    learn.record(blocked / "learn.jsonl", "Building", "q", "p", "property")   # a file, not a folder
    assert _bundle.FORMAT == "ceist.vocab/1"


def test_mask_takes_record_data_out_of_the_question():
    assert learn.mask('Which buildings did "Smith & Sons" restore at 14 Acacia Avenue in 1890?') == \
        "Which buildings did <text> restore at <number> <Name> in 1890?"
    assert learn.mask("what was built in the 1850s by Isambard's firm?") == \
        "what was built in the 1850s by <Name> firm?"


def test_a_phrase_that_is_a_name_is_never_logged(tmp_path):
    class G:
        unplaced = [{"phrase": "victoria dock", "slot": "property", "model": "Building"},
                    {"phrase": "knocked about", "slot": "property", "model": "Building"}]
    log = tmp_path / "learn.jsonl"
    assert learn.from_grounding(log, "which buildings near Victoria Dock got knocked about?", G()) == 1
    (line,) = log.read_text().splitlines()
    ev = json.loads(line)
    assert ev["phrase"] == "knocked about" and "Victoria" not in ev["q"]


def test_the_learn_prompt_is_inline_and_assign_fills_it(tmp_path):
    log = tmp_path / "learn.jsonl"
    _log(log, dict(model="Building", question="which buildings were knocked about?",
                   phrase="knocked about", slot="property"),
         dict(model="Building", question="buildings drafted by <Person>?", phrase="drafted by",
              slot="link:Person"))
    props = learn.proposals(log, BUNDLE)
    text = learn.prompt(props, BUNDLE)
    assert "knocked about" in text and '"label": "Heritage status"' in text
    assert str(tmp_path) not in text and '"value": "Builder"' in text      # qualifiers inline
    i = {u["phrase"]: n for n, u in enumerate(props["to_assign"])}
    reply = json.dumps([{"i": i["drafted by"], "assign": {"node": "architect"}},
                        {"i": i["knocked about"], "assign": {"node": "architect"}},  # not a candidate
                        {"i": 9, "assign": "none"}])
    done, errors = learn.assign(props, reply)
    assert done == 1 and len(errors) == 2
    assert props["to_assign"][i["drafted by"]]["assign"] == {"node": "architect"}
    assert props["to_assign"][i["knocked about"]]["assign"] is None
    assert all(u["approve"] is False for u in props["to_assign"])          # a person approves


def test_assign_reports_a_malformed_reply_instead_of_crashing():
    props = {"to_assign": [{"phrase": "knocked about"}]}            # no candidates
    assert learn.assign(props, json.dumps({"i": 0, "assign": "none"})) == \
        (0, ["the reply is a JSON dict, not an array of items"])
    assert learn.assign(props, "nope")[1][0].startswith("the reply is not JSON")
    done, errors = learn.assign(props, json.dumps([7, {"i": 0, "assign": {"node": "x"}}]))
    assert done == 0 and errors == ["7 is not an item",
                                    "item 0 ('knocked about'): {'node': 'x'} is not one of its candidates"]


def test_mask_catches_a_name_that_starts_the_question():
    assert learn.mask("Brunel built which bridges?") == "<Name> built which bridges?"
    assert learn.mask("Which bridges did Brunel build?") == "Which bridges did <Name> build?"


class _Anchor:
    type, name, match_terms = "Person", "Ada Lovelace", ["ada", "lovelace"]


def test_a_logged_phrase_is_masked_like_the_question(tmp_path):
    class G:
        anchors = [_Anchor()]
        unplaced = [{"phrase": "ada lovelace", "slot": "property", "model": "Building"},
                    {"phrase": "knocked about by brunel", "slot": "property", "model": "Building"},
                    {"phrase": "victoria dock", "slot": "property", "model": "Building"}]
    log = tmp_path / "learn.jsonl"
    q = "Victoria Dock buildings ada lovelace saw knocked about by Brunel?"
    assert learn.from_grounding(log, q, G()) == 1
    (ev,) = [json.loads(line) for line in log.read_text().splitlines()]
    assert ev["phrase"] == "knocked about by <Name>"
    assert ev["q"] == "<Name> buildings <Person> saw knocked about by <Name>?"
