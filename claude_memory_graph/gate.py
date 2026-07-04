"""Per-prompt hook runtime (UserPromptSubmit).

Reads the hook's stdin JSON once, runs each check, prints whatever they
return (Claude Code injects hook stdout as context), and always exits 0 —
a broken gate must never degrade the session.

Checks are plain functions returning str | None. To add one, write the
function and call it from main(). Current checks:
- recall_gate: ambient memory injection (IDF-scored, silent by default)
- context_nudge: deterministic context-file write reminder (prompt counter)

Shared per-session state lives in one JSON file per session_id under
_STATE_DIR; every injection decision is appended to injections.jsonl for
threshold tuning.
"""

import json
import math
import os
import re
import sys
import time
from pathlib import Path

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
    "are", "this", "that", "it", "be", "can", "could", "would", "how", "what",
    "when", "i", "you", "we", "do", "does", "make", "get", "set", "use",
    # acknowledgement words: bare "thanks"/"yes"/"ok" must reduce to no terms
    "thanks", "thank", "yes", "yep", "ok", "okay", "sure", "no", "nope", "please",
}
_WORD = re.compile(r"[a-z0-9]+")

ABS_MIN = 3.0   # tune: absolute score floor
MARGIN = 1.5    # tune: top must beat 2nd by this factor
TOP_N = 2
N_TURNS = 3     # nudge every N significant prompts (protocol's "3+")

_STATE_DIR = Path.home() / ".claude" / "memory-graph" / "state"

# Timestamps/provenance carry no retrieval signal — keep them out of the corpus.
_SKIP_PROPS = {
    "createdAt", "updatedAt", "capturedBy", "sourceContext", "sourceDocument",
    "sourceKind", "invalidatedAt", "invalidationReason",
}


def _terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP]


def _store_dir() -> Path:
    # duplicated from __main__._store_path: importing __main__ would pull in mcp
    env = os.environ.get("MEMORY_GRAPH_PATH")
    return Path(env) if env else Path.home() / ".claude" / "memory-graph" / "store"


# ================================================================
# Session state (a hook is a fresh subprocess per prompt)
# ================================================================

def _load_state(session_id: str) -> dict:
    try:
        return json.loads((_STATE_DIR / f"{session_id}.json").read_text())
    except Exception:
        return {}


def _save_state(session_id: str, state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    (_STATE_DIR / f"{session_id}.json").write_text(json.dumps(state))


def _log(decision: dict) -> None:
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        decision["ts"] = int(time.time())
        with open(_STATE_DIR / "injections.jsonl", "a") as f:
            f.write(json.dumps(decision) + "\n")
    except Exception:
        pass


# ================================================================
# Check 1: ambient recall (prompt-gated, silent by default)
# ================================================================

def _corpus(store) -> list[dict]:
    """(gid, name, text) per live resource — name + every mem: literal
    property, so Decisions (rationale) and aliases score, not just
    description-bearing nodes."""
    import pyoxigraph as ox
    from .namespaces import GRAPH_RESOURCE_BASE, MEM

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
            "name_terms": set(_terms(d["name"])),
            "terms": set(_terms(f"{d['name']} {body}")),
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


def recall_gate(prompt: str, session_id: str = "") -> str | None:
    q = set(_terms(prompt))
    if not q:
        return None
    from .store import MemoryStore
    store = MemoryStore.open_or_create(_store_dir())
    docs = _corpus(store)
    if not docs:
        return None
    idf = _idf(docs)
    ranked = sorted(((_score(q, d, idf), d) for d in docs),
                    key=lambda x: x[0], reverse=True)
    top = ranked[0][0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if top < ABS_MIN or top < MARGIN * (second or 0.0001):
        _log({"fired": False, "top": round(top, 2), "second": round(second, 2),
              "terms": sorted(q)})
        return None  # not confident -> silent, zero tokens added

    state = _load_state(session_id) if session_id else {}
    injected = set(state.get("injected", []))
    lines, fresh = [], []
    for sc, d in ranked[:TOP_N]:
        if sc >= ABS_MIN and d["gid"] not in injected:
            lines.append(f"- {d['name'] or d['gid']}: {d['desc']}")
            fresh.append(d["gid"])
    _log({"fired": bool(fresh), "top": round(top, 2), "second": round(second, 2),
          "terms": sorted(q), "nodes": [d["name"] for _, d in ranked[:TOP_N]]})
    if not fresh:
        return None  # already injected this session
    if session_id:
        state["injected"] = sorted(injected | set(fresh))
        _save_state(session_id, state)
    return ("Relevant memory (auto-recalled, may be stale — verify before acting):\n"
            + "\n".join(lines))


# ================================================================
# Check 2: deterministic context-write nudge (prompt counter)
# ================================================================

def context_nudge(session_id: str, prompt: str) -> str | None:
    if not session_id or not _terms(prompt):
        return None  # bare thanks/yes/ok -> don't count, don't nudge
    state = _load_state(session_id)
    state["significant"] = state.get("significant", 0) + 1
    nudge = None
    if state["significant"] - state.get("last_nudge_at", 0) >= N_TURNS:
        state["last_nudge_at"] = state["significant"]
        nudge = (f"[context] {state['significant']} significant exchanges since last "
                 "context update — you are overdue. Append the decisions/problems/"
                 "preferences since your last entry to the session context file per "
                 "the context protocol, then continue.")
    _save_state(session_id, state)
    return nudge


# ================================================================
# Entry point — always exit 0
# ================================================================

def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip().startswith("{") else {}
        prompt = (data.get("prompt") if data else raw) or ""
        session_id = data.get("session_id", "") if data else ""
        out = []
        for result in (
            _safe(recall_gate, prompt, session_id),
            _safe(context_nudge, session_id, prompt),
        ):
            if result:
                out.append(result)
        if out:
            print("\n\n".join(out))
    except Exception:
        pass  # fail open: the session must never degrade because the gate broke


def _safe(fn, *args) -> str | None:
    try:
        return fn(*args)
    except Exception:
        return None


if __name__ == "__main__":
    main()
