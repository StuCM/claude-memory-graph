"""bench/run.py with stub question sets (kind jsonl) and a stub LLM: nothing real is run or sent."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import test_judge

from ceist import pipeline

BENCH = Path(__file__).parents[1] / "bench"


def load(name):
    spec = importlib.util.spec_from_file_location(f"bench_{name}", BENCH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run = load("run")
testbed = load("testbed")

ROWS = [
    {"question": "shelters", "narration": "Find Buildings.", "status": "right", "expected": 3, "got": 3},
    {"question": "hospitals", "narration": "wider reading", "status": "right", "expected": 4, "got": 4},
    {"question": "unclear one", "narration": "wrong reading", "status": "right", "expected": 0, "got": 0},
    {"question": "nonsense", "refused": "no grounding", "status": "right refusal"},
    {"question": "doctors", "refused": "no grounding", "status": "refused", "expected": 2},
    {"question": "ghost", "narration": "wrong reading", "status": "corpus missing"},
]


@pytest.fixture
def bench(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "CAP", None)
    (tmp_path / "stub.py").write_text(test_judge.STUB)
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("STUB_SKIP", "")
    rows = tmp_path / "rows.jsonl"
    rows.write_text("\n".join(json.dumps(r) for r in ROWS))
    sets = tmp_path / "sets.toml"
    sets.write_text("".join(f'[{n}]\nrole = "{role}"\nkind = "jsonl"\nfile = "{rows}"\n\n'
                            for n, role in (("reg", "regression"), ("dev", "development"), ("ex", "exam"))))

    def go(*args):
        return run.main(["--sets-file", str(sets), "--verdicts", str(tmp_path / "verdicts.jsonl"),
                         "--exam-log", str(tmp_path / "exam-log.jsonl"), "--out", str(tmp_path / "out"),
                         "--llm-cmd", f"{sys.executable} {tmp_path / 'stub.py'}", *args])
    return go, tmp_path


def summary(tmp_path) -> str:
    (out,) = (tmp_path / "out").iterdir()
    return (out / "summary.md").read_text()


def test_no_judge_prints_the_count_check_only(bench, capsys):
    go, tmp_path = bench
    assert go("--sets", "dev", "--no-judge") == 0
    assert "Count check: corpus missing 1, refused 1, right 3, right refusal 1" in summary(tmp_path)
    assert test_judge.calls(tmp_path) == []


def test_a_judged_run_tables_the_verdicts_and_lists_what_stays_unclear(bench):
    go, tmp_path = bench
    assert go("--sets", "dev") == 0
    text = summary(tmp_path)
    # shelters exact; hospitals wider (count says right: settled wider); unclear one: settled unclear;
    # nonsense right refusal; doctors missed
    row = next(x for x in text.splitlines() if x.startswith("| ") and "right 3" in x)
    assert row.split("|")[1:8] == [" 1 ", " 1 ", " 0 ", " 0 ", " 1 ", " 1 ", " 1 "]   # exact wider narrower wrong rr missed unclear
    assert "## To settle" in text and "'unclear one'" in text
    assert "'hospitals'" not in text.split("## To settle")[1]   # settled to wider, not left for a person


def test_a_disagreement_goes_to_settle_and_agreement_does_not(bench):
    go, tmp_path = bench
    go("--sets", "dev")
    settles = [p for p in test_judge.calls(tmp_path) if "Settle it" in p]
    asked = {json.loads(p.split("INPUT:\n", 1)[1])["question"] for p in settles}
    assert asked == {"hospitals", "unclear one"}


def test_a_second_run_sends_nothing_it_has_asked(bench):
    go, tmp_path = bench
    go("--sets", "dev")
    sent = len(test_judge.calls(tmp_path))
    assert sent > 0
    go("--sets", "dev")
    assert len(test_judge.calls(tmp_path)) == sent


def test_default_sets_leave_out_the_exam_set(bench):
    go, tmp_path = bench
    go("--no-judge")
    text = summary(tmp_path)
    assert "### reg (regression" in text and "### dev (development" in text and "### ex " not in text


def test_an_exam_set_is_refused_without_the_flag(bench, capsys):
    go, tmp_path = bench
    assert go("--sets", "ex", "--no-judge") == 2
    assert "only with --exam" in capsys.readouterr().err
    assert not (tmp_path / "exam-log.jsonl").exists() and not (tmp_path / "out").exists()


def test_an_exam_run_is_logged(bench):
    go, tmp_path = bench
    assert go("--sets", "ex", "--exam", "--no-judge", "--bundle", "b.json") == 0
    (line,) = (tmp_path / "exam-log.jsonl").read_text().splitlines()
    logged = json.loads(line)
    assert logged["set"] == "ex" and logged["bundle"] == "b.json" and logged["ts"] and "commit" in logged


def test_ant_without_a_cap_is_refused_and_sends_nothing(bench, capsys):
    go, tmp_path = bench
    assert go("--sets", "dev", "--llm", "ant") == 2
    assert "--llm ant needs --max-dollars" in capsys.readouterr().err
    assert not (tmp_path / "out").exists() and test_judge.calls(tmp_path) == []


@pytest.mark.parametrize("status, verdict, same", [
    ("right", "exact", True), ("right", "wider", False), ("right", "right refusal", True),
    ("right refusal", "exact", False), ("refused", "missed", True), ("refused", "right refusal", False),
    ("wrong, silent", "wider", True), ("wrong reading", "exact", False), ("as reviewed", "wrong", True),
])
def test_the_count_check_and_the_judge_agree_or_not(status, verdict, same):
    assert run.agrees(status, verdict) is same


def test_testbed_status_is_the_scored_classes():
    o = {"group": "answer", "accept": [5]}
    assert testbed.status(o, 5, False, False) == "right"
    assert testbed.status(o, 4, False, False) == "wrong, silent"
    assert testbed.status(o, 4, False, True) == "wrong, flagged"
    assert testbed.status(o, None, True, False) == "refused"
    assert testbed.status({"group": "refuse", "accept": []}, 1, False, False) == "wrong, silent"
    assert testbed.status({"group": "refuse", "accept": []}, None, True, False) == "right refusal"
