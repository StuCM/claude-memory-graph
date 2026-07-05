# Task: grounding-coverage experiment

Status: **harness ready — awaiting real data** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Run the grounder over real prompts and report: % of prompts with any graph match, % of
question-shaped prompts fully groundable. **This number is the go/no-go** for the query
planner's v0 grammar and the POS-tagger/stemmer decision — measure before building more.

## The harness (built: [gate/coverage.py](../../claude_memory_graph/gate/coverage.py))

Every content word of every prompt is assigned one category, in precedence order:
`wh` → `model` (names a resource model: "decisions") → `relation` (inside a matched verb-form
phrase: "works on") → `alias` → `entity` (node names/labels) → `modifier` (recent, active, …)
→ **`leftover`** (the graph has no idea — the number that matters). The report gives coverage
buckets for question-shaped vs all prompts, category totals, the **top-leftover work order**
(the exact missing vocabulary, ranked), and the planner-ready question sample.

## How to run (when you have a few days of real sessions)

```sh
# easiest: your real Claude Code transcripts (user prompts are extracted,
# command/meta noise skipped) — run against your real store
claude-memory-graph coverage --transcripts ~/.claude/projects

# or a hand-picked prompt file (one per line), or both
claude-memory-graph coverage --prompts my-questions.txt

# scope to one project's transcripts
claude-memory-graph coverage --transcripts ~/.claude/projects/-home-stuart-myproject
```

Read-only, deterministic, no LLM. Point `MEMORY_GRAPH_PATH` elsewhere to test against a
different store.

## How to read the results — the decision table

| Observation | Decision it drives |
|---|---|
| Question-shaped fully-grounded % is high (≳60%) | planner v0's small grammar is enough — build it |
| Leftovers dominated by *inflections* of known words (saving/save, deciding/decide) | add a light stemmer to `text.py` (now evidence-backed) |
| Leftovers dominated by *unknown domain words* | capture-side fix: aliases / concept links / more distillation — no code change |
| Leftovers dominated by *verb phrasings* | extend `verbForms` in base.ttl (each is a one-line fix) |
| Few question-shaped prompts at all | ambient gate matters more than the planner — reprioritise |

Re-run after each fix round; the leftover list should shrink toward proper nouns the graph
genuinely doesn't know yet.

## Validation so far

10 tests over a fixture store (categorisation per class, question-shape detection, transcript
extraction incl. noise filtering, report format). The harness's first synthetic run already
paid for itself: it flagged bare verb forms ("affect" vs "affects") missing from the base
lexicon — fixed in base.ttl the same commit.

## Test

pytest: `tests/test_coverage.py`.
