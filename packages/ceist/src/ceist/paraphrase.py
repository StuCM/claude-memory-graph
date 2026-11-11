"""Paraphrases of what Ceist can already answer (OVERNIGHT-style, PRIOR-ART.md): a site's canonical
sentences from its schema, and new phrasings for their links, values and dates from two sources,
each candidate carrying the questions and plans the site gate checks it on.

    bge mining (free)   short phrases of the site's own text, ranked against each element's phrasing
    LLM (`--llm`)       everyday rewordings of the canonical sentences, about 50 to a call

No record data goes to the LLM: a canonical sentence names models, fields and list values only.
"""

import json
import re
from collections import Counter

from .narrate import narrate
from .plan import DateRange, HasValue, LinkTo, Plan
from .questions import _link_question, _plural, plan_target
from .text import STOP, terms

BATCH = 50
VERSION = "1"
MIN_SIMILARITY = 0.9       # bge-small: unrelated short phrases sit around 0.6-0.75, a role's volunteer at 0.82
MAX_NGRAMS = 2000
NEAREST = 3
PROMPT = """You reword questions for an offline, no-LLM natural-language search over a site's records. \
Each sentence below is a question the search can already answer, written the way the search narrates it. \
"say" is the part of it to reword.

For each sentence give 3 to 5 everyday rewordings a member of the public might type: a whole question \
each ("q"), and "phrase", the words in q that say what "say" says. Keep every other part of the meaning; \
no record names, no numbers the sentence doesn't hold.

SENTENCES:
{sentences}

Reply with JSON only:
{{"sentences": [{{"id": <as given>, "rewordings": [{{"q": "...", "phrase": "..."}}]}}]}}
"""


def link_targets(vocab, tiles=None) -> dict[tuple[str, str], list[str]]:
    """{(model, link alias): the models its records point at}: from the records when the
    business data has them (a link with no target list may otherwise reach any CRM-compatible
    model), else the vocabulary's ends."""
    out: dict[tuple[str, str], set] = {}
    if tiles is not None:
        for rid, links in tiles.out.items():
            for alias, targets in links.items():
                out.setdefault((tiles.type_of[rid], alias), set()).update(
                    tiles.type_of[t] for t in targets if t in tiles.type_of)
    for r in vocab.relations():
        if "#" in r.name:
            continue
        for model, ends in r.ends:
            if not out.get((model, r.name)):
                out[(model, r.name)] = set(ends or r.range)
    return {k: sorted(v) for k, v in out.items() if v}


def canonical(vocab, tiles=None) -> list[dict]:
    """The site's canonical sentences: a plan per value, link (alone and with one value of the
    far model) and date, narrated, with the element it phrases and its target."""
    values: dict[str, list] = {}
    for x in vocab.values():
        for m in x.owners:
            if x.phrase == x.label.lower():
                values.setdefault(m, []).append(x)
    out = []

    def add(plan: Plan, element: dict, say: str):
        out.append({"id": len(out), "sentence": narrate(plan), "say": say, "element": element,
                    "target": plan_target(plan)})

    for m in sorted(vocab.models):
        for x in sorted(values.get(m, []), key=lambda x: (x.field, x.label)):
            add(Plan(m, [HasValue(x.field, x.value, x.label)]),
                {"layer": "client", "model": m, "nodegroup": vocab.group_of(m, x.field), "node": x.field,
                 "value": x.label, "key": f"value {m}.{x.field}={x.label.lower()}"}, x.label)
        for d in vocab.date_fields():
            if m in d.owners:
                add(Plan(m, [DateRange(d.field, "1900-01-01", None, d.label)]),
                    {"layer": "client", "kind": "date", "model": m, "nodegroup": vocab.group_of(m, d.field),
                     "node": d.field, "key": f"date {m}.{d.field}"}, d.label)
    for (m, alias), targets in sorted(link_targets(vocab, tiles).items()):
        label = str((vocab.node(m, alias) or {}).get("name") or alias).lower()
        element = {"layer": "client", "kind": "link", "model": m, "nodegroup": vocab.group_of(m, alias),
                   "node": alias, "key": f"link {m}.{alias}"}
        for t in targets:
            add(Plan(m, [LinkTo(alias, Plan(t), style="field")]), element, label)
            fields = {}
            for x in values.get(t, []):
                fields.setdefault(x.field, x)
            for x in fields.values():
                add(Plan(m, [LinkTo(alias, Plan(t, [HasValue(x.field, x.value, x.label)]), style="field")]),
                    element, label)
    return out


def _checks(c: dict, phrase: str) -> list[dict]:
    """Template questions saying a canonical sentence's element with `phrase`, each with the target
    the sentence has."""
    t, el = c["target"], c["element"]
    many = _plural(t["model"])
    if "value" in el:
        return [{"q": f"how many {phrase} are there?", "target": dict(t, count=True)},
                {"q": f"which {many} are {phrase}?", "target": t}]
    if el["kind"] == "date":
        return [{"q": f"which {many} were {phrase} after 1900?", "target": t}]
    if len(t["conditions"]) != 1:
        return []
    return [{"q": _link_question(phrase, many, t["conditions"][0]["link"]), "target": t}]


def _candidate(c: dict, phrase: str, source: str, checks: list[dict]) -> dict:
    return dict(c["element"], key=f"{c['element']['key']}: {phrase}", phrases=[phrase], rule=[source],
                checks=checks)


def site_texts(vocab, docs=()) -> list[str]:
    """The site's own prose: each record's text values other than its name, and the docs given."""
    from .alizarin import _strings
    text_nodes = {n["nodeid"] for m in vocab.models.values() for n in m.nodes if n.get("datatype") == "string"}
    out = []
    for r in vocab.resources:
        name = vocab.names.get((r.get("resourceinstance") or {}).get("resourceinstanceid"), "")
        for t in r.get("tiles") or []:
            out += [s for k, v in (t.get("data") or {}).items() if k in text_nodes for s in _strings(v) if s != name]
    return out + [p.read_text() for p in docs]


def ngrams(texts: list[str], most: int = MAX_NGRAMS) -> list[str]:
    """Phrases of one to three words, starting and ending on a content word, seen at least twice."""
    seen = Counter()
    for text in texts:
        for sentence in re.split(r"[.;:!?\n]", text.lower()):
            words = re.findall(r"[a-z][a-z'-]*", sentence)
            for n in (1, 2, 3):
                for i in range(len(words) - n + 1):
                    gram = words[i:i + n]
                    if gram[0] not in STOP and gram[-1] not in STOP and terms(gram[0]) and terms(gram[-1]):
                        seen[" ".join(gram)] += 1
    return [g for g, n in seen.most_common(most) if n >= 2]


def mined(canon: list[dict], texts: list[str], encoder, said: set[str], names: set[str] = frozenset()) -> list[dict]:
    """bge mining: for each element a canonical sentence phrases, the NEAREST site phrases to its
    phrasing (at least MIN_SIMILARITY), with their checks. Never a phrase already said, one holding a
    word of a record's name (`names`: "teacher cuain"), or one inside another element's phrase
    ("officer" for police officer, inside "fire officer")."""
    import numpy as np
    grams = [g for g in ngrams(texts) if g not in said and not set(g.split()) & names]
    if not grams:
        return []
    by_element = {}
    for c in canon:
        by_element.setdefault(c["element"]["key"], c)
    first = list(by_element.values())
    a = np.asarray(encoder.encode([c["say"].lower() for c in first]))
    b = np.asarray(encoder.encode(grams))
    sims = a @ b.T
    out = []
    for i, c in enumerate(first):
        own = c["say"].lower()
        for j in sims[i].argsort()[::-1][:NEAREST]:
            inside = any(f" {grams[j]} " in f" {p} " for p in said if p != own)
            near = sims[i, j] >= MIN_SIMILARITY and grams[j] != own and not inside
            checks = _checks(c, grams[j]) if near else []
            if checks:
                out.append(_candidate(c, grams[j], "bge", checks))
    return out


def prompts(canon: list[dict]) -> list[tuple[list[dict], str]]:
    """(batch, prompt) per call: the sentences and what to reword, nothing else."""
    out = []
    for i in range(0, len(canon), BATCH):
        batch = canon[i:i + BATCH]
        text = json.dumps([{"id": c["id"], "sentence": c["sentence"], "say": c["say"]} for c in batch],
                          ensure_ascii=False, indent=1)
        out.append((batch, PROMPT.format(sentences=text)))
    return out


def check(reply, batch: list[dict]) -> list[str]:
    if not isinstance(reply, dict) or not isinstance(reply.get("sentences"), list):
        return ['the reply must be {"sentences": [...]}']
    ids, errors = {c["id"] for c in batch}, []
    for s in reply["sentences"]:
        if not isinstance(s, dict) or s.get("id") not in ids:
            errors.append(f"unknown sentence {s.get('id') if isinstance(s, dict) else s!r}")
            continue
        for r in s.get("rewordings") or []:
            q, p = (r.get("q"), r.get("phrase")) if isinstance(r, dict) else (None, None)
            if not (isinstance(q, str) and isinstance(p, str) and p.strip() and p.lower() in q.lower()
                    and len(p.split()) <= 5):
                errors.append(f"sentence {s['id']}: each rewording needs q, and a phrase of 1 to 5 words in it")
    return errors


def paraphrased(canon: list[dict], runner) -> list[dict]:
    """LLM paraphrase: one call per BATCH sentences through `runner` (pipeline.Runner, cached and
    audited); each rewording a candidate for its sentence's element, checked on the rewording itself."""
    from .pipeline import _key
    out = []
    for batch, text in prompts(canon):
        reply = runner.ask(_key("paraphrase", VERSION, text), text, lambda r, b=batch: check(r, b),
                           {"kind": "paraphrase", "sentences": len(batch)})
        by_id = {c["id"]: c for c in batch}
        for s in (reply or {}).get("sentences", []):
            c = by_id[s["id"]]
            for r in s.get("rewordings") or []:
                phrase = r["phrase"].strip().lower()
                if phrase != c["say"].lower():
                    out.append(_candidate(c, phrase, "llm", [{"q": r["q"].strip(), "target": c["target"]}]))
    return out
