"""Gate preview — "what would this prompt inject?", answered exactly.

memory_search is NOT the injection pipeline: it's the fuzzy entry-point
finder (no thresholds, no margin band, no proximity prior, no session-log
layer, concepts included). Using it to predict injections misleads. This
module runs the REAL decision math — the same corpus, scorer, thresholds,
and both layers the gate uses per prompt — and shows its work, without
side effects: nothing is logged, no memo is written, so terminal
experiments never pollute the tuning data.

Differences from a live session, stated in the output:
- the session memo doesn't apply (a live session injects each node once);
- session-log eligibility is simplified (all undistilled entries shown —
  live, own-session entries wait for a compaction).

`claude-memory-graph gate "why did we pick pyoxigraph?" [--project P]`
"""

from .recall import _bigrams, _corpus, _idf, _project_neighbourhood, query_views, score_views
from .runtime import config, store_dir


def _rank(docs, views, idf, near, boost):
    return sorted(
        ((score_views(views, d, idf) * (boost if d.get("iri") in near else 1.0), d)
         for d in docs),
        key=lambda x: x[0], reverse=True)


def preview(prompt: str, project: str = "", show: int = 6) -> str:
    from ..store import MemoryStore
    from . import session_corpus

    cfg = config()
    views = query_views(prompt)
    q = views[0][0]
    lines = [f"prompt terms: {' '.join(sorted(q)) or '(none — trivial prompt, gate never runs)'}"
             + (f"  ·  scored as {len(views)} views (whole prompt + sentences; best wins)"
                if len(views) > 1 else "")]
    if not q:
        return "\n".join(lines)

    store = MemoryStore.open_or_create(store_dir())
    docs = _corpus(store)
    idf = _idf(docs) if docs else {}

    # ---- graph layer: the exact live decision ----
    lines.append(f"\nGRAPH LAYER ({len(docs)} nodes; thresholds: ABS_MIN {cfg['ABS_MIN']}, "
                 f"MARGIN {cfg['MARGIN']}, TOP_N {cfg['TOP_N']}"
                 + (f"; proximity ×{cfg['PROX_BOOST']} near Project '{project}'" if project else "")
                 + ")")
    if not docs:
        lines.append("  graph empty — nothing can inject from this layer")
        strong = []
    else:
        near = _project_neighbourhood(store, project)
        ranked = _rank(docs, views, idf, near, cfg["PROX_BOOST"])
        top = ranked[0][0]
        strong = [(s, d) for s, d in ranked[:cfg["TOP_N"]]
                  if s >= cfg["ABS_MIN"] and s > top / cfg["MARGIN"]]
        rest = ranked[len(strong)][0] if len(ranked) > len(strong) else 0.0
        for s, d in ranked[:show]:
            marks = []
            if s >= cfg["ABS_MIN"]:
                marks.append("≥ABS_MIN")
            if d.get("iri") in near:
                marks.append("proximity-boosted")
            if any(d is sd for _, sd in strong):
                marks.append("IN GROUP")
            lines.append(f"  {s:6.2f}  {d['model'] or '?':<11} {d['name'][:52]:<52} "
                         f"{' '.join(marks)}")
        if strong and top >= cfg["MARGIN"] * (rest or 0.0001):
            lines.append(f"  → INJECTS {len(strong)} node(s): group beats the rest "
                         f"({rest:.2f}) by ≥ MARGIN")
        else:
            why = ("no candidate reached ABS_MIN" if not strong else
                   f"group ({top:.2f}) doesn't beat the rest ({rest:.2f}) by MARGIN")
            lines.append(f"  → SILENT: {why}")

    # ---- session-log layer ----
    log_docs = session_corpus.docs(project, "", 1, _bigrams) if project else []
    budget = cfg["TOP_N"] - len(strong)
    lines.append(f"\nSESSION-LOG LAYER ({len(log_docs)} undistilled entr"
                 f"{'y' if len(log_docs) == 1 else 'ies'} for project "
                 f"'{project or '—'}'; floor LOG_ABS_MIN {cfg['LOG_ABS_MIN']}; "
                 f"budget {max(budget, 0)} after graph)")
    if not project:
        lines.append("  pass --project to preview this layer (entries are per-project)")
    elif not log_docs:
        lines.append("  no eligible entries")
    else:
        log_idf = {**_idf(log_docs), **idf}  # same merge as the live layer
        log_ranked = _rank(log_docs, views, log_idf, set(), 1.0)
        log_strong = [(s, d) for s, d in log_ranked[:max(budget, 0)]
                      if s >= cfg["LOG_ABS_MIN"]]
        for s, d in log_ranked[:show]:
            mark = "WOULD INJECT" if any(d is sd for _, sd in log_strong) else ""
            lines.append(f"  {s:6.2f}  {d['model']:<11} {d['name'][:44]:<44} "
                         f"[{d['source_file']}] {mark}")
        if not log_strong:
            lines.append(f"  → SILENT: nothing ≥ LOG_ABS_MIN within budget")

    lines.append("\nnotes: preview writes NO logs and NO memo. Live differences: each "
                 "node injects once per session (memo); own-session log entries only "
                 "become eligible after a compaction.")
    return "\n".join(lines)
