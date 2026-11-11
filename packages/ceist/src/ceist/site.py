"""`ceist setup`: a new site's vocabulary from its own data dir, in one command.

    ceist setup <data dir> -o <out> [--base vocabularies/base] [--client <dir>] [--default shelter=Building]
                [--docs <dir>] [--questions <practice.json>] [--accept-risks]
                [--llm [--max-calls N] [--llm-cmd CMD] [--model M]]

The shared layers are used as they are: the CIDOC-CRM ontology layer, and each graph's base where
vocabularies/base has one (copied to <out>/base). A graph with no base gets one from the rules
(`vocab_rules`), and with --llm from `vocab pipeline --layer base`. The client layer gets the rules'
value plurals and role nouns (a plural naming a kind of thing, "hospitals", or the holder of a link,
"keyholders", is a type word with its value or link preset, on the one model the site's default names
when two hold it), bge-mined phrasings and, with --llm, the directed
fill and LLM paraphrases. Every candidate is gated on this site's own questions only: template
questions from its schema, filled with its own record names, compositions of its words, probes of its
record names and its practice questions (`compose`). setup.md opens with the status: wrong readings or
partial name binds exit 1 unless --accept-risks. Writes <out>/bundle.json, the
coverage report, the audit and setup.md. Ontology and base proposals for the shared layers are
the maintainers' build (`vocab ontology build`), never a site's.
"""

import json
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from . import bundle as _bundle
from . import vocab_rules as vr

BAD = ("wrong reading", "wrong")
PROBES = 50        # phrases of the site's own prose asked of every model, which must stay refused
_SMALL = {"the", "and", "for", "with", "from", "was", "were", "has", "have", "are", "who", "its"}


# ── judging a candidate (shared with bench/ontology/gate.py) ───────────────
def words(text: str) -> set[str]:
    """Its words' first four letters: a phrase can only change a question that has one."""
    return {w[:4] for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _SMALL}


def judge(before: dict, after: dict) -> tuple[int, list[str]]:
    """(right answers added, questions made worse): a right answer, right refusal or answer
    lost, or a wrong reading or wrong that was not there before."""
    gained = sum(1 for k, s in after.items() if s == "right" and before.get(k) != "right")
    worse = [q for (mode, q), s in after.items()
             if (s in BAD and before.get((mode, q)) not in BAD)]
    worse += [q for (mode, q), s in before.items()
              if s in ("right", "right refusal", "answered") and after.get((mode, q)) != s]
    return gained, sorted(set(worse))


def holding(cands: list[dict], questions: list[str]) -> list[dict]:
    """The candidates with a phrase in one of these questions."""
    text = " ".join(f" {q.lower()} " for q in questions)
    return [c for c in cands if any(f" {p} " in text for p in c["phrases"])]


def culprits(cands: list[dict], worse, lines: list[str]) -> list[tuple[dict, list[str]]]:
    """(candidate, the questions it makes worse) for each of `cands` that makes a question
    worse on its own, by halving: `worse(subset)` lists the questions a subset makes worse,
    `lines` those all of `cands` do. If neither half is worse alone, it takes them together:
    the ones without which the rest are no longer worse, or if none, every one of `cands`."""
    if len(cands) == 1:
        return [(cands[0], lines)]
    out = []
    for half in (cands[:len(cands) // 2], cands[len(cands) // 2:]):
        got = worse(half)
        if got:
            out += culprits(half, worse, got)
    if out:
        return out
    needed = [c for c in cands if not worse([x for x in cands if x is not c])]
    return [(c, lines) for c in needed or cands]


# ── the site's own benchmark ─────────────────────────────────────────────────
def value_checks(c: dict) -> list[dict]:
    """A value plural said as a type word: "how many shelters are there?" counts the model's records
    with that value."""
    if c["layer"] != "client" or "value" not in c:
        return []
    target = {"model": c["model"], "count": True, "conditions": [{"node": c["node"], "value": c["value"]}]}
    return [{"q": f"how many {p} are there?", "target": target} for p in c["phrases"]]


def role_checks(c: dict, vocab) -> list[dict]:
    """A role noun said of a record the link may point at: "list the keyholders of {Building}" finds
    the records holding the link to it."""
    if c["layer"] != "client" or "role" not in c:
        return []
    link = next((r for r in vocab.relations() if r.name == c["node"]), None)
    other = sorted(link.targets(c["model"]))[:1] if link else []
    target = {"model": c["model"], "count": False, "conditions": [{"node": c["node"], "link": t} for t in other]}
    return [{"q": f"list the {p} of {{{t}}}", "target": target} for p in c["phrases"] for t in other]


class SiteGate:
    """Candidates scored on the site's template questions, alone and then together, as
    bench/ontology/gate.py scores the shared layers on the bench sets, with the matcher the site
    answers with. `probes`: questions that hold none of the schema (its own prose), so a phrasing
    the vectors layer stretches to them shows as a refusal lost. Also every check in `compose`:
    compositions, name probes and the site's own `questions`."""

    def __init__(self, L: vr.Layers, cands: list[dict], matcher=None, probes: list[str] = (),
                 questions: list[dict] = (), generic: set[str] = frozenset()):
        from .alizarin import Tiles
        from .compose import compositions, name_probes
        from .ontology_vocab import load
        from .questions import templated
        self.L, self.cands, self.matcher = L, cands, matcher
        self.vocab = L.vocab()
        self.tiles = Tiles(self.vocab)
        only = {(c["model"], c["node"]) for c in cands if c.get("node") and "value" not in c}
        ontology = load(L.ontology_dir)
        every = self.bundle(cands)
        said = self.vocab.with_bundle(every)
        self.items = templated(said, ontology, every, only)
        for c in cands:
            self.items += [dict(x, expect="answer", model=c["model"], shape="site check")
                           for x in c.get("checks") or value_checks(c) or role_checks(c, self.vocab)]
        self.items += [{"q": q, "expect": "refuse", "reason": "the site's prose, not its schema", "shape": "probe"}
                       for q in probes]
        self.items += compositions(said, self.tiles) + name_probes(said, generic) + list(questions)
        self.items = list({o["q"]: o for o in self.items}.values())
        self.before = self.scores([])

    def bundle(self, cands: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as d:
            base, client = Path(d) / "base", Path(d) / "client"
            shutil.copytree(self.L.base_dir, base)
            shutil.copytree(self.L.client_dir, client)
            vr.apply(cands, self.L.ontology_dir, base, client)
            return _bundle.layered(self.L.graphs, base, client, ontology_dir=self.L.ontology_dir)[0]

    def scores(self, cands: list[dict], only: set[str] | None = None) -> dict:
        """{("site", question): score} for the items (only those sharing one of `only`'s words)."""
        from . import compose
        from .plan import interpret
        from .questions import fill, score
        b = self.bundle(cands)
        v = self.vocab.with_bundle(b)
        ends = {e["node"]: e["end_node"] for m in b["models"].values() for e in m["entries"] if e.get("end_node")}
        out = {}
        for o in self.items:
            if only is not None and not only & words(o["q"]):
                continue
            if o.get("shape") in compose.SHAPES:
                out[("site", o["q"])] = compose.score(o, interpret(v, o["q"], matcher=self.matcher), self.tiles)
                continue
            q = fill(o["q"], v)
            if q is not None:
                out[("site", o["q"])] = score(o, interpret(v, q, matcher=self.matcher), ends)
        return out

    def run(self, log=print) -> dict:
        from . import compose
        rejected, runs = {}, {(): self.before}
        for c in self.cands:
            gained, worse = judge(self.before, {**self.before, **self.scores([c], words(" ".join(c["phrases"])))})
            if worse:
                rejected[c["key"]] = f"site gate: worse on {len(worse)}, e.g. {worse[0]}"
            elif not gained:
                rejected[c["key"]] = "site gate: adds no right answer"
        passing = [c for c in self.cands if c["key"] not in rejected]
        log(f"site gate: {len(self.items)} questions; {len(passing)} of {len(self.cands)} pass alone")

        def together(cs: list[dict]) -> dict:
            ks = tuple(sorted(c["key"] for c in cs))
            if ks not in runs:
                runs[ks] = self.scores(cs)
            return runs[ks]

        def worse_of(cs: list[dict]) -> list[str]:
            return judge(self.before, together(cs))[1]

        def worse_on(asked: set[str]):
            """worse_of, re-asking only the questions sharing a word with these."""
            return lambda cs: judge(self.before, {**self.before, **self.scores(cs, asked)})[1]

        # a composition holds several candidates' phrases: halving finds which of them, not holding
        composed = {o["q"] for o in self.items if o.get("shape") in compose.SHAPES}
        while passing:
            worse = worse_of(passing)
            if not worse:
                break
            one_piece = [q for q in worse if q not in composed]
            suspects = holding(passing, worse) or list(passing)
            hit = [(c, one_piece) for c in holding(passing, one_piece)] or culprits(
                suspects, worse_on(words(" ".join(worse))), worse)
            for c, lines in hit:
                rejected[c["key"]] = f"site gate, together: {lines[0]}"
                passing.remove(c)
        after = together(passing)
        return {"accepted": [c["key"] for c in passing], "rejected": rejected,
                "tally": {"before": _counts(self.before), "after": _counts(after)}, "after": after}


def _counts(scored: dict) -> dict:
    return dict(Counter(scored.values()))


# ── the client layer's own rules ─────────────────────────────────────────────
def settle_type_words(cands: list[dict], defaults: dict[str, str]) -> tuple[list[dict], dict, list[str]]:
    """Value plurals and role nouns as type words with their value or link preset: where two models
    hold it, only the one the site default names keeps it; without a default none does, and grounding
    keeps asking "did you mean". (kept, {key: {phrase: why}}, [values and roles that need a default])."""
    def said(c: dict) -> str:
        return (c.get("value") or c.get("role") or "").lower() if c["layer"] == "client" else ""

    owners: dict[str, set] = {}
    for c in cands:
        if said(c):
            owners.setdefault(said(c), set()).add(c["model"])
    kept, dropped, ask = [], {}, []
    for c in cands:
        word = said(c)
        held = owners.get(word, set())
        if len(held) < 2:
            kept.append(c)
            continue
        default = defaults.get(word)
        if default == c["model"]:
            kept.append(c)
            continue
        why = (f"site default: {word} means {default}" if default else
               f"{c.get('value') or word} is held by {', '.join(sorted(held))}: no site default, so it stays a "
               "'did you mean'")
        dropped[c["key"]] = {p: why for p in c["phrases"]}
        if not default and word not in ask:
            ask.append(word)
    return kept, dropped, ask


def merged(cands: list[dict]) -> list[dict]:
    """One candidate per key, and none for a phrase an earlier candidate already proposes for the
    same element (a mined "shelters" beside the rules' plural): their checks go together."""
    out: dict[str, dict] = {}
    for c in cands:
        element = c["key"].partition(": ")[0]
        have = out.get(c["key"]) or next((o for o in out.values() if o["key"].partition(": ")[0] == element
                                          and set(c["phrases"]) <= set(o["phrases"])), None)
        if have is None:
            out[c["key"]] = dict(c)
        else:
            have["checks"] = have.get("checks", []) + [x for x in c.get("checks", []) if x not in have.get("checks", [])]
    return list(out.values())


# ── setup ────────────────────────────────────────────────────────────────────
def _site_layers(graphs: list[dict], base_root: Path, client: Path | None, out: Path) -> tuple[Path, Path, list[dict]]:
    """<out>/base with the shared base of each graph that has one, <out>/client from the site's
    own client layer (or empty, with its manifest); and the graphs with no base."""
    site_base, site_client = out / "base", out / "client"
    if site_client.exists():
        shutil.rmtree(site_client)
    if client:
        shutil.copytree(client, site_client)
    site_client.mkdir(parents=True, exist_ok=True)
    if not (site_client / _bundle.MANIFEST).exists():
        vr._dump(site_client / _bundle.MANIFEST, {"format": _bundle.LAYOUT, "models": {}})
    listed = _bundle._manifest(site_client).get("models") or {}
    if site_base.exists():
        shutil.rmtree(site_base)
    site_base.mkdir(parents=True)
    unbased = []
    for g in graphs:
        name = _name(g)
        gid = (listed.get(name) or {}).get("base") or g["graphid"]
        if (base_root / gid).is_dir():
            shutil.copytree(base_root / gid, site_base / gid)
        else:
            unbased.append(g)
    return site_base, site_client, unbased


def _record_defaults(client: Path, defaults: dict[str, str]) -> dict[str, str]:
    path = client / _bundle.MANIFEST
    doc = json.loads(path.read_text())
    doc["defaults"] = dict(doc.get("defaults") or {}, **defaults)
    vr._dump(path, doc)
    return doc["defaults"]


def _base_candidates(written: Path, unbased: list[dict]) -> list[dict]:
    """What `vocab pipeline --layer base` wrote for the graphs with no base, as gate candidates."""
    out = []
    for g in unbased:
        d = written / g["graphid"]
        name = _name(g)
        words_ = _bundle._manifest(d).get("type_words") or []
        if words_:
            out.append({"layer": "base", "kind": "type", "graphid": g["graphid"], "model": name,
                        "key": f"type {name}: llm", "phrases": words_, "rule": ["llm"]})
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            if p.name == _bundle.MANIFEST:
                continue
            doc = json.loads(p.read_text())
            for e in doc.get("entries") or []:
                if e.get("kind") in ("link", "date") and not e.get("qualifier"):
                    out.append({"layer": "base", "kind": e["kind"], "graphid": g["graphid"], "model": name,
                                "nodegroup": doc["nodegroup"], "node": e["node"], "phrases": e["phrases"],
                                "key": f"{e['kind']} {name}.{e['node']}: llm", "rule": ["llm"]})
    return out


def estimate(unbased_dir: Path | None, reference, fill_prompts: list[str], para_prompts: list[str],
             model: str | None) -> tuple[int, list[str]]:
    """(calls, report lines) for --llm: the base pipeline on the graphs with no base, the directed
    fill and the paraphrases, with claude -p's system prompt on every call."""
    from . import cost, prices
    rows = []
    if unbased_dir is not None:
        e = cost.estimate(unbased_dir, ["base"], {"base": model} if model else None, reference=reference)
        s = e["stages"]["base"]
        rows.append(("base (graphs with no base)", s["model"], s["calls"], s["input_tokens"], s["output_tokens"],
                     s["dollars"]))
    for stage, ps, default in (("directed fill", fill_prompts, "opus"), ("paraphrase", para_prompts, "sonnet")):
        if ps:
            m = model or default
            tin = sum(cost.by_chars(p) for p in ps)
            tout = cost.DEFAULT_OUTPUT * len(ps)
            rows.append((stage, m, len(ps), tin, tout,
                         prices.cost({"input_tokens": tin, "output_tokens": tout}, m)))
    calls = sum(r[2] for r in rows)
    lines = ["| stage | model | calls | input tokens | output tokens | dollars |", "| --- " * 6 + "|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | ${r[5]:.2f} |" for r in rows]
    lines += [f"| total | | {calls} | | | ${sum(r[5] for r in rows):.2f} |", "",
              cost.claude_p_overhead([(r[2], r[1]) for r in rows]), cost.NOTE]
    return calls, lines


def setup(data_dir, out, base_root="vocabularies/base", ontology_dir=None, client=None, defaults=None,
          docs=None, llm=False, llm_cmd=None, model=None, max_calls: int = 50, config_path=None, encoder=None,
          questions=None, accept_risks: bool = False, log=print) -> int:
    """The whole site setup; 0 when the bundle is written, 1 when it is written with wrong readings or
    partial name binds (unless `accept_risks`), 2 when --llm's estimate is over --max-calls or a --default
    names no model of the site. `questions`: the site's practice set (never the frozen exam)."""
    from .arches import graph_doc, read_resources
    from .paraphrase import canonical, mined, ngrams, paraphrased, prompts, site_texts
    from .questions import _plural
    started = time.perf_counter()
    data, out, base_root = Path(data_dir), Path(out), Path(base_root)
    ontology_dir = Path(ontology_dir) if ontology_dir else base_root.parent / "ontology" / "cidoc-crm"
    reference = data / "vocabularies" if (data / "vocabularies").is_dir() else None
    out.mkdir(parents=True, exist_ok=True)
    graphs = [graph_doc(p) for p in sorted((data / "graphs").glob("*.json"))]
    resources = read_resources(data / "resources")
    log(f"{len(graphs)} graphs, {len(resources)} records from {data}")
    site_base, site_client, unbased = _site_layers(graphs, base_root, Path(client) if client else None, out)
    unknown = sorted({m for m in (defaults or {}).values()} - {_name(g) for g in graphs})
    if unknown:
        log(f"--default names no model of this site: {', '.join(unknown)} (models: "
            f"{', '.join(sorted(_name(g) for g in graphs))})")
        return 2
    defaults = _record_defaults(site_client, {k.lower(): v for k, v in (defaults or {}).items()})
    log(f"shared layers as they are: the ontology ({ontology_dir}); a base for {len(graphs) - len(unbased)} "
        f"graph(s); none for {', '.join(_name(g) for g in unbased) or 'none'}")
    L = vr.Layers([data / "graphs"], site_base, site_client, ontology_dir, reference, resources=resources)
    from .alizarin import Tiles
    canon = canonical(L.vocab(), Tiles(L.vocab()))
    unbased_ids = {g["graphid"] for g in unbased}
    elements = vr.checklist(L)
    gaps = [e for e in vr.fill_gaps(elements) if e["layer"] == "client"
            or e["target"].get("graphid") in unbased_ids]
    fill_texts = vr.fill_prompts(gaps)
    para = prompts(canon)
    unbased_dir = None
    if unbased:
        unbased_dir = out / "work" / "graphs"
        if unbased_dir.exists():
            shutil.rmtree(unbased_dir)
        unbased_dir.mkdir(parents=True)
        for g in unbased:
            (unbased_dir / f"{g['graphid']}.json").write_text(json.dumps({"graph": [g]}))
    calls, cost_lines = estimate(unbased_dir, reference, fill_texts, [p for _, p in para], model)
    if not llm:
        cost_lines.append("Not sent: --llm not given (the rules and bge mining only).")
    log("\n".join(cost_lines))
    if llm and calls > max_calls:
        log(f"over --max-calls {max_calls}: nothing sent")
        return 2

    # the rules
    cands = [c for c in vr.candidates(elements) if c["layer"] == "client"
             or (c["layer"] == "base" and c.get("graphid") in unbased_ids)]
    sources = {"rules": cands}
    runner = None
    if llm:
        from .pipeline import Runner
        from .pipeline import run as pipeline
        runner = Runner(out / "llm", llm_cmd, model)
        if unbased_dir is not None:
            written = out / "work" / "llm-base"
            pipeline(unbased_dir, out / "work" / "pipeline", reference, llm_cmd=llm_cmd, model=model,
                     layer="base", base=written, log=log)
            sources["llm base"] = _base_candidates(written, unbased)
        extra, _ = vr.fill_replies(gaps, fill_texts, runner)
        sources["llm fill"] = [dict(c, key=f"{c['key']}: llm") for c in extra]
    # paraphrases
    encoder = encoder or _bge(log)
    said = set(L.vocab().type_words()) | {f for r in L.vocab().relations() for f in r.forms} \
        | {x.phrase for x in L.vocab().values()}
    texts = []
    if encoder is not None:
        texts = site_texts(L.vocab(), sorted(Path(docs).rglob("*.md")) + sorted(Path(docs).rglob("*.txt"))
                           if docs else ())
        names = {w for e in L.vocab()._index.entities for w in re.findall(r"[a-z][a-z'-]*", e.name.lower())}
        sources["bge"] = mined(canon, texts, encoder, said, names)
    if runner is not None:
        sources["llm paraphrase"] = paraphrased(canon, runner)

    everything = merged([dict(c, source=s) for s, cs in sources.items() for c in cs])
    generic = set(json.loads((L.ontology_dir / "generic.json").read_text())["phrases"])
    dropped = vr.review(everything, L.vocab(), generic)
    kept, more, need = settle_type_words(everything, defaults)
    for k, d in more.items():
        dropped.setdefault(k, {}).update(d)
    todo = []
    for c in kept:
        c["phrases"] = [p for p in c["phrases"] if p not in dropped.get(c["key"], {})]
        if c["phrases"]:
            todo.append(c)
    log(f"{len(everything)} candidates ({', '.join(f'{s} {len(cs)}' for s, cs in sources.items())}); "
        f"review dropped {sum(len(d) for d in dropped.values())} phrases; {len(todo)} to the site gate")
    for v in need:
        log(f"  '{v}' is held by more than one model: pass --default {v}=<Model> to make its plural a type word")
    proposed = {p for c in everything for p in c["phrases"]}
    prose = [gram for gram in ngrams(texts, PROBES * 4) if gram not in said and gram not in proposed][:PROBES]
    probes = [f"which {_plural(_name(graph))} are {gram}?" for gram in prose for graph in graphs]
    from . import config
    from .compose import site_questions
    cfg = config.load(config_path)
    asked = site_questions(questions) if questions else []
    verdict = SiteGate(L, todo, config.chain(cfg), probes, asked, generic).run(log)
    accepted = [c for c in todo if c["key"] in set(verdict["accepted"])]
    vr.apply(accepted, L.ontology_dir, site_base, site_client)

    # the bundle, the checklist and the audit
    from .audit import audit, audit_md
    bundle, merge_report = _bundle.layered(L.graphs, site_base, site_client, ontology_dir=ontology_dir)
    (out / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")))
    after = vr.Layers([data / "graphs"], site_base, site_client, ontology_dir, reference, resources=resources)
    vr.write_report(vr.checklist(after), out, "coverage", f"site {data.name}", vr.where_md(after, None))
    found = audit(after.vocab(), defaults, _bundle._manifest(site_client).get("accepted") or {}, generic)
    (out / "audit.json").write_text(json.dumps(found, ensure_ascii=False, indent=1) + "\n")
    (out / "audit.md").write_text(audit_md(found))
    final = SiteGate(after, [], config.chain(cfg), (), asked, generic)
    status, risks = _status(final.items, final.before, found)
    seconds = time.perf_counter() - started
    survived = {s: (sum(1 for c in accepted if c["source"] == s), sum(1 for c in todo if c["source"] == s))
                for s in sources}
    report = _report(data, out, unbased, cost_lines, survived, verdict, dropped, todo, need, merge_report,
                     found, seconds, status)
    (out / "setup.md").write_text(report)
    for s, (n, of) in survived.items():
        log(f"  {s}: {n} of {of} survive the site gate")
    log(f"audit: {', '.join(f'{k} {v}' for k, v in found['totals'].items())}")
    log(f"set up in {seconds:.0f}s → {out / 'bundle.json'} (ask with `ceist ask {data} \"…\" --bundle "
        f"{out / 'bundle.json'}`)")
    if risks and not accept_risks:
        print("\n".join(status), file=sys.stderr)
        print(f"not set up: {risks} wrong-answer risk(s) (setup.md); --accept-risks to accept them", file=sys.stderr)
        return 1
    return 0


def _name(g: dict) -> str:
    return g["name"].get("en") if isinstance(g["name"], dict) else g["name"]


def _bge(log):
    from . import onnx
    why = onnx.missing("bge-small-en-v1.5")
    if why:
        log(f"bge mining skipped: {why}")
        return None
    return onnx.encoder("bge-small-en-v1.5")


def _status(items: list[dict], scores: dict, found: dict, examples: int = 3) -> tuple[list[str], int]:
    """setup.md's opening block, and how many wrong-answer risks it lists (wrong readings and partial
    name binds): compositions by family, the site's own questions, name probes and the audit totals."""
    from .compose import FAMILIES
    got = {o["q"]: scores.get(("site", o["q"])) for o in items}
    composed = [o for o in items if o.get("shape") == "composition"]
    probes = [o for o in items if o.get("shape") == "name probe"]
    own = [o for o in items if o.get("shape") == "site question"]
    wrong = [o for o in composed + own if got[o["q"]] in BAD]
    partial = [o for o in probes if not o["bind"] and got[o["q"]] == "wrong"]
    risks = len(wrong) + len(partial)
    verdict = f"Not set up: {risks} wrong-answer risk(s)." if risks else "Set up: no known wrong-answer risks."
    lines = ["## Status", "", f"**{verdict}**", "", f"Compositions: {len(composed)} (refused, by family, with examples):", "",
             "| family | right | refused | wrong reading | refused, e.g. |", "| --- " * 5 + "|"]
    for family in FAMILIES:
        mine = [o for o in composed if o["family"] == family]
        tally = Counter(got[o["q"]] for o in mine)
        refused = "; ".join([o["q"] for o in mine if got[o["q"]] == "refused"][:examples])
        lines.append(f"| {family} | {tally['right']} | {tally['refused']} | {tally['wrong reading']} | {refused} |")
    lines += ["", f"Wrong readings: {len(wrong)}" + (":" if wrong else ".")]
    lines += [f"- {o['q']}" for o in wrong]
    if own:
        tally = Counter(got[o["q"]] for o in own)
        lines += ["", "The site's own questions: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())) + "."]
    whole = [o for o in probes if o["bind"]]
    lines += ["", f"Name probes: {len(probes) - len(whole)} partial names of {len(whole)} records; partial binds: "
              f"{len(partial)}" + (":" if partial else "."), *[f"- '{o['q']}' binds one of: {', '.join(o['records'].values())}" for o in partial],
              "", f"Whole names that don't bind: {sum(1 for o in whole if got[o['q']] != 'right')} of {len(whole)}.",
              "", "Audit (open items): " + ", ".join(f"{k} {v}" for k, v in found["totals"].items()) + "."]
    return lines, risks


def _report(data, out, unbased, cost_lines, survived, verdict, dropped, todo, need, merge_report, found,
            seconds, status) -> str:
    lines = [f"# Site setup: {data}", ""] + status + ["", f"Took {seconds:.0f} s. Graphs with no shared base (built here): "
             f"{', '.join(_name(g) for g in unbased) or 'none'}.", "", "## Cost estimate", ""] + cost_lines
    lines += ["", "## Site gate", "", "Each candidate alone, then together, on this site's own template questions "
              "(never another site's bench).", "", "| source | survive | of |", "| --- | --- | --- |"]
    lines += [f"| {s} | {n} | {of} |" for s, (n, of) in survived.items()]
    tally = verdict.get("tally") or {}
    lines += ["", f"Before: {tally.get('before', {})}", "", f"After: {tally.get('after', {})}", "",
              "| element | phrases | source | verdict |", "| --- " * 4 + "|"]
    passed = set(verdict["accepted"])
    lines += [f"| {c['key']} | {', '.join(c['phrases'])} | {c['source']} | "
              f"{'accepted' if c['key'] in passed else verdict['rejected'].get(c['key'], '?')} |" for c in todo]
    if need:
        lines += ["", "## Values and roles more than one model holds, with no site default", ""]
        lines += [f"- {v}: `--default {v}=<Model>` makes its plural a type word on that model" for v in need]
    lines += ["", "## Dropped by review", "", "| element | phrase | why |", "| --- " * 3 + "|"]
    lines += [f"| {k} | {p} | {why} |" for k, d in sorted(dropped.items()) for p, why in d.items()]
    lines += ["", "## Merge report", ""] + [f"- {r}" for r in merge_report] + [
        "", f"Coverage: coverage.md. Audit: audit.md ({'set up' if found['set_up'] else 'not set up yet'})."]
    return "\n".join(lines) + "\n"


def defaults_arg(pairs: list[str]) -> dict[str, str]:
    """["shelter=Building"] → {"shelter": "Building"}."""
    out = {}
    for p in pairs or []:
        value, _, model = p.partition("=")
        if not model:
            raise ValueError(f"--default {p}: give <value>=<Model>")
        out[value.strip().lower()] = model.strip()
    return out

