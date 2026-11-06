---
id: 023
slug: crm-ontology-layer
status: approved
branch: crew/023-crm-ontology-layer
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
---

# A CIDOC-CRM vocabulary layer under the graph layer: phrasings, question words and paths from the ontology

## Goal
Vocabulary layers become **ontology → graph → client**.
- **The ontology layer:** `vocabularies/ontology/cidoc-crm/`. Phrasings attached to CRM properties and classes, not to graph fields, for example:
  - P14 *carried out by* → "built by", "made by", "by";
  - P7 *took place at* → "at", "in";
  - P2 *has type* / E55 → "what kind of", "type";
  - P45 *consists of* → "made of".
  Any Arches graph whose nodes map to those CRM properties gets them **without graph-specific vocabulary**. The graph and client layers still override, through the 011/020 merge rules.
- **Question words from classes:**
  - "who" means records whose model is an E39 Actor (or a subclass);
  - "where" means an E53 Place link;
  - "when" means an E52 Time-Span or date;
  - "what is it made of" means P45.
  Today "who" only works for a model literally named Person.
- **Paths:** "who built X?" follows the CRM path X → P108 *produced by* → E12 Production → P14 *carried out by* → E39, when the graph models it that way. It compiles to the links and nodegroups the graph actually uses, and reads back exactly.

## Why now
Stu, 2026-11-06: "I feel the ontology could be our greatest strength with this and as you say fix the endless vocab issue, someone has done the hard work." Phrasings that live at the ontology level are written once and shared by every graph and client.

## Step 1 (do first, stop and report if it fails): audit the CRM mapping
Before building, measure how consistently the graphs map their nodes to CRM:
- HER, from the arches-her clone at `/home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models`;
- the demo graphs (`/home/stuart/git/personal/starches-demo/prebuild/graphs/resource_models`, read only).

For each graph:
- the share of nodes with an `ontologyclass` and a parent property;
- which CRM properties and classes are most used;
- whether the same meaning uses the same property across graphs (for example, is "named location" always P53 or P89?).

If the mapping is too inconsistent for a shared layer to help (say, under half of the link and date nodes carry a usable property), **stop, write the audit into Worker notes, and report**. Then the orchestrator and Stu decide. Otherwise continue.

## Background
- **CRM code lives in `crm.py`** (task 010 split it out): `crm_code`, `crm_roles`, `ROLES`, `CRM_PROPERTIES`, a small class hierarchy and `clash`.
- **Layers and merge rules:** `bundle.layered` and the 020 overrides. Read 011's and 020's Worker notes. The ontology layer sits beneath the graph base. Its phrases apply to a node whose parent property or class matches, and the graph and client layers may add to them or override them by the same rules.
- **Grounding:** `ground.py` (`_fit_relations` and the wh-word handling; check how "who" is handled today, in `arches.py` `implied_types`).
- **Write the ontology phrasings by hand** for roughly the top 30 properties and classes the audit finds. They're small, reviewable and reusable. An LLM pass can extend them later.

## Definition of done
- [ ] The audit is in Worker notes, with numbers per graph.
- [ ] Unit tests, each failing on the base code:
  - an ontology phrase reaches a node only through its CRM property;
  - a graph-layer phrase overrides it;
  - "who" finds an E39 model that isn't named Person;
  - "who built X" follows a P108/E12/P14 path in a fixture, and reads back.
- [ ] On the demo, with the ontology layer loaded, the question bank exits 0 (no regressions). Report any bank question it newly answers. Also report what "who built Navan Fort?", "who made the Gáe Bulg?" and "when was Navan Fort built?" do.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes

## Graph writes proposed

## Review rounds
