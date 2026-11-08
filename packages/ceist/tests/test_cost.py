"""The cost ledger, the size profile and the estimate, against stub LLMs."""

import importlib.util
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from test_ontology import data  # noqa: F401  (the module fixture)
from test_ontology_vocab import graphs_dir, ontology_dir, stub
from test_pipeline import project

from ceist import cost, ontology_vocab as ov, pipeline, questions

TRAINING = Path(__file__).resolve().parents[1] / "bench" / "training" / "run.py"

ENVELOPE = '''import json, sys
sys.stdin.read()
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": json.dumps({"ok": 1}),
                  "usage": {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 200,
                            "cache_creation_input_tokens": 0},
                  "modelUsage": {"claude-sonnet-5-5": {}}, **json.loads(sys.argv[1])}))
'''


def runner(tmp_path, extra: dict) -> pipeline.Runner:
    (tmp_path / "claude.py").write_text(ENVELOPE)
    return pipeline.Runner(tmp_path / "out", f"{sys.executable} {tmp_path / 'claude.py'} '{json.dumps(extra)}'")


def ledger(out) -> list[dict]:
    return cost.read_runs([out])[0]["spent"]


def test_the_ledger_records_usage_and_cost_and_zero_for_a_cached_reply(tmp_path):
    run = runner(tmp_path, {"total_cost_usd": 0.0123})
    assert run.ask("k", "a prompt", lambda r: [], {"kind": "values", "model": "Building"}) == {"ok": 1}
    assert run.ask("k", "a prompt", lambda r: [], {"kind": "values", "model": "Building"}) == {"ok": 1}
    paid, cached = ledger(tmp_path / "out")
    assert paid["stage"] == "data" and paid["llm"] == "claude-sonnet-5-5" and not paid["cached"]
    assert paid["usage"]["input_tokens"] == 1000 and paid["usage"]["output_tokens"] == 500
    assert paid["cost_usd"] == 0.0123 and paid["cost_from"] == "claude"
    assert cached["cached"] and cached["cost_usd"] == 0 and cached["usage"]["output_tokens"] == 0
    lines = cost.summary(run.ledger)
    assert "| data | 2 | 1 | 1000 | 200 | 0 | 500 | $0.01 |" in lines
    assert cost.NOTE in lines


def test_with_no_total_cost_the_price_table_prices_the_usage(tmp_path):
    run = runner(tmp_path, {})
    run.ask("k", "a prompt", lambda r: [], {"kind": "refine", "round": 2})
    row, = ledger(tmp_path / "out")
    # sonnet: 1000 in at $2, 500 out at $10, 200 cache reads at $0.20, per million
    assert row["stage"] == "refine" and row["round"] == 2 and row["cost_from"] == "prices"
    assert abs(row["cost_usd"] - (1000 * 2 + 500 * 10 + 200 * 0.2) / 1e6) < 1e-12


def test_the_estimate_counts_the_calls_a_stub_run_makes_per_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "BATCH", 2)
    graphs_data, ref, cmd, _ = project(tmp_path, {})
    graphs = graphs_data / "graphs"
    real = tmp_path / "real.txt"
    real.write_text("which listed buildings did Ada Lovelace design?\n")
    client = tmp_path / "client"
    client.mkdir()
    planned = Counter(x["stage"] for x in cost.plan(graphs, ["base", "data", "questions"], ref, client=client,
                                                    questions=real))
    pipeline.run(graphs, tmp_path / "base", ref, real, llm_cmd=cmd, log=lambda _: None)
    pipeline.run(graphs, tmp_path / "data", ref, real, llm_cmd=cmd, layer="data", client=client, log=lambda _: None)
    questions.generate(graphs, tmp_path / "questions", ref, llm_cmd=cmd, log=lambda _: None)
    made = Counter(r["stage"] for d in ("base", "data", "questions") for r in ledger(tmp_path / d))
    assert made == planned
    assert planned["base"] == 8 + 3 + 3 + 1   # per nodegroup, per model, its questions; the real ones labelled
    assert planned["data"] == 3 + 3          # five labels in two lists, batches of two; a phrases call per model


def test_the_estimate_counts_the_ontology_calls_a_stub_run_makes(tmp_path, monkeypatch):
    monkeypatch.setattr(ov, "BATCH", 1)
    graphs, onto = graphs_dir(tmp_path), ontology_dir(tmp_path)
    planned = [x for x in cost.plan(graphs, ["ontology"], ontology_dir=onto)]
    ov.propose([graphs], onto, tmp_path / "out", stub(tmp_path), log=lambda _: None)
    made = ledger(tmp_path / "out")
    assert len(planned) == len(made) == 4 and {r["stage"] for r in made} == {"ontology"}   # maker, made, keeper; kind, a list field


def test_the_estimate_sizes_replies_from_the_ledger_and_sets_itself_beside_it(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = runner(tmp_path, {})
    run.ask("k", "x" * 4000, lambda r: [], {"kind": "values"})
    graphs_data, ref, _, _ = project(tmp_path, {})
    e = cost.estimate(graphs_data / "graphs", ["data"], {"data": "sonnet"}, rounds=2, ledger=[tmp_path / "out"],
                      reference=ref)
    data_ = e["stages"]["data"]
    assert data_["output_tokens"] == 500 * data_["calls"] and data_["output_from"] == "ledger, 1 calls"
    assert e["stages"]["refine"]["calls"] == 2 and e["stages"]["refine"]["input_tokens"] == 2 * cost.DEFAULT_REFINE_INPUT
    assert e["stages"]["refine"]["output_from"] == "default (no history)"
    assert abs(sum(c[3] for c in e["calls"]) - data_["dollars"] - e["stages"]["refine"]["dollars"]) < 1e-12
    row = next(x for x in cost.against(cost.read_runs([tmp_path / "out"])) if "| data |" in x)
    est_in = (len(cost._system()) + 4000) // 4
    assert f"| 1 | {est_in} | 1200 | 500 | 500 |" in row


def test_an_old_run_with_prompts_only_reads_as_estimated_not_measured(tmp_path):
    (tmp_path / "audit.jsonl").write_text(json.dumps({"kind": "group", "prompt": "y" * 400}) + "\n")
    row = next(x for x in cost.against(cost.read_runs([tmp_path])) if "| base |" in x)
    assert "| 1 | " in row and "estimated, not measured" in row


def test_the_profile_counts_a_fixture_graph(data, tmp_path):  # noqa: F811
    root, _ = data
    ref = tmp_path / "ref" / "concepts"
    ref.mkdir(parents=True)
    for p in (root / "vocabularies").glob("*.xml"):
        shutil.copy(p, ref)
    onto = ontology_dir(tmp_path, [{"path": "P108i E12 P14", "kind": "link", "phrases": ["built by"]}])
    p = cost.profile(root / "graphs", ref.parent, onto)
    building = next(r for r in p["graphs"] if r["model"] == "Building")
    assert building == {"model": "Building", "nodegroups": 6, "link": 3, "date": 2, "property": 3,
                        "crm_paths": 5, "lists": 2, "distinct_lists": 2, "labels": 5, "long_lists": 0}
    # E22 E12 E39 E52 E61 E55 E21 E53; P108i P14 P4 P82a P2 P53; the actor, architect, date, status and site
    # paths, all but the actor's unphrased (the status a list field, which the ontology stage now proposes)
    assert p["ontology"] == {"classes": 8, "properties": 6, "paths": 5, "unphrased": 4, "unphrased_nodes": 4,
                             "calls": 1}


def _training():
    spec = importlib.util.spec_from_file_location("training_run", TRAINING)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_matrix_estimate_sums_its_runs_and_pays_a_shared_prompt_once(tmp_path):
    t = _training()
    paths = {"her": str(tmp_path / "her"), "demo": str(tmp_path / "demo"), "work": str(tmp_path / "work")}
    baseline = {"ontology": "none", "ontology_model": "opus", "base_model": "opus", "data_model": "sonnet",
                "questions_model": "opus", "seeds": True, "rounds": 0}
    runs = [dict(baseline, name="baseline"), dict(baseline, name="rounds-1", rounds=1)]
    calls = {"base": [["base", "opus", "b1", 1.0], ["base", "opus", "b2", 2.0]],
             "data": [["data", "sonnet", "d1", 0.5]], "questions": [["questions", "opus", "q1", 0.1]]}

    def est(graphs, args):
        stage = args[args.index("--stages") + 1]
        mine = calls[stage] + ([["refine", "sonnet", None, 0.25]] if stage == "data" and "1" in args else [])
        stages = {}
        for s, _, _, d in mine:
            stages.setdefault(s, {"calls": 0, "dollars": 0.0})
            stages[s]["calls"] += 1
            stages[s]["dollars"] += d
        return {"stages": stages, "calls": mine}

    lines = t.estimate_matrix(runs, baseline, paths, est)
    assert "| baseline | baseline |  | $3.00 |  | $0.50 |  | 3 | $3.50 |" in lines
    assert "| rounds-1 | rounds 1 |  | $3.00 | $0.10 | $0.50 | $0.25 | 5 | $3.85 |" in lines
    assert any("each run on its own: $7.35" in x and "**$3.85**" in x for x in lines)


def test_the_report_runs_over_a_results_file(tmp_path):
    t = _training()
    res = {"run": "rounds-1", "varies": "rounds 1", "choices": {"rounds": 1},
           "scores": {"fresh graphs": {"right": 40, "of": 50, "wrong": 2}, "demo bank": {"right": 60, "of": 87},
                      "HER plans": {"right": 120, "of": 125}, "hold-out": None},
           "cost": {"base": {"calls": 10, "cached": 2, "dollars": 3.0}, "refine": {"calls": 1, "cached": 0, "dollars": 0.2}},
           "size": {"base": 4, "data": 543}}
    (tmp_path / "results.jsonl").write_text(json.dumps(res) + "\n")
    lines = t.report([json.loads(x) for x in (tmp_path / "results.jsonl").read_text().splitlines()])
    assert "| rounds-1 | rounds 1 | 40/50 (2 wrong) | 60/87 | 120/125 |  | 9 | $3.20 |" in lines
    assert "| rounds-1 | base | 8 | $3.00 | 4 nodegroup | 2.00 | $0.750 |" in lines
    assert "| rounds-1 | refine | 1 | $0.20 | 1 round | 1.00 | $0.200 |" in lines
