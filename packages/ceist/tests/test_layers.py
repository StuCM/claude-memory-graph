"""A vocabulary in two layers: a base per graph id, and a client layer that only adds."""

import json

import arches_fixture as fx
import pytest

from ceist import DateRange, interpret
from ceist.arches import ArchesVocabulary, graph_doc
from ceist.bundle import layered

BASE = {"construction": {"model": "HER Building", "nodegroup": "construction", "entries": [
    {"phrases": ["put up", "erected"], "kind": "date", "node": "construction_date"}]},
        "phase": {"model": "HER Building", "nodegroup": "phase", "entries": [], "group": {
    "phrases": ["phase"], "nodes": {"phase_type": {"role": "type"}, "phase_date": {"role": "date"}},
    "combos": [{"phrases": ["burnt down"], "node": "phase_date", "set": {"phase_type": "Destruction"}}]}}}


def write(root, files: dict, manifest: dict | None = None):
    root.mkdir(parents=True)
    for path, doc in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(json.dumps(doc))
    if manifest is not None:
        (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def base(tmp_path, gid=fx.BUILDING):
    return write(tmp_path / "base", {f"{gid}/{g}.json": f for g, f in BASE.items()}
                 | {f"{gid}/manifest.json": {"type_words": ["edifices"]}})


def client(tmp_path, groups: dict, models: dict | None = None):
    files = {f"Building/{g}.json": dict({"model": "Building", "nodegroup": g, "entries": []}, **f)
             for g, f in groups.items()}
    return write(tmp_path / "client", files,
                 {"format": "ceist.vocab-groups/1", "models": models or {"Building": {}}})


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("layers")
    return root, fx.write(root, phases=True)


def graphs(data):
    return [graph_doc(p) for p in sorted((data[0] / "graphs").glob("*.json"))]


def test_a_client_layer_adds_to_the_base(data, tmp_path):
    c = client(tmp_path, {
        "architect": {"entries": [{"phrases": ["drawn up by"], "kind": "link", "node": "architect"}]},
        "phase": {"group": {"combos": [{"phrases": ["damaged"], "node": "phase_date",
                                        "set": {"phase_type": "Damage"}}]}}},
        {"Building": {"type_words": ["halls"]}})
    bundle, report = layered(graphs(data), base(tmp_path), c)
    assert report == []
    assert bundle["extra_type_words"] == {"edifices": "Building", "halls": "Building"}
    phase = bundle["models"]["Building"]["groups"]["phase"]
    assert [x["phrases"] for x in phase["combos"]] == [["burnt down"], ["damaged"]]
    v = ArchesVocabulary.from_data_dir(data[0], bundle=bundle)
    m = interpret(v, "which halls were put up before 1900?")
    assert m.plan.type == "Building" and m.plan.where[0].field == "construction_date"
    m = interpret(v, "which buildings were drawn up by Ada Lovelace?")
    assert m.plan.where[0].relation == "architect"


def test_a_client_phrase_that_would_change_a_base_one_is_reported_not_applied(data, tmp_path):
    c = client(tmp_path, {
        "architect": {"entries": [{"phrases": ["put up", "drawn up by"], "kind": "link",
                                   "node": "architect"}]},
        "phase": {"group": {"nodes": {"phase_type": {"role": "cause"}}}}},
        {"Building": {}, "Person": {"type_words": ["edifices"]}})
    bundle, report = layered(graphs(data), base(tmp_path), c)
    assert report == ["Building: 'put up' means construction_date in the base, architect in the client; "
                      "not applied",
                      "Building.phase: nodes phase_type is {'role': 'type'} in the base, "
                      "{'role': 'cause'} in the client; not applied",
                      "type word 'edifices' names Building already, Person in the client; not applied"]
    assert bundle["extra_type_words"] == {"edifices": "Building"}
    building = bundle["models"]["Building"]
    assert building["entries"][-1]["phrases"] == ["drawn up by"]
    assert building["groups"]["phase"]["nodes"]["phase_type"] == {"role": "type"}
    m = interpret(ArchesVocabulary.from_data_dir(data[0], bundle=bundle),
                  "which buildings were put up before 1900?")
    assert isinstance(m.plan.where[0], DateRange)


def test_the_base_is_found_by_graph_id_whatever_the_model_is_named(data, tmp_path):
    renamed = [dict(g, name={"en": "Edifice"}) if g["graphid"] == fx.BUILDING else g
               for g in graphs(data)]
    bundle, _ = layered(renamed, base(tmp_path))
    assert bundle["models"]["Edifice"]["entries"][0]["phrases"] == ["put up", "erected"]
    assert bundle["models"]["Edifice"]["groups"]["phase"]["phrases"] == ["phase"]


def test_a_client_names_the_base_graph_when_its_own_id_differs(data, tmp_path):
    c = client(tmp_path, {}, {"Building": {"base": "her-building"}})
    bundle, _ = layered(graphs(data), base(tmp_path, gid="her-building"), c)
    assert bundle["models"]["Building"]["graphid"] == fx.BUILDING
    assert bundle["models"]["Building"]["entries"][0]["node"] == "construction_date"
