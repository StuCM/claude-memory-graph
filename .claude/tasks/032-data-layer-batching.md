---
id: 032
slug: data-layer-batching
status: approved
branch: crew/032-data-layer-batching
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/
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

## Graph writes proposed

## Review rounds
