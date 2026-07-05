"""The miss detector's JOIN: grade the gate's homework from two logs.

Inputs (both in the hook-kit home, both written automatically):
- injections.jsonl        every gate decision: fired or silent, scores, terms,
                          the would-have-been top node on silence
- explicit-recalls.jsonl  every time the model explicitly reached for memory
                          (memory_recall / memory_query / memory_search)

The rule: an explicit recall shortly after gate SILENCE, in the same session,
is a revealed false negative — the model went to the shelf itself, so the
memory existed, was wanted, and the gate didn't hand it over. Nobody labels
anything; the model's own behaviour is the answer key.

Exclusions (the two cases that are NOT gate misses):
- the recall found nothing        -> a CAPTURE GAP: nobody ever stored it;
                                     report separately, it indicts distill,
                                     not the gate
- the gate FIRED for that node    -> the model drilled deeper into something
  shortly before                     already injected; the gate did its job

Each miss carries the silent decision's score, so the report can say WHICH
fix the evidence points at:
- score close to ABS_MIN  -> threshold miss: the knob is a touch too high
- score far below         -> vocabulary miss: no threshold would have caught
                             it; the NODE needs aliases / concept links

Run: `claude-memory-graph misses` (analysis only — no runtime cost; the two
logs are written live, this join happens when you ask for it).
"""

import json

from claude_hook_kit import state_home

from .runtime import config

# An explicit recall is joined against silent decisions no older than this.
# Generous on purpose: the model often works for a few minutes before
# deciding it needs memory. Tighten if joins look spurious.
WINDOW_SECONDS = 600


def _read_jsonl(filename: str) -> list[dict]:
    path = state_home() / filename
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                out.append(entry)
        except ValueError:
            continue
    return out


def _name_of(target: str) -> str:
    """'Decision/Use pyoxigraph over rdflib' -> 'Use pyoxigraph over rdflib'."""
    return target.split("/", 1)[-1] if target else ""


def _classify(top: float) -> str:
    abs_min = config()["ABS_MIN"]
    if top >= 0.7 * abs_min:
        return f"threshold miss — scored {top} vs ABS_MIN {abs_min}; consider lowering ABS_MIN"
    return (f"vocabulary miss — scored only {top}; no sane threshold catches this. "
            "Add aliases/concept links to the node instead")


def analyse(window: int = WINDOW_SECONDS) -> dict:
    """Join the two logs. Returns {'misses': [...], 'gaps': [...], counts...}."""
    decisions = _read_jsonl("injections.jsonl")
    recalls = _read_jsonl("explicit-recalls.jsonl")

    misses, gaps = [], []
    for recall in recalls:
        session, ts = recall.get("session", ""), recall.get("ts", 0)
        wanted = _name_of(recall.get("target", "")) or recall.get("sparql", "")

        before = [d for d in decisions
                  if d.get("session", "") == session
                  and 0 <= ts - d.get("ts", 0) <= window]
        if not before:
            continue  # recall with no gate decision in range — nothing to grade

        # If the gate recently fired for this node, the model is drilling
        # deeper into an injected memory — that's success, not a miss.
        lower_wanted = wanted.lower()
        covered = any(
            d.get("fired") and any(
                n.lower() in lower_wanted or lower_wanted in n.lower()
                for n in d.get("nodes", []) if n)
            for d in before)
        if covered:
            continue

        silents = [d for d in before if not d.get("fired")]
        if not silents:
            continue
        nearest = max(silents, key=lambda d: d.get("ts", 0))

        record = {"recall": recall, "decision": nearest}
        if recall.get("found"):
            misses.append(record)
        else:
            gaps.append(record)

    return {"misses": misses, "gaps": gaps,
            "decisions": len(decisions), "recalls": len(recalls)}


def report(window: int = WINDOW_SECONDS) -> str:
    result = analyse(window)
    lines = [f"gate decisions: {result['decisions']} · explicit recalls: "
             f"{result['recalls']} · misses: {len(result['misses'])} · "
             f"capture gaps: {len(result['gaps'])}"]

    for record in result["misses"]:
        d, r = record["decision"], record["recall"]
        wanted = r.get("target") or r.get("sparql", "?")
        lines += [
            "",
            f"MISS  session={r.get('session', '?')}",
            f"  gate:   silent  top={d.get('top')}  top_node='{d.get('top_node', '?')}'"
            f"  terms({' '.join(d.get('terms', []))})",
            f"  model:  {r.get('tool')} -> {wanted}  [found]",
            f"  fix:    {_classify(d.get('top', 0.0))}",
        ]

    for record in result["gaps"]:
        r = record["recall"]
        wanted = r.get("target") or r.get("sparql", "?")
        lines += [
            "",
            f"CAPTURE GAP  session={r.get('session', '?')}",
            f"  model looked for: {r.get('tool')} -> {wanted}  [nothing stored]",
            "  fix:    not a gate problem — this knowledge was never captured. "
            "Worth a context note or distill run.",
        ]

    if not result["misses"] and not result["gaps"]:
        lines.append("no misses detected — the gate's silences went unchallenged.")
    return "\n".join(lines)
