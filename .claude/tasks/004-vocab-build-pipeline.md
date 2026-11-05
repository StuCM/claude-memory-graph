---
id: 004
slug: vocab-build-pipeline
status: approved
branch: crew/004-vocab-build-pipeline
model: opus
env: laptop
rounds: 0
depends: [003]
files:
  - packages/ceist/
  - docs/tasks/ceist-vocab-pipeline.md
  - .github/workflows/ci.yml
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

## Review rounds
