---
id: 032
slug: data-layer-batching
status: done
branch: crew/032-data-layer-batching
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/
gate: pass
gateSha: ed594ec12e51d041f9ae08a65cb7434f5c6aefc5
gateAt: 2026-11-08T12:53:31.174Z
rounds: 1
---

# The data layer sends each distinct list once, in batches, and a base run with no answers refuses

## Goal
1. **Each distinct list once:** task 030's estimate found the HER data layer would make about 1,810 calls (roughly $41 at Sonnet), because every list *field* is sent as its own call: 1,325 fields, but only 480 distinct lists. Send each distinct list (collection) once, and map its phrasings back to every field that uses it.
2. **Batch small lists:** several small lists go in one call, up to a token budget. Large lists are still split into label batches (100 labels, as today).
3. **A base run where every call fails** currently passes its gate and writes an unchanged base. Make it fail clearly: report the failed calls, and write nothing. The same goes for the data layer.
4. **The estimate follows:** `ceist vocab estimate` (task 030) must count the new calls. Report HER, Catalina and the demo before and after.

## Why now
Found by task 030 (2026-11-08). Stu wants the whole training process repeatable and costed before it runs.

## Background
- **Read first:** 012's and 030's Worker notes. Code: `pipeline.py` data layer, `arches_describe.collection_labels`, `cost.plan`.
- **Privacy is unchanged:** labels only, never records. The audit test must still pass.
- **No live LLM calls.** Stubs only.

## Definition of done
- [ ] Unit tests with a stub:
  - two fields sharing one list make one call, and both get the phrasings;
  - small lists are batched;
  - an all-failed base or data run fails and writes nothing;
  - the estimate equals the stub run's calls.
- [ ] `ceist vocab estimate --stages data` before and after for HER, Catalina and the demo, in Worker notes.
- [ ] The demo question bank exits 0. The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-032`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

### What changed
- `src/ceist/pipeline.py`: `value_calls(d, seeds)` (new) groups a model's list fields by their labels, so each distinct list goes once with every field that uses it, keyed by its first field's alias; small lists (≤ BATCH labels) are packed into one call up to `VALUE_BUDGET` = 1500 tokens (characters / 4 of the list entries), a long list still goes alone in batches of BATCH = 100. `value_variants` sends `{model, about, lists: {key: {fields, labels, seed}}, others, questions}` and writes each label's variants as a one-value combo for every field of the list, in that field's nodegroup (a field keeps its own seeds). `others` = small-list siblings of the call's nodegroups not already in the call. `check_values` takes the lists; a combo must set a field of the lists, use labels of each alias's own list, and stay in one nodegroup. `VALUE_PROMPT` reworded for lists.
- `Runner.answered` and `Runner.all_failed()` (failures, and nothing answered by the LLM or the cache). Base: the gate fails with "every LLM call failed (N)", so no base is written; the report lists the failed calls (as before). Data: `run_data` holds its group writes until the loop ends; all failed → report "Every LLM call failed (N): nothing written", client folder and manifest untouched, exit 1. A partly failed data run still writes and exits 1, as before. `_data_report` factored out for both exits.
- `cost.plan` unchanged: it calls `value_variants` with its dry Runner, so the estimate follows.
- `tests/test_pipeline.py`: FAKE keys values calls by their lists; the data-layer test reads the new payload (keys `model/about/lists/others/questions`, list keys `fields/labels/seed`, privacy greps unchanged). New: a shared list is sent once and both fields get the variants (seed kept, cross-nodegroup combo refused); small lists packed to the budget and a long one split, siblings as `others`; an all-failed base run (`--llm-cmd false`) fails and writes no base; an all-failed data run fails and leaves the client byte-identical. Both all-failed tests fail on the old pipeline.py.
- `tests/test_cost.py`: the estimate-vs-stub test parametrized over BATCH 2 (3 values calls) and 100 (1, both lists packed).

### Decided, spec silent
- **"Distinct" is per model** (lists with the same labels, which stands for the collection; no `arches_describe` change needed). That is the 480 the spec counts. Across models HER has only **94** distinct lists (16,595 labels, against 72,551 per model): sending each once per run would cut the data layer much further, but needs a prompt over several models and per-model seeds/combos. Not done; a next task if wanted.
- Combos still come from the call: fields packed together plus `others`, kept in one nodegroup (they are written as that nodegroup's group combos).

### Estimate, `ceist vocab estimate <graphs> --reference <ref> --stages data` (chars / 4, 2000 out per call, Sonnet)

| set | before calls | before input | before $ | after calls | after input | after $ |
| --- | --- | --- | --- | --- | --- | --- |
| demo | 8 | 6,148 | $0.17 | 4 | 4,059 | $0.09 |
| HER | 1,810 | 2,258,108 | $40.72 | 403 | 1,043,470 | $10.15 |
| Catalina | 2,287 | 2,742,895 | $51.23 | 516 | 1,297,081 | $12.91 |

HER at other budgets: 600 → 528 calls (max 115 labels a call), 1000 → 444, 1500 → 403 (max 278), 3000 → 362. Most of what remains is long lists in 100-label batches. Caveat: the 2000-token reply default is per call, and a packed call can carry up to ~280 labels, so output is likely understated until a real run's ledger sizes it (`--ledger`).

### Checks
- Demo bank (worktree PYTHONPATH): exit 0; answer/right 71, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 11. No question-time code changed.
- Gate passed on ed594ec: root 634 passed (51 skipped, 1 deselected); Ceist 330 passed.
- No change to ground.py, plan.py, rosmadair.py, bundle.py or any vocabulary; nothing reaches `memory_ask`. No live LLM run.

## Graph writes proposed
- Decision (ceist data layer): values calls send each distinct list of a model once (keyed by its first field, with every field that uses it), small lists packed to VALUE_BUDGET (1500 tokens), long lists in batches of BATCH (100); variants are written for every field of the list. HER 1810 → 403 calls ($40.72 → $10.15 estimated).
- Pattern (ceist pipeline): a run whose every LLM call failed (`Runner.all_failed()`: failures and nothing answered, cache included) fails and writes nothing: base via the gate, data by holding its writes until the loop ends.
- Finding: HER has 94 distinct lists across models (16,595 labels) vs 480 per model (72,551); cross-model dedupe is the next cut.

## Review rounds
- Round 1 (ed594ec): PASS. No findings; reviewer noted cross-model dedupe (94 lists) as a possible follow-up, not a question.
