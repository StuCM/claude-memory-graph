---
id: 035
slug: date-paths-and-033-findings
status: done
branch: crew/035-date-paths-and-033-findings
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: b75c64aee927b245e5ca19ef11d24b46eaf6dce2
gateAt: 2026-11-08T17:06:05.023Z
rounds: 1
---

# Hand phrasings for the high-use date paths the LLM skipped, plus 033's small findings

## Goal
1. **Date paths.** The live ontology run's LLM skipped the most-used date paths as "generic". 033's build report lists 6 that need a hand phrasing; the top two are `P4 E52 P86i` (44 nodes) and `P140i E13 P4` (37). For each of the 6:
   - look at which fields it reaches in HER, Catalina, arches-lingo and the demo (read only, schema only), and what those dates mean;
   - write phrasings only where the path's meaning is clear and specific (for example a timespan's "falls within" date, an attribute assignment's "assessed on" / "recorded on");
   - where one path reaches dates that mean different things in different graphs, leave it unphrased and say why.
   Add them to `vocabularies/ontology/cidoc-crm/phrases.json` through the **same gate** (`ceist vocab ontology --accept`, or the `build` command with no LLM calls), so they're accepted only if they add right answers and break nothing.
2. **033's reviewer findings** (non-blocking, listed in `033-ontology-build-automated.md`):
   - re-running `--review` loses earlier drop reasons from `proposed.json`; keep them;
   - the build report's "Generated:" line is taken by position from `propose`'s output; take it from the ledger instead;
   - the cost table shows $0 when everything came from the cache; add a line saying so;
   - `cost.stage_of`'s handling of pre-030 audit lines has no test; add one.

## Why now
Stu, 2026-11-08: "Yeh let's do one". These are the cheap, no-LLM follow-ups to the ontology build.

## Background
- **Read first:** 023's, 025's, 027's and 033's Worker notes, and the build report at `vocabularies/ontology/cidoc-crm/build-report.md`.
- **No `claude -p`, live LLM or vocab pipeline runs.**
- A live experiment run may be using the foundation checkout in parallel; you work only in your worktree.

## Definition of done
- [ ] The phrases are accepted through the gate. Bench before and after (026's `bench/ontology/run.py`) in Worker notes; wrong readings and wrongs must not rise.
- [ ] One test per 033 finding.
- [ ] The demo question bank exits 0. HER plans: every diff is justified and re-pinned deliberately.
- [ ] The gate passes. Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-035`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

### What changed
- `src/ceist/ontology_vocab.py`: `review()` starts each proposal's drops from its earlier `review.dropped`, so a re-run keeps the reasons (and a sibling-moved phrase is not appended twice). `propose()` carries `review` and `checks` over a re-run too, so `build` keeps them. `build()` counts this run's LLM calls from the audit lines propose appended (the ledger), not from propose's log by position; the "Generated:" line now holds the proposals, skips, calls and not-proposed counts (it absorbs the old "Proposed:" line). When the build made no LLM calls, the report says so under the Cost table.
- Tests: `test_a_second_review_keeps_the_first_reviews_drop_reasons`; `test_the_report_counts_the_calls_when_retries_hit_max_calls` (BATCH=1, a stub whose first reply is nonsense, `--max-calls 4`: the old code put "stopped at --max-calls" into Generated); the end-to-end build test now builds twice and checks the "no LLM calls" line; `test_cost.py::test_an_audit_line_from_before_the_ledger_counts_as_its_step`. All three ontology tests fail on the old `ontology_vocab.py`.
- `vocabularies/ontology/cidoc-crm/`: two hand proposals (`"reviewed": true`) through `ceist vocab ontology --accept`; one merged into phrases.json.

### The six date paths (fields read from HER, Catalina, arches-lingo and the demo, schema only)
| path | reaches | verdict |
| --- | --- | --- |
| P4 E52 P86i (44) | Catalina status time-spans (appellative, whakapapa, classificatory, function, custodial…), HER/Catalina consultation and field-assessment target dates, aircraft expected arrival | unphrased: many meanings |
| P140i E13 P4 (37) | a geometry's authorization date (`SP6 P140i E13 P4`, most), a scientific date's "when determined", lingo's concept status time-span | unphrased: three meanings |
| P140i E13 P141 (23) | an area assignment's status time-span vs a scientific date's time-span (what the thing is dated to) | unphrased: two meanings |
| P9 E7 P4 (20) | associated actor time-span vs consultation communications dates | unphrased: two meanings |
| P140i E17 P17 (18) | designation and protection time-span (start and amendment dates) in every graph | phrased "designated, protected, date of designation, designation date": **rejected by the gate**, adds no right answer |
| P141i E13 P141 (15) | land use classification time-span of a location, in every graph | phrased "land use assessed, date of land use assessment, land use assessment date": **merged** |

The split meanings sit on longer, specific paths (`SP6 P140i E13 P4` = a geometry's authorization date; `E18 P140i E13 P141` = dated to). Phrasing those is a decision the spec didn't make; left for a later spec.

### Gate run (`ceist vocab ontology --accept`, 13m50s)
- It gated 27: my 2 and the 25 that 033's gate rejected (`--accept` re-gates any reviewed proposal not merged). All 25 were rejected again; two reasons changed against the new baseline (`P93i E81 P2` from "adds no right answer" to "worse on 6"; `P129i` from "worse on 7" to "worse on 10").
- 1 of 27 passed. Bench: 1 pass alone and together; demo bank unchanged; HER plans 125/125.

### Bench (026's `bench/ontology/run.py`; right / wrong reading / refused / right refusal / wrong)
| set | mode | before | after |
| --- | --- | --- | --- |
| lingo | ontology | 33 / 0 / 5 / 2 / 0 | 33 / 0 / 5 / 2 / 0 |
| catalina | ontology | 646 / 0 / 143 / 47 / 0 | 653 / 0 / 164 / 54 / 0 |
| her | ontology | 518 / 0 / 52 / 42 / 0 | 524 / 0 / 70 / 48 / 0 |
| her | ontology+base | 508 / 0 / 62 / 42 / 0 | 514 / 0 / 80 / 48 / 0 |

Wrong readings and wrongs stay 0. The question count rises with the new phrase's templates; the refused rise is those new template questions, not old ones turning (the gate rejects a candidate that makes any question worse).

### Demo and HER
- Demo bank with this worktree's src: **exit 0**, tally unchanged (answer/right 71, answer/refused 1, refuse/right 7, answer-later 11).
- HER plans 125/125 (in the gate); no re-pin needed. No change to ground, plan, bundle or crm; `memory_ask` doesn't read the ontology layer.
- `build-report.md` is still 033's run's report; not regenerated (no build was run).

## Graph writes proposed
- Pattern: a CRM date path the LLM calls "generic" is usually several specific ones sharing a tail. Status time-spans, geometry authorizations and scientific dating all end in `P140i E13 P4/P141`. Look at the fields it reaches before phrasing it, and phrase the longer path that has one meaning.
- Gotcha: `ceist vocab ontology --accept` re-gates every reviewed proposal that is not merged, including those an earlier gate rejected. A hand run of 2 proposals gated 27 and took 14 minutes.

## Review rounds
- Round 1 (b75c64a): **PASS**. Not blocking: a carried-over drop reason stays even after its clash is gone, which is what "keep them" asks for. The rejected `P140i E17 P17` is `reviewed: true`, so later `--accept` runs re-gate it, as 033 already did.
