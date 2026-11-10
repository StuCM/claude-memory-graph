"""`ceist questions generate`: a labelled starting question set for a graph, written
by an LLM from the schema alone, and scored by comparing Ceist's plan with each
question's target.

The LLM sees what `ceist vocab pipeline` sends (the describe output, short list
labels, CRM role hints), never a record and never the vocabulary. A question that
needs a named record holds a typed placeholder ("which monuments are in {Site}?");
`fill` puts a record's name in locally, at test time.

Out dir: descriptions/, audit.jsonl, cache/ (as the pipeline's), train.json and
holdout.json in the question-bank format, each item with its reading:

    "target": {"model", "count", "group"?, "detail"?, "conditions": [
                  {"node", "value"?, "link"?, "near"?, "tile"?, "negated"?}]}
    or "reason": why the right answer is a refusal
"""

import hashlib
import json
import re
import zlib
from pathlib import Path

from . import cost, crm
from .ground import PREPS
from .pipeline import Runner, _a_value, _key, model_roles, outline
from .text import plural, plurals

SHAPES = ("value", "date", "link", "on-tile", "negation", "or", "group-by", "near", "name match",
          "record detail", "chain", "backlink")
# what a node with this CRM role lets a question ask
ASKS = {"date": "when", "actor": "who", "place": "where", "type": "what kind", "link": "which"}
NAME, TEXT = "@name", "@text"
HOLDOUT_EVERY = 5
_PLACEHOLDER = re.compile(r"\{([A-Za-z][^{}]*)\}")

PROMPT = """You write a starting question set for a natural-language search over the Arches \
model "{model}". People will ask these; the search reads each question into a structured plan, \
with no LLM. You see the model's schema only (its fields, links, short value lists and CRM role \
hints), never its records and never the search's vocabulary.

Write about {n} questions about {model} records, or about records linked to them. Cover:
- every field, link, list and nodegroup ("asks" says what a field answers: when, who, where, \
what kind);
- direct, paraphrased and awkward wordings of the same reading;
- these shapes: {shapes};
- about 15% that the search should refuse, with the reason: story or free text ("what happens \
in…"), an "or" across two different fields, a shape it can't express (why, compare, sort by, \
averages, anything the schema doesn't hold).

Never write a record's name. Where a question needs one, write the linked model in braces: \
"which monuments are in {{Site}}?", "who is associated with {{Figure}}?". Write name fragments \
for a name match in lowercase ("whose name has fort").

Give each answerable question its target: the plan it should read as.
- "model": the model whose records are listed or counted; "count": true for "how many".
- "conditions": every constraint, keyed by field alias:
  - a value: {{"node": "<alias>", "value": "<label from its values>"}}; an "or" between values \
of one field: "value": ["<label>", "<label>"];
  - a date: {{"node": "<alias>"}};
  - a link: {{"node": "<alias>", "link": "<the linked model>"}}, the same for a {{Model}} \
placeholder or a sub-question ("monuments at sites of type X" is one link to Site);
  - a backlink ("sites that have monuments"): the alias on the other model, with "link": \
"<that model>";
  - near a record: {{"node": "<the geometry alias>", "near": "<the record's model>"}};
  - a name match: {{"node": "@name"}}; words its text mentions: {{"node": "@text"}};
  - "negated": true for a "not"/"without" constraint; "tile": "<nodegroup>" when constraints must \
hold on one entry of that nodegroup (actor with role Architect).
- "group": "<link alias>" for "by <link>" or "which <link> has the most".
- "detail": ["<alias>", ...] for a named record's own fields ("what period is {{Site}}?"), \
"detail": [] for the record itself; conditions then empty.

Reply with ONLY one JSON object:
{{"questions": [{{"q": "<question>", "shape": "<one of the shapes>",
                 "wording": "direct" | "paraphrase" | "awkward",
                 "target": {{"model": "<model>", "count": false, "conditions": [...]}}
                 or "refuse": "<why the search should refuse>"}}]}}
Check that your reply parses as JSON.

INPUT:
{payload}
"""


def payload(d: dict, roles: dict, descriptions: dict) -> dict:
    nodes = []
    for n in d["nodes"]:
        x = dict(n)
        hint = roles.get(n["alias"])
        if hint:
            x["hint"] = hint
            if hint["role"] in ASKS:
                x["asks"] = ASKS[hint["role"]]
        nodes.append(x)
    return {"model": outline(d), "nodes": nodes,
            "models": {k: v.get("description", "") for k, v in sorted(descriptions.items())}}


def _check_condition(c, model: str, descriptions: dict) -> str:
    if not isinstance(c, dict):
        return f"condition {c!r} is not an object"
    if c.get("node") in (NAME, TEXT):
        return ""
    for key in ("link", "near"):
        if c.get(key) is not None and c[key] not in descriptions:
            return f"{key} '{c[key]}' is not a model"
    on = c.get("link") if c.get("link") in descriptions else None
    nodes = {n["alias"]: n for n in descriptions[model]["nodes"]}
    if on:                                  # a link of this model, or a backlink on the other
        nodes = {**{n["alias"]: n for n in descriptions[on]["nodes"]}, **nodes}
    n = nodes.get(c.get("node"))
    if n is None:
        return f"condition {c!r}: no node {c.get('node')!r} on {model}{' or ' + on if on else ''}"
    values = c.get("value")
    for v in values if isinstance(values, list) else [values] if values is not None else []:
        if not _a_value(n, v):
            return f"'{v}' is not a value of {c['node']}"
    if c.get("tile") is not None and c["tile"] not in (descriptions[model].get("nodegroups") or {}):
        return f"tile '{c['tile']}' is not a nodegroup of {model}"
    return ""


def check(reply, descriptions: dict) -> list[str]:
    """Errors in a generated reply: every model, node, value and placeholder must exist,
    and no record name may be written out."""
    from .learn import mask
    if not isinstance(reply, dict) or not isinstance(reply.get("questions"), list):
        return ['no "questions" list']
    errors = []
    for i, x in enumerate(reply["questions"]):
        q = x.get("q") if isinstance(x, dict) else None
        if not (isinstance(q, str) and q.strip()):
            errors.append(f"question {i}: needs \"q\"")
            continue
        bad = [t for t in _PLACEHOLDER.findall(q) if t not in descriptions]
        if bad:
            errors.append(f"question {i}: placeholder {{{bad[0]}}} is not a model")
        if "<Name>" in mask(_PLACEHOLDER.sub("", q)):
            errors.append(f"question {i}: {q!r} names a record; write {{Model}} instead")
        t, why = x.get("target"), x.get("refuse")
        if (t is None) == (why is None):
            errors.append(f"question {i}: needs a \"target\" or a \"refuse\" reason, not both")
            continue
        if why is not None:
            if not (isinstance(why, str) and why.strip()):
                errors.append(f"question {i}: \"refuse\" needs the reason")
            continue
        model = t.get("model") if isinstance(t, dict) else None
        if model not in descriptions:
            errors.append(f"question {i}: target model {model!r} is not a model")
            continue
        if not isinstance(t.get("conditions", []), list):
            errors.append(f"question {i}: \"conditions\" is not a list")
            continue
        aliases = {n["alias"] for n in descriptions[model]["nodes"]}
        for a in [t["group"]] if t.get("group") else []:
            if a not in aliases:
                errors.append(f"question {i}: group {a!r} is not a node of {model}")
        for a in t.get("detail") or []:
            if a not in aliases:
                errors.append(f"question {i}: detail {a!r} is not a node of {model}")
        errors += [f"question {i}: {e}" for e in
                   (_check_condition(c, model, descriptions) for c in t.get("conditions", [])) if e]
    return errors


def held_out(q: str) -> bool:
    """One question in HOLDOUT_EVERY, by a hash of its text: the same split every run."""
    from .learn import _norm
    return int(hashlib.sha256(_norm(q).encode()).hexdigest(), 16) % HOLDOUT_EVERY == 0


def bank_item(x: dict, model: str) -> dict:
    out = {"q": x["q"], "expect": "refuse" if x.get("refuse") else "answer", "count": None,
           "note": x.get("refuse") or "", "model": model, "shape": x.get("shape", ""),
           "wording": x.get("wording", "")}
    if x.get("refuse"):
        out["reason"] = x["refuse"]
    else:
        out["target"] = x["target"]
    return out


def prompt_for(name: str, descriptions: dict, roles: dict, per_model: int) -> tuple[str, str]:
    """(cache key, prompt) of one model's call."""
    p = payload(descriptions[name], roles.get(name, {}), descriptions)
    text = json.dumps(p, ensure_ascii=False, indent=1)
    return (_key("generate", name, str(per_model), json.dumps(p, sort_keys=True)),
            PROMPT.format(model=name, n=per_model, shapes=", ".join(SHAPES), payload=text))


def generate(graphs, out, reference=None, llm_cmd=None, model=None, models=None, per_model: int = 40,
             log=print) -> int:
    """train.json and holdout.json for the graphs; 0 when every call answered, else 1."""
    from .arches_describe import describe
    from .learn import _norm
    graphs, out = Path(graphs), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    descriptions = describe(graphs, out / "descriptions", reference)
    roles = model_roles(graphs, descriptions)
    asked = sorted(models or descriptions)
    unknown = set(asked) - set(descriptions)
    if unknown:
        raise ValueError(f"no such model: {', '.join(sorted(unknown))}")
    llm = Runner(out, llm_cmd, model)
    items, seen = [], set()
    for name in asked:
        key, prompt = prompt_for(name, descriptions, roles, per_model)
        reply = llm.ask(key, prompt, lambda r: check(r, descriptions), {"kind": "generate", "model": name})
        for x in (reply or {}).get("questions", []):
            if _norm(x["q"]) not in seen:
                seen.add(_norm(x["q"]))
                items.append(bank_item(x, name))
    about = "Generated by `ceist questions generate` from the schema only; {} split, one in {}."
    for part, keep in (("train", False), ("holdout", True)):
        doc = {"about": about.format(part, HOLDOUT_EVERY),
               "questions": [o for o in items if held_out(o["q"]) == keep]}
        (out / f"{part}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    refuse = sum(1 for o in items if o["expect"] == "refuse")
    log(f"{len(items)} questions ({refuse} should refuse) from {len(asked)} model(s); "
        f"LLM calls: {llm.calls} ({llm.hits} from the cache)")
    for f in llm.failures:
        log(f"failed: {f['model']}: {'; '.join(f['errors'][:3])}")
    log("\n".join(cost.summary(llm.ledger)))
    return 1 if llm.failures else 0


def fill(q: str, vocab) -> str | None:
    """The question with each {Model} placeholder replaced by the name of one of its
    records, chosen by the question's text; None when a model has no records."""
    out = q
    for t in _PLACEHOLDER.findall(q):
        names = sorted(vocab.names[i] for i in vocab.ids_of(t))
        if not names:
            return None
        out = out.replace("{" + t + "}", names[zlib.crc32(q.encode()) % len(names)], 1)
    return out


def _conditions(where, tile: str = "", negated: bool = False) -> list[dict]:
    from .plan import (
        AnyOf,
        Contains,
        DateRange,
        HasValue,
        LinkTo,
        Mention,
        NameMatch,
        Near,
        Not,
        OnTile,
    )
    out = []

    def add(c: dict):
        c = dict(c, **({"tile": tile} if tile else {}), **({"negated": True} if negated else {}))
        keep([c])

    def keep(xs):
        out.extend(x for x in xs if x not in out)

    for c in where:
        if isinstance(c, Not):
            keep(_conditions([c.condition], tile, not negated))
        elif isinstance(c, OnTile):
            keep(_conditions(c.conditions, c.group, negated))
        elif isinstance(c, AnyOf) and c.conditions and all(
                isinstance(x, HasValue) and x.field == c.conditions[0].field for x in c.conditions):
            add({"node": c.conditions[0].field, "value": sorted(x.label for x in c.conditions)})
        elif isinstance(c, AnyOf):
            keep(_conditions(c.conditions, tile, negated))
        elif isinstance(c, LinkTo):
            target = c.target.entity.type if hasattr(c.target, "entity") else c.target.type
            add({"node": (c.relation or "").split("#")[0], "link": target})
            if c.qualifier is not None:
                add({"node": c.qualifier.field, "value": c.qualifier.label})
        elif isinstance(c, HasValue):
            add({"node": c.field, "value": c.label})
        elif isinstance(c, DateRange):
            add({"node": c.field})
        elif isinstance(c, Near):
            add({"node": c.field, "near": c.entity.type})
        elif isinstance(c, NameMatch):
            add({"node": NAME})
        elif isinstance(c, (Mention, Contains)):
            add({"node": TEXT})
    return out


def target_of(m) -> dict | None:
    """An interpretation as a target ({"model", "count", "conditions", …}); None when refused."""
    if m.refused or m.statement:
        return None
    if m.direct is not None:
        return {"model": m.direct.type, "detail": [], "conditions": []}
    if m.detail is not None:
        return {"model": m.detail.entity.type, "detail": [f for f, _ in m.detail.fields],
                "conditions": []}
    return None if m.plan is None else plan_target(m.plan)


def plan_target(plan) -> dict:
    t = {"model": plan.type, "count": plan.count, "conditions": _conditions(plan.where)}
    if plan.group is not None:
        t["group"] = plan.group.relation.split("#")[0]
    return t


def _same(want: dict, got: dict, ends: dict[str, str]) -> bool:
    if not ({want["node"], ends.get(want["node"])} & {got["node"], ends.get(got["node"])}) - {None}:
        return False
    if bool(want.get("negated")) != bool(got.get("negated")):
        return False
    for key in ("link", "near", "tile"):
        if want.get(key) is not None and want[key] != got.get(key):
            return False
    if want.get("value") is None:
        return True
    w, g = want["value"], got.get("value")
    w = sorted(v.lower() for v in w) if isinstance(w, list) else w.lower()
    g = sorted(v.lower() for v in g) if isinstance(g, list) else (g or "").lower()
    return w == g


def matches(want: dict, got: dict, ends: dict[str, str] | None = None) -> bool:
    """The plan reads as the target: same model, count, group and detail, and its
    conditions pair off one to one with the target's (a tile, link or value only
    checked where the target gives it)."""
    ends = ends or {}
    counts = bool(want.get("count") or want.get("group"))      # a group is always counted
    if want["model"] != got["model"] or counts != bool(got.get("count")):
        return False
    if want.get("group") != got.get("group"):
        return False
    if ("detail" in want) != ("detail" in got):
        return False
    if sorted(want.get("detail") or []) != sorted(got.get("detail") or []):
        return False
    left = list(got["conditions"])
    for w in want.get("conditions", []):
        hit = next((g for g in left if _same(w, g, ends)), None)
        if hit is None:
            return False
        left.remove(hit)
    return not left


def wider(want: dict, got: dict, ends: dict[str, str] | None = None) -> bool:
    """`got` is the target with conditions left out, or a link by any relation in place of
    one by a named relation: the right reading, only wider (how a partial match is judged)."""
    ends = ends or {}
    counts = bool(want.get("count") or want.get("group"))
    if "detail" in want or want["model"] != got["model"] or counts != bool(got.get("count")):
        return False
    left = list(want.get("conditions", []))
    for c in got["conditions"]:
        if c["node"]:
            hit = next((w for w in left if _same(c, w, ends)), None)
        else:
            hit = next((w for w in left if w.get("link") == c["link"]
                        and bool(w.get("negated")) == bool(c.get("negated"))), None)
        if hit is None:
            return False
        left.remove(hit)
    return True


def score(item: dict, m, ends: dict[str, str] | None = None) -> str:
    """right / wrong reading / refused for a question with a target; right refusal /
    wrong for one that should be refused."""
    got = target_of(m)
    if "target" not in item:
        return "right refusal" if got is None else "wrong"
    if got is None:
        return "refused"
    return "right" if matches(item["target"], got, ends) else "wrong reading"


_AT = ("in", "of", "within", "at", "as", "from", "with")
_VERBS = {"involved", "mentions", "concerns"}


def _plural(name: str) -> str:
    return plural(name.replace("_", " ").lower())


def _link_question(p: str, many: str, other: str) -> str:
    last = p.split()[-1]
    if last == "by":
        return f"which {many} were {p} {{{other}}}?"
    if last in _AT:
        return f"which {many} are {p} {{{other}}}?"
    if p in _VERBS:
        return f"which {many} {p} {{{other}}}?"
    return f"which {many} have {{{other}}} as {p}?"


def templated(vocab, ontology: dict, bundle: dict | None = None, only: set | None = None) -> list[dict]:
    """A question bank from the ontology layer alone, with no LLM: for each link, date or
    field node a graph's CRM paths give a phrase, template questions using it, each with its
    target, plus refusals ("why", and "who <verb>" where the event has no one actor).
    With a bundle, also "how many <w> are there?" for its type words, and the same templates
    for its base and client link and date phrasings on the (model, node) pairs in `only`.
    A text with two targets is left out: the layer drops that phrase, so the reading
    rests on node labels, which no target here can predict."""
    who = vocab.implied_types().get("who")
    ends = {(m, r.name): sorted(t) for r in vocab.relations() for m, t in r.ends}
    found: dict[str, list[dict]] = {}

    def add(q: str, model: str, shape: str, target: dict | None = None, refuse: str = ""):
        x = {"q": q, "model": model, "shape": shape, "wording": "template"}
        found.setdefault(q, []).append(dict(x, refuse=refuse) if refuse else dict(x, target=target))

    for w, name in sorted(((bundle or {}).get("extra_type_words") or {}).items()):
        if name in vocab.models and w not in plurals(name):
            add(f"how many {w} are there?", name, "count", {"model": name, "count": True, "conditions": []})
    for name in sorted(vocab.models):
        entries = crm.ontology_entries(vocab.models[name].doc, ontology)
        mine = ((bundle or {}).get("models") or {}).get(name) or {"entries": []}
        entries += [e for e in mine["entries"] if e.get("layer") != "ontology" and not e.get("qualifier")
                    and e["kind"] in ("link", "date") and (name, e["node"]) in (only or ())]
        many, said = _plural(name), {p for e in entries for p in e["phrases"]}
        for e in entries:
            node = e["node"]
            for i, p in enumerate(e["phrases"]):
                if e["kind"] == "date":
                    if p.endswith(" date") or p.startswith("date of"):
                        add(f"what is the {p} of {{{name}}}?", name, "record detail",
                            {"model": name, "detail": [node], "conditions": []})
                    if "date" in p:
                        continue
                    add(f"when was {{{name}}} {p}?", name, "record detail",
                        {"model": name, "detail": [node], "conditions": []})
                    if i == 0:
                        add(f"which {many} were {p} before 1900?", name, "date",
                            {"model": name, "count": False, "conditions": [{"node": node}]})
                        add(f"why was {{{name}}} {p}?", name, "date", refuse="why")
                    if " " not in p and f"who {p}" not in said:
                        add(f"who {p} {{{name}}}?", name, "backlink",
                            refuse=f"no one actor on the event {node} hangs from")
                    continue
                if e["kind"] == "property":
                    if p.split()[-1] not in PREPS:
                        add(f"what is the {p} of {{{name}}}?", name, "record detail",
                            {"model": name, "detail": [node], "conditions": []})
                    continue
                targets = ends.get((name, node)) or []
                if p.startswith("who "):
                    if who in targets:
                        add(f"{p} {{{name}}}?", who, "backlink",
                            {"model": who, "count": False, "conditions": [{"node": node, "link": name}]})
                    continue
                if not targets:
                    continue
                other = who if who in targets else targets[0]
                q = _link_question(p, many, other)
                add(q, name, "link", {"model": name, "count": False, "conditions": [{"node": node, "link": other}]})
                if i == 0:
                    add("how many " + q[len("which "):], name, "link",
                        {"model": name, "count": True, "conditions": [{"node": node, "link": other}]})
    items = []
    for q in sorted(found):
        xs = [x for i, x in enumerate(found[q]) if x not in found[q][:i]]
        if len(xs) == 1:
            items.append(bank_item(xs[0], xs[0]["model"]))
    return items
