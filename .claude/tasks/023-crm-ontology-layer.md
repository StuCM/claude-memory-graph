---
id: 023
slug: crm-ontology-layer
status: done
branch: crew/023-crm-ontology-layer
model: opus
env: laptop
work: ceist-ontology
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: 595acf1ea741dbbc4843d3c6abc63eaf673d7b4f
gateAt: 2026-11-08T09:39:09.033Z
rounds: 1
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

### Step 1: CRM-mapping audit (passes the stop condition by a wide margin)

Script: `/home/stuart/.cache/tmp-023/audit/audit.py` (paths: `paths.py`, `chains.py`). "Property" = `parentproperty`, else the edge's `ontologyproperty`.

| graph | root | nodes | with class | non-root with property | link+date nodes | with property |
|---|---|---|---|---|---|---|
| HER Activity | E7 | 324 | 87% | 100% | 28 | 100% |
| HER Application Area | E53 | 228 | 86% | 100% | 16 | 100% |
| HER Area | E27 | 429 | 88% | 100% | 39 | 100% |
| HER Artefact | E22 | 416 | 88% | 100% | 33 | 100% |
| HER Bibliographic Source | E33 | 145 | 85% | 100% | 8 | 100% |
| HER Consultation | E7 | 314 | 90% | 100% | 41 | 100% |
| HER Digital Object | D1 | 92 | 84% | 100% | 8 | 100% |
| HER Heritage Story | E33 | 218 | 89% | 100% | 21 | 100% |
| HER Historic Aircraft | E24 | 472 | 89% | 100% | 42 | 100% |
| HER Historic Landscape Char. | E53 | 218 | 89% | 100% | 16 | 100% |
| HER Maritime Vessel | E24 | 495 | 88% | 100% | 49 | 100% |
| HER Monument | E18 | 433 | 88% | 100% | 40 | 100% |
| HER Organization | E74 | 184 | 84% | 100% | 13 | 100% |
| HER Period | E4 | 175 | 90% | 100% | 18 | 100% |
| HER Person | E21 | 226 | 83% | 100% | 17 | 100% |
| HER Place | E53 | 202 | 87% | 100% | 10 | 100% |
| demo Figure (=HER Person) | E21 | 226 | 83% | 100% | 17 | 100% |
| demo Group (=Organization) | E74 | 184 | 84% | 100% | 13 | 100% |
| demo Monument | E18 | 433 | 88% | 100% | 39 | 100% |
| demo Object (=Artefact) | E22 | 416 | 88% | 100% | 33 | 100% |
| demo Site (own graph) | E53 | 46 | 67% | 84% | 14 | 100% |
| demo Tale (=Heritage Story) | E33 | 218 | 89% | 100% | 21 | 100% |

The nodes with no class (11–17%) are string literals: names and notes. Five of the six demo graphs are HER graphs under new names, so they are not independent evidence. Only Site is a separate mapping.

**Most used in HER (node counts).** Properties: P2 2283, P3 559, P1 173, P106 132, P82a 130, P82b 126, P67i 112, P141 105, P4 104, P14 89, P129i 68, P140i 56, P72 56, P37 48, P94i 38. Classes: E55 2411, (none) 563, E61 260, E41 244, E33 133, E52 129, E42 84, E21 78, D10 68, E73 63, E56 57, E53 51, D1 50, E13 47, E7 44, E39 44.

**The same meaning, across graphs:**
- Dates are very consistent. Start dates are P82a under E52 in 97/102 cases; end dates are P82b in 157/165. Each event is told apart by what its time-span hangs from: O18i E11 construction, P108i E12 production, P98i E67 birth, P100i E69 death, P95i E66 formation, P12i E5 use.
- Named location is always `P53 E53 / P89 E53 / P89i E53` (7/7; never P53 alone). Copyright holder is always P75i (18/18). Citations are P67i E73 (12/14, P129i twice). Parent monument is P46i, parent story P148i, mother P96, father P97.
- Inconsistent: "associated activities" and "associated consultations" use six different properties across six graphs (P12i, P11i, P15, P16i, P8i, P17i). P10 → E4 means three different things (production period, use period, construction phase). P140i E13 P141 (attribute assignment) covers scientific dates and area-status dates alike.
- **The headline is that the property into a node is reliable, but on its own it is often too general to carry a phrase.** P14 *carried out by* appears 89 times in HER. 67 of those are audit or spatial metadata (creator, updater, compiler, authorizer). Only 1 is P108i/E12 production → producer, 1 is O18i/E11 construction → builder (Maritime Vessel only), and 1 is publication. A "by"/"made by" phrase on P14 would be wrong 3 times in 4. So the layer attaches phrases to the CRM path that ends at a node (`P108i E12 P14`), not to the bare property.
- Demo facts that matter: Monument has no builder (its E11 construction phase has no P14). Object has `P108i E12 P14` producer. Site's dates use P81a/P81b and the statement's E65 Creation.

So more than half the link and date nodes carry a usable property (100% do). I continued to build.

### What was built (595acf1)
- `vocabularies/ontology/cidoc-crm/phrases.json`: 29 phrasings, written by hand, each keyed by a CRM path rather than a bare property, because of the audit finding about P14. There are 22 for links (`P108i E12 P14` made by, `O18i E11 P14` built by, `P89i` located in, `P75i` copyright holder, `P46i`/`P148i` part of, `P96`/`P97` mother/father, and so on) and 7 for dates, keyed by the event the time-span hangs from (`O18i E11 P4` built, `P108i E12 P4` made, `P98i E67 P4` born, `P100i E69 P4` died, `P95i E66 P4` founded, and others). No LLM was used and no pipeline was run.
- `crm.py`: `chains` (each node's CRM path from the root), `ontology_entries` and `is_a`. A date's path stops at its time-span property, and it carries its P82b mate as `end_node`. "who" plus a date phrase ("who made") becomes a link phrase on the single P14 actor of that same event node. If an event has no P14 actor, or more than one, no such phrase is made.
- `bundle.layered`: the ontology layer sits under the base. It is read from `ontology_dir`, which defaults to `ontology/cidoc-crm` beside `base_dir`, so the demo picks it up with no change to ask.py. If the base already uses a phrase, the base's meaning wins. If an ontology phrase fits two nodes of one model, it is left out and reported. The client then merges by the 011/020 rules, so overriding an ontology phrase also needs confirmation.
- `arches.py implied_types`: "who" maps to the model whose root is an E39 Actor. If several are, it takes the one E21 Person. Otherwise it falls back to a model named Person, as before. HER gives Person, as before; the demo now gives Figure.
- `ground._assign_edges`: `<` became `<=` for the left neighbour. The type implied by "who" sits at position 0.0, the same position as a phrase that starts with "who" ("who made"), so before this change it was never seen as that phrase's left end.
- `plan._detail`: "when" with one named record, plus words that exactly match one date form of that record's type, becomes a Detail of that date. That covers "when was Navan Fort built?".
- `tests/test_ontology.py`: the four DoD tests. All four fail on the base code; I ran them against a `git archive` of HEAD~ src.

### Not done
- "where" maps to an E53 link: not built. No bank question asks it. "where is X?" stays a direct answer.
- P2/E55 "what kind of" and P45 "made of": these are property (concept) nodes, and bundle entries only carry link and date phrases (`_absorb`), so the layer cannot attach them. It would need a group or value hook.
- The ontology file has no format validation beyond JSON.

### Checks
- **Bank** (demo venv, `CEIST_BASE=<worktree>/vocabularies/base`, `PYTHONPATH=<worktree>/packages/ceist/src`): before and after are identical, exit 0. answer/right 68, answer/refused 1, refuse/right 7, answer-later/refused-should-answer 11. It newly answers no bank question, so questions.json is unchanged.
- **The three questions** (base → this branch):
  - "who built Navan Fort?": refuses before and after, "couldn't place 'built'". This is correct: the demo Monument's construction phase (O18i E11) has no P14 actor, so there is no builder to follow. Only HER Maritime Vessel has a builder.
  - "who made the Gáe Bulg?": before, "out of grammar (Object isn't a Figure or Group, which 'who' points at)". Now it plans `Find Figures that are the producer of Object 'Gáe Bulg'.` (via `P108i E12 P14`), then Rós Madair refuses it: "walking 'producer' backwards … from one named record". That is ROS-MADAIR.md #3. Alizarin evaluates the same plan in the fixture test.
  - "when was Navan Fort built?": before, "couldn't place 'built'". Now `Show the construction phase start date of Monument 'Navan Fort, Navan'.`, which reads back exactly. The record holds no value for it, so the answer is "no … recorded".
  - Extras: "which objects were made by Cú Chulainn?" now grounds to producer (0 records). "when was Cú Chulainn born?" gives the date_of_birth Detail.
  - Spotted on the way, not caused here: "when was the Gáe Bulg made?" answers with the record itself. "made" seems to be dropped as a filler word, so the question widens silently. Worth a separate task.
- **HER plans 2.0** (local clone 9f6a113): 125/125 as reviewed, no re-pin. HER uses the assembled bundle, not `layered`, so the ontology layer does not reach it. "who" is still Person, and neither the `<=` change nor the "when" change altered any plan. I did not run 1.1, to keep machine load down; nothing in this change is specific to concept collections.
- **memory_ask**: `MemoryVocabulary` keeps its own `implied_types` and does not use `layered`. The `<=` change only matters when a phrase starts at word 0 and a type is implied there. `tests/test_planner.py` passes in the gate, so nothing changed for memory_ask.
- **Gate** passed on 595acf1: root 578 passed (51 skipped, 1 deselected); Ceist 274 passed.

## Graph writes proposed
- Decision: Ceist's CIDOC-CRM ontology layer (`vocabularies/ontology/cidoc-crm/`) keys each phrase by the CRM path that ends at a node, never by the bare property. In HER, 67 of the 89 P14 nodes are audit or spatial metadata. The base wins on conflict, and a phrase that fits two nodes of one model is dropped.
- Pattern: in Arches graphs, an event's date and its actor share the event node (E12, E11, E65…). "who <date verb> X" is that event's P14 link, and "when <verb> X" is its P82a. If the event has no P14 (demo Monument construction), refuse rather than guess.
- Pattern: five of the six starches-demo graphs are HER graphs renamed (Figure=Person, Group=Organization, Object=Artefact, Tale=Heritage Story, Monument). Only Site is an independent CRM mapping.

## Review rounds
- Round 1 (595acf1): **PASS**. Notes: "where", P2/E55 and P45 are not built (the DoD doesn't need them; a follow-up task). The `ground.py` `<=` change is low risk, but HER 1.1 was not run. The "when was the Gáe Bulg made?" widening predates this diff and should be queued as its own task.
