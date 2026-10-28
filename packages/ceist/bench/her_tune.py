"""Thresholds for a vectors model, tuned honestly: swept on every other HER
question (the even half), chosen there, and reported on the questions it
never saw (the odd half) — and on all of them, for comparison with the gate.

    ceist vectors fetch bge-small-en-v1.5
    uv run python packages/ceist/bench/her_tune.py <her.bundle.json> [model …]

A setting wins on the even half if it is right most often with at most
MAX_DANGEROUS dangerous answers there (ties: more right within one click).
The defaults in ceist.onnx.MODELS come from this script.
"""

import itertools
import sys
from pathlib import Path

from ceist import config
from ceist.evaluate import evaluate

HERE = Path(__file__).parent
QUESTIONS = HERE / "her" / "cases.json"
MAX_DANGEROUS = 1                      # per half (the full-set gate allows 3)
MINS = [round(0.30 + 0.05 * i, 2) for i in range(12)]          # 0.30 … 0.85
GAPS = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20]


def score(bundle, model, low, gap, half=None):
    cfg = config.load(HERE / "her" / "ceist.toml", model=model, low=low, gap=gap)
    r = evaluate(bundle, QUESTIONS, cfg, half=half)
    if cfg.notes:
        raise SystemExit("; ".join(cfg.notes))
    return r


def tune(bundle, model):
    best = None
    for low, gap in itertools.product(MINS, GAPS):
        r = score(bundle, model, low, gap, "even")
        if r.counts["dangerous"] > MAX_DANGEROUS:
            continue
        key = (r.counts["right"], r.one_click, -r.counts["dangerous"])
        if best is None or key > best[0]:
            best = (key, low, gap)
    return best


def main():
    bundle = sys.argv[1]
    models = sys.argv[2:] or [config.WORDLLAMA, "bge-small-en-v1.5", "all-minilm-l6-v2"]
    print("| model | min | gap | tuned on (even half) | held out (odd half) | all questions | one click (all) | ms/question |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for model in models:
        found = tune(bundle, model)
        if found is None:
            print(f"| {model} | – | – | nothing within {MAX_DANGEROUS} dangerous | | | | |")
            continue
        _, low, gap = found
        even, odd = score(bundle, model, low, gap, "even"), score(bundle, model, low, gap, "odd")
        full = score(bundle, model, low, gap)
        fmt = lambda r: f"{r.counts['right']}/{r.n_match} right, {r.counts['dangerous']} dangerous"
        print(f"| {model} | {low} | {gap} | {fmt(even)} | {fmt(odd)} | {fmt(full)} | "
              f"{full.one_click}/{full.n_match} | {full.ms:.1f} |")


if __name__ == "__main__":
    main()
