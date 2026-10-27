"""The stateless hook runner the mod calls, and the hookcore helpers it
stands on (formerly claude-hook-kit's own tests)."""

import io
import json
import subprocess

import pytest

from claude_memory_graph import hookrun
from claude_memory_graph.hookcore import (HookExtension, advance_core, project_of,
                                          state as hc_state, terms)
from claude_memory_graph.gate.logview import format_log_entry, print_log


# ---------------------------------------------------------------- tokenizer

def test_ack_words_yield_no_terms():
    assert terms("Thanks, yes please — OK!") == []


def test_terms_keep_distinctive_words():
    assert "pyoxigraph" in terms("why did we pick pyoxigraph?")


def test_system_reminders_do_not_count_as_significant():
    core = advance_core({}, "UserPromptSubmit", {
        "prompt": "<system-reminder>pyoxigraph rdflib quad store</system-reminder> thanks"})
    assert core["prompt_count"] == 1
    assert core["significant_prompt_count"] == 0


# --------------------------------------------------------------------- core

def test_core_counts_prompts_and_significance():
    core = {}
    advance_core(core, "SessionStart", {"session_id": "s1", "cwd": "/w/quartz"})
    advance_core(core, "UserPromptSubmit", {"cwd": "/w/quartz", "prompt": "design the harness merge"})
    advance_core(core, "UserPromptSubmit", {"cwd": "/w/quartz", "prompt": "thanks"})
    assert core["project"] == "quartz"
    assert core["prompt_count"] == 2
    assert core["significant_prompt_count"] == 1
    assert core["events"] == {"SessionStart": 1, "UserPromptSubmit": 2}


def test_project_is_git_root_not_subdirectory(tmp_path):
    repo = tmp_path / "charcoal"
    (repo / "frontend").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert project_of(str(repo / "frontend")) == "charcoal"


def test_non_repo_directory_keeps_basename(tmp_path):
    assert project_of(str(tmp_path / "loose")) == "loose"


def test_transcript_usage_lands_in_core(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 10, "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 5, "output_tokens": 7}}}) + "\n")
    core = advance_core({}, "Stop", {"transcript_path": str(transcript)})
    assert core["context_tokens"] == 115 and core["last_output_tokens"] == 7


def test_missing_transcript_fails_open():
    core = advance_core({}, "Stop", {"transcript_path": "/nope/t.jsonl"})
    assert "context_tokens" not in core


# --------------------------------------------------------------- state home

def test_state_home_prefers_the_new_variable(tmp_path, monkeypatch):
    monkeypatch.setenv(hc_state.STATE_HOME_ENV, str(tmp_path / "new"))
    monkeypatch.setenv(hc_state.HOOK_KIT_HOME_ENV, str(tmp_path / "old"))
    assert hc_state.state_home() == tmp_path / "new"


def test_legacy_hook_kit_home_is_migrated(tmp_path, monkeypatch):
    monkeypatch.delenv(hc_state.STATE_HOME_ENV, raising=False)
    monkeypatch.delenv(hc_state.HOOK_KIT_HOME_ENV, raising=False)
    monkeypatch.setattr(hc_state.Path, "home", lambda: tmp_path)
    legacy = tmp_path / ".claude" / "hook-kit"
    legacy.mkdir(parents=True)
    (legacy / "injections.jsonl").write_text('{"fired": true}\n')
    home = hc_state.state_home()
    assert home == tmp_path / ".claude" / "memory-graph" / "state"
    assert (home / "injections.jsonl").read_text() == '{"fired": true}\n'
    assert not legacy.exists()


# ------------------------------------------------------------------- runner

class Greeter(HookExtension):
    name = "greeter"

    def on_session_start(self, ctx):
        ctx.state["greeted"] = ctx.state.get("greeted", 0) + 1
        ctx.global_state["sessions"] = ctx.global_state.get("sessions", 0) + 1
        return f"hello from {ctx.project}"


class Broken(HookExtension):
    name = "broken"

    def on_session_start(self, ctx):
        raise RuntimeError("boom")


@pytest.fixture
def fake_extensions(monkeypatch):
    monkeypatch.setattr(hookrun, "_extensions", lambda: {"greeter": Greeter, "broken": Broken})


def test_state_round_trips_through_the_caller(fake_extensions):
    first = hookrun.run({"event": "SessionStart", "payload": {"cwd": "/w/quartz"},
                         "enabled": ["greeter"]})
    assert first["output"] == "hello from quartz"
    second = hookrun.run({"event": "SessionStart", "payload": {"cwd": "/w/quartz"},
                          "core": first["core"], "state": first["state"],
                          "global": first["global"], "enabled": ["greeter"]})
    assert second["state"]["greeter"]["greeted"] == 2
    assert second["global"]["greeter"]["sessions"] == 2
    assert second["core"]["events"]["SessionStart"] == 2


def test_only_enabled_extensions_run(fake_extensions):
    reply = hookrun.run({"event": "SessionStart", "payload": {"cwd": "/w/q"}, "enabled": []})
    assert reply["output"] == "" and "greeter" not in reply["state"]


def test_broken_extension_fails_open(fake_extensions):
    reply = hookrun.run({"event": "SessionStart", "payload": {"cwd": "/w/quartz"},
                         "enabled": ["broken", "greeter"]})
    assert reply["output"] == "hello from quartz"
    assert reply["errors"] and "boom" in reply["errors"][0]
    assert "boom" in (hc_state.state_home() / "errors.log").read_text()


def test_unknown_event_is_noop(fake_extensions):
    reply = hookrun.run({"event": "NotAnEvent", "enabled": ["greeter"]})
    assert reply["output"] == "" and reply["core"] == {}


def test_session_start_creates_the_context_archive(tmp_path, monkeypatch, fake_extensions):
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "ctx"))
    hookrun.run({"event": "SessionStart", "payload": {"cwd": "/w/q"}, "enabled": []})
    assert (tmp_path / "ctx" / "archive").is_dir()


def test_main_answers_garbage_with_valid_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    hookrun.main()
    reply = json.loads(capsys.readouterr().out)
    assert reply["output"] == "" and reply["errors"]


def test_default_extensions_are_recall_and_counter():
    names = set(hookrun._extensions())
    assert {"memory-recall", "context-counter", "graph-review"} <= names
    assert hookrun.DEFAULT_ENABLED == ("memory-recall", "context-counter")


# --------------------------------------------------------------------- logs

def test_log_formats_known_and_unknown_keys():
    line = format_log_entry(json.dumps({"ts": 0, "fired": True, "top": 5.2, "nodes": ["n"],
                                        "terms": ["a", "b"], "custom": 1}))
    assert "INJECT" in line and "nodes[n]" in line and "terms(a b)" in line and "custom=1" in line
    assert format_log_entry("{not json\n") == "{not json"


def test_log_missing_file_reports_cleanly(capsys):
    print_log("nope.jsonl", 5, False)
    assert "No log at" in capsys.readouterr().out
