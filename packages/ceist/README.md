# ceist

*Ceist* is Irish for "question". The package turns a plain-English question into a structured query over a graph, without using an LLM. It never guesses.

```python
from ceist import interpret, narrate
from ceist.arches import ArchesVocabulary

vocab = ArchesVocabulary.from_data_dir("data")
meaning = interpret(vocab, "which listed buildings are on site Leeds Dock?")
narrate(meaning.plan)
# "Find Buildings that site Site 'Leeds Dock' and whose heritage status is Listed."
```

The planner knows nothing about any particular database. It grounds each question against a **vocabulary**, meaning what the data source itself calls things:

| the vocabulary gives | a question names it as |
| --- | --- |
| types | "buildings", "decisions" |
| relations | "on site", "designed by", "affects" |
| controlled values | "listed", "protected" (an alt label), "superseded" |
| date fields (optional) | "built before 1900", "made last month" |
| record names | "Leeds Dock", "Ada Lovelace" |

From that it builds a small, backend-neutral **plan**, and each **output** compiles the plan for its own engine.

## How a question is read

1. **Ground.**
   - Relation phrases are matched first, longest first.
   - Controlled values and type names follow; multi-word types like "insurance policies" count.
   - Dates: "in 1850", "before 1900", "after", "since", "between 1800 and 1850", "the 1890s", "the 19th century", "May 2020", ISO dates, "last year", "in the last 3 months". A word like "built" picks the date field. Without one, the type's only date (or its default date) is used; if it could be either of two, the planner refuses and asks which.
   - Negation: "not", "no", "without", "never", "isn't", "don't", "non-". Each one negates the next thing named: a relation, a value, a date, or a type ("sites with **no buildings** designed by X" negates the hop to buildings, not the architect).
   - Up to two named records become anchors. Only a name may bind one: a record that merely mentions the word does not.
   - When two types are named but no relation is, a join is implied only if exactly one relation connects them.
2. **Refuse rather than guess.**
   - Statements are not answered.
   - Neither are questions outside the grammar.
   - Neither are questions where too little of the text grounded (coverage below 60%).
   - Neither are questions naming two records whose role in the question is unclear.
   - Neither are questions with a "not" that has nothing after it to negate, because dropping it would invert the answer.
3. **Plan.**
   - `Plan(type, where=[...], count, recent)`.
   - Conditions are `LinkTo` (to a record, or to the records a nested plan selects, in either direction), `HasValue`, `DateRange`, `Mention`, `Contains`, and `Not` around any of them.
4. **Relax.** The plan comes with looser variants, in order, for a backend to try when the strict plan finds nothing. One drops a word that matched nothing; another treats a loose link as a text mention. Each variant carries a note that says what was dropped.
5. **Narrate.** `narrate(plan)` reads the plan back in English, so a person can see what was understood before trusting the answer.
6. **Read back.** Each compiling output turns the query it is about to send back into a plan (`read_back`) and compares the two narrations (`ceist.check`). If the compiled query says something different from what was understood (a dropped "not", a wrong record, a missing narrower concept), it doesn't run. `explain` shows both:

```
── understood ──
  Find Buildings whose architect is not Person 'Ada Lovelace'.
── query ──
  {"model": "…building…", "measures": ["select_ids"]}
  {"model": "…building…", "measures": ["select_ids"], "where": {"has_link": {"path": "architect", …}}}
  (the first, minus the records each later one selects)
── query says ──
  Find Buildings whose architect is not Person 'Ada Lovelace'.
  ✓ matches what was understood
```

## Outputs

| output | module | runs | can't express (refused by name) |
| --- | --- | --- | --- |
| **Alizarin** | `ceist.alizarin` | in-process, straight over a data_dir's tiles | nothing in the plan |
| **Rós Madair** | `ceist.rosmadair` | `compile_plan` / `to_query` produce the Query IR; `ask` runs it on a snapshot | links walked backwards, a negated link inside a hop, free text |
| **Arches Search** | `ceist.arches_search` | `to_payload` / `compile_checked` produce an advanced-search GroupPayload | concepts (unless `concept_operator=`), a link by any field |
| **SPARQL** | in the memory graph (`claude_memory_graph.planner`) | Oxigraph | — |

How dates and negation compile:

| | Rós Madair (unchanged) | Arches Search | SPARQL |
| --- | --- | --- | --- |
| date | `range`, in days since 1970: Alizarin's `quantize_date`, which the emitter uses | `BETWEEN` / `>=` / `<=` with ISO dates | `SUBSTR(STR(?d),1,10)` compared with ISO dates |
| not (value, date) | `not` | clause quantifier `NONE` | `FILTER NOT EXISTS` |
| not (link) | a second query, subtracted (Rós Madair refuses `not` over a link, which is chunk-coarse) | quantifier `NONE` / `traversal_quantifier: NONE` | `FILTER NOT EXISTS` |

One Rós Madair behaviour to know about: a query with no filter, or only a `backlink`, isn't limited to its `model`, so "how many buildings are there?" counts every record. `ceist.rosmadair.ask` resolves such queries and keeps only the model's own records. This and the other Rós Madair workarounds are written up, ready to raise upstream, in [ROS-MADAIR.md](ROS-MADAIR.md).

A compiler that can't express a condition raises `Unsupported` with the reason. It never drops a condition silently. The runners then fall back to the next relaxation, or say what they couldn't do.

### Arches data (Alizarin, Rós Madair, Arches Search)

`ArchesVocabulary.from_data_dir(path)` reads the layout that Alizarin and Rós Madair share:

```
data/graphs/*.json           resource models     → types; resource-instance nodes → relations
data/resources/**/*.json     business data       → record names (and tiles, for Alizarin)
data/vocabularies/*.xml      SKOS thesauri       → controlled values, via Alizarin's RDM cache
```

- **Concept ids.** They come from Alizarin, so they are the same ids that Rós Madair interns.
- **Value hierarchy.** "Listed" covers "Grade II": each output expands a value to include every narrower concept.
- **Alternative labels.** They are read from the SKOS, so "protected" finds Listed.
- **Dates.** Each `date` node, named by its own name. Add words that pick it with `date_forms`.
- **Relation synonyms.** Teach phrasings like "designed by" with `relation_forms`:

```python
vocab = ArchesVocabulary.from_data_dir(
    "data",
    relation_forms={"architect": ["designed by"]},
    date_forms={"construction_date": ["built", "constructed"]},
)
```

```python
from ceist.alizarin import ask                      # no server
print(ask("which sites have buildings designed by Isambard Brunel?", vocab))

from ceist.rosmadair import to_query, ask as rm_ask # pip install ros-madair
to_query(interpret(vocab, "how many listed buildings are on site Leeds Dock?").plan, vocab)
# {"model": "<building graph id>", "measures": ["count_records"],
#  "where": {"all": [{"has_link": {...}}, {"concept": {"op": "descendant_or_self_of", ...}}]}}

from ceist.arches_search import to_payload
to_payload(interpret(vocab, "which sites have buildings designed by Ada Lovelace?").plan, vocab)
# a Site group with a child Building group: relationship (building.site, is_inverse) and
# the clause architect REFERENCES_ANY [Ada's id]
```

### Your own graph

Implement `ceist.Vocabulary`: `type_words`, `relations`, `values`, `rank_entities`, `implied_types` and `hint_words`, plus `date_fields` if questions should be able to filter on dates. `ceist.index.NameIndex` handles record-name ranking. Then compile the plan however your store is queried. The memory graph's `MemoryVocabulary` and `compile_sparql` are a worked example.

## Matching: layers, a vocabulary bundle and a config per project

Exact phrase lookup finds what the vocabulary already names. Words it leaves over get a second chance from a **chain of matching layers**, configured per project. Questions are still answered with no model at query time.

```
question → exact phrases (relations, values, dates, types, records)
         → leftover words → shortlist by structure → matcher chain → match | "did you mean" | refuse
         → plan → compile → read-back → run
```

- **Shortlist:** the planner's structure narrows what leftover words can mean:
  - a run of words between two named things can only be a relation that joins their types;
  - a run just before a date can only be one of the date fields it could be.
  On the HER evaluation this narrowing is the biggest single gain.
- **Layers** (`ceist.matching`):
  - `exact`: equal or covering phrasings, optionally on word roots, and never "from" against "to";
  - `vectors`: meaning-level matching against the vocabulary's phrasings, with a minimum score and a gap to the runner-up. The model is a choice:
    - `wordllama-256` (default): static word vectors, a 16 MB lookup table (`pip install ceist[vectors]`).
    - `bge-small-en-v1.5`: a small sentence transformer that reads the phrase as a whole, as 34 MB of int8 ONNX, the same file transformers.js runs in a browser (`pip install ceist[onnx]`, then `ceist vectors fetch bge-small-en-v1.5`). On HER, with thresholds tuned on half the questions, it gets 40/49 right with 1 dangerous on the half it never saw, against WordLlama's 36/49 with 3; on all 102 it gets 86 right, 2 dangerous, 96 within one click. Each new text costs a model run, so every vector is kept in the cache folder, and `ceist vectors embed <bundle>` embeds a vocabulary ahead of time (3,696 texts in about 3 s on CPU).

  The first layer to decide confidently wins, and every decision names its layer in the grounding notes.
- **Fallback:** when no layer is sure, the closest items become suggestions. `chooser = "host"` hands them to the caller: a person in a UI, or Claude through `memory_ask`, which then asks again in the graph's own words. `chooser = "none"` refuses instead. `local-llm` and `api` are reserved for later.

```toml
# ceist.toml
[vocabulary]
bundle = "vocab/her.bundle.json"

[matching]
layers = ["exact", "vectors"]
[matching.exact]
roots = true
direction = true
[matching.vectors]
model = "wordllama-256"   # or "bge-small-en-v1.5"
min = 0.6                 # leave out to use the model's own thresholds
gap = 0.08
[matching.fallback]
chooser = "host"
clarify_top = 3
clarify_min = 0.15
```

### Building a project's vocabulary, and measuring it

```
ceist vocab describe <graphs dir> descriptions/ --reference <reference_data dir>   # read the models (Alizarin)
ceist vocab prompt descriptions/ Monument Person …                                  # the instruction for an LLM (or agent)
ceist vocab assemble descriptions/ vocab/ -o her.bundle.json --graphs <graphs dir> # validate and bundle
ceist vocab check her.bundle.json <graphs dir>                                      # stale since the graphs changed?
ceist eval --bundle her.bundle.json --questions cases.json --config ceist.toml \
           --min-right 80 --max-dangerous 3                                         # the acceptance gate
ceist vectors fetch bge-small-en-v1.5                                               # a transformer for the vectors layer
ceist vectors embed her.bundle.json --config ceist-bge.toml                         # its phrasings, once
```

To tune a model's thresholds without grading it on the same questions, use `ceist eval --half even` to tune and `--half odd` to report. `bench/her_tune.py` does the whole sweep.

`ArchesVocabulary.from_data_dir(path, bundle="her.bundle.json")` uses a bundle's link and date phrasings directly.

### Qualified links: a link and a value on the same entry

Arches often records *who did what* as one entry (a tile) holding a generic actor link and a role. So "designed by Ada" means **one entry** whose actor is Ada **and** whose role is Architect. Ada as builder on one entry plus somebody else's architect entry on the same record doesn't count. A bundle entry with a `qualifier` becomes a qualified link in the plan, read back as "whose actor is Person 'Ada Lovelace' (actor role: Architect)":

| output | compiles to |
| --- | --- |
| Alizarin (in-process) | checks the link and the value within each tile |
| Rós Madair | `{"on_tile": [<the link>, {"concept": …}]}`, its native same-tile predicate, so no workaround is needed |
| Arches Search | a `TILE`-scoped group: the whole search when it's the only condition, otherwise a nested `TILE` group beside the other conditions. Reading the plugin's code suggests a nested `TILE` group may be evaluated per resource when the search has no relationship; that's written up to raise in [ARCHES-SEARCH.md](ARCHES-SEARCH.md). |

A qualifier value that isn't in its node's collection is counted in `skipped_qualified`, never guessed.

CI runs this pipeline on the real Arches HER models: it clones arches-her, describes, assembles the committed vocabulary, and gates `ceist eval` on the blind questions (82/102 right, 3 dangerous, 91/102 right within one click). The flow for a new project is in [bench/ADAPTATION-FLOW.md](bench/ADAPTATION-FLOW.md).

## The grammar, honestly

The grammar covers questions with one subject type and up to two hops. Each question can have up to two named records, any number of controlled values and dates, and "not" in front of any of them. It can ask to count, or for the most recent. It does not handle numeric ranges, "or", or comparisons between records ("older than the Clock Tower"). Questions using those are refused or relaxed, and never half-answered without a note.
