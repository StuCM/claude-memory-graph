# How Ceist reads a question: the `ground/` package

A walkthrough of `src/ceist/ground/`, file by file, with a small example for each step and the known weak spots. It is written for a reviewer reading the code for the first time. Last updated 2026-11-11, after tasks 040–060.

## The three layers

| Layer | Where | What it does |
| --- | --- | --- |
| **Find the pieces** | `ground/__init__.py` `pieces()` | Runs a fixed list of *readers*. Each looks for one kind of word and **claims** the words it uses, so no later reader can take them. |
| **Assemble** (the default) | `assemble.py` | Calls `pieces(fit=False)`, then tries every way the schema lets the pieces join. One reading answers, several ask "did you mean", none refuses. PRECISE-style; see `PRIOR-ART.md`. |
| **Strict** (old; comparison only, not ported) | `ground/__init__.py` `ground()` | `pieces()`, then `_or`, `_wire` (joins pieces **by word order**), `_subject` and `_scope_negations`. |

`pieces()` parameters:
- **`today`**: the date "now" means for relative dates ("in the last 10 years", "recently"). It's `None` (the real today) except in tests and the golden dump, which fix it so answers don't change from day to day.
- **`fit`**: `True` (strict) runs `_fit_relations`, which picks **one** link for a phrase that several links share. `False` (assembly) keeps every link open, so assembly can try each one.
- **`filler`**: extra words to ignore, never place (assembly passes its filler list).

## Two kinds of match: the graph, and the records

| | Matches against | Found by | Examples |
| --- | --- | --- | --- |
| **Graph (schema) match** | the vocabulary: models, links, fields, values | readers 1–10 | "monuments", "built by", "scheduled", "rath", "capacity" |
| **Record match** | the data: a record's name | found at the start, bound near the end | "County Down", "Cú Chulainn", "Hill of Tara" |

Record names are **reserved first and bound last**:
1. **`_scan` finds every whole record name** in the question before any reader runs (`s.names`).
2. **Every graph reader skips a phrase that sits inside a longer record name.** "Hill of Tara" keeps its "of"; "Giant's Grave" keeps its "grave".
3. **`_anchors` binds the records late,** because it needs the links already found: one record per link, and the link's expected type breaks ties.

So `_anchors` isn't catching records that slipped through. They were protected from the start, and only *bound* at the end.

**Where a record can still lose its words:**
- a phrase **exactly as long as** a record's name wins over it (only *shorter* phrases give way). A record named exactly like a value label ("Rath") is read as the value;
- a phrase that **overlaps the edge** of a name (starting inside it and running past it) claims words the name needs, so the name can't bind.

Both are rare in heritage data, but worth knowing.

## Worked examples: which reader claims each word

Traced on the demo (2026-11-10). Every word ends with one of three outcomes:
- **claimed by a reader**;
- **ignored**, because it isn't a meaningful word ("the", "of"…);
- **LEFT OVER**: a meaningful word nothing placed, which makes the question refuse.

```
how many scheduled raths are near Armagh?
   how, many  -> shape        ('how many' → count)
   scheduled  -> values       (designation or protection type)
   raths      -> values       (functional type / monument type)
   are        -> words        (helper verb: shape only)
   near       -> near         (within 5 km of …)
   armagh     -> records      (Monument 'Armagh, Armagh', used as the point to measure from)
   + imply type: 'scheduled' implies a Monument variable (claims no words)
   uncovered: none → answers (4 on the demo)

how many tales originate from the Ulster Cycle?
   how, many         -> shape
   tales             -> words      (Tale variable)
   originate, from   -> matcher    (no link phrase matched; bge: parent_story, 0.85)
   the               -> ignored
   ulster, cycle     -> records    (Tale 'Ulster Cycle')
   uncovered: none → answers

which folk are associated with Conchobar mac Nessa?
   which                   -> shape
   folk                    -> LEFT OVER   (not a type word; the matcher has no slot for it)
   are                     -> words
   associated, with        -> links       (actor)
   conchobar, mac, nessa   -> records     (Figure 'Conchobar mac Nessa')
   uncovered: ['folk'] → refuses: "couldn't place 'folk'"
```

The third shows the gap in the leftovers stage: "folk" is a type word that the vocabulary doesn't have, and the matcher only looks in three slots (dates, links, group tiles), so nothing retries it as a type word. "Which **people** are associated with …" works, because 039 added "people" as a type word for Figure. Reproduce with `~/.cache/tmp-demo/trace.py`, run from `starches-demo/ask` with questions on stdin.

## What gets stored: words → references → plan → query

A match stores **a reference into the vocabulary**, not the word: an object pointing at a field, a concept, a model or a record id, which comes from the graphs and reference data. Traced on the demo for "how many scheduled raths are near Armagh?":

**1. The grounding: the readers' output (objects from `model.py`)**
```
count: True
Node        var Monument                                 (from 'scheduled' implying it)
ValueMatch  'scheduled' → Value(field=designation_or_protection_type,
                                concept=843b3e88…, label 'Scheduled', owners Monument)
ValueMatch  'raths'     → Value(field=monument_type,   concept=0400f05f…, label 'Rath')
                          Value(field=functional_type, concept=0400f05f…, label 'Rath')
NearGround  5 km of Monument 'Armagh, Armagh' (record id f636805d…)
```
A value keeps every field it could belong to. The concept id is the thesaurus entry, not the text.

**2. The plan: after assembly, backend-neutral** (`plan.py`; shown with `questions.target_of`)
```
model Monument, count
  designation_or_protection_type = Scheduled
  monument_type = Rath   or   functional_type = Rath     (a value in several fields means any)
  geospatial_coordinates near Monument 'Armagh'
```
The plan is also what is **narrated** back ("Count Monuments whose …") and **read back** from the compiled query, to check they mean the same thing.

**3. The compiled query: one backend's language** (`rosmadair.compile_plan`)
```json
{"model": "<Monument graph id>", "where": {"all": [
  {"concept": {"path": "designation_or_protection_type", "op": "descendant_or_self_of", "value": "843b3e88…"}},
  {"any": [{"concept": {"path": "monument_type",   "op": "descendant_or_self_of", "value": "0400f05f…"}},
           {"concept": {"path": "functional_type", "op": "descendant_or_self_of", "value": "0400f05f…"}}]},
  {"bbox": {"path": "geospatial_coordinates", "min_lng": …, "max_lat": …}}]}}
```
- `descendant_or_self_of` includes narrower concepts, so a "rath" subtype counts too.
- "near" becomes a bounding box, refined to the true distance after the query (`keep_near` in the demo's `ask.py`).
- The same plan compiles to Arches Search (`arches_search.py`) or SPARQL (the memory graph) instead.

## The order of the readers

| # | Reader | File | Finds | Example |
| --- | --- | --- | --- | --- |
| 0 | `_scan` | scan.py | the words, record names, the shared notebook | |
| 1 | `_shape` | phrases.py | the kind of question | "how many", "which", "list", "about X" |
| 2 | `_relations` | phrases.py | link phrases | "built by", "part of", "near" |
| 3 | `_group_by` | phrases.py | count per something | "by county", "which county has the most" |
| 4 | `_tile_phrases` | phrases.py | a phrase naming one tile of a nodegroup | "burnt down" |
| 5 | `_values` | phrases.py | controlled values | "scheduled", "rath" |
| 6 | `_field_phrases` | phrases.py | a field named before its value | "monument type rath" |
| 7 | `_near` | phrases.py | a distance | "near Belfast", "within 5 km of X" |
| 8 | `_dates` | phrases.py | dates and their field word | "built before 1900" |
| 9 | `_numbers` | phrases.py | number comparisons and their field | "capacity over 200", "taller than 30 metres" |
| 10 | `_words` | nodes.py | type nouns, negators, hints | "monuments", "not" |
| 11 | `_anchors` | nodes.py | named records | "County Down" |
| 12 | `_fit_relations` | nodes.py | (strict only) one link per shared phrase | |
| 13 | `_imply_model` | nodes.py | a type a value implies | "raths" → Monument |
| 14 | `_match_leftovers` | leftovers.py | second chance for leftover words (roots, then bge) | |
| 15 | `_fill_groups`, `_text_filter` | leftovers.py | clause groups; free text (memory graph only) | |
| 16 | `_coverage` | leftovers.py | how many meaningful words were placed | |

**The order is how contested words are settled.** Each line in `pieces()` carries one comment saying why it sits where it does:
- links come before dates, so "built **by**" is a link and "built **before**" a date;
- `_near` comes before `_dates`, so "2000 miles" is no year;
- `_numbers` comes after `_near` and `_dates`, so "within 20 km of X" stays a distance and "before 1900" a date. It takes only the comparisons they left; `_dates` itself leaves a year-shaped number after a number word ("capacity over 1500"), with a unit, or with a cue;
- `_field_phrases` comes after `_values`, because it needs the values found.

## `model.py`: the shapes of what is found

Plain data classes, no logic. Each is a slot for one kind of meaning.

| Class | What it is | Example |
| --- | --- | --- |
| `Node` | a thing **in the question** (not a graph, and not an Arches graph node): a **var** ("some Monument records", the answer's placeholder) or an **anchor** (a named record). Its `type` is the graph it belongs to. Rename in the port (e.g. `QuestionThing`) to avoid the clash with Arches nodes | "monuments" → var Monument; "County Down" → anchor |
| `Edge` | a link phrase, with two ends to fill (`source`, `target`) | "built by" → relation `actor` |
| `ValueMatch` | a controlled value, with **every** field it could belong to | "rath" → monument type, functional type |
| `DateGround` | a date range and the field the words picked | "built before 1900" → `hi=1900`, construction date |
| `NumberGround` | a number's bounds (each strict or inclusive), the unit said, and the fields it may be on | "capacity over 200" → `lo=200`, strict, occupant capacity |
| `NearGround` | a distance from a named record (measured, not linked) | "near Belfast" → 5 km |
| `GroupGround` | a phrase naming one tile of a nodegroup | "burnt down" |
| `NameGround` | a spelled-out name condition | "whose name starts with Cat" |
| `Grounding` | **the output**: everything above, plus the shape (`wh`, `count`), notes, refusal reason, unplaced words and coverage | |

`pos` is the word position everywhere. Strict joins by it; assembly uses it only where word order genuinely decides (links between two records of the same type, bare prepositions).

**How slots get filled:**
- **From the vocabulary:** links, values, groups and type words. These are phrases in the layers, which can be added to and changed.
- **From fixed grammar in code:** "near / within N km of" (`NEAR_RE`), dates (`dates.py`), number comparisons and units (`numbers.py`), "how many", "not", "called X". The vocabulary only says what they act on, such as which records have a location, or which number fields there are and their units.

### Weak spots
- `Grounding.near` holds **one** distance, so "near Belfast and near Armagh" can't be said.

## `scan.py`: the words and the shared notebook

1. **The grammar word lists** (top of file): question words (`WH`), helper verbs (`AUX`), commands (`IMPERATIVE`), filler (`FILLER`), negators (`NEG`), prepositions (`PREPS`), `NEAR_RE`, and the caps (`MAX_*`). They are deliberately in code, not vocabulary: a site editing them could break never-guess.
2. **`Scan`**, the notebook every reader shares:
   - `words`: the question split into words, with positions;
   - **`consumed`**: word indexes already claimed. This is how "one word, one meaning" works;
   - `taken`: the same idea in character spans, for multi-word phrases;
   - **`names`**: spans where a whole record name appears;
   - `g`: the `Grounding` being filled.
3. **`_scan`** lowercases and normalises ("non-listed" → "non listed", the same length so positions stay aligned), indexes value and group phrases, and finds record names.

### How a phrase is found (`_phrase_spans`)
Ceist never *detects* phrases. It takes **every known phrasing** a reader cares about (every link form, every value label…) and:
1. sorts them **longest first**, by characters;
2. regex-searches the question for each, as whole words;
3. skips a match that **overlaps a span already claimed**, or sits **inside a longer record name**;
4. otherwise claims it.

The question text never shrinks: the claimed spans grow, so positions stay right. Example: "part of a larger story" (parent story) wins over "part of", which four links share. A phrasing not in the vocabulary is never found, which is why vocabulary coverage matters.

### How a record is found (`_record_spans`)
Records are **ranked** against the question's words (`index.py` `rank`): each matching word scores by its rarity, a word in the record's *name* counts double, and having every name word in the question multiplies the score by 1.5. **Ranking only nominates.** A record binds only if its **whole name or an alias** appears.

```
"crannogs in County Fermanagh"   words: county, crannogs, fermanagh
  52.47  County Fermanagh   (every name word present: x1.5)
  15.29  County Donegal, County Meath, …   ("county" only)
  record span: "county fermanagh"  -> bound

"crannogs in Fermanagh"          words: crannogs, fermanagh
  19.69  County Fermanagh   (the only candidate, but "county" is missing)
  record span: none  -> not bound -> "couldn't place 'fermanagh'"
```

The fix is aliases, not looser matching (task 057): "Fermanagh" as an alias of County Fermanagh, made at build time, only when it is unique and not already a word or phrase. "Down" stays "did you mean".

### Leftover runs (`_leftover_runs`)
Runs of unclaimed words, trimmed to start and end at a meaningful word (or end at a preposition: "designed by"). They go to the matcher and to the "couldn't place" message.

### Weak spots
- **`Scan.seen` holds one variable per record type**, so "figures whose father is a figure" can't have two Figure variables.
- **Short variable names** (`s`, `g`, `w`, `e`, `m`): the TypeScript port uses descriptive ones.
- **Every known phrasing is regex-searched per question**, thousands of times. The port uses a one-pass matcher (a trie, or Aho–Corasick) with identical results (task 042).

## `phrases.py`: readers 1–9

### `_shape`: what kind of question
- First word: a question word goes in `g.wh`. A command ("list", "show", "find") counts as "what", and is claimed, so "Find" isn't read as a value.
- "how many" / "how much" → `g.count = True`.
- "what do we know about X" / "tell me about X" → the answer is X itself, and link-reading is switched off.
- `_name_match`: "whose name starts with Cat", "fort in the name", "called Lismahon" → one word matched against record names.

### `_relations`: link phrases
1. Find longer value and group phrases first, so a link phrase inside one is skipped ("bronze age" is a period, not the link word "age").
2. Try first the links that join types the question names. "Part of" with "tales" tries a tale's parent story before an organisation's parent.
3. Search every link phrasing, longest first.
4. **Skip a phrasing that is just the subject's type name** ("which *monuments*…"), even though "associated monuments" is also a link name.
5. Each link is used once.
6. Record the `Edge`, the phrasing that matched, and every link that phrasing could mean (`sharing`), for assembly to try.

Example: "which tales are part of the Ulster Cycle?" → edge `parent_story`, phrasing "part of".

### `_group_by`: count per something
- "monuments **by county**" (at the end) → count per county;
- "**which county has the most** raths" → count per county, the top one.

### `_tile_phrases`: one tile of a nodegroup
"burnt down" sets several fields of one tile; the clause after it fills in more (`_fill_groups`).

### `_values`: controlled values
"scheduled", "rath", "neolithic". Each keeps **every field** it could belong to; that is where "monument type or functional type is Rath" comes from (a value in several fields means any of them).

### `_field_phrases`: a field named before its value
"monument type rath", "made of bronze": narrows the following value to that field, if nothing meaningful sits between them.

### `_near`: distance
"near X" (5 km) or "within N km/miles of X". It runs only if the vocabulary has map locations, and takes the **first** match.

Example: "souterrains near Belfast" → within 5 km of Belfast (5 results on the demo).

### `_dates`: dates and their field word
1. `dates.find` spots "before 1900", "in the 1920s", "between 1800 and 1850", "recently".
2. Field words are found separately: "built", "died", "date of production".
3. Each date takes the **nearest field word before it**, else after it. With none, every date field stays possible, and the subject's type decides later.

Example: "built before 1900" → construction start date before 1900.

### `_numbers`: number comparisons and their field
Only when the vocabulary has number fields (`number_fields()`: Arches `number` nodes, with a unit read from the node's name, description, config or the bundle's phrasings, never guessed).
1. `numbers.find` spots a comparison word and a number, with an optional unit or money word and a trailing "tall"/"high"/"long"/"wide": "over 200", "room for 200 people", "between 10 and 30 metres", "worth more than 5 crore". Each is strict ("over", "taller than") or inclusive ("at least", "room for", "between") as `numbers.py`'s table says, and the narration always says which.
2. The field it is on:
   - its own **unit or cue** decides first: "30 metres" is a length, "5 crore" money, "room for" a count, "taller than" a height. A field word just before it must agree ("height over 30 metres");
   - otherwise the **nearest field word before it, else after it** ("capacity over 200"), as dates do;
   - otherwise every number field stays possible, and the subject's type decides: **one** field answers, **several** ask "did you mean".
3. A number followed by a type word ("more than 3 figures") counts linked records, which no field holds, so it is left for the leftovers to refuse.

Example: "buildings taller than 30 metres" → height more than 30 metres (strict: a building of exactly 30 m is left out).

`plan._attach_numbers` converts to the field's unit (feet to metres, crore to the amount) and refuses a unit that doesn't fit the field: "'over 30 metres' is a length, but the insured value of Building is an amount of money". A field with no unit takes only a bare number. A negated comparison is its complement: "not more than 200" is at most 200.

### Weak spots
- **A year-shaped number after "between" or "of", with no unit or cue, is still a date** when the vocabulary has date fields: "capacity between 1800 and 1900" refuses, because "capacity" is left over.
- **Units and cues are a short fixed list** (metres, km, feet; thousand to billion; people). Area units, currencies and words like "storeys" aren't read, so those questions refuse.
- **"capacity of 200" is at least 200** (the table's reading of "capacity of"), not exactly 200.
- **"in" and "within" are claimed too early,** as bare link phrases (from the CRM layer's `P89i` / `E53 P89 E53`). So "within 20 km of Belfast" never reaches `_near`, and "in state care" is read as a location (task 057: read "in" together with what follows).
- **Only the first occurrence of each phrasing** is used, and **each link once**: "near A and near B" fails.
- **Dates pair with the nearest field word.** That's fine in usual English, but fragile in long sentences with several dates.

## `nodes.py`: readers 10–13

### `_words`: type nouns, negators, hints
It goes through the words nobody has claimed yet:
- **multi-word type names first** ("insurance policies"), then single ones: "monuments" → a var of type Monument;
- **negators** ("not", "without", "non") are kept with their position, for `_scope_negations` later;
- **"recent", "latest"** → newest first;
- **hint words** (a vocabulary's own: a word that implies a type) → that type;
- helper verbs, filler, and date words once a date was found → claimed, as shape only.

Finally, **the question word's implied type:** "who" → the model whose CRM class is an Actor (E39), or among several, the Person one (E21).

Example: "which monuments are not scheduled?" → var Monument; "not" kept for later.

### `_anchors`: named records
Up to two (`MAX_ANCHORS`), from the leftover words:
1. Rank records against the leftover words (`rank_entities`). **Only a record whose whole name or an alias is there may bind** (`named_by`); the memory graph alone allows partial names (`partial_names`, for first names like "Stuart").
2. **A record named exactly what was asked beats one that merely mentions it.**
3. **Role fit:** if the links found want a certain type, a near-tied record (≥ 75% of the top score) of that type beats a lexical tie.
4. **At most one anchor per link, or per "near".** A question with no link names at most one record.
5. **The record after "near" becomes the distance's starting point,** not a node.

Examples:
- "souterrains near Belfast" → Belfast is the point measured from;
- "which figures are associated with Conchobar mac Nessa?" → anchor Figure 'Conchobar mac Nessa'.

**`_either_records`:** "County Antrim or County Down" → one anchor that may be either record, if both are the same type.

### `_fit_relations` (strict only; assembly skips it with `fit=False`)
A phrase several links share ("in": a monument's location, a tale's parent story) keeps the link that can join two of the things named. Otherwise:
- a specific phrase ("architect") **refuses**;
- a bare function word ("at") **is set aside**, and the record is linked loosely;
- "which monuments are in Belfast", where Belfast is itself a Monument, **refuses with `_wrong_end`**: "Monument 'Belfast' isn't a Site, which 'in' points at".

### `_imply_model`: a type named by a value
**Only when nothing else is named** (no type, no link): "how many raths are there?" → the values that only Monument holds imply Monument. If several models hold them, it doesn't guess: it offers each as "did you mean".

### Weak spots
- **`_imply_model` gives up when any link was found.** "souterrains within 10 km of Navan Fort" fails because "within" was claimed as a link, so "souterrains" never implies Monument (task 057).
- **The anchor cap is tied to the number of links:** with no link phrase, only one record can be named, and two records need a phrase between them.
- **One var per type** (`seen`), as noted under `scan.py`.
- **Names must be whole** (aliases are the fix, task 057).
- **The "who" check** refused "who was the father of Cú Chulainn?" with a self-contradicting message ("Figure 'Cú Chulainn' isn't a Figure or Group"). It's on 057's list; `_wrong_end` and the "who" implied type are where to look.

## `leftovers.py`: readers 14–16

What happens to words no reader claimed. There are only two outcomes: **placed** or **refuse**. Nothing is silently dropped, except filler words.

### `_match_leftovers`: the second chance
Only with a matcher configured (`ceist.matching.Chain`: exact word roots, then bge vectors), and not for "about X" questions. A leftover run is matched **only against what the structure says it could be**, in three slots:

1. **Just before a date that has several possible fields** (up to 3 words before): pick the date field. In "erected before 1900", "erected" is matched against each candidate field's words. If two fields score too close, it doesn't choose.
2. **Between two named things, when no link joined them:** pick the link that can join their two types. "how many tales **originate from** the Ulster Cycle?" → `parent_story` (bge, 0.85). "stem from" refuses: two links score too close.
3. **Any other run:** match it against the group phrases (tiles) of the types named.

Each time:
- **a confident match** grounds like an exact one, and the note says which layer decided;
- **otherwise** the closest options become **"did you mean"** (`_offer`), and the phrase is logged for learning (`_unplaced`: phrase, slot, model and options, masked) so a later vocabulary build can add it.

### `_fill_groups`: a group phrase takes its clause
After a group phrase ("burnt down"), it takes the values and the date in **its own clause**, up to the next named thing or a clause word ("and", "which", "that"…). It only uses values that fit that group's fields, so "burnt down in 1920" fills the tile's date. A group phrase that absorbs nothing is dropped, and its words are **held**, so they refuse rather than vanish.

### `_text_filter`: free text only
Only for vocabularies with `free_text` (the memory graph): **one** leftover word becomes "mentioning 'x'". Arches vocabularies never do this. For Starches, the labelled Pagefind mention (task 046) is the planned equivalent.

### `_coverage`: how much was placed
`coverage` is placed meaningful words ÷ all meaningful words. `uncovered` lists the words not placed. **`plan.py` refuses if any meaningful word is uncovered:** "couldn't place 'X' — answering without it would widen the question".

### Weak spots
- **The matcher only looks in three slots.** A leftover run anywhere else (a type word like "people" for Figure, a synonym for a value) never gets a second chance. Vocabulary has to cover it.
- **bge separates poorly.** Wrong picks score as high as right ones (measured: 0.84–0.91 against 0.65–0.75), so it rarely decides and mostly supplies "did you mean" (STATUS.md §4).
- **Only one run is tried between two named things** (`between[:1]`).
- **Only one leftover word** can become a text filter.

## Placing the links: the second half of the job

The phrase readers only **nominate** a link: "feature" → `actor`; "in" → named location *or* parent story. They make an `Edge` with **no ends attached**, plus every link the phrase could mean (`sharing`). **Placing it** (which two pieces it joins, and which way round) is a separate step:

| | How a link finds its two ends |
| --- | --- |
| **Strict** (`wire.py` `_assign_edges`) | **by word order:** the nearest piece on each side whose type fits |
| **Assembly** (`assemble.py`, the default) | **by the schema:** a link joins two pieces only if their types fit its domain and range; it tries every pairing and counts the fits |

Example, "which tales feature Cú Chulainn?": "feature" → `actor` (Tale → Figure). The pieces are a Tale var and the Figure record Cú Chulainn. Only Tale →actor→ Cú Chulainn fits, so it answers, in any word order.

Word order still decides two things the schema can't: **links between two pieces of the same type** ("the father of Fionn") and **bare prepositions** ("in", "at").

## `wire.py`: the strict joiner, and four steps both modes share

### Strict only (not ported)
- **`_wire`:** the caps (`MAX_EDGES`, `MAX_VARS`), then `_assign_edges`, `_check_anchors` and `_imply_join`. In the memory graph only, a link with no second end is dropped and the type is listed.
- **`_assign_edges`:** for each link, take **the nearest piece before it and the nearest after it** whose type fits. Then:
  - "X **as** copyright holder" → the phrase names X's role;
  - a missing end gets an **implicit variable** of the type the link wants;
  - the link is turned whichever way more of its types fit.
- **`_imply_join`:** two types named with no phrase between them ("sites with buildings designed by X") are joined **only if exactly one link** connects those types. Otherwise it notes "not guessing".

### Shared with assembly
- **`_or`:** "raths or cairns" → one condition, "rath *or* cairn", when both are values of one field (or both are named records of one type). Otherwise it refuses: "ask one at a time".
- **`_check_anchors`:** a named record must be something its link can point at. "what is in Navan Fort" (a Monument, where "in" points at Sites) refuses, saying why (`_wrong_end`). When the link can't say what it points at, the record's own field may be meant ("what period is Navan Fort"): `field_of`, settled in `plan.py`.
- **`_subject`:** what the question asks for. It's the type "who" implies, else **the first variable named**.
- **`_scope_negations`:** each "not", "no" or "without" negates **the next thing named within 4 words** (`NEG_REACH`): a link, a value, a date, a distance or a name match. A type counts too ("sites with no buildings" negates the link that joins buildings). **If nothing is in reach, the question refuses:** a dropped "not" would invert the answer. The same idea as NegEx (`PRIOR-ART.md`).

### Weak spots
- **The subject is the first variable by position** (a word-order rule both modes use), so leading with a named record can change the reading. "County Antrim souterrains" is read as a yes/no question about County Antrim.
- **The 4-word negation window** misses a "not" said further back. "which tales are not about Cú Chulainn?" refuses: "about" isn't a link phrase, so nothing is in reach.
- **`_check_anchors` produced the self-contradicting "who" refusal** ("Figure 'Cú Chulainn' isn't a Figure or Group, which 'who' points at") in task 057's list. This is where to look.
- **Names:** `_wire` and `_assign_edges` say *how* (wire up), not *what* (join links by word order). Moot, since they aren't ported.

## Where this fits
`interpret()` runs `pieces()`, then **assembly** (`assemble.py`, the default; strict `wire.py` only on request), then `plan._finish` (plan, refusals, "did you mean", partial match). After that: `narrate.py` says it back, `rosmadair.py` compiles it, `readback.py` checks the compiled query means the same.

## `assemble.py`: the jigsaw (the default)

PRECISE-style (`PRIOR-ART.md`): **list every way the schema lets the pieces join, and answer only when exactly one meaning fits.**

### `assemble()`: the steps
1. **`pieces(fit=False, filler=FILLER)`.** The readers run, with every link a phrase could mean kept open. `FILLER` adds PRECISE's "syntactic markers", function words that name nothing ("their", "same", "through", "someone", mid-sentence "who/which"). **An unknown content word still refuses.**
2. **`_or`** (shared with strict): "raths or cairns" → one any-of condition, or a refusal.
3. **`readings()`**: enumerate every allowed reading (below).
4. **`_finish`** (in `plan.py`) turns each reading into an interpretation: a plan, or a refusal with its reason.
5. **Group the answering readings by their canonical narration** (`_key`). Two readings that *say the same thing* count once (PRECISE's equivalence check).

### `interpret()`: the decision
- **One distinct meaning** → answer it.
- **Several** → refuse with **"N readings fit; did you mean 'A' or 'B'?"**, each narrated.
- **None** → refuse with the reason (`_none`): a word it couldn't place, or "no reading fits the schema: 'X' can't join A and B".
- A non-question that doesn't assemble is labelled a **statement**. A fragment that *does* assemble is answered.
- **Partial match** (`_agreed`): offered only if **every** refused reading gives the same one. If they differ, picking one would be a guess.

### `readings()`: how the readings are listed
For every combination (`itertools.product`) of:
- **each link phrase → one of its links, between two pieces whose types fit** (`_link_options`). It is tried either way round, except where word order must decide;
- **two groups of pieces no phrase joins → joined by any one plain link that fits** (`_joins`). Each candidate link is a reading. A named record beside a type with no link stays loose ("linked to or from");
- **each value → a variable whose type holds that field** (`_value_options`). Within that type, a value in several fields means any of them;
- **each date → a variable that has one of its date fields** (`_date_options`);
- **each number comparison → a variable that has one of its number fields** (`_number_options`);

then:
- **reject** a combination where one named record ends two links ("a record is one piece");
- `_check_anchors`, `_subject` and `_scope_negations` (shared from `wire.py`) on each;
- **stop at 256 readings** (`MAX_READINGS`): "ask one thing at a time".

### `_link_options`: where a link may sit
For a link phrase, given the pieces:
- **Both ends named:** every (link, piece A, piece B) whose types the link joins.
- **Two pieces of the same type** (Figure–Figure, Tale–Tale): word order decides which is which (`_in_order`, the same rule strict uses). "X **as** father" makes X the target.
- **One end missing:** the missing end becomes an *implicit* variable of the type the link wants, **but only** if the link has a role ("architects", "surveyed by") or a value names that type ("flew in **the Lancaster**" → Aircraft). Otherwise "in County Nowhere" would become "in any Site".
- **A bare preposition** ("in", "at", no content word) **orders its ends like a same-type link.** "What is in Clock Tower" asks what Clock Tower holds, never what holds it.
- **Nothing fits:**
  - a bare function word is set aside;
  - "which monuments are in Belfast" (where Belfast is a Monument) refuses with the reason;
  - a specific phrase refuses ("'designed by' can't join …");
  - in the memory graph, the link is dropped and the type listed (loose listing).

Example, "which tales feature Cú Chulainn?":
- the pieces are a Tale var, the Figure 'Cú Chulainn', and "feature" → `actor`;
- the options are `actor`: Tale → Cú Chulainn (the only pairing whose types fit);
- that gives 1 reading, which answers.

Example, "which architects died before 1800?": the role link "architects" and the date can sit on a Person or on the Person's associated organisation, so 5 readings fit, and it asks "did you mean …".

### Worked examples, traced on the demo (2026-11-10)
Reproduce with `~/.cache/tmp-demo/asm_trace.py`, run from `starches-demo/ask` with questions on stdin.

**"which figures are associated with Conchobar mac Nessa?" → answers**
```
1 pieces   var Figure · anchor Figure 'Conchobar mac Nessa' · link 'associated with' → [actor]
2 options  actor: Figure var → Conchobar           (same type: word order puts the var first)
3 readings 1: "Find Figures whose actor is Figure 'Conchobar mac Nessa'."
4 meanings 1
5 decision ANSWER
```

**"what is in County Down?" → asks**
```
1 pieces   anchor Site 'County Down' · link 'in' → [named_location, parent_story]   (no subject named)
2 options  named_location: Monument → County Down     (a Monument end is implied by the link)
           named_location: Object   → County Down     (so is an Object end)
           parent_story            (dropped: its ends are Tales, and County Down is a Site)
3 readings 2: "Find Monuments whose named location is …", "Find Objects whose named location is …"
4 meanings 2
5 decision REFUSE: "2 readings fit; did you mean 'Find Monuments …' or 'Find Objects …'?"
```
Never-guess at work: "what" names no type, and two types can be "in" a place.

**"figures in tales of the Ulster Cycle" → asks, but both options are wrong** (known gap)
```
1 pieces   var Figure · var Tale · anchor Tale 'Ulster Cycle' · link 'in' → [parent_story, named_location]
2 options  parent_story: Ulster Cycle → Tale var      ("in" taken as the Tale–Tale link, by word order)
3 readings 2: Figure joined to Tale by copyright holder, or by actor (_joins: no phrase joins them)
5 decision REFUSE with 2 "did you mean" options, both reading "Tales that are the parent story of Ulster Cycle"
```
Two weak spots show at once:
- **"in" went to the wrong pair.** "Figures **in** tales" is the Figure–Tale link.
- **"of" isn't understood.** "Tales **of** the Ulster Cycle" is the parent-story link pointing the other way, and nothing reads "of", so the bare-preposition order rule inverts it.

Task 057's "read 'in' with what follows" and the "of" rule are the fixes.

**"which tales are linked to Cú Chulainn?" → refuses** (known gap)
```
1 pieces   var Tale · anchor Figure 'Cú Chulainn' · link 'linked to' → [actor, associated_actors]
2 options  none: each of those links is phrased "linked to" only on other models (Monument),
           and a phrasing is kept per model (said_as), so Tale's actor link isn't "linked to"
5 decision REFUSE: "'linked to' can't join Figure and Tale"
```
"Which tales **feature** Cú Chulainn?" works. This is a vocabulary gap (the phrasing is per model), which CRM-first coverage should close: the phrase belongs on the CRM path, not on one model's node.

### Weak spots
- **Plain enumeration.** Readings multiply with each piece (links × pairings × values × dates), capped at 256. Fine for a handful of pieces. If questions grow (task 057's 2-record cap, longer chains), use PRECISE's max-flow matching instead (marked `ponytail:` in `readings`).
- **Same-type direction is word order alone, and doesn't know "of".** "The father **of** Fionn" puts Fionn after the link, but means Fionn's father: "of" turns the direction round. That's the likely cause of the "who was the father of Cú Chulainn?" refusal (task 057).
- **Only one join** between two unconnected groups of pieces, and only plain (unqualified) links.
- **The subject is still the first variable by position** (`_subject`, shared).
- **A link phrase with only one possible meaning in the vocabulary can still give the wrong reading** if the schema has another link, with no phrase, that is meant. That's the 039 case: "associated with" sits on Monument's actor only, not on Figure's link to monuments. Task 048 (link direction) and vocabulary coverage are the fixes. This document grows as the walkthrough continues.
