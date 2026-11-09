"""What grounding finds: the nodes, edges, values, dates and groups a question names."""

from dataclasses import dataclass, field

from ..vocabulary import DateField, Entity, Group, Relation, Value


@dataclass
class Node:
    kind: str                 # "var" | "anchor"
    type: str
    pos: float                # word index, for word-order rules
    entity: Entity | None = None
    match_terms: list[str] = field(default_factory=list)
    implicit: bool = False    # a var only a relation's end implied, not named
    either: list[Entity] = field(default_factory=list)   # anchors: the records "or" adds

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
    negated: bool = False
    style: str = "verb"
    path: str = ""                                    # the backend's name for the link
    qualifier: tuple[str, str, str] | None = None     # (field, value, label) on the same tile
    group: str = ""                                   # that tile's nodegroup


def _edge(rel: Relation, pos: float, **kw) -> Edge:
    return Edge(rel.name, pos, style=rel.style, path=rel.path or rel.name,
                qualifier=rel.qualifier, group=rel.group, **kw)


@dataclass
class ValueMatch:
    phrase: str
    pos: float
    candidates: list[Value]   # every field this phrase can be a value of
    negated: bool = False
    words: list[int] = field(default_factory=list)
    either: list["ValueMatch"] = field(default_factory=list)   # the values "or" adds


@dataclass
class DateGround:
    phrase: str
    pos: float
    lo: str | None
    hi: str | None
    fields: list[DateField]   # the field the words picked, else every candidate
    negated: bool = False
    picked: float | None = None   # where the word that picked the field is


@dataclass
class NearGround:
    """"near X" / "within 5 km of X": X is measured from, not linked to."""
    phrase: str
    pos: float
    km: float
    unit: str = "km"                  # as asked: "km" | "miles"
    entity: Entity | None = None      # the named record after the phrase
    negated: bool = False


@dataclass
class GroupGround:
    """A phrase naming one tile of a nodegroup, and what its clause says of it."""
    phrase: str
    pos: float
    words: list[int]                                  # the phrase's word indices
    candidates: list[tuple[Group, tuple[Value, ...]]]  # each group it names, with the values it sets
    group: Group | None = None                        # the one chosen
    values: list[Value] = field(default_factory=list)
    date: DateGround | None = None
    negated: bool = False


@dataclass
class NameGround:
    """A record-name condition the question spells out: "whose name starts with Cat"."""
    term: str                 # as typed
    mode: str                 # "prefix" | "word"
    pos: float
    negated: bool = False


@dataclass
class Grounding:
    text: str = ""
    wh: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    values: list[ValueMatch] = field(default_factory=list)
    dates: list[DateGround] = field(default_factory=list)
    groups: list[GroupGround] = field(default_factory=list)
    near: NearGround | None = None
    recent: bool = False
    contains: str | None = None
    contains_negated: bool = False
    name: NameGround | None = None
    negation_unplaced: str = ""   # a negator with nothing after it to negate
    subject: Node | None = None
    anchors: list[Node] = field(default_factory=list)
    coverage: float = 0.0
    uncovered: list[str] = field(default_factory=list)
    refuse: str = ""          # out-of-grammar reason
    field_of: Edge | None = None   # a link to a named record that can't say what it
                                   # points at: the record's own field may be meant
    count: bool = False       # "how many …"
    group: Edge | None = None # "by county": count per record this link points at
    group_order: str = ""     # "most" | "fewest": only the top or bottom one
    loose: str = ""           # relation phrases dropped to list a type
    notes: list[str] = field(default_factory=list)
    suggestions: list[tuple[str, list[str]]] = field(default_factory=list)   # (words, did-you-mean)
    # phrases no layer placed, for the learning log (ceist.learn.from_grounding):
    # {"phrase", "model", "slot", "options": [{"node", "qualifier", "end_node", "label"}]}
    unplaced: list[dict] = field(default_factory=list)

    @property
    def anchor(self) -> Node | None:
        return self.anchors[0] if self.anchors else None

    def vars(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "var"]
