"""Which matcher should ground everyday phrases onto Arches nodes?

    uv run python packages/ceist/bench/compare.py            # what runs here
    CEIST_BENCH_MODELS=~/models uv run python packages/ceist/bench/compare.py

Each matcher answers one question: given the question, the phrase to place
("built", "pulled down", "owned by") and the candidate nodes, which node —
or none (abstain: the planner then asks or refuses). Two conditions:

- restricted: candidates narrowed first by what the planner's structure
  already knows (a date phrase → date nodes; "by <a Person>" → links to
  Person; a property → concept/number/string nodes) — how ceist would use it;
- all nodes: no narrowing — what a matcher manages on its own.

Scoring: a wrong pick is worse than an abstention (it answers a different
question), so both are reported. Everything a matcher here uses must also
run in a browser with no backend (Rós Madair's deployment): static word
vectors (plain arrays), ONNX models (onnxruntime-web / transformers.js), and
GGUF models (wllama, llama.cpp compiled to WASM). The Python runtimes below
load the same weight files, so results carry over; browser speed differs and
is reported separately.

Model weights (not downloaded by this script; put them under
$CEIST_BENCH_MODELS):

    minilm/            model.onnx + tokenizer.json   bi-encoder (all-MiniLM-L6-v2)
    bge-small/         model.onnx + tokenizer.json   bi-encoder (BAAI/bge-small-en-v1.5)
    cross-minilm/      model.onnx + tokenizer.json   cross-encoder (ms-marco-MiniLM-L-6-v2)
    qwen3-0.6b.gguf, qwen3-1.7b.gguf, qwen3-4b.gguf  small LLMs (Q4_K_M)

A matcher whose weights or runtime are missing is listed as skipped, never
estimated.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
GENERIC = {"date", "of", "by", "the", "type", "start", "end", "m"}
STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "by", "is", "are", "was", "were",
        "which", "what", "who", "how", "did", "do", "does", "have", "has", "their", "can"}


# ── the cases ──────────────────────────────────────────────────────────────

def load():
    models = json.loads((HERE / "models.json").read_text())
    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    return models, cases


def candidates(models, case, restricted: bool) -> list[dict]:
    nodes = models[case["model"]]
    if not restricted:
        return nodes
    slot = case["slot"]
    if slot == "date":
        return [n for n in nodes if n["datatype"] in ("date", "edtf")]
    if slot.startswith("link:"):
        target = slot.split(":", 1)[1]
        return [n for n in nodes if n["datatype"].startswith("resource-instance")
                and n.get("target") == target]
    return [n for n in nodes if not n["datatype"].startswith("resource-instance")
            and n["datatype"] not in ("date", "edtf")]


def describe(n: dict) -> str:
    """A node as words: its name without generic words, with its group."""
    name = " ".join(w for w in re.findall(r"[a-z]+", n["name"].lower()) if w not in GENERIC)
    group = n.get("group", "")
    if group and group.lower() not in name:
        return f"{name} ({group.lower()})"
    return name


# ── matchers ───────────────────────────────────────────────────────────────

class Skip(Exception):
    pass


def _stem(w: str) -> str:
    for suf in ("ation", "ion", "ing", "ed", "er", "es", "s", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


class Exact:
    """Today's ceist: the node's own words (stemmed), nothing else."""
    name = "exact words (today)"
    size, browser = "0", "yes"

    def pick(self, q, phrase, cands):
        words = {_stem(w) for w in re.findall(r"[a-z]+", phrase.lower()) if w not in STOP}
        hits = [n for n in cands
                if words & {_stem(w) for w in re.findall(r"[a-z]+", (n["name"] + " " + n["alias"]).lower())
                            if w not in GENERIC}]
        return (hits[0]["alias"] if len(hits) == 1 else None), None


def _vocab():
    path = HERE / "vocab.json"
    return json.loads(path.read_text()) if path.exists() else None


def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


class VocabExact:
    """An LLM-written vocabulary (vocab.json, built once offline), matched by
    words: the phrase equals one of a node's phrasings, or one contains the
    other as whole words. One node must win, else abstain."""
    name = "vocabulary + exact words"
    size, browser = "the vocabulary file (~20 KB)", "yes"

    def __init__(self):
        self.vocab = _vocab()
        if self.vocab is None:
            raise Skip("no vocab.json")

    def pick(self, q, phrase, cands, model=None):
        p = _norm(phrase)
        best = {}
        for n in cands:
            for v in self.vocab.get(model, {}).get(n["alias"], []):
                v = _norm(v)
                if v == p:
                    score = 3
                elif f" {v} " in f" {p} " or f" {p} " in f" {v} ":
                    score = 1 + (len(v) > 3)
                else:
                    continue
                best[n["alias"]] = max(best.get(n["alias"], 0), score)
        if not best:
            return None, None
        top = max(best.values())
        winners = [a for a, s in best.items() if s == top]
        return (winners[0] if len(winners) == 1 else None), None


class Threshold:
    """Pick the best score if it clears `low` and beats the runner-up by `gap`."""
    low, gap = 0.40, 0.08

    def choose(self, scored):
        scored = sorted(scored, key=lambda x: -x[0])
        if not scored or scored[0][0] < self.low:
            return None
        if len(scored) > 1 and scored[0][0] - scored[1][0] < self.gap:
            return None
        return scored[0][1]


class WordLlama(Threshold):
    """Static word vectors — what the memory graph's gate uses (256-d, 16 MB)."""
    name = "WordLlama (static vectors)"
    size, browser = "16 MB", "yes (a lookup table)"

    def __init__(self):
        try:
            sys.path.insert(0, str(HERE.parents[2]))
            from claude_memory_graph.gate import semantic
            self.enc = semantic.encoder()
        except Exception as exc:                          # noqa: BLE001
            raise Skip(f"wordllama not installed ({exc})")
        import numpy as np
        self.np = np

    def vec(self, text):
        return self.np.asarray(self.enc.encode([text]))[0]

    def pick(self, q, phrase, cands):
        p = self.vec(phrase)
        scored = [(float(p @ self.vec(describe(n))), n["alias"]) for n in cands]
        return self.choose(scored), scored


class VocabWordLlama(WordLlama):
    """The vocabulary's phrasings, matched by meaning with WordLlama: a node
    scores its best phrasing. Exact vocabulary hits win outright."""
    name = "vocabulary + WordLlama"
    size, browser = "16 MB + the vocabulary file", "yes"

    def __init__(self):
        super().__init__()
        self.vocab = _vocab()
        if self.vocab is None:
            raise Skip("no vocab.json")
        self.exact = VocabExact()
        self._cache = {}

    def cvec(self, text):
        if text not in self._cache:
            self._cache[text] = self.vec(text)
        return self._cache[text]

    def pick(self, q, phrase, cands, model=None):
        hit, _ = self.exact.pick(q, phrase, cands, model)
        p = self.vec(phrase)
        scored = []
        for n in cands:
            texts = [describe(n)] + self.vocab.get(model, {}).get(n["alias"], [])
            scored.append((max(float(p @ self.cvec(x)) for x in texts), n["alias"]))
        if hit:
            return hit, [(1.0 if a == hit else s, a) for s, a in scored]
        return self.choose(scored), scored


class OnnxBiEncoder(Threshold):
    """A small sentence-embedding transformer (ONNX): phrase-in-question vs node."""
    size, browser = "~25–35 MB (int8)", "yes (transformers.js / onnxruntime-web)"

    def __init__(self, folder: str, label: str, low=0.45, gap=0.04, pooling="mean"):
        self.name, self.low, self.gap, self.pooling = label, low, gap, pooling
        root = Path(os.environ.get("CEIST_BENCH_MODELS", "~/models")).expanduser() / folder
        if not (root / "model.onnx").exists():
            raise Skip(f"no weights at {root}")
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise Skip(f"runtime missing ({exc}): pip install onnxruntime tokenizers")
        self.np = np
        self.tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.sess = ort.InferenceSession(str(root / "model.onnx"))
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def embed(self, text):
        np = self.np
        enc = self.tok.encode(text)
        feed = {"input_ids": np.array([enc.ids], dtype=np.int64),
                "attention_mask": np.array([enc.attention_mask], dtype=np.int64)}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
        hidden = self.sess.run(None, feed)[0][0]          # tokens × dim
        if self.pooling == "cls":
            v = hidden[0]
        else:
            mask = np.array(enc.attention_mask, dtype=np.float32)[:, None]
            v = (hidden * mask).sum(0) / mask.sum()
        return v / (np.linalg.norm(v) or 1)

    def pick(self, q, phrase, cands):
        # the phrase in its question, so "built" next to "before 1900" reads as a date
        p = self.embed(f"{phrase} — as in: {q}")
        scored = [(float(p @ self.embed(describe(n))), n["alias"]) for n in cands]
        return self.choose(scored), scored


class OnnxCrossEncoder(Threshold):
    """A small cross-encoder (ONNX): reads question + node together, scores relevance."""
    size, browser = "~25 MB (int8)", "yes (transformers.js / onnxruntime-web)"

    def __init__(self, folder="cross-minilm", label="cross-encoder (MiniLM, ONNX)",
                 low=0.0, gap=1.0):
        self.name, self.low, self.gap = label, low, gap
        root = Path(os.environ.get("CEIST_BENCH_MODELS", "~/models")).expanduser() / folder
        if not (root / "model.onnx").exists():
            raise Skip(f"no weights at {root}")
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise Skip(f"runtime missing ({exc}): pip install onnxruntime tokenizers")
        self.np = np
        self.tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.sess = ort.InferenceSession(str(root / "model.onnx"))
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def score(self, a, b):
        np = self.np
        enc = self.tok.encode(a, b)
        feed = {"input_ids": np.array([enc.ids], dtype=np.int64),
                "attention_mask": np.array([enc.attention_mask], dtype=np.int64)}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
        return float(self.sess.run(None, feed)[0].reshape(-1)[0])     # a logit

    def pick(self, q, phrase, cands):
        scored = [(self.score(f'In "{q}", "{phrase}" refers to', describe(n)), n["alias"])
                  for n in cands]
        return self.choose(scored), scored


class GgufChooser:
    """A small instruction model (GGUF), forced by a grammar to answer with one
    of the option numbers or 0 (none). It chooses; it never writes a query."""
    browser = "yes (wllama: llama.cpp in WASM; WebGPU via WebLLM is faster)"

    def __init__(self, file: str, label: str, size: str):
        self.name, self.size = label, size
        path = Path(os.environ.get("CEIST_BENCH_MODELS", "~/models")).expanduser() / file
        if not path.exists():
            raise Skip(f"no weights at {path}")
        try:
            from llama_cpp import Llama, LlamaGrammar
        except ImportError as exc:
            raise Skip(f"runtime missing ({exc}): pip install llama-cpp-python")
        self.grammar_cls = LlamaGrammar
        self.llm = Llama(model_path=str(path), n_ctx=1024, verbose=False, seed=0)

    def pick(self, q, phrase, cands):
        options = "\n".join(f"{i}. {describe(n)}" for i, n in enumerate(cands, 1))
        prompt = (
            "You map a word in a question onto a field of a database record.\n"
            f'Question: "{q}"\n'
            f'Which field does "{phrase}" refer to?\n'
            f"{options}\n"
            "0. none of these\n"
            "Answer with the number only.\nAnswer: ")
        alts = " | ".join(f'"{i}"' for i in range(len(cands) + 1))
        grammar = self.grammar_cls.from_string(f"root ::= {alts}")
        out = self.llm(prompt, max_tokens=3, temperature=0.0, grammar=grammar)
        k = int(out["choices"][0]["text"].strip() or 0)
        return (cands[k - 1]["alias"] if k else None), None


def matchers():
    built = [lambda: Exact(), lambda: WordLlama(), lambda: VocabExact(), lambda: VocabWordLlama(),
             lambda: OnnxBiEncoder("minilm", "bi-encoder (all-MiniLM-L6-v2, ONNX)"),
             lambda: OnnxBiEncoder("bge-small", "bi-encoder (bge-small-en-v1.5, ONNX)", pooling="cls"),
             lambda: OnnxCrossEncoder(),
             lambda: GgufChooser("qwen3-0.6b.gguf", "Qwen3 0.6B (GGUF, chooses)", "~400 MB"),
             lambda: GgufChooser("qwen3-1.7b.gguf", "Qwen3 1.7B (GGUF, chooses)", "~1.1 GB"),
             lambda: GgufChooser("qwen3-4b.gguf", "Qwen3 4B (GGUF, chooses)", "~2.5 GB")]
    out, skipped = [], []
    for make in built:
        try:
            out.append(make())
        except Skip as why:
            skipped.append(str(why))
    return out, skipped


# ── scoring ────────────────────────────────────────────────────────────────

def run(m, models, cases, restricted: bool):
    tally = {"right": 0, "wrong": 0, "missed": 0, "false_match": 0, "abstained_ok": 0}
    rows, t0 = [], time.perf_counter()
    for case in cases:
        cands = candidates(models, case, restricted)
        if isinstance(m, (VocabExact, VocabWordLlama)):
            got, scored = m.pick(case["q"], case["phrase"], cands, case["model"])
        else:
            got, scored = m.pick(case["q"], case["phrase"], cands)
        want = case["expect"]
        if want is None:
            kind = "abstained_ok" if got is None else "false_match"
        elif got == want:
            kind = "right"
        elif got is None:
            kind = "missed"
        else:
            kind = "wrong"
        tally[kind] += 1
        rows.append({"q": case["q"], "phrase": case["phrase"], "expect": want, "got": got,
                     "result": kind, "scores": [(round(s, 3), a) for s, a in
                                                sorted(scored or [], key=lambda x: -x[0])][:3]})
    tally["ms_per_case"] = round((time.perf_counter() - t0) * 1000 / len(cases), 2)
    return tally, rows


def tune(rows):
    """For a scoring matcher: top-1 accuracy, and the threshold that does best
    on THIS set (a wrong pick costs 3 misses). Optimistic: tuned on what it's
    scored on — needs a held-out set before it's trusted."""
    if not rows or not any(r["scores"] for r in rows):
        return None
    top1 = sum(1 for r in rows if r["expect"] and r["scores"] and r["scores"][0][1] == r["expect"])
    best = None
    for low in [x / 100 for x in range(0, 45, 2)]:
        for gap in [x / 100 for x in range(0, 21, 2)]:
            right = bad = 0
            for r in rows:
                s = r["scores"]
                got = None
                if s and s[0][0] >= low and (len(s) == 1 or s[0][0] - s[1][0] >= gap):
                    got = s[0][1]
                if r["expect"] is None:
                    bad += got is not None
                elif got == r["expect"]:
                    right += 1
                elif got is not None:
                    bad += 1
            key = right - 3 * bad
            if best is None or key > best[0]:
                best = (key, right, bad, low, gap)
    return {"top1": top1, "right": best[1], "dangerous": best[2], "low": best[3], "gap": best[4]}


def report(results, skipped, n_match, n_none) -> str:
    out = ["# Phrase → node matcher comparison", "",
           f"{n_match + n_none} cases: {n_match} where a node fits, {n_none} where none does "
           "(the right answer is to abstain). A **dangerous** answer picks a node when it "
           "shouldn't, or the wrong node.", ""]
    for restricted in (True, False):
        out += [f"## {'Restricted by the planner (how ceist would use it)' if restricted else 'All nodes (the matcher alone)'}",
                "", "| matcher | right | dangerous | missed | abstained correctly | ms/case | size | in browser |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for m, by in results:
            t = by[restricted][0]
            out.append(f"| {m.name} | {t['right']}/{n_match} | **{t['wrong'] + t['false_match']}** | "
                       f"{t['missed']} | {t['abstained_ok']}/{n_none} | {t['ms_per_case']} | "
                       f"{m.size} | {m.browser} |")
        out.append("")
        tuned = [(m, tune(by[restricted][1])) for m, by in results]
        tuned = [(m, x) for m, x in tuned if x]
        if tuned:
            out += ["Scoring matchers, before and after tuning the thresholds:", "",
                    "| matcher | best-scored node is right (top-1) | tuned: right | tuned: dangerous | threshold, gap |",
                    "| --- | --- | --- | --- | --- |"]
            out += [f"| {m.name} | {x['top1']}/{n_match} | {x['right']}/{n_match} | "
                    f"{x['dangerous']} | {x['low']}, {x['gap']} |" for m, x in tuned]
            out += ["", "_Tuned on the same cases it is scored on: an upper bound until "
                    "checked on held-out questions._", ""]
    if skipped:
        out += ["## Skipped (not run — no numbers are estimated for these)", ""]
        out += [f"- {s}" for s in skipped] + [""]
    return "\n".join(out)


def main():
    models, cases = load()
    found, skipped = matchers()
    results = [(m, {r: run(m, models, cases, r) for r in (True, False)}) for m in found]
    n_none = sum(c["expect"] is None for c in cases)
    text = report(results, skipped, len(cases) - n_none, n_none)
    print(text)
    out = Path(os.environ.get("CEIST_BENCH_OUT", HERE / "results"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(text)
    (out / "details.json").write_text(json.dumps(
        {m.name: {("restricted" if r else "all"): by[r][1] for r in by} for m, by in results},
        indent=1))


if __name__ == "__main__":
    main()
