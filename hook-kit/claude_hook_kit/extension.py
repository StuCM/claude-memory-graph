from dataclasses import dataclass, field
from functools import cached_property

from .text import terms_pos

# Claude Code hook event name -> handler method on HookExtension.
EVENT_METHODS = {
    "SessionStart": "on_session_start",
    "UserPromptSubmit": "on_user_prompt_submit",
    "PostToolUse": "on_post_tool_use",
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
      (session_id, started_at, cwd, project, prompt_count,
      significant_prompt_count, last_prompt_at, event counts) — always
      present, extensions never maintain it
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

    @property
    def tool_name(self) -> str:
        """PostToolUse only: the tool that just ran (empty otherwise)."""
        return self.payload.get("tool_name", "") or ""

    @property
    def project(self) -> str:
        """Basename of the working directory = current Project name."""
        return self.core.get("project", "") or ""

    @property
    def stop_hook_active(self) -> bool:
        """Stop only: true when the model is already continuing because a
        stop hook blocked this same stop — returning output again would loop."""
        return bool(self.payload.get("stop_hook_active"))

    @cached_property
    def terms_pos(self) -> list[tuple[int, str]]:
        """[(position, word)] for the prompt — tokenized LAZILY on first
        access: an extension that never touches it costs nothing; extensions
        that do all share one tokenization."""
        return terms_pos(self.prompt)

    @property
    def terms(self) -> list[str]:
        return [w for _, w in self.terms_pos]


class HookExtension:
    """Base class for hook extensions.

    Subclass, set `name` (stable identifier used for enable/disable and
    state namespacing), and override the on_* methods you need. Return a
    string to inject it into the session context (SessionStart /
    UserPromptSubmit), or None to stay silent — silence is the default
    and the norm. On Stop, a returned string BLOCKS the stop: the
    dispatcher emits it as {"decision": "block", "reason": <string>}, so
    the model must act on it before it can finish the turn.

    Set `enabled_by_default = True` for extensions that should run as soon
    as their package is installed; the user's explicit enable/disable
    choices (config.json) always win once made.
    """

    name: str = ""
    enabled_by_default: bool = False

    def on_session_start(self, ctx: HookContext) -> str | None:
        return None

    def on_user_prompt_submit(self, ctx: HookContext) -> str | None:
        return None

    def on_post_tool_use(self, ctx: HookContext) -> str | None:
        return None

    def on_stop(self, ctx: HookContext) -> str | None:
        return None

    def on_pre_compact(self, ctx: HookContext) -> str | None:
        return None

    def on_session_end(self, ctx: HookContext) -> str | None:
        return None
