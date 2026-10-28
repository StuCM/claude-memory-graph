"""Growing a project's vocabulary from use, the "learn" step of the loop:

    use     the app records every phrase ceist couldn't place, and every
            "did you mean" option a person picked              (record)
    learn   the log → proposals: picks are confirmed by a person already;
            the rest go to an LLM, which assigns each a node or "none"
                                            (`ceist vocab learn`)
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
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path

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


def from_grounding(path: str | Path, question: str, grounding) -> int:
    """Log every phrase the planner couldn't place in a question (its
    grounding's `unplaced`); how many. Call it after `interpret`."""
    for u in getattr(grounding, "unplaced", []) or []:
        record(path, u.get("model", ""), question, u["phrase"], u["slot"], u.get("options"))
    return len(getattr(grounding, "unplaced", []) or [])


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

Edit {proposals} in place. For each item in "to_assign", set "assign" to:
- {{"node": "<alias>"}} — the field the phrase means, chosen from its "candidates" (the fields \
that fit where the phrase sat in the question). Add "qualifier": {{"node": "<alias>", "value": \
"<label>"}} when the meaning needs a value too (a role such as Architect, a phase type such as \
Demolition), using an existing entry's qualifier from the bundle; add "end_node" for a date that \
is an event's start, as the bundle's entries for that event do.
- "none" — when no field fits: the question asks for something the data doesn't hold, or the \
phrase isn't about a field at all.

Read the example "questions" for each phrase; judge by them, not the phrase alone. Read the \
bundle, {bundle}, for each model's nodes (labels, kinds, targets) and its existing entries — \
match how those are written. Do not change "approve": a person reviews and sets it. Do not \
touch "confirmed": those were picked by the people who asked. Keep the file valid JSON.
"""


def prompt(proposals_path, bundle_path) -> str:
    return PROMPT.format(proposals=proposals_path, bundle=bundle_path)


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
