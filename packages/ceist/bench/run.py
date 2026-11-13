"""One command scores every question set, and an LLM judges what each reading means.

    .venv-ceist/bin/python packages/ceist/bench/run.py [--sets regression,her-2.0] [--exam]
        [--bundle B] [--src DIR] [--no-judge] [--llm ant --max-dollars N] [--model opus]

Each set in sets.toml is collected by its own runner (bank, structural, reorder, her, testbed) into rows of
{question, narration or refusal, count status}. The judge marks each row from Ceist's narration alone
(exact / wider / narrower / wrong / right refusal / missed). Where the mark and the count check disagree, a
second judgement settles it; what that one calls unclear is listed for a person. Verdicts are cached in
verdicts.jsonl, so a rerun sends nothing it has already asked. Exam sets run only with --exam, and each use
is logged in exam-log.jsonl. Nothing here runs at question time.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROLES = ("regression", "development", "exam")
VERDICTS = ("exact", "wider", "narrower", "wrong", "right refusal", "missed")
NOT_JUDGED = ("corpus missing", "no record to fill")


def agrees(status: str, verdict: str) -> bool:
    """Whether the count check's status and the judge's verdict say the same; a status that only
    compares with reviewed text (her) has no count to disagree with."""
    if status in ("right", "right, live flagged"):
        return verdict in ("exact", "right refusal")
    if status == "right refusal":
        return verdict == "right refusal"
    if status in ("refused", "refused-should-answer"):
        return verdict == "missed"
    if status.startswith("wrong"):
        return verdict in ("wider", "narrower", "wrong")
    return True


def load_sets(path: Path) -> dict[str, dict]:
    return tomllib.loads(path.read_text())


def choose(sets: dict, wanted: str | None, exam: bool) -> list[str] | str:
    """The set names to run, or the reason none can."""
    if wanted is None:
        names = [n for n, s in sets.items() if s["role"] in ("regression", "development")]
    else:
        names = []
        for w in wanted.split(","):
            hit = [n for n, s in sets.items() if n == w or s["role"] == w]
            if not hit:
                return f"no set or role called '{w}' in sets.toml"
            names += [n for n in hit if n not in names]
    if exam and wanted is None:
        names += [n for n, s in sets.items() if s["role"] == "exam"]
    refused = [n for n in names if sets[n]["role"] == "exam" and not exam]
    if refused:
        return f"{', '.join(refused)}: exam set(s) are scored only with --exam, and each use is logged"
    return names


def commit_of() -> str:
    p = subprocess.run(["git", "-C", str(HERE), "rev-parse", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip()


def log_exam(path: Path, names: list[str], sets: dict, bundle: str | None) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(path, "a", encoding="utf-8") as f:
        for n in names:
            if sets[n]["role"] == "exam":
                f.write(json.dumps({"ts": ts, "set": n, "bundle": bundle or sets[n].get("bundle", ""),
                                    "commit": commit_of()}) + "\n")


# ---- collecting: each runner returns rows {question, narration, refused, status, expected, note, got}

def load_script(path: Path) -> dict:
    """A bench script's functions without running its trailing `main()`."""
    src = path.read_text().rsplit("\nmain()", 1)[0]
    ns = {"__file__": str(path), "__name__": path.stem}
    sys.path.insert(0, str(path.parent))
    exec(compile(src, str(path), "exec"), ns)
    return ns


def collect_bank() -> list[dict]:
    ns = load_script(HERE / "demo" / "run_bank.py")
    ask = ns["ask"]
    v, r, m, rec = ask.startup()
    rows = []
    for o in json.loads(ns["BANK"].read_text())["questions"]:
        a = ask.answer(o["q"], v, r, m, rec)
        rows.append({"question": o["q"], "narration": a.get("understood"), "refused": a.get("refused"),
                     "status": ns["status"](o, a), "expected": o.get("count"), "note": o.get("note"),
                     "got": a.get("total")})
    return rows


def collect_reorder() -> list[dict]:
    ns = load_script(HERE / "assembly" / "measure.py")
    ask = ns["ask"]
    seen, real = [], ask.answer
    ask.answer = lambda *a: seen.append(real(*a)) or seen[-1]   # run() makes one ask.answer call per question
    items = json.loads(ns["BANKS"]["reorder"].read_text())["questions"]
    v, r, matcher, rec = ask.startup()
    out = ns["run"](items, "strict", True, v, r, matcher, rec)
    return [{"question": x["q"], "narration": a.get("understood"), "refused": a.get("refused"),
             "status": x["status"], "expected": o.get("count"), "note": o.get("note"), "got": a.get("total")}
            for o, x, a in zip(items, out, seen)]


def collect_structural(cfg: dict) -> list[dict]:
    ns = load_script(HERE / "demo" / "run_bank.py")
    from ceist import interpret, narrate
    from ceist.questions import fill, score, target_of
    v, _, matcher, _ = ns["ask"].startup()
    rows = []
    for o in json.loads(Path(cfg["file"]).read_text())["questions"]:
        q = fill(o["q"], v)
        if q is None:
            rows.append({"question": o["q"], "status": "no record to fill"})
            continue
        m = interpret(v, q, matcher=matcher)
        meaning = m.plan or m.detail
        rows.append({"question": q, "narration": narrate(meaning) if meaning else None, "refused": m.refused,
                     "status": score(o, m), "expected": json.dumps(o.get("target") or o.get("reason")),
                     "got": json.dumps(target_of(m))})
    return rows


def collect_her(cfg: dict) -> list[dict]:
    sys.path.insert(0, str(HERE))
    import her_plans
    pkg, work = Path(cfg["pkg"]), Path(tempfile.mkdtemp())
    ceist = [sys.executable, "-m", "ceist.cli", "vocab"]
    quiet = {"check": True, "capture_output": True}
    subprocess.run([*ceist, "describe", pkg / "graphs" / "resource_models", work / "models",
                    "--reference", pkg / "reference_data"], **quiet)
    bundle = work / "bundle.json"
    subprocess.run([*ceist, "assemble", work / "models", HERE / "her" / "vocab", "-o", bundle,
                    "--graphs", pkg / "graphs" / "resource_models"], **quiet)
    reviewed = json.loads((HERE / cfg["plans"]).read_text())
    rows = []
    for q, plan in her_plans.answers(pkg, bundle).items():
        refused = plan == "refused"
        rows.append({"question": q, "narration": None if refused else plan, "refused": "refused" if refused else "",
                     "status": "as reviewed" if reviewed.get(q) == plan else "changed",
                     "expected": reviewed.get(q)})
    return rows


def collect_testbed(cfg: dict, bundle: str | None) -> list[dict]:
    sys.path.insert(0, str(HERE))
    import testbed
    note = ""
    if "expect" in cfg:
        qset, note = testbed.expected(Path(cfg["corpus"]), Path(cfg["questions"]), Path(cfg["expect"]),
                                      cfg["sha256"])
    else:
        qset = testbed.from_bank(json.loads(Path(cfg["questions"]).read_text())["questions"])
    sha = testbed.sha256(Path(cfg["questions"]))
    if "expect" not in cfg and "sha256" in cfg and sha != cfg["sha256"]:
        note = f"not the frozen file: sha {sha[:12]}, frozen {cfg['sha256'][:12]}"
    if note:
        print(f"testbed: {note}", file=sys.stderr)
    rows = []
    for r in testbed.rows(qset, Path(cfg["corpus"]), Path(bundle or cfg["bundle"])):
        rows.append({"question": r["q"], "narration": r["understood"], "refused": r["refused"],
                     "status": r["status"], "expected": r["accept"], "note": r["note"], "got": r["got"],
                     "group": r["group"], "tier": r.get("tier", "")})
    return rows


def collect(name: str, cfg: dict, bundle: str | None) -> list[dict]:
    kind = cfg["kind"]
    if kind == "bank":
        return collect_bank()
    if kind == "reorder":
        return collect_reorder()
    if kind == "structural":
        return collect_structural(cfg)
    if kind == "her":
        return collect_her(cfg)
    if kind == "testbed":
        return collect_testbed(cfg, bundle)
    if kind == "jsonl":
        return [json.loads(line) for line in Path(cfg["file"]).read_text().splitlines()]
    raise SystemExit(f"{name}: unknown kind '{kind}'")


def collect_in_child(name: str, cfg: dict, args) -> list[dict]:
    """The set's rows, collected by `run.py --collect` in the python (and directory) the set names."""
    if cfg["kind"] == "jsonl":
        return collect(name, cfg, args.bundle)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rows.jsonl"
        cmd = [*cfg.get("python", [sys.executable]), str(HERE / "run.py"), "--collect", name,
               "--sets-file", str(args.sets_file), "--rows", str(out)]
        if args.bundle:
            cmd += ["--bundle", args.bundle]
        env = dict(os.environ, PYTHONPATH=args.src + os.pathsep + os.environ.get("PYTHONPATH", ""))
        p = subprocess.run(cmd, cwd=cfg.get("cwd"), env=env)
        if p.returncode:
            raise RuntimeError(f"{name}: the runner exited {p.returncode}")
        return [json.loads(line) for line in out.read_text().splitlines()]


# ---- judging

def digest(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


class Verdicts:
    """verdicts.jsonl: {key, verdict, reason} for each judgement, and the same with "settled" for a settled one."""

    def __init__(self, path: Path):
        self.path = path
        self.seen = {}
        if path.exists():
            for line in path.read_text().splitlines():
                r = json.loads(line)
                self.seen[r["key"]] = r

    def add(self, key: str, verdict: str, reason: str, settled: bool = False) -> dict:
        r = {"key": key, "verdict": verdict, "reason": reason, **({"settled": True} if settled else {})}
        self.seen[key] = r
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return r


def judge_rows(rows: list[dict], verdicts: Verdicts, make_runner, model: str) -> None:
    """Fills each row's `judged`, `reason` and, where the count disagrees, `settled`: {verdict, reason}."""
    from ceist import judge as _judge
    todo = [r for r in rows if r["status"] not in NOT_JUDGED]
    for r in todo:
        r["jkey"] = digest(r["question"], r.get("narration"), r.get("refused"), _judge.PROMPT_VERSION)
    new = [r for r in todo if r["jkey"] not in verdicts.seen]
    if new:
        by_id = {r["id"]: r for r in new}
        items = [{"id": r["id"], "question": r["question"], "narration": r.get("narration"),
                  "refused": r.get("refused") or None} for r in new]
        for v in _judge.judge(items, make_runner(), model):
            verdicts.add(by_id[v["id"]]["jkey"], v["verdict"], v["reason"])
    for r in todo:
        first = verdicts.seen.get(r["jkey"])
        if first is None:
            continue
        r["judged"], r["reason"] = first["verdict"], first["reason"]
        if agrees(r["status"], r["judged"]):
            continue
        skey = digest("settle", r["jkey"], r.get("expected"), r.get("got"), r["status"])
        if skey not in verdicts.seen:
            item = {"id": r["id"], "question": r["question"], "narration": r.get("narration"),
                    "refused": r.get("refused") or None, "expected": r.get("expected"), "note": r.get("note"),
                    "got": r.get("got"), "first": r["judged"], "first_reason": r["reason"]}
            s = _judge.settle(item, make_runner(), model)
            if s:
                verdicts.add(skey, s["verdict"], s["reason"], settled=True)
        if skey in verdicts.seen:
            r["settled"] = {k: verdicts.seen[skey][k] for k in ("verdict", "reason")}


def final_verdict(r: dict) -> str:
    if "judged" not in r:
        return "unjudged"
    return r["settled"]["verdict"] if "settled" in r else r["judged"]


# ---- the report

def table(name: str, role: str, rows: list[dict], judged: bool) -> list[str]:
    counts = Counter(r["status"] for r in rows)
    count_col = ", ".join(f"{k} {n}" for k, n in sorted(counts.items()))
    lines = [f"### {name} ({role}, {len(rows)} questions)", ""]
    if not judged:
        return lines + [f"Count check: {count_col}", ""]
    cols = (*VERDICTS, "unclear", "unjudged")
    final = Counter(final_verdict(r) for r in rows if r["status"] not in NOT_JUDGED)
    lines += ["| " + " | ".join(cols) + " | count check |", "| --- " * (len(cols) + 1) + "|",
              "| " + " | ".join(str(final[c]) for c in cols) + f" | {count_col} |", ""]
    return lines + [f"Judge and count disagreed on {sum(map(disagrees, rows))}.", ""]


def disagrees(r: dict) -> bool:
    return "judged" in r and not agrees(r["status"], r["judged"])


def to_settle(rows: list[dict]) -> list[str]:
    """The disagreements the second judgement called unclear or could not make."""
    out = []
    for r in rows:
        if not disagrees(r) or ("settled" in r and r["settled"]["verdict"] != "unclear"):
            continue
        said = r.get("narration") or f"refused: {r.get('refused')}"
        why = (r.get("settled") or {}).get("reason") or "the second judgement could not be made"
        out.append(f"- {r['id']} {r['question']!r} :: {said}\n  count check {r['status']} "
                   f"(expected {r.get('expected')}, got {r.get('got')}); judge {r['judged']}: {r['reason']}\n"
                   f"  second judgement: {why}")
    return out


def run(args) -> int:
    sets = load_sets(args.sets_file)
    names = choose(sets, args.sets, args.exam)
    if isinstance(names, str):
        print(names, file=sys.stderr)
        return 2
    if args.llm == "ant" and args.max_dollars is None and not args.no_judge:
        print("--llm ant needs --max-dollars N: the most this command may spend on API credits", file=sys.stderr)
        return 2
    if args.exam:
        log_exam(args.exam_log, names, sets, args.bundle)
    out = args.out / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out.mkdir(parents=True, exist_ok=True)
    all_rows, failed = {}, []
    for n in names:
        try:
            all_rows[n] = collect_in_child(n, sets[n], args)
        except (RuntimeError, OSError, KeyError) as e:
            failed.append(f"{n}: {e}")
            continue
        for i, r in enumerate(all_rows[n], 1):
            r.update(set=n, id=f"{n}:{i}")
    judged, runner = not args.no_judge, None
    if judged:
        from ceist import pipeline

        def make_runner():
            nonlocal runner
            if runner is None:
                if args.llm == "ant":
                    pipeline.CAP = pipeline.Cap(args.max_dollars)
                runner = pipeline.Runner(out / "llm", args.llm_cmd, args.model)
            return runner

        verdicts = Verdicts(args.verdicts)
        try:
            judge_rows([r for rows in all_rows.values() for r in rows], verdicts, make_runner, args.model)
        except pipeline.OverCap as e:
            print(e, file=sys.stderr)
            return 1
    lines = [f"# Benchmark {out.name}", "", f"commit {commit_of()[:10]}, sets: {', '.join(names)}"
             + (f", bundle {args.bundle}" if args.bundle else ""), ""]
    for n, rows in all_rows.items():
        lines += table(n, sets[n]["role"], rows, judged)
    lines += [f"FAILED {f}" for f in failed]
    if judged:
        settle = [x for rows in all_rows.values() for x in to_settle(rows)]
        lines += ["## To settle", "", *(settle or ["Nothing: every disagreement was settled."]), ""]
        if runner is not None:
            from ceist import cost
            lines += cost.summary(runner.ledger)
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    with open(out / "rows.jsonl", "w", encoding="utf-8") as f:
        for rows in all_rows.values():
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print("\n".join(lines))
    print(f"written to {out}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sets", help="set names or roles, comma-separated (default: regression + development)")
    ap.add_argument("--exam", action="store_true", help="include the exam sets; each use is logged")
    ap.add_argument("--bundle", help="the vocabulary bundle the testbed sets are scored with")
    ap.add_argument("--src", default=str(HERE.parent / "src"), help="the Ceist source scored (PYTHONPATH)")
    ap.add_argument("--no-judge", action="store_true", help="counts only")
    ap.add_argument("--llm", choices=["claude", "ant"], default="claude")
    ap.add_argument("--llm-cmd", help="a stub standing in for the LLM: reads the prompt on stdin")
    ap.add_argument("--max-dollars", type=float)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--sets-file", type=Path, default=HERE / "sets.toml")
    ap.add_argument("--verdicts", type=Path, default=HERE / "verdicts.jsonl")
    ap.add_argument("--exam-log", type=Path, default=HERE / "exam-log.jsonl")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--collect", help=argparse.SUPPRESS)
    ap.add_argument("--rows", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.collect:
        rows = collect(args.collect, load_sets(args.sets_file)[args.collect], args.bundle)
        args.rows.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
