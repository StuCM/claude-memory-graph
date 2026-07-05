"""claude-hook-kit: an extension framework for Claude Code hooks.

Subclass HookExtension, set `name`, override the `on_*` methods you need,
and expose the class as a `claude_hook_kit` entry point. The dispatcher
(`claude-hooks dispatch <Event>`) runs every enabled extension for the
event, maintains core session state for all of them, and gives each
extension its own persisted state namespace.

Design rules (see docs/ORCHESTRATION.md in claude-memory-graph):
- hooks are dumb: extensions decide, the dispatcher only routes and persists
- fail open: an extension error is logged to stderr, never breaks the session
- milliseconds or nothing: extensions run synchronously in the prompt path
"""

from .state import StateStore, HOOK_KIT_HOME_ENV
from .extension import HookExtension, HookContext, EVENT_METHODS

__all__ = [
    "HookExtension",
    "HookContext",
    "StateStore",
    "EVENT_METHODS",
    "HOOK_KIT_HOME_ENV",
]
