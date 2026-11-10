---
id: 059
slug: one-command-site-setup
status: approved
branch: crew/059-one-command-site-setup
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
  - packages/ceist/bench/ontology/gate.py
  - packages/ceist/VOCAB-TRAINING.md
  - packages/ceist/README.md
---

# One command sets up Ceist for a new site: the shared layers as they are, plus a gated client layer on top

## Goal
Stu, 2026-11-10: the vocabulary process "needs full automation so that a developer can just run it and it sets up", and "we have the cidoc and graphs set and we just need the client layer on top".

The reverse test on Phil's responder data (`/home/stuart/git/fat/aonach-responder-assessment.md` §2b) ran Ceist cold on a new six-graph site:
- 2 right, 0 wrong, 23 refused of 35, rising to 4 right with Phil's curated terms;
- `ceist vocab generate` re-scored ontology candidates against HER, lingo and Catalina for 30 to 40+ minutes and never finished.

1. **`ceist setup <data dir> -o <out>`.** One command that turns a site's Arches graphs and records into a ready vocabulary bundle:
   1. read the graphs and records;
   2. print the cost estimate;
   3. use the shared ontology (CIDOC-CRM) layer and any base layer **as they are**;
   4. generate the **client layer only**, with the rule generators and, optionally (`--llm`, with a call or dollar cap), the directed LLM fill;
   5. gate the client candidates against **this site's own** benchmark (the fresh-graph template questions generated from the site's own schema), never against HER, lingo or Catalina;
   6. write the coverage report and the frozen bundle (041's format, if it exists by then, else the bundle Ceist reads today).

   It must finish in minutes on a six-graph site. Measure it and report the time.
2. **Ontology and base proposals become a separate, occasional build** (the existing `vocab ontology build`), run by the maintainers, not by each site. Document the split in `VOCAB-TRAINING.md`.
3. **`ceist ask <data dir> "<question>"`.** A site-agnostic way to ask a question against any data dir, without the demo's `ask.py`. It prints the narration, the results count and the refusal or "did you mean".
4. **Bugs the reverse test found:**
   - `vocab_rules.apply` into an empty client dir writes no `manifest.json`, so `bundle.read_vocab` silently ignores the per-model folders. Fix it, and make a missing manifest an error, not silence.
   - Read label-valued concept tiles when a node has no `rdmCollection`.
   - The plural rule produces "f — constructions" and "heritages", and misses "hospitals". Fix it, with tests.
5. **Prove it cold.** Re-run the reverse test with `ceist setup` alone (no hand steps), using the side chat's harness and frozen set (`/home/stuart/git/fat/aonach-responder-assessment.md` §7, sha `ad2e6bba`). **Don't tune on that set.** Report before and after. Also run it on the demo data and check the demo bank still exits 0.

6. **Vocabulary upgrades** (Stu, 2026-11-10, after the reverse test):
   - **Values that name kinds of things become type words.** For each controlled value that names a kind of thing ("Shelter", "Hospital" as a service role), generate the plural as a type word with that value preset: "shelters" = *Buildings whose service role is Shelter*.
     - Where two models hold the value (service roles sit on both Building and Organisation), the setup asks for, or reads, a **one-line site default** (`defaults: {shelter: Building}` in the site's vocabulary config) and records it.
     - Without a default it stays ambiguous, and Ceist asks "did you mean". No guessing at question time.
   - **Paraphrases of what Ceist can already answer** (OVERNIGHT-style; credit it in `PRIOR-ART.md`). Enumerate the site's canonical answerable sentences from its schema (narrated plans up to one link plus one value or date). Then propose paraphrases two ways, both through the site gate, each paraphrase carrying its known plan so the gate checks it exactly:
     - **bge mining, free:** bge can't write paraphrases, but it can rank. Score short phrases from the site's own text (record descriptions, the site's docs if given) against each canonical sentence's link and value phrasings, and propose the nearest as candidates. Report how many survive the gate. bge separates poorly, so expect a low yield.
     - **LLM paraphrase, `--llm`, capped:** batch the canonical sentences (about 50 per call) and ask for 3 to 5 everyday rewordings each. **Estimate first** (`ceist vocab estimate`), including the `claude -p` system-prompt overhead (about 33k tokens per call, so prefer few large batches, or the API directly), and show the estimate before any call. Tested with a stub here. No live calls in this task.
   - **Practice and exam sets.** Build a **practice** set from Phil's material, separate from the frozen 39-question exam (sha `ad2e6bba`), and use it for any checking. The frozen set is only scored at the end, once.

7. **A gap and ambiguity audit, as part of `ceist setup`'s report.** Find whole *classes* of problem before any visitor hits one, rather than one instance at a time (Stu, 2026-11-10: "we keep hitting random issues… in a real life test more and more will come up"). For the site, list:
   - **every value, type word or phrase that more than one model or field can mean** (the "shelter" class), with how it's settled: a site default, the subject type, or "did you mean". Count them;
   - **every number, date and geometry field**, and whether Ceist's grammar can ask about it (numbers before 060, for example), so missing grammar shows as a count of fields, not as surprised users;
   - **every link with no phrasing in any layer** (the 039 class: Figure's link to monuments), so "unphrased links" is a number that falls;
   - **every controlled value with no plural or type-word form,** and every model with no type word;
   - **every link two pieces of the same type can sit on** (direction set by word order, and "of" flips it);
   - **records whose name is also a vocabulary phrase,** or contains only a generic word.

   Each item gets a one-line fix or a reason. The report ends with totals per class, and a site is "set up" when each class is resolved or its remainder is accepted.

## Background
- **Read first:**
  - the assessment report (§2b and §7);
  - `VOCAB-TRAINING.md`;
  - 039's, 053's and 056's Worker notes;
  - `vocab_rules.py` (generate and apply), `cli.py`, `bench/ontology/gate.py`, `bundle.py` (`read_vocab`).
- **The responder data** comes from Phil's public `flaxandteal/ros-madair` (`example/aonach_mor`, the `build/emit_*.py` generators). The side chat already generated it; find its location in the report's §7.
- **No `claude -p` or live LLM runs.** The `--llm` path is tested with a stub only.
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names.
- This runs after 056 and 057 (shared `packages/ceist/src/ceist/`).

## Definition of done
- [ ] `ceist setup` and `ceist ask` exist and are tested. The setup time on the responder site and on the demo is in Worker notes.
- [ ] The four bugs are fixed, with tests.
- [ ] The audit runs in `ceist setup` and lists each class with counts, on the responder site and the demo.
- [ ] Value-as-type words with site defaults, and both paraphrase sources, are tested. Gate survival counts per source are in Worker notes.
- [ ] Cold reverse-test scores are in Worker notes; wrong answers stay at 0. The demo bank exits 0 and HER plans are 125/125.
- [ ] The gate passes. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-059`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
