# Task: memory_search — fuzzy entry-point finder

Status: **done — memory_search MCP tool + `claude-memory-graph search` CLI; reuses the gate's corpus/IDF/phrase scoring (one matcher, two consumers); concepts included as entry points** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

`memory_search(text, model?)` MCP tool + CLI subcommand: match free text against node
names, labels, aliases, and property text; return ranked, terse matches. Fixes the
exact-name cliff (recall needs exact model+name today).

## Notes

- v1: normalised token match + `CONTAINS` over literals — reuse/extend `names_similar`
  in [capture_rules.py](../../claude_memory_graph/capture_rules.py).
- Same primitive serves the write path: [[distill-two-pass-dedup]] and the duplicate
  guard should converge on it.
- Output: `Decision 'Use pyoxigraph over rdflib' — rationale: …` one line per hit, top 5.

## Test

pytest: exact hit, alias hit, property-text hit, model filter, no-match returns empty.
