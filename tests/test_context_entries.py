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


def test_block_scalar_value_is_the_body_not_the_indicator():
    """`key: >` and `key: |` were parsed as the literal value ">" while the
    indented body below was silently dropped — half the descriptions in a real
    graph ended up as a bare marker. The body IS the value."""
    entries = parse(
        "- [10:00] Discovery: how the thing is wired\n"
        "  description: >\n"
        "    Where the triple is declared and how the versions\n"
        "    interlock. Python side: pyproject.toml.\n"
        "  rationale: |\n"
        "    kept because the alternative needs a fork\n"
        "  aliases: one, two\n",
        "t.md",
    )
    (entry,) = entries
    assert entry.properties["description"] == (
        "Where the triple is declared and how the versions "
        "interlock. Python side: pyproject.toml."
    )
    assert entry.properties["rationale"] == "kept because the alternative needs a fork"
    assert entry.properties["aliases"] == "one, two"   # one-line values unaffected


def test_block_scalar_body_ends_at_dedent_and_never_stores_the_marker():
    """A block must not swallow the next entry, and an empty one stores
    nothing rather than a stray '>'."""
    entries = parse(
        "- [10:00] Discovery: first\n"
        "  description: >\n"
        "    the body\n"
        "- [10:01] Decision: second\n"
        "  rationale: because\n"
        "  description: >\n",
        "t.md",
    )
    first, second = entries
    assert first.properties["description"] == "the body"
    assert second.name == "second"
    assert second.properties["rationale"] == "because"
    assert "description" not in second.properties


def test_capitalised_prose_line_does_not_invent_a_property():
    """'  Symptom: the page 500s' is a narrative line, not a property. Keys are
    lowercase by convention, so anything capitalised is prose — it used to
    become a property and a junk predicate in the ontology namespace."""
    (entry,) = parse(
        "- [10:00] Discovery: the page breaks\n"
        "  description: the real property\n"
        "  Symptom: the page 500s under load\n"
        "  Stuart: \"I'm nervous running this\"\n"
        "  anchorPath: /srv/app/views.py\n",
        "t.md",
    )
    assert set(entry.properties) == {"description", "anchorPath"}
    assert entry.properties["anchorPath"] == "/srv/app/views.py"
