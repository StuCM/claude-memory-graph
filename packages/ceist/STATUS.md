# Ceist: where we are (2026-11-09)

One picture of the system, what is proven, what isn't, and the plan we work from. New work starts from here, not from the latest experiment.

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

**The core problem:** each layer was built ad hoc (an LLM pass, seeds, fixes), with **no definition of what a complete layer contains**. Gaps only show when a question fails.

## 3. How we measure: the benchmarks

| Benchmark | What it is | Use | Latest |
| --- | --- | --- | --- |
| Demo bank (`bench/demo/questions.json`, 90 questions) | hand-written, near Ceist's phrasing | **regression only**, not coverage | 71 right, 7 right refusals, 0 wrong |
| Generated demo set (`~/.cache/ceist-questions-demo`, 144 questions, 34 held out) | LLM-written from the schema, **deliberately awkward** | stress test | hold-out **4 of 34 right** (strict 2), 2 wrong readings (as strict) |
| Fresh-graph bench (`bench/ontology/run.py`) | template questions built from the ontology layer's own phrases | does the ontology layer ground correctly | 0 wrong readings; flatters coverage |
| Reorder set (`bench/assembly/reorder.json`, 30) | right demo-bank questions, reordered or as fragments | does assembly read word order freely | 30 right, 0 wrong (strict 9) |
| HER plans (`bench/her_plans.py`) | 125 pinned plans | regression | 125/125 (3 re-pinned to refusals in 051) |

**Missing: a realistic visitor question set,** and **one command that runs every benchmark** and prints one table.

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
| Cost estimates | about 5–7 times low for small calls: `claude -p` writes ~33k tokens of system prompt per call | estimator needs fixing |

## 5. The plan: three workstreams, in order

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
- the TypeScript / browser port (spike done; waits for A and B; leave bge out of the browser build, or load it only after a refusal for "did you mean");
- the question-capture loop (designed);
- the experiment matrix (budget pending; will be re-costed after the estimator fix);
- 008 (value inflections; folded into A);
- 028 (memory graph "made recently");
- 034 (data layer cross-model lists);
- the Rós Madair binding diff and distance predicate for Phil;
- Starches 216 (`build --ui-only`);
- the demo `.search.md` wiring.
