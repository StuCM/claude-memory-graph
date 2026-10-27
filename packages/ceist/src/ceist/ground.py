"""Grounding: which words of a question name which parts of the vocabulary.

Pipeline: shape → relations (longest phrase first, on the raw text, so
"works on" keeps its stopword) → controlled values ("listed", "active") →
type nouns, modifiers and hints → implied types (who → Person) → one named
anchor (only a name-term hit may bind; never a guess) → one leftover word as a
text filter → coverage → wire the relations to their ends.

The result says what was understood and how sure (coverage); plan.py turns
it into a query plan, and refuses rather than guesses when it is thin.
"""

import re
from dataclasses import dataclass, field

from .text import terms_pos
from .vocabulary import Entity, Relation, Value, Vocabulary

WH = {"what", "which", "who", "whom", "whose", "why", "when", "how", "where"}
AUX = {"is", "are", "was", "were", "do", "does", "did", "has", "have", "had",
       "can", "could", "should", "would", "any"}
RECENT = {"recent", "recently", "latest", "newest"}
# commands that ask a question: "list all decisions", "show me patterns"
IMPERATIVE = {"list", "show", "find", "give", "tell", "name"}
# words that shape a question but name nothing: never a text filter
FILLER = {"me", "all", "every", "please", "made", "make", "been", "exist", "exists",
          "there", "we", "us", "our", "i", "you", "about", "ever", "currently", "have",
          "got", "keep", "kept"}
# "what do we know about X", "tell me about X": the answer is X itself, and the
# verb ("know") must not ground as a relation
ABOUT_RE = re.compile(r"^\s*(?:what\s+(?:do|does|did)\s+(?:we|i|you)\s+(?:know|have|remember)"
                      r"|tell\s+me|what(?:'s| is)\s+(?:known|there))\s+about\s+", re.I)
WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")
MAX_EDGES = 2
MAX_VARS = 2


@dataclass
class Node:
    kind: str                 # "var" | "anchor"
    type: str
    pos: float                # word index, for word-order rules
    var: str = ""             # variable name (vars)
    entity: Entity | None = None
    match_terms: list[str] = field(default_factory=list)

    # conveniences for backends that address anchors directly
    @property
    def name(self) -> str:
        return self.entity.name if self.entity else ""

    @property
    def id(self) -> str:
        return self.entity.id if self.entity else ""


@dataclass
class Edge:
    relation: str
    pos: float
    form: str = ""            # the phrase that grounded it
    source: Node | None = None
    target: Node | None = None


@dataclass
class ValueMatch:
    phrase: str
    pos: float
    candidates: list[Value]   # every field this phrase can be a value of


@dataclass
class Grounding:
    text: str = ""
    wh: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    values: list[ValueMatch] = field(default_factory=list)
    recent: bool = False
    contains: str | None = None
    subject: Node | None = None
    anchor: Node | None = None
    coverage: float = 0.0
    uncovered: list[str] = field(default_factory=list)
    refuse: str = ""          # out-of-grammar reason
    count: bool = False       # "how many …"
    loose: str = ""           # relation phrases dropped to list a type
    about: bool = False       # "what do we know about X"
    notes: list[str] = field(default_factory=list)

    def vars(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "var"]


def is_question(text: str) -> bool:
    stripped = text.strip()
    words = WORD_RE.findall(stripped.lower())
    return bool(stripped.endswith("?")
                or (words and (words[0] in WH or words[0] in AUX or words[0] in IMPERATIVE)))


def _phrase_spans(raw: str, phrases: list[tuple[str, object]], taken: list[tuple[int, int]]):
    """Longest phrase first; each match must not overlap an earlier one."""
    for phrase, payload in sorted(phrases, key=lambda x: -len(x[0])):
        m = re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", raw)
        if not m or any(m.start() < e and m.end() > s for s, e in taken):
            continue
        taken.append((m.start(), m.end()))
        yield phrase, payload, m


def ground(vocab: Vocabulary, text: str) -> Grounding:
    g = Grounding(text=text)
    raw = text.lower()
    words = [(i, m.start(), m.end(), m.group())
             for i, m in enumerate(WORD_RE.finditer(raw))]
    terms = {w for _, w in terms_pos(text)}
    consumed: set[int] = set()

    def parts_of(word: str) -> set[str]:
        # raw words like "memory-graph" must meet terms ("memory", "graph")
        return {p for p in re.split(r"[^a-z0-9]+", word) if p} & terms

    def consume_span(start: int, end: int) -> float:
        first = None
        for i, s, e, _w in words:
            if s >= start and e <= end:
                consumed.add(i)
                first = i if first is None else first
        return float(first if first is not None else 0)

    if words and (words[0][3] in WH or words[0][3] in AUX or words[0][3] in IMPERATIVE):
        if words[0][3] in WH:
            g.wh = words[0][3]
        elif words[0][3] in IMPERATIVE:
            g.wh = "what"                 # "list decisions" = "what decisions"
        consumed.add(0)
    if len(words) > 1 and words[0][3] == "how" and words[1][3] in ("many", "much"):
        g.count, g.wh = True, "what"      # not "how" → its implied type
        consumed.add(1)
        g.notes.append("'how many' → count")
    about = ABOUT_RE.match(text)
    if about:
        g.about = True
        consumed.update(i for i, s, _e, _w in words if s < about.end())
        g.notes.append("'… about X' → X itself")

    # ── relations
    relations = {r.name: r for r in vocab.relations()}
    taken: list[tuple[int, int]] = []
    matched: set[str] = set()
    forms = [(f, r.name) for r in relations.values() for f in r.forms]
    for form, rel, m in ([] if g.about else _phrase_spans(raw, forms, taken)):
        if rel in matched:
            taken.remove((m.start(), m.end()))
            continue
        matched.add(rel)
        g.edges.append(Edge(rel, consume_span(m.start(), m.end()), form=form))
        g.notes.append(f"'{form}' → relation {rel}")
    g.edges.sort(key=lambda e: e.pos)

    # ── controlled values ("listed", "active")
    by_phrase: dict[str, list[Value]] = {}
    for v in vocab.values():
        by_phrase.setdefault(v.phrase, []).append(v)
    for phrase, cands, m in _phrase_spans(raw, list(by_phrase.items()), taken):
        g.values.append(ValueMatch(phrase, consume_span(m.start(), m.end()), cands))
        g.notes.append(f"'{phrase}' → value of "
                       + " / ".join(sorted({c.field for c in cands})))

    # ── type nouns, modifiers, hints
    nouns, hints = vocab.type_words(), vocab.hint_words()
    seen: dict[str, Node] = {}

    def add_var(t: str, pos: float, why: str) -> Node:
        node = Node("var", t, pos, var=f"?v{len(seen)}")
        seen[t] = node
        g.nodes.append(node)
        g.notes.append(f"{why} → typed variable {node.var} : {t}")
        return node

    for i, _s, _e, w in words:
        if i in consumed:
            continue
        if w in nouns:
            if nouns[w] not in seen:
                add_var(nouns[w], float(i), f"'{w}'")
            consumed.add(i)
        elif w in RECENT:
            g.recent = True
            consumed.add(i)
            g.notes.append(f"'{w}' → most recent first")
        elif w in hints:
            consumed.add(i)
            if hints[w] not in seen:
                add_var(hints[w], float(i), f"'{w}' implies")
        elif w in AUX or w in FILLER:
            consumed.add(i)

    implied = vocab.implied_types()
    if g.wh in implied and implied[g.wh] not in seen:
        add_var(implied[g.wh], 0.0, f"'{g.wh}' implies")

    # ── the anchor: leftover terms against the records — only a NAME-term
    # hit may bind, never a guess
    leftovers = [(i, w) for i, _s, _e, w in words if i not in consumed and parts_of(w)]
    if leftovers:
        left = set().union(*(parts_of(w) for _i, w in leftovers))
        ranked = vocab.rank_entities(left)
        if ranked:
            score, top = ranked[0]
            # a record NAMED exactly what was asked beats one that mentions it
            exact = next((e for s, e in ranked[1:]
                          if s > 0 and e.name_terms == left and top.name_terms != left), None)
            if exact is not None:
                g.notes.append(f"anchor exact name: {exact.type} '{exact.name}' "
                               f"preferred over {top.type} '{top.name}'")
                score, top = next(s for s, e in ranked if e is exact), exact
            # role fit: the grounded relations say what TYPE the anchor should
            # be; a near-tied candidate of that type beats a lexical tie
            expected = {t for e in g.edges if e.relation in relations
                        for t in relations[e.relation].domain | relations[e.relation].range}
            if expected and top.type not in expected:
                for s, e in ranked[1:]:
                    if s >= 0.75 * score and e.type in expected and left & e.name_terms:
                        g.notes.append(f"anchor role fit: {e.type} '{e.name}' "
                                       f"preferred over {top.type} '{top.name}'")
                        score, top = s, e
                        break
            if score > 0 and left & top.name_terms:
                hit = left & top.terms
                pos = min(i for i, w in leftovers if parts_of(w) & hit)
                g.anchor = Node("anchor", top.type, float(pos), entity=top,
                                match_terms=sorted(left & top.name_terms))
                g.nodes.append(g.anchor)
                consumed.update(i for i, w in leftovers if parts_of(w) <= hit)
                g.notes.append(f"{'/'.join(g.anchor.match_terms)} → anchor "
                               f"{top.type or 'Concept'} '{top.name}'")

    # ── one leftover word → a text filter; more stay uncovered
    remaining = [(i, w) for i, _s, _e, w in words if i not in consumed and parts_of(w)]
    if len(remaining) == 1:
        i, w = remaining[0]
        g.contains = sorted(parts_of(w))[0]
        consumed.add(i)
        g.notes.append(f"'{w}' → text filter")

    covered = set().union(set(), *(parts_of(w) for i, _s, _e, w in words if i in consumed))
    g.coverage = len(covered & terms) / len(terms) if terms else 0.0
    g.uncovered = sorted(terms - covered)

    # ── grammar caps + wiring the relations to their ends
    if len(g.edges) > MAX_EDGES:
        g.refuse = f"{len(g.edges)} relations — the grammar caps at {MAX_EDGES}"
        return g
    _assign_edges(g, relations, seen)
    if (g.refuse.startswith("cannot resolve") and g.anchor is None
            and any(n.kind == "var" for n in g.nodes)):
        # "what technologies do we use?": the relation has no second end, but
        # the question still names what it wants — list that
        dropped = ", ".join(f"'{e.form}'" for e in g.edges)
        g.edges, g.refuse = [], ""
        g.notes.append(f"could not place {dropped}; listing the type instead")
        g.loose = dropped
    if len(g.vars()) > MAX_VARS:
        g.refuse = f"{len(g.vars())} typed variables — the grammar caps at {MAX_VARS}"
        return g
    _imply_join(g, relations)

    # the subject = what the question asks for
    if g.wh in implied:
        g.subject = seen.get(implied[g.wh])
    if g.subject is None:
        explicit = sorted(g.vars(), key=lambda n: n.pos)
        g.subject = explicit[0] if explicit else None
    return g


def _imply_join(g: Grounding, relations: dict[str, Relation]) -> None:
    """Two types named with no phrase joining them ("sites with buildings
    designed by X"): if exactly ONE relation in the vocabulary connects the
    two types, that is the join. Ambiguity (or none) leaves them unjoined —
    never a guess."""
    pair = g.vars()
    if len(pair) != 2:
        return
    a, b = pair
    if any((e.source is a and e.target is b) or (e.source is b and e.target is a)
           for e in g.edges):
        return
    candidates = [(r, a, b) for r in relations.values() if a.type in r.domain and b.type in r.range]
    candidates += [(r, b, a) for r in relations.values() if b.type in r.domain and a.type in r.range]
    if len(candidates) != 1:
        if candidates:
            g.notes.append(f"{a.type} and {b.type} could be joined by "
                           f"{', '.join(sorted(c[0].name for c in candidates))}; not guessing")
        return
    rel, src, dst = candidates[0]
    g.edges.append(Edge(rel.name, (a.pos + b.pos) / 2, form=rel.forms[0] if rel.forms else "",
                        source=src, target=dst))
    g.notes.append(f"{src.type} → {dst.type} joined by {rel.name} (the only relation between them)")


def _assign_edges(g: Grounding, relations: dict[str, Relation], seen: dict) -> None:
    """Word order picks each relation's neighbours; domain/range orient it and
    fill a missing end (with an implicit typed variable when needed)."""
    for edge in g.edges:
        rel = relations.get(edge.relation)
        dom = set(rel.domain) if rel else set()
        rng = set(rel.range) if rel else set()
        parts = sorted(g.nodes, key=lambda n: n.pos)
        left = next((n for n in reversed(parts) if n.pos < edge.pos), None)
        right = next((n for n in parts if n.pos > edge.pos), None)

        def fill(hints: set, present: Node | None) -> Node | None:
            cand = next((n for n in parts if n is not present and n.type in hints), None)
            if cand is None and hints:
                t = sorted(hints)[0]
                if t in seen:
                    # never join a relation to itself — a relation whose only
                    # type-fitting candidate is its OTHER end is misgrounded
                    existing = seen[t]
                    return existing if existing is not present else None
                cand = Node("var", t, edge.pos + 0.5, var=f"?v{len(seen)}")
                seen[t] = cand
                g.nodes.append(cand)
                g.notes.append(f"relation {edge.relation} → implicit {t} variable {cand.var}")
            return cand

        if left is None:
            left = fill(dom, right)
        if right is None:
            right = fill(rng, left)
        if left is None or right is None:
            g.refuse = f"cannot resolve both ends of relation {edge.relation}"
            return
        straight = (left.type in dom) + (right.type in rng)
        swapped = (right.type in dom) + (left.type in rng)
        edge.source, edge.target = (right, left) if swapped > straight else (left, right)
