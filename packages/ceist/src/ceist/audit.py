"""The gap and ambiguity audit in `ceist setup`'s report: whole classes of problem a site's visitors
would otherwise meet one at a time. Each item is resolved (with why) or open (with a one-line fix);
a site is set up when no class has an open item, or the client manifest's "accepted" gives the
reason a class's remainder is accepted ({"accepted": {"<class>": "<why>"}})."""

from . import vocab_rules as vr
from .alizarin import Tiles
from .arches import DATE_TYPES, GEO_TYPES, LINK_TYPES
from .paraphrase import link_targets
from .text import terms

CLASSES = {
    "shared meanings": "a value, type word or phrase more than one model or field can mean",
    "number, date and place fields": "whether the grammar can ask about each",
    "unphrased links": "a link with no phrasing in any layer, only its own label",
    "values and models with no type word": "a controlled value with no plural, a model with no type word",
    "links within one model": "a link both ends of which are the same model: word order sets the direction",
    "names that are phrases": "a record named by a vocabulary phrase, or by generic words only",
}


def _item(what: str, open_: bool, note: str) -> dict:
    return {"what": what, "status": "open" if open_ else "resolved", ("fix" if open_ else "reason"): note}


def _meanings(v) -> dict[str, set[tuple[str, str]]]:
    """{phrase: {(model, field or "")}}: what each type word, link, date, value and group phrase can mean."""
    out: dict[str, set] = {}
    for w, m in v.type_words().items():
        out.setdefault(w, set()).add((m, ""))
    for r in v.relations():
        owners = dict(r.form_owners)
        for f in r.forms:
            out.setdefault(f, set()).update((m, r.name.split("#")[0]) for m in owners.get(f, r.domain))
    for d in v.date_fields():
        for f in d.forms:
            out.setdefault(f, set()).update((m, d.field) for m in d.owners)
    for x in v.values():
        out.setdefault(x.phrase, set()).update((m, x.field) for m in x.owners)
    for g in v.groups():
        for phrase, preset in g.forms:
            out.setdefault(phrase, set()).update({(g.model, x.field) for x in preset} or {(g.model, g.name)})
    return out


def audit(v, defaults: dict[str, str] | None = None, accepted: dict[str, str] | None = None,
          generic: set[str] = frozenset()) -> dict:
    """{"classes": {class: [item]}, "totals": {class: open count}, "set_up": bool}."""
    defaults, accepted = defaults or {}, accepted or {}
    meanings = _meanings(v)
    found = {k: [] for k in CLASSES}

    for phrase, means in sorted(meanings.items()):
        if len(means) < 2:
            continue
        said = "; ".join(f"{m}.{f}" if f else m for m, f in sorted(means))
        models = {m for m, _ in means}
        if phrase in defaults or phrase.rstrip("s") in defaults:
            found["shared meanings"].append(_item(f"'{phrase}': {said}", False,
                                                  f"site default: {defaults.get(phrase) or defaults[phrase.rstrip('s')]}"))
        elif len(models) == len(means):
            found["shared meanings"].append(_item(f"'{phrase}': {said}", False,
                                                  "the subject type settles it; 'did you mean' when the question names none"))
        else:
            found["shared meanings"].append(_item(f"'{phrase}': {said}", True,
                                                  "'did you mean' every time: rephrase one field in the client layer"))

    for m in sorted(v.models):
        for n in v.model(m).nodes:
            kind, alias = n.get("datatype"), n.get("alias")
            if not alias:
                continue
            if kind == "number":
                found["number, date and place fields"].append(_item(
                    f"{m}.{alias} (number)", True, "numeric comparisons are not in the grammar yet (task 060)"))
            elif kind in DATE_TYPES:
                found["number, date and place fields"].append(_item(
                    f"{m}.{alias} (date)", False, "before, after, between and in a year"))
            elif kind in GEO_TYPES:
                found["number, date and place fields"].append(_item(
                    f"{m}.{alias} (geometry)", False, "near a named record"))
            elif kind in LINK_TYPES and not v._bundle_forms.get((m, alias)):
                found["unphrased links"].append(_item(
                    f"{m}.{alias} ('{str(n.get('name') or alias).lower()}')", True,
                    "phrase it in the client layer (a verb or its inverse), or run setup with --llm"))

    combos = {(g.model, x.field, x.label.lower()) for g in v.groups() for p, preset in g.forms for x in preset}
    holders: dict[str, set] = {}
    for x in v.values():
        holders.setdefault(x.label.lower(), set()).update(x.owners)
    seen = set()
    for x in sorted(v.values(), key=lambda x: (x.field, x.label)):
        label = x.label.lower()
        for m in sorted(x.owners):
            if (m, x.field, label) in seen or x.phrase != label:
                continue
            seen.add((m, x.field, label))
            what = f"{m}.{x.field} = {x.label}"
            if (m, x.field, label) in combos:
                continue
            if not vr.word_like(label):
                found["values and models with no type word"].append(_item(what, False, "a code, not said as a word"))
            elif not vr.count_noun(label):
                found["values and models with no type word"].append(_item(what, False, "not a count noun"))
            elif len(holders[label]) > 1 and label not in defaults:
                found["values and models with no type word"].append(_item(
                    what, True, f"held by {', '.join(sorted(holders[label]))}: `--default {label}=<Model>`"))
            else:
                found["values and models with no type word"].append(_item(
                    what, True, f"'{vr.plural(label)}' not proposed or not passed: see setup.md"))
    own = set(v.extra_type_words.values())
    for m in sorted(v.models):
        if m not in own and not vr.word_like(m.replace("_", " ").lower()):
            found["values and models with no type word"].append(_item(
                f"model {m}", True, "its name is not a word people say: add type_words in the client manifest"))

    for (m, alias), targets in sorted(link_targets(v, Tiles(v)).items()):
        if targets == [m]:
            found["links within one model"].append(_item(
                f"{m}.{alias}", False, "word order sets the direction, and 'of' flips it: check both in the practice set"))

    for e in sorted(v._index.entities, key=lambda e: e.name):
        low = e.name.lower()
        if low in meanings:
            found["names that are phrases"].append(_item(f"{e.type} '{e.name}'", True,
                                                         "a question naming it reads the phrase: quote the name"))
        elif generic and terms(low) and set(terms(low)) <= generic:
            found["names that are phrases"].append(_item(f"{e.type} '{e.name}'", True,
                                                         "only generic words: give it a site alias"))

    totals = {k: sum(1 for it in items if it["status"] == "open") for k, items in found.items()}
    set_up = all(n == 0 or k in accepted for k, n in totals.items())
    return {"classes": found, "totals": totals, "accepted": accepted, "set_up": set_up}


def audit_md(found: dict, limit: int = 30) -> str:
    lines = ["# Gap and ambiguity audit", "",
             "Each class lists every item, resolved (with why) or open (with a fix). A site is set up when no "
             "class has an open item or its remainder is accepted (client manifest, \"accepted\").", "",
             "| class | items | open | accepted |", "| --- " * 4 + "|"]
    for k, items in found["classes"].items():
        lines.append(f"| {k} | {len(items)} | {found['totals'][k]} | {found['accepted'].get(k, '')} |")
    lines += ["", f"**{'Set up.' if found['set_up'] else 'Not set up yet: open items remain.'}**"]
    for k, items in found["classes"].items():
        lines += ["", f"## {k}", "", CLASSES[k][0].upper() + CLASSES[k][1:] + ".", ""]
        ordered = sorted(items, key=lambda it: it["status"] != "open")
        lines += [f"- {it['status']}: {it['what']} — {it.get('fix') or it.get('reason')}" for it in ordered[:limit]]
        if len(items) > limit:
            lines.append(f"- … {len(items) - limit} more in audit.json")
    return "\n".join(lines) + "\n"
