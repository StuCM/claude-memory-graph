"""A question set scored against a record corpus, after the testbed's score.py: every question through
`interpret`, its plan evaluated over the corpus, the count compared with the expected one.

    testbed.expected(corpus, questions, expect_py, frozen)   Phil's testbed: counts from his expect.py
    testbed.from_bank(questions)                             a bank-shaped set ({q, expect, count})
    testbed.rows(qset, corpus, bundle)                       one row per question
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected(corpus: Path, questions: Path, expect_py: Path, frozen: str) -> tuple[list[dict], str]:
    """The questions with the counts expect.py computes from the corpus alone, and a note
    saying whether the set is the frozen one (expect.py prints the set's sha)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "expected.json"
        p = subprocess.run([sys.executable, str(expect_py), str(corpus), str(questions), str(out)],
                           capture_output=True, text=True, check=True)
        sha = p.stdout.strip().splitlines()[-1]
        qset = json.loads(out.read_text())["questions"]
    note = "the frozen set" if sha == frozen else (
        f"corpus changed: the set's sha is {sha[:12]}, the frozen one {frozen[:12]}; counts differ from the baseline")
    return qset, note


def from_bank(questions: list[dict]) -> list[dict]:
    """A bank-shaped set in the testbed's: the group and the accepted counts."""
    return [{"n": i, "q": o["q"], "note": o.get("note", ""),
             "group": "answer" if o["expect"] == "answer" else "refuse",
             "accept": [] if o.get("count") is None else [o["count"]]}
            for i, o in enumerate(questions, 1)]


def status(o: dict, got, refused: bool, flagged: bool) -> str:
    g = o["group"]
    if g == "missing":
        return "corpus missing"
    if g in ("refuse", "live"):
        if refused:
            return "right refusal"
        return "wrong, flagged" if flagged else "wrong, silent"
    if refused:
        return "refused"
    if got in o["accept"]:
        return "right"
    return "wrong, flagged" if flagged else "wrong, silent"


def rows(qset: list[dict], corpus: Path, bundle: Path) -> list[dict]:
    from ceist import interpret, narrate
    from ceist.alizarin import Tiles, evaluate
    from ceist.arches import ArchesVocabulary
    from ceist.config import chain, load
    matcher = chain(load(os.environ.get("CEIST_CONFIG") or None))
    vocab = ArchesVocabulary.from_data_dir(corpus, bundle=bundle)
    tiles = Tiles(vocab)

    def answer(q):
        """(count or None when refused, refusal, narration, relaxed)"""
        m = interpret(vocab, q, matcher=matcher)
        if m.refused or m.statement:
            return None, m.refused or "statement", None, False
        if m.direct is not None:
            return 1, "", f"Show the record {m.direct.type} '{m.direct.name}'.", False
        if m.detail is not None:
            return 1, "", narrate(m.detail), False
        if m.plan.group is not None:
            return None, "group-by", None, False
        for plan, note in [(m.plan, "")] + [(r.plan, r.note) for r in m.relaxations]:
            ids = evaluate(plan, tiles)
            if ids or not note:
                return len(ids), "", narrate(plan), bool(note)
        return 0, "", None, False

    out = []
    for o in qset:
        start = time.time()
        got, refused, understood, relaxed = answer(o["q"])
        out.append({**o, "status": status(o, got, got is None, relaxed), "got": got,
                    "understood": understood, "refused": refused, "ms": (time.time() - start) * 1000})
    return out
