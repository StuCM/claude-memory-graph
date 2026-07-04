"""The prompt gate — per-prompt hook checks.

- runtime.py  the engine: stdin -> Context -> run registered checks -> exit 0
- recall.py   check: ambient memory injection (scored, silent by default)
- nudge.py    check: context-file write reminder (prompt counter)

See runtime.py's docstring for the full how-it-works and debugging notes.
"""

from .runtime import CHECKS, Context, check, log_decision, main, store_dir, terms
from . import recall, nudge  # noqa: E402,F401 — importing registers their @check functions

__all__ = ["CHECKS", "Context", "check", "log_decision", "main", "store_dir", "terms"]
