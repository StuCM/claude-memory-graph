"""`ceist setup` and `ceist ask`: a site's vocabulary from its own data dir, gated on its own questions;
value type words with site defaults, both paraphrase sources (a stub LLM), the audit and the estimate."""

import json
import sys

import arches_fixture as fx
import pytest
from fakes import FakeEncoder
from test_ontology import data  # noqa: F401  (the module fixture)
from test_vocab_rules import layers_dir

from ceist import cost, paraphrase, site
from ceist import vocab_rules as vr
from ceist.alizarin import Tiles
from ceist.audit import CLASSES, audit
from ceist.cli import main

needs_numpy = pytest.mark.skipif(not FakeEncoder.ready(), reason="needs numpy")

# a stub LLM: paraphrases the Listed and Candidate sentences, skips every fill element, logs each prompt
STUB = '''import json, sys
prompt = sys.stdin.read()
with open(sys.argv[1], "a") as f:
    f.write(prompt + "\\0")
if "SENTENCES:" in prompt:
    items = json.loads(prompt.split("SENTENCES:\\n", 1)[1].split("\\n\\nReply", 1)[0])
    out = []
    for s in items:
        if s["say"] == "Listed" and "whose heritage status is Listed." in s["sentence"]:
            out.append({"id": s["id"], "rewordings": [{"q": "which buildings are landmarks?",
                                                        "phrase": "landmarks"}]})
        elif s["say"] == "Candidate":
            out.append({"id": s["id"], "rewordings": [{"q": "how many buildings are hopefuls?", "phrase": "hopefuls"}]})
    print(json.dumps({"sentences": out}))
else:
    els = json.loads(prompt.split("ELEMENTS:\\n", 1)[1].split("\\n\\nReply", 1)[0])
    print(json.dumps({"elements": [{"key": e["key"], "skip": "nobody asks"} for e in els]}))
'''


@pytest.fixture
def site_dir(data, tmp_path):  # noqa: F811
    layers = layers_dir(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "about.md").write_text("Every grade two listing. A grade two listing is rare.\n")
    return data[0], layers, docs


def test_value_plurals_two_models_hold_go_only_to_the_site_default():
    cands = [{"layer": "client", "model": m, "node": "role", "value": "Hospital", "key": f"value {m}.role=hospital",
              "phrases": ["hospitals"]} for m in ("Building", "Organisation")]
    cands.append({"layer": "client", "model": "Building", "node": "role", "value": "Shelter",
                  "key": "value Building.role=shelter", "phrases": ["shelters"]})
    kept, dropped, ask = site.settle_type_words(cands, {})
    assert [c["key"] for c in kept] == ["value Building.role=shelter"] and ask == ["hospital"]
    assert "no site default" in dropped["value Organisation.role=hospital"]["hospitals"]
    kept, dropped, ask = site.settle_type_words(cands, {"hospital": "Building"})
    assert [c["key"] for c in kept] == ["value Building.role=hospital", "value Building.role=shelter"] and not ask
    assert dropped["value Organisation.role=hospital"]["hospitals"] == "site default: hospital means Building"


def test_a_role_noun_two_models_hold_goes_only_to_the_site_default():
    cands = [{"layer": "client", "model": m, "node": "keyholder_for", "kind": "link", "role": "keyholder",
              "key": f"role {m}.keyholder_for", "phrases": ["keyholders"]} for m in ("Person", "Organisation")]
    kept, dropped, ask = site.settle_type_words(cands, {})
    assert kept == [] and ask == ["keyholder"]
    assert "no site default" in dropped["role Person.keyholder_for"]["keyholders"]
    kept, dropped, ask = site.settle_type_words(cands, {"keyholder": "Person"})
    assert [c["key"] for c in kept] == ["role Person.keyholder_for"] and not ask
    assert kept == site.settle_type_words(cands[:1], {})[0]          # one model holds it: no default needed


def test_canonical_sentences_narrate_values_links_and_dates_with_their_targets(data):  # noqa: F811
    from ceist.arches import ArchesVocabulary
    v = ArchesVocabulary.from_data_dir(data[0])
    canon = paraphrase.canonical(v, Tiles(v))
    said = {c["sentence"]: c for c in canon}
    listed = said["Find Buildings whose heritage status is Listed."]
    assert listed["target"] == {"model": "Building", "count": False,
                                "conditions": [{"node": "heritage_status", "value": "Listed"}]}
    assert listed["element"]["key"] == "value Building.heritage_status=listed"
    assert any(c["element"]["key"] == "link Building.site" and c["target"]["conditions"][0]["link"] == "Site"
               for c in canon)
    assert any(c["element"]["key"] == "date Building.construction_date" for c in canon)


@needs_numpy
def test_bge_mining_proposes_the_sites_own_phrase_nearest_an_element_and_never_a_name(data, monkeypatch):  # noqa: F811
    from ceist.arches import ArchesVocabulary
    v = ArchesVocabulary.from_data_dir(data[0])
    canon = paraphrase.canonical(v, Tiles(v))
    monkeypatch.setattr(paraphrase, "MIN_SIMILARITY", 0.45)
    texts = ["the grade two listing", "a grade two listing", "Leeds grade ii", "Leeds grade ii"]
    got = paraphrase.mined(canon, texts, FakeEncoder(), {"grade ii"}, names={"leeds"})
    phrases = {c["phrases"][0]: c for c in got}
    assert phrases["grade two"]["value"] == "Grade II" and phrases["grade two"]["checks"][0]["q"] == \
        "how many grade two are there?"
    assert not any("leeds" in p for p in phrases)


def test_the_llm_paraphrase_check_wants_the_phrase_inside_the_rewording():
    batch = [{"id": 0}]
    assert paraphrase.check({"sentences": [{"id": 0, "rewordings": [{"q": "which are old?", "phrase": "old"}]}]},
                            batch) == []
    assert paraphrase.check({"sentences": [{"id": 0, "rewordings": [{"q": "which are old?", "phrase": "new"}]}]},
                            batch)
    assert paraphrase.check({"sentences": [{"id": 3}]}, batch) == ["unknown sentence 3"]


@needs_numpy
def test_setup_builds_the_client_layer_gated_on_the_sites_own_questions(site_dir, tmp_path, monkeypatch):
    data_dir, layers, docs = site_dir
    monkeypatch.setattr(paraphrase, "MIN_SIMILARITY", 0.45)
    out = tmp_path / "out"
    said = []
    rc = site.setup(data_dir, out, layers / "base", docs=docs, defaults={"Listed": "Building"},
                    encoder=FakeEncoder(), log=said.append)
    assert rc == 0
    bundle = json.loads((out / "bundle.json").read_text())
    report = (out / "setup.md").read_text()
    assert "| bge |" in report and "| rules |" in report
    assert "grade two" in report                                     # mined from the docs
    manifest = json.loads((out / "client" / "manifest.json").read_text())
    assert manifest["defaults"] == {"listed": "Building"}
    assert set(json.loads((out / "audit.json").read_text())["totals"]) == set(CLASSES)
    assert (out / "coverage.md").exists() and bundle["models"]["Building"]
    assert any(line.startswith("set up in") for line in said)
    assert any("Not sent: --llm not given" in line for line in said)


@needs_numpy
def test_setup_with_llm_stops_over_max_calls_and_sends_nothing(site_dir, tmp_path):
    data_dir, layers, _ = site_dir
    log = tmp_path / "prompts.log"
    stub = tmp_path / "stub.py"
    stub.write_text(STUB)
    said = []
    rc = site.setup(data_dir, tmp_path / "out", layers / "base", llm=True, llm_cmd=f"{sys.executable} {stub} {log}",
                    max_calls=0, encoder=FakeEncoder(), log=said.append)
    assert rc == 2 and not log.exists()
    assert any("claude -p adds its own system prompt" in line for line in said)


def test_setup_refuses_a_default_naming_no_model(site_dir, tmp_path):
    data_dir, layers, _ = site_dir
    said = []
    assert site.setup(data_dir, tmp_path / "out", layers / "base", defaults={"listed": "building"},
                      encoder=FakeEncoder(), log=said.append) == 2
    assert said[-1].startswith("--default names no model of this site: building")


@needs_numpy
def test_setup_with_llm_gates_each_paraphrase_on_its_own_rewording(site_dir, tmp_path, monkeypatch):
    data_dir, layers, _ = site_dir
    log = tmp_path / "prompts.log"
    stub = tmp_path / "stub.py"
    stub.write_text(STUB)

    def pipeline(graphs, out, reference, llm_cmd=None, model=None, layer=None, base=None, log=print):
        """The base route for the graph with no base: a type word for Site."""
        (base / fx.SITE).mkdir(parents=True)
        (base / fx.SITE / "manifest.json").write_text(json.dumps({"format": "ceist.vocab-groups/1",
                                                                   "type_words": ["venues"]}))
        return 0
    monkeypatch.setattr("ceist.pipeline.run", pipeline)
    out = tmp_path / "out"
    rc = site.setup(data_dir, out, layers / "base", llm=True, llm_cmd=f"{sys.executable} {stub} {log}",
                    encoder=FakeEncoder(), log=lambda *_: None)
    assert rc == 0
    prompts = log.read_text().split("\0")
    assert any("SENTENCES:" in p for p in prompts)
    assert not any("Leeds Dock" in p for p in prompts)               # no record names to the LLM
    report = (out / "setup.md").read_text()
    row = {line.split(" | ")[0].strip("| "): line for line in report.splitlines() if line.startswith("| value")
           or line.startswith("| type")}
    assert "accepted" in row["value Building.heritage_status=listed: landmarks"]
    assert "site gate" in row["value Building.heritage_status=candidate: hopefuls"]    # read as a count: rejected
    assert "accepted" in row["type Site: llm"]
    bundle = json.loads((out / "bundle.json").read_text())
    assert bundle["extra_type_words"]["venues"] == "Site"


def test_ask_prints_the_narration_the_count_and_a_refusal(data, capsys):  # noqa: F811
    assert main(["ask", str(data[0]), "how many listed buildings are there?"]) == 0
    out = capsys.readouterr().out
    assert "understood: Count Buildings whose heritage status is Listed." in out and "results: 2" in out
    assert main(["ask", str(data[0]), "which dragons breathe fire?"]) == 1
    assert capsys.readouterr().out.startswith("refused: ")


def test_the_audit_lists_each_class_with_a_fix_or_a_reason(site_dir, tmp_path):
    data_dir, layers, _ = site_dir
    from ceist.arches import read_resources
    L = vr.Layers([data_dir / "graphs"], layers / "base", tmp_path / "client", reference=data_dir / "vocabularies",
                  resources=read_resources(data_dir / "resources"))
    found = audit(L.vocab(), {}, {}, {"dock"})
    by = {k: {it["what"]: it for it in items} for k, items in found["classes"].items()}
    assert by["number, date and place fields"]["Building.construction_date (date)"]["status"] == "resolved"
    assert by["unphrased links"]["Building.site ('site')"]["status"] == "open"
    assert by["values and models with no type word"]["Building.heritage_status = Listed"]["reason"] == \
        "not a count noun"
    assert found["totals"]["unphrased links"] == len(by["unphrased links"]) > 0 and not found["set_up"]
    accepted = audit(L.vocab(), {}, {k: "accepted for the test" for k in CLASSES})
    assert accepted["set_up"]


def test_the_estimate_adds_claude_ps_system_prompt_per_call():
    line = cost.claude_p_overhead([(10, "opus")])
    assert "10 calls" in line and "+$0.07 if every call reads it" in line and "+$1.65 if every call writes it" in line


def test_a_mined_phrase_the_rules_already_propose_for_the_element_is_one_candidate():
    rule = {"key": "value Building.role=shelter", "phrases": ["shelters"]}
    mined = {"key": "value Building.role=shelter: shelters", "phrases": ["shelters"], "checks": [{"q": "x"}]}
    other = {"key": "value Building.role=shelter: refuges", "phrases": ["refuges"]}
    got = site.merged([rule, mined, other])
    assert [c["key"] for c in got] == ["value Building.role=shelter", "value Building.role=shelter: refuges"]
    assert got[0]["checks"] == [{"q": "x"}]


def test_the_site_gate_rejects_only_the_phrases_a_composition_reads_wrong_with():
    insurer = {"key": "link Insurance policy.insurer: llm", "phrases": ["insured by", "covered by", "issued by"]}
    policy = {"key": "type Insurance policy: llm", "phrases": ["policies", "contracts"]}
    wrong = "which contracts have fire station organisations as covered by the policy?"
    gate = object.__new__(site.SiteGate)
    gate.cands = [insurer, policy]
    gate.items = [{"q": wrong, "shape": "composition"}, {"q": "policies insured by Ada"}, {"q": "how many policies?"}]

    def scores(cs, only=None):
        said = {p for c in cs for p in c["phrases"]}
        return {("site", wrong): "wrong reading" if {"contracts", "covered by"} <= said else "refused",
                ("site", "policies insured by Ada"): "right" if "insured by" in said else "refused",
                ("site", "how many policies?"): "right" if "policies" in said else "refused"}

    gate.scores = scores
    gate.before = scores([])
    verdict = gate.run(log=lambda _: None)
    assert verdict["accepted"] == [insurer["key"], policy["key"]] and verdict["rejected"] == {}
    blame = f"site gate, together: {wrong}"
    # the element with more phrases loses its phrase first; then the other is fine beside it
    assert verdict["phrases"] == {insurer["key"]: {"covered by": blame}}
    assert verdict["after"] == {("site", wrong): "refused", ("site", "policies insured by Ada"): "right",
                                ("site", "how many policies?"): "right"}
