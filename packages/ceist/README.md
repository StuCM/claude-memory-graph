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
| record names | "Leeds Dock", "Ada Lovelace" |

From that it builds a small, backend-neutral **plan**, and each **output** compiles the plan for its own engine.

## How a question is read

1. **Ground.**
   - Relation phrases are matched first, longest first.
   - Controlled values and type names follow; multi-word types like "insurance policies" count.
   - Up to two named records become anchors. Only a name may bind one: a record that merely mentions the word does not.
   - When two types are named but no relation is, a join is implied only if exactly one relation connects them.
2. **Refuse rather than guess.**
   - Statements are not answered.
   - Neither are questions outside the grammar.
   - Neither are questions where too little of the text grounded (coverage below 60%).
   - Neither are questions naming two records whose role in the question is unclear.
3. **Plan.**
   - `Plan(type, where=[...], count, recent)`.
   - Conditions are `LinkTo` (to a record, or to the records a nested plan selects, in either direction), `HasValue`, `Mention` and `Contains`.
4. **Relax.** The plan comes with looser variants, in order, for a backend to try when the strict plan finds nothing. One drops a word that matched nothing; another treats a loose link as a text mention. Each variant carries a note that says what was dropped.
5. **Narrate.** `narrate(plan)` reads the plan back in English, so a person can see what was understood before trusting the answer.

## Outputs

| output | module | runs | can't express (refused by name) |
| --- | --- | --- | --- |
| **Alizarin** | `ceist.alizarin` | in-process, straight over a data_dir's tiles | nothing in the plan |
| **Rós Madair** | `ceist.rosmadair` | `to_query` produces the Query IR; `ask` runs it on a snapshot | links walked backwards, free text |
| **Arches Search** | `ceist.arches_search` | `to_payload` produces an advanced-search GroupPayload | concepts (unless `concept_operator=`), a link by any field |
| **SPARQL** | in the memory graph (`claude_memory_graph.planner`) | Oxigraph | — |

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
- **Relation synonyms.** Teach phrasings like "designed by" with `relation_forms`:

```python
vocab = ArchesVocabulary.from_data_dir("data", relation_forms={"architect": ["designed by"]})
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

Implement `ceist.Vocabulary`: `type_words`, `relations`, `values`, `rank_entities`, `implied_types` and `hint_words`. `ceist.index.NameIndex` handles record-name ranking. Then compile the plan however your store is queried. The memory graph's `MemoryVocabulary` and `compile_sparql` are a worked example.

## The grammar, honestly

The grammar covers questions with one subject type and up to two hops. Each question can have up to two named records and any number of controlled values. It can ask to count, or for the most recent. It does not handle dates, numeric ranges, negation ("not listed"), or "or". Questions using those are refused or relaxed, and never half-answered without a note.
