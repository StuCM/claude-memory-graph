---
id: 033
slug: ontology-build-automated
status: done
branch: crew/033-ontology-build-automated
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: b8b7b72a79f3c916fdda5f900c28c753eb2ae1e1
gateAt: 2026-11-08T13:07:02.989Z
rounds: 1
---

# The ontology vocabulary build runs end to end without hand review, and is written up as a playbook

## Goal
Stu, 2026-11-08: "make sure all these processes are recorded and becomes part of the pipeline so that I don't have to run through with you on every build."

1. **Automatic review of proposals** (`ceist vocab ontology --review`). It applies the checks the orchestrator did by hand after the first live run, and writes a verdict and a reason on every proposal in `proposed.json`:
   - **Clash:** the phrase already exists in `phrases.json` on a different path. Drop that phrase from the proposal, unless the proposal's path is a strict extension of the existing path with the same meaning (task 025 keeps "same meaning" base phrases; reuse that test).
   - **Too generic:** a list of phrases that can't carry a CRM path on their own ("used", "use", "has", "of", "in", "about", "subject", "motivation", "was at", "involved in", "type", "kind", "classification", "material" as a bare single word…). Keep the list in a data file beside `phrases.json`, so it can grow. Bare single nouns are dropped unless the path ends at a field that is unique in its model.
   - **Shared across sibling paths:** the same phrase proposed on several paths that differ only in the start class (for example "subject of" on 10 `* P129i` paths, "activity type" on 4 `* E7 P2` paths, "object type" on `E24/E18/E22 P2`). Keep it on one path: the one reaching the most nodes. If the start class doesn't matter to the question, propose the path without it, when `crm` can key it that way.
   - **Skipped high-use paths:** the LLM skipped the most-used date paths (`P4 E52 P86i`, `P140i E13 P4`, …) as generic. List them in the review report as "needs a hand phrasing", and don't drop them silently.
   - Everything that survives is marked `"reviewed": "auto"`, with the checks it passed.
2. **One command for the whole build** (`ceist vocab ontology build <graph dirs…> -o <out>`): estimate (print it and stop if over `--max-calls`), generate, auto-review, gate (`bench/ontology/gate.py`: each proposal alone on 026's bench, then together on the bench, the demo question bank and the HER plans), accept the ones that pass into `phrases.json`, and write a **build report**:
   - what was proposed, dropped by review (with reasons), rejected by the gate (with the score that failed), and accepted;
   - the bench and demo bank before and after;
   - calls, tokens and cost from task 030's ledger.
   A person reads the report. Nothing needs editing by hand for the build to finish. `--review-only` stops after the review, for anyone who wants to look first.
3. **Run it for real on the existing proposals.** Copy the untracked `vocabularies/ontology/cidoc-crm/proposed.json` from `/home/stuart/git/personal/claude-memory-graph-foundation` (100 proposals from two live passes, 26 calls already paid; the cache is in `/home/stuart/.cache/ceist-ontology-run`) into the worktree. Run the review, gate and accept steps on it **without new LLM calls** (`--llm-cmd false`, or the cache only). Commit the resulting `phrases.json`, the reviewed `proposed.json` and the build report.
4. **The playbook** (`packages/ceist/VOCAB-TRAINING.md`): the whole vocabulary training route as it exists today, with the exact commands in order:
   - ontology layer: `vocab ontology build`;
   - graph base: `vocab pipeline --layer base`;
   - question set: `questions generate`;
   - client layer: `vocab pipeline --layer data`;
   - refine loop: `--rounds`, with the hold-out;
   - cost first: `vocab profile` / `vocab estimate`;
   - experiments: `bench/training/run.py`.
   For each step say which model, what it costs (from 030's estimates), what gate it must pass, what to look at in its report, and what not to do (never feed the hold-out bank to a prompt; review the merge report; run the estimate first). Link it from `packages/ceist/README.md`.

## Background
- **Read first:** 025's, 027's, 029's and 030's Worker notes, and the two live-run reports (summarised in this task's Why).
- **Live-run findings to encode as review checks:**
  - clashes: "cited in"/"references" (E33 P67i vs P67i E73), "mentions" (vs P129 E18), "forms part of" (vs P46i), "falls within" (vs E53 P89 E53), "used" (vs P12i E5 P4), bare "material" (vs ^ P45 / P108i E12 P126), "type"/"kind"/"classification" on P41i E17 P42 (sub-path of existing O18i/P108i paths);
  - generic: "used", "use", "subject", "motivation", "was at", "involved in", "events held", "activities held";
  - shared across siblings: "subject of" (10 P129i paths), "described in"/"documented in" (7), "written about in"/"the subject of" (6), "took part in" (3), "activity type" (4), "object type"/"type of object"/"kind of object" (3).
- **A small bug:** the tool's summary line printed "from the cache 0" when 117 paths came from the cache. Fix it from the ledger.
- **No new live LLM calls.** The existing proposals and cache are enough.

## Definition of done
- [ ] Unit tests, one per review check, plus the `build` command end to end with a stub LLM.
- [ ] The real run on the existing 100 proposals: review → gate → accept, committed, with the build report in Worker notes (counts per verdict, bench and bank before and after). Wrong readings and wrongs on the bench must not rise, and the demo bank must exit 0.
- [ ] `VOCAB-TRAINING.md` written and linked.
- [ ] The gate passes. Machine load: one heavy suite at a time (the accept gate takes about 7 minutes), `TMPDIR=/home/stuart/.cache/tmp-033`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

### What changed
- `src/ceist/ontology_vocab.py`: `review()` runs the four checks on every proposal no person has reviewed, and writes `review: {verdict kept|trimmed|dropped, reason, dropped: {phrase: why}}` on each. Survivors get `"reviewed": "auto"` and `checks`. Skipped date paths with 10 or more nodes go to `needs_hand` and to the report. `build()` runs estimate → propose → review → `accept` (the gate) and writes `<ontology>/build-report.md`. `--review-only` stops after the review. `propose` now prints the estimate in dollars, and refuses before any call if the uncached batches exceed `--max-calls`. Its summary line counts the paths from the cache, which fixes "from the cache 0". `accept` returns the gate's verdict (None if the gate failed).
- `vocabularies/ontology/cidoc-crm/generic.json` (new): the generic list, read by review. It has no `entries`, so the layer loaders ignore it.
- `bench/ontology/gate.py`: the verdict also carries the bench tallies per set and mode, before and after (a final together run on what passed), and the demo bank's tally line.
- `cli.py`: `ceist vocab ontology build <dirs> -o <out> [--review-only] [--skip]` and `ceist vocab ontology --review <dirs>`.
- `cost.py` `stage_of`: an audit line from before 030 (`"step": "ontology"`) counts as ontology, not base.
- `VOCAB-TRAINING.md` (new), linked from `README.md`. The data-layer costs are the post-032 figures.
- Tests in `test_ontology_vocab.py`: one test per check (generic, clash with strict extension kept, siblings both ways, bare noun unique/not, high-use skipped dates), plus `build` end to end with a stub LLM and stub gate (it refuses at `max_calls=0` with no call, then merges and writes the report). I broke each check in turn (mutation-checked), and its own test failed each time.

### Decided, spec silent
- **Clash:** the path test is "the proposal ends with the existing path and is longer". Such a proposal reaches only nodes the existing path reaches, so one phrase means one node, which is 025's same-meaning test applied to paths. The check runs across kinds ("used" link vs date).
- **Siblings:** this applies to phrases on proposals ending in the same property. For **links** whose paths differ only in a start class, the phrase moves to a new proposal on the path without that class ("subject of" → `P129i`; `from` lists the siblings). Otherwise the phrase stays on the path that reaches the most nodes. For a property or a date the start class is the meaning ("object type", an event's date), so those are never generalised.
- **Bare noun:** a single word that doesn't end in "ed" (the heuristic is marked `ponytail:`). It is kept only if, in every graph that has the path, the path reaches exactly one node of its kind.
- **Report location:** `vocabularies/ontology/cidoc-crm/build-report.md`, so it is committed beside phrases.json.

### The real run (`--llm-cmd false`, a copy of the cache in TMPDIR; 0 calls, 257 paths from the cache; 10m43s)
- Proposed: 100 proposals, 157 skipped by the LLM. The sibling check adds 7 start-class-free link paths, so 107 were reviewed.
- Review: **59 kept, 35 trimmed, 13 dropped**. 94 went to the gate. 6 skipped date paths need a hand phrasing: `P4 E52 P86i` 44, `P140i E13 P4` 37, `P140i E13 P141` 23, `P9 E7 P4` 20, `P140i E17 P17` 18, `P141i E13 P141` 15.
- Gate: **69 accepted, 25 rejected**. 20 add no right answer. 5 are worse: `O18i E11 P32`, `E18 P2`, `P9 E7 P11`, `P14i E7 P2`, and `P129i`, which is "subject of" generalised, worse on 7 Catalina questions such as "how many heritage stories are subject of X?".
- Bench (right / wrong reading / refused / right refusal / wrong). The question count rises because the templates come from the phrases:

| set | before | after |
| --- | --- | --- |
| lingo | 22 / 0 / 0 / 2 / 0 | 33 / 0 / 5 / 2 / 0 |
| catalina | 298 / 0 / 39 / 25 / 0 | 646 / 0 / 143 / 47 / 0 |
| her | 257 / 0 / 8 / 26 / 0 | 518 / 0 / 52 / 42 / 0 |
| her, ontology+base | 253 / 0 / 12 / 26 / 0 | 508 / 0 / 62 / 42 / 0 |

  Wrong readings and wrongs stayed at 0 everywhere.
- Demo bank: unchanged (answer/right 71, answer/refused 1, refuse/right 7, answer-later 11). Rechecked by hand with this worktree's src: **exit 0**. HER plans: 125/125.
- Cost: this build made 0 calls. The 26 calls of the two earlier live passes predate the ledger, so the report shows them as "estimated, not measured", at about $1.34.

### Checks
- Gate passed on b8b7b72 (rebased on 11ecc00, after 032 merged): root 640 passed, 51 skipped, 1 deselected; Ceist 336 passed.
- No change to ground, plan, bundle or crm. `memory_ask` doesn't read the ontology layer, and `tests/test_planner.py` passes in the gate.

### Left for later (reviewer, non-blocking)
- `review()` re-run on a reviewed proposed.json recomputes verdicts from the trimmed phrases, so it loses the earlier drop reasons (the committed report keeps them).
- `build()` reads propose's first two log lines by position. A run that hits `--max-calls` through retries would mislabel "Generated:".
- The report's Cost table shows $0 when everything comes from the cache, with no line saying so.
- The `stage_of` "step" fallback has no test.

## Graph writes proposed
- Pattern: ontology proposals from an LLM need an automatic review before the gate. Generic words, phrases shared across start-class siblings, and clashes with the layer's own paths are what the LLM gets wrong. The gate alone rejects whole proposals, while review trims single phrases.
- Decision: a phrase shared by sibling link paths moves to the path without its start class, but the gate can still reject it. "subject of" on `P129i` was worse on Catalina, so the start class mattered there after all.

## Review rounds
- Round 1 (b8b7b72): **PASS**. The 5 non-blocking findings are listed under "Left for later".
