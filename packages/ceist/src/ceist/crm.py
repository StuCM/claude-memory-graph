"""CIDOC-CRM, as Arches graphs carry it: each node's class and the property into
it, decoded into role hints (for the vocabulary pipeline's prompts) and into a
link's range (for fitting a link to the types a question names)."""

import re

from . import bundle as _bundle

# (role, CRM classes, CRM properties): a node's role from its own class, else the
# property into it; a literal (a note, a number) from the class of the node it describes
ROLES = [
    ("date", {"E52", "E61", "E49", "E50"}, {"P4", "P82", "P82a", "P82b", "P78", "P81", "P81a", "P81b"}),
    ("actor", {"E39", "E21", "E74", "E40"}, {"P14", "P11", "P49", "P51", "P52", "P75", "P107"}),
    ("place", {"E53", "E27"}, {"P53", "P7", "P89", "P55", "P156", "P161", "P74"}),
    ("name", {"E41", "E35", "E82"}, {"P1", "P102"}),
    ("identifier", {"E42"}, {"P48"}),
    ("unit", {"E58"}, {"P91"}),
    ("type", {"E55", "E57", "E56"}, {"P2", "P45", "P72", "P141", "P42", "P32", "P126"}),
    ("description", {"E33", "E73", "E62"}, {"P3"}),
]
CRM_PROPERTIES = {   # property: (forward label, inverse label)
    "P1": ("is identified by", "identifies"), "P2": ("has type", "is type of"),
    "P4": ("has time-span", "is time-span of"), "P7": ("took place at", "witnessed"),
    "P12": ("occurred in the presence of", "was present at"),
    "P14": ("carried out by", "performed"), "P46": ("is composed of", "forms part of"),
    "P53": ("has former or current location", "is former or current location of"),
    "P74": ("has current or former residence", "is current or former residence of"),
    "P75": ("possesses", "is possessed by"), "P89": ("falls within", "contains"),
    "P108": ("has produced", "was produced by"), "P126": ("employed", "was employed in"),
    "P129": ("is about", "is subject of"), "P140": ("assigned attribute to", "was attributed by"),
    "P148": ("has component", "is component of"), "P67": ("refers to", "is referred to by"),
}
_CODE = re.compile(r"^([A-Z]+\d+[a-z]*)")


def crm_code(uri: str | None) -> str:
    """'http://…/cidoc-crm/P82a_begin_of_the_begin' → 'P82a'."""
    local = (uri or "").rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    m = _CODE.match(local)
    return m.group(1) if m else ""


def _role(cls: str, prop: str, parent: str, datatype: str) -> str:
    """A literal has no class of its own: it is the name, identifier or note of its parent."""
    base = prop[:-1] if prop.endswith("i") else prop
    for role, classes, props in ROLES:
        if cls in classes or (not cls and role in ("name", "identifier") and parent in classes):
            return role
    for role, classes, props in ROLES:
        if base in props:
            return role
    for role, classes, _ in ROLES:
        if not cls and parent in classes:
            return role
    if datatype in _bundle.DATE:
        return "date"
    return "link" if datatype.startswith("resource-instance") else ""


def crm_roles(graph: dict) -> dict[str, dict]:
    """Each node's role hint from its CIDOC-CRM class and the property into it:
    {alias: {"role", "crm", "reverse"?, "pairs_with"?}}. Deterministic; the LLM
    confirms or corrects it."""
    g = graph["graph"][0] if "graph" in graph else graph
    nodes = {n["nodeid"]: n for n in g["nodes"]}
    parent = {e["rangenode_id"]: e for e in g.get("edges", [])}
    out = {}
    for n in g["nodes"]:
        alias = n.get("alias")
        if not alias or n["datatype"] == "semantic":
            continue
        edge = parent.get(n["nodeid"]) or {}
        up = nodes.get(edge.get("domainnode_id")) or {}
        cls = crm_code(n.get("ontologyclass"))
        prop = crm_code(n.get("parentproperty") or edge.get("ontologyproperty"))
        up_cls = crm_code(up.get("ontologyclass"))
        role = _role(cls, prop, up_cls, n["datatype"])
        if not role:
            continue
        hint = {"role": role, "crm": " ".join(x for x in (cls, "via " + prop if prop else "",
                                                           "in " + up_cls if up_cls else "") if x)}
        base, inverse = (prop[:-1], True) if prop.endswith("i") else (prop, False)
        if base in CRM_PROPERTIES:
            hint["reverse"] = CRM_PROPERTIES[base][0 if inverse else 1]
        if prop == "P82a":
            end = next((m for m in g["nodes"] if crm_code(m.get("parentproperty")) == "P82b"
                        and (parent.get(m["nodeid"]) or {}).get("domainnode_id") == up.get("nodeid")),
                       None)
            if end and end.get("alias"):
                hint["pairs_with"] = end["alias"]
        out[alias] = hint
    return out


# Enough of the class hierarchy to tell a known clash: each class with its parents
PARENTS = {
    "E18": (), "E19": ("E18",), "E20": ("E19",), "E21": ("E20", "E39"), "E22": ("E19", "E24"),
    "E24": ("E18",), "E25": ("E24", "E26"), "E26": ("E18",), "E27": ("E26",),
    "E39": (), "E74": ("E39",), "E40": ("E74",),
    "E28": (), "E89": ("E28",), "E90": ("E28",), "E73": ("E89", "E90"), "E33": ("E73",),
    "E31": ("E73",), "E36": ("E73",), "D1": ("E73",),
    "E53": (),
    "E2": (), "E4": ("E2",), "E5": ("E4",), "E7": ("E5",),
}
# a link node with no class of its own: the range of the property into it (P14 → E39 Actor)
_ROLE_RANGE = {"actor": "E39", "place": "E53"}


def _kinds(cls: str) -> set[str]:
    out, todo = set(), [cls]
    while todo:
        c = todo.pop()
        if c not in out:
            out.add(c)
            todo += PARENTS.get(c, ())
    return out


def clash(a: str, b: str) -> bool:
    """Neither class is a kind of the other. A class outside PARENTS never clashes."""
    if a not in PARENTS or b not in PARENTS:
        return False
    return a not in _kinds(b) and b not in _kinds(a)


def root_class(graph: dict) -> str:
    g = graph["graph"][0] if "graph" in graph else graph
    return next((crm_code(n.get("ontologyclass")) for n in g["nodes"] if n.get("istopnode")), "")


def link_ranges(graph: dict) -> dict[str, str]:
    """{link alias: the class it points at}: its own class, else its property's range."""
    g = graph["graph"][0] if "graph" in graph else graph
    prop_of = {e["rangenode_id"]: e.get("ontologyproperty") for e in g.get("edges", [])}
    out = {}
    for n in g["nodes"]:
        if not (n.get("alias") and n["datatype"].startswith("resource-instance")):
            continue
        prop = crm_code(n.get("parentproperty") or prop_of.get(n["nodeid"]))
        cls = crm_code(n.get("ontologyclass")) or _ROLE_RANGE.get(_role("", prop, "", ""), "")
        if cls:
            out[n["alias"]] = cls
    return out


def is_a(cls: str, kind: str) -> bool:
    return kind in _kinds(cls)


def chains(graph: dict) -> dict[str, list[str]]:
    """{alias: [root class, property, class, …, property, its class]}: each node's
    CIDOC-CRM path down from the root ("-" for a node with no class)."""
    g = graph["graph"][0] if "graph" in graph else graph
    nodes = {n["nodeid"]: n for n in g["nodes"]}
    parent = {e["rangenode_id"]: e for e in g.get("edges", [])}
    out = {}
    for n in g["nodes"]:
        if not n.get("alias"):
            continue
        tokens, m = [crm_code(n.get("ontologyclass")) or "-"], n
        while m["nodeid"] in parent and parent[m["nodeid"]]["domainnode_id"] in nodes:
            e = parent[m["nodeid"]]
            tokens.append(crm_code(m.get("parentproperty") or e.get("ontologyproperty")) or "-")
            m = nodes[e["domainnode_id"]]
            tokens.append(crm_code(m.get("ontologyclass")) or "-")
        out[n["alias"]] = tokens[::-1]
    return out


def is_controlled(node: dict) -> bool:
    return "concept" in node["datatype"] or node["datatype"] == "reference"


_TIME_SPAN_ENDS = {"P82a": "P82b", "P82": None}
_ENDS = ("P82b", "P81b", "P3")


def keyed(graph: dict) -> dict[str, tuple[str, list[str]]]:
    """{alias: (kind, tokens)} for each node the ontology layer can phrase: a link or field
    by its CRM path with its class; a date's begin by the path down to its event's time-span
    ("… O18i E11 P4"), and an end by the path to that end ("… P93i E81 P4 E52 P82b"), so it
    never takes its begin's phrasings.
    A plain (not controlled) field is kind "field", so a "property" path, written for a
    controlled one, never reaches a note beside it."""
    g = graph["graph"][0] if "graph" in graph else graph
    paths = chains(g)
    out = {}
    for n in g["nodes"]:
        tokens, kind = paths.get(n.get("alias") or ""), _bundle.kind_of(n)
        if not tokens or n["datatype"] == "semantic":
            continue
        if kind == "property" and not is_controlled(n):
            kind = "field"
        if kind == "date":
            if len(tokens) < 3 or tokens[-3] != "E52" or tokens[-2] not in (*_TIME_SPAN_ENDS, *_ENDS):
                continue
            tokens = tokens[:-3] if tokens[-2] in _TIME_SPAN_ENDS else tokens[:-1]
        out[n["alias"]] = (kind, tokens)
    return out


def ontology_entries(graph: dict, ontology: dict) -> list[dict]:
    """The ontology layer's entries for one graph: each node `keyed` gives a path gets the
    phrases of every ontology path of its kind its CRM path ends with. A date carries its
    span's end when the begin keys it.
    "who" before a date's phrase ("who made") names the one actor (P14) of that event."""
    g = graph["graph"][0] if "graph" in graph else graph
    paths = chains(g)
    up = {e["rangenode_id"]: e["domainnode_id"] for e in g.get("edges", [])}
    keys = keyed(g)
    out = []
    for n in g["nodes"]:
        if n.get("alias") not in keys:
            continue
        kind, tokens = keys[n["alias"]]
        entry = {"kind": "property" if kind == "field" else kind, "node": n["alias"]}
        end = _TIME_SPAN_ENDS.get(paths[n["alias"]][-2]) if kind == "date" else None
        mate = next((m["alias"] for m in g["nodes"] if end and m.get("alias")
                     and up.get(m["nodeid"]) == up.get(n["nodeid"]) and paths[m["alias"]][-2] == end), None)
        if mate:
            entry["end_node"] = mate
        phrases = [p for o in ontology["entries"] if o["kind"] == kind
                   and _ends_with(tokens, o["path"].split()) for p in o["phrases"]]
        if not phrases:
            continue
        out.append(dict(entry, phrases=list(dict.fromkeys(phrases))))
        if kind == "date":
            event = up.get(up.get(n["nodeid"]))
            actors = [m["alias"] for m in g["nodes"] if m.get("alias") and up.get(m["nodeid"]) == event
                      and _bundle.kind_of(m) == "link" and paths[m["alias"]][-2] == "P14"]
            if len(actors) == 1:
                out.append({"kind": "link", "node": actors[0], "phrases": [f"who {p}" for p in out[-1]["phrases"]]})
    return out


def _ends_with(tokens: list[str], path: list[str]) -> bool:
    """The path may stop at the property into the node, or name the node's class too.
    A path that starts with "^" starts at the record's root ("^ P107": its own members)."""
    if path[0] == "^":
        return tokens[1:] == path[1:] or tokens[1:-1] == path[1:]
    return tokens[-len(path):] == path or tokens[:-1][-len(path):] == path
