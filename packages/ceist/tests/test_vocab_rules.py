"""`ceist vocab coverage / generate / fill`: the checklist per element, the rules that fill it
(CRM labels, morphology, base graph names, label splitting), review, the layers they write, and
the LLM fill on the gaps left, with a stub LLM."""

import json
import sys
from pathlib import Path

import arches_fixture as fx
from test_ontology import ONTOLOGY, data  # noqa: F401  (the module fixture)
from test_ontology_vocab import SOURCE, _gate

from ceist import vocab_rules as vr
from ceist.bundle import _add_class_words, layered

# a stub gate: called as <gate> <copy to> <candidates> --ontology …; passes all but the P14 ones
ACCEPT_ALL = '''import json, sys
cands = json.load(open(sys.argv[2]))
keys = [c["kind"] + " " + c["path"] if c.get("layer", "ontology") == "ontology" else c["key"] for c in cands]
with open(sys.argv[1], "w") as f:
    json.dump(cands, f)
print(json.dumps({"accepted": [k for k in keys if "P14" not in k],
                  "rejected": {k: "bench: adds no right answer" for k in keys if "P14" in k}, "checks": []}))
'''
FILL_STUB = '''import json, sys
prompt = sys.stdin.read()
with open(sys.argv[1], "a") as f:
    f.write(prompt + "\\0")
if "PATHS:" in prompt:
    paths = json.loads(prompt.split("PATHS:\\n", 1)[1].split("\\n\\nReply", 1)[0])
    print(json.dumps({"paths": [{"path": p["path"], "skip": "metadata"} for p in paths]}))
else:
    els = json.loads(prompt.split("ELEMENTS:\\n", 1)[1].split("\\n\\nReply", 1)[0])
    print(json.dumps({"elements": [{"key": e["key"], "phrases": ["zz " + e["key"].split(".")[-1]]}
                                   if "architect" not in e["key"] else {"key": e["key"], "skip": "nobody asks"}
                                   for e in els]}))
'''


def layers_dir(tmp_path, entries=ONTOLOGY["entries"]) -> Path:
    """vocabularies/ with the CRM source, the generic list and phrases.json; a base whose Person
    graph (the fixture's renamed Maker) keeps its own name; an empty client layer."""
    onto = tmp_path / "vocabularies" / "ontology" / "cidoc-crm"
    onto.mkdir(parents=True)
    (onto / "source").symlink_to(SOURCE)
    (onto / "generic.json").symlink_to(SOURCE.parent / "generic.json")
    (onto / "phrases.json").write_text(json.dumps({"format": "ceist.ontology/1", "entries": list(entries)}))
    base = tmp_path / "vocabularies" / "base"
    (base / fx.PERSON).mkdir(parents=True)
    (base / fx.PERSON / "manifest.json").write_text(json.dumps({"format": "ceist.vocab-groups/1", "model": "Person"}))
    (base / fx.BUILDING).mkdir()
    client = tmp_path / "client"
    client.mkdir()
    (client / "manifest.json").write_text(json.dumps({"format": "ceist.vocab-groups/1", "models": {}}))
    return tmp_path / "vocabularies"


def fixture_layers(data, tmp_path, entries=ONTOLOGY["entries"]):  # noqa: F811
    v = layers_dir(tmp_path, entries)
    return vr.Layers([data[0] / "graphs"], v / "base", tmp_path / "client", reference=data[0] / "vocabularies")


def items(elements, key):
    e = next(e for e in elements if e["key"] == key)
    return {(it["aspect"], it["phrase"]): (it["status"], it.get("reason", "")) for it in e["items"]}


def test_morphology_plurals_agent_nouns_of_forms_and_date_events():
    assert [vr.plural(w) for w in ("story", "person", "church", "copyright holder", "day")] == [
        "stories", "people", "churches", "copyright holders", "days"]
    assert vr.noun_forms("Heritage Story") == ["heritage story", "heritage stories"]
    assert vr.agent_verbs("Copyright Holder") == ["holds copyright", "hold copyright", "copyright held by"]
    assert vr.agent_verbs("occupier") == ["occupies", "occupy", "occupied by"]
    assert vr.agent_verbs("mother") == [] and vr.agent_verbs("actor") == []
    assert vr.of_forms("part of") == ["parts of"] and vr.of_forms("made of") == []
    assert vr.date_forms("Date of Death") == (["death date"], ["died", "die"])
    assert vr.date_forms("construction date") == (["date of construction"], ["built", "constructed"])
    assert vr.date_forms("Start Date") == ([], [])


def test_label_splitting_and_crm_labels_as_said():
    assert vr.head("Human-Made Object") == "object" and vr.head("Place") is None
    assert vr.unaux("is possessed by") == "possessed by"
    assert vr.unaux("has former or current keeper") == "former or current keeper"
    assert vr.sayable("occurred in the presence of") and not vr.sayable("carried out by")


def test_the_checklist_reads_class_and_property_words_from_the_crm_labels(data, tmp_path):  # noqa: F811
    els = vr.checklist(fixture_layers(data, tmp_path))
    assert items(els, "class E21") == {("class word", "person"): ("missing", ""),
                                       ("class word", "people"): ("missing", "")}
    e22 = items(els, "class E22")
    assert e22[("class word", "human-made object")] == ("missing", "")
    # label splitting: "object" ends many CRM class labels, so it would name several
    assert e22[("class word", "object")][1].startswith("label splitting: 'object' ends")
    assert items(els, "class E55")[("class word", "type")][1].startswith("no model's root is this class")
    p14 = items(els, "property P14")
    assert p14 == {("forward", "carried out by"): ("missing", ""), ("inverse", "who performed"): ("missing", "")}


def test_a_renamed_graph_gets_its_base_graphs_name_as_type_words(data, tmp_path):  # noqa: F811
    els = vr.checklist(fixture_layers(data, tmp_path))
    assert items(els, "type Maker") == {("type word", "maker"): ("present", ""), ("type word", "makers"): ("present", ""),
                                        ("type word", "person"): ("missing", ""), ("type word", "people"): ("missing", "")}
    # the fixture's date is labelled "Production date": its other order and its event's verbs
    assert items(els, "date Building.production_date") == {
        ("label", "production date"): ("present", ""), ("other order", "date of production"): ("missing", ""),
        ("verb", "made"): ("missing", ""), ("verb", "produced"): ("missing", "")}


def test_review_drops_a_phrase_that_could_name_two_elements(data, tmp_path):  # noqa: F811
    L = fixture_layers(data, tmp_path)
    cands = [{"layer": "base", "kind": "type", "model": "Maker", "key": "type Maker", "phrases": ["people", "buildings"]},
             {"layer": "base", "kind": "date", "node": "production_date", "key": "date Building.production_date",
              "phrases": ["made", "type"]},
             {"layer": "base", "kind": "date", "node": "phase_date", "key": "date Building.phase_date",
              "phrases": ["made"]},
             # a class word and a base type word for the same model don't compete
             {"layer": "ontology", "kind": "class", "path": "E21", "key": "class E21", "phrases": ["people", "maker"]}]
    dropped = vr.review(cands, L.vocab(), {"type"})
    assert dropped == {
        "type Maker": {"buildings": "could name two elements: already type Building"},
        "date Building.production_date": {"made": "could name two elements: also proposed for date Building.phase_date",
                                          "type": "too generic"},
        "date Building.phase_date": {"made": "could name two elements: also proposed for date Building.production_date"}}


def test_class_words_name_the_one_model_whose_root_is_that_class():
    graphs = [{"graphid": g, "nodes": [{"istopnode": True, "ontologyclass": "http://x/" + c}]}
              for g, c in (("a", "E21_Person"), ("b", "E53_Place"), ("c", "E53_Place"))]
    models = {"Maker": {}, "Site": {}, "Area": {}}
    ontology = {"entries": [{"path": "E21", "kind": "class", "phrases": ["person", "people", "site"]},
                            {"path": "E53", "kind": "class", "phrases": ["place", "places"]}]}
    words = {}
    report = _add_class_words(graphs, models, ontology, words)
    # "site" is the Site model's own name: never another model's type word
    assert words == {"person": "Maker", "people": "Maker"}
    assert report == ["class words place, places (E53) fit Site, Area; not applied"]


def test_generate_writes_what_the_gate_passes_and_records_why_not(data, tmp_path):  # noqa: F811
    L = fixture_layers(data, tmp_path)
    (tmp_path / "gate.py").write_text(ACCEPT_ALL)
    gated = tmp_path / "gated.json"
    out = tmp_path / "coverage"
    assert vr.generate(L, out, "fx", gate_cmd=[sys.executable, str(tmp_path / "gate.py"), str(gated)],
                       log=lambda *_: None) == 0
    sent = {c["key"] for c in json.loads(gated.read_text())}
    assert {"class E21", "type Maker", "property P14", "date Building.production_date"} <= sent
    phrases = json.loads((L.ontology_dir / "phrases.json").read_text())["entries"]
    assert {"path": "E21", "kind": "class", "phrases": ["person", "people"]} in phrases
    assert not any(e["path"] == "P14" for e in phrases)
    manifest = json.loads((L.base_dir / fx.PERSON / "manifest.json").read_text())
    assert manifest["type_words"] == ["person", "people"]
    entry = json.loads((L.base_dir / fx.BUILDING / "associated_actor.json").read_text())["entries"]
    assert entry == [{"phrases": ["date of production", "made", "produced"], "kind": "date", "node": "production_date"}]
    reasons = json.loads((out / "rules-fx.json").read_text())["reasons"]
    assert reasons["property P14"] == {"carried out by": "gate: bench: adds no right answer",
                                       "who performed": "gate: bench: adds no right answer"}
    report = (out / "rules-fx.md").read_text()
    assert "| ontology | class E21 | class word | person, people |" in report
    # the coverage after: what merged is present, what the gate turned down is set aside
    after = vr.checklist(vr.Layers(L.graph_dirs, L.base_dir, L.client_dir, reference=L.reference),
                         vr.read_reasons(out / "rules-fx.json"))
    assert items(after, "type Maker")[("type word", "people")] == ("present", "")
    assert items(after, "property P14")[("forward", "carried out by")] == ("set aside", "gate: bench: adds no right answer")
    v = vr.Layers(L.graph_dirs, L.base_dir, L.client_dir, reference=L.reference).vocab()
    assert v.type_words()["people"] == "Maker"


def test_apply_writes_a_value_variant_as_a_client_combo(tmp_path):
    client = tmp_path / "client"
    vr.apply([{"layer": "client", "model": "Monument", "nodegroup": "types", "node": "monument_type",
               "value": "Fort", "phrases": ["forts"]}], tmp_path, tmp_path, client)
    vr.apply([{"layer": "client", "model": "Monument", "nodegroup": "types", "node": "monument_type",
               "value": "Fort", "phrases": ["forts", "fortresses"]}], tmp_path, tmp_path, client)
    doc = json.loads((client / "Monument" / "types.json").read_text())
    assert doc["group"]["combos"] == [{"phrases": ["forts", "fortresses"], "set": {"monument_type": "Fort"}}]


def test_the_gate_counts_a_bank_question_turning_right_as_a_gain_not_a_change():
    gate = _gate()
    was = "refused -> refused: old one | x\n{'answer': 1}"
    now = ("refused -> refused: old one | x\nrefused -> right: how many people are there? | y\n"
           "right -> refused: which forts are there? | z\nrefused -> wrong: who died? | w\n{'answer': 2}")
    assert gate.worse_lines(was, now) == ["refused -> wrong: who died? | w",
                                          "right -> refused: which forts are there? | z"]


def test_a_base_type_word_adds_a_right_answer_on_the_bench_under_the_base(data, tmp_path):  # noqa: F811
    gate = _gate()
    v = layers_dir(tmp_path)
    cand = {"layer": "base", "kind": "type", "graphid": fx.PERSON, "model": "Maker", "key": "type Maker",
            "phrases": ["people"]}
    got = gate.one_set("her", str(data[0] / "graphs"), ONTOLOGY["entries"], [cand], False, v / "base")
    assert got == {"type Maker": (1, [])}


def test_fill_sends_only_the_gaps_the_rules_left_and_nothing_with_estimate(data, tmp_path):  # noqa: F811
    L = fixture_layers(data, tmp_path)
    (tmp_path / "stub.py").write_text(FILL_STUB)
    (tmp_path / "gate.py").write_text(ACCEPT_ALL)
    calls, gated, out = tmp_path / "calls.txt", tmp_path / "gated.json", tmp_path / "coverage"
    llm = f"{sys.executable} {tmp_path / 'stub.py'} {calls}"
    said = []
    assert vr.fill(L, out, "fx", llm, estimate=True, log=said.append) == 0
    assert not calls.exists() and "calls, about $" in said[0]
    assert vr.fill(L, out, "fx", llm, gate_cmd=[sys.executable, str(tmp_path / "gate.py"), str(gated)],
                   log=lambda *_: None) == 0
    prompts = calls.read_text().split("\0")[:-1]
    asked = [json.loads(p.split("ELEMENTS:\n", 1)[1].split("\n\nReply", 1)[0]) for p in prompts if "ELEMENTS:" in p]
    keys = {e["key"] for batch in asked for e in batch}
    # a gap is an element with an item no rule could phrase; a rule's missing item is generate's
    assert keys == {"link Building.actor", "link Building.architect", "link Building.site"}
    assert not any("Leeds Dock" in p or "Salts Mill" in p for p in prompts)
    entries = json.loads((L.base_dir / fx.BUILDING / "site.json").read_text())["entries"]
    assert entries == [{"phrases": ["zz site"], "kind": "link", "node": "site"}]
    reasons = json.loads((out / "rules-fx.json").read_text())["reasons"]
    assert reasons["link Building.architect"][""] == "the LLM skipped it: nobody asks"
