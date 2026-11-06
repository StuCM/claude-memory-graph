---
id: 013
slug: refine-loop
status: done
branch: crew/013-refine-loop
model: opus
env: laptop
work: vocab-layers
depends: [012]
files:
  - packages/ceist/
gate: pass
gateSha: b52ef789fb0c1919b9c10223a6e6326d4e47f12d
gateAt: 2026-11-06T16:16:13.208Z
rounds: 1
---

# The pipeline refines the vocabulary by running Ceist on its own failures

## Goal
`ceist vocab pipeline … --rounds N` (default 0, meaning off) runs a refine loop after the first build.
1. Run the cases (the generated ones plus `--questions`, and the question bank format) through `interpret`, and collect:
   - refusals, with the words Ceist couldn't place;
   - wrong answers;
   - "did you mean" cases where the right field was a suggestion.
2. Send each failure to the LLM **masked** (record names replaced as at learn time), with the vocabulary entries of the candidate fields, and ask for phrase additions or removals.
3. Apply them and re-score. **Keep the round only if right answers go up and wrong answers do not.** Otherwise roll it back and stop.
4. **Hold-out questions** (`--holdout <file>`, for example `bench/demo/questions.json`) are never sent to the LLM. They are scored every round and reported. A round that makes a hold-out question wrong is rolled back.

The report shows each round's scores, what was added, and what was rolled back.

## Why now
Stu, 2026-11-06: "Is it useful during the training that the llm runs ceist to see what is refused and update as it trains?" Yes: today the pipeline scores once and stops.

## Background
- **Scoring exists:** the pipeline's gate (`pipeline.py`), and since 010 it scores qualified phrases honestly.
- **Masking exists** in learn (`learn.py`).
- **Caching exists:** the `cache/` keyed by prompt. A rolled-back round's calls are still cached.
- **Seeds and base phrases are never deleted by the loop;** removals apply only to phrases the loop itself added. With layers (011/012), the loop writes to the layer being built.
- **No live LLM in tests:** a stub `--llm-cmd` whose replies are scripted per round. Write the live command for Stu in Worker notes.

## Definition of done
- [ ] Unit tests with a scripted stub:
  - a round that fixes a refusal is kept;
  - a round that adds a wrong answer is rolled back;
  - a round that breaks a hold-out question is rolled back;
  - hold-out questions never appear in any prompt (assert on the audit).
- [ ] A dry run of `--rounds 2` against the demo with a stub is in Worker notes, with the report section.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- `packages/ceist/src/ceist/pipeline.py`: `refine()` (the loop), `REFINE_PROMPT`, `check_refine`, `_failure` (one failed question, masked with `learn.mask`/`_masked_phrase`, and its candidate fields: the expected node and conditions, the unplaced options, the fields of the unplaced slot, suggestion labels that name a node, and for a wrong answer the plan's fields), `_apply` (adds into `<edit dir>/<Model>/<nodegroup>.json` via `_write_group`; removes only phrases the loop added), `read_questions` (text or question-bank JSON; hold-out questions dropped), `judge_bank`. `planner_run`'s vocabulary building factored into `_vocabulary`/`_ends` and reused. `run()`/`run_data()` call the loop after the first build: the default and base layers edit `out/vocab` (so the base is written refined, after the gate); the data layer edits `--client`, scored through `bundle.layered`.
- `cli.py`: `--rounds N` (default 0), `--holdout bank.json`, `--records <business_data dir>`.
- `tests/test_pipeline.py`: kept round (and a removal of a phrase the loop didn't add is refused), wrong answer rolled back, hold-out broken rolled back + no hold-out question in any prompt (also proved failing when the hold-out filter is removed), data layer refined from bank questions.
- **Decided, spec silent:**
  - *Scoring a bank-format question* (no node to judge against, records' counts need Rós Madair): `refuse` → right if refused, else wrong; `answer` → right when the narration equals the bank's `understood` for a `status: right` item, wrong when it differs, "answered, unchecked" when the bank has no right reading. The keep rule counts right + answered-unchecked (else a refused question the loop fixes could never count); wrong is only what is checkably wrong. `answer-later` refusals are not sent as failures.
  - *`--records`* (new flag): business data read locally so the loop's scoring and masking know record names (anchors). Without it the demo's named questions all refuse and the hold-out check has no teeth; with it the hold-out scores 60 right at round 0, matching the bank. Never sent.
  - *`--questions` as a bank JSON* is scored as bank items (not LLM-labelled); a text file behaves as before. Questions also in the hold-out are dropped with a warning, and generated cases equal to a hold-out question are not scored or sent.
  - One refine call per round over all failures (cached by payload, which carries the round).
- **Dry run, `--rounds 2`, data layer against the demo, stub LLM** (`/home/stuart/.cache/tmp-013/dry/stub.py`: round 1 adds Tale.actor "mention(s)", round 2 adds "speak of", "killed"); training bank of 3 (one of them, "which tales feature Medb?", is in the hold-out and was dropped), client = copy of `bench/demo/vocab`, hold-out `bench/demo/questions.json`, `--records` data/resources:

```
| round | right | answered, unchecked | wrong | refused | hold-out right | hold-out answered | hold-out wrong | |
| 0 | 0 | 0 | 0 | 2 | 60 | 2 | 1 | first build |
| 1 | 0 | 1 | 0 | 1 | 60 | 2 | 1 | kept |
| 2 | 0 | 2 | 0 | 0 | 59 | 2 | 2 | rolled back |
Round 1, kept:
- added Tale.actor 'mention'
- added Tale.actor 'mentions'
Round 2, rolled back (hold-out turned wrong: who killed Cú Chulainn?):
- added Tale.actor 'speak of'
- added Tale.actor 'killed'
```
  The refine prompt carried `"q": "which tales mention <Figure>?"` with the Tale.actor and copyright_holder phrases; `grep -c` in audit.jsonl: Chulainn 0, Medb 0, Navan 0, "who killed" 0. The client copy differs from `bench/demo/vocab` only by "mention", "mentions".
- **Question bank:** before = after (no grounding change), exit 0: answer/right 60, answer/refused 1, refuse/right 6, refuse/wrong 1, answer-later/wrong 2, answer-later/refused-should-answer 17. questions.json unchanged.
- **HER plans / memory_ask:** no grounding, plan or vocabulary-loading change; `tests/test_planner.py` passes in the gate. `bench/her_plans.py` not run (needs an arches-her clone). No change for `memory_ask`.
- **Live command for Stu (not run).** From the worktree (or ceist-foundation after merge), with the 012 setup (`D`, `R` with `concepts/`), and a training bank that is not the hold-out:
  ```sh
  D=/home/stuart/git/personal/starches-demo/ask; R=$(mktemp -d); mkdir $R/concepts; ln -s $D/data/vocabularies/smr.xml $R/concepts/
  .venv-ceist/bin/ceist vocab pipeline $D/data/graphs -o ~/.cache/ceist-data-demo --reference $R \
    --questions <training bank or questions.txt> --layer data --client packages/ceist/bench/demo/vocab \
    --base vocabularies/base --rounds 3 --holdout packages/ceist/bench/demo/questions.json \
    --records $D/data/resources --jobs 2
  grep -c -e Navan -e 'Emain Macha' -e Chulainn ~/.cache/ceist-data-demo/audit.jsonl   # expect 0
  ```
  The loop needs failing training questions: a text `--questions` file gives the data layer none to score (only a bank JSON is scored there). The default/base pipelines score their generated cases, e.g. add `--rounds 3 --holdout …` to the 012 base command.
- Not done: the loop adds field phrases only, not value variants (so "forts"/"portal tombs" stay with the data layer's value pass); scoring uses the default matcher config unless `--config` is given (the demo answers with `ceist-bge.toml`).

## Graph writes proposed
- Decision: `ceist vocab pipeline --rounds N` refines the layer being built on its own failures: masked failures + candidate fields' phrases to the LLM, phrase adds/removes (removes only of loop-added phrases), kept only if right (+ unchecked answers) rises, wrong doesn't, and no hold-out question turns wrong; else rolled back and stop. Hold-out (`--holdout`, bank format) is scored every round, never sent.
- Pattern: a question-bank item is judged without counts by comparing the narration with the bank's `understood` for a status-right item; that needs the records loaded (`--records`), or every named question refuses.

## Review rounds
- Round 1: PASS. Minor, not acted on: a text `--questions` file gives the data-layer loop nothing to score (documented); a bank JSON whose items only partly carry `expect` drops the unlabelled ones from labelling in the default/base pipelines.
