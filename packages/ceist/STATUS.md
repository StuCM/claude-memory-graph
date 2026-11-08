# Ceist: where we are (2026-11-08)

One picture of the system, what is proven, what isn't, and the plan we work from. New work starts from here, not from the latest experiment.

## 1. The system in one line

**question → front end → grounding against the vocabulary → plan → read-back check → Rós Madair → answer**, or a refusal with a partial match and a "did you mean".

| Stage | What it does | State |
| --- | --- | --- |
| Front end | decides it's a question; tokenises | **weak**: refuses search-box fragments ("stories that mention X") outright |
| Vocabulary | phrases → models, fields, links, values (three layers, below) | **thin**: the main gap |
| Grounding and plan | places every word, or refuses; builds the plan | strong; has a known list of grammar gaps |
| Read-back | the plan is narrated, and the query must read back to the same words | strong |
| Rós Madair | runs the query (Parquet/DuckDB; WASM in the browser) | strong; chains and backlinks work |
| Fallback | partial match from what grounded (038) | works, but rarely fires (10 of 109 refusals) |

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
| Demo bank (`bench/demo/questions.json`, 89 questions) | hand-written, near Ceist's phrasing | **regression only**, not coverage | 71 right, 0 wrong |
| Generated demo set (`~/.cache/ceist-questions-demo`, 144 questions, 34 held out) | LLM-written from the schema, **deliberately awkward** | stress test | hold-out **2 of 34 right**, 0 wrong |
| Fresh-graph bench (`bench/ontology/run.py`) | template questions built from the ontology layer's own phrases | does the ontology layer ground correctly | 0 wrong readings; flatters coverage |
| HER plans (`bench/her_plans.py`) | 125 pinned plans | regression | 125/125 |

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

**Decision point:** after A and B, score the realistic set and the awkward hold-out. If the realistic set's unseen answer rate is still well below about 60%, revisit the hybrid (a rewriter in front of Ceist, still checked by it).

## 6. Parked (deliberately not now)
- the TypeScript / browser port (spike done; waits for A and B);
- the question-capture loop (designed);
- the experiment matrix (budget pending; will be re-costed after the estimator fix);
- 008 (value inflections; folded into A);
- 028 (memory graph "made recently");
- 034 (data layer cross-model lists);
- the Rós Madair binding diff and distance predicate for Phil;
- Starches 216 (`build --ui-only`);
- the demo `.search.md` wiring.
