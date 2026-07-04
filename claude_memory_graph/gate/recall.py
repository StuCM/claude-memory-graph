"""Check: ambient memory recall — inject relevant memories, unasked.

The idea in one line: if your prompt contains rare words that also appear
in a stored memory's name or text, that memory is probably relevant —
inject it; otherwise say nothing.

Scoring (no LLM anywhere):
- every memory becomes a bag of words from its name + literal properties
- each shared word scores its IDF weight (rare words count, common words
  barely count), x3 if it matched the memory's NAME (an entity mention
  is a strong signal)
- inject only if the best score clears ABS_MIN *and* beats the runner-up
  by MARGIN — if everything is equally weakly related, that's noise

Tuning rule: bias hard toward silence. A miss costs nothing (the model
can still recall explicitly); a wrong injection wastes tokens and feeds
the model stale context. Decisions are logged to injections.jsonl so the
thresholds can be tuned from real sessions.
"""

import math

from .runtime import Context, check, log_decision, store_dir, terms

ABS_MIN = 3.0   # tune: absolute score floor
MARGIN = 1.5    # tune: top must beat 2nd by this factor
TOP_N = 2

# Timestamps/provenance carry no retrieval signal — keep them out of the corpus.
_SKIP_PROPS = {
    "createdAt", "updatedAt", "capturedBy", "sourceContext", "sourceDocument",
    "sourceKind", "invalidatedAt", "invalidationReason",
}


def _corpus(store) -> list[dict]:
    """(gid, name, text) per live resource — name + every mem: literal
    property, so Decisions (rationale) and aliases score, not just
    description-bearing nodes."""
    import pyoxigraph as ox
    from ..namespaces import GRAPH_RESOURCE_BASE, MEM

    rows = store.query(
        f'SELECT ?g ?p ?o WHERE {{ GRAPH ?g {{ ?s ?p ?o }} '
        f'FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}")) }}'
    )
    by: dict[str, dict] = {}
    for r in rows:
        pred = r["p"].value
        if not pred.startswith(MEM):
            continue
        key = pred[len(MEM):]
        d = by.setdefault(r["g"].value.removeprefix(GRAPH_RESOURCE_BASE),
                          {"name": "", "parts": [], "dead": False})
        if key == "invalidated":
            d["dead"] = True
        elif key in _SKIP_PROPS or not isinstance(r["o"], ox.Literal):
            continue
        elif key == "name":
            d["name"] = r["o"].value
        else:
            d["parts"].append(r["o"].value)

    docs = []
    for gid, d in by.items():
        if d["dead"]:
            continue
        body = " ".join(d["parts"])
        docs.append({
            "gid": gid,
            "name": d["name"],
            "desc": body[:300],
            "name_terms": set(terms(d["name"])),
            "terms": set(terms(f"{d['name']} {body}")),
        })
    return docs


def _idf(docs: list[dict]) -> dict[str, float]:
    n = len(docs) or 1
    df: dict[str, int] = {}
    for d in docs:
        for t in d["terms"]:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1 + n / c) for t, c in df.items()}


def _score(q_terms: set[str], d: dict, idf: dict[str, float]) -> float:
    s = 0.0
    for t in q_terms:
        if t in d["terms"]:
            s += idf.get(t, 0.0) * (3.0 if t in d["name_terms"] else 1.0)
    return s


@check
def recall_memories(ctx: Context) -> str | None:
    q = set(terms(ctx.prompt))
    if not q:
        return None
    from ..store import MemoryStore
    store = MemoryStore.open_or_create(store_dir())
    docs = _corpus(store)
    if not docs:
        return None

    idf = _idf(docs)
    ranked = sorted(((_score(q, d, idf), d) for d in docs),
                    key=lambda x: x[0], reverse=True)
    top = ranked[0][0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if top < ABS_MIN or top < MARGIN * (second or 0.0001):
        log_decision({"fired": False, "top": round(top, 2),
                      "second": round(second, 2), "terms": sorted(q)})
        return None  # not confident -> silent, zero tokens added

    injected = set(ctx.state.get("injected", []))
    lines, fresh = [], []
    for score, d in ranked[:TOP_N]:
        if score >= ABS_MIN and d["gid"] not in injected:
            lines.append(f"- {d['name'] or d['gid']}: {d['desc']}")
            fresh.append(d["gid"])
    log_decision({"fired": bool(fresh), "top": round(top, 2),
                  "second": round(second, 2), "terms": sorted(q),
                  "nodes": [d["name"] for _, d in ranked[:TOP_N]]})
    if not fresh:
        return None  # everything relevant was already injected this session
    ctx.state["injected"] = sorted(injected | set(fresh))
    return ("Relevant memory (auto-recalled, may be stale — verify before acting):\n"
            + "\n".join(lines))
