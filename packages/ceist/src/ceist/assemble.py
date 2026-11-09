"""Schema assembly: a question's pieces put together by what the schema allows, not by
word order, and answered only when exactly one reading fits. After PRECISE (PRIOR-ART.md)."""

from dataclasses import replace
from itertools import product

from .ground import Grounding, Node, pieces
from .ground.model import _edge
from .ground.scan import Scan
from .ground.wire import _check_anchors, _or, _scope_negations, _subject
from .narrate import narrate
from .plan import Interpretation, _finish, _unplaced
from .text import terms_pos
from .vocabulary import Relation, Vocabulary

# words that shape a sentence but name nothing, ignored rather than placed: PRECISE's
# "syntactic markers". Function words only; an unknown content word still refuses.
FILLER = frozenset({"their", "its", "his", "her", "same", "through", "someone", "somebody",
                    "anyone", "anybody", "these", "those", "each", "ones",
                    "who", "whom", "whose", "which"})     # mid-sentence: relative pronouns
MAX_READINGS = 256


def interpret(vocab: Vocabulary, text: str, today=None, matcher=None) -> Interpretation:
    s, answers, outs = assemble(vocab, text, today, matcher)
    if len(answers) == 1:
        return next(iter(answers.values()))
    if answers:
        said = [narrate(_meaning(o), forms=False) for o in answers.values()]
        s.g.suggestions.append(("the question", said))
        return Interpretation(s.g, refused=f"{len(said)} readings fit; did you mean "
                              + " or ".join(f"'{x}'" for x in said) + "?")
    return outs[0] if outs else Interpretation(s.g, refused=_none(s))


def assemble(vocab: Vocabulary, text: str, today=None, matcher=None, filler=FILLER):
    """The question's pieces, its distinct answering readings by their canonical
    narration (PRECISE's equivalence check), and every reading's interpretation."""
    s = pieces(vocab, text, today, matcher, fit=False, filler=filler)
    if _or(s):
        return s, {}, [_finish(vocab, s.g)]
    found = readings(s)
    if found is None:
        return s, {}, [Interpretation(s.g, refused=f"more than {MAX_READINGS} readings fit; "
                                                   "ask one thing at a time")]
    outs = [_finish(vocab, g) for g in found]
    answers = {}
    for o in outs:
        if not o.refused:
            answers.setdefault(_key(o), o)
    return s, answers, outs


def _meaning(o: Interpretation):
    return o.plan or o.detail


def _key(o: Interpretation) -> str:
    if o.direct is not None:
        return f"record {o.direct.id}"
    return narrate(_meaning(o), canonical=True)


def _none(s: Scan) -> str:
    g = s.g
    if g.uncovered:
        return _unplaced(g)
    types = " and ".join(sorted({n.type for n in g.nodes})) or "nothing named"
    forms = ", ".join(f"'{e.form}'" for e in g.edges)
    return f"no reading fits the schema: {forms or 'no link'} can't join {types}"


def readings(s: Scan) -> list[Grounding] | None:
    """Every assignment of pieces to schema elements the schema allows: each link phrase
    to one of its relations between two pieces (either way round), variables no phrase
    links joined by any one relation, and each value and date to a variable whose type
    holds that field. None past the bound."""
    g = s.g
    every = s.vocab.relations()       # by name, s.relations keeps one of each name's variants
    options = [_link_options(s, e, every) for e in g.edges]
    out: list[Grounding] = []
    # ponytail: plain enumeration, bounded by MAX_READINGS; a max-flow matcher as
    # PRECISE has if questions ever carry more than a handful of pieces
    for combo in product(*options):
        implicit: dict[str, Node] = {}
        notes = list(g.notes)

        def end(x, pos):
            if isinstance(x, Node):
                return x
            if x not in implicit:
                implicit[x] = Node("var", x, pos + 0.5, var=f"?v{len(s.seen) + len(implicit)}",
                                   implicit=True)
            return implicit[x]

        edges = []
        for e, option in zip(g.edges, combo):
            if option is None:
                notes.append(f"'{e.form}' set aside: no relation it names joins what is named")
                continue
            rel, a, b = option
            src, dst = end(a, e.pos), end(b, e.pos)
            edges.append(_edge(rel, e.pos, form=e.form, source=src, target=dst))
            notes.append(f"'{e.form}' → {rel.name}: {src.type} → {dst.type}")
        if any(sum(n is x for e in edges for x in (e.source, e.target)) > 1 for n in g.anchors):
            continue                  # a record is one piece: it ends one link, not two
        nodes = g.nodes + list(implicit.values())
        chosen = {o[0].name: o[0] for o in combo if o is not None}
        for join in _joins(s, nodes, edges, every):
            wired = replace(g, nodes=nodes, edges=edges + join, notes=list(notes))
            for j in join:
                wired.notes.append(f"{j.source.type} → {j.target.type} joined by {j.relation}")
            _check_anchors(wired, {**s.relations, **chosen})
            _subject(replace(s, g=wired))
            for values, dates in product(product(*(_value_options(v, wired) for v in g.values)),
                                         product(*(_date_options(d, wired) for d in g.dates))):
                r = replace(wired, values=list(values), dates=list(dates),
                            groups=[replace(x) for x in g.groups], notes=list(wired.notes),
                            near=replace(g.near) if g.near else None,
                            name=replace(g.name) if g.name else None)
                _scope_negations(replace(s, g=r))
                out.append(r)
                if len(out) > MAX_READINGS:
                    return None
    return out


def _link_options(s: Scan, e, every: list[Relation]) -> list:
    """(relation, source, target) for each way the phrase can join two named pieces. With
    one piece or none named, a missing end is an implicit variable given as its type.
    None: set aside, as a bare function word ("in") that joins nothing named is."""
    names = s.sharing.get(e.form, [e.relation])
    rels = [r.said_as(e.form) for r in every if r.name in names]
    nodes = s.g.nodes
    both = [(r, a, b) for r in rels for a in nodes for b in nodes
            if a is not b and r.joins(a.type, b.type)
            and (a.type != b.type or _in_order(s, e, a, b) == (a, b))]
    if both:
        return both
    if len(nodes) >= 2:
        # "which monuments are in Belfast", Belfast a Monument: not set aside, it would
        # answer with the record itself
        same = any(a.type == v.type for a in s.g.anchors for v in s.g.vars())
        return [] if same or terms_pos(e.form) else [None]
    out = []
    for r in rels:
        # an implicit end opposite a variable says something only when the link has a
        # role: "architects", "surveyed by"; "in County Nowhere" must not become "in any Site"
        ends = nodes if r.qualifier else s.g.anchors
        for x in ends:
            leads = x.pos <= e.pos and not _after_as(s, e)
            out += [(r, x, t) for t in sorted(r.targets(x.type))
                    if r.joins(x.type, t) and (t != x.type or leads)]
            out += [(r, t, x) for t in sorted(r.domain)
                    if r.joins(t, x.type) and (t != x.type or not leads)]
        if not nodes and r.qualifier:
            out += [(r, a, b) for a in sorted(r.domain) for b in sorted(r.targets(a))]
    return out


def _in_order(s: Scan, e, a: Node, b: Node) -> tuple[Node, Node]:
    """Two pieces of one type as source and target of the link between them, by word
    order as _assign_edges reads it: the schema allows either way round."""
    before = sorted((n for n in (a, b) if n.pos <= e.pos), key=lambda n: n.pos)
    if len(before) == 2:
        near, far = before[1], before[0]
        return (far, near) if _after_as(s, e) else (near, far)   # "X as father": X the target
    if before:
        return (a, b) if before[0] is a else (b, a)
    return (a, b) if a.pos > b.pos else (b, a)                 # both after: the farther leads


def _after_as(s: Scan, e) -> bool:
    return e.pos >= 1 and s.words[int(e.pos) - 1].text == "as"


def _joins(s: Scan, nodes: list[Node], edges: list, every: list[Relation]) -> list[list]:
    """The joins that connect what no phrase links: none needed, or one relation between
    a variable in each of two parts, each such relation a reading. A record named beside
    a type with no link at all stays loose ("linked to or from"), as without assembly."""
    groups: list[list[Node]] = []
    for n in nodes:
        near = [grp for grp in groups if any(_linked(edges, n, m) for m in grp)]
        merged = [n] + [m for grp in near for m in grp]
        groups = [grp for grp in groups if not any(grp is x for x in near)] + [merged]
    if len(groups) <= 1 or (not edges and len(nodes) == 2 and s.g.anchor is not None):
        return [[]]
    if len(groups) != 2:
        return []
    left, right = groups
    plain = [r for r in every if not r.qualifier]
    return [[_edge(r, (a.pos + b.pos) / 2, form=r.forms[0] if r.forms else "",
                   source=a, target=b)]
            for r in plain for x in left for y in right for a, b in ((x, y), (y, x))
            if a.kind == "var" and b.kind == "var" and a.type in r.domain
            and b.type in r.range]


def _linked(edges: list, a: Node, b: Node) -> bool:
    return any({id(e.source), id(e.target)} == {id(a), id(b)} for e in edges)


def _value_options(vm, g: Grounding) -> list:
    """The value on each variable whose type holds one of its fields: one choice each.
    plan._attach_values reads it as any of that type's fields that hold it."""
    out = []
    for n in g.vars():
        def on(m):
            return replace(m, candidates=[replace(c, owners=frozenset({n.type}))
                                          for c in m.candidates
                                          if not c.owners or n.type in c.owners])
        if on(vm).candidates:
            out.append(replace(on(vm), either=[on(x) for x in vm.either]))
    return out or [replace(vm)]


def _date_options(dm, g: Grounding) -> list:
    """The date on each variable that has one of its fields."""
    out = []
    for n in g.vars():
        fits = [replace(f, owners=frozenset({n.type})) for f in dm.fields
                if not f.owners or n.type in f.owners]
        if fits:
            out.append(replace(dm, fields=fits))
    return out or [replace(dm)]
