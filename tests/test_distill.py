"""Mechanical distill: parse -> fold -> apply, refusing to residue."""

import os
import time

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


def test_auto_distill_promotes_without_archiving(store, tmp_path, monkeypatch):
    """The startup lane: promote-only, idempotent, self-healing. Files stay
    active (never marked/archived headlessly); a second run duplicates
    nothing; the run is logged for pulse/dashboard."""
    import claude_hook_kit.state as kit_state
    from claude_hook_kit import state_home
    from claude_memory_graph.distill import auto_distill
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    path = ctx / "claude-memory-graph__2026-07-09_09-00.md"
    path.write_text(GOOD)
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(ctx))

    report = auto_distill(store)
    assert report is not None and report.stored
    assert store.find_resource("Decision", "Use pyoxigraph over rdflib") is not None
    assert path.exists() and "distilled: false" in path.read_text()  # never archived

    auto_distill(store)  # second startup: upserts, no twins
    gid, iri = store.find_resource("Decision", "Use pyoxigraph over rdflib")
    assert len(store.recall(iri, gid, 1).linked) == 2  # affects + concept, once

    import json
    lines = (state_home() / "capture.jsonl").read_text().strip().splitlines()
    assert all(json.loads(l)["kind"] == "distill" for l in lines) and len(lines) == 2


def test_auto_distill_disabled_by_env(store, tmp_path, monkeypatch):
    from claude_memory_graph.distill import auto_distill
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(GOOD)
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(ctx))
    monkeypatch.setenv("MEMORY_GRAPH_AUTO_DISTILL", "0")
    assert auto_distill(store) is None
    assert store.find_resource("Decision", "Use pyoxigraph over rdflib") is None


def test_memory_distill_mcp_tool(store, tmp_path, monkeypatch):
    """The in-session lane: memory_distill dispatches to the same code —
    sessions must never need the CLI (it isn't on PATH in plugin installs)."""
    from claude_memory_graph.tools import _dispatch
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "claude-memory-graph__2026-07-08_09-00.md").write_text(GOOD)
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(ctx))
    out = _dispatch(store, "memory_distill", {})
    assert "Created Decision 'Use pyoxigraph over rdflib'" in out
    assert store.find_resource("Decision", "Use pyoxigraph over rdflib") is not None
    out = _dispatch(store, "memory_distill", {"dry_run": True})
    assert "files: 0" in out  # first run archived the clean file


def test_upsert_not_duplicate_on_rerun(store, tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(GOOD)
    distill(store, directory=ctx, keep=True)
    report = distill(store, directory=ctx, keep=True)  # second run: update path
    assert any(m.startswith("Updated") for m in report.stored)


def test_name_with_a_quote_does_not_break_the_query(store):
    """Names are free text. An unescaped one used to be interpolated straight
    into SPARQL, so a single quote raised SyntaxError mid-distill."""
    from claude_memory_graph.tools.store_resource import handle_resource
    name = 'Why "Heritage Items" fail with a back\\slash'
    handle_resource(store, "Pattern", {"name": name, "description": "d"})
    assert store.find_resource("Pattern", name) is not None


HEADS = """---
created: 2026-07-06T14:00
distilled: false
summary: "s"
---

## Key Points

- [14:00] Problem: Buttons plugin cannot work on a dashboard
  description: clickHandler reads the active file, which a dashboard has none of
  concepts: obsidian
- [14:01] User preference: Root cause before workaround
  rationale: a symptom fix leaves every sibling caller broken
- [14:02] Scope: awaiting confirmation of which patch they meant
  description: session state, not durable knowledge
"""


def test_narrative_head_words_promote_to_the_model_they_mean(store, tmp_path):
    """The protocol's own examples say "Problem:" and "User preference:", so
    real logs are full of them; they carry a Decision entry's structure."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(HEADS)
    store.create_resource("Person", {"name": "Stuart"})
    report = distill(store, directory=ctx, keep=True)

    assert store.find_resource(
        "Pattern", "Buttons plugin cannot work on a dashboard") is not None
    assert store.find_concept("Preference", "Root cause before workaround") is not None

    # Session-state heads stay unmapped on purpose — the LLM lane decides.
    assert store.find_resource("Pattern", "awaiting confirmation of which "
                               "patch they meant") is None
    assert any("Scope" in reason for _, reason in report.residue)


def test_preference_is_attributed_to_the_only_person(store, tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(HEADS)
    store.create_resource("Person", {"name": "Stuart"})
    distill(store, directory=ctx, keep=True)
    graph_id, iri = store.find_resource("Person", "Stuart")
    recalled = store.recall(iri, graph_id, 1)
    assert any(l.relation == "hasPreference" for l in recalled.linked)


def test_preference_not_attributed_when_the_person_is_ambiguous(store, tmp_path):
    """Two people and no way to tell whose preference it is: store the
    concept, refuse the link, say why."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "p__1.md").write_text(HEADS)
    store.create_resource("Person", {"name": "Stuart"})
    store.create_resource("Person", {"name": "Phil"})
    report = distill(store, directory=ctx, keep=True)
    assert store.find_concept("Preference", "Root cause before workaround") is not None
    assert any("cannot attribute" in reason for _, reason in report.residue)


def test_overlong_concept_label_is_refused_not_stored(store, tmp_path):
    """Concept writes used to call store.store_concept directly, skipping
    check_name — which is why every over-long label in a real graph was a
    concept and never a resource. A narrative 'User preference:' head is a
    label, so it has to face the same 120-char rule and land in residue."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    sentence = (
        "the user wants every single one of these long narrative preference "
        "sentences written out in full as the node label rather than kept as "
        "a short stable title with the detail in properties where it belongs"
    )
    assert len(sentence) > 120
    (ctx / "p__2026-07-06_14-00.md").write_text(
        "---\ncreated: 2026-07-06T14:00\ndistilled: false\nsummary: \"s\"\n---\n\n"
        f"- [14:00] User preference: {sentence}\n"
        "  rationale: stated outright\n"
    )
    report = distill(store, directory=ctx)
    assert report.stored == []
    assert any("120 characters" in reason for _entry, reason in report.residue)
    assert store.find_concept("Preference", sentence) is None


# ============ age-based retirement (the auto lane) ============

def _aged(path, days=5):
    old = time.time() - days * 86400
    os.utime(path, (old, old))
    return path


def test_stale_clean_file_is_retired_by_the_auto_lane(store, tmp_path):
    """keep=True holds files back, but a clean file older than the window is
    finished — everything in it is in the graph, so it archives itself."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    f = ctx / "claude-memory-graph__2026-07-06_14-00.md"
    f.write_text(GOOD)
    _aged(f)
    report = distill(store, directory=ctx, keep=True, retire_after_days=2)
    assert report.archived == [f.name] and not f.exists()
    assert (ctx / "archive" / f.name).exists()


def test_fresh_file_is_kept_by_the_auto_lane(store, tmp_path):
    """mtime is what protects a live session's own log: it is written every
    few turns, so it never reaches the window."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    f = ctx / "claude-memory-graph__2026-07-06_14-00.md"
    f.write_text(GOOD)
    report = distill(store, directory=ctx, keep=True, retire_after_days=2)
    assert not report.archived and f.exists()


def test_stale_file_with_residue_is_not_retired(store, tmp_path):
    """Residue means an LLM pass is still owed — age must not lose it."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    f = ctx / "claude-memory-graph__2026-07-06_14-00.md"
    f.write_text(MIXED)
    _aged(f)
    report = distill(store, directory=ctx, keep=True, retire_after_days=2)
    assert report.residue and not report.archived and f.exists()


def test_stale_mixed_file_is_split_not_pinned(store, tmp_path):
    """Residue used to be per FILE, so one narrative bullet pinned a fully
    promoted log open forever. The unit is now the entry."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    f = ctx / "claude-memory-graph__2026-07-06_14-00.md"
    f.write_text(MIXED)
    _aged(f)
    report = distill(store, directory=ctx, keep=True, retire_after_days=2)

    assert report.split and report.split[0][0] == f.name
    assert f.exists(), "the file stays active — its residue still needs the skill"
    remaining = f.read_text()
    assert "flaky mtime test" in remaining          # the narrative bullet survives
    assert "Use pyoxigraph over rdflib" not in remaining  # the promoted one is gone
    assert "## Key Points" in remaining             # still a valid context file
    original = (ctx / "archive" / f.name).read_text()
    assert "Use pyoxigraph over rdflib" in original, "the original is preserved whole"


def test_split_output_reparses(store, tmp_path):
    """A split file must still be a context file: parseable, and its residue
    unchanged in meaning."""
    from claude_memory_graph.context_entries import parse_file
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    f = ctx / "claude-memory-graph__2026-07-06_14-00.md"
    f.write_text(MIXED)
    _aged(f)
    before = [e.name for e in parse_file(f)[1] if not e.structured]
    distill(store, directory=ctx, keep=True, retire_after_days=2)
    after = [e.name for e in parse_file(f)[1] if not e.structured]
    assert before == after and after


def test_fresh_mixed_file_is_left_alone(store, tmp_path):
    """Splitting a live session's log would rewrite the file underneath it."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    f = ctx / "claude-memory-graph__2026-07-06_14-00.md"
    f.write_text(MIXED)
    report = distill(store, directory=ctx, keep=True, retire_after_days=2)
    assert not report.split and f.read_text() == MIXED
