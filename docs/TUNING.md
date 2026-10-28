# Observability & tuning — what the gate writes down, and why

Every automatic decision this system makes is recorded, and this document explains each record
field-by-field: what it means, why it exists, and what to do about what you see. The design
stance behind all of it: **a deterministic system can afford perfect bookkeeping** — the gate
has no LLM in it, so every decision has exact, replayable reasons, and we write them all down.

## The three logs (all in the state home, default `~/.claude/memory-graph/state/`)

| File | Written by | One line per |
|---|---|---|
| `injections.jsonl` | the recall extension, every prompt | gate decision (fired *or* silent) |
| `explicit-recalls.jsonl` | the recall extension, on PostToolUse | explicit memory tool call by the model |
| `errors.log` | the dispatcher | extension crash (traceback) |

View them with `claude-memory-graph log [file] [-n N] [-f]` (pretty-printed) or raw with `jq`.

## `injections.jsonl` — the decision log

A **fired** decision:

```json
{"fired": true, "top": 15.88, "rest": 0.0, "session": "abc123",
 "project": "claude-memory-graph", "terms": ["pyoxigraph", "quad", "rdflib", "store", "why"],
 "nodes": ["Use pyoxigraph over rdflib"], "ts": 1751737212}
```

A **silent** decision:

```json
{"fired": false, "top": 2.7, "rest": 1.1, "top_node": "Save after every mutation",
 "session": "abc123", "project": "claude-memory-graph",
 "terms": ["save", "mutation", "every"], "ts": 1751737290}
```

Field by field, and *why each is there*:

- **`fired`** — did anything reach the context window. Silences are logged as deliberately as
  injections: a retrieval system's false negatives are invisible unless you record the moments
  it chose to say nothing.
- **`top`** — the best-scoring memory's score. On a silent line this is the single most
  important number in the system: *how close was the gate to speaking?* `top=2.9` against
  `ABS_MIN=3.0` is a near-miss; `top=0.3` means no threshold change would have mattered.
- **`rest`** — the best score *outside* the injected group. The gate only fires when the group
  beats `rest` by `MARGIN`; logging both lets you replay that comparison exactly.
- **`top_node`** (silent lines only) — what the gate *would have* injected. Exists purely for
  the miss detector: when the model later recalls something explicitly, we can check whether it
  was the very node the gate had ranked first and declined.
- **`terms`** — the prompt's meaningful words after stopwording. Lets you reconstruct why
  something matched (or couldn't have): if the term you'd expect isn't in this list, the
  tokenizer dropped it and no downstream tuning will help.
- **`nodes`** (fired lines) — what was injected, for the fired-recently exclusion in the miss
  join and for eyeballing false positives.
- **`session`**, **`project`**, **`ts`** — the join keys. Misses are detected per-session
  within a time window; `project` also tells you whether the proximity prior was in play.

### Answered questions (`"kind": "answer"`)

When a prompt contains a question, even one buried in a long prompt, the gate runs it through
the query planner and injects the rows as **Memory answers**, so the model gets the answer as
memory without calling `memory_ask`. It only does this when the planner understood *all* of
the question. That means no word left unmatched, no "did you mean", no loose "linked somehow",
no loosened retry, and at least one row. Anything less stays a pointer. Each question is
answered once per session.

```json
{"kind": "answer", "fired": true, "q": "which decisions affect claude-memory-graph?",
 "understood": "Find Decisions that affect Project 'claude-memory-graph'.", "rows": 3}
```

| `/config` setting | `gate.json` key | Default | What it does |
|---|---|---|---|
| Answer questions from memory | `ANSWER_QUESTIONS` | `true` | turn auto-answering off |
| Questions answered per prompt | `ANSWER_MAX_QUESTIONS` | `2` | questions tried per prompt |
| Rows per answer | `ANSWER_MAX_ROWS` | `8` | rows injected per answer (the rest: "+N more — memory_ask for all") |
| Answer strictness | `ANSWER_COVERAGE` | `0.8` | how much of the question must ground |

The `/config` settings win over `gate.json`. The gate.json keys are for running the gate
without the plugin.

Cost: a prompt with no question pays nothing. A prompt with a question adds about 95 ms at 500
memories and 150 ms at 2,000. About half of that is loading the store, which the gate otherwise
never opens. The planner's record index is pickled (`planner-index.pickle`) and rebuilt only when
`graph.nq` changes.

### Known issue: per-prompt cost grows with the store (local graphs only)

This applies when the gate reads a graph on the machine itself: a local store, or a memory server
with **Memory lookups** set to `local copy`. With a server and the default `server` lookups, the
server runs the gate against its live store, keeps its indexes in memory, and rebuilds them in the
background after a write (docs/REMOTE.md). A warm prompt with a question takes about 35 ms there at
2,000 memories and 140 ms at 10,000, plus the round trip.

On the machine itself, every hook call is a fresh process that reads whole files, so the cost grows
roughly linearly with the number of memories. Measured warm, per prompt:

| | 2,000 memories | 10,000 memories | runs on |
|---|---|---|---|
| recall index (`gate-index.pickle`, unpickled whole) | 20 ms | 300 ms | every prompt |
| load the store (`graph.nq`, parsed whole) | 55 ms | 200 ms | prompts with a question |
| planner record index (`planner-index.pickle`) | 23 ms | 330 ms | prompts with a question |
| the SPARQL itself | 8 ms | 31 ms | prompts with a question |

Under a few thousand memories it isn't noticeable. Past that, the prompt hook slows down: use a
memory server, even one on the same machine, or the fix below.

**A possible fix, not adopted:** keep a read-only on-disk Oxigraph copy and a SQLite word →
record index beside `graph.nq`, rebuilt in the background when it changes (~0.7 s at 10,000).
Opening the copy takes ~33 ms at any size, and only the records sharing a word with the prompt
are read. It's deferred because it adds local state, and server lookups already cover the case.

To re-measure, time `planner.answer` and `gate_index` on a store of the size in question.

## `explicit-recalls.jsonl` — the model reaching for memory itself

```json
{"session": "abc123", "project": "claude-memory-graph", "tool": "memory_recall",
 "target": "Decision/Save after every mutation", "found": true, "ts": 1751737350}
```

- **`tool`** — which memory tool (`memory_recall`, `memory_query`, `memory_search`).
- **`target`** — what it asked for (`Model/name`), or `sparql` (truncated) for raw queries.
- **`found`** — did memory actually hold it. This one bit is what separates the two verdicts
  below: a *gate miss* requires the knowledge to have existed; "went looking, found nothing"
  indicts capture, not retrieval.

Why log *every* explicit call rather than only post-silence ones: the logger is dumb on purpose
(milliseconds, no decisions); all intelligence lives in the offline join, which can be re-run
with different windows/rules over the full history as the rules improve.

## The miss report — `claude-memory-graph misses`

The join (in [gate/misses.py](../claude_memory_graph/gate/misses.py)) walks both logs and
grades every explicit recall against the gate decisions that preceded it (same session, within
10 minutes). Output:

```
gate decisions: 41 · explicit recalls: 3 · misses: 1 · capture gaps: 1

MISS  session=abc123
  gate:   silent  top=2.7  top_node='Save after every mutation'  terms(save mutation every)
  model:  memory_recall -> Decision/Save after every mutation  [found]
  fix:    threshold miss — scored 2.7 vs ABS_MIN 3.0; consider lowering ABS_MIN

CAPTURE GAP  session=def456
  model looked for: memory_recall -> Decision/deploy pipeline choice  [nothing stored]
  fix:    not a gate problem — this knowledge was never captured. Worth a context note or distill run.
```

How each verdict is reached, and why the exclusions exist:

- **MISS** = gate silent → model explicitly recalled → **and it found something**. The model's
  own behaviour is the label: it demonstrated the memory was wanted *and present*. The attached
  silent decision carries the exact score, which drives the `fix` line:
  - **threshold miss** (score ≥ 70% of `ABS_MIN`): the gate nearly spoke; the knob is a touch
    high. Several of these clustered in a score band is an evidence-backed argument for a
    specific new `ABS_MIN`.
  - **vocabulary miss** (score below that): no sane threshold catches a 0.4 — the prompt and
    the node share almost no words. The fix is on the *capture* side: aliases or concept links
    on that node (DISTILL-CREATION.md §4), not gate tuning. Distinguishing these two cases is
    the whole reason scores are logged.
- **CAPTURE GAP** = same shape but the recall found nothing. Excluded from misses because the
  gate cannot inject what was never stored — but reported separately because it's the capture
  pipeline's miss list: things you demonstrably wanted from memory that distill never wrote.
- **Excluded: recall after a fired injection** — the model drilling deeper into something
  already injected is the gate *succeeding*. Counting it would punish good injections.
- **Excluded: different session or outside the window** — no causal story connects the silence
  to the recall.

### The asymmetry to keep in mind

False negatives label themselves (the explicit recall is an observable event); **false
positives don't** — a wrong injection just sits in context being ignored, producing no signal.
So this machinery applies downward pressure on thresholds automatically, while upward pressure
(against noise) stays human: skim `claude-memory-graph log` for INJECT lines that look irrelevant.
That division is acceptable because the gate is already biased hard toward silence — the
direction that needed data is the direction the data now flows.

### From self-labelling to self-tuning (not built yet)

Today: logs accumulate automatically, `misses` turns them into verdicts, a human edits
`gate.json`. The missing third step is a **tuner** that reads the labelled history and
*proposes* concrete values ("3 misses at 2.4–2.9 this week; ABS_MIN 2.3 would have caught all
three at an estimated +2 injections/week") — proposals first, auto-apply within bounds only
after they've earned trust. That's the `gate-tuner` task when we want it.

## The capture-side knobs (context-counter)

The same `~/.claude/memory-graph/gate.json` file tunes the capture loop's two triggers —
both enforced via **Stop blocks** ([ORCHESTRATION.md](ORCHESTRATION.md)), both observable in
session state (the pane's **State** tab; raw fields in the mod's state for `context-counter`):

- **`N_TURNS`** (default 3) — significant prompts the context log may fall behind before the
  Stop hook blocks with "write the context file now". The baseline is the count at the last
  *observed write* (`written_at` in state), so an ignored block re-fires every stop until the
  file's mtime moves. Raise it if the block fires during legitimately note-free stretches;
  remember trivial prompts ("thanks", "ok") never advance the counter.
- **`DIG_THRESHOLD`** (default 8) — file-inspection calls (Grep/Glob/Read + search-shaped
  Bash) in one turn that make it a *dig*, triggering the trace-entry ask
  ([tasks/dig-counter](tasks/dig-counter.md)). State fields `dig_turn`/`dig_count` show the
  live counter. If it catches routine multi-file edits (false digs), raise it; genuine
  investigations that stay under it argue for lowering — carefully, since Read-heavy work
  counts too.
- **`PRESSURE_TOKENS`** (default 140000) — context size (from transcript telemetry:
  `context_tokens` in core state) past which the Stop block escalates: ANY uncaptured
  exchange blocks, because compaction is close and PreCompact can only steer the summary,
  not trigger writes.
- **`LOG_ABS_MIN`** (default 3.0) — score floor for **session-log recall**
  ([tasks/session-context-recall](tasks/session-context-recall.md)): undistilled context
  entries injected per prompt. `kind: "log"` lines in `injections.jsonl` record its
  decisions; raise it if unvetted entries produce false positives that the graph's
  `ABS_MIN` wouldn't.
- **`NAME_WORD_SOFT_MAX` / `CONCEPT_WORD_SOFT_MAX`** (6 / 3, in `capture_rules.py`, not
  `gate.json`) — the naming ceiling. Over it, the write path *appends a `[naming]` warning* to
  its success message rather than refusing: a bad name is worth less than a lost node. Existing
  offenders are listed worst-first by `claude-memory-graph gaps`. Measured origin: on a real
  2010-node graph, Concept labels held a median of 1 word while Pattern/Decision/Preference
  names drifted to 11-12, because concepts were the only model given a concrete shape.
- **`DISTILL_AFTER_DAYS`** (default 2) — how long a context file may sit untouched (mtime)
  before auto-distill treats it as finished. A file with **no residue** is marked
  `distilled: true` and archived at the next server start, with no human in the loop; a
  file *with* residue is instead escalated once per session by a Stop block asking for
  `/memory-graph:distill`. Raise it if files you are still working across sessions get
  archived out from under you (nothing is lost — the entries are already in the graph, and
  the file moves to `~/.claude/context/archive/`); lower it if the backlog nags too late.
  Age, not "chat archived": there is no observable archive signal, and mtime is what keeps
  a live session's own log — rewritten every few turns — out of reach.
  Past the window a file with residue is **split** rather than pinned: the whole original is
  archived and the active file is rewritten with only the entries that still need a model.
  Measured on a real backlog: 35 of 44 files split, active log 2156 kB → 816 kB, every kept
  entry a verbatim subset of its original.
- **`REVIEW_EVERY_DAYS`** (default 7) — period between graph self-review asks
  (`graph-review`, off by default: turn on **Periodic graph review** in `/config`).
  On the first Stop of a session past the period, the mechanical detectors in `gaps.py` run and
  their headline numbers become a Stop block asking for `/memory-graph:reflect`. A clean graph
  is silent and resets the clock without spending a turn. The ask is capped at "fix the worst
  handful" on purpose — it fires again next period, and a maintenance session that never ends
  is worse than a slightly untidy graph.
- **`GAP_MIN`** (default 6.0) — the IDF mass (name hits ×3) two *unlinked* nodes must
  share before `claude-memory-graph gaps` suggests connecting them. Raise if the reflect
  skill keeps dismissing suggestions as coincidence; lower if a visualisation shows
  obviously-related nodes the report missed.

The capture loop also writes its own decision log — `capture.jsonl` (`kind`:
`block`/`write`/`stamp` fields per event) — which `claude-memory-graph pulse` reads to
report enforcement activity alongside retrieval.

Whether the model *complied* with a block is only observable for the write cadence (mtime);
trace compliance is not, which is why the dig ask fires once per dig turn and the write
cadence is the backstop.

## Commands, in one place

```sh
claude-memory-graph log            # last 20 gate decisions, pretty
claude-memory-graph log -f         # follow live while you work
claude-memory-graph log explicit-recalls.jsonl
claude-memory-graph misses          # the join: misses + capture gaps
cat ~/.claude/memory-graph/state/errors.log  # extension crashes
```
