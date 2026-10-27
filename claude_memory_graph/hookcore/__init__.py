"""What the hook extensions share: the per-event context, the state home and
its logs, and the prompt tokenizer. Formerly the standalone claude-hook-kit
package; its dispatcher and extension registry were retired when the
plugin's mod took over routing and session state (see hooks/register.js and
claude_memory_graph/hookrun.py)."""

from .state import (STATE_HOME_ENV, HOOK_KIT_HOME_ENV, advance_core, append_jsonl,
                    log_error, project_of, state_home)
from .extension import HookExtension, HookContext, EVENT_METHODS
from .text import terms, terms_pos, bigrams, user_text

__all__ = [
    "HookExtension", "HookContext", "EVENT_METHODS",
    "STATE_HOME_ENV", "HOOK_KIT_HOME_ENV", "state_home", "advance_core",
    "append_jsonl", "log_error", "project_of",
    "terms", "terms_pos", "bigrams", "user_text",
]
