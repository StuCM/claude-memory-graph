"""Mechanical distill: parse -> fold -> apply, refusing to residue."""

import pytest

from claude_memory_graph.distill import distill
from claude_memory_graph.store import MemoryStore

GOOD = """---
created: 2026-07-06T14:00
distilled: false
summary: "s"
---

## Key Points

- [14:32] Decision: Use pyoxigraph over rdflib
  rationale: native quad store beats rdflib
  affects: Project/claude-memory-graph
  concepts: rdf
  aliases: rdf store choice
"""

MIXED = GOOD + """- [15:00] Problem: flaky mtime test, fixed with utime
- [15:05] Decision: Ship without lockfile
  outcome: fine so far
"""


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "store")
    s.create_resource("Project", {"name": "claude-memory-graph"})
    s.save()
    return s


def test_clean_file_promoted_marked_archived(store, tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "claude-memory-graph__2026-07-06_14-00.md").write_text(GOOD)
    report = distill(store, directory=ctx)
    assert any("Decision 'Use pyoxigraph over rdflib'" in m for m in report.stored)
    assert report.linked == 2  # concept + affects
    assert report.residue == []
    assert report.archived == ["claude-memory-graph__2026-07-06_14-00.md"]
    assert not list(ctx.glob("*.md"))
    archived = ctx / "archive" / "claude-memory-graph__2026-07-06_14-00.md"
    assert "distilled: true" in archived.read_text()

    # the node is real, properly linked, and carries provenance
    gid, iri = store.find_resource("Decision", "Use pyoxigraph over rdflib")
    props = store.get_resource_properties(iri, gid)
    assert props["rationale"].startswith("native quad store")
    assert props["sourceContext"] == "claude-memory-graph__2026-07-06_14-00.md"
    assert props["aliases"] == "rdf store choice"
    linked = store.recall(iri, gid, 1).linked
    assert {lr.relation for lr in linked} == {"affects", "hasConcept"}


def test_residue_keeps_file_active(store, tmp_path):
    """Narrative bullets and rule violations go to residue; a file with
    residue stays active (not archived) for the /distill skill."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    path = ctx / "claude-memory-graph__2026-07-06_15-00.md"
    path.write_text(MIXED)
    report = distill(store, directory=ctx)
    # the good entry still promoted
    assert any("pyoxigraph" in m for m in report.stored)
    # 'Ship without lockfile' lacks rationale -> refused, not forced
    reasons = " | ".join(r for _, r in report.residue)
    assert "rationale" in reasons
    assert "narrative entry" in reasons
    assert report.archived == [] and path.exists()
    assert store.find_resource("Decision", "Ship without lockfile") is None


def test_unknown_relation_refused_to_residue(store, tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(
        "---\ndistilled: false\n---\n"
        "- [10:00] Decision: Adopt trunk-based flow\n"
        "  rationale: fewer merge stalls\n"
        "  blessedBy: Project/claude-memory-graph\n")
    report = distill(store, directory=ctx)
    reasons = " | ".join(r for _, r in report.residue)
    assert "blessedBy" in reasons  # ontology extension is the skill's call
    # node itself was still created
    assert store.find_resource("Decision", "Adopt trunk-based flow") is not None


def test_dry_run_writes_nothing(store, tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    path = ctx / "p__1.md"
    path.write_text(GOOD)
    report = distill(store, directory=ctx, dry_run=True)
    assert any("[dry-run]" in m for m in report.stored)
    assert store.find_resource("Decision", "Use pyoxigraph over rdflib") is None
    assert path.exists() and "distilled: false" in path.read_text()


def test_upsert_not_duplicate_on_rerun(store, tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(GOOD)
    distill(store, directory=ctx, keep=True)
    report = distill(store, directory=ctx, keep=True)  # second run: update path
    assert any(m.startswith("Updated") for m in report.stored)
