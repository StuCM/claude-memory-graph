"""`ceist vocab ontology`: phrasings for the CIDOC-CRM paths real graphs reach,
proposed by an LLM from the public CRM definitions, reviewed, gated, then merged.

    collect   the link, date and controlled-field paths of the graphs that no phrasing reaches yet,
              ranked by how many nodes each reaches
    propose   per batch of paths, the CRM labels and scope notes along them and the
              existing phrasings as seeds → <ontology>/proposed.json, for review
    accept    the proposals marked "reviewed": true, through the gate script
              (bench/ontology/gate.py), → phrases.json

Privacy: a prompt holds CRM codes, CRM labels and scope notes, and the layer's own
phrasings. No graph, node or record name, label or alias.
"""

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from . import bundle as _bundle
from . import crm
from .pipeline import Runner, _key

PROMPT_VERSION = "1"
BATCH = 10
MAX_CALLS = 300
NOTE_CHARS = 700
GATE = Path(__file__).resolve().parents[2] / "bench" / "ontology" / "gate.py"
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"

PROMPT = """You extend the CIDOC-CRM layer of an offline, no-LLM natural-language search over \
cultural-heritage records (Arches). A record's field is reached from the record by a CIDOC-CRM \
path, and the layer gives each path the plain-English words people use when they ask about it, \
so any graph that uses the path gets them.

A path is CRM classes and properties read from the record outward, ending at the property into \
the field. A "link" path ends at another record (a person, a place, a document): its phrasings fit \
"which objects were <p> X?", "which objects are <p> X?" or "which objects have X as <p>?". A \
"date" path ends at the time-span (P4) of an event: its phrasings fit "when was X <p>?", or are a \
noun such as "date of birth". A "property" path ends at a field holding a term from a list (a \
type, a material): its phrasings name the field, and fit "what is the <p> of X?" or "which objects \
have <p> bronze?". "P108i E12 P14" is the producer of a thing; "P108i E12 P4" when it was made; \
"P108i E12 P126" what it was made of. A path that starts with "^" starts at the record itself.

For each path give either
- "phrases": 2 to 6 short lowercase phrasings people use in questions: a verb phrase ("made by", \
"born") and a noun ("maker", "date of birth"). No question words, no names, no phrasing that \
would fit a more general path just as well; and a "reason": one line on what the path means; or
- "skip": why nobody asks about it this way (record-keeping, audit or digital metadata, a \
statement about the record rather than the thing), or why it is too general to mean one thing.

The existing phrasings (match their style; reuse one for another path only if it means the same):
{seeds}

The CIDOC-CRM definitions of the codes in these paths (label, then the scope note):
{definitions}

PATHS:
{paths}

Reply with JSON only:
{{"paths": [{{"path": "<as given>", "phrases": ["..."], "reason": "..."}} | {{"path": "<as given>", "skip": "..."}}]}}
"""


def definitions(source: Path) -> dict[str, dict]:
    """{code: {"label", "note"}} from the RDFS files in source/; an inverse property
    with no scope note of its own takes its forward property's."""
    out = {}
    for path in sorted(Path(source).glob("*.xml")):
        for el in ET.parse(path).getroot():
            about = (el.get(_RDF + "about") or "").rsplit("/", 1)[-1]
            code = crm.crm_code(about)
            if el.tag not in (_RDFS + "Class", _RDF + "Property") or not code or out.get(code, {}).get("note"):
                continue
            # CRMsci has no labels and redeclares some CRM properties bare: the name says it
            label = next((x.text for x in el.findall(_RDFS + "label")
                          if x.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"), None)
            note = " ".join((el.findtext(_RDFS + "comment") or "").split())
            out[code] = {"label": (label or about[len(code):].replace("_", " ")).strip(), "note": note}
    for code, d in out.items():
        if not d["note"] and code.endswith("i") and code[:-1] in out:
            d["note"] = out[code[:-1]]["note"]
    return out


def path_of(tokens: list[str], kind: str) -> str | None:
    """The path a node's phrasing is keyed by, as phrases.json keys it: up to three
    tokens ending at the property into the node; for a date, into its event's time-span."""
    if kind == "date":
        if len(tokens) < 3 or tokens[-3] != "E52" or tokens[-2] not in ("P82a", "P82"):
            return None
        tokens = tokens[:-3]
    else:
        tokens = tokens[:-1]
    return " ".join(tokens[-3:]) if tokens else None


def graph_docs(dirs) -> list[dict]:
    return [json.loads(p.read_text()) for d in dirs for p in sorted(Path(d).glob("*.json"))]


def collect(graphs: list[dict], ontology: dict, known: dict) -> tuple[list[dict], Counter]:
    """(candidates, skipped reasons): the link, date and controlled-field paths no
    phrasing reaches, each with the nodes and graphs it reaches, most nodes first.
    A path with a code outside `known` (CRMdig, CRMgeo, an extension) is skipped."""
    nodes, graphs_of, skipped = Counter(), {}, Counter()
    for doc in graphs:
        g = doc["graph"][0] if "graph" in doc else doc
        chains = crm.chains(g)
        phrased = {e["node"] for e in crm.ontology_entries(g, ontology)}
        for n in g["nodes"]:
            tokens = chains.get(n.get("alias") or "")
            kind = _bundle.kind_of(n)
            if not tokens or n["datatype"] == "semantic" or (kind == "property" and not crm.is_controlled(n)):
                continue
            path = path_of(tokens, kind)
            if path is None:
                continue
            if n["alias"] in phrased:
                skipped["already phrased"] += 1
            elif any(t not in known for t in path.split()):
                skipped["outside CIDOC-CRM and CRMsci"] += 1
            else:
                nodes[(path, kind)] += 1
                graphs_of.setdefault((path, kind), set()).add(g["graphid"])
    ranked = sorted(nodes, key=lambda k: (-nodes[k], -len(graphs_of[k]), k))
    return ([{"path": p, "kind": k, "nodes": nodes[(p, k)], "graphs": len(graphs_of[(p, k)])}
             for p, k in ranked], skipped)


def prompt(batch: list[dict], ontology: dict, defs: dict) -> str:
    codes = sorted({t for c in batch for t in c["path"].split()}, key=lambda t: (t[0], len(t), t))
    lines = []
    for code in codes:
        note = defs[code]["note"]
        if len(note) > NOTE_CHARS:
            note = note[:NOTE_CHARS].rsplit(". ", 1)[0] + "."
        lines.append(f"{code} {defs[code]['label']}: {note}")
    seeds = "\n".join(f'{e["path"]} ({e["kind"]}): {", ".join(e["phrases"])}' for e in ontology["entries"])
    paths = json.dumps([{"path": c["path"], "kind": c["kind"]} for c in batch])
    return PROMPT.format(seeds=seeds, definitions="\n".join(lines), paths=paths)


def check(reply, batch: list[dict]) -> list[str]:
    if not isinstance(reply, dict) or not isinstance(reply.get("paths"), list):
        return ['the reply must be {"paths": [...]}']
    want, errors, seen = {c["path"] for c in batch}, [], set()
    for x in reply["paths"]:
        p = x.get("path") if isinstance(x, dict) else None
        if p not in want:
            errors.append(f"unknown path {p!r}")
            continue
        seen.add(p)
        if "skip" in x:
            continue
        ph = x.get("phrases")
        if not (isinstance(ph, list) and ph and all(isinstance(s, str) and s.strip() for s in ph)):
            errors.append(f"{p}: phrases must be a non-empty list of strings, or give skip")
        elif any(len(s.split()) > 5 for s in ph):
            errors.append(f"{p}: a phrasing of more than five words")
        if not isinstance(x.get("reason"), str):
            errors.append(f"{p}: reason missing")
    errors += [f"{p}: not answered" for p in sorted(want - seen)]
    return errors


def propose(graph_dirs, ontology_dir: Path, out: Path, llm_cmd: str | None = None, model: str | None = None,
            max_calls: int = MAX_CALLS, top: int | None = None, log=print) -> int:
    """Ranked paths → the LLM, in batches, cached per path → <ontology_dir>/proposed.json."""
    ontology_dir = Path(ontology_dir)
    ontology = load(ontology_dir)
    defs = definitions(ontology_dir / "source")
    cands, skipped = collect(graph_docs(graph_dirs), ontology, defs)
    cands = cands[:top] if top else cands
    run = Runner(Path(out), llm_cmd, model)
    answered = {}
    for c in cands:
        hit = run.cache / f"{_key('ontology-path', PROMPT_VERSION, c['path'], c['kind'])}.json"
        if hit.exists():
            answered[(c["path"], c["kind"])] = json.loads(hit.read_text())
    todo = [c for c in cands if (c["path"], c["kind"]) not in answered]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    log(f"{len(cands)} paths ({sum(c['nodes'] for c in cands)} nodes), {len(cands) - len(todo)} cached: "
        f"{len(batches)} calls, up to {2 * len(batches)} with retries (--max-calls {max_calls})")
    for batch in batches:
        if run.calls >= max_calls:
            log(f"stopped at --max-calls {max_calls}; re-run to go on (answered paths are cached)")
            break
        text = prompt(batch, ontology, defs)
        what = {"step": "ontology", "paths": [c["path"] for c in batch]}
        reply = run.ask("ontology\0" + PROMPT_VERSION + "\0" + text, text, lambda r, b=batch: check(r, b), what)
        for x in (reply or {}).get("paths", []):
            c = next(c for c in batch if c["path"] == x["path"])
            answered[(c["path"], c["kind"])] = x
            hit = run.cache / f"{_key('ontology-path', PROMPT_VERSION, c['path'], c['kind'])}.json"
            hit.write_text(json.dumps(x, ensure_ascii=False))
    old = {(p["path"], p["kind"]): p for p in read_proposed(ontology_dir).get("proposals", [])}
    proposals, skips = [], []
    for c in cands:
        x = answered.get((c["path"], c["kind"]))
        if x is None:
            continue
        if "skip" in x:
            skips.append(dict(c, skip=x["skip"]))
            continue
        p = dict(c, phrases=[s.strip().lower() for s in x["phrases"]], reason=x["reason"], reviewed=False)
        prev = old.get((c["path"], c["kind"])) or {}
        for k in ("phrases", "reviewed", "gate"):
            if k in prev:
                p[k] = prev[k]
        proposals.append(p)
    doc = {"format": "ceist.ontology-proposals/1",
           "how": 'review each proposal: edit its phrases, set "reviewed": true, then '
                  "`ceist vocab ontology --accept`",
           "proposals": proposals, "skipped": skips,
           "not_proposed": dict(skipped)}
    (ontology_dir / "proposed.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    log(f"{len(proposals)} proposals, {len(skips)} skipped by the LLM → {ontology_dir / 'proposed.json'}; "
        f"LLM calls {run.calls}, from the cache {run.hits}; {len(run.failures)} failed")
    return 1 if run.failures else 0


def load(ontology_dir: Path) -> dict:
    return json.loads((Path(ontology_dir) / "phrases.json").read_text())


def read_proposed(ontology_dir: Path) -> dict:
    p = Path(ontology_dir) / "proposed.json"
    return json.loads(p.read_text()) if p.exists() else {}


def write_phrases(ontology_dir: Path, ontology: dict) -> None:
    """phrases.json as it is laid out by hand: one entry per line."""
    rows = [json.dumps({"path": e["path"], "kind": e["kind"], "phrases": e["phrases"]}, ensure_ascii=False)
            for e in ontology["entries"]]
    text = '{\n "format": "' + ontology["format"] + '",\n "entries": [\n  ' + ",\n  ".join(rows) + "\n ]\n}\n"
    (Path(ontology_dir) / "phrases.json").write_text(text)


def merge(ontology: dict, accepted: list[dict]) -> dict:
    entries = [dict(e) for e in ontology["entries"]]
    for a in accepted:
        same = next((e for e in entries if e["path"] == a["path"] and e["kind"] == a["kind"]), None)
        if same:
            same["phrases"] = list(dict.fromkeys(same["phrases"] + a["phrases"]))
        else:
            entries.append({"path": a["path"], "kind": a["kind"], "phrases": a["phrases"]})
    return dict(ontology, entries=entries)


def accept(ontology_dir: Path, gate_cmd: list[str] | None = None, skip=(), log=print) -> int:
    """The reviewed proposals through the gate; those it passes go into phrases.json,
    and each proposal's verdict is written back into proposed.json. `skip`: "demo" or
    "her", gate checks to leave out on a machine without that checkout."""
    ontology_dir = Path(ontology_dir)
    doc = read_proposed(ontology_dir)
    todo = [p for p in doc.get("proposals", []) if p.get("reviewed") and p.get("gate") != "merged"]
    if not todo:
        log('nothing to accept: no proposal has "reviewed": true')
        return 0
    with tempfile.TemporaryDirectory() as d:
        cands = Path(d) / "candidates.json"
        cands.write_text(json.dumps([{"path": p["path"], "kind": p["kind"], "phrases": p["phrases"]} for p in todo]))
        cmd = (gate_cmd or [sys.executable, str(GATE)]) + [str(cands), "--ontology", str(ontology_dir)]
        cmd += [a for s in skip for a in (f"--{s}", "skip")]
        res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        log(f"the gate failed (exit {res.returncode}); nothing merged\n{res.stderr[-2000:]}")
        return 1
    verdict = json.loads(res.stdout.strip().splitlines()[-1])
    passed = set(verdict["accepted"])
    for p in todo:
        k = f"{p['kind']} {p['path']}"
        p["gate"] = "merged" if k in passed else "rejected: " + verdict["rejected"].get(k, "?")
    write_phrases(ontology_dir, merge(load(ontology_dir), [p for p in todo if p["gate"] == "merged"]))
    (ontology_dir / "proposed.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    log(f"{len(passed)} of {len(todo)} reviewed proposals passed the gate and are in phrases.json")
    for line in verdict.get("checks", []):
        log("  " + line)
    return 0
