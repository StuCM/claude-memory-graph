"""ceist on the command line: build a project's vocabulary bundle, and measure it.

    ceist vocab describe <graphs dir> <descriptions dir> [--reference <reference_data dir>]
    ceist vocab prompt <descriptions dir> <Model> [<Model> …] [--vocab <vocab dir>]
    ceist vocab assemble <descriptions dir> <vocab dir> -o <bundle.json> [--graphs <graphs dir>]
    ceist vocab check <bundle.json> <graphs dir>
    ceist eval --bundle <bundle.json> --questions <cases.json> [--config ceist.toml] [--report out.md]
               [--min-right N] [--max-dangerous N]      # the acceptance gate: exit 1 if missed
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
    print(prompt(a.descriptions, a.models, a.vocab))


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
    print(f"{built['models']} models, {built['entries']} entries, {built['phrasings']} phrasings "
          f"→ {a.out} ({Path(a.out).stat().st_size // 1024} KB)")
    return 0


def _check(a):
    from .bundle import load, stale
    if stale(load(a.bundle), a.graphs):
        print(f"stale: the graphs changed since {a.bundle} was built — rebuild the vocabulary")
        return 1
    print("up to date")
    return 0


def _eval(a):
    from . import config
    from .evaluate import evaluate, report
    cfg = config.load(a.config)
    bundle = a.bundle or cfg.bundle
    if not bundle:
        print("no bundle: pass --bundle or set [vocabulary] bundle in the config", file=sys.stderr)
        return 2
    result = evaluate(bundle, a.questions, cfg)
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
    p.add_argument("--vocab", default="vocab")
    p.set_defaults(fn=_prompt)

    p = vocab.add_parser("assemble", help="validate entries and write the bundle")
    p.add_argument("descriptions")
    p.add_argument("vocab")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--graphs", help="graph files, hashed so a stale bundle is caught")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=_assemble)

    p = vocab.add_parser("check", help="is the bundle older than the graphs?")
    p.add_argument("bundle")
    p.add_argument("graphs")
    p.set_defaults(fn=_check)

    p = sub.add_parser("eval", help="score a bundle and config on acceptance questions")
    p.add_argument("--bundle")
    p.add_argument("--questions", required=True)
    p.add_argument("--config")
    p.add_argument("--report")
    p.add_argument("--min-right", type=int)
    p.add_argument("--max-dangerous", type=int)
    p.set_defaults(fn=_eval)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
