# Observability & tuning — what the gate writes down, and why

Every automatic decision this system makes is recorded, and this document explains each record
field-by-field: what it means, why it exists, and what to do about what you see. The design
stance behind all of it: **a deterministic system can afford perfect bookkeeping** — the gate
has no LLM in it, so every decision has exact, replayable reasons, and we write them all down.

## The three logs (all in the hook-kit home, default `~/.claude/hook-kit/`)

| File | Written by | One line per |
|---|---|---|
| `injections.jsonl` | the recall extension, every prompt | gate decision (fired *or* silent) |
| `explicit-recalls.jsonl` | the recall extension, on PostToolUse | explicit memory tool call by the model |
| `errors.log` | the dispatcher | extension crash (traceback) |

View them with `claude-hooks log [file] [-n N] [-f]` (pretty-printed) or raw with `jq`.

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
(against noise) stays human: skim `claude-hooks log` for INJECT lines that look irrelevant.
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
session state (`claude-hooks state <session_id>`, extension `context-counter`):

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

Whether the model *complied* with a block is only observable for the write cadence (mtime);
trace compliance is not, which is why the dig ask fires once per dig turn and the write
cadence is the backstop.

## Commands, in one place

```sh
claude-hooks log                    # last 20 gate decisions, pretty
claude-hooks log -f                 # follow live while you work
claude-hooks log explicit-recalls.jsonl
claude-hooks state <session_id>     # core counters + extension state
claude-memory-graph misses          # the join: misses + capture gaps
cat ~/.claude/hook-kit/errors.log   # extension crashes
```
