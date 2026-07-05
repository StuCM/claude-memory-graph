from dataclasses import dataclass, field

# Claude Code hook event name -> handler method on HookExtension.
EVENT_METHODS = {
    "SessionStart": "on_session_start",
    "UserPromptSubmit": "on_user_prompt_submit",
    "Stop": "on_stop",
    "PreCompact": "on_pre_compact",
    "SessionEnd": "on_session_end",
}


@dataclass
class HookContext:
    """Everything an extension gets per event.

    - payload: the hook input JSON Claude Code passed on stdin
      (session_id, cwd, prompt, ... — fields vary per event)
    - core: read-only view of framework-maintained session state
      (session_id, started_at, cwd, project, prompt_count, last_prompt_at,
      event counts) — always present, extensions never maintain it
    - state: this extension's own per-session dict — persisted after dispatch
    - global_state: this extension's cross-session dict — persisted after dispatch
    """

    event: str
    payload: dict
    core: dict
    state: dict
    global_state: dict = field(default_factory=dict)

    @property
    def prompt(self) -> str:
        return self.payload.get("prompt", "") or ""

    @property
    def cwd(self) -> str:
        return self.payload.get("cwd", "") or ""


class HookExtension:
    """Base class for hook extensions.

    Subclass, set `name` (stable identifier used for enable/disable and
    state namespacing), and override the on_* methods you need. Return a
    string to inject it into the session context (SessionStart /
    UserPromptSubmit), or None to stay silent — silence is the default
    and the norm.
    """

    name: str = ""

    def on_session_start(self, ctx: HookContext) -> str | None:
        return None

    def on_user_prompt_submit(self, ctx: HookContext) -> str | None:
        return None

    def on_stop(self, ctx: HookContext) -> str | None:
        return None

    def on_pre_compact(self, ctx: HookContext) -> str | None:
        return None

    def on_session_end(self, ctx: HookContext) -> str | None:
        return None
