"""ceist.judge: batches of 20, the reply check, and the second judgement. A stub stands in for the LLM."""

import json
import sys

from ceist import cost, judge, pipeline

# Marks each item by the first verdict word in its narration (else exact), and logs the prompts it was given.
STUB = '''
import json, os, sys
prompt = sys.stdin.read()
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps(prompt) + "\\n")
payload = json.loads(prompt.split("INPUT:\\n", 1)[1])
def mark(x):
    if x.get("refused"):
        return "missed" if "doctor" in x["question"] else "right refusal"
    text = x.get("narration") or ""
    return next((v for v in ("wider", "narrower", "wrong") if v in text), "exact")
if "Settle it" in prompt:
    print(json.dumps({"verdict": "unclear" if "unclear" in payload["question"] else mark(payload), "reason": "r"}))
else:
    print(json.dumps({"verdicts": [{"id": x["id"], "verdict": mark(x), "reason": "r"} for x in payload
                                   if x["id"] != os.environ.get("STUB_SKIP")]}))
'''


def runner(tmp_path, monkeypatch, skip=""):
    (tmp_path / "stub.py").write_text(STUB)
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("STUB_SKIP", skip)
    monkeypatch.setattr(pipeline, "CAP", None)
    return pipeline.Runner(tmp_path / "out", f"{sys.executable} {tmp_path / 'stub.py'}", "opus")


def calls(tmp_path) -> list[str]:
    log = tmp_path / "log.jsonl"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def items(n):
    return [{"id": f"s:{i}", "question": f"q{i}", "narration": "wider reading" if i % 2 else "Find Buildings."}
            for i in range(n)]


def test_judge_sends_twenty_readings_a_call(tmp_path, monkeypatch):
    got = judge.judge(items(45), runner(tmp_path, monkeypatch), "opus")
    assert len(calls(tmp_path)) == 3
    assert len(got) == 45
    assert {v["id"]: v["verdict"] for v in got}["s:1"] == "wider"
    assert {v["id"]: v["verdict"] for v in got}["s:0"] == "exact"


def test_a_reply_missing_an_id_is_rejected_and_asked_again(tmp_path, monkeypatch):
    got = judge.judge(items(3), runner(tmp_path, monkeypatch, skip="s:2"), "opus")
    prompts = calls(tmp_path)
    assert len(prompts) == 2 and "no verdict for id s:2" in prompts[1]
    assert got == []   # still missing on the retry: the batch is left out, not guessed


def test_check_rejects_an_unknown_verdict():
    check = judge._check_batch(["a"])
    assert check({"verdicts": [{"id": "a", "verdict": "fine", "reason": "r"}]})
    assert check({"verdicts": [{"id": "a", "verdict": "wider", "reason": "r"}]}) == []


def test_settle_adds_the_expected_count_and_may_say_unclear(tmp_path, monkeypatch):
    r = runner(tmp_path, monkeypatch)
    item = {"id": "s:1", "question": "unclear one", "narration": "Find Buildings.", "expected": 10, "note": "n",
            "got": 7, "first": "wrong", "first_reason": "x"}
    assert judge.settle(item, r, "opus")["verdict"] == "unclear"
    assert '"expected": 10' in calls(tmp_path)[0] and '"got": 7' in calls(tmp_path)[0]
    assert judge.settle({**item, "question": "q", "narration": "wider"}, r, "opus")["verdict"] == "wider"


def test_judge_and_settle_are_priced_as_stages():
    assert cost.stage_of({"kind": "judge"}) == "judge" and cost.stage_of({"kind": "settle"}) == "settle"
    assert {"judge", "settle"} <= set(cost.ORDER) and cost.MODELS["judge"] == "opus"
