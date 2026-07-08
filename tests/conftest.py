import pytest
from claude_hook_kit import state as kit_state


@pytest.fixture(autouse=True)
def _isolated_kit_home(tmp_path_factory, monkeypatch):
    """Every test gets a throwaway hook-kit home so best-effort telemetry
    (injections.jsonl, ask-decisions.jsonl) never pollutes the real one."""
    home = tmp_path_factory.mktemp("kit-home")
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(home))
    return home
