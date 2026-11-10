"""`ceist questions generate` with a fake LLM, and the structural score."""

import json
from types import SimpleNamespace

import pytest
from test_pipeline import project

from ceist import interpret, pipeline
from ceist.arches import ArchesVocabulary
from ceist.cli import main
from ceist.questions import check, fill, held_out, score

ON_SITE = {"q": "which listed buildings are on site {Site}?", "shape": "link", "wording": "direct",
           "target": {"model": "Building", "count": False, "conditions": [
               {"node": "heritage_status", "value": "Listed"}, {"node": "site", "link": "Site"}]}}
NOT_BY = {"q": "which buildings were not designed by {Person}?", "shape": "negation",
          "wording": "direct", "target": {"model": "Building", "conditions": [
              {"node": "architect", "link": "Person", "negated": True}]}}
COUNT = {"q": "how many buildings were built before 1900?", "shape": "date", "wording": "direct",
         "target": {"model": "Building", "count": True,
                    "conditions": [{"node": "construction_date"}]}}
STORY = {"q": "what happens in the story of {Building}?", "shape": "record detail",
         "wording": "awkward", "refuse": "story text"}
GENERATED = {"generate:Building": {"questions": [ON_SITE, NOT_BY, COUNT, STORY]}}


@pytest.fixture
def made(tmp_path):
    data, ref, cmd, ids = project(tmp_path, GENERATED)
    out = tmp_path / "out"
    assert main(["questions", "generate", str(data / "graphs"), "-o", str(out),
                 "--reference", str(ref), "--llm-cmd", cmd, "--per-model", "4"]) == 0
    vocab = ArchesVocabulary.from_data_dir(data, relation_forms={"architect": ["designed by"]},
                                           date_forms={"construction_date": ["built"]})
    return SimpleNamespace(data=data, ref=ref, cmd=cmd, ids=ids, out=out, vocab=vocab)


def generated(out) -> list[dict]:
    return [o for part in ("train", "holdout")
            for o in json.loads((out / f"{part}.json").read_text())["questions"]]


def test_a_generated_set_is_split_into_bank_files_with_targets(made):
    items = {o["q"]: o for o in generated(made.out)}
    assert set(items) == {ON_SITE["q"], NOT_BY["q"], COUNT["q"], STORY["q"]}
    assert items[ON_SITE["q"]]["expect"] == "answer" and items[ON_SITE["q"]]["target"] == ON_SITE["target"]
    assert items[STORY["q"]]["expect"] == "refuse" and items[STORY["q"]]["reason"] == "story text"
    holdout = [o["q"] for o in json.loads((made.out / "holdout.json").read_text())["questions"]]
    assert holdout == [q for q in items if held_out(q)]


def test_the_split_is_by_the_question_text_alone():
    qs = [f"which buildings were built before {1800 + i}?" for i in range(40)]
    first = [held_out(q) for q in qs]
    assert first == [held_out(q) for q in qs] and 0 < sum(first) < len(qs)
    assert held_out("Which buildings were built before 1801 ?") == held_out(qs[1])


def test_no_record_data_is_in_any_prompt(made):
    audit = (made.out / "audit.jsonl").read_text()
    assert '"kind": "generate"' in audit and "heritage_status" in audit and "Listed" in audit
    for leak in ["Clock Tower", "Grain Warehouse", "Boat Shed", "Leeds Dock", "Salts Mill",
                 "Ada Lovelace", "Isambard", "1845-06-01", "1872-03-15", *made.ids["ids"].values()]:
        assert leak not in audit, leak
    tiles = [t for f in (made.data / "resources").rglob("*.json")
             for r in json.loads(f.read_text())["business_data"]["resources"] for t in r["tiles"]]
    assert tiles and not any(t["tileid"] in audit for t in tiles)


def test_placeholders_are_filled_from_the_vocabularys_own_record_names(made):
    q = fill(ON_SITE["q"], made.vocab)
    assert q in ("which listed buildings are on site Leeds Dock?",
                 "which listed buildings are on site Salts Mill?")
    assert fill(ON_SITE["q"], made.vocab) == q
    assert fill(NOT_BY["q"], made.vocab).split(" by ")[1] in ("Ada Lovelace?", "Isambard Brunel?")
    assert fill(ON_SITE["q"], SimpleNamespace(names={}, ids_of=lambda t: set())) is None


def test_the_score_compares_the_plan_with_the_target(made):
    def scored(item, q=None):
        return score(item, interpret(made.vocab, q or fill(item["q"], made.vocab)))

    assert scored(ON_SITE) == "right"
    assert scored(NOT_BY) == "right"
    assert scored(COUNT) == "right"
    candidate = {**ON_SITE, "target": {**ON_SITE["target"], "conditions": [
        {"node": "heritage_status", "value": "Candidate"}, {"node": "site", "link": "Site"}]}}
    assert scored(candidate) == "wrong reading"
    unnegated = {**NOT_BY, "target": {"model": "Building", "conditions": [
        {"node": "architect", "link": "Person"}]}}
    assert scored(unnegated) == "wrong reading"
    assert scored({**COUNT, "target": {**COUNT["target"], "count": False}}) == "wrong reading"
    dropped = {**ON_SITE, "target": {**ON_SITE["target"], "conditions": [{"node": "site", "link": "Site"}]}}
    assert scored(dropped) == "wrong reading"                     # the plan holds one more
    painted = "which buildings were painted by elves?"
    assert scored(COUNT, painted) == "refused"
    assert scored(STORY, painted) == "right refusal"
    assert scored(STORY, fill(ON_SITE["q"], made.vocab)) == "wrong"


def test_a_reply_naming_a_record_or_an_unknown_field_is_rejected(made):
    descriptions = {p.stem: json.loads(p.read_text()) for p in (made.out / "descriptions").glob("*.json")}
    assert check({"questions": [ON_SITE, NOT_BY, COUNT, STORY]}, descriptions) == []
    errors = check({"questions": [
        {**ON_SITE, "q": "which listed buildings are on site Leeds Dock?"},
        {**ON_SITE, "q": "which buildings are in {Town}?"},
        {**COUNT, "target": {"model": "Building", "conditions": [{"node": "colour"}]}},
        {**ON_SITE, "target": {"model": "Building", "conditions": [
            {"node": "heritage_status", "value": "Lovely"}]}},
        {**STORY, "target": ON_SITE["target"]}]}, descriptions)
    assert [e.split(":")[0] for e in errors] == [f"question {i}" for i in range(5)], errors


def test_the_refine_loop_takes_a_generated_train_and_holdout(made, tmp_path):
    client = tmp_path / "client"
    client.mkdir()
    rc = pipeline.run(made.data / "graphs", tmp_path / "refine", made.ref, made.out / "train.json",
                      llm_cmd=made.cmd, layer="data", client=client, rounds=1,
                      holdout=made.out / "holdout.json", log=lambda _: None)
    assert rc == 0
    # placeholders are not filled in the loop: the train set is read as written
    assert "| 0 | 0 | 1 | 0 | 1 | 1 | 0 | 0 | first build |" in (tmp_path / "refine" / "report.md").read_text()
