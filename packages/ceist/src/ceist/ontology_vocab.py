"""`ceist vocab ontology`: phrasings for the CIDOC-CRM paths real graphs reach,
proposed by an LLM from the public CRM definitions, reviewed, gated, then merged.

    collect   the link, date and controlled-field paths of the graphs that no phrasing reaches yet,
              ranked by how many nodes each reaches
    propose   per batch of paths, the CRM labels and scope notes along them and the
              existing phrasings as seeds → <ontology>/proposed.json, for review
    review    the checks a person made by hand: generic phrasings, phrasings shared by sibling
              paths, clashes with phrases.json, bare nouns → "reviewed": "auto" on what survives
    accept    the reviewed proposals, through the gate script (bench/ontology/gate.py), → phrases.json
    build     all of it, after an estimate, and build-report.md

Privacy: a prompt holds CRM codes, CRM labels and scope notes, and the layer's own
phrasings. No graph, node or record name, label or alias.
"""

import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from . import bundle as _bundle
from . import cost, crm, prices
from .pipeline import Runner, _key

PROMPT_VERSION = "1"
BATCH = 10
MAX_CALLS = 300
NOTE_CHARS = 700
GATE = Path(__file__).resolve().parents[2] / "bench" / "ontology" / "gate.py"
GENERIC = "generic.json"
HIGH_USE = 10
SCORES = ("right", "wrong reading", "refused", "right refusal", "wrong")
CHECKS = ("not generic", "not shared with a sibling path", "no clash with phrases.json",
          "a bare noun only where the path reaches one field")
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
    dollars = sum(prices.cost({"input_tokens": cost.by_chars(prompt(b, ontology, defs)),
                               "output_tokens": cost.DEFAULT_OUTPUT}, model or "opus") for b in batches)
    log(f"{len(cands)} paths ({sum(c['nodes'] for c in cands)} nodes), {len(cands) - len(todo)} cached: "
        f"{len(batches)} calls, up to {2 * len(batches)} with retries, about ${dollars:.2f} "
        f"(--max-calls {max_calls})")
    if len(batches) > max_calls:
        log(f"over --max-calls {max_calls}: nothing sent")
        return 2
    for batch in batches:
        if run.calls >= max_calls:
            log(f"stopped at --max-calls {max_calls}; re-run to go on (answered paths are cached)")
            break
        text = prompt(batch, ontology, defs)
        what = {"kind": "ontology", "paths": [c["path"] for c in batch]}
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
        for k in ("phrases", "reviewed", "gate", "review", "checks"):
            if k in prev:
                p[k] = prev[k]
        proposals.append(p)
    doc = {"format": "ceist.ontology-proposals/1",
           "how": 'review each proposal: edit its phrases, set "reviewed": true, then '
                  "`ceist vocab ontology --accept`",
           "proposals": proposals, "skipped": skips,
           "not_proposed": dict(skipped)}
    _write_proposed(ontology_dir, doc)
    log(f"{len(proposals)} proposals, {len(skips)} skipped by the LLM → {ontology_dir / 'proposed.json'}; "
        f"LLM calls {run.calls}; {len(cands) - len(todo)} paths from the cache; {len(run.failures)} failed")
    log("\n".join(cost.summary(run.ledger)))
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


def accept(ontology_dir: Path, gate_cmd: list[str] | None = None, skip=(), log=print) -> dict | None:
    """The reviewed proposals through the gate; those it passes go into phrases.json,
    and each proposal's verdict is written back into proposed.json. `skip`: "demo" or
    "her", gate checks to leave out on a machine without that checkout. The gate's
    verdict, {} with nothing to accept, None when the gate failed."""
    ontology_dir = Path(ontology_dir)
    doc = read_proposed(ontology_dir)
    todo = [p for p in doc.get("proposals", []) if p.get("reviewed") and p.get("gate") != "merged"]
    if not todo:
        log('nothing to accept: no proposal is reviewed')
        return {}
    with tempfile.TemporaryDirectory() as d:
        cands = Path(d) / "candidates.json"
        cands.write_text(json.dumps([{"path": p["path"], "kind": p["kind"], "phrases": p["phrases"]} for p in todo]))
        cmd = (gate_cmd or [sys.executable, str(GATE)]) + [str(cands), "--ontology", str(ontology_dir)]
        cmd += [a for s in skip for a in (f"--{s}", "skip")]
        res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        log(f"the gate failed (exit {res.returncode}); nothing merged\n{res.stderr[-2000:]}")
        return None
    verdict = json.loads(res.stdout.strip().splitlines()[-1])
    passed = set(verdict["accepted"])
    for p in todo:
        k = f"{p['kind']} {p['path']}"
        p["gate"] = "merged" if k in passed else "rejected: " + verdict["rejected"].get(k, "?")
    write_phrases(ontology_dir, merge(load(ontology_dir), [p for p in todo if p["gate"] == "merged"]))
    _write_proposed(ontology_dir, doc)
    log(f"{len(passed)} of {len(todo)} reviewed proposals passed the gate and are in phrases.json")
    for line in verdict.get("checks", []):
        log("  " + line)
    return verdict


def _write_proposed(ontology_dir: Path, doc: dict) -> None:
    (Path(ontology_dir) / "proposed.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def _is_class(token: str) -> bool:
    return token != "^" and not re.fullmatch(r"[PO]\d+[a-z]?", token)


def _extends(path: str, other: str) -> bool:
    """`path` is `other` with more in front: it reaches only nodes `other` reaches, so a phrase
    on both means one node (025's same-meaning test, at the path)."""
    a, b = path.split(), other.split()
    return len(a) > len(b) and a[-len(b):] == b


def _bare_noun(phrase: str) -> bool:
    # ponytail: one word not ending in "ed" counts as a noun; a POS tagger if this misfires
    return " " not in phrase and not phrase.endswith("ed")


def _unique_in_models(p: dict, graphs: list[dict]) -> bool:
    """The path reaches at most one node of its kind in every graph."""
    one = {"entries": [{"path": p["path"], "kind": p["kind"], "phrases": ["x"]}]}
    counts = [sum(1 for e in crm.ontology_entries(g, one) if e["kind"] == p["kind"]) for g in graphs]
    return any(counts) and max(counts) == 1


def _share(todo: list[dict], doc: dict, dropped: dict) -> None:
    """A phrase on several proposals ending in the same property keeps one: for links that
    differ only in their start class, the path without it; else the one reaching most nodes."""
    holders: dict[tuple, list[dict]] = {}
    for p in todo:
        for ph in p["phrases"]:
            if ph not in dropped.get(id(p), {}):
                holders.setdefault((ph, p["kind"], p["path"].split()[-1]), []).append(p)
    for (ph, kind, _), ps in holders.items():
        if len(ps) < 2:
            continue
        tails = {" ".join(p["path"].split()[1:]) for p in ps}
        tail = next(iter(tails))
        # a link's start class rarely changes the question; an object type's or an event's date does
        if kind == "link" and len(tails) == 1 and tail and all(_is_class(p["path"].split()[0]) for p in ps):
            home = next((p for p in todo if p["path"] == tail and p["kind"] == kind), None)
            if home is None:
                home = {"path": tail, "kind": kind, "nodes": 0, "graphs": 0, "phrases": [],
                        "reason": "the phrasings its start-class variants shared", "from": []}
                doc["proposals"].append(home)
                todo.append(home)
            home["nodes"] += sum(p["nodes"] for p in ps)
            home["graphs"] = max([home["graphs"]] + [p["graphs"] for p in ps])
            home["from"] = sorted(set(home.get("from", []) + [p["path"] for p in ps]))
            home["phrases"].append(ph)
            keep = home
        else:
            keep = max(ps, key=lambda p: (p["nodes"], p["graphs"]))
        for p in ps:
            if p is not keep:
                dropped.setdefault(id(p), {})[ph] = f"shared by {len(ps)} sibling paths; kept on {keep['path']}"


def review(ontology_dir: Path, graph_dirs, log=print) -> list[str]:
    """The checks a person made by hand after the first live run, on each proposal no person
    has reviewed: a verdict and reason on each, "reviewed": "auto" on what survives.
    The review report as markdown lines."""
    ontology_dir = Path(ontology_dir)
    doc = read_proposed(ontology_dir)
    generic = set(json.loads((ontology_dir / GENERIC).read_text())["phrases"])
    existing: dict[str, set] = {}
    for e in load(ontology_dir)["entries"]:
        for ph in e["phrases"]:
            existing.setdefault(ph, set()).add(e["path"])
    todo = [p for p in doc.get("proposals", []) if p.get("reviewed") is not True and p.get("gate") != "merged"]
    graphs = [d["graph"][0] if "graph" in d else d for d in graph_docs(graph_dirs)]
    # a re-run sees only the phrases an earlier review kept: carry its reasons for the rest
    dropped = {id(p): dict(p.get("review", {}).get("dropped", {})) for p in todo}
    for p in todo:
        for ph in p["phrases"]:
            if ph in generic:
                dropped.setdefault(id(p), {})[ph] = "too generic"
    _share(todo, doc, dropped)
    for p in todo:
        mine = dropped.setdefault(id(p), {})
        for ph in p["phrases"]:
            clash = sorted(q for q in existing.get(ph, ()) if not _extends(p["path"], q))
            if ph in mine:
                continue
            if clash:
                mine[ph] = f"clash: already on {', '.join(clash)}"
            elif _bare_noun(ph) and not _unique_in_models(p, graphs):
                mine[ph] = "a bare noun, and the path reaches several fields in a model"
        kept = [ph for ph in p["phrases"] if ph not in mine]
        why = "; ".join(f"'{ph}': {r}" for ph, r in mine.items())
        if kept:
            p.update(phrases=kept, reviewed="auto", checks=list(CHECKS))
            p["review"] = {"verdict": "trimmed" if mine else "kept", "reason": why or "passed every check",
                           "dropped": mine}
        else:
            p.update(reviewed=False)
            p["review"] = {"verdict": "dropped", "reason": why, "dropped": mine}
    hand = [s for s in doc.get("skipped", []) if s["kind"] == "date" and s["nodes"] >= HIGH_USE]
    doc["needs_hand"] = [{"path": s["path"], "kind": s["kind"], "nodes": s["nodes"]} for s in hand]
    _write_proposed(ontology_dir, doc)
    verdicts = Counter(p["review"]["verdict"] for p in todo)
    log(f"review: {len(todo)} proposals: {verdicts['kept']} kept, {verdicts['trimmed']} trimmed, "
        f"{verdicts['dropped']} dropped; {len(hand)} skipped high-use date paths need a hand phrasing")
    lines = ["## Review", "", f"{len(todo)} proposals reviewed: {verdicts['kept']} kept whole, "
             f"{verdicts['trimmed']} trimmed, {verdicts['dropped']} dropped.", "",
             "| verdict | kind | path | kept | dropped |", "| --- " * 5 + "|"]
    for p in todo:
        gone = "; ".join(f"{ph} ({r})" for ph, r in p["review"]["dropped"].items())
        kept = ", ".join(p["phrases"]) if p["reviewed"] else ""
        lines.append(f"| {p['review']['verdict']} | {p['kind']} | {p['path']} | {kept} | {gone} |")
    lines += ["", "### Needs a hand phrasing", "",
              f"Date paths reaching {HIGH_USE} or more nodes that the LLM skipped:", "",
              "| path | nodes | the LLM's reason |", "| --- " * 3 + "|"]
    lines += [f"| {s['path']} | {s['nodes']} | {s['skip']} |" for s in hand]
    return lines


def _tally_rows(verdict: dict) -> list[str]:
    bench = verdict.get("bench") or {}
    rows = ["| set | mode | before | after |", "| --- " * 4 + "|"]
    for name, modes in (bench.get("before") or {}).items():
        for mode, counts in modes.items():
            rows.append(f"| {name} | {mode} | {' / '.join(map(str, counts))} | "
                        f"{' / '.join(map(str, bench['after'][name][mode]))} |")
    return rows


def build(graph_dirs, ontology_dir: Path, out: Path, llm_cmd: str | None = None, model: str | None = None,
          max_calls: int = MAX_CALLS, review_only: bool = False, skip=(), gate_cmd: list[str] | None = None,
          log=print) -> int:
    """estimate → propose → review → gate → accept, and <ontology_dir>/build-report.md for a person to read."""
    ontology_dir, out = Path(ontology_dir), Path(out)
    said = []

    def note(line: str) -> None:
        said.append(line)
        log(line)
    audit = out / "audit.jsonl"
    seen = len(audit.read_text().splitlines()) if audit.exists() else 0
    rc = propose(graph_dirs, ontology_dir, out, llm_cmd, model, max_calls, log=note)
    if rc:
        log("the proposals are incomplete; fix that and re-run (answered paths are cached)")
        return rc
    doc = read_proposed(ontology_dir)
    this_run = audit.read_text().splitlines()[seen:] if audit.exists() else []
    calls = sum(1 for line in this_run if not json.loads(line)["cached"])
    lines = ["# Ontology build report", "",
             f"Graphs: {', '.join(str(d) for d in graph_dirs)}.", "",
             f"Estimate: {said[0]}", "",
             f"Generated: {len(doc['proposals'])} paths with phrasings; {len(doc['skipped'])} skipped by the LLM; "
             f"LLM calls {calls}; not proposed: {', '.join(f'{n} {k}' for k, n in doc.get('not_proposed', {}).items())}.", ""]
    lines += review(ontology_dir, graph_dirs, log) + [""]
    if not review_only:
        verdict = accept(ontology_dir, gate_cmd, skip, log)
        if verdict is None:
            return 1
        proposals = read_proposed(ontology_dir)["proposals"]
        gated = [p for p in proposals if str(p.get("gate", "")).startswith("rejected")]
        merged = [p for p in proposals if p.get("gate") == "merged"]
        lines += ["## Rejected by the gate", "", "| kind | path | phrases | why |", "| --- " * 4 + "|"]
        lines += [f"| {p['kind']} | {p['path']} | {', '.join(p['phrases'])} | {p['gate'][len('rejected: '):]} |"
                  for p in gated]
        lines += ["", "## Accepted into phrases.json", "", "| kind | path | phrases |", "| --- " * 3 + "|"]
        lines += [f"| {p['kind']} | {p['path']} | {', '.join(p['phrases'])} |" for p in merged]
        lines += ["", "## Bench and demo bank", "", "Bench counts: " + " / ".join(SCORES) + ".", ""]
        lines += _tally_rows(verdict)
        demo = verdict.get("demo") or {}
        lines += ["", f"Demo bank before: {demo.get('before', 'not run')}", "",
                  f"Demo bank after: {demo.get('after', 'not run')}", ""]
        lines += [f"- {c}" for c in verdict.get("checks", [])] + [""]
    runs = cost.read_runs([out]) if (out / "audit.jsonl").exists() else []
    lines += cost.summary([r for run in runs for r in run["spent"]])
    if not calls:
        lines += ["", "This build made no LLM calls: every answer came from the cache, so it cost $0."]
    if any(run["prompts"] for run in runs):
        lines += [""] + cost.against(runs)
    report = ontology_dir / "build-report.md"
    report.write_text("\n".join(lines) + "\n")
    log(f"build report → {report}")
    return 0
