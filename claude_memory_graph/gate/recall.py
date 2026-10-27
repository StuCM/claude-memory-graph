"""Extension: ambient memory recall — inject relevant memories, unasked.

The idea in one line: if your prompt contains rare words that also appear
in a stored memory's name or text, that memory is probably relevant —
inject it; otherwise say nothing.

Scoring (no LLM anywhere):
- every memory becomes a bag of words from its name + literal properties
- each shared word scores its IDF weight (rare words count, common words
  barely count), x3 if it matched the memory's NAME (an entity mention
  is a strong signal)
- proximity prior: memories that ARE the current project's node or sit
  one link from it score xPROX_BOOST — "arches" typed inside the
  memory-graph project should rank this project's arches-inspired design
  above another project's arches gotcha
- inject when the group of strong scorers (>= ABS_MIN, within MARGIN of
  the top) stands out from the rest of the graph by MARGIN; the in-group
  band also sheds lexical-only stragglers a boosted winner leaves behind

Tuning rule: bias hard toward silence. A miss costs nothing (the model
can still recall explicitly); a wrong injection wastes tokens and feeds
the model stale context. Decisions are logged to injections.jsonl in the
hook-kit home so the thresholds can be tuned from real sessions.

Also handles SessionStart: auto-prime with the current project's (and
MEMORY_GRAPH_USER's) recall, so sessions begin already primed.
"""

import math
import os
import re
from pathlib import Path

from claude_memory_graph.hookcore import (HookContext, HookExtension, append_jsonl, bigrams,
                                          log_error, terms_pos)

from .runtime import config, store_dir

# Timestamps/provenance carry no retrieval signal — keep them out of the corpus.
_SKIP_PROPS = {
    "createdAt", "updatedAt", "capturedBy", "sourceContext", "sourceDocument",
    "sourceKind", "invalidatedAt", "invalidationReason",
}


def _bigrams(pos_terms: list[tuple[int, str]]) -> set[tuple[str, str]]:
    return bigrams(pos_terms, gap=config()["PHRASE_GAP"])


# Hook context past ~10k chars is cut off; a depth-2 prime was ~440KB.
# Lines are additionally capped by PRIME_MAX_CHARS (runtime config).
PRIME_LINKS = 20
_DESC_CHARS = 200

_SEGMENT_RE = re.compile(r"[.!?;\n]+")
_SEGMENT_MIN_TERMS = 12  # prompts shorter than this score fine as one view


def query_views(prompt: str) -> list[tuple[set, set]]:
    """(terms, bigrams) views of the prompt: the whole thing, plus each
    sentence-ish segment when the prompt is a real chunk of text.

    A prompt is rarely a single question — it's usually descriptive prose
    with the actual asks embedded in it. Scored as one bag of words, a
    long prompt DROWNS its own signals: the coverage factor divides by
    every word in the prompt, so three strong rare-word matches inside
    sixty words of description get halved into silence. Scoring each
    segment separately and taking a document's BEST view means a memory
    relevant to one sentence fires regardless of how much surrounds it."""
    pos = terms_pos(prompt)
    views = [({w for _, w in pos}, _bigrams(pos))]
    if len(pos) >= _SEGMENT_MIN_TERMS:
        for segment in _SEGMENT_RE.split(prompt):
            seg_pos = terms_pos(segment)
            if len(seg_pos) >= 2:
                views.append(({w for _, w in seg_pos}, _bigrams(seg_pos)))
    return views


def score_views(views: list[tuple[set, set]], d: dict, idf: dict) -> float:
    return max(_score(q, d, idf, q_bi) for q, q_bi in views)


def _corpus(store, include_concepts: bool = False) -> list[dict]:
    """(gid, name, text) per live resource — name + every mem: literal
    property, so Decisions (rationale) and aliases score, not just
    description-bearing nodes. With include_concepts, concept nodes join
    the corpus too (label as name, gid=None) — memory_search wants them
    as entry points; the gate's injection path does not use them."""
    import pyoxigraph as ox
    from ..namespaces import GRAPH_CONCEPTS, GRAPH_RESOURCE_BASE, MEM, RDF_TYPE
    from ..tools.recall import _CONTENT_KEYS, _DISPLAY_SKIP

    def _collect(rows, gid_of) -> dict[str, dict]:
        by: dict[str, dict] = {}
        for r in rows:
            d = by.setdefault(gid_of(r), {"name": "", "parts": [], "dead": False,
                                          "model": "", "iri": r["s"].value})
            if r["p"] == RDF_TYPE:
                if isinstance(r["o"], ox.NamedNode) and r["o"].value.startswith(MEM):
                    d["model"] = r["o"].value[len(MEM):]
                continue
            pred = r["p"].value
            if not pred.startswith(MEM):
                continue
            key = pred[len(MEM):]
            if key == "invalidated":
                d["dead"] = True
            elif key in _SKIP_PROPS or not isinstance(r["o"], ox.Literal):
                continue
            elif key in ("name", "label"):
                d["name"] = r["o"].value
            else:
                d["parts"].append((key, r["o"].value))
        return by

    def _display(parts: list[tuple[str, str]]) -> str:
        """What the model reads: content first, matching data (aliases,
        status, anchors) left out — it scored the match, it isn't the memory."""
        readable = [(k, v) for k, v in parts if k not in _DISPLAY_SKIP]
        readable.sort(key=lambda kv: _CONTENT_KEYS.index(kv[0])
                      if kv[0] in _CONTENT_KEYS else len(_CONTENT_KEYS))
        text = " ".join(" ".join(v.split()) for _k, v in readable)
        return text[:_DESC_CHARS] + ("…" if len(text) > _DESC_CHARS else "")

    rows = store.query(
        f'SELECT ?g ?s ?p ?o WHERE {{ GRAPH ?g {{ ?s ?p ?o }} '
        f'FILTER(STRSTARTS(STR(?g), "{GRAPH_RESOURCE_BASE}")) }}'
    )
    by = {gid: d for gid, d in _collect(
        rows, lambda r: r["g"].value.removeprefix(GRAPH_RESOURCE_BASE)).items()}

    concept_by: dict[str, dict] = {}
    if include_concepts:
        rows = store.query(
            f'SELECT ?s ?p ?o WHERE {{ GRAPH <{GRAPH_CONCEPTS}> {{ ?s ?p ?o }} }}'
        )
        concept_by = _collect(rows, lambda r: r["s"].value)

    concepts_of = _concept_labels(store)
    docs = []
    for gid, d in list(by.items()) + [(None, d) for d in concept_by.values()]:
        if d["dead"]:
            continue
        body = " ".join(v for _k, v in d["parts"])
        name_pos = terms_pos(d["name"])
        all_pos = terms_pos(f"{d['name']} {body}")
        concept_bigrams = set()
        for label in concepts_of.get(d["iri"], ()):
            label_pos = terms_pos(label)
            all_pos += label_pos
            concept_bigrams |= _bigrams(label_pos)
        docs.append({
            "gid": gid,
            "iri": d["iri"],
            "name": d["name"],
            "model": d["model"],
            "desc": _display(d["parts"]),
            "name_terms": {w for _, w in name_pos},
            "terms": {w for _, w in all_pos},
            "name_bigrams": _bigrams(name_pos),
            "bigrams": _bigrams(all_pos) | concept_bigrams,
            "parts": d["parts"],          # the semantic channel embeds these
        })
    return docs


def _concept_labels(store) -> dict[str, list[str]]:
    """Resource IRI -> labels of its concepts. The concept links are the
    graph's linking vocabulary; without them a node only matches its own text."""
    from ..namespaces import GRAPH_CONCEPTS, GRAPH_LINKS
    # Three flat queries in Python, not one SPARQL join: the join took ~5s.
    labels = {r["c"].value: r["label"].value for r in store.query(
        f'SELECT ?c ?label WHERE {{ GRAPH <{GRAPH_CONCEPTS}> {{ ?c mem:label ?label }} }}')}
    closed = {r["l"].value for r in store.query(
        f'SELECT ?l WHERE {{ GRAPH <{GRAPH_LINKS}> {{ '
        f'{{ ?l mem:linkValidUntil ?e }} UNION {{ ?l mem:linkInvalidatedAt ?i }} }} }}')}
    out: dict[str, list[str]] = {}
    for r in store.query(
            f'SELECT ?l ?s ?c WHERE {{ GRAPH <{GRAPH_LINKS}> {{ ?l mem:linkRelation "hasConcept" ; '
            f'mem:linkSource ?s ; mem:linkTarget ?c }} }}'):
        label = labels.get(r["c"].value)
        if label and r["l"].value not in closed:
            out.setdefault(r["s"].value, []).append(label)
    return out


def _project_neighbourhood(store, project: str) -> set[str]:
    """IRIs of the current project's node plus everything one link away —
    the graph-distance prior's 'near' set. Empty when cwd has no Project node."""
    if not project:
        return set()
    found = store.find_resource("Project", project)
    if not found:
        return set()
    _, iri = found
    from ..namespaces import GRAPH_LINKS
    near = {iri.value}
    rows = store.query(
        f'SELECT ?other WHERE {{\n'
        f'    GRAPH <{GRAPH_LINKS}> {{\n'
        f'        ?l mem:linkSource ?s ; mem:linkTarget ?t .\n'
        f'        FILTER NOT EXISTS {{ ?l mem:linkValidUntil ?end }}\n'
        f'        FILTER NOT EXISTS {{ ?l mem:linkInvalidatedAt ?inv }}\n'
        f'    }}\n'
        f'    FILTER(?s = <{iri.value}> || ?t = <{iri.value}>)\n'
        f'    BIND(IF(?s = <{iri.value}>, ?t, ?s) AS ?other)\n'
        f'}}'
    )
    for r in rows:
        near.add(r["other"].value)
    return near


def _idf(docs: list[dict]) -> dict[str, float]:
    n = len(docs) or 1
    df: dict[str, int] = {}
    for d in docs:
        for t in d["terms"]:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1 + n / c) for t, c in df.items()}


def _score(q_terms: set[str], d: dict, idf: dict[str, float],
           q_bigrams: set[tuple[str, str]] = frozenset()) -> float:
    s = 0.0
    matched = 0
    for t in q_terms:
        if t in d["terms"]:
            matched += 1
            s += idf.get(t, 0.0) * (3.0 if t in d["name_terms"] else 1.0)
    # Phrase evidence: a shared adjacent pair scores both words again,
    # x3 when the phrase sits in the memory's name.
    for a, b in q_bigrams & d.get("bigrams", set()):
        s += (idf.get(a, 0.0) + idf.get(b, 0.0)) * \
             (3.0 if (a, b) in d.get("name_bigrams", set()) else 1.0)
    # Coordination: a memory covering MORE of the prompt's distinct concepts
    # beats one matching a single concept heavily — "arches AND the memory
    # graph" should prefer the doc that knows about both.
    coverage = matched / len(q_terms) if q_terms else 0.0
    return s * (0.5 + 0.5 * coverage)


def decide(ranked: list[tuple[float, dict]], cfg: dict) -> tuple[list, float, int]:
    """The inject-or-stay-silent decision, shared by the live gate and the
    preview so they cannot disagree. Returns (group, rest, similar): an empty
    group means silence; `similar` counts further band members left out.

    Band = nodes >= ABS_MIN and within MARGIN of the top. The group is the
    band's first TOP_N; normally it must beat the best node left behind by
    MARGIN, which silences generic matches (one common word scoring a dozen
    nodes alike). But a band wider than TOP_N is ALSO what a well-distilled
    topic looks like: five arches gotchas all scoring 64 against a floor of
    3 tied each other, so `rest` was one of them and the gate went silent on
    the strongest possible match. A group that strong (>= CLUSTER_FACTOR x
    ABS_MIN) is a topic cluster: inject its head and point at the rest."""
    if not ranked:
        return [], 0.0, 0
    top = ranked[0][0]
    band = [(s, d) for s, d in ranked if s >= cfg["ABS_MIN"] and s > top / cfg["MARGIN"]]
    group = band[:cfg["TOP_N"]]
    rest = ranked[len(group)][0] if len(ranked) > len(group) else 0.0
    if not group:
        return [], rest, 0
    if top >= cfg["MARGIN"] * (rest or 0.0001):
        return group, rest, 0
    if top >= cfg["CLUSTER_FACTOR"] * cfg["ABS_MIN"]:
        return group, rest, len(band) - len(group)
    return [], rest, 0


# ----------------------------------------------------------------
# Per-prompt index cache
# ----------------------------------------------------------------

# Bump when the doc dict shape or scoring inputs change.
_INDEX_VERSION = 2   # 2: docs carry parts; the index carries field embeddings


def _index_key() -> tuple | None:
    nq = store_dir() / "graph.nq"
    try:
        st = nq.stat()
    except OSError:
        return None
    return (str(nq), st.st_mtime_ns, st.st_size, st.st_ino,
            _INDEX_VERSION, config()["PHRASE_GAP"])


def gate_index(project: str, opener) -> tuple[list[dict], dict, set[str], dict[str, str]]:
    """(docs, idf, near, links) for this prompt, rebuilt only when graph.nq changed.

    Every prompt is a fresh hook process, and building the corpus means
    loading the whole store and tokenizing every node: ~40ms at 300 nodes,
    ~450ms at 3,000 — on every keystroke-to-answer. The index depends only
    on the store file, so it's pickled in the hook-kit home keyed by the
    file's identity (path, mtime, size, inode) and rebuilt on change. The
    project neighbourhood is cached per project alongside. `opener` returns
    the MemoryStore, called only on a miss. Fail open: any cache problem
    means a normal rebuild."""
    import pickle
    from claude_memory_graph.hookcore import state_home

    path = state_home() / "gate-index.pickle"
    key = _index_key()
    cached = None
    if key is not None:
        try:
            with open(path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("key") != key:
                cached = None
        except Exception:
            cached = None

    dirty = False
    if cached is None:
        store = opener()
        docs = _corpus(store)
        cached = {"key": key, "docs": docs, "idf": _idf(docs), "near": {},
                  "links": _link_summaries(store, docs), "sem": _semantic_index(docs)}
        dirty = True
    near = cached["near"].get(project)
    if near is None:
        near = _project_neighbourhood(opener(), project)
        cached["near"][project] = near
        dirty = True
    if dirty and key is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "wb") as f:
                pickle.dump(cached, f)
            tmp.replace(path)
        except Exception:
            pass
    global _last_semantic
    _last_semantic = cached.get("sem")
    return cached["docs"], cached["idf"], near, cached["links"]


_ENTITY_MODELS = frozenset({"Project", "Person", "Company", "Technology"})

# The field embeddings that came with the gate index this process loaded.
_last_semantic = None


def _semantic_index(docs: list[dict]) -> dict | None:
    if not config()["SEMANTIC"]:
        return None
    try:
        from . import semantic
        return semantic.build_index(docs)
    except Exception as exc:  # embeddings are an extra channel — fail open
        log_error("semantic index", exc)
        return None


_GIST_CHARS = 90


def _pointer_line(d: dict, link_suffix: str, q: set, idf: dict, via: str) -> str:
    """One line per nominated memory: what it is, a gist, its first link, and
    why it matched, so the model can judge relevance without opening it."""
    gist = d["desc"].split("; ")[0].split(". ")[0]
    if len(gist) > _GIST_CHARS:
        gist = gist[:_GIST_CHARS].rsplit(" ", 1)[0] + "…"
    link = ""
    if link_suffix:
        first = link_suffix.strip(" ()").split(" · ")[0]
        link = f" · {first}"
    if via == "semantic":
        why = "by meaning"
    else:
        shared = sorted(q & d["terms"], key=lambda w: idf.get(w, 0.0), reverse=True)[:3]
        why = ", ".join(shared) if shared else "words"
    model = d["model"] or "Concept"
    return (f"- {model} '{d['name'] or d['gid']}'" + (f" — {gist}" if gist else "")
            + f"{link} · matched: {why}")


def semantic_pick(prompt: str, docs: list[dict], cfg: dict) -> tuple[list, float, float]:
    """The meaning channel, consulted when the lexical gate stays silent.
    Fires on one memory when its best field is close enough to the prompt
    AND clearly ahead of the runner-up — a flat field of weak similarities
    is noise, not a match. Returns ([(score, doc)] or [], top, second)."""
    index = _last_semantic
    if index is None or not docs:
        return [], 0.0, 0.0
    try:
        from . import semantic
        ranked = semantic.rank(index, prompt, len(docs))
    except Exception as exc:
        log_error("semantic rank", exc)
        return [], 0.0, 0.0
    # Knowledge, not entities: a prompt about search is near the Elasticsearch
    # node in meaning without needing it. Entities are matched by name — the
    # lexical channel's job; meaning is for decisions, patterns, problems.
    ranked = [(s, i) for s, i in ranked if docs[i]["model"] not in _ENTITY_MODELS]
    if not ranked:
        return [], 0.0, 0.0
    top, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if top >= cfg["SEM_MIN"] and top - second >= cfg["SEM_GAP"]:
        return [(top, docs[best])], top, second
    return [], top, second


def _link_summaries(store, docs: list[dict]) -> dict[str, str]:
    """Every node's neighbourhood suffix — ' (affects→ Project 'quartz' ·
    +2 more)' — computed once per index build, so the injection carries the
    neighbourhood (decision + what it affects), not a bare match.

    Building these per winner meant opening the whole store on every firing
    prompt (~2s at 3,000 nodes); one pass over the links graph here costs a
    fraction of that and is cached with the index. Same filters as
    store.recall at depth 1: open links only, live nodes only."""
    from ..namespaces import GRAPH_CONCEPTS, GRAPH_LINKS
    known = {d["iri"]: (d["model"], d["name"]) for d in docs}
    for r in store.query(
            f'SELECT ?c ?type ?label WHERE {{ GRAPH <{GRAPH_CONCEPTS}> '
            f'{{ ?c rdf:type ?type ; mem:label ?label }} }}'):
        known[r["c"].value] = (r["type"].value.rsplit("#", 1)[-1], r["label"].value)
    neighbours: dict[str, list[tuple[str, str]]] = {}
    for r in store.query(
            f'SELECT ?s ?t ?rel WHERE {{ GRAPH <{GRAPH_LINKS}> {{\n'
            f'    ?l mem:linkSource ?s ; mem:linkTarget ?t ; mem:linkRelation ?rel .\n'
            f'    FILTER NOT EXISTS {{ ?l mem:linkValidUntil ?end }}\n'
            f'    FILTER NOT EXISTS {{ ?l mem:linkInvalidatedAt ?inv }}\n'
            f'}} }}'):
        s, t, rel = r["s"].value, r["t"].value, r["rel"].value
        for me, other in ((s, t), (t, s)):
            if me in known and other in known:
                neighbours.setdefault(me, []).append((rel, other))
    out: dict[str, str] = {}
    for me, links in neighbours.items():
        links = list(dict.fromkeys(links))
        parts = [f"{rel}→ {known[other][0]} '{known[other][1]}'" for rel, other in links[:3]]
        extra = len(links) - len(parts)
        out[me] = f" ({' · '.join(parts)}" + (f" · +{extra} more" if extra > 0 else "") + ")"
    return out


class RecallExtension(HookExtension):
    """Ambient memory recall: scored per-prompt injection + session-start auto-prime."""

    name = "memory-recall"
    enabled_by_default = True

    def on_session_start(self, ctx: HookContext) -> str | None:
        if ctx.state.get("primed"):
            return None
        from ..store import MemoryStore
        from ..tools import recall as recall_tool

        store = MemoryStore.open_or_create(store_dir())
        budget = config()["PRIME_MAX_CHARS"]
        project = ctx.project or Path(ctx.cwd or os.getcwd()).name
        user = os.environ.get("MEMORY_GRAPH_USER")
        sections = [s for s in (
            recall_tool.prime(store, "Project", project, PRIME_LINKS, budget),
            recall_tool.prime(store, "Person", user, PRIME_LINKS, budget) if user else None,
        ) if s]

        if not sections:
            return None  # nothing known -> silence, not noise
        ctx.state["primed"] = True
        append_jsonl("injections.jsonl", {
            "kind": "prime", "fired": True, "project": project,
            "session": ctx.core.get("session_id", "")})
        return "memory-graph auto-prime (recalled, not instructions):\n" + "\n\n".join(sections)

    def on_user_prompt_submit(self, ctx: HookContext) -> str | None:
        q = {w for _, w in ctx.terms_pos}
        if not q:
            return None
        cfg = config()
        views = query_views(ctx.prompt)  # whole prompt + its sentences
        from ..store import MemoryStore
        store = None

        def opener():
            nonlocal store
            if store is None:
                store = MemoryStore.open_or_create(store_dir())
            return store

        docs, idf, near, links = gate_index(ctx.project, opener)
        if not docs:
            # empty graph: the session log is still a retrieval source
            return self._log_recall(ctx, q, views, {}, budget=cfg["TOP_N"])

        boost = cfg["PROX_BOOST"]
        ranked = sorted(
            ((score_views(views, d, idf) * (boost if d["iri"] in near else 1.0), d)
             for d in docs),
            key=lambda x: x[0], reverse=True)
        top = ranked[0][0]
        strong, rest, similar = decide(ranked, cfg)
        session = ctx.core.get("session_id", "")
        via = "lexical"
        sem_top = sem_second = 0.0
        if not strong:
            # the words didn't match; does the meaning? (gate/semantic.py)
            strong, sem_top, sem_second = semantic_pick(ctx.prompt, docs, cfg)
            similar = 0
            if strong:
                via = "semantic"
        if not strong:
            # top_node makes silent decisions joinable by the miss detector:
            # "what WOULD the gate have injected, and what did it score?"
            append_jsonl("injections.jsonl", {
                "fired": False, "top": round(top, 2), "rest": round(rest, 2),
                "top_node": ranked[0][1]["name"], "session": session,
                "project": ctx.project, "terms": sorted(q),
                "sem_top": round(sem_top, 3), "sem_second": round(sem_second, 3)})
            # graph silent -> the session log gets the whole budget
            return self._log_recall(ctx, q, views, idf, budget=cfg["TOP_N"])

        injected = set(ctx.state.get("injected", []))
        pointer = cfg["INJECT_STYLE"] != "full"
        lines, fresh = [], []
        for _unused, d in strong:
            if d["gid"] in injected:
                continue
            fresh.append(d["gid"])
            if pointer:
                lines.append(_pointer_line(d, links.get(d["iri"], ""), q, idf, via))
            else:
                lines.append(f"- {d['name'] or d['gid']}: {d['desc']}{links.get(d['iri'], '')}")
                lines.append(f'  next: memory_recall(model="{d["model"]}", '
                             f'name="{d["name"]}", depth=2, focus="<what you need>")')
        entry = {"fired": bool(fresh), "top": round(top, 2), "rest": round(rest, 2),
                 "session": session, "project": ctx.project, "terms": sorted(q),
                 "nodes": [d["name"] for _, d in strong], "via": via}
        if via == "semantic":
            entry["sem_top"], entry["sem_second"] = round(sem_top, 3), round(sem_second, 3)
        if similar:
            entry["cluster"] = similar
        append_jsonl("injections.jsonl", entry)
        if not fresh:
            # graph already injected this session -> log layer still gets a look
            return self._log_recall(ctx, q, views, idf, budget=cfg["TOP_N"])
        ctx.state["injected"] = sorted(injected | set(fresh))
        if similar:
            topic = " ".join(sorted(q, key=lambda t: idf.get(t, 0.0), reverse=True)[:4])
            lines.append(f'- +{similar} similar — memory_search("{topic}")')
        if pointer:
            graph_section = (
                "Memory may bear on this (auto-matched, may be stale; your call):\n"
                + "\n".join(lines)
                + "\nIf it bears on the task: memory_recall(model, name, depth=2) to open one, "
                  "memory_ask a question, or hand it to the memory-researcher agent if it "
                  "needs digging. Otherwise ignore it.")
        else:
            graph_section = (
                "Memory entry points (auto-recalled, may be stale) — doors, not answers; "
                "traverse before re-deriving:\n"
                + "\n".join(lines))
        log_section = self._log_recall(
            ctx, q, views, idf, budget=max(1, cfg["TOP_N"] - len(fresh)),
            exclude=frozenset((d["model"], d["name"]) for _s, d in strong))
        return graph_section + (f"\n\n{log_section}" if log_section else "")

    def _log_recall(self, ctx: HookContext, q: set, views: list,
                    idf: dict, budget: int,
                    exclude: frozenset = frozenset()) -> str | None:
        """Second retrieval layer this prompt: score eligible session-log
        entries with the same machinery. Shares the TOP_N budget with the
        graph injection (graph wins the split); memoed per entry key."""
        if budget <= 0:
            return None
        from . import session_corpus
        cfg = config()
        try:
            docs = session_corpus.docs(
                ctx.project, ctx.core.get("started_at", ""),
                ctx.core.get("events", {}).get("PreCompact", 0), _bigrams)
        except Exception:
            return None  # the log index is best-effort — fail open
        if not docs:
            return None
        # Rarity for log terms the graph has never seen must come from the
        # log corpus itself — graph IDF alone would score fresh vocabulary 0
        # and the newest knowledge (the layer's whole point) could never fire.
        # Graph values win on overlap (bigger corpus, better estimates).
        idf = {**_idf(docs), **(idf or {})}
        seen = set(ctx.state.get("injected_log", []))
        ranked = sorted(((score_views(views, d, idf), d) for d in docs),
                        key=lambda x: x[0], reverse=True)
        # Filter, THEN take the budget: slicing first meant a batch of
        # already-injected entries at the top silenced the layer even with a
        # fresh one ranked just below. `exclude` drops entries whose node the
        # graph layer already injected this prompt — the same memory twice.
        eligible = [(s, d) for s, d in ranked
                    if s >= cfg["LOG_ABS_MIN"] and d["key"] not in seen
                    and (d["model"], d["name"]) not in exclude]
        strong = eligible[:budget]
        append_jsonl("injections.jsonl", {
            "kind": "log", "fired": bool(strong),
            "top": round(ranked[0][0], 2) if ranked else 0.0,
            "session": ctx.core.get("session_id", ""), "project": ctx.project,
            "nodes": [d["name"] for _, d in strong]})
        if not strong:
            return None
        ctx.state["injected_log"] = sorted(seen | {d["key"] for _, d in strong})
        lines = [
            f"- [{d['source_file']}] {d['model']}: {d['name']}"
            + (f" — {d['desc']}" if d["desc"] else "")
            for _, d in strong
        ]
        return ("Session log (undistilled — verify before acting):\n"
                + "\n".join(lines))

    # The other half of the miss detector: whenever the model EXPLICITLY
    # reaches for memory (PostToolUse on the memory-graph MCP tools), record
    # it. An explicit recall shortly after gate silence is a revealed false
    # negative — the model went to the shelf itself. The join lives in
    # gate/misses.py (`claude-memory-graph misses`); this just writes the log.
    def on_post_tool_use(self, ctx: HookContext) -> str | None:
        tool = ctx.tool_name
        short = tool.rsplit("__", 1)[-1]
        if short not in ("memory_recall", "memory_query", "memory_search"):
            return None
        tool_input = ctx.payload.get("tool_input") or {}
        response = str(ctx.payload.get("tool_response", ""))
        entry = {
            "session": ctx.core.get("session_id", ""),
            "project": ctx.project,
            "tool": short,
            # "found": did memory actually hold something? Distinguishes a
            # gate miss (it was there, gate stayed quiet) from a capture gap
            # (the model went looking for knowledge nobody ever stored).
            "found": bool(response.strip())
            and "not found" not in response.lower()
            and not response.startswith("Error"),
        }
        if "model" in tool_input and "name" in tool_input:
            entry["target"] = f"{tool_input['model']}/{tool_input['name']}"
        elif "sparql" in tool_input:
            entry["sparql"] = str(tool_input["sparql"])[:150]
        elif "text" in tool_input:
            entry["target"] = str(tool_input["text"])
        append_jsonl("explicit-recalls.jsonl", entry)
        return None  # telemetry only — never injects
