"""Memory-graph gate configuration.

The engine that used to live here (stdin → Context → checks → exit 0) is
now claude-hook-kit's dispatcher — a standalone framework this package
depends on. What remains is memory-graph's own tuning surface and paths;
the checks themselves are HookExtension subclasses in recall.py / nudge.py,
discovered via the `claude_memory_graph.hookcore` entry points in pyproject.toml and
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

import contextlib
import json
import os
from pathlib import Path


# Set when the gate runs inside the memory server, on its live store.
_live_store = None
# Set (by hookrun) when the gate's lookups go to a memory server: this
# machine holds no graph, so nothing here may open one.
SERVER_LOOKUPS_ENV = "MEMORY_GRAPH_LOOKUPS"


def store_dir() -> Path:
    if _live_store is not None and getattr(_live_store, "_data_path", None):
        return _live_store._data_path.parent
    # duplicated from __main__._store_path: importing __main__ would pull in mcp
    env = os.environ.get("MEMORY_GRAPH_PATH")
    return Path(env) if env else Path.home() / ".claude" / "memory-graph" / "store"


def use_live_store(store) -> None:
    """The memory server's own store: the gate reads it instead of opening
    one from disk."""
    global _live_store
    _live_store = store


def server_lookups() -> bool:
    return os.environ.get(SERVER_LOOKUPS_ENV) == "server"


def open_store():
    """The store the gate reads: the server's live one, else the one on disk."""
    if _live_store is not None:
        return _live_store
    if server_lookups():
        raise RuntimeError("memory lookups go to the server: there is no local graph")
    from ..store import MemoryStore
    return MemoryStore.open_or_create(store_dir())


# ================================================================
# Tuning config — one file for every knob
# ================================================================

_DEFAULTS = {
    "ABS_MIN": 3.0,     # recall: absolute score floor
    "MARGIN": 1.5,      # recall: group must beat the rest by this; members stay within it of top
    "TOP_N": 2,         # recall: max memories per injection
    "CLUSTER_FACTOR": 3.0,  # recall: a group scoring >= this x ABS_MIN is a topic cluster, not noise
    "PRIME_MAX_CHARS": 3000,  # auto-prime: size budget for each session-start section
    "INJECT_STYLE": "pointer",  # recall: "pointer" = one line per memory, Claude decides; "full" = content + recall call
    "SEMANTIC": True,   # recall: when the words don't match, try the meaning (gate/semantic.py)
    "ANSWER_QUESTIONS": True,  # recall: a question in the prompt the planner fully understands is answered and injected
    "ANSWER_MAX_QUESTIONS": 2,  # ...at most this many per prompt
    "ANSWER_MAX_ROWS": 8,       # ...rows shown per answer (the rest: "+N more")
    "ANSWER_COVERAGE": 0.8,     # ...share of the question's words the planner must account for
    "SEM_MIN": 0.40,    # recall: best-field cosine a semantic match needs
    "SEM_GAP": 0.08,    # recall: ...and its lead over the runner-up (a flat field is noise)
    "PROX_BOOST": 1.5,  # recall: multiplier for current project's node + 1-hop neighbours
    "PHRASE_GAP": 2,    # recall: max original-token distance for a bigram (2 = one word between)
    "N_TURNS": 3,       # nudge: remind every N significant prompts
    "DIG_THRESHOLD": 8, # nudge: file-inspection calls in one turn that make it a dig
    "LOG_ABS_MIN": 3.0, # session-log recall: score floor for undistilled entries
    "PRESSURE_TOKENS": 140000,  # nudge: context size that escalates the flush
    "GAP_MIN": 6.0,     # gaps: IDF mass two unlinked nodes must share to suggest a link
    "DISTILL_AFTER_DAYS": 2,  # auto-distill: age at which an untouched context file is done
    "REVIEW_EVERY_DAYS": 7,   # graph-review: period between self-review asks
    "CAPTURE_SHAPE_MIN": 0.7, # graph-review: structured share of log entries to expect
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


@contextlib.contextmanager
def overridden(values: dict):
    """override() for one request in a long-lived process (the memory
    server): the settings apply inside the block, then the old ones return."""
    global _config
    saved = _config
    _config = dict(config())
    try:
        override(values or {})
        yield
    finally:
        _config = saved


def override(values: dict) -> None:
    """Settings from the plugin's settings menu, over gate.json, for this
    process (one hook call). Only known keys of the default's type are
    taken: a stray or mistyped value is ignored, never a crash."""
    cfg = config()
    for key, value in values.items():
        default = _DEFAULTS.get(key)
        if default is None:
            continue
        if isinstance(default, bool):
            if isinstance(value, bool):
                cfg[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            cfg[key] = type(default)(value)
