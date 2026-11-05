"""Growing a project's vocabulary from use, the "learn" step of the loop:

    use     the app records every phrase ceist couldn't place, and every
            "did you mean" option a person picked              (record)
    learn   the log → proposals: picks are confirmed by a person already;
            the rest go to an LLM, which assigns each a node or "none"
                                            (`ceist vocab learn`, then `ceist vocab assign`)
    review  a person approves the proposals they agree with
    merge   the approved phrasings join the vocabulary files (`ceist vocab merge`)
    build   `ceist vocab assemble`, then `ceist eval` on held-out questions

Nothing is trained: the vocabulary is phrasings per node, and the loop adds the
phrasings real people use. Keep the questions that measure the vocabulary
(`ceist eval`) apart from the log that grows it — `learn --exclude` drops any
logged phrase that appears in them, so the measure never marks its own work.

A log line (JSONL, one per event):

    {"model": "Monument", "q": "which buildings were turned down for listing?",
     "phrase": "turned down", "slot": "property",
     "options": [{"node": "designation_type", "label": "Designation Type"}, …],
     "chosen": {"node": "designation_type", "qualifier": null, "end_node": null} | null}

`options` are the "did you mean" offers, `chosen` the one the person picked
(null: nothing offered fitted, or they gave up).

Privacy: the log is what reaches an LLM, so it never holds record data.
`from_grounding` masks the question and the phrase before they are written:
the records it named become `<Type>`, quoted text `<text>`, other
capitalised words `<Name>`, long numbers `<number>` (years stay: they are
how dates are asked). A phrase that is itself a name is not logged at all:
it is a record, not vocabulary. A record name typed in lowercase that the
grounding didn't name gets through. The `learn` prompt carries the masked items inline,
so the LLM is never pointed at a file.
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path

from .ground import AUX, IMPERATIVE, WH
from .text import STOP

PROPOSALS = "ceist.proposals/1"
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").lower()).strip()


def option(item) -> dict:
    """A matching.Item as a log option ({node, qualifier, end_node, label});
    items keyed (node, qualifier value, end node), as ceist's Arches ones are."""
    key = item.key if isinstance(item.key, tuple) else (item.key, None, None)
    node, qual, end = (list(key) + [None, None, None])[:3]
    return {"node": node, "qualifier": qual, "end_node": end, "label": item.label}


def record(path: str | Path, model: str, question: str, phrase: str, slot: str,
           options: list | None = None, chosen=None) -> None:
    """Append one event to the learning log. `options` and `chosen` may be
    matching.Items or option dicts. Best-effort: a log must never break a search."""
    def as_option(x):
        return x if isinstance(x, dict) else option(x)
    entry = {"model": model, "q": question, "phrase": phrase, "slot": slot,
             "options": [as_option(o) for o in options or []],
             "chosen": as_option(chosen) if chosen is not None else None,
             "ts": int(time.time())}
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


_WORD = re.compile(r"[A-Za-z][\w'’-]*|\d[\d,.]*")
_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|‘[^’]*’|(?<!\w)'[^']+'(?!\w)")
_YEAR = re.compile(r"(1[0-9]|20)\d\d(s)?$")
_TAG = re.compile(r"<[A-Za-z]+>")
_COMMON = WH | AUX | IMPERATIVE | STOP     # a capitalised first word that names nothing


def mask(question: str, grounding=None) -> str:
    """The question with record data taken out, for the learning log: the
    records the grounding named → <Type> (in any case), quoted text → <text>,
    other capitalised words → <Name> (the first only when it isn't a
    question or function word), numbers other than years → <number>. Values
    and dates the grounding placed are schema words, kept. A record name
    typed in lowercase that the grounding didn't name is not caught."""
    return _mask(question, grounding, at_start=True)


def _mask(text: str, grounding, at_start: bool) -> str:
    keep = set()
    if grounding is not None:
        for v in getattr(grounding, "values", []) or []:
            keep |= {w.lower() for w in _WORD.findall(v.phrase)}
        for d in getattr(grounding, "dates", []) or []:
            keep |= {w.lower() for w in _WORD.findall(d.phrase)}
    anchor_terms: dict[str, str] = {}
    for a in getattr(grounding, "anchors", None) or []:
        for t in list(a.match_terms) + _WORD.findall(a.name or ""):
            anchor_terms[t.lower()] = a.type or "Record"
    text = _QUOTED.sub("<text>", text)
    out, first, prev, pos = [], at_start, None, 0
    for m in _WORD.finditer(text):
        w = m.group(0)
        lw = w.lower()
        if lw.endswith(("'s", "’s")):
            lw = lw[:-2]                        # "Ada's" names Ada
        if lw in anchor_terms:
            tag = f"<{anchor_terms[lw]}>"
        elif w[0].isdigit():
            tag = None if _YEAR.match(w) else "<number>"
        elif (w[0].isupper() and lw not in keep and w != "I"
              and not (first and lw in _COMMON)):
            tag = "<Name>"
        else:
            tag = None
        first = False
        between = text[pos:m.start()]
        if tag is not None and tag == prev and not between.strip():
            pos = m.end()                       # "Ada Lovelace" → one <Person>
            continue
        out.append(between + (tag or w))
        prev, pos = tag, m.end()
    out.append(text[pos:])
    return "".join(out)


def _masked_phrase(phrase: str, question: str, grounding) -> str | None:
    """The phrase as written in the question, masked as the question is;
    None when it is all record data (a name is a record, not vocabulary)."""
    m = re.search(re.escape(phrase), question, re.I)
    if m is None:
        return phrase
    written = question[m.start():m.end()]
    masked = _mask(written, grounding, at_start=m.start() == 0)
    if masked == written:
        return phrase
    if not _WORD.findall(_TAG.sub("", masked)):
        return None
    return masked


def from_grounding(path: str | Path, question: str, grounding) -> int:
    """Log every phrase the planner couldn't place in a question (its
    grounding's `unplaced`), question and phrase masked (`mask`); how many.
    Call it after `interpret`. Phrases that are names aren't logged."""
    masked, n = mask(question, grounding), 0
    for u in getattr(grounding, "unplaced", []) or []:
        phrase = _masked_phrase(u["phrase"], question, grounding)
        if phrase is None:
            continue
        record(path, u.get("model", ""), masked, phrase, u["slot"], u.get("options"))
        n += 1
    return n


def _read(path) -> list[dict]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue                         # a torn line from a crash mid-write
    return out


def _known(bundle: dict) -> dict:
    """model → {normalised phrase} already in the vocabulary."""
    return {m: {_norm(p) for e in model["entries"] for p in e["phrases"]}
            for m, model in bundle["models"].items()}


def _fits(node: dict, slot: str) -> bool:
    if slot == "date":
        return node.get("kind") == "date"
    if slot.startswith("link:"):
        return node.get("kind") == "link" and slot[5:] in (node.get("targets") or [])
    return node.get("kind") == "property"


def proposals(log_path, bundle: dict, exclude=None) -> dict:
    """The log, as proposals to review: `confirmed` (a person picked the node)
    and `to_assign` (nobody did: for an LLM to propose, then a person)."""
    held_out = set()
    if exclude:
        held_out = {(c["model"], _norm(c["phrase"]))
                    for c in json.loads(Path(exclude).read_text())["cases"]}
    known = _known(bundle)
    picked: dict[tuple, dict] = {}
    unplaced: dict[tuple, dict] = {}
    skipped = {"held_out": 0, "known": 0, "unknown_model": 0}
    for ev in _read(log_path):
        model, phrase = ev.get("model"), _norm(ev.get("phrase", ""))
        if not phrase:
            continue
        if model not in bundle["models"]:
            skipped["unknown_model"] += 1
            continue
        if (model, phrase) in held_out:
            skipped["held_out"] += 1
            continue
        if phrase in known.get(model, set()):
            skipped["known"] += 1           # added since it was logged
            continue
        ch = ev.get("chosen")
        if ch and ch.get("node"):
            key = (model, ch["node"], ch.get("qualifier"), ch.get("end_node"), phrase)
            p = picked.setdefault(key, {"model": model, "phrase": phrase, "node": ch["node"],
                                        "qualifier": ch.get("qualifier"),
                                        "end_node": ch.get("end_node"), "seen": 0,
                                        "questions": [], "approve": True})
            p["seen"] += 1
            if len(p["questions"]) < 3 and ev.get("q") not in p["questions"]:
                p["questions"].append(ev.get("q"))
            continue
        key = (model, ev.get("slot", "property"), phrase)
        u = unplaced.setdefault(key, {"model": model, "slot": key[1], "phrase": phrase,
                                      "seen": 0, "questions": [], "offered": []})
        u["seen"] += 1
        if len(u["questions"]) < 3 and ev.get("q") not in u["questions"]:
            u["questions"].append(ev.get("q"))
        for o in ev.get("options") or []:
            if o.get("node") and o["node"] not in u["offered"]:
                u["offered"].append(o["node"])
    # one phrase picked as two different things: a person decides, not the count
    meanings = defaultdict(int)
    for p in picked.values():
        meanings[(p["model"], p["phrase"])] += 1
    for p in picked.values():
        if meanings[(p["model"], p["phrase"])] > 1:
            p["approve"], p["conflict"] = False, True
    picked_phrases = {(p["model"], p["phrase"]) for p in picked.values()}
    to_assign = []
    for u in unplaced.values():
        if (u["model"], u["phrase"]) in picked_phrases:
            continue                         # someone picked it elsewhere: that wins
        nodes = bundle["models"][u["model"]]["nodes"]
        u["candidates"] = sorted(a for a, n in nodes.items() if _fits(n, u["slot"]))
        u["assign"] = None                   # the LLM writes {node, qualifier?, end_node?} or "none"
        u["approve"] = False                 # a person sets this
        to_assign.append(u)
    by_seen = lambda x: (-x["seen"], x["model"], x["phrase"])
    return {"format": PROPOSALS,
            "confirmed": sorted(picked.values(), key=by_seen),
            "to_assign": sorted(to_assign, key=by_seen),
            "skipped": skipped}


PROMPT = """You are the "learn" step of a no-LLM natural-language search over Arches data. People \
asked questions using the phrases below, and the search couldn't tell which field each meant. \
Assign each one, so the next vocabulary build knows it.

Everything you need is in this message: there are no files to read. Names and numbers in the \
questions are masked (<Person>, <Name>, <number>, …) on purpose; don't guess them.

Each item has an index "i", the model, the slot the phrase sat in, the phrase, up to three \
example questions, and its "candidates": the fields that fit where the phrase sat, with their \
labels. "qualifiers" lists how the model's existing entries pair a field with a value (a role \
such as Architect, a phase type such as Demolition).

Reply with ONLY a JSON array, one object per item you can judge:
  {{"i": <index>, "assign": {{"node": "<alias from candidates>"}}}}   — the field the phrase means;
      add "qualifier": {{"node": "<alias>", "value": "<label>"}} when the meaning needs a value too,
      copying one from "qualifiers"; add "end_node" for a date that is an event's start
  {{"i": <index>, "assign": "none"}}   — no field fits: the question asks for something the data
      doesn't hold, or the phrase isn't about a field at all.
Judge by the example questions, not the phrase alone. Check that your reply parses as JSON.

Items:
{items}
"""


def prompt(props: dict, bundle: dict) -> str:
    """The assignment instruction with the items inline: only the masked
    questions and the schema's own labels, never a path."""
    items = []
    for i, u in enumerate(props.get("to_assign", [])):
        model = bundle["models"].get(u["model"], {})
        nodes = model.get("nodes", {})
        quals = sorted({(e["node"], e["qualifier"]["node"], str(e["qualifier"]["value"]))
                        for e in model.get("entries", []) if e.get("qualifier")})
        items.append({"i": i, "model": u["model"], "slot": u["slot"], "phrase": u["phrase"],
                      "questions": u.get("questions", []),
                      "candidates": [{"node": a, **{k: v for k, v in nodes[a].items()
                                                    if k in ("label", "kind", "targets")}}
                                     for a in u.get("candidates", []) if a in nodes],
                      "qualifiers": [{"node": n, "qualifier": {"node": q, "value": v}}
                                     for n, q, v in quals]})
    return PROMPT.format(items=json.dumps(items, indent=1, ensure_ascii=False))


def assign(props: dict, reply: str) -> tuple[int, list[str]]:
    """Fill "assign" on the proposals from the LLM's reply to `prompt`;
    (how many, errors). A node outside the item's candidates is refused.
    "approve" is never touched: a person sets it."""
    from .bundle import parse_reply
    todo, done, errors = props.get("to_assign", []), 0, []
    try:
        items = parse_reply(reply)
    except ValueError as e:
        return 0, [f"the reply is not JSON: {e}"]
    if not isinstance(items, list):
        return 0, [f"the reply is a JSON {type(items).__name__}, not an array of items"]
    for a in items:
        i = a.get("i") if isinstance(a, dict) else None
        if not isinstance(i, int) or not 0 <= i < len(todo):
            errors.append(f"no item {i!r}" if isinstance(a, dict) else f"{a!r} is not an item")
            continue
        u, value = todo[i], a.get("assign")
        if value != "none" and not (isinstance(value, dict)
                                    and value.get("node") in u.get("candidates", [])):
            errors.append(f"item {i} ('{u['phrase']}'): {value!r} is not one of its candidates")
            continue
        u["assign"] = value
        done += 1
    return done, errors


def _entry_key(e: dict):
    q = e.get("qualifier") or {}
    return (e["node"], q.get("value"), e.get("end_node"))


def merge(proposals_path, vocab_dir, bundle: dict) -> dict:
    """Add every approved phrasing to the vocabulary files; what was done.
    A phrase goes into the entry for the same node, qualifier and end node,
    or a new entry when there is none."""
    props = json.loads(Path(proposals_path).read_text())
    if props.get("format") != PROPOSALS:
        raise ValueError(f"{proposals_path} is not a {PROPOSALS} file")
    todo = []
    for p in props.get("confirmed", []):
        if p.get("approve"):
            todo.append((p["model"], p["phrase"], p["node"], p.get("qualifier"),
                         p.get("end_node")))
    for u in props.get("to_assign", []):
        a = u.get("assign")
        if u.get("approve") and isinstance(a, dict) and a.get("node"):
            q = a.get("qualifier")
            todo.append((u["model"], u["phrase"], a["node"],
                         q.get("value") if isinstance(q, dict) else q, a.get("end_node"),
                         q.get("node") if isinstance(q, dict) else None))
    done = {"added": 0, "new_entries": 0, "already": 0, "files": set(), "errors": []}
    files: dict[str, dict] = {}
    for item in todo:
        model, phrase, node, qual, end = item[:5]
        qual_node = item[5] if len(item) > 5 else None
        nodes = bundle["models"].get(model, {}).get("nodes", {})
        if node not in nodes:
            done["errors"].append(f"{model}: no node '{node}' (for '{phrase}')")
            continue
        path = Path(vocab_dir) / f"{model}.json"
        if model not in files:
            files[model] = (json.loads(path.read_text()) if path.exists()
                            else {"model": model, "entries": []})
        entries = files[model]["entries"]
        want = (node, qual, end)
        entry = next((e for e in entries if _entry_key(e) == want), None)
        if entry is None and qual:
            # the qualifier's node, from an existing entry with that value
            if qual_node is None:
                qual_node = next(((e.get("qualifier") or {}).get("node") for e in entries
                                  if (e.get("qualifier") or {}).get("value") == qual), None)
            if qual_node is None:
                done["errors"].append(f"{model}: qualifier '{qual}' for '{phrase}' names no node")
                continue
        if entry is None:
            entry = {"phrases": [], "kind": nodes[node].get("kind", "property"), "node": node}
            if end:
                entry["end_node"] = end
            if qual:
                entry["qualifier"] = {"node": qual_node, "value": qual}
            entries.append(entry)
            done["new_entries"] += 1
        if phrase in (_norm(p) for p in entry["phrases"]):
            done["already"] += 1
            continue
        entry["phrases"].append(phrase)
        done["added"] += 1
        done["files"].add(str(path))
    for model, data in files.items():
        path = Path(vocab_dir) / f"{model}.json"
        if str(path) in done["files"]:
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    done["files"] = sorted(done["files"])
    return done


def summary(props: dict) -> str:
    s = props["skipped"]
    lines = [f"confirmed by a person's pick: {len(props['confirmed'])} phrasing(s)",
             f"to assign (an LLM proposes, a person approves): {len(props['to_assign'])}",
             f"skipped: {s['known']} already in the vocabulary, {s['held_out']} in the held-out "
             f"questions, {s['unknown_model']} for models not in the bundle"]
    for p in props["confirmed"][:5]:
        lines.append(f"  + '{p['phrase']}' → {p['model']}.{p['node']}"
                     + (f" ({p['qualifier']})" if p.get("qualifier") else "") + f"  ×{p['seen']}")
    for u in props["to_assign"][:5]:
        lines.append(f"  ? '{u['phrase']}' ({u['model']}, {u['slot']})  ×{u['seen']}: "
                     f"{u['questions'][0] if u['questions'] else ''}")
    return "\n".join(lines)
