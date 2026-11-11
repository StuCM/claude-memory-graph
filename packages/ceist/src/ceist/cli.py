"""ceist on the command line: build a project's vocabulary bundle, and measure it.

    ceist vocab describe <graphs dir> <descriptions dir> [--reference <reference_data dir>]
    ceist vocab prompt <descriptions dir> <Model> [<Model> …]   # the schema inline: no paths, no data
    ceist vocab save <reply.json> <descriptions dir> <vocab dir>   # the LLM's reply → vocab/<Model>.json
    ceist vocab split <descriptions dir> <vocab dir> [-o <out dir>]   # → <Model>/<nodegroup>.json + manifest
    ceist vocab assemble <descriptions dir> <vocab dir> -o <bundle.json> [--graphs <graphs dir>]
    ceist vocab check <bundle.json> <graphs dir> [--vocab <vocab dir> --descriptions <dir>]
    ceist vocab slice <bundle.json | vocab dir> --data <business_data dir> --graphs <graphs dir> -o <out>
                      [--reference <reference_data dir>]   # only what the data uses; read locally
    ceist vocab pipeline <graphs dir> -o <out dir> [--reference <dir>] [--questions real.txt] [--seed S]
                         [--llm-cmd CMD] [--model M] [--models A,B] [--config ceist.toml]
                         [--min-right N] [--max-dangerous N] [--jobs N]   # LLM build → gate
                         [--layer base --base <dir> | --layer data --client <dir> [--base <dir>]]
                         [--rounds N [--holdout bank.json] [--records <business_data dir>]]
    ceist vocab try <data dir> <questions.txt> --bundle <bundle.json> [--log learn.jsonl]   # how each reads
    ceist vocab learn <learn.jsonl> --bundle <bundle.json> -o proposals.json [--exclude cases.json]
    ceist vocab assign <proposals.json> <reply.json>    # the LLM's reply to `learn` → "assign" fields
    ceist vocab merge <proposals.json> <vocab dir> --bundle <bundle.json>   # the approved ones
    ceist vocab ontology <graphs dir> [<graphs dir> …] -o <out dir> [--max-calls N] [--top N]
                         [--llm-cmd CMD] [--model M]   # CRM path phrasings → proposed.json
    ceist vocab ontology --review <graphs dir> [<graphs dir> …]   # the automatic review of proposed.json
    ceist vocab ontology --accept [--skip demo|her]   # the reviewed proposals, gated → phrases.json
    ceist vocab ontology build <graphs dir> [<graphs dir> …] -o <out dir> [--review-only]
                         [--max-calls N] [--skip demo|her]   # estimate, propose, review, gate, accept, report
    ceist vocab coverage <graphs dir> [<graphs dir> …] [--base <dir>] [--client <dir>] [--reference <dir>]
                         [-o <dir> --name N]   # the checklist per element: present, set aside, missing
    ceist vocab generate <graphs dir> [<graphs dir> …] [--base …] [--client …] [--reference …] -o <dir> --name N
                         [--review-only] [--skip demo|her]   # rules (no LLM) → review → gate → the layers
    ceist vocab fill <graphs dir> [<graphs dir> …] [as generate] [--estimate] [--llm-cmd CMD] [--model M]
                     [--max-calls N]   # the LLM on the gaps the rules left, then generate's review and gate
    ceist vocab crm-first <base graphs> [<client graphs>] [<more graph sets> …] [--base …] [--client …] -o <dir>
                          [--review-only] [--skip demo|her]   # base/client phrasings a CRM path carries → ontology
    ceist vocab profile <graphs dir> [--reference <dir>] [--json]   # the sizes that drive LLM cost
    ceist vocab estimate <graphs dir> --stages base,data,questions,ontology [--model M] [--rounds N]
                         [--ledger <run dir> …] [--json]   # calls, tokens and dollars before a run
    ceist setup <data dir> -o <out> [--base <dir>] [--client <dir>] [--default <value>=<Model> …] [--docs <dir>]
                [--config ceist.toml] [--llm [--max-calls N] [--llm-cmd CMD] [--model M]]   # a new site's vocabulary, gated on its own questions
    ceist ask <data dir> "<question>" [--bundle <bundle.json>] [--config ceist.toml]   # narration, count, refusal
    ceist questions generate <graphs dir> -o <out dir> [--reference <dir>] [--per-model N]
                             [--llm-cmd CMD] [--model M] [--models A,B]   # → train.json, holdout.json
    ceist eval --bundle <bundle.json> --questions <cases.json> [--config ceist.toml] [--report out.md]
               [--min-right N] [--max-dangerous N]      # the acceptance gate: exit 1 if missed
               [--half even|odd]                         # every other question: tune on one half
    ceist vectors fetch <model>                         # a transformer's weights (huggingface.co)
    ceist vectors embed <bundle.json> [--config ceist.toml]   # embed its phrasings ahead of time
"""

import argparse
import json
import sys
from pathlib import Path


def _describe(a):
    from .arches_describe import describe
    models = describe(a.graphs, a.out, a.reference)
    total = sum(len(m["nodes"]) for m in models.values())
    print(f"{len(models)} models, {total} searchable nodes → {a.out}")


def _prompt(a):
    from .bundle import prompt
    print(prompt(a.descriptions, a.models))


def _save(a):
    from .bundle import save
    written, errors, warnings = save(Path(a.reply).read_text(), a.descriptions, a.vocab)
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"  ! {e}", file=sys.stderr)
    print(f"{len(written)} model(s) written to {a.vocab}: {', '.join(written) or '-'}")
    return 1 if errors else 0


def _assemble(a):
    from .bundle import assemble
    b, errors, warnings = assemble(a.descriptions, a.vocab, a.graphs)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if errors and not a.force:
        print(f"{len(errors)} errors: bundle not written (--force to write anyway)", file=sys.stderr)
        return 1
    Path(a.out).write_text(json.dumps(b, separators=(",", ":")))
    built = b["built"]
    print(f"{built['models']} models, {built['entries']} entries, {built['phrasings']} phrasings, "
          f"{built['groups']} groups "
          f"→ {a.out} ({Path(a.out).stat().st_size // 1024} KB)")
    return 0


def _split(a):
    from .bundle import split
    written, errors = split(a.descriptions, a.vocab, a.out or a.vocab)
    for e in errors:
        print(f"  ! {e}", file=sys.stderr)
    print(f"{len(written)} nodegroup file(s) written to {a.out or a.vocab}")
    return 1 if errors else 0


def _check(a):
    from .bundle import load, stale, stale_groups
    if stale(load(a.bundle), a.graphs):
        print(f"stale: the graphs changed since {a.bundle} was built — rebuild the vocabulary")
        return 1
    if a.vocab:
        if not a.descriptions:
            print("--vocab needs --descriptions", file=sys.stderr)
            return 2
        groups = stale_groups(a.vocab, a.descriptions)
        for g in groups:
            print(f"stale: {g}")
        if groups:
            return 1
    print("up to date")
    return 0


def _size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*.json")) if path.is_dir() else path.stat().st_size


def _slice(a):
    from . import bundle as _bundle
    from .slicing import Usage, slice_bundle, slice_vocab
    src, out = Path(a.source), Path(a.out)
    use = Usage(a.graphs, a.data, a.reference)
    if src.is_dir():
        sliced = slice_vocab(src, out, use)
    else:
        b = slice_bundle(_bundle.load(src), use)
        sliced = b["sliced"]
        out.write_text(json.dumps(b, separators=(",", ":")))
    for model, groups in sorted(use.groups.items()):
        if use.records[model]:
            print(f"{model}: {use.records[model]} records; {len(use.kept[model])} of "
                  f"{len(groups)} nodegroups kept")
    print(f"dropped: models with no records {sliced['models'] or '-'}")
    for kind in ("groups", "links", "values"):
        for model, what in sorted(sliced[kind].items()):
            print(f"dropped {kind}, {model}: {', '.join(sorted(set(what)))}")
    if use.used is None:
        print("values not checked: no --reference")
    print(f"{_size(src) // 1024} KB → {_size(out) // 1024} KB ({out})")
    return 0


def _pipeline(a):
    from .pipeline import run
    return run(a.graphs, a.out, a.reference, a.questions, a.llm_cmd, a.model,
               a.models.split(",") if a.models else None, a.config, a.min_right, a.max_dangerous,
               a.jobs, seeds=a.seed, layer=a.layer, base=a.base, client=a.client, rounds=a.rounds,
               holdout=a.holdout, records=a.records)


def _questions(a):
    from .questions import generate
    return generate(a.graphs, a.out, a.reference, a.llm_cmd, a.model,
                    a.models.split(",") if a.models else None, a.per_model)


def _eval(a):
    from . import config
    from .evaluate import evaluate, report
    cfg = config.load(a.config)
    bundle = a.bundle or cfg.bundle
    if not bundle:
        print("no bundle: pass --bundle or set [vocabulary] bundle in the config", file=sys.stderr)
        return 2
    result = evaluate(bundle, a.questions, cfg, half=a.half)
    text = report(result)
    print(text)
    if a.report:
        Path(a.report).write_text(text)
    failed = []
    if a.min_right is not None and result.counts["right"] < a.min_right:
        failed.append(f"right {result.counts['right']} < {a.min_right}")
    if a.max_dangerous is not None and result.counts["dangerous"] > a.max_dangerous:
        failed.append(f"dangerous {result.counts['dangerous']} > {a.max_dangerous}")
    if failed:
        print("gate failed: " + "; ".join(failed), file=sys.stderr)
        return 1
    return 0


def _try(a):
    """Real questions, unlabelled: how each was read, and every phrase that
    couldn't be placed written to the learning log."""
    from . import config, learn
    from .arches import ArchesVocabulary
    from .narrate import narrate
    from .plan import interpret
    cfg = config.load(a.config)
    vocab = ArchesVocabulary.from_data_dir(a.data_dir, bundle=a.bundle or cfg.bundle)
    chain = config.chain(cfg)
    lines = [q.strip() for q in Path(a.questions).read_text().splitlines()
             if q.strip() and not q.lstrip().startswith("#")]
    read = unplaced = 0
    for q in lines:
        m = interpret(vocab, q, matcher=chain)
        if (m.plan or m.detail) and not m.refused:
            read += 1
            print(f"✓ {q}\n    {narrate(m.plan or m.detail)}")
        else:
            print(f"✗ {q}\n    ({m.refused or 'not understood'})")
        for phrase, options in m.grounding.suggestions:
            print(f"    did you mean, for '{phrase}': {', '.join(options)}")
        if a.log:
            unplaced += learn.from_grounding(a.log, q, m.grounding)
    print(f"\n{read}/{len(lines)} read" + (f"; {unplaced} unplaced phrase(s) logged to {a.log}"
                                            if a.log else ""))
    for n in cfg.notes:
        print(n)
    return 0


def _learn(a):
    from . import bundle as _bundle
    from . import learn
    b = _bundle.load(a.bundle)
    props = learn.proposals(a.log, b, exclude=a.exclude)
    Path(a.out).write_text(json.dumps(props, indent=1, ensure_ascii=False) + "\n")
    print(learn.summary(props))
    if props["to_assign"]:
        print("\n── for the LLM that assigns the rest (everything it needs is inline) ──\n")
        print(learn.prompt(props, b))
        print(f"\nSave its reply and run `ceist vocab assign {a.out} <reply.json>`.")
    print(f"\nThen review {a.out}: set \"approve\": true on what you agree with, and run "
          f"`ceist vocab merge {a.out} <vocab dir> --bundle {a.bundle}`.")
    return 0


def _assign(a):
    from . import learn
    path = Path(a.proposals)
    props = json.loads(path.read_text())
    done, errors = learn.assign(props, Path(a.reply).read_text())
    path.write_text(json.dumps(props, indent=1, ensure_ascii=False) + "\n")
    for e in errors:
        print(f"  ! {e}", file=sys.stderr)
    print(f"{done} assignment(s) written to {a.proposals}; a person sets \"approve\" next.")
    return 1 if errors else 0


def _merge(a):
    from . import bundle as _bundle
    from . import learn
    done = learn.merge(a.proposals, a.vocab, _bundle.load(a.bundle))
    print(f"{done['added']} phrasing(s) added ({done['new_entries']} new entries, "
          f"{done['already']} already there) in {len(done['files'])} file(s)")
    for e in done["errors"]:
        print(f"  ! {e}", file=sys.stderr)
    print("Next: `ceist vocab assemble`, then `ceist eval` on the held-out questions.")
    return 1 if done["errors"] else 0


def _ontology(a):
    from . import ontology_vocab as ov
    if a.accept:
        return 0 if ov.accept(a.ontology, skip=a.skip or ()) is not None else 1
    building = a.graphs[:1] == ["build"]
    graphs = a.graphs[1:] if building else a.graphs
    if a.review and graphs:
        ov.review(a.ontology, graphs)
        return 0
    if not (graphs and a.out):
        print("give the graphs dirs and -o, or --accept, or --review with the graphs dirs", file=sys.stderr)
        return 2
    if building:
        return ov.build(graphs, a.ontology, a.out, a.llm_cmd, a.model, a.max_calls, a.review_only, a.skip or ())
    return ov.propose(a.graphs, a.ontology, a.out, a.llm_cmd, a.model, a.max_calls, a.top)


def _layers(a):
    from .vocab_rules import Layers
    return Layers(a.graphs, a.base, a.client, a.ontology, a.reference)


def _coverage(a):
    from . import vocab_rules as vr
    from .crm_first import LEDGER
    layers = _layers(a)
    elements = vr.checklist(layers, vr.read_reasons(Path(a.out) / f"rules-{a.name}.json") if a.out else None)
    tail = vr.where_md(layers, Path(a.out) / LEDGER if a.out else None)
    if a.out:
        vr.write_report(elements, Path(a.out), a.name, a.name, tail)
    print(vr.report_md(elements, a.name) + tail)
    return 0


def _generate(a):
    from . import vocab_rules as vr
    return vr.generate(_layers(a), Path(a.out), a.name, a.review_only, a.skip or ())


def _fill(a):
    from . import vocab_rules as vr
    return vr.fill(_layers(a), Path(a.out), a.name, a.llm_cmd, a.model, a.max_calls, a.estimate, a.skip or ())


def _crm_first(a):
    from . import crm_first
    ontology = a.ontology or Path(a.base).parent / "ontology" / "cidoc-crm"
    return crm_first.run(a.graphs, a.base, a.client, ontology, Path(a.out), a.review_only, a.skip or ())


def _profile(a):
    from . import cost
    p = cost.profile(a.graphs, a.reference, a.ontology)
    print(json.dumps(p, indent=1) if a.json else "\n".join(cost.profile_lines(p)))
    return 0


def _estimate(a):
    from . import cost
    stages = a.stages.split(",")
    unknown = set(stages) - set(cost.MODELS)
    if unknown:
        print(f"unknown stage: {', '.join(sorted(unknown))} (known: {', '.join(cost.MODELS)})", file=sys.stderr)
        return 2
    e = cost.estimate(a.graphs, stages, {s: a.model for s in stages} if a.model else None, a.rounds,
                      a.ledger or (), reference=a.reference, seeds=a.seed, base=a.base, client=a.client,
                      questions=a.questions, per_model=a.per_model, ontology_dir=a.ontology)
    if a.json:
        print(json.dumps(e))
        return 0
    print("\n".join(cost.estimate_lines(e, a.rounds)))
    if a.ledger:
        print("\n" + "\n".join(cost.against(cost.read_runs(a.ledger))))
    return 0


def _setup(a):
    from .site import defaults_arg, setup
    return setup(a.data_dir, a.out, a.base, a.ontology, a.client, defaults_arg(a.default), a.docs, a.llm,
                 a.llm_cmd, a.model, a.max_calls, a.config)


def _ask(a):
    """One question against a data dir, answered from its records in memory (ceist.alizarin)."""
    from . import config
    from .alizarin import Tiles, evaluate
    from .arches import ArchesVocabulary
    from .narrate import narrate
    from .plan import interpret
    cfg = config.load(a.config)
    vocab = ArchesVocabulary.from_data_dir(a.data_dir, bundle=a.bundle or cfg.bundle)
    m = interpret(vocab, a.question, matcher=config.chain(cfg))
    for phrase, options in m.grounding.suggestions:
        print(f"did you mean, for '{phrase}': {', '.join(o.replace('_', ' ') for o in options)}")
    if m.refused or m.statement:
        print(f"refused: {m.refused or 'a statement, not a question'}")
        return 1
    if m.direct is not None or m.detail is not None:
        print(f"understood: {narrate(m.detail) if m.detail else f'{m.direct.type} {m.direct.name!r}'}")
        print("results: 1")
        return 0
    if m.plan.group is not None:
        print(f"understood: {narrate(m.plan)}")
        print("refused: counting by a field is answered over Rós Madair, not from the data dir")
        return 1
    tiles = Tiles(vocab)
    for plan, note in [(m.plan, "")] + [(r.plan, r.note) for r in m.relaxations]:
        ids = evaluate(plan, tiles)
        if ids or not note:
            print(f"understood: {narrate(plan)}" + (f"\n{note}" if note else ""))
            print(f"results: {len(ids)}")
            if not plan.count:
                for name in sorted(vocab.names.get(i, i) for i in ids)[:a.limit]:
                    print(f"  - {name}")
            return 0
    return 0


def _fetch(a):
    from . import onnx
    if a.model not in onnx.MODELS:
        print(f"unknown model '{a.model}' (known: {', '.join(onnx.MODELS)})", file=sys.stderr)
        return 2
    print(onnx.fetch(a.model, a.cache_dir))
    return 0


def _embed(a):
    """Every phrasing of a bundle through the configured transformer, once,
    into the vector cache — so no question pays for it."""
    import time

    from . import bundle as _bundle
    from . import config
    cfg = config.load(a.config, **({"model": a.model} if a.model else {}))
    if cfg.model == config.WORDLLAMA:
        print("wordllama needs no embedding ahead of time (it is a lookup table)")
        return 0
    from . import onnx
    why = onnx.missing(cfg.model, a.cache_dir, cfg.model_dir)
    if why:
        print(f"{cfg.model}: {why}", file=sys.stderr)
        return 2
    b = _bundle.load(a.bundle or cfg.bundle)
    texts = sorted({t for m in b["models"].values() for e in m["entries"] for t in e["phrases"]}
                   | {n.get("label", k) for m in b["models"].values()
                      for k, n in m["nodes"].items()})
    t0 = time.perf_counter()
    onnx.encoder(cfg.model, a.cache_dir, cfg.model_dir).encode(texts)
    print(f"{len(texts)} texts embedded with {cfg.model} in {time.perf_counter() - t0:.1f}s")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ceist")
    sub = ap.add_subparsers(dest="cmd", required=True)
    vocab = sub.add_parser("vocab", help="build a project's vocabulary bundle").add_subparsers(
        dest="step", required=True)

    p = vocab.add_parser("describe", help="read Arches models (needs alizarin)")
    p.add_argument("graphs")
    p.add_argument("out")
    p.add_argument("--reference", help="the package's reference_data (SKOS)")
    p.set_defaults(fn=_describe)

    p = vocab.add_parser("prompt", help="the instruction an LLM follows to write entries")
    p.add_argument("descriptions")
    p.add_argument("models", nargs="+")
    p.set_defaults(fn=_prompt)

    p = vocab.add_parser("save", help="an LLM's reply to `prompt` → validated vocab files")
    p.add_argument("reply", help="the reply: one JSON object keyed by model name")
    p.add_argument("descriptions")
    p.add_argument("vocab")
    p.set_defaults(fn=_save)

    p = vocab.add_parser("assemble", help="validate entries and write the bundle")
    p.add_argument("descriptions")
    p.add_argument("vocab")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--graphs", help="graph files, hashed so a stale bundle is caught")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=_assemble)

    p = vocab.add_parser("split", help="one file per nodegroup, plus a manifest")
    p.add_argument("descriptions")
    p.add_argument("vocab")
    p.add_argument("-o", "--out", help="default: the vocab dir itself")
    p.set_defaults(fn=_split)

    p = vocab.add_parser("check", help="is the bundle older than the graphs?")
    p.add_argument("bundle")
    p.add_argument("graphs")
    p.add_argument("--vocab", help="a split vocab dir: also list its stale nodegroups")
    p.add_argument("--descriptions", help="the current descriptions (with --vocab)")
    p.set_defaults(fn=_check)

    p = vocab.add_parser("slice", help="cut a bundle or split vocab down to what a dataset uses")
    p.add_argument("source", help="a bundle, or a split vocab dir")
    p.add_argument("--data", required=True, help="the business data (read here, never sent)")
    p.add_argument("--graphs", required=True)
    p.add_argument("--reference", help="reference_data: to keep only the values the data holds")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=_slice)

    p = vocab.add_parser("pipeline", help="an LLM writes the vocabulary per nodegroup; then the gate")
    p.add_argument("graphs", help="graphs/resource_models")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--reference", help="reference_data: value labels for the descriptions")
    p.add_argument("--questions", help="real questions, one per line: masked, then added to the cases")
    p.add_argument("--seed", action="append", help="phrasings already in use, which the LLM extends: "
                                                   "a bundle, a vocab dir, or {extra_type_words, "
                                                   "relation_forms, date_forms} JSON (repeatable)")
    p.add_argument("--llm-cmd", help="a command that reads a prompt on stdin and prints the reply "
                                     "(default: claude -p, no tools, over your subscription)")
    p.add_argument("--model", help="passed to claude -p")
    p.add_argument("--models", help="only these models, comma-separated")
    p.add_argument("--config", help="the matching config the gate scores with")
    p.add_argument("--min-right", type=int)
    p.add_argument("--max-dangerous", type=int)
    p.add_argument("--jobs", type=int, default=1, help="LLM calls at once")
    p.add_argument("--layer", choices=["base", "data"],
                   help="base: the schema's vocabulary into --base/<graph id>/; data: value variants "
                        "and the questions' phrasings into --client")
    p.add_argument("--base", help="the base layer's root (vocabularies/base)")
    p.add_argument("--client", help="the client layer's folder (--layer data)")
    p.add_argument("--rounds", type=int, default=0,
                   help="refine rounds: the failed cases to the LLM, masked; a round is kept only "
                        "when it answers more right and no more wrong")
    p.add_argument("--holdout", help="a question bank (JSON) scored every round, never sent")
    p.add_argument("--records", help="business data, read here so the loop scores named records; "
                                     "never sent")
    p.set_defaults(fn=_pipeline)

    p = vocab.add_parser("try", help="real questions: how each reads; log what wasn't placed")
    p.add_argument("data_dir", help="graphs/ (and resources/, vocabularies/) as Alizarin reads them")
    p.add_argument("questions", help="one question per line")
    p.add_argument("--bundle")
    p.add_argument("--config")
    p.add_argument("--log", help="append unplaced phrases to this learning log (JSONL)")
    p.set_defaults(fn=_try)

    p = vocab.add_parser("learn", help="a learning log → proposals to review")
    p.add_argument("log")
    p.add_argument("--bundle", required=True)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--exclude", help="held-out questions (cases.json): never learn from these")
    p.set_defaults(fn=_learn)

    p = vocab.add_parser("assign", help="an LLM's reply to `learn` → the proposals' assign fields")
    p.add_argument("proposals")
    p.add_argument("reply")
    p.set_defaults(fn=_assign)

    p = vocab.add_parser("merge", help="add the approved proposals to the vocabulary files")
    p.add_argument("proposals")
    p.add_argument("vocab")
    p.add_argument("--bundle", required=True)
    p.set_defaults(fn=_merge)

    p = vocab.add_parser("ontology", help="CIDOC-CRM path phrasings from an LLM, reviewed, gated, merged")
    p.add_argument("graphs", nargs="*", help='graphs/resource_models dirs, read for their CRM paths; '
                                             '"build" first runs the whole build')
    p.add_argument("-o", "--out", help="the LLM cache and audit log")
    p.add_argument("--ontology", default="vocabularies/ontology/cidoc-crm")
    p.add_argument("--llm-cmd", help="a command that reads a prompt on stdin and prints the reply "
                                     "(default: claude -p, no tools, over your subscription)")
    p.add_argument("--model", help="passed to claude -p")
    p.add_argument("--max-calls", type=int, default=300)
    p.add_argument("--top", type=int, help="only the N most used paths")
    p.add_argument("--accept", action="store_true", help='merge the "reviewed": true proposals that pass the gate')
    p.add_argument("--skip", action="append", choices=["demo", "her"],
                   help="with --accept or build: leave out a gate check whose checkout this machine lacks")
    p.add_argument("--review", action="store_true", help="review proposed.json automatically")
    p.add_argument("--review-only", action="store_true", help="build: stop after the review")
    p.set_defaults(fn=_ontology)

    for cmd, fn, help_ in (("coverage", _coverage, "the vocabulary checklist per element and layer"),
                           ("generate", _generate, "fill the checklist by rule (no LLM), reviewed and gated"),
                           ("fill", _fill, "an LLM on the checklist's remaining gaps, reviewed and gated")):
        p = vocab.add_parser(cmd, help=help_)
        p.add_argument("graphs", nargs="+", help="graphs/resource_models dirs: one graph set")
        p.add_argument("--base", default="vocabularies/base")
        p.add_argument("--client", help="the client layer (a site's vocab dir)")
        p.add_argument("--ontology", help="default: ontology/cidoc-crm beside --base")
        p.add_argument("--reference", help="reference data (SKOS XML, collection JSON): the values")
        p.add_argument("-o", "--out", required=cmd != "coverage", help="the reports' dir")
        p.add_argument("--name", default="coverage", help="the graph set's name in the report files")
        p.add_argument("--skip", action="append", choices=["demo", "her"])
        p.add_argument("--review-only", action="store_true")
        p.add_argument("--estimate", action="store_true", help="fill: print the estimate, send nothing")
        p.add_argument("--llm-cmd")
        p.add_argument("--model")
        p.add_argument("--max-calls", type=int, default=300)
        p.set_defaults(fn=fn)

    p = vocab.add_parser("crm-first", help="move the phrasings a CRM path carries into the ontology layer, gated")
    p.add_argument("graphs", nargs="+", help="graph sets a path must mean one thing in; the base's graphs first")
    p.add_argument("--base", default="vocabularies/base")
    p.add_argument("--client", help="the client layer (a site's vocab dir); its graphs among the sets")
    p.add_argument("--ontology", help="default: ontology/cidoc-crm beside --base")
    p.add_argument("-o", "--out", required=True, help="the ledger's and report's dir")
    p.add_argument("--skip", action="append", choices=["demo", "her"])
    p.add_argument("--review-only", action="store_true", help="classify and write the ledger; no gate, no move")
    p.set_defaults(fn=_crm_first)

    p = vocab.add_parser("profile", help="the sizes that drive a build's LLM cost, per graph")
    p.add_argument("graphs")
    p.add_argument("--reference", help="reference_data: list sizes")
    p.add_argument("--ontology", default="vocabularies/ontology/cidoc-crm")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_profile)

    p = vocab.add_parser("estimate", help="calls, tokens and dollars per stage, before a run")
    p.add_argument("graphs")
    p.add_argument("--stages", default="base", help="comma-separated: ontology, base, data, questions")
    p.add_argument("--model", help="every stage's model (default: opus, data sonnet)")
    p.add_argument("--rounds", type=int, default=0, help="refine rounds")
    p.add_argument("--reference")
    p.add_argument("--seed", action="append", help="as the pipeline's --seed")
    p.add_argument("--base", help="the base layer's root, a seed as --layer base reads it")
    p.add_argument("--client", help="the client layer (data): its combos go with the labels")
    p.add_argument("--questions", help="as the pipeline's --questions")
    p.add_argument("--per-model", type=int, default=40, help="questions stage: as `questions generate`")
    p.add_argument("--ontology", default="vocabularies/ontology/cidoc-crm")
    p.add_argument("--ledger", action="append", help="a past run's out dir: replies sized from its usage, "
                                                     "and the estimate set beside its actuals")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_estimate)

    p = sub.add_parser("setup", help="a new site's vocabulary from its data dir, gated on its own questions")
    p.add_argument("data_dir", help="graphs/, resources/ and vocabularies/ (optional)")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--base", default="vocabularies/base", help="the shared base layer, used as it is")
    p.add_argument("--ontology", help="the shared ontology layer (default: ontology/cidoc-crm beside --base)")
    p.add_argument("--client", help="the site's client layer so far, copied to <out>/client and added to")
    p.add_argument("--default", action="append", help="<value>=<Model>: the model a value two models hold "
                                                       "names as a type word (recorded in the client manifest)")
    p.add_argument("--docs", help="the site's own docs (*.md, *.txt): text for bge mining")
    p.add_argument("--config", help="the matching config the site answers with (ceist.toml); the gate uses it")
    p.add_argument("--llm", action="store_true", help="also the LLM routes, after the estimate")
    p.add_argument("--max-calls", type=int, default=50)
    p.add_argument("--llm-cmd")
    p.add_argument("--model")
    p.set_defaults(fn=_setup)

    p = sub.add_parser("ask", help="ask one question of a data dir")
    p.add_argument("data_dir")
    p.add_argument("question")
    p.add_argument("--bundle", help="e.g. <out>/bundle.json from ceist setup")
    p.add_argument("--config")
    p.add_argument("--limit", type=int, default=10, help="names listed at most")
    p.set_defaults(fn=_ask)

    qs = sub.add_parser("questions", help="a labelled starting question set").add_subparsers(
        dest="step", required=True)
    p = qs.add_parser("generate", help="an LLM writes questions and their readings from the schema")
    p.add_argument("graphs", help="graphs/resource_models")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--reference", help="reference_data: value labels for the descriptions")
    p.add_argument("--per-model", type=int, default=40, help="about this many questions per model")
    p.add_argument("--llm-cmd", help="a command that reads a prompt on stdin and prints the reply "
                                     "(default: claude -p)")
    p.add_argument("--model", help="passed to claude -p")
    p.add_argument("--models", help="only these models, comma-separated")
    p.set_defaults(fn=_questions)

    p = sub.add_parser("eval", help="score a bundle and config on acceptance questions")
    p.add_argument("--bundle")
    p.add_argument("--questions", required=True)
    p.add_argument("--config")
    p.add_argument("--report")
    p.add_argument("--min-right", type=int)
    p.add_argument("--max-dangerous", type=int)
    p.add_argument("--half", choices=["even", "odd"],
                   help="score every other question only: tune on one half, report the other")
    p.set_defaults(fn=_eval)

    vec = sub.add_parser("vectors", help="transformer models for the vectors layer").add_subparsers(
        dest="step", required=True)
    p = vec.add_parser("fetch", help="download a model's weights once")
    p.add_argument("model")
    p.add_argument("--cache-dir")
    p.set_defaults(fn=_fetch)
    p = vec.add_parser("embed", help="embed a bundle's phrasings ahead of time")
    p.add_argument("bundle", nargs="?")
    p.add_argument("--config")
    p.add_argument("--model")
    p.add_argument("--cache-dir")
    p.set_defaults(fn=_embed)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
