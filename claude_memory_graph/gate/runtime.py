"""Memory-graph gate configuration.

The engine that used to live here (stdin → Context → checks → exit 0) is
now claude-hook-kit's dispatcher — a standalone framework this package
depends on. What remains is memory-graph's own tuning surface and paths;
the checks themselves are HookExtension subclasses in recall.py / nudge.py,
discovered via the `claude_hook_kit` entry points in pyproject.toml and
managed with `claude-hooks enable/disable` (the /hook-kit:install skill).
Both are enabled_by_default: installing memory-graph gives a working gate
with zero setup, and an explicit enable/disable overrides that.

Debugging
---------
- extension errors: <hook-kit home>/errors.log (default ~/.claude/hook-kit)
- recall decisions (fired or silent, with scores): <hook-kit home>/injections.jsonl
- session state (core counters + per-extension namespaces):
      claude-hooks state <session_id>
- run the gate by hand:
      echo '{"prompt":"why pyoxigraph?","session_id":"debug"}' \\
          | claude-hooks dispatch UserPromptSubmit
"""

import json
import os
from pathlib import Path


def store_dir() -> Path:
    # duplicated from __main__._store_path: importing __main__ would pull in mcp
    env = os.environ.get("MEMORY_GRAPH_PATH")
    return Path(env) if env else Path.home() / ".claude" / "memory-graph" / "store"


# ================================================================
# Tuning config — one file for every knob
# ================================================================

_DEFAULTS = {
    "ABS_MIN": 3.0,     # recall: absolute score floor
    "MARGIN": 1.5,      # recall: group must beat the rest by this; members stay within it of top
    "TOP_N": 2,         # recall: max memories per injection
    "PROX_BOOST": 1.5,  # recall: multiplier for current project's node + 1-hop neighbours
    "PHRASE_GAP": 2,    # recall: max original-token distance for a bigram (2 = one word between)
    "N_TURNS": 3,       # nudge: remind every N significant prompts
    "DIG_THRESHOLD": 8, # nudge: file-inspection calls in one turn that make it a dig
    "LOG_ABS_MIN": 3.0, # session-log recall: score floor for undistilled entries
    "PRESSURE_TOKENS": 140000,  # nudge: context size that escalates the flush
}
_CONFIG_PATH = Path.home() / ".claude" / "memory-graph" / "gate.json"
_config: dict | None = None


def config() -> dict:
    """Tuning values: _DEFAULTS overlaid with ~/.claude/memory-graph/gate.json
    (if present). Edit that file to tune — no code changes, next prompt picks
    it up. Example: {"ABS_MIN": 4.0, "N_TURNS": 5}"""
    global _config
    if _config is None:
        cfg = dict(_DEFAULTS)
        try:
            cfg.update(json.loads(_CONFIG_PATH.read_text()))
        except Exception:
            pass  # no file / bad JSON -> defaults
        _config = cfg
    return _config
