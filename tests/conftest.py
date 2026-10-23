import pytest
from claude_hook_kit import state as kit_state


@pytest.fixture(autouse=True)
def _isolated_kit_home(tmp_path_factory, monkeypatch):
    """Every test gets a throwaway hook-kit home so best-effort telemetry
    (injections.jsonl, ask-decisions.jsonl) never pollutes the real one."""
    home = tmp_path_factory.mktemp("kit-home")
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(home))
    return home


@pytest.fixture(autouse=True)
def _no_shared_server(monkeypatch):
    """Port 9 refuses at once, so no test reaches a real server on 8848."""
    monkeypatch.setenv("MEMORY_GRAPH_URL", "http://127.0.0.1:9")
