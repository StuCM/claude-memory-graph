"""What the vocabulary build costs: the ledger every LLM call writes, a graph set's size
profile, and an estimate of a run before it is paid for.

    ceist vocab profile <graphs dir> [--reference <dir>] [--ontology <dir>] [--json]
    ceist vocab estimate <graphs dir> --stages base,data,questions,ontology [--model M] [--rounds N]
                         [--reference <dir>] [--seed S] [--base <dir>] [--client <dir>]
                         [--questions F] [--per-model N] [--ledger <run dir> …] [--json]

The ledger is in audit.jsonl, on each call's line beside its prompt: the stage, model,
usage and dollars (claude -p's total_cost_usd, else prices.py). A reply from the cache
costs 0 and is marked cached. The estimate runs each stage's own code with an LLM that
answers nothing, so it counts the calls that code makes and sizes their real prompts.
"""

import hashlib
import json
import math
import os
import tempfile
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from . import prices

USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
STAGES = {"values": "data", "phrases": "data", "generate": "questions", "refine": "refine",
          "ontology": "ontology"}
ORDER = ("ontology", "base", "data", "questions", "refine")
MODELS = {"ontology": "opus", "base": "opus", "data": "sonnet", "questions": "opus"}
DEFAULT_OUTPUT = 2000         # tokens a call writes, reply and thinking, before any run is measured
DEFAULT_REFINE_INPUT = 8000   # a refine prompt holds the failures, which exist only once a run has
NOTE = "Dollars are API list prices; on a Claude subscription they are usage, not a bill."


def stage_of(what: dict) -> str:
    return STAGES.get(what.get("kind"), "base")


def _row(name: str, t: Counter) -> str:
    return (f"| {name} | {t['calls']} | {t['cached']} | {t['input_tokens']} | {t['cache_read_input_tokens']} | "
            f"{t['cache_creation_input_tokens']} | {t['output_tokens']} | ${t['dollars']:.2f} |")


def tally(ledger: list[dict]) -> dict[str, Counter]:
    """{stage: calls, cached, tokens by kind, dollars, calls with no usage reported}."""
    out: dict[str, Counter] = {}
    for r in ledger:
        t = out.setdefault(r["stage"], Counter())
        t["calls"] += 1
        t["cached"] += r["cached"]
        t.update({k: r["usage"].get(k, 0) for k in USAGE})
        t["dollars"] += r["cost_usd"] or 0
        t["unpriced"] += r["cost_usd"] is None
    return out


def summary(ledger: list[dict]) -> list[str]:
    """The cost table a run's report ends with."""
    lines = ["## Cost", "", "| stage | calls | from the cache | input | cache read | cache write | output | dollars |",
             "| --- " * 8 + "|"]
    total = Counter()
    for stage, t in sorted(tally(ledger).items(), key=lambda x: ORDER.index(x[0])):
        lines.append(_row(stage, t))
        total.update(t)
    lines += [_row("total", total), "", NOTE]
    if total["unpriced"]:
        lines.append(f"{total['unpriced']} call(s) reported no usage (an --llm-cmd stub): counted as $0.")
    return lines


def read_runs(paths) -> list[dict]:
    """Each run dir (or audit.jsonl): its prompts as (stage, chars) and its ledger rows."""
    runs = []
    for p in map(Path, paths):
        p = p / "audit.jsonl" if p.is_dir() else p
        prompts, spent = [], []
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if "prompt" in r:
                prompts.append((stage_of(r), len(r["prompt"])))
            if "cost_usd" in r:
                spent.append(r)
        runs.append({"path": str(p.parent), "prompts": prompts, "spent": spent})
    return runs


def observed(runs: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """{(stage, model family): usage of each paid call}."""
    seen = defaultdict(list)
    for run in runs:
        for r in run["spent"]:
            if not r["cached"] and r["usage"].get("output_tokens"):
                seen[(r["stage"], prices.family(r["llm"]))].append(r["usage"])
    return seen


def _mean(xs) -> int:
    xs = list(xs)
    return round(sum(xs) / len(xs)) if xs else 0


def per_call_output(seen: dict, stage: str, model: str) -> tuple[int, str]:
    hist = seen.get((stage, prices.family(model)))
    if hist:
        return _mean(u["output_tokens"] for u in hist), f"ledger, {len(hist)} calls"
    return DEFAULT_OUTPUT, "default (no history)"


def _system() -> str:
    from .pipeline import CLAUDE
    return CLAUDE[-1]


def by_chars(prompt: str) -> int:
    return (len(_system()) + len(prompt)) // 4


def input_tokens(prompts: list[str], model: str) -> tuple[list[int], str]:
    """Each prompt's input tokens: messages.count_tokens when ANTHROPIC_API_KEY is set, else chars / 4."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and prompts:
        try:
            return [_count(p, model, key) for p in prompts], "messages.count_tokens"
        except OSError as e:
            return [by_chars(p) for p in prompts], f"characters / 4 (count_tokens failed: {e})"
    return [by_chars(p) for p in prompts], "characters / 4 (no ANTHROPIC_API_KEY)"


def _count(prompt: str, model: str, key: str) -> int:
    body = {"model": prices.API_IDS[prices.family(model)], "system": _system(),
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages/count_tokens",
                                 data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["input_tokens"]


def _dry(out: Path):
    from .pipeline import Runner

    class Dry(Runner):
        """Keeps each prompt a stage would send and answers none: nothing retried or cached."""

        def ask(self, key, prompt, check, what):
            self.sent.append({"stage": stage_of(what), "prompt": prompt})
            return None

    run = Dry(out)
    run.sent = []
    return run


def plan(graphs, stages, reference=None, seeds=None, base=None, client=None, questions=None,
         per_model: int = 40, ontology_dir="vocabularies/ontology/cidoc-crm") -> list[dict]:
    """The prompts each stage sends on a fresh run, [{stage, prompt}], from the stage's own code.
    Not here: base's collision passes (one per model at most, only when phrases collide),
    retries, and refine (its prompts hold failures that exist only after a build)."""
    from . import ontology_vocab as ov
    from .arches_describe import describe
    from .learn import mask
    from .pipeline import (base_seed, build_model, field_phrases, load_seeds, model_roles, name_model,
                           read_questions, value_variants, write_cases)
    from .questions import prompt_for
    graphs = Path(graphs)
    real, bank, _ = read_questions(questions, set())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = _dry(tmp)
        if "base" in stages or "questions" in stages:
            descriptions = describe(graphs, tmp / "descriptions", reference)
            roles = model_roles(graphs, descriptions)
        if "base" in stages:
            seeded, _ = load_seeds(list(seeds or []) + ([base_seed(descriptions, Path(base), tmp)] if base else []),
                                   descriptions)
            for name, d in sorted(descriptions.items()):
                build_model(run, d, roles[name], tmp / "vocab", seeds=seeded["nodes"].get(name))
            for name, d in sorted(descriptions.items()):
                name_model(run, d, roles[name], descriptions, seeded)
            write_cases(run, descriptions, roles, [] if bank else real)
        if "data" in stages:
            masked = [mask(q) for q in real]
            for name, d in sorted(describe(graphs, tmp / "listed", reference, small=math.inf).items()):
                files = ({p.stem: json.loads(p.read_text()) for p in sorted((Path(client) / name).glob("*.json"))}
                         if client else {})
                value_variants(run, d, files, masked)
                if masked:
                    field_phrases(run, d, files, masked)
        if "questions" in stages:
            for name in sorted(descriptions):
                run.sent.append({"stage": "questions", "prompt": prompt_for(name, descriptions, roles, per_model)[1]})
        if "ontology" in stages:
            ontology, defs = ov.load(ontology_dir), ov.definitions(Path(ontology_dir) / "source")
            cands = ov.collect(ov.graph_docs([graphs]), ontology, defs)[0]
            for i in range(0, len(cands), ov.BATCH):
                run.sent.append({"stage": "ontology", "prompt": ov.prompt(cands[i:i + ov.BATCH], ontology, defs)})
    return run.sent


def estimate(graphs, stages, models: dict | None = None, rounds: int = 0, ledger=(), **plan_args) -> dict:
    """Calls, tokens and dollars per stage: {"stages": {stage: …}, "calls": [[stage, model, sha, $]], "sizing"}."""
    models = dict(MODELS, **(models or {}))
    models.setdefault("refine", models["data" if "data" in stages else "base"])
    sent = plan(graphs, stages, **plan_args)
    seen = observed(read_runs(ledger))
    out = {"stages": {}, "calls": [], "sizing": None}
    for stage in [s for s in ORDER if s in stages or (s == "refine" and rounds)]:
        model = models[stage]
        each_out, out_from = per_call_output(seen, stage, model)
        if stage == "refine":
            hist = seen.get(("refine", prices.family(model)))
            each_in = _mean(sum(u.get(k, 0) for k in USAGE if k != "output_tokens") for u in hist) if hist else (
                DEFAULT_REFINE_INPUT)
            prompts, tin = [None] * rounds, [each_in] * rounds
        else:
            prompts = [x["prompt"] for x in sent if x["stage"] == stage]
            tin, out["sizing"] = input_tokens(prompts, model)
        for p, n in zip(prompts, tin):
            sha = hashlib.sha256(p.encode()).hexdigest() if p else None
            out["calls"].append([stage, model, sha, prices.cost({"input_tokens": n, "output_tokens": each_out}, model)])
        mine = [c for c in out["calls"] if c[0] == stage]
        out["stages"][stage] = {"model": model, "calls": len(prompts), "input_tokens": sum(tin),
                                "output_tokens": each_out * len(prompts), "dollars": sum(c[3] for c in mine),
                                "output_from": out_from}
    return out


def estimate_lines(e: dict, rounds: int = 0) -> list[str]:
    lines = ["| stage | model | calls | input tokens | output tokens | dollars | output per call from |",
             "| --- " * 7 + "|"]
    for stage, s in e["stages"].items():
        lines.append(f"| {stage} | {s['model']} | {s['calls']} | {s['input_tokens']} | {s['output_tokens']} | "
                     f"${s['dollars']:.2f} | {s['output_from']} |")
    tot = {k: sum(s[k] for s in e["stages"].values()) for k in ("calls", "input_tokens", "output_tokens", "dollars")}
    lines += [f"| total | | {tot['calls']} | {tot['input_tokens']} | {tot['output_tokens']} | ${tot['dollars']:.2f} | |",
              "", f"Input sized by {e['sizing'] or 'the ledger'}; system prompt included.",
              "Not counted: base's collision passes (at most one call per model, only when phrases "
              "collide), and retries (at most one more per call)."]
    if rounds:
        lines.append(f"Refine: {rounds} round(s) is the most; the loop stops early when nothing fails or a "
                     "round is rolled back.")
    return lines + [NOTE]


def against(runs: list[dict]) -> list[str]:
    """The estimate's sizing beside each past run's actuals, per stage."""
    seen = observed(runs)
    lines = ["## The estimate against past runs", "",
             "| run | stage | model | calls | input est | input actual | output est | output actual | "
             "dollars est | dollars actual | error |", "| --- " * 11 + "|"]
    for run in runs:
        for stage in sorted({s for s, _ in run["prompts"]}, key=ORDER.index):
            chars = [c for s, c in run["prompts"] if s == stage]
            paid = [r for r in run["spent"] if r["stage"] == stage and not r["cached"]]
            model = paid[0]["llm"] if paid else ""
            each_out, _ = per_call_output(seen, stage, model)
            est_in = sum((len(_system()) + c) // 4 for c in chars)
            est_out = each_out * len(chars)
            est = prices.cost({"input_tokens": est_in, "output_tokens": est_out}, model)
            if not paid:
                lines.append(f"| {run['path']} | {stage} | {model or '?'} | {len(chars)} | {est_in} | "
                             f"estimated, not measured | {est_out} | | ${est:.2f} | | |")
                continue
            act_in = sum(r["usage"][k] for r in paid for k in USAGE if k != "output_tokens")
            act_out = sum(r["usage"]["output_tokens"] for r in paid)
            act = sum(r["cost_usd"] or 0 for r in paid)
            err = f"{100 * (est - act) / act:+.0f}%" if act else ""
            lines.append(f"| {run['path']} | {stage} | {model} | {len(paid)} | {est_in} | {act_in} | {est_out} | "
                         f"{act_out} | ${est:.2f} | ${act:.2f} | {err} |")
    return lines


def profile(graphs, reference=None, ontology_dir=None) -> dict:
    """The measures that drive cost, per graph, and the CRM in use across them."""
    from . import crm
    from . import ontology_vocab as ov
    from .arches_describe import describe
    from .bundle import kind_of
    from .pipeline import BATCH
    with tempfile.TemporaryDirectory() as tmp:
        described = {d["graphid"]: d for d in describe(graphs, tmp, reference, small=math.inf).values()}
    docs = ov.graph_docs([graphs])
    rows, classes, props, paths = [], set(), set(), set()
    for doc in docs:
        g = doc["graph"][0] if "graph" in doc else doc
        d, chains, mine, kinds = described[g["graphid"]], crm.chains(g), set(), Counter()
        for n in d["nodes"]:
            kind, tokens = kind_of(n), chains.get(n["alias"])
            kinds[kind] += 1
            if tokens:
                classes.update(tokens[0::2])
                props.update(tokens[1::2])
                path = ov.path_of(tokens, kind)
                if path and "-" not in path.split():
                    mine.add(path)
        lists = [n["values"] for n in d["nodes"] if isinstance(n.get("values"), list)]
        paths |= mine
        rows.append({"model": d["name"], "nodegroups": len(d["nodegroups"]), "link": kinds["link"],
                     "date": kinds["date"], "property": kinds["property"], "crm_paths": len(mine),
                     "lists": len(lists), "distinct_lists": len({tuple(v) for v in lists}),
                     "labels": sum(map(len, lists)), "long_lists": sum(1 for v in lists if len(v) > BATCH)})
    onto = {"classes": len(classes - {"-"}), "properties": len(props - {"-"}), "paths": len(paths)}
    if ontology_dir and Path(ontology_dir, "phrases.json").exists():
        defs = ov.definitions(Path(ontology_dir) / "source")
        cands = ov.collect(docs, ov.load(ontology_dir), defs)[0]
        onto.update(unphrased=len(cands), unphrased_nodes=sum(c["nodes"] for c in cands),
                    calls=math.ceil(len(cands) / ov.BATCH))
    return {"graphs": rows, "ontology": onto}


def profile_lines(p: dict) -> list[str]:
    keys = ("nodegroups", "link", "date", "property", "crm_paths", "lists", "distinct_lists", "labels", "long_lists")
    lines = ["| model | nodegroups | link | date | property | CRM paths | list fields | distinct lists | labels | "
             "lists over the batch |", "| --- " * 10 + "|"]
    for r in sorted(p["graphs"], key=lambda r: r["model"]):
        lines.append(f"| {r['model']} | " + " | ".join(str(r[k]) for k in keys) + " |")
    lines.append(f"| total ({len(p['graphs'])} models) | "
                 + " | ".join(str(sum(r[k] for r in p["graphs"])) for k in keys) + " |")
    o = p["ontology"]
    lines += ["", f"CIDOC-CRM in use: {o['classes']} classes, {o['properties']} properties, {o['paths']} distinct "
                  "paths across the graphs (up to three tokens, as phrases.json keys them; the table total counts a path once per graph)."]
    if "unphrased" in o:
        lines.append(f"Ontology stage: {o['unphrased']} unphrased link, date and list-field paths ({o['unphrased_nodes']} nodes) "
                     f"→ {o['calls']} calls.")
    return lines
