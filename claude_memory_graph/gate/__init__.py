"""The prompt gate — memory-graph's hook-kit extensions.

- runtime.py  memory-graph's tuning config (gate.json) + store path
- recall.py   RecallExtension: ambient memory injection + session-start prime
- nudge.py    ContextCounterExtension: context-log cadence + flush points

The engine lives in claude-hook-kit (this package's dependency): its
dispatcher runs these extensions per hook event, owns core session state
(prompt/significant counts, project), and namespaces each extension's own
persisted state. Discovery is via the `claude_hook_kit` entry points in
pyproject.toml; manage with `claude-hooks enable/disable <name>` or the
/hook-kit:install skill. See runtime.py's docstring for debugging notes.
"""

from .runtime import config, store_dir
from .recall import RecallExtension
from .nudge import ContextCounterExtension

__all__ = ["config", "store_dir", "RecallExtension", "ContextCounterExtension"]
