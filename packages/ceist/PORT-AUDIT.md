# Ceist runtime: port audit and ground.py split

Read-only audit, 2026-11-08, of `packages/ceist/src/ceist/` before the TypeScript port of the question-time runtime.
I grepped callers in `packages/ceist` (src, tests, bench), `claude_memory_graph/` and `tests/` at the repo root, and `starches-demo/ask/ask.py`.
(`<foundation>/src` does not exist. The memory graph's callers are in `claude_memory_graph/planner.py` and `claude_memory_graph/gate/semantic.py`.)

**Assumption behind every "don't port" below:** the TypeScript runtime serves **Arches over Rós Madair only**. The memory graph's planner stays in Python and keeps using Python Ceist. `ArchesVocabulary` sets `any_of`, `group_by` and `name_match` (arches.py:153-155). It never sets `free_text` or `partial_names`; only `MemoryVocabulary` does (planner.py:83,86).

Tags: `delete` `stdlib` `yagni` `shrink` `no-port`. **Safe** means no change in behaviour. **Behaviour** means a refusal, note or suggestion would change.

## 1. Ranked findings (biggest cut first)

| # | Tag | What | Replacement | Where | Callers checked | Effect |
|---|---|---|---|---|---|---|
| 1 | no-port | Building the Arches vocabulary at runtime: Alizarin graph registration, SKOS and RDM reading, bundle absorption, `_load_groups`, CRM targets, `values()` and `date_fields()` | Python writes a **frozen vocabulary JSON** at build time. It holds relations, values, date fields, groups, type words, implied types, field phrases, fields, place fields, geometry fields, entities and names, concept labels, `concept_of`, the node index (nodeid, nodegroup, tile line), per-record geometry, and the link targets `group_values` needs. TS only reads it. | arches.py:62-599 (~560 lines) | ask.py:162 builds the vocabulary per process from graphs + bundle + resources + RDM | Safe if the dump is faithful. Prove it with a Python `FrozenVocabulary` that passes the same tests and benches. |
| 2 | no-port | crm.py: all of it once (1) holds. Only `root_class`, `link_ranges`, `clash` and `is_a` are reached at runtime, and only from vocabulary load (arches.py:170,396,509,585). The rest is build-only: `crm_roles` (pipeline), `chains` and `ontology_entries` (bundle, ontology_vocab, questions, cost). | Keep it in Python tools | crm.py (221 lines) | crm.py:7 imports `bundle` (a build tool) at module load, so the runtime depends on the tools | Safe |
| 3 | no-port | slicing.py: a build tool that writes files (`ceist vocab slice`) | Stays in Python | slicing.py (189 lines) | Only caller is cli.py:118 | Safe |
| 4 | no-port | Two copies of the Rós Madair runner: `rosmadair.ask` returns text, `ask.py _answer` returns structure, and they have drifted (ask.py also catches `ValueError` and always uses `select_ids`) | Port one runner that returns structure; text output is a view over it | rosmadair.py:469-565; ask.py:56-107 | Tests use `compile_plan`/`read_back`, not `ask` | Safe for TS (port the ask.py version) |
| 5 | no-port | The free-text branch: text-filter pass, `contains`/`contains_negated`/`contains_pos`, the `loose` drop, `Relaxation` with Mention/Contains relaxations, `partial_names`, `hint_words`, `extra["recallable"]` | Nothing. Arches never sets these, and Rós Madair refuses Contains/Mention anyway (rosmadair.py:160). Keep the `elif g.uncovered: g.refuse = ""` arm (ground.py:595-597). | ground.py:492,552-561,588-594; plan.py:233,284-298; narrate.py:74-77 | planner.py:430,474,486-492 (Python only) | Safe for an Arches-only TS; the Python code stays |
| 6 | no-port | config.py's TOML loader, the wordllama encoder path, and `PLANNED_CHOOSERS` | In TS the config is a plain object `{layers, roots, direction, low, gap, clarifyTop, clarifyMin}`. In Python, delete `PLANNED_CHOOSERS` ("designed for; not built yet") | config.py:43,89-91,122-136 | `PLANNED_CHOOSERS` is only read at config.py:89 | Deleting it in Python changes behaviour: "local-llm" then gets the generic "unknown chooser" message **Done (055):** `PLANNED_CHOOSERS` deleted; "local-llm" now gets "unknown chooser", as no LLM runs at question time. |
| 7 | delete | `matching` `context` parameter: passed in, never read | Drop it from `decide` and `resolve` | matching.py:115,154,181; passed at ground.py:662,691,725 and evaluate.py:117 | The fake in tests/test_planner.py:228 takes it as a keyword with a default | Safe **Done (055).** |
| 8 | no-port | `simplemma` rooter (`_rooter`) | `_light_root` only. HER configs set `roots = true` (bench/her/ceist.toml), and `simplemma` is an optional extra (pyproject `roots`) | matching.py:89-96 | — | Behaviour change wherever `simplemma` is installed. Drop it in Python too so both runtimes agree, then re-run her_plans. **Done (055):** simplemma dropped; `text.PAST` read backwards is the irregulars table. |
| 9 | no-port (for now) | `Vectors` layer | Port the `Exact` layer and `Chain` first. STATUS §4 found bge "disproven as a question-time fix"; the demo uses it only for "did you mean" (ask.py:163) | matching.py:142-171, onnx.py, vectors.py | ask.py:164 | Behaviour change: the demo's suggestions change |
| 10 | delete | `rosmadair.to_query`, a wrapper used by tests only; `DEFAULT_LIMIT`, which nothing reads | Tests call `compile_plan(...).query` | rosmadair.py:71,260-266 | test_arches.py:49,59,68; test_controlled_lists.py:207,329 | Safe (tests need a one-line edit) |
| 11 | delete | `plan.describe` | Nothing | plan.py:632-633 | No callers (the `describe` in cost.py is `arches_describe`'s) | Safe |
| 12 | no-port | `ArchesVocabulary` knobs used only by tests or other backends: `relation_forms`, `date_forms`, `extra_type_words`, `skipped_qualified`, `model_by_slug`, `is_reference`, `reference_items`, `descendants` | The bundle carries the phrasings. The rest serve Arches Search and Alizarin, not Rós Madair | arches.py:158-161,208-211,462-472,487-488,546-558,575-577 | test_arches.py:30, test_questions.py:34 (knobs); arches_search, alizarin and slicing (lookups) | Safe |
| 13 | yagni | `Vocabulary` is a Protocol whose optional members are probed with `getattr` (11 sites) | A TS interface with every member required; the test fake implements all of them | vocabulary.py:257-260; ground.py:321,324,384,405,416,490,492,553,571; plan.py:289,310,353 | — | Safe |
| 14 | shrink | `ground._targets` is a private helper imported across modules | Make it a `Relation.targets(source=None)` method in vocabulary.py | ground.py:908-912 | rosmadair.py:242 | Safe |
| 15 | shrink | The same span tests written out repeatedly: overlap (4×), containment (3×), "word indices inside this span" (5×) | `overlaps(span, spans)` and `words_in(start, end)` | overlap: ground.py:222,341,407, dates.py:334. Inside: ground.py:220,569,1052. Words-in: ground.py:298,389,397,629,1060 | — | Safe **Done** (040; dates.py in 055, on `text.overlaps`). |
| 16 | shrink | Word tuples read by position: `w[0]`, `w[3]`, `words[i][1]` | A `Word` NamedTuple (`i, start, end, text`) in Python and an interface in TS | All over ground.py | — | Safe |
| 17 | shrink | The "first word opens a question" test is written twice | `_opens(word)` | ground.py:210-211, 305 | — | Safe |
| 18 | shrink | `vocab.type_words()` called twice; flags read again and again (`any_of` 2×, `free_text` 2×) | Read each once, onto the scan state | ground.py:352,445,490,544,553,571 | — | Safe |
| 19 | shrink | `by_form` reused for date forms, shadowing the group index | Rename it `date_forms` | ground.py:325 vs 424 | — | Safe |
| 20 | shrink | Two identical "`taken.remove(span)`; continue" arms in the relations loop | One `if` that tests both conditions | ground.py:371-377 | — | Safe |
| 21 | shrink | `_match_leftovers`: the suggestion and `unplaced` blocks repeated (3× and 2×); `named = {n.type for n in g.vars()}` written twice | `_offer(phrase, res)` and `_unplaced(phrase, slot, model, options)` | ground.py:668-677,697-708,731-732; 711,776 | `unplaced` feeds pipeline.py:1301 (the learn log) | Safe **Done (055):** `_offer` and `_unplaced`; the two `named` lines are in different passes and stay. |
| 22 | delete | Dead write: `consumed.add(i)` after coverage, which nothing reads afterwards | Nothing | ground.py:577 | — | Safe |
| 23 | shrink | `narrate._plural` repeats the rule in `text.plurals` | `text.plural(word)`; `plurals(w) = {low, low+"s", plural(low)}`. Checked identical on y, s, x, ch, sh and length 2 | narrate.py:10-15; text.py:36-45 | arches.py:281, questions.py:375, pipeline.py:46 | Safe **Done (055):** `text.plural()`; questions.py's `_plural` uses it too. |
| 24 | shrink | narrate imports `MILE_KM` from ground | Put unit constants beside the dates code, or in a `units` constant | narrate.py:5 | — | Safe |
| 25 | yagni | `Grounding.anchor` duplicates `anchors[0]`; `Grounding.about` is read only inside ground | `anchor` becomes a getter; `about` moves to the scan state | ground.py:185,196,543 | planner.py:341-360 reads `g.anchor` (fine as a property) | Safe **Done (055).** |
| 26 | no-port | `Node.var` (`?v0`…) appears only in notes; the memory graph names its own SPARQL variables (planner.py:311) | Drop it; the notes say "typed variable : T" | ground.py:69,450,1000 | No test asserts on it | Behaviour change (note text only) **Done (055):** notes say "typed variable : T" and "implicit T variable". |
| 27 | stdlib | `dates._iso` wraps `d.isoformat()` | Call `.isoformat()` directly | dates.py:40 | — | Safe |
| 28 | shrink | rosmadair imports Alizarin's private helpers `_links` and `_atoms` | Move them to a small tile-value helper; TS needs them anyway | rosmadair.py:241,346,389 | — | Safe |
| 29 | yagni (later) | `LinkTo.qualifier` shim plus `as_tile` for a qualified link walked backwards. Rós Madair refuses it (rosmadair.py:127); only Python's Alizarin backend reads it | TS could refuse at plan time instead | plan.py:61,137,481-483 | alizarin.py:180,269 | Behaviour change (refusal text). Low priority. |

**Over-long functions** (lines):
- `ground()`: 330 (section 2).
- `plan._interpret`: 105. A linear chain of refusals; port it as it is.
- `rosmadair.ask`: 97 (finding 4).
- `_match_leftovers`: 90 (finding 21; three sub-passes).
- `plan._detail`: 66.
- `arches._load_groups`: 57 (finding 1).
- `_assign_edges`: 52.
- `plan._partial`: 50.

**Out of scope** (pass these to a normal review):
- dates.py:243-244 bounds words with `[a-z0-9]`, but ground and text use `ALNUM`.
- `ArchesVocabulary.relations()` and `values()` are rebuilt on every question (plan.py:254, rosmadair.py:244, ground.py:331,344). Finding 1 removes this cost.
- `_attach_*` in plan.py change the Grounding (`uncovered`, `notes`); this is why `_partial` copies it at plan.py:400.

**Net:** Python can safely lose about 60 lines (findings 7, 10, 11, 14-25, 27, 28). The TS port can skip about 1,350 of the ~4,300 runtime lines: arches loading (~560), crm (221), slicing (189), config (~120), the text runner (97) and the free-text branches (~80). No dependencies are removed in Python; TS needs no wordllama or simplemma.

## 2. Splitting ground()

### The state threaded through `ground()` today

| Name | Kind | Written by | Read by |
|---|---|---|---|
| `raw`, `words`, `terms`, `names` | Fixed once at setup | setup (282-303) | Every pass |
| `consumed: set[int]` | Word indices | Nearly every pass. `_fill_groups` **removes** indices (ground.py:804) | anchors, leftovers, text filter, coverage |
| `taken: list[span]` | Character spans claimed | shape, relations, tile phrases, values, field phrases, near, `dates.find` | every `_phrase_spans` call, near, dates |
| `relations`, `sharing`, `types_of` | Relation by name (narrowed by `said_as`); a form's other meanings | relations (379-382); `_fit_relations` (903) | anchors (`expected`), fit, match, wire |
| `seen`, `add_var` | Type to its variable node | words pass, implied type, `_imply_model`, `_assign_edges` (1001) | wire, subject |
| `negs` | Negator positions | words pass | scope negations |
| `held`, `contains_pos` | Words kept out of the text filter; where the text word is | `_fill_groups`; text filter | text filter; scope negations |
| `g: Grounding` | The output | Every pass | `plan.py`, callers |

**A shared state object is warranted.** Helpers already take 5-8 positional arguments (`_field_phrases` takes 8; `_match_leftovers` 7), and the closures `parts_of`, `consume_span` and `add_var` capture locals. One plain dataclass, not a class hierarchy:

```python
@dataclass
class Scan:                     # TS: interface Scan + plain functions
    vocab: Vocabulary; text: str; raw: str; words: list[Word]; terms: set[str]; names: list[Span]
    g: Grounding
    flags: Flags                # any_of, group_by, name_match, free_text, partial: read once
    consumed: set[int] = field(default_factory=set)
    taken: list[Span] = field(default_factory=list)
    relations: dict[str, Relation] = ...; sharing: dict[str, list[str]] = ...
    seen: dict[str, Node] = ...; negs: list[tuple[int, str]] = ...
    held: set[int] = ...; contains_pos: float | None = None; about: bool = False
    def parts_of(self, w) -> set[str]: ...
    def consume_span(self, start, end) -> float: ...
    def add_var(self, t, pos, why) -> Node: ...
    def words_in(self, start, end) -> list[int]: ...
```

Each pass is a module function `def _relations(s: Scan) -> None`. There is no pass registry and no base class: `ground()` simply calls the passes in order.

### The passes, in order

| # | Pass (new name) | Today | Reads | Writes | Helpers |
|---|---|---|---|---|---|
| 0 | `_scan` (set-up) | 282-303 | text, vocab | raw, words, terms, names | `_record_spans` |
| 1 | `_shape` | 305-322 | words, text | g.wh, g.count, about, g.name; consumed {0,1,about}; taken (imperative, name match) | `_name_match`, `is_question`/`_opens` |
| 2 | `_relations` | 324-385 | taken, consumed, names, type words, the spans of longer group/value phrases (`longer`) | g.edges, relations, sharing, taken, consumed; then g.group/g.group_order | `_phrase_spans`, `just_a_type`, `_group_by`, `_edge` |
| 3 | `_tile_phrases` | 387-393 | the group form index, taken, consumed | g.groups, taken, consumed | `_phrase_spans` |
| 4 | `_values` | 395-400 | the value index, taken | g.values, taken, consumed | `_phrase_spans` |
| 5 | `_field_phrases` | 402, 621-640 | g.values, a **copy** of taken | value candidates narrowed, taken, consumed | `_phrase_spans` |
| 6 | `_near` | 404-413 | taken, names | g.near, taken, consumed | — |
| 7 | `_dates` | 415-442 | taken, `today` | g.dates, taken, consumed | `dates.find`, `_phrase_spans` |
| 8 | `_words` | 444-486 | consumed, g.dates | g.nodes (vars), seen, negs, g.recent, consumed | `add_var` |
| 9 | `_anchors` | 488-543 | consumed, edges, sharing, near | g.anchors, g.nodes, consumed, near's record | `_either_records` |
| 10 | `_fit_relations` | 544 | nodes, edges, relations, sharing | edges, relations, g.refuse | `_fit_relations`, `_wrong_end`, `Relation.targets` |
| 11 | `_imply_model` | 545-546 | values, groups, raw | g.nodes, g.suggestions | `_imply_model` |
| 12 | `_match_leftovers` | 548-549 | consumed, nodes, edges, dates, groups | edges, groups, the fields of each date, consumed, suggestions, unplaced | `_leftover_runs`, `matching.Item` |
| 13 | `_fill_groups` | 550, 770-810 | groups, values, dates, edges, nodes | groups, values, dates; consumed (also **un**-consumes); held | — |
| 14 | `_text_filter` | 552-561 | consumed, held | g.contains, contains_pos, consumed | (Python only; not ported) |
| 15 | `_coverage` | 563-565 | consumed, terms | g.coverage, g.uncovered | — |
| 16 | `_or` | 567-577 | words, consumed, names, values | g.values[].either, g.refuse | `_either_values` |
| 17 | `_wire` | 579-601 | edges, nodes, seen, words | edge ends, implicit vars, g.refuse, g.field_of, g.loose | `_assign_edges`, `_check_anchors`, `_imply_join` |
| 18 | `_subject` and `_scope_negations` | 603-609 | wh, implied types, seen, negs, contains_pos | g.subject, `.negated` on items, g.negation_unplaced | `_scope_negations` |

`ground()` becomes:

```python
def ground(vocab, text, today=None, matcher=None) -> Grounding:
    s = _scan(vocab, text)
    for p in (_shape, _relations, _tile_phrases, _values, _field_phrases, _near):
        p(s)
    _dates(s, today)
    for p in (_words, _anchors, _fit_relations, _imply_model):
        p(s)
    if matcher is not None and not s.about:
        _match_leftovers(s, matcher)
    for p in (_fill_groups, _text_filter, _coverage):
        p(s)
    if _or(s) or _wire(s):          # each returns True when it refused
        return s.g
    _subject(s)
    _scope_negations(s)
    return s.g
```

Keep the internals of `_wire` in today's exact order. `_assign_edges` sets "cannot resolve", lines 586-597 may clear it, and the variable cap comes after that.

### Order constraints between passes, and why

Two mechanisms decide which pass claims a word:
- Within one pass, the longest phrase wins (`_phrase_spans`).
- Between passes, whatever `taken` and `consumed` already hold blocks later passes.

| Constraint | Why | Evidence |
|---|---|---|
| shape → everything | "Find" must not ground as a value. "how many" must not be read as a group phrase. "about X" turns relations off. | ground.py:310 (taken); 390 (`consumed & at`); 370 (`[] if g.about`) |
| `longer` is computed before relations | A longer group or value phrase beats a relation phrase inside it ("bronze age" is not the relation 'age'). It is computed against the shape spans only. | 336-341, passed to 370 |
| relations → tile phrases → values | Priority order is record name > longer group/value phrase > relation > tile phrase > value. `names` is passed to each pass. | 370, 388, 396 |
| `_group_by` straight after relations, before anchors | It removes the "by county" edge, and the anchor cap counts edges (`len(anchors) >= len(edges) + near`) | 384-385, 532 |
| values → field phrases | A field phrase holds the value that follows it, so it needs `g.values`. It matches against a copy of `taken` and claims its span only when a value fits. | 630, 638 |
| near → dates | "within 2000 miles of" would otherwise read "2000" as a year | 405-413, dates.py `_POINT` |
| relations → dates | A relation phrase ("built by") beats the date-field word inside it ("built"): date-field picking uses `taken` | 428 |
| dates → words | DATE_WORDS are consumed only once a date has grounded | 481 |
| words → anchors | Anchors rank only the leftover words. A type noun or negator must already be consumed. | 496 |
| relations and near → anchors | `expected` (the types that fit the role) comes from the edges, and the cap from edges + near. Near takes the first anchor after it. | 493-494, 532-542 |
| anchors → fit relations | Fitting needs both ends named. When no fit exists it may refuse ("Belfast is a Monument") or set the edge aside. | 871, 889-899 |
| fit → imply model → matcher | The matcher's "between two nodes" sub-pass runs only `if not g.edges`, after fitting has removed edges. The tile sub-pass needs the var types, including ones `_imply_model` adds. | 680, 711 |
| matcher → fill groups | The matcher adds GroupGrounds that fill groups then completes or drops | 728, 778 |
| fill groups → text filter → coverage | fill groups un-consumes the words of an empty group and returns `held`, which blocks the text filter. Coverage needs the final `consumed`. | 804, 556, 563 |
| values and `_either_records` → `_or` | `_or` needs value word indices; an "or" already used between two records is consumed | 569, 1072 |
| `MAX_EDGES` → assign → check → relax → `MAX_VARS` → imply join | Assigning ends can add implicit vars, so the var cap comes after it. A join is implied only once the ends are wired. | 580-601 |
| subject → scope negations | A negator never targets the subject itself, and it scopes over wired edges | 830 |

### Module layout (the same shape in Python and TS)

| Python `ceist/ground/` | TS `ground/` | Contents | ~Lines |
|---|---|---|---|
| `__init__.py` | `index.ts` | `ground()`, `is_question`; re-exports `WORD_RE`, `NEG` and `DATE_WORDS` for plan, and the types | 40 |
| `model.py` | `model.ts` | Node, Edge, ValueMatch, DateGround, NearGround, GroupGround, NameGround, Grounding, `_edge` | 150 |
| `scan.py` | `scan.ts` | Word sets and caps, regexes, `Word`, `Scan`, `_scan`, `_phrase_spans`, `_record_spans`, `_leftover_runs`, `overlaps`/`words_in` | 200 |
| `phrases.py` | `phrases.ts` | Passes 1-7: shape, name match, relations, group_by, tile phrases, values, field phrases, near, dates | 260 |
| `nodes.py` | `nodes.ts` | Passes 8-11: words, implied type, anchors, either records, fit relations, wrong end, imply model | 220 |
| `leftovers.py` | `leftovers.ts` | Passes 12-15: match leftovers, fill groups, text filter (Python only), coverage | 170 |
| `wire.py` | `wire.ts` | Passes 16-18: or/either values, caps, assign edges, check anchors, imply join, subject, scope negations | 210 |

The order of work:
1. Refactor in the same file first (add `Scan`, extract the passes; findings 14-22).
2. Prove it identical (section 3).
3. Split the file mechanically.

The import paths `ceist.ground.{ground, Grounding, Node, Edge, NEG, WORD_RE, DATE_WORDS}` stay as they are (plan.py:44; planner.py:22). `MILE_KM` moves out (finding 24) and `_targets` moves out (finding 14).

### Fit with the earlier folder regrouping

The earlier proposal kept core flat, with `matching/`, `sources/`, `backends/` and `tools/` subpackages.
- **`ground/` fits as the one core subpackage.** It is a single unit with one entry point, and nothing outside it reaches in once finding 14 is done. If "core flat" is strict, keep `ground.py` as one file with the passes as functions (~1,000 lines); the readability gain comes from the passes, not from the files.
- **crm.py has to be split by the regrouping anyway.** Its runtime class hierarchy (`PARENTS`, `is_a`, `clash`, `root_class`, `link_ranges`) goes to `sources/`; `crm_roles`, `chains` and `ontology_entries` go to `tools/`. Today crm.py:7 makes the source depend on `tools` (bundle).
- **rosmadair.py's import of `alizarin._links` and `_atoms` is a backend reaching into a backend** (finding 28).

## 3. What pins ground's behaviour

| Check | Pins | Needs | Exact? |
|---|---|---|---|
| tests/test_ceist.py (53 tests) | ground, interpret, narrate, readback and dates on a Toy vocabulary, including the free-text and partial-name paths | nothing external | yes, on asserted fields |
| tests/test_groups.py (8) | tile phrases, fill groups | — | yes |
| tests/test_arches.py (47) | Arches vocabulary, compile and read-back for Rós Madair, Alizarin | alizarin; some tests need `ros_madair` and a snapshot | yes |
| tests/test_controlled_lists.py (14), test_layers.py (8), test_ontology.py (19), test_questions.py (7), test_pipeline.py (28) | values and lists, bundle layers, the ontology layer through ground, `planner_run` | alizarin | yes |
| tests/test_learn.py (12) | `g.unplaced` shape | — | yes |
| tests/test_matching.py (5) | Chain, Exact | — | yes |
| `<repo>/tests/test_planner.py` | the memory-graph vocabulary: `loose`, `free_text`, `partial` | repo venv | yes |
| bench/her_plans.py | 125 HER questions → narrated plan or "refused" (plans-2.0.json) | HER package + bundle (external paths) | yes |
| bench/demo/run_bank.py | the demo bank through ask.py `answer`; exits 1 on a regression | starches-demo, `ros_madair`, snapshot | right/wrong only |
| bench/ontology/run.py | scores per set over lingo, catalina and HER | local checkouts | counts only |

**Gap:** nothing pins `notes`, `suggestions`, `unplaced`, `coverage` or `uncovered`, or which word grounded as what, across all the bench questions.

**The fix:** one golden-dump script (~40 lines). For every question in bench/demo, her/cases.json and the generated set, under the demo and HER vocabularies, it writes the Grounding to JSON, with entities given as ids, plus the narrated plan or the refusal. Run it before the split and diff it after. The same file then serves as the TS conformance fixture, alongside `ceist-web/spike/fixtures.json`, which already pins the compiled IR and result hashes.
