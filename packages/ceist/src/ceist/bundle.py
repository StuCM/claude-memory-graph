"""The vocabulary bundle: everything question time needs about a project's
models, in one file built once, offline.

    {"format": "ceist.vocab/1",
     "built": {"graphs_sha256": "…", "models": 16, "entries": 1301, "phrasings": 7392},
     "models": {
       "Monument": {
         "graphid": "…",
         "nodes": {"<alias>": {"kind": "date|link|property", "label": "…", "targets": [...]}},
         "entries": [
           {"phrases": ["built", "put up", …], "kind": "date",
            "node": "construction_phase_start_date",
            "end_node": "construction_phase_end_date",                     # dates: the event's other end
            "qualifier": {"node": "role_type", "value": "Architect"}},     # when the meaning needs a value
           …]}}}

How it is made (`ceist vocab …`):

    describe   read the models (Alizarin) → one description per model
    prompt     the instruction an LLM follows to write a model's entries
    assemble   validate the entries against the descriptions and write the bundle,
               with a hash of the graph files so a stale bundle is caught (`check`)
"""

import hashlib
import json
from pathlib import Path

FORMAT = "ceist.vocab/1"
DATE = {"date", "edtf"}


def kind_of(node: dict) -> str:
    if node["datatype"] in DATE:
        return "date"
    if node["datatype"].startswith("resource-instance"):
        return "link"
    return "property"


def graphs_hash(graphs_dir: str | Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(graphs_dir).glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def validate(description: dict, entries: list[dict]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one model's entries against its description."""
    nodes = {n["alias"]: n for n in description["nodes"]}
    errors, warnings, seen = [], [], {}
    for i, e in enumerate(entries):
        where = f"{description['name']} entry {i} ({e.get('node')})"
        n = nodes.get(e.get("node"))
        if n is None:
            errors.append(f"{where}: no node '{e.get('node')}'")
            continue
        if not e.get("phrases"):
            errors.append(f"{where}: no phrases")
        if e.get("end_node"):
            end = nodes.get(e["end_node"])
            if end is None or kind_of(end) != "date":
                errors.append(f"{where}: end_node '{e['end_node']}' is not a date of this model")
        q = e.get("qualifier")
        if q:
            qn = nodes.get(q.get("node"))
            if qn is None:
                errors.append(f"{where}: qualifier node '{q.get('node')}' not in the model")
            elif isinstance(qn.get("values"), list) and q.get("value") not in qn["values"]:
                errors.append(f"{where}: '{q.get('value')}' is not a value of {q['node']}")
        for ph in e.get("phrases", []):
            key = ph.strip().lower()
            if key in seen and seen[key] != i:
                warnings.append(f"{description['name']}: '{key}' is a phrasing of two entries "
                                f"({entries[seen[key]]['node']}, {e['node']}) — ambiguous on purpose?")
            seen.setdefault(key, i)
    return errors, warnings


def assemble(descriptions_dir: str | Path, vocab_dir: str | Path,
             graphs_dir: str | Path | None = None) -> tuple[dict, list[str], list[str]]:
    """The bundle, plus (errors, warnings). A bundle with errors shouldn't ship."""
    descriptions = {json.loads(p.read_text())["name"]: json.loads(p.read_text())
                    for p in sorted(Path(descriptions_dir).glob("*.json"))}
    models, errors, warnings = {}, [], []
    for p in sorted(Path(vocab_dir).glob("*.json")):
        v = json.loads(p.read_text())
        d = descriptions.get(v["model"])
        if d is None:
            errors.append(f"{p.name}: no description for model '{v['model']}'")
            continue
        err, warn = validate(d, v["entries"])
        errors += err
        warnings += warn
        models[v["model"]] = {
            "graphid": d.get("graphid"),
            "nodes": {n["alias"]: {k: x for k, x in (("kind", kind_of(n)),
                                                      ("label", n.get("label") or n["name"]),
                                                      ("targets", n.get("targets"))) if x}
                      for n in d["nodes"]},
            "entries": [dict(e, phrases=sorted({x.strip().lower() for x in e["phrases"] if x.strip()}))
                        for e in v["entries"]],
        }
    missing = sorted(set(descriptions) - set(models))
    if missing:
        warnings.append("no vocabulary for: " + ", ".join(missing))
    bundle = {"format": FORMAT,
              "built": {"graphs_sha256": graphs_hash(graphs_dir) if graphs_dir else None,
                        "models": len(models),
                        "entries": sum(len(m["entries"]) for m in models.values()),
                        "phrasings": sum(len(e["phrases"]) for m in models.values()
                                         for e in m["entries"])},
             "models": models}
    return bundle, errors, warnings


def load(path: str | Path) -> dict:
    b = json.loads(Path(path).read_text())
    if b.get("format") != FORMAT:
        raise ValueError(f"{path}: not a {FORMAT} bundle")
    return b


def stale(bundle: dict, graphs_dir: str | Path) -> bool:
    built = (bundle.get("built") or {}).get("graphs_sha256")
    return built is not None and built != graphs_hash(graphs_dir)


PROMPT = """You are the offline "vocabulary build" step for a no-LLM natural-language search over \
Arches data. At query time only exact phrase lookup and static word vectors run, so the everyday \
phrasings people use for each node must be written now, once.

Read ONLY the model description(s) listed below. Each lists the model's searchable nodes: alias, \
name, datatype, card (the UI card it's on), path (its place in the model tree), label (the UI \
widget label, if different), crm (its CIDOC-CRM context), targets (for links: which models it \
points to), values (labels of a small concept collection) or values_count (a large thesaurus). \
Do not read any test questions: this is a blind build.

For each model write {vocab_dir}/<Model>.json:
{{"model": "<Model>",
 "entries": [
   {{"phrases": ["...", ...],          // lowercase everyday phrasings
    "kind": "date" | "link" | "property",
    "node": "<alias>",                // the node a question means
    "end_node": "<alias>",            // dates only: the END date of the same timespan, when node is its start
    "qualifier": {{"node": "<alias>", "value": "<label from values>"}}   // optional: when the meaning needs a concept value too
   }}, ...]}}

Guidance:
- Think like the people who will ask: members of the public, researchers, officers. Spend effort \
on what they ask about (events and their dates, people/organisations and their roles, types, \
periods, condition, protection, materials, location, dimensions, names, descriptions). Record-\
keeping metadata needs only a few phrases.
- Dates: give ONE entry per event with node = start date and end_node = end date, with the \
event's verbs and phrases (built, constructed, erected, put up, ...). Don't let two events share \
a phrase.
- Links to people/organisations are often generic (an actor link plus a role type). Where the \
role values list roles, write entries with node = the actor link and qualifier = the role for \
commonly asked roles (designed by → Architect, built by → Builder, ...), plus one entry without \
a qualifier for generic involvement. Use only labels in the values list. Likewise typed events \
(a phase type of Construction / Alteration / Destruction).
- Properties: nouns, adjectives and question forms (how tall → height; made of → material).
- Include direction words where they matter ("sailing from" vs "sailing to").
- Keep a model's entries distinguishable; 3–20 phrases per entry; skip nodes nobody would ask \
about by name.
Validate that each file parses as JSON.

Model descriptions:
{files}
"""


def prompt(descriptions_dir: str | Path, models: list[str], vocab_dir: str | Path) -> str:
    files = "\n".join(str(Path(descriptions_dir) / f"{m}.json") for m in models)
    return PROMPT.format(vocab_dir=vocab_dir, files=files)
