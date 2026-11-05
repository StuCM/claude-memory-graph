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
    prompt     the instruction an LLM follows to write a model's entries, with the
               model's description inline (the LLM sees the schema, never a path
               into the project or a record)
    save       the LLM's JSON reply → vocab/<Model>.json, validated
    split      vocab/<Model>.json → vocab/<Model>/<nodegroup alias>.json, plus
               vocab/manifest.json: each nodegroup's id, parent and a hash of its
               description, so `check --vocab` finds the groups that went stale
    assemble   validate the entries against the descriptions and write the bundle,
               with a hash of the graph files so a stale bundle is caught (`check`)
    slice      (ceist.slicing) cut a bundle down to what one dataset uses

A vocabulary directory holds either layout; with a manifest.json it is read
as the split one. A group file is {"model", "nodegroup", "entries"}; the key
"group" is reserved for the group's own block (docs/tasks/ceist-group-grounding.md).
"""

import hashlib
import json
from pathlib import Path

FORMAT = "ceist.vocab/1"
LAYOUT = "ceist.vocab-groups/1"
MANIFEST = "manifest.json"
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
    errors, warnings = [], []
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
    for key, owners in shared_phrases(entries).items():
        for i in owners[1:]:
            warnings.append(f"{description['name']}: '{key}' is a phrasing of two entries "
                            f"({entries[owners[0]]['node']}, {entries[i]['node']}) — ambiguous on purpose?")
    return errors, warnings


def shared_phrases(entries: list[dict]) -> dict[str, list[int]]:
    """Each phrase that belongs to more than one entry, with those entries' indices."""
    owners: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        for ph in e.get("phrases", []):
            seen = owners.setdefault(ph.strip().lower(), [])
            if i not in seen:
                seen.append(i)
    return {k: v for k, v in owners.items() if len(v) > 1}


def nodegroups(graph: dict) -> tuple[dict[str, dict], dict[str, str]]:
    """A graph's nodegroups, {alias: {"id", "parent"}}, and each node's nodegroup
    alias. A nodegroup is named by its top node, whose id it shares."""
    alias = {n["nodeid"]: n.get("alias") or n["nodeid"] for n in graph["nodes"]}
    groups = {alias.get(g["nodegroupid"], g["nodegroupid"]):
              {"id": g["nodegroupid"], "parent": alias.get(g.get("parentnodegroup_id"))}
              for g in graph.get("nodegroups", [])}
    node_group = {n["alias"]: alias.get(n["nodegroup_id"], n["nodegroup_id"])
                  for n in graph["nodes"] if n.get("alias") and n.get("nodegroup_id")}
    return groups, node_group


def group_hash(description: dict, group: str) -> str:
    nodes = [n for n in description["nodes"] if n.get("nodegroup") == group]
    return hashlib.sha256(json.dumps(nodes, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _descriptions(descriptions_dir: str | Path) -> dict:
    out = {}
    for p in sorted(Path(descriptions_dir).glob("*.json")):
        d = json.loads(p.read_text())
        out[d["name"]] = d
    return out


def read_vocab(vocab_dir: str | Path) -> tuple[list[dict], list[str]]:
    """Each model's {"model", "entries"} from either layout, plus warnings.
    Split layout: a model's entries in the order of its group files' names."""
    root = Path(vocab_dir)
    files = sorted((p for p in root.glob("*.json") if p.name != MANIFEST), key=lambda p: p.stem)
    if not (root / MANIFEST).exists():
        return [json.loads(p.read_text()) for p in files], []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        groups = sorted(d.glob("*.json"), key=lambda p: p.stem)
        if groups:
            out.append({"model": d.name, "entries": [e for g in groups
                                                     for e in json.loads(g.read_text())["entries"]]})
    warnings = [f"{p.name} not read: {MANIFEST} says the split layout is read" for p in files]
    return out, warnings


def assemble(descriptions_dir: str | Path, vocab_dir: str | Path,
             graphs_dir: str | Path | None = None) -> tuple[dict, list[str], list[str]]:
    """The bundle, plus (errors, warnings). A bundle with errors shouldn't ship.
    A model's entries are ordered by nodegroup, so both layouts give the same bundle."""
    descriptions = _descriptions(descriptions_dir)
    models, errors = {}, []
    vocab, warnings = read_vocab(vocab_dir)
    for v in vocab:
        d = descriptions.get(v["model"])
        if d is None:
            errors.append(f"{v['model']}: no description for model '{v['model']}'")
            continue
        err, warn = validate(d, v["entries"])
        errors += err
        warnings += warn
        group_of = {n["alias"]: n.get("nodegroup") or "" for n in d["nodes"]}
        models[v["model"]] = {
            "graphid": d.get("graphid"),
            "nodes": {n["alias"]: {k: x for k, x in (("kind", kind_of(n)),
                                                      ("label", n.get("label") or n["name"]),
                                                      ("targets", n.get("targets"))) if x}
                      for n in d["nodes"]},
            "entries": [dict(e, phrases=sorted({x.strip().lower() for x in e["phrases"] if x.strip()}))
                        for e in sorted(v["entries"], key=lambda e: group_of.get(e.get("node"), ""))],
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


def manifest(descriptions: dict) -> dict:
    return {"format": LAYOUT, "models": {
        name: {"graphid": d.get("graphid"),
               "nodegroups": {a: dict(g, description_sha256=group_hash(d, a))
                              for a, g in sorted((d.get("nodegroups") or {}).items())}}
        for name, d in sorted(descriptions.items())}}


def split(descriptions_dir: str | Path, vocab_dir: str | Path,
          out_dir: str | Path) -> tuple[list[str], list[str]]:
    """vocab/<Model>.json → <out>/<Model>/<nodegroup alias>.json and <out>/manifest.json;
    (files written, errors). A model with errors is not written."""
    descriptions = _descriptions(descriptions_dir)
    out = Path(out_dir)
    written, errors, done = [], [], {}
    for p in sorted((p for p in Path(vocab_dir).glob("*.json") if p.name != MANIFEST),
                    key=lambda p: p.stem):
        v = json.loads(p.read_text())
        d = descriptions.get(v["model"])
        if d is None or "nodegroups" not in d:
            errors.append(f"{p.name}: no description of {v['model']}'s nodegroups "
                          "(run `ceist vocab describe` again)")
            continue
        group_of = {n["alias"]: n.get("nodegroup") for n in d["nodes"]}
        by_group: dict[str, list] = {}
        for e in v["entries"]:
            g = group_of.get(e.get("node"))
            if g is None:
                errors.append(f"{v['model']}: '{e.get('node')}' is in no nodegroup")
            by_group.setdefault(g, []).append(e)
        if None in by_group:
            continue
        model_dir = out / v["model"]
        model_dir.mkdir(parents=True, exist_ok=True)
        for old in model_dir.glob("*.json"):
            old.unlink()
        for g, entries in sorted(by_group.items()):
            path = model_dir / f"{g}.json"
            path.write_text(json.dumps({"model": v["model"], "nodegroup": g, "entries": entries},
                                       indent=1, ensure_ascii=False) + "\n")
            written.append(str(path))
        done[v["model"]] = d
    if done:
        (out / MANIFEST).write_text(json.dumps(manifest(done), indent=1) + "\n")
    return written, errors


def stale_groups(vocab_dir: str | Path, descriptions_dir: str | Path) -> list[str]:
    """The nodegroups whose description changed since the split vocabulary was written."""
    m = json.loads((Path(vocab_dir) / MANIFEST).read_text())
    descriptions = _descriptions(descriptions_dir)
    out = []
    for name, model in m["models"].items():
        d = descriptions.get(name)
        if d is None:
            out.append(f"{name}: no longer described")
            continue
        now = manifest({name: d})["models"][name]["nodegroups"]
        for a, g in model["nodegroups"].items():
            if a not in now:
                out.append(f"{name}.{a}: no longer in the model")
            elif now[a]["description_sha256"] != g["description_sha256"]:
                out.append(f"{name}.{a}: its description changed")
        out += [f"{name}.{a}: new nodegroup" for a in now if a not in model["nodegroups"]]
    return out


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

The model description(s) are at the end of this message, inline. Use ONLY them: there are no files \
to read, and you must not look for any (no records, no test questions: this is a blind build that \
sees the schema, never the data). Each description lists the model's searchable nodes: alias, \
name, datatype, card (the UI card it's on), path (its place in the model tree), label (the UI \
widget label, if different), crm (its CIDOC-CRM context), targets (for links: which models it \
points to), values (labels of a small controlled list or concept collection) or values_count (a \
large one).

Reply with ONLY one JSON object, keyed by model name, with each model's entries:
{{"<Model>": {{"model": "<Model>",
 "entries": [
   {{"phrases": ["...", ...],          // lowercase everyday phrasings
    "kind": "date" | "link" | "property",
    "node": "<alias>",                // the node a question means
    "end_node": "<alias>",            // dates only: the END date of the same timespan, when node is its start
    "qualifier": {{"node": "<alias>", "value": "<label from values>"}}   // optional: when the meaning needs a concept value too
   }}, ...]}}, ...}}

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
Check that your reply parses as JSON.

Model descriptions:
{descriptions}
"""


def prompt(descriptions_dir: str | Path, models: list[str]) -> str:
    """The build instruction with the models' descriptions inline: the LLM is
    handed the schema itself, never a path into the project (where the
    records live). One model per prompt keeps it small (HER: 20–130 KB each)."""
    blocks = []
    for m in models:
        d = json.loads((Path(descriptions_dir) / f"{m}.json").read_text())
        blocks.append(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    return PROMPT.format(descriptions="\n\n".join(blocks))


def parse_reply(text: str) -> dict:
    """An LLM's JSON reply, with any ```json fence around it removed."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return json.loads(t)


def save(reply: str, descriptions_dir: str | Path, vocab_dir: str | Path) -> tuple[list[str], list[str], list[str]]:
    """Write a build reply ({Model: {"model", "entries"}}) as <vocab dir>/<Model>.json,
    validated against each model's description; (written, errors, warnings).
    A model with errors is not written."""
    out = Path(vocab_dir)
    out.mkdir(parents=True, exist_ok=True)
    written, errors, warnings = [], [], []
    for name, v in parse_reply(reply).items():
        path = Path(descriptions_dir) / f"{name}.json"
        if not path.exists():
            errors.append(f"{name}: no description (not a model of this project)")
            continue
        v = {"model": name, "entries": v.get("entries", []) if isinstance(v, dict) else v}
        err, warn = validate(json.loads(path.read_text()), v["entries"])
        errors += err
        warnings += warn
        if err:
            continue
        (out / f"{name}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n")
        written.append(name)
    return written, errors, warnings
