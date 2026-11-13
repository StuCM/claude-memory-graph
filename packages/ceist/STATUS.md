# Ceist: where we are (2026-11-13)

One picture of the system, what is proven, what isn't, and the plan we work from. New work starts from here, not from the latest experiment.

## 0. Realignment (Stu, 2026-11-12)

From 11-10, the work followed Phil's responder data instead of this plan (059–067), and some rules slipped:
- **The exam became the training set.** The testbed was scored 5 times, every new right was read question by question, and the specs fixed what those readings showed. The frozen responder set (`ad2e6bba`) was scored by 059 and again by 060. 067 planned to pass testbed halves to setup as `--questions`, which `VOCAB-TRAINING.md` forbids ("never the frozen exam").
- **A disproven method came back.** 067 turned refine rounds on by default; §4 records them as disproven on casual wording.
- **`ceist setup` (059) became a second route.** It ran only part of `VOCAB-TRAINING.md` (no list items, no generated questions), and 060–066 were tuned through it.
- **Live API runs were used to find bugs.** 067's live run crashed three times on code bugs, then hung in the gate for 3 hours (stopped, $0 lost: every reply was cached).
- **Results levelled off.** The testbed was unchanged from 064 to 066: 15 read right, 6 unread, 0 wrong.

**What holds from now:**
1. **No LLM at question time, until the no-LLM approach is concrete.** The hybrid (an LLM proposing at question time, 061) is later work, designed on top of a finished build-time route, not alongside it.
2. **One route.** `VOCAB-TRAINING.md` steps 0–8 are the route. `ceist setup` runs those steps in order, calling the same code; it is not a separate version.
3. **Every question set has one role:**

   | Role | Sets | Rule |
   | --- | --- | --- |
   | Regression | demo bank, HER plans, reorder set, golden dump | must not change; every task runs them |
   | Development | responder practice (`d716b5cf`), generated train sets, **Phil's testbed** (read too closely to stay an exam) | tune on these; specs may name their questions |
   | Exam | frozen responder set (`ad2e6bba`), generated hold-outs, a fresh set on Phil's real corpus (to ask him for) | scored once per milestone by the orchestrator, never by a worker mid-task, never passed as `--questions` or `--seed` |
4. **Fix by class, not by question.** A spec names a class of failure (a grammar rule, a vocabulary element), with development questions as examples; a fix for one question alone is not a task.
5. **Stubs before spend.** The full route runs end to end with stub LLMs (`--llm-cmd`) before any live call; a live run is for data, never for finding bugs.
6. **Refine rounds stay off** unless a run shows them gaining on a hold-out.

## 0b. The reasoned build (Stu, 2026-11-13)

**Why:** `ceist setup` (059–067) turned the build into a script. The LLM supplied bare phrase lists; mechanical review and a gate of the script's own template questions pruned them, and no reason was kept. Every testbed loss on 11-12 came from that pruning ("keyholders", "fire stations" dropped as clashes), not from the LLM. The LLM's value is the **broader vocabulary**: everyday words, synonyms and how people phrase each value, link and chain, which no rule produces. It is paid for once at build time and stored, so the runtime stays deterministic.

**What we learnt measuring it:**
- **Count-matching overstates.** Testbed #10 read Organisations for a Building question and matched by luck; #70 matched an expected 0; the gate passed Q11's wrong reading ("Non-listed and Listed"). 066's "21 right" is unjudged.
- **The planner can't chain.** It tries a link only between the two named types. Phil's graphs declare no link targets, so each link looked like it reached 6 models; in the records each reaches exactly one. Tier 3–4 refusals: 12 vocabulary ("couldn't place 'run'"), 8 chaining ("'staff of' can't join Building and Organisation").
- **Tier 4 needs 3+ links** in our schema (#77, #79, #87); "covered by a policy" alone is 2 (a join record).
- **Phil's greasan-ask-bench** (same 100 questions, Claude judging the query, not running it): Qwen 1.5b faithful on 25 of our 55 answerable, 30 more widened or wrong; Ceist 21 right, 0 wrong; union 31. A small model at question time gets structure, misses details; Ceist the reverse.

**The build:**
1. **The script** reads the graphs and reference lists: every element (model, field, list value, link, join record), each link's real targets (schema, else the records, else the CRM range class, via `crm.py`), the mechanical forms (labels, plurals), and flags for judgement (coded labels, link direction).
2. **The LLM supplies the words** per element, each with a short reason, stored per element and keyed by a hash of it (a rebuild pays only for what changed).
3. **Words are checked, never silently dropped.** A word that could name two elements goes back to the LLM for a ruling with a reason.
4. **The loop:** questions generated from the schema and its links (never the test sets) are asked; an LLM judge marks each reading from Ceist's narration (exact / wider / narrower / wrong / right refusal / missed); for each failure the LLM names the element at fault and supplies its words; repeat until it gains under ~2 on the generated hold-out. Grammar gaps come to us as tasks, never as vocabulary.
5. **The planner** reads a **link catalogue** (links, inverses, join records) from the bundle and chains through it. No hop limit: every link in a chain must be accounted for by the question's words, except a join record, and exactly one chain must fit, else "did you mean".

**Scoring** uses the same judge on the test sets plus the count; where they disagree, a person reads it. The test sets are only ever judged, never fed back.

**Not used:** pyoxigraph (plain Python and `crm.py` cover the catalogue); an LLM at question time (061 waits until this is measured).

**Cost (Phil's schema; Sonnet's measured token use from 11-11/12 runs, `prices.py`):**

| Step | Calls | Sonnet | Opus |
| --- | --- | --- | --- |
| Words: models and fields, with reasons | 101 | $1.12 | $2.24 |
| Words: list values, with reasons | 44 | $1.10 | $2.20 |
| Words: links and join records | 5 | $0.18 | $0.36 |
| Rulings on clashes (241 flags, 20 a call) | 13 | $0.25 | $0.49 |
| Questions from the catalogue | 50 | $2.72 | $5.44 |
| Judge: testbed, 93 readings | 5 | $0.07 | $0.13 |
| Loop, per round: judge ~400 generated, diagnose ~150, words for faults | 38 | $0.63 | $1.27 |
| **Whole build, 3 rounds** | | **$7.33** | **$14.65** |
| Mixed: Opus for rulings and diagnosis only | | **$7.80** | |

Estimates, ±50%: reasons lengthen replies, and flag and refusal counts will move. Each new stage goes into `vocab estimate`, and the first live run's ledger re-calibrates it. HER is about 4–5 times this schema.

## 1. The system in one line

**question → front end → grounding against the vocabulary → plan → read-back check → Rós Madair → answer**, or a refusal with a partial match and a "did you mean".

| Stage | What it does | State |
| --- | --- | --- |
| Front end | tokenises; a fragment is answered when it assembles, else labelled a statement | fixed by schema assembly (051): "medieval raths in County Down" answers |
| Vocabulary | phrases → models, fields, links, values (three layers, below) | **thin**: the main gap |
| Grounding and plan | places every word, or refuses; schema assembly (the default since 051) builds every reading the schema allows and answers only when exactly one fits | strong; has a known list of grammar gaps |
| Read-back | the plan is narrated, and the query must read back to the same words | strong |
| Rós Madair | runs the query (Parquet/DuckDB; WASM in the browser) | strong; chains and backlinks work |
| Fallback | partial match from what grounded (038), offered only when every refused reading gives the same one | works, but rarely fires (17 of 98 refusals on the generated set) |

**The rule that holds throughout: never guess.** A word Ceist can't place means a refusal. In every test so far, **wrong answers stayed at or near 0.**

## 2. The vocabulary: three layers, and what each is missing

| Layer | Where | Holds today | Missing |
| --- | --- | --- | --- |
| **Ontology** (CIDOC-CRM, shared by every graph) | `vocabularies/ontology/cidoc-crm/` | phrasings on CRM **paths** (29 by hand, plus 69 accepted from the live run, plus a few more) | **class words** ("person, people, who" for E21; "place, where" for E53), at **0%**; **both directions of each property** from CRM's own labels; ambiguous phrases are dropped |
| **Graph base** (per graph, e.g. HER) | `vocabularies/base/<graph id>/` | nodegroup, field and link phrasings | **type words** (none at all: "people" for Person was lost); base-graph names for renamed graphs; inverse and noun forms of links |
| **Client** (per site) | the site's `vocab/` | the demo's extras, period combos, confirmed overrides | plural values ("townlands"), synonyms; the data-layer LLM run made things worse once (rejected) |

**CRM-first (053).** The ontology layer is now the default home for a phrasing; the graph and client
layers hold the exceptions, each with a reason (`vocabularies/coverage/crm-first.json`, shown by `vocab
coverage`). `vocab crm-first` moved 1,474 base phrasings (152 CRM paths, gated) and 148 copies the ontology
already gave into `phrases.json`; plain fields (`"kind": "field"`) and time-span ends are now ontology
paths. Across HER the ontology gives 31% of a graph's phrasings (was 7%); the rest is each graph's delta:
3,326 on an ambiguous path, 962 on a path the gate rejected, 799 site-specific (value combos), 791 clashes,
2 non-CRM. Rules compose a path's base meaning from its CRM labels ("P108i E12 P4" → "date of
production"), and review gives a phrase to the path rather than the node it reaches.

**The core problem:** each layer was built ad hoc (an LLM pass, seeds, fixes), with **no definition of what a complete layer contains**. Gaps only show when a question fails.

## 3. How we measure: the benchmarks

| Benchmark | What it is | Use | Latest |
| --- | --- | --- | --- |
| Demo bank (`bench/demo/questions.json`, 90 questions) | hand-written, near Ceist's phrasing | **regression only**, not coverage | 71 right, 7 right refusals, 0 wrong |
| Generated demo set (`~/.cache/ceist-questions-demo`, 144 questions, 34 held out) | LLM-written from the schema, **deliberately awkward** | stress test | hold-out **4 of 34 right** (strict 2), 2 wrong readings (as strict) |
| Fresh-graph bench (`bench/ontology/run.py`) | template questions built from the ontology layer's own phrases | does the ontology layer ground correctly | 0 wrong readings; flatters coverage |
| Reorder set (`bench/assembly/reorder.json`, 30) | right demo-bank questions, reordered or as fragments | does assembly read word order freely | 30 right, 0 wrong (strict 9) |
| HER plans (`bench/her_plans.py`) | 125 pinned plans | regression | 125/125 (3 re-pinned to refusals in 051) |
| Responder practice (`~/.cache/tmp-aonach/responder-practice.json`, 20) | Phil's responder data, our wording | development | 6 right, 5 right refusals, 0 wrong (060) |
| Phil's testbed (`~/.cache/tmp-aonach/testbed`, 93 scorable) | his 100 questions, four tiers, his wording | development (since 11-12) | 15 right + 6 unread, 0 wrong (064–066); aonach text 23 right / 33 wrong |
| Frozen responder set (`~/.cache/tmp-aonach/responder.json`, `ad2e6bba`, 35 + 4 near-me) | Phil's tests and docs | **exam** | 10 right, 10 right refusals, 0 wrong (060) |

**Missing: a realistic visitor question set,** and **one command that runs every benchmark** and prints one table. Each set's roles are in §0.

## 4. What experiments proved and disproved

| Experiment | Result | Verdict |
| --- | --- | --- |
| Ontology layer on graphs with no vocabulary (026, 029, 033) | right answers roughly doubled on lingo, Catalina and HER; 0 wrong readings | **proven**: the ontology layer is worth investing in |
| Refine loop on the demo client layer (2 rounds) | unseen 2/34 → 2/34; found nothing to fix | **disproven** for casual wording |
| Accepting search-box fragments as questions | +5 only: unknown words underneath | not enough on its own |
| Learned rewrite patterns (no LLM) | 2/34 → 2/34 | **disproven** at this data size |
| Live LLM rewrite (the ceiling) | ~9/34; blocked by grammar gaps | not the fix on its own |
| Type-word synonyms (people → Figure, stories → Tale) | most of the 7 → 22 gain on train | **cheap, big**, and belongs in the vocabulary |
| bge-small on the words the awkward set leaves unplaced (no LLM; `~/.cache/tmp-demo/bgecheck/`) | 74 words in 41 refused questions: right and confident 3, right but too close to call 13, wrong or no right candidate near 58; would fix 2 questions. Wrong picks score as high as right ones (0.84–0.91 vs 0.65–0.75) | **disproven** as a question-time fix; looser thresholds would bring wrongs. A weak build-time hint (top pick right about 1 time in 4) |
| Loosening: drop the unplaced words, accept fragments (`~/.cache/tmp-demo/bgecheck/loosen.py`) | of 109 refusals: 10 right, 11 right but wider, **26 wrong**, 62 still refused; demo bank: "which tales are about love?" answers with every tale | **disproven** as answers (wrong outnumber right); possible as a labelled "closest I can do" suggestion, an extension of 038 |
| Schema assembly as the default (049–051) | demo bank unchanged (78 right incl. refusals, 0 wrong); reorder 9 → 30 of 30; train 10 → 16 right; hold-out 2 → 4; fresh-graph catalina 729 → 746, independent 74 → 95, HER 595 → 589; 0 wrong throughout; median time ~120 ms, worst cut from 822 to 174 ms on the bank | **proven**: the design to port |
| Cost estimates | about 5–7 times low for small calls: `claude -p` writes ~33k tokens of system prompt per call | estimator needs fixing; `--llm ant` (062) removes the overhead and caps spend |
| aonach head-to-head and reverse test (assessment, `/home/stuart/git/fat/aonach-responder-assessment.md`) | demo bank: Ceist 71 right / 0 wrong, aonach 3 / 52. Testbed: Ceist 7 → 15 right / 0 wrong, aonach 23 / 33 | **proven**: keep Ceist as the grounding core; take aonach's UX ideas |
| Numeric comparisons (060) | testbed 7 → 15 right; frozen responder 4 → 10 right; 0 wrong | **proven**, a grammar class |
| One-command site setup with combination and name-probe gate (059, 065, 066) | catches wrong-answer risks a one-word gate missed ("covered by" read as insurer; partial name binds); testbed flat from 064 to 066 | **proven as a gate**; not yet the full route (067) |
| bge on leftover words in an open slot (063) | five wrong readings at the open slot, all fixed by making it exact-only | **disproven** again at question time; vector picks are "did you mean" only |

## 5. The plan: three workstreams, in order

**The next steps, in order (2026-11-13; §0b):**

| Task | What | After | Done when |
| --- | --- | --- | --- |
| 068 | 067's fix commits only (gate speed, review agreement, negator, hyphen and question fixes); its route is not kept | — | regression sets unchanged |
| 069 | one benchmark command, with the LLM judge; disagreements settled by a second LLM judgement, unclear ones to Stu; an exam needs a logged flag | 068 | reproduces 066's counts; the judged 066 score is the baseline |
| 070 | link catalogue: real targets (schema → records → CRM), inverses, join records, in the bundle; a sense check in the planner | 069 | each testbed link has its one real target; regression unchanged |
| 071 | chaining planner: words-accounted chains, no hop limit; takes 048 | 070 | the 8 chaining refusals; 0 wrong |
| 072 | vocabulary one entry per element id, words appended with provenance; clashes queued, not dropped; site builds propose ontology words; reconcile | 070 | the words dropped on 11-12 stay; ontology untouched by a site build |
| 073 | the LLM supplies words with reasons, and rules on clashes | 072 | stub build complete; the 12 vocabulary refusals are its target in the live run |
| 074 | questions generated from the catalogue: tiered, chains, must-refuse, voices, target plans, train/hold-out | 070 | every tier and link covered |
| 075 | the loop: judge, diagnose, supply, check; stop rule | 073, 074 | stub run with a stop reason; then Stu approves the live run |
| later | ontology sweep for HER and the demo (class words, both directions, ambiguous CRM paths) | 075 | demo and HER sets |

071 and 072 run in parallel (planner and vocabulary). 057's demo bugs and 058 follow 071. Every task states its expected effect and closes against it; `STATUS.md` is updated at each merge.

**A. Systematic vocabulary coverage** (the biggest gap; replaces ad hoc building)
1. A **coverage checklist** per element:
   - ontology: CRM class words with question words; both directions of each property; paths;
   - graph: type words with base-graph names; link forward, inverse, passive and noun forms; field forms;
   - client: value plurals, alternative labels, synonyms.
2. **Deterministic generators first:** CRM labels (classes and inverse properties, already saved locally), morphology (plurals, tenses), base-graph names, label splitting. No LLM.
3. **A directed LLM fill** of the remaining gaps only, gated as now. (bge was checked as a cheaper ranker and is too weak to replace this step.)
4. **A coverage report per element**, as a build stage in `VOCAB-TRAINING.md`.

**B. The grammar gaps** (a short, known list from the refusals)
- search-box fragments as queries;
- type-value filters ("sites that are townlands");
- "no recorded X";
- decades ("died in the 1920s");
- record-detail lookup variants;
- the remaining negation forms;
- no partial match for counts;
- the name-match bug ("called something with bally").

**C. Measurement and guidance**
- **One benchmark command** running every set above, plus a **realistic visitor question set**: the honest score.
- **The cost-estimate fix** (the `claude -p` overhead and cache writes, calibrated from the cost record).
- UI guidance (suggestions as you type, a refusal that offers a plain-form question) waits for the TypeScript port.

**Decision point:** after A and B, score the realistic set and the awkward hold-out. If the realistic set's unseen answer rate is still well below about 60%, bring the capture loop forward: learn from real refused questions at build time. There is no LLM at question time; it would be too slow in the browser.

**When vocabulary work ends:**
1. The coverage checklist is at 100%, or each remaining item has a recorded reason. The list is finite: it is bounded by the schema, not by English.
2. Some things are not vocabulary's job:
   - topics the data doesn't record (refusing them is right);
   - filler words and question shapes (they belong to B);
   - misspelt or partial names (they belong to name matching).
3. Results level off: a round that adds fewer than about 2 right answers on the hold-out set stops.
4. Live: repeated in-scope refusals (the same phrase 3 or more times in the capture log) stay under an agreed rate.

After that, builds run only when the schema changes or the capture log repeats a phrase, and they run automatically. Work on the ontology layer carries across every site.

## 5a. Schema assembly (049–051): decisions
- **The default since 051**, and the only mode the TypeScript port carries. Strict wiring stays behind `assembly="strict"` / `CEIST_ASSEMBLY=strict` for comparison until the port. Reordered and fragment questions: 9 → 30 of 30 right, 0 wrong.
- **It does everything strict did:** the partial match (only when every refused reading gives the same one), the `statement` label (a non-question that doesn't assemble), the memory graph's loose listing (free text only), and strict's refusal wording.
- **An implicit end opposite a type needs a role or a value to name it.** "Which airmen flew in the Lancaster?" answers (the Lancaster names an Aircraft); "which monuments are in County Nowhere?" still refuses. A bare preposition orders its ends: "what is in Clock Tower" never reads as what holds it.
- **Known cost:** "which groups have people associated with them?" now refuses (an implicit end opposite a type, no value). HER: "architects died before 1800" and "areas surveyed by Historic England" ask between 5 and 4 readings; "buildings in Southwark" refuses rather than answer about Heritage Stories.
- **A value held by several fields means any of them** (Stu, 2026-11-09). "rath" is monument type *or* functional type, and the narration says so. This replaces strict mode's silent first-field pick.
- **Word order decides direction only for links between two records of the same type** (a tale's parent tale, a figure's father). The schema can't tell those apart.

## 5b. Direction: an ontology base, with graphs as the delta (Stu, 2026-11-09)
- **The ontology gives the base meaning.** A path's meaning is composed from the labels along it, across several hops, not one link. Anything built on that ontology starts with it.
- **A graph adds only its delta,** through its node structure and names. The graph and client layers hold what the ontology can't say, each with a reason (task 053).
- **One vocabulary per ontology** (`vocabularies/ontology/<name>/`), each built and gated on its own. An extension or profile (CRMsci, Linked Art) holds only what it adds, and names the parent it builds on. A site declares its ontology, and at build time Ceist stacks that site's layers into one runtime vocabulary: ontology (with its parent) → graph delta → site terms.
- **Ontologies are pluggable.** CIDOC-CRM is the first. The same machinery can build a base vocabulary for any RDFS or OWL ontology (task 054, draft), so Ceist works for any domain whose data sits on a shared ontology, not only heritage.

## 6. Parked (deliberately not now)
- the hybrid: an LLM at question time proposing a rewording that Ceist then grounds (061, Qwen). It waits until the no-LLM route is concrete (§0), and Phil's `serve.py`;
- the TypeScript / browser port (spike done; waits for A and B; leave bge out of the browser build, or load it only after a refusal for "did you mean");
- the question-capture loop (designed);
- the experiment matrix (budget pending; will be re-costed after the estimator fix);
- 008 (value inflections; folded into A);
- 028 (memory graph "made recently");
- 034 (data layer cross-model lists);
- the Rós Madair binding diff and distance predicate for Phil;
- Starches 216 (`build --ui-only`);
- the demo `.search.md` wiring.
