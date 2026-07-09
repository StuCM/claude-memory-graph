"""The shared entry parser: context-file bullets -> Entry objects."""

from claude_memory_graph.context_entries import (
    Entry, fold, frontmatter, parse, parse_file, undistilled_files,
)

SAMPLE = """---
created: 2026-07-06T14:00
distilled: false
summary: "pyoxigraph decision"
---

## Key Points

- [14:32] Decision: Use pyoxigraph over rdflib
  rationale: native quad store; rdflib named-graph handling too slow
  affects: Project/claude-memory-graph
  concepts: rdf, storage
  aliases: rdf store choice, oxigraph
- [14:40] Problem: encountered flaky mtime test, fixed with utime
- [15:10] Pattern: hook-kit state layout
  description: per-session JSON under ~/.claude/hook-kit/sessions
  kind: storage
  anchorPath: hook-kit/claude_hook_kit/state.py
  appliesTo: Project/claude-memory-graph

Some narrative paragraph that is not an entry.

- [15:30] Decision: Use pyoxigraph over rdflib
  outcome: shipped; 30x faster
"""


def test_parses_structured_entry():
    entries = parse(SAMPLE, source="f.md")
    e = entries[0]
    assert e.type == "Decision" and e.name == "Use pyoxigraph over rdflib"
    assert e.properties["rationale"].startswith("native quad store")
    assert ("affects", "Project", "claude-memory-graph") in e.links
    assert e.concepts == ["rdf", "storage"]
    assert e.properties["aliases"] == "rdf store choice, oxigraph"
    assert e.structured and e.promotable
    assert e.source == "f.md" and e.line == 9


def test_narrative_entry_is_not_promotable():
    entries = parse(SAMPLE)
    problem = entries[1]
    assert problem.type == "Problem" and not problem.structured
    assert not problem.promotable
    assert "flaky mtime" in problem.text


def test_property_value_with_slash_is_not_a_link():
    e = parse(SAMPLE)[2]
    assert e.properties["anchorPath"] == "hook-kit/claude_hook_kit/state.py"
    assert ("appliesTo", "Project", "claude-memory-graph") in e.links
    assert e.properties["kind"] == "storage"


def test_fold_latest_values_win_and_links_union():
    folded = fold([e for e in parse(SAMPLE) if e.promotable])
    d = folded[("Decision", "Use pyoxigraph over rdflib")]
    assert d.properties["outcome"] == "shipped; 30x faster"   # late entry merged
    assert d.properties["rationale"].startswith("native")     # early value kept
    assert ("affects", "Project", "claude-memory-graph") in d.links


def test_frontmatter_parsed():
    meta = frontmatter(SAMPLE)
    assert meta["distilled"] == "false"
    assert meta["summary"] == "pyoxigraph decision"


def test_undistilled_files_filter(tmp_path):
    (tmp_path / "p__1.md").write_text("---\ndistilled: false\n---\n")
    (tmp_path / "p__2.md").write_text("---\ndistilled: true\n---\n")
    (tmp_path / "q__1.md").write_text("---\ndistilled: false\n---\n")
    assert [f.name for f in undistilled_files(tmp_path, "p")] == ["p__1.md"]
    assert len(undistilled_files(tmp_path)) == 2


def test_parse_file_missing_is_empty(tmp_path):
    meta, entries = parse_file(tmp_path / "nope.md")
    assert meta == {} and entries == []
