# Task: prompt-gated ambient recall (deterministic injection)

Status: **planned** · Owner: Stuart · Created: 2026-07-02

## Goal

Make recall feel like real memory — active *in tandem* with every prompt —
**without** spending Claude tokens to decide. A `UserPromptSubmit` hook parses
the prompt, scores it against the graph in pure Python (no LLM in the loop), and
injects the top matches **only if** they clear a confidence bar. Silent by
default.

## Why this beats the `memory_recall` tool

When the model fires `memory_recall`, it costs a tool round-trip *every time it
decides to*, and it over-fires to be safe. It also misses the highest-value
case: the correction the model is about to confidently repeat because nothing in
the prompt flags "you got this wrong before" — it never thinks to recall for its
own blind spots.

A deterministic gate flips the economics:

- **Zero model tokens on the prompts where it stays silent** (should be most).
- Fires for blind spots, because the trigger is the *prompt text*, not the
  model's self-awareness.
- A small, precise injection only when confident — the opposite of maxing usage.

## Design

`UserPromptSubmit` hook → `claude_memory_graph.gate`:

1. Read the prompt from the hook's stdin JSON.
2. Tokenise → drop stopwords → keep terms length > 2.
3. Score every non-invalidated resource's `name` + `description` against the
   prompt terms (see scoring).
4. If the top score clears an absolute floor **and** beats the runner-up by a
   margin → print the top 1–2 memory bodies to stdout (Claude Code injects hook
   stdout as context). Otherwise print nothing.
5. Always exit 0.

No LLM call anywhere in the gate. It's a subprocess; it only spends tokens when
it *chooses to speak*.

## Scoring

- **IDF-weighted term overlap.** Build document frequency over all descriptions;
  `score = Σ idf(term)` over terms shared by prompt and doc. Generic words
  ("file", "run", "fix") get near-zero weight; rare project terms ("dc03",
  "waspacing", "sops") carry the signal.
- **Name/slug boost.** A prompt term matching a resource `name` scores ×3 — an
  exact entity mention is a strong signal.
- **Margin threshold, not just absolute.** Require `top >= ABS_MIN` AND
  `top >= MARGIN * second`. If everything is equally weakly related, that's
  noise → stay silent.

### The one tuning rule

Bias hard toward **silence**. The errors are asymmetric:

- **False negative** (miss a memory) = back to status quo. Cheap.
- **False positive** (inject loosely-related memory) = wastes tokens *and* feeds
  stale/irrelevant context the model may treat as instruction. Expensive.

Tune for **high precision, low recall**. Start `ABS_MIN` conservative and let it
miss — misses cost nothing.

## Build order

1. `gate.py` — corpus loader + IDF scorer + stdin `main()`. Keyword only.
2. One test (below). Tune `ABS_MIN` / `MARGIN` against a handful of real prompts.
3. Wire the hook (`hooks/user-prompt-submit.sh` + `hooks.json` entry).
4. **Only if** keyword measurably misses semantically-related-but-lexically-
   different prompts: add a *local* embedding model (runs on your machine, still
   zero Claude tokens). Not before — measure first.

## Skeleton

`claude_memory_graph/gate.py`:

```python
import json, math, re, sys
from pathlib import Path
from .store import MemoryStore
from .namespaces import SPARQL_PREFIXES, GRAPH_RESOURCE_BASE

_STOP = {"the","a","an","and","or","to","of","in","on","for","with","is","are",
         "this","that","it","be","can","could","would","how","what","when","i",
         "you","we","do","does","make","get","set","use"}
_WORD = re.compile(r"[a-z0-9]+")
ABS_MIN = 3.0      # tune: absolute score floor
MARGIN  = 1.5      # tune: top must beat 2nd by this factor
TOP_N   = 2

def _terms(text):
    return [w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP]

def _corpus(store):
    # (graph_id, name, description) per live resource
    rows = store.query(SPARQL_PREFIXES + f'''
        SELECT ?g ?name ?desc WHERE {{
          GRAPH ?g {{
            ?n mem:description ?desc .
            OPTIONAL {{ ?n mem:name ?name }}
            FILTER NOT EXISTS {{ ?n mem:invalidated ?x }}
          }}
          FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}"))
        }}''')
    docs = []
    for r in rows:
        name = r["name"].value if r["name"] else ""
        desc = r["desc"].value if r["desc"] else ""
        docs.append({
            "gid": r["g"].value.removeprefix(GRAPH_RESOURCE_BASE),
            "name": name,
            "desc": desc,
            "name_terms": set(_terms(name)),
            "terms": set(_terms(f"{name} {desc}")),
        })
    return docs

def _idf(docs):
    n = len(docs) or 1
    df = {}
    for d in docs:
        for t in d["terms"]:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1 + n / c) for t, c in df.items()}

def _score(q_terms, d, idf):
    s = 0.0
    for t in q_terms:
        if t in d["terms"]:
            w = idf.get(t, 0.0)
            s += w * (3.0 if t in d["name_terms"] else 1.0)
    return s

def main():
    raw = sys.stdin.read()
    prompt = (json.loads(raw).get("prompt") if raw.strip().startswith("{") else raw) or ""
    q = set(_terms(prompt))
    if not q:
        return
    store = MemoryStore.open_or_create(Path.home() / ".claude/memory-graph/store")
    docs = _corpus(store)
    if not docs:
        return
    idf = _idf(docs)
    ranked = sorted(((_score(q, d, idf), d) for d in docs), key=lambda x: x[0], reverse=True)
    top = ranked[0][0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if top < ABS_MIN or top < MARGIN * (second or 0.0001):
        return  # not confident -> silent, zero tokens added
    print("Relevant memory (auto-recalled, may be stale — verify before acting):")
    for sc, d in ranked[:TOP_N]:
        if sc >= ABS_MIN:
            print(f"- {d['name'] or d['gid']}: {d['desc']}")

if __name__ == "__main__":
    main()
```
<!-- ponytail: loads the whole store per prompt. Fine at current graph size;
     if latency bites, cache an idf+corpus JSON sidecar rebuilt on each mutation
     (store already saves on every mutation) and read that here instead. -->

`hooks/user-prompt-submit.sh`:

```sh
#!/bin/sh
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
exec "$PLUGIN_ROOT/.venv/bin/python" -m claude_memory_graph.gate
```

`hooks/hooks.json` — add alongside `SessionStart`:

```json
"UserPromptSubmit": [
  { "hooks": [
      { "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}\"/hooks/user-prompt-submit.sh" }
  ] }
]
```

## Test

`tests/test_gate.py` — the stopword/IDF logic is the part that fails silently if
it drifts, so pin the injection decision:

```python
from claude_memory_graph import gate

def test_generic_prompt_stays_silent():
    idf = {"dc03": 4.0, "harness": 3.0}
    docs = [{"name":"charcoal","desc":"dc03 harness",
             "name_terms":{"charcoal"},"terms":{"dc03","harness"}}]
    assert gate._score(set(gate._terms("thanks, run the tests")), docs[0], idf) == 0.0

def test_specific_prompt_scores():
    idf = {"dc03": 4.0, "harness": 3.0}
    docs = [{"name":"charcoal","desc":"dc03 harness",
             "name_terms":{"charcoal"},"terms":{"dc03","harness"}}]
    assert gate._score(set(gate._terms("fix the dc03 harness")), docs[0], idf) >= gate.ABS_MIN
```

## Open questions

- **Concepts too?** Skeleton indexes resources only. Fold in Concept nodes
  (shared multi-hop hubs) if resource descriptions alone under-recall.
- **Dedup vs SessionStart.** `MEMORY.md` index is already injected at session
  start; the gate injects full *bodies* on match, so additive — but watch for
  the same fact arriving twice in one session.
- **Per-turn cache cost.** Injecting varying content each turn busts the prompt
  cache *for that turn*. Rare injection = rare cost; acceptable, but a reason to
  keep the gate quiet.
- **Embedding upgrade path.** Local sentence-transformer for semantic match if
  keyword misses — zero Claude tokens, some latency. Deferred until measured.
