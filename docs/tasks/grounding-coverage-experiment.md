# Task: grounding-coverage experiment

Status: **run (2026-09-09) — result below; verdict: NO-GO on planner composer work, and the
metric itself needs the node-naming fix first** · Owner: Stuart · Created: 2026-07-04 · Size: S

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

## Result (2026-09-09, 1048 prompts from ~/.claude/projects, 217 question-shaped)

```
question-shaped: fully grounded (>=90%): 103 (47%) · partial: 109 · weak: 5
all prompts:     fully grounded (>=90%): 429 (40%) · partial: 583 · weak: 36
category hits:   entity 17799 · leftover 6871 · alias 649 · relation 428 · model 233 · wh 141
```

**The headline number is not the finding.** Getting to it exposed two measurement faults and
one real defect in the graph, and the third is the one that matters.

1. **Alias unigram artefact (fixed here).** `_alias_tokens` flattened every alias phrase into
   words, so `fix broken graph properties` credited `fix`, `broken` and `properties`. That is
   2104 unigrams of mostly ordinary English. Multi-word aliases now ground as phrases, like
   verb forms already did. Effect: question-shaped full grounding 57% → 47%.
2. **Multi-word aliases almost never fire.** Only 51 of 1056 prompts contain any alias phrase
   verbatim, and most of those hits are the project name, which `entity` already covers.
   ROADMAP claims aliases are what "closes paraphrase"; on this corpus they close nothing.
   Same for verb forms: 66 of 132 patterns ever fired, and the top firers are `\buse\b`,
   `\bfix\b`, `\bunder\b`, `\blike\b`, `\bknow\b` — coincidental English, not relations.
3. **Node names are sentences, not names.** 2010 nodes, **mean 7.7 words per name, 1214 names
   of 6+ words**. So the `entity` vocabulary is 3158 words including `add`, `check`, `code`,
   `error`, `file`, `fix`, `run`, `test`. After fix (1) the same artefact simply reappeared one
   category over — `entity` hits jumped to 17799 because node names supply ordinary English too.

### Verdict

**No-go on composer work.** The gate was meant to answer "does a small grammar suffice?", and it
cannot: on this graph, a prompt word "grounds" mostly by coinciding with English inside a
sentence-shaped node name. Worse, the two categories that would tell the planner *what is being
asked* — `relation` and `model` — fire on 428 and 233 words out of ~26k. The graph can often
recognise what a prompt is **about**; it almost never recognises what is being **asked**. You
cannot compose SPARQL from that.

**Do first:** enforce the naming rule the distill skill already states ("a short, specific,
stable title"). It is the same class of problem as the structured-entry drift — the rule is
written down, nothing measures compliance, so it decays. Re-run this experiment afterwards; the
number only becomes meaningful once node names stop being sentences.

Also worth knowing: the leftover "work order" is a flat tail — 294 leftover words across 217
question-shaped prompts, top item appearing 5 times, and mostly ordinary verbs (`looking`,
`happening`, `causing`, `proceeding`). There is no concentrated missing vocabulary to go and
add. That is further evidence the metric, not the lexicon, is what needs work.
