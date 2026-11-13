"""The link catalogue: each link's real targets, its inverse, join records; and the planner using it.

A small data set shaped like Phil's: its links name no target model, so the records say.
"""

import json

import pytest
from arches_fixture import _graph, _id, _node

from ceist import bundle, catalogue
from ceist.arches import ArchesVocabulary
from ceist.plan import interpret

PERSON, BUILDING, ORG, COVERAGE, POLICY, HAZARD = (_id(f"cat/{n}") for n in (
    "person", "building", "org", "coverage", "policy", "hazard"))


def link(g, alias, schema=None):
    return _node(g, alias, alias.replace("_", " ").title(), "resource-instance",
                 {"graphs": [{"graphid": schema}]} if schema else {})


def string(g, alias):
    return _node(g, alias, alias.title(), "string")


def graphs():
    docs = {
        PERSON: _graph(PERSON, "Person", [string(PERSON, "name"), string(PERSON, "born"),
                                          string(PERSON, "email"), link(PERSON, "employer"),
                                          link(PERSON, "keyholder_for")]),
        BUILDING: _graph(BUILDING, "Building", [string(BUILDING, "name"), string(BUILDING, "address"),
                                                string(BUILDING, "grade"), link(BUILDING, "keyholder"),
                                                link(BUILDING, "managed_by", ORG)]),
        ORG: _graph(ORG, "Organisation", [string(ORG, "name"), string(ORG, "address"), string(ORG, "kind"),
                                          link(ORG, "occupies"),
                                          link(ORG, "parent_org")]),
        COVERAGE: _graph(COVERAGE, "Insurance coverage", [
            string(COVERAGE, "coverage_id"), link(COVERAGE, "part_of_policy"), link(COVERAGE, "insured_building")]),
        POLICY: _graph(POLICY, "Insurance policy", [string(POLICY, "name"), link(POLICY, "superseded_by")]),
        HAZARD: _graph(HAZARD, "Hazard footprint", [string(HAZARD, "name")]),
    }
    return [d["graph"][0] for d in docs.values()]


def records(gs):
    node = {g["graphid"]: {n["alias"]: n["nodeid"] for n in g["nodes"]} for g in gs}
    made = {}

    def resource(gid, key, **data):
        rid = made[key] = _id(f"cat/resource/{key}")
        return {"resourceinstance": {"resourceinstanceid": rid, "graph_id": gid, "name": key},
                "tiles": [{"tileid": _id(f"cat/tile/{key}/{a}"), "nodegroup_id": node[gid][a],
                           "data": {node[gid][a]: v}} for a, v in data.items()]}

    def to(*keys):
        return [{"resourceId": _id(f"cat/resource/{k}")} for k in keys]

    return [resource(PERSON, "ada", employer=to("acme"), keyholder_for=to("hall", "mill")),
            resource(ORG, "acme", occupies=to("hall"), parent_org=to("acme")),
            resource(BUILDING, "hall", keyholder=to("ada")),
            resource(BUILDING, "mill", keyholder=to("ada")),
            resource(COVERAGE, "cover", part_of_policy=to("pol"), insured_building=to("hall")),
            resource(POLICY, "pol", superseded_by=to("pol"))]


@pytest.fixture
def vocab():
    gs = graphs()
    return ArchesVocabulary(gs, resources=records(gs))


def test_a_link_takes_its_targets_from_the_schema_then_the_records_then_the_crm_class(vocab):
    assert vocab.ends_of("Building", "managed_by") == (frozenset({"Organisation"}), "schema")
    assert vocab.ends_of("Person", "keyholder_for") == (frozenset({"Building"}), "records")
    assert vocab.ends_of("Person", "employer") == (frozenset({"Organisation"}), "records")
    assert vocab.ends_of("Organisation", "parent_org") == (frozenset({"Organisation"}), "records")
    bare = ArchesVocabulary(graphs())
    assert bare.ends_of("Organisation", "parent_org") == (frozenset(), "crm")      # no class, no records
    bare._crm["Organisation"] = ("E74", {"parent_org": "E74"})
    bare._crm["Person"] = ("E21", {})
    assert bare.ends_of("Organisation", "parent_org") == (frozenset({"Organisation"}), "crm")


def test_the_catalogue_gives_each_link_its_inverse_and_marks_join_records(vocab):
    links = catalogue.build(vocab)
    assert links["Person.keyholder_for"] == {"targets": ["Building"], "from": "records",
                                             "inverse": "keyholder", "join": False}
    assert links["Building.keyholder"]["inverse"] == "keyholder_for"
    assert links["Person.employer"]["inverse"] is None           # Organisation holds nothing back to Person
    assert links["Insurance coverage.part_of_policy"]["join"] is True
    assert links["Insurance coverage.insured_building"]["targets"] == ["Building"]
    assert not any(e["join"] for k, e in links.items() if not k.startswith("Insurance coverage"))


def test_relations_carry_the_catalogue_so_a_link_joins_only_what_it_points_at(vocab):
    keyholder_for = next(r for r in vocab.relations() if r.name == "keyholder_for")
    assert keyholder_for.targets("Person") == {"Building"}
    assert keyholder_for.joins("Person", "Building")
    assert not keyholder_for.joins("Person", "Organisation")


def test_a_bundle_carries_the_catalogue_to_a_vocabulary_without_records(tmp_path, vocab):
    gs = graphs()
    out, _ = bundle.layered(gs, tmp_path / "base", records=records(gs))
    assert out["format"] == "ceist.vocab/3" and out["links"] == catalogue.build(vocab)
    bare = ArchesVocabulary(gs, bundle=out)
    assert bare.catalogued and bare.ends_of("Person", "keyholder_for") == (frozenset({"Building"}), "records")
    assert "links" not in bundle.layered(gs, tmp_path / "base")[0]


def test_a_v2_bundle_still_loads_with_no_catalogue(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"format": "ceist.vocab/2", "models": {}}))
    old = ArchesVocabulary(graphs(), bundle=path)
    assert not old.catalogued
    assert old.ends_of("Person", "keyholder_for") == (frozenset(), "crm")


def test_two_types_no_link_connects_are_refused_saying_so(vocab):
    linked = vocab.with_bundle({"format": "ceist.vocab/3", "models": {}, "links": catalogue.build(vocab)})
    out = interpret(linked, "which hazard footprints have the employer Acme?")
    assert "'Hazard footprint' and 'Organisation' aren't linked in this data" in out.refused
    # linked types are answered, and a vocabulary with no catalogue gives no such reason
    assert interpret(linked, "which persons have the employer Acme?").plan is not None
    assert "aren't linked" not in interpret(vocab, "which hazard footprints have the employer Acme?").refused
