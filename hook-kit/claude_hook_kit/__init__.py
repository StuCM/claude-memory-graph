"""claude-hook-kit: an extension framework for Claude Code hooks.

Subclass HookExtension, set `name`, override the `on_*` methods you need,
and expose the class as a `claude_hook_kit` entry point. The dispatcher
(`claude-hooks dispatch <Event>`, also `python -m claude_hook_kit dispatch
<Event>`) runs every enabled extension for the event, maintains core
session state for all of them, and gives each extension its own persisted
state namespace (session + global scopes).

Design rules (see docs/ORCHESTRATION.md in claude-memory-graph):
- hooks are dumb: extensions decide, the dispatcher only routes and persists
- fail open: an extension error goes to errors.log, never breaks the session
- milliseconds or nothing: extensions run synchronously in the prompt path
"""

from .state import StateStore, HOOK_KIT_HOME_ENV, state_home, append_jsonl, log_error
from .extension import HookExtension, HookContext, EVENT_METHODS
from .text import terms, terms_pos, bigrams

__all__ = [
    "HookExtension",
    "HookContext",
    "StateStore",
    "EVENT_METHODS",
    "HOOK_KIT_HOME_ENV",
    "state_home",
    "append_jsonl",
    "log_error",
    "terms",
    "terms_pos",
    "bigrams",
]
