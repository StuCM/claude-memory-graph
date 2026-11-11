"""--llm ant: `ant messages create` on API credits, under a --max-dollars cap, with a fake ant on PATH."""

import json
import os
import sys

import pytest
from test_pipeline import project

from ceist import cost, pipeline, prices
from ceist.cli import main

TOKEN = "sk-ant-oat01-not-a-real-token"
USAGE = {"input_tokens": 1000, "output_tokens": 500}

# Answers each message as test_pipeline's fake LLM does, and logs what it was given. FAKE_ANT_FAIL:
# exits 1 once the request is in; FAKE_ANT_DENSE: bills two characters a token and the whole max_tokens.
FAKE_ANT = f'''#!{sys.executable}
import json, os, subprocess, sys
body = json.load(sys.stdin)
log = os.environ["FAKE_ANT_LOG"]
with open(log, "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "body": body}}) + "\\n")
if os.environ.get("FAKE_ANT_FAIL"):
    sys.exit("connection reset")
content = body["messages"][0]["content"]
if os.environ.get("FAKE_ANT_DENSE"):
    reply = "{{}}"
    usage = {{"input_tokens": len(body["system"] + content) // 2, "output_tokens": body["max_tokens"]}}
else:
    reply = subprocess.run([sys.executable, *os.environ["FAKE_LLM"].split()], input=content,
                           capture_output=True, text=True).stdout
    usage = {json.dumps(USAGE)}
print(json.dumps({{"model": body["model"], "content": [{{"type": "text", "text": reply}}], "usage": usage}},
                 indent=2))
'''


@pytest.fixture
def ant(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "CAP", None)
    data, ref, cmd, _ = project(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ant").write_text(FAKE_ANT)
    (bin_dir / "ant").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_ANT_LOG", str(tmp_path / "ant.jsonl"))
    monkeypatch.setenv("FAKE_LLM", cmd.split(maxsplit=1)[1])
    monkeypatch.setenv("ANTHROPIC_API_KEY", TOKEN)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", TOKEN)
    return data, ref, tmp_path


def sent(tmp_path) -> list[dict]:
    log = tmp_path / "ant.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def pipeline_args(data, ref, out, *more) -> list[str]:
    return ["vocab", "pipeline", str(data / "graphs"), "-o", str(out), "--reference", str(ref), "--llm", "ant",
            *more]


def test_ant_refuses_to_start_without_a_cap(ant, capsys):
    data, ref, tmp_path = ant
    assert main(pipeline_args(data, ref, tmp_path / "out")) == 2
    assert "--llm ant needs --max-dollars" in capsys.readouterr().err
    assert sent(tmp_path) == [] and not (tmp_path / "out").exists()


def test_ant_sends_the_prompts_and_the_ledger_records_its_usage(ant, capsys):
    data, ref, tmp_path = ant
    out = tmp_path / "out"
    assert main(pipeline_args(data, ref, out, "--max-dollars", "50")) == 0
    printed = capsys.readouterr().out
    assert "capped at $50.00" in printed
    assert printed.index("| base | opus |") < printed.index("nodegroups built")   # the estimate comes first
    assert "--llm ant: no claude -p system prompt" in printed and "about 33k tokens" not in printed

    calls = sent(tmp_path)
    assert len(calls) == 15
    first = calls[0]
    assert first["argv"] == ["--format", "json", "messages", "create"]
    assert first["body"]["model"] == "claude-opus-5-5" and first["body"]["system"] == pipeline.CLAUDE[-1]
    assert first["body"]["max_tokens"] == pipeline.ANT_MAX_TOKENS
    assert first["body"]["messages"][0]["content"].startswith("You are the offline")

    rows = cost.read_runs([out])[0]["spent"]
    assert len(rows) == 15
    each = prices.cost(USAGE, "opus")
    for row in rows:
        assert row["llm"] == "claude-opus-5-5" and row["cost_from"] == "prices"
        assert row["usage"]["input_tokens"] == 1000 and row["usage"]["output_tokens"] == 500
        assert row["cost_usd"] == pytest.approx(each)
    assert "**passed**" in (out / "report.md").read_text()


def test_ant_stops_before_a_call_that_could_pass_the_cap(ant, capsys):
    data, ref, tmp_path = ant
    out = tmp_path / "out"
    # a call costs $0.014 by its usage here, and its worst case about $0.33 (16k output tokens)
    assert main(pipeline_args(data, ref, out, "--max-dollars", "0.40")) == 1
    err = capsys.readouterr().err
    each = prices.cost(USAGE, "opus")
    calls = sent(tmp_path)
    assert len(calls) == 5
    for i, call in enumerate(calls):
        worst = prices.cost({"input_tokens": len((pipeline.CLAUDE[-1] + call["body"]["messages"][0]["content"]).encode()),
                             "output_tokens": pipeline.ANT_MAX_TOKENS}, "opus")
        assert i * each + worst <= 0.40
    rows = cost.read_runs([out])[0]["spent"]
    assert len(rows) == 5 and sum(r["cost_usd"] for r in rows) == pytest.approx(5 * each)
    assert "Stopped by --max-dollars $0.40: spent $0.07." in err
    assert "Done: 5 paid call(s)" in err
    refused = float(err.split("worst case $")[1].split(",")[0])
    assert 5 * each + refused > 0.40
    assert "Not done: the next call (group Building; worst case" in err and "and the rest of this command." in err

    # a rerun with room takes the five from the cache and pays only for the rest
    assert main(pipeline_args(data, ref, out, "--max-dollars", "50")) == 0
    assert len(sent(tmp_path)) == 15


def test_no_token_reaches_argv_the_output_or_the_ledger(ant, capsys):
    data, ref, tmp_path = ant
    out = tmp_path / "out"
    assert main(pipeline_args(data, ref, out, "--max-dollars", "0.40")) == 1
    assert main(["questions", "generate", str(data / "graphs"), "-o", str(tmp_path / "q"), "--reference", str(ref),
                 "--llm", "ant", "--max-dollars", "5"]) == 0
    printed = capsys.readouterr()
    assert sent(tmp_path)
    written = [p.read_text() for p in tmp_path.rglob("*") if p.is_file() and p.name != "ant.jsonl"]
    assert any("cost_usd" in text for text in written)
    for text in [printed.out, printed.err, (tmp_path / "ant.jsonl").read_text(), *written]:
        assert TOKEN not in text


def test_the_llm_cmd_stub_and_claude_p_stay_the_default(ant):
    data, ref, tmp_path = ant
    assert main(["vocab", "estimate", str(data / "graphs"), "--reference", str(ref)]) == 0
    assert pipeline.CAP is None and pipeline.Runner(tmp_path / "x").argv[:2] == ["claude", "-p"]


def test_a_prompt_that_tokenises_densely_cannot_pass_the_cap(ant, monkeypatch):
    _, _, tmp_path = ant
    monkeypatch.setenv("FAKE_ANT_DENSE", "1")
    prompt = json.dumps([{"alias": f"node_{i}", "nodegroup": f"group_{i}"} for i in range(2000)])
    by_chars = prices.cost({"input_tokens": cost.by_chars(prompt), "output_tokens": pipeline.ANT_MAX_TOKENS}, "opus")
    monkeypatch.setattr(pipeline, "CAP", pipeline.Cap(by_chars + 0.001))   # room for chars / 4, not for the bill
    run = pipeline.Runner(tmp_path / "out")
    with pytest.raises(pipeline.OverCap):
        run.ask("k", prompt, lambda r: [], {"kind": "test"})
    assert pipeline.CAP.spent() <= pipeline.CAP.max_dollars


def test_a_failed_ant_call_costs_its_worst_case(ant, monkeypatch):
    _, _, tmp_path = ant
    monkeypatch.setenv("FAKE_ANT_FAIL", "1")
    monkeypatch.setattr(pipeline, "CAP", pipeline.Cap(0.50))
    run = pipeline.Runner(tmp_path / "out")
    assert run.ask("k", "a prompt", lambda r: [], {"kind": "test"}) is None
    assert run.failures[0]["errors"][0].startswith("ant exited 1: connection reset")
    row, = cost.read_runs([tmp_path / "out"])[0]["spent"]
    assert row["cost_from"] == "worst case (no usage reported)" and row["cost_usd"] > 0.32
    with pytest.raises(pipeline.OverCap):   # the failed call's worst case leaves too little for another
        run.ask("k2", "a prompt", lambda r: [], {"kind": "test"})
    assert len(sent(tmp_path)) == 1


def test_calls_under_way_hold_their_worst_case():
    cap = pipeline.Cap(0.50)
    worst = cap.reserve("a prompt", "opus", {})
    with pytest.raises(pipeline.OverCap, match=r"held for calls under way"):
        cap.reserve("a prompt", "opus", {})
    cap.release(worst)
    cap.release(cap.reserve("a prompt", "opus", {}))
    assert cap.held == 0
