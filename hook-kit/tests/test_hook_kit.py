import json

import pytest

from claude_hook_kit import HookExtension, StateStore
from claude_hook_kit.dispatch import run_dispatch
from claude_hook_kit import registry, state


@pytest.fixture(autouse=True)
def kit_home(tmp_path, monkeypatch):
    monkeypatch.setenv(state.HOOK_KIT_HOME_ENV, str(tmp_path))
    return tmp_path


# ----------------------------------------------------------------
# State store
# ----------------------------------------------------------------

def test_core_state_maintained_across_dispatches(kit_home):
    payload = {"session_id": "s1", "cwd": "/home/user/quartz"}
    run_dispatch("SessionStart", payload)
    run_dispatch("UserPromptSubmit", {**payload, "prompt": "hi"})
    run_dispatch("UserPromptSubmit", {**payload, "prompt": "again"})

    store = StateStore("s1")
    assert store.core["project"] == "quartz"
    assert store.core["prompt_count"] == 2
    assert store.core["events"]["UserPromptSubmit"] == 2
    assert store.core["events"]["SessionStart"] == 1
    assert "last_prompt_at" in store.core


def test_sessions_are_isolated(kit_home):
    run_dispatch("UserPromptSubmit", {"session_id": "a", "cwd": "/p/one"})
    run_dispatch("UserPromptSubmit", {"session_id": "b", "cwd": "/p/two"})
    assert StateStore("a").core["prompt_count"] == 1
    assert StateStore("a").core["project"] == "one"
    assert StateStore("b").core["project"] == "two"


def test_corrupt_state_fails_open(kit_home):
    path = kit_home / "sessions" / "s1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    store = StateStore("s1")
    assert store.core == {}
    store.touch_core("SessionStart", {})
    store.save()
    assert json.loads(path.read_text())["core"]["session_id"] == "s1"


def test_extension_state_namespaced_and_persisted(kit_home):
    store = StateStore("s1")
    store.extension("ext-a")["count"] = 3
    store.extension("ext-b")["count"] = 9
    store.global_extension("ext-a")["seen"] = ["x"]
    store.save()

    reloaded = StateStore("s1")
    assert reloaded.extension("ext-a") == {"count": 3}
    assert reloaded.extension("ext-b") == {"count": 9}
    assert reloaded.global_extension("ext-a") == {"seen": ["x"]}


# ----------------------------------------------------------------
# Dispatch + extensions
# ----------------------------------------------------------------

class Greeter(HookExtension):
    """Says hello on session start."""
    name = "greeter"

    def on_session_start(self, ctx):
        ctx.state["greeted"] = True
        return f"hello from {ctx.core['project']}"


class Counter(HookExtension):
    name = "counter"

    def on_user_prompt_submit(self, ctx):
        ctx.state["seen"] = ctx.state.get("seen", 0) + 1
        return None  # silent


class Broken(HookExtension):
    name = "broken"

    def on_session_start(self, ctx):
        raise RuntimeError("boom")


@pytest.fixture
def fake_extensions(monkeypatch):
    exts = {"greeter": Greeter, "counter": Counter, "broken": Broken}
    monkeypatch.setattr(registry, "discover", lambda: exts)
    return exts


def test_only_enabled_extensions_run(kit_home, fake_extensions):
    registry.set_enabled(["greeter"])
    out = run_dispatch("SessionStart", {"session_id": "s1", "cwd": "/p/quartz"})
    assert out == "hello from quartz"
    assert StateStore("s1").extension("greeter") == {"greeted": True}
    assert StateStore("s1").extension("counter") == {}


def test_silent_extension_injects_nothing(kit_home, fake_extensions):
    registry.set_enabled(["counter"])
    out = run_dispatch("UserPromptSubmit", {"session_id": "s1", "prompt": "x"})
    assert out == ""
    assert StateStore("s1").extension("counter") == {"seen": 1}


def test_broken_extension_fails_open(kit_home, fake_extensions, capsys):
    registry.set_enabled(["broken", "greeter"])
    out = run_dispatch("SessionStart", {"session_id": "s1", "cwd": "/p/quartz"})
    assert out == "hello from quartz"  # the healthy extension still ran
    assert "boom" in capsys.readouterr().err


def test_unknown_event_is_noop(kit_home, fake_extensions):
    registry.set_enabled(["greeter"])
    assert run_dispatch("NotAnEvent", {"session_id": "s1"}) == ""


# ----------------------------------------------------------------
# Registry
# ----------------------------------------------------------------

def test_enable_unknown_extension_reports(kit_home, fake_extensions):
    msg = registry.enable("nope")
    assert "Unknown extension" in msg and "greeter" in msg


def test_enable_disable_roundtrip(kit_home, fake_extensions):
    assert "Enabled" in registry.enable("greeter")
    assert "already enabled" in registry.enable("greeter")
    assert registry.enabled_names() == ["greeter"]
    assert "Disabled" in registry.disable("greeter")
    assert registry.enabled_names() == []
