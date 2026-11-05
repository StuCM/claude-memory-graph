---
id: 004
slug: vocab-build-pipeline
status: blocked
branch: crew/004-vocab-build-pipeline
model: opus
env: laptop
rounds: 2
depends: [003]
files:
  - packages/ceist/
  - docs/tasks/ceist-vocab-pipeline.md
  - .github/workflows/ci.yml
gate: pass
gateSha: 05ec4e3235d4b059a9a6000b2d04b8be5c5d672d
gateAt: 2026-11-05T10:12:19.634Z
blocked: review PASS; 3 DoD items need a live claude -p run from a logged-in terminal (demo, demo_compare, HER subset) - commands in Worker notes
blocked-by: person
---

# A scripted LLM build that writes a graph's vocabulary, one nodegroup at a time

## Goal
One command, `ceist vocab pipeline <graphs> [--reference <dir>] [--questions real.txt] -o <dir>`, builds the most accurate baseline vocabulary it can for any Arches graph. It runs over Stu's Claude subscription. It analyses every nodegroup, writes test questions separately, gates on accuracy, and reports what it covered and what it skipped. No record data is sent.

## Why now
Stu, 2026-11-05: "a process or series of scripts that we can run an llm on to build the most accurate set of vocab we can for a graph, a structured way … include questions if we have them but a base line llm build"; "the llm should be looking at each nodegroup and thinking what questions could arise … in relation to the data"; "are we using the ontologies to help with the relationships?"; "set it to use llm subscription".

## Background
- **The design:** `docs/tasks/ceist-vocab-pipeline.md` (privacy model, pipeline, commands). Update it as you build.
- **Today:** `ceist vocab describe` (Arches through Alizarin), `bundle.PROMPT` and `learn.PROMPT` with the schema inlined (PR #38), `vocab save`/`assign`, `assemble`, `eval`. The manual HER flow is in `bench/ADAPTATION-FLOW.md`. On HER, node names alone got 20/102 right, the LLM vocabulary 81/102, and "did you mean" 94/102 within one click.
- **CIDOC-CRM is on every node and edge,** but it's used only as context labels (`arches_describe.crm_label`). Examples from the demo's Monument graph: `E55 Type` (229 nodes), `E52 Time-Span`, `E39 Actor`, `E53 Place`; edges `P2 has type`, `P14 carried out by`, `P53 has location`.

## Approach
1. **The LLM runner, over the subscription.**
   - The default runner pipes each prompt to Claude Code headless: `claude -p`, read with `--output-format json` or similar. Check the flags against `claude --help` on this machine.
   - It runs **with no tools**, from an empty temporary working directory, so the model can't read files. Find the flag that disables tools in the installed version, and say which you used.
   - `--llm-cmd` takes any command that reads a prompt on stdin and prints a reply. `--model` is passed through.
   - Calls are cached per nodegroup by a hash of its description plus the prompt version.
   - Every call is appended to `audit.jsonl`: what was sent (hashed and in full), and when.
   - Don't add an API-key path unless it's free to do; the subscription is the default.
2. **CRM-derived roles, a deterministic pre-pass.** Map each node's role from its ontology class and the edge property into it:
   - `E52` → date;
   - `P14`/`E39` → actor ("who");
   - `P53`/`P7`/`E53` → place ("where");
   - `E55` via `P2` → type;
   - names and identifiers likewise.

   Include CRM inverse properties (`P14i` and the like) as hints for reverse phrasings. Put these roles in the nodegroup description the LLM sees, marked as hints.
3. **One analysis per nodegroup.** One call per nodegroup, with the model's whole outline in context, returning JSON validated against a schema:
   - the group's purpose;
   - each node's role (confirmed or corrected);
   - **question intents** (filter, list, count, when, who, where, which kind, combined with which other groups), each with several realistic wordings;
   - phrasings per node;
   - combos (several values set by one phrase);
   - an explicit "not asked about" with a reason for metadata and audit groups.

   It writes into 003's per-nodegroup files. Keep the group-level block in a form 005 can consume; coordinate through the format in `docs/tasks/ceist-group-grounding.md` §2.
4. **A collision pass per model.** `validate`'s shared-phrase warnings go back to the LLM, to resolve or mark as deliberately ambiguous.
5. **A separate question writer.** A different prompt, given the description only, never the vocabulary, writes acceptance cases per model: question, expected type and conditions, or expected refusal. `--questions` adds real questions, masked with `learn`'s rules. The cases are frozen per build.
6. **The gate and coverage.**
   - `ceist eval` (phrase level) **plus** a planner-level run of every case through `interpret`, scoring right, refused and dangerous against the expected conditions.
   - `--min-right`/`--max-dangerous`.
   - A coverage report: nodegroups and nodes with no phrasings, split into skipped on purpose and missed.
7. `ceist vocab pipeline` wraps describe → CRM pre-pass → build → collisions → questions → assemble → gate → report, and stops at the gate.

## Out of scope
Group-first grounding (005), the learn loop's auto-accept, and non-Arches sources.

## Definition of done
- [ ] **On the demo graphs** (`/home/stuart/git/personal/starches-demo/prebuild/graphs/resource_models`): one pipeline run through `claude -p`, with audit, cases, gate output and coverage report in Worker notes. Then the demo's question set, plus the paraphrases from the demo README and the bge comparison, run with the generated vocabulary against the current hand-tuned one, both through the demo's `ask.answer`.
- [ ] **On HER:** if the HER graphs are reachable, compare with the existing `bench/her` result (81/102 WordLlama, 89/102 bge-small, at most 3 dangerous). The target is to beat it with no more dangerous answers. If the run is too heavy for the machine, run a stated subset of models and say so.
- [ ] **Privacy test:** the audit file holds no resource ids, record names or tile values. Test this on the fixture.
- [ ] **Unit tests** with a fake `--llm-cmd` returning canned JSON, covering: the CRM pre-pass, schema validation of replies, the cache, the collision pass, and gate pass and fail.
## Definition of done (common)
- [ ] The gate (`crew.config.json` `verify`) passes; test counts before and after are in Worker notes.
- [ ] The HER questions (`packages/ceist/bench/her/cases.json`) run through `interpret` before and after. The table of changed answers is in Worker notes, with every change justified. If you can't get the HER graphs locally, say so.
- [ ] The Friday demo questions in `/home/stuart/git/personal/starches-demo/ask/README.md` run with `PYTHONPATH=<worktree>/packages/ceist/src` and give the same answers, or each difference is explained.
- [ ] Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, no servers left running, never `git add -A` or `git stash`.

## Worker notes

**What changed**
- `ceist/pipeline.py` (new): the `claude -p` runner (cache, audit, one retry with the schema errors shown), `crm_roles` (the CRM pre-pass), `check_group` (the reply schema), `entries_of`/`group_block` (entries plus the §2 group block), `resolve_collisions`, `write_cases` (questions per model, plus masked real questions labelled in one call), `judge_plan`/`planner_run` (every case through `interpret`), `coverage`, `report`, `run`.
- `ceist/cli.py`: `ceist vocab pipeline` (also `--models` for a subset, `--config`, `--jobs`).
- `ceist/bundle.py`: `shared_phrases()` factored out of `validate`, with the same warnings, so the collision pass reuses it.
- `ceist/arches_describe.py`: `reference_files()` factored out of `load_rdm`, reused by the planner run.
- `bench/demo_compare.py` (new, round 2): the demo README's questions through the demo's `ask.answer` with the hand-tuned and a generated bundle, as a markdown table of the differences. The demo-only phrasings in `ask.py` (`EXTRA_TYPE_WORDS`, `RELATION_FORMS`) apply to both.
- `tests/test_pipeline.py` (7 tests, fake `--llm-cmd`): CRM roles, the reply schema, a fixture run end to end (group files, collisions, cases, report, audit privacy, the cache, one changed group rebuilt alone), gate fail on right and dangerous, retry then failure reported, and the `claude -p` result envelope. Mutation-checked: sending real questions unmasked fails the privacy test.
- `docs/tasks/ceist-vocab-pipeline.md`: the "Pipeline" section (runner flags, cache, audit, CRM rules, reply format, collisions, cases, gate, coverage).
- `.github/workflows/ci.yml`: not changed. The unit tests run in the existing ceist job.

**Runner flags (claude 2.1.300):** `claude -p --output-format json --tools "" --strict-mcp-config --setting-sources project --no-session-persistence --system-prompt …`, from an empty temp dir. `--tools ""` disables all built-in tools. `--bare` was rejected because it never reads OAuth, so it can't use the subscription.

**Pending a live run (Stu, from a terminal where `claude` is logged in).** Three Definition-of-done items are open: the demo run, demo generated vs hand-tuned through `ask.answer`, and the HER comparison. From this session every `claude -p` call fails with "Failed to authenticate: OAuth session expired and could not be refreshed". I tried the inherited env, `env -u CLAUDE_CODE_SIMPLE`, `env -i`, and the desktop app's bundled binary. `~/.claude/.credentials.json` has `expiresAt: 0`, so the desktop app holds the login. Run these from the worktree (`cd /home/stuart/git/personal/claude-memory-graph-004`), one at a time, with `export TMPDIR=/home/stuart/.cache/tmp-004`:

1. Demo build: 156 calls, about 2.5 MB of prompts (a stub run measured a median of 15 KB per prompt and a maximum of 104 KB). Outputs land in `/home/stuart/.cache/tmp-004/demo-run/`: `report.md` (the gate and coverage), `audit.jsonl`, `cases.json`, `bundle.json`, `collisions.json` and `vocab/`. A rerun resumes from `cache/`.
   ```
   D=/home/stuart/git/personal/starches-demo/prebuild
   .venv-ceist/bin/ceist vocab pipeline $D/graphs/resource_models --reference $D/reference_data \
     -o /home/stuart/.cache/tmp-004/demo-run --model sonnet --jobs 2 \
     --config packages/ceist/bench/her/ceist-bge.toml --min-right 1 --max-dangerous 0
   ```
2. Demo answers, generated vs hand-tuned, both through `ask.answer` (README questions; add paraphrases with `--questions`). Output: `/home/stuart/.cache/tmp-004/demo-compare.md`.
   ```
   CEIST_HER=$PWD/packages/ceist/bench/her PYTHONPATH=$PWD/packages/ceist/src .venv-ceist/bin/python \
     packages/ceist/bench/demo_compare.py /home/stuart/git/personal/starches-demo/ask \
     /home/stuart/.cache/tmp-004/demo-run/bundle.json > /home/stuart/.cache/tmp-004/demo-compare.md
   ```
   I smoke-tested it with the stub run's empty bundle: it ran end to end, and 18/26 answers matched.
3. HER subset: 6 models, 69 of the 120 cases. Output: `/home/stuart/.cache/tmp-004/her-run/`. Then score the generated bundle on the HER cases with both configs, to compare with 81/102 (WordLlama) and 89/102 (bge-small), at most 3 dangerous. The committed vocab currently scores 90/102 with 2 dangerous using bge in `.venv-ceist`. These scores cover the subset's models only. The other models have no generated vocabulary, so their cases are missed.
   ```
   P=/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg
   .venv-ceist/bin/ceist vocab pipeline $P/graphs/resource_models --reference $P/reference_data \
     -o /home/stuart/.cache/tmp-004/her-run --model sonnet --jobs 2 \
     --models "Monument,Person,Artefact,Activity,Area,Maritime Vessel" \
     --config packages/ceist/bench/her/ceist-bge.toml --max-dangerous 3
   for c in ceist ceist-bge; do .venv-ceist/bin/ceist eval --bundle /home/stuart/.cache/tmp-004/her-run/bundle.json \
     --questions packages/ceist/bench/her/cases.json --config packages/ceist/bench/her/$c.toml; done
   ```
   (`.venv-ceist` has no wordllama, so `ceist.toml` runs exact-only there. 003 measured that config at 67/102.)

**Where the spec bent**
- CRM roles are hints in the prompt and in the cache key. They're not written into the descriptions, so 003's manifest hashes don't move.
- The planner run loads graphs and reference data but no records. Cases that name a record are "missed" there. The question prompt asks for questions without record names.
- `judge_plan` is strict: an answer to a case that expects a refusal is dangerous. On the fixture, interpret answers "which buildings were painted in 1900?" with the construction date plus a text mention of "painted", and that counts as dangerous. The planner wasn't changed.
- `--min-right` applies to the phrase level and `--max-dangerous` to both levels.
- A changed nodegroup also re-asks its model's collision pass (labels are in that prompt). Cache hits aren't re-audited.

**Round 2 changes** (folded into the commits they belong to):
- `_check_cases` requires each case to be an object with `q` (not for labels, where we hold the question) and an `expect` key. A malformed reply is asked again and never cached.
- `--model` is in the cache key.
- An LLM error or timeout fails that call only. It's recorded in `Runner.failures` and not cached, the run goes on, and `report.md` lists the "Failed calls" at the end.
- With no cases, the gate fails when a threshold is given, and warns otherwise.
- When a question call failed, the cases go to `cases.unfrozen.json`, so a rerun asks again instead of freezing a partial set.
- The new test feeds a reply with a case missing `q` and `expect` plus a non-object case, and a group whose LLM call exits non-zero. Mutation-checked: dropping the `q` requirement fails it.

**Gate:** round 2 passed, stamped on 05ec4e3, with the same deselects. Root: 486 passed, 26 skipped, 3 deselected (485 in round 1; no root code touched). Ceist: 153 → 160 passed. Round 1: `crew gate` passed, stamped on 357c115. It ran with `PYTEST_ADDOPTS` deselecting the two known 001 failures, `tests/test_planner.py::test_did_you_mean_for_an_unplaced_verb` and `::test_did_you_mean_says_how_to_teach_the_phrasing` (they fail on the base too). Root: 485 passed, 26 skipped, 3 deselected (no root code touched). Ceist: 153 → 159 passed.

**HER (arches-her dev/2.0.x, task 003's local clone):** the assembled bundle is byte-identical to 003's. All 120 cases through `interpret` give byte-identical output (narrated plan, refusal, suggestions). `ceist eval` with bge: 90/102 right, 2 dangerous, unchanged. No answers changed, so there's no changed-answer table.

**Demo** (`starches-demo/ask` via task 003's `demo.py`, run through `.venv-ceist` with `CEIST_HER` and `PYTHONPATH` set to this worktree): all 26 questions give byte-identical answers to 003's branch output.

**Memory graph:** no planner, grounding or `interpret` code changed, so `memory_ask` is unaffected.

## Scout requests
None.

## Graph writes proposed
- Gotcha: `claude -p` started from inside a Claude Code desktop session can't use the subscription ("OAuth session expired"): the desktop app owns the login (`expiresAt: 0`). `--bare` never reads OAuth. Run subscription LLM builds from a terminal.
- Decision: the vocab pipeline's CRM roles are prompt hints and cache inputs, not description fields, so the split-vocab manifest hashes stay stable.
- Gotcha (seen with the stub vocabulary): "which tales are part of the Ulster Cycle?" is refused with "compile: unknown path alias 'part_of'". With no bundle phrasing, the grounder picks a relation whose name the Rós Madair compiler doesn't know. This was not investigated, and it doesn't happen with the hand-tuned vocabulary.
- Pattern: in a test's fake LLM command, don't let canned config override the computed reply (a canned map leaked in as the reply, and the retry hid it).

## Review rounds

- Round 1: BLOCKED. The reviewer reran test_pipeline.py and test_bundle.py (14 passed) and accepted the privacy test, the unit tests, the scope, and the CRM-as-hints departure. Findings:
  1. A blocker: `_check_cases` doesn't require `q` or the `expect` key, and doesn't check that a case is a dict before using it. A malformed question-writer or label reply then passes the check, is cached, and makes `write_cases` raise KeyError/AttributeError on every rerun. The fix is about 10 lines, plus a test.
  2. `subprocess.TimeoutExpired` and `LLMError` abort the whole run. The cache resumes it.
  3. With no thresholds, failed groups or an empty case set still "pass". Pass `--min-right`/`--max-dangerous 0` in the live runs.
  4. The cache key leaves out the outline, `--model` and the prompt text. Bump `PROMPT_VERSION` when a prompt changes.
  The reviewer says it's ready for the live runs once finding 1 is fixed. Not fixed here: the verdict was BLOCKED, so the decision is Stu's.
- Round 2: PASS. The reviewer reran test_pipeline.py and test_bundle.py (15 passed) and confirmed all four round-1 findings fixed: case schema with no caching, `--model` in the key, per-call failures recorded and the run goes on, empty cases fail or warn. It accepted the three live-run DoD items as pending Stu, with exact commands in Worker notes. Prompt text is still outside the cache key; `PROMPT_VERSION` covers that.

