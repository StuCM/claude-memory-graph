"""memory_search — the fuzzy entry-point finder.

Fixes the exact-name cliff: memory_recall needs an exact model+name, so a
model that guesses "pyoxigraph choice" for a node named "Use pyoxigraph
over rdflib" silently finds nothing. Search matches free text against the
graph's whole matching surface — names, concept labels, aliases, and
property text — and returns ranked entry points to recall from.

Deliberately the same machinery as the ambient gate (corpus, IDF, phrase
and coverage evidence): one matcher, two consumers — the gate decides
whether to speak; search answers when asked. This is also the primitive
the write-time duplicate guard and distill's two-pass dedup converge on.

Search finds doors; memory_recall explores rooms — output says so.
"""

from claude_hook_kit import terms_pos

from ..gate.recall import _bigrams, _corpus, _idf, _score
from ..store import MemoryStore


def handle(store: MemoryStore, text: str, model: str | None = None, limit: int = 5) -> str:
    q_pos = terms_pos(text)
    q = {w for _, w in q_pos}
    if not q:
        return "No searchable terms in query."

    docs = _corpus(store, include_concepts=True)
    if model:
        docs = [d for d in docs if d["model"] == model]
    if not docs:
        return "No matches." if model is None else f"No matches for model {model}."

    idf = _idf(docs)
    q_bi = _bigrams(q_pos)
    ranked = sorted(
        ((s, d) for d in docs if (s := _score(q, d, idf, q_bi)) > 0),
        key=lambda x: x[0], reverse=True,
    )[:max(1, limit)]

    if not ranked:
        return f"No matches for '{text}'."
    lines = []
    for _s, d in ranked:
        desc = f" — {d['desc'][:120]}" if d["desc"] else ""
        lines.append(f"- {d['model'] or '?'} '{d['name']}'{desc}")
    return "\n".join(lines) + "\n(entry points — memory_recall one for its neighbourhood)"
