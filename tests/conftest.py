import pytest
from claude_memory_graph.hookcore import state as kit_state


@pytest.fixture(autouse=True)
def _isolated_kit_home(tmp_path_factory, monkeypatch):
    """Every test gets a throwaway state home so best-effort telemetry
    (injections.jsonl, ask-decisions.jsonl) never pollutes the real one."""
    home = tmp_path_factory.mktemp("kit-home")
    monkeypatch.setenv(kit_state.STATE_HOME_ENV, str(home))
    return home
