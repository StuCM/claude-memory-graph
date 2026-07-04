"""The prompt gate — a tiny runtime for per-prompt hook checks.

How it fits together
--------------------
Claude Code runs hooks/user-prompt-submit.sh on EVERY user prompt. That
script starts this package as a fresh subprocess:

    python -m claude_memory_graph.gate

and feeds it one JSON object on stdin:

    {"prompt": "<what you typed>", "session_id": "abc123", ...}

Whatever this process prints to stdout gets injected into the model's
context for that turn; printing nothing means the model notices nothing.
The process must ALWAYS exit 0 — a broken gate must never break a session.

Structure (one job per file):
- this module   the runtime: parse stdin, load session state, run every
                registered check, save state, print outputs, exit 0
- recall.py     check: ambient memory injection (scored, silent by default)
- nudge.py      check: context-file write reminder (prompt counter)

A check is a function ``fn(ctx) -> str | None`` registered with the
``@check`` decorator. It receives a Context — the prompt text, the
session id, and a shared mutable ``state`` dict that the runtime loads
before the checks and saves after them (a hook subprocess dies after
every prompt, so anything worth remembering between prompts must go in
``state``). Return text to inject, or None to stay silent.

To add a new behaviour: create a module with one ``@check`` function and
import it in the ``# registered checks`` block at the bottom of this file.

Debugging
---------
- A crashing check never reaches the session; its traceback is appended
  to ~/.claude/memory-graph/state/errors.log and the other checks still run.
- Recall decisions (fired or silent, with scores) append to
  injections.jsonl in the same directory.
- Run the gate by hand:
      echo '{"prompt":"why pyoxigraph?","session_id":"debug"}' \\
          | python -m claude_memory_graph.gate
"""

import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

_STATE_DIR = Path.home() / ".claude" / "memory-graph" / "state"

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
    "are", "this", "that", "it", "be", "can", "could", "would", "how", "what",
    "when", "i", "you", "we", "do", "does", "make", "get", "set", "use",
    "about", "did", "was", "were", "they", "them", "our", "your", "just", "some",
    # acknowledgement words: bare "thanks"/"yes"/"ok" must reduce to no terms
    "thanks", "thank", "yes", "yep", "ok", "okay", "sure", "no", "nope", "please",
}
_WORD = re.compile(r"[a-z0-9]+")


def terms_pos(text: str) -> list[tuple[int, str]]:
    """Meaningful words with their ORIGINAL positions: (index-in-full-token-
    stream, word). Positions let phrase matching tell 'memory graph' (adjacent)
    from 'memory of the whole graph' (four words apart) even after stopwords
    are stripped out of the sequence."""
    return [(i, w) for i, w in enumerate(_WORD.findall(text.lower()))
            if len(w) > 2 and w not in _STOP]


def terms(text: str) -> list[str]:
    """Meaningful words in `text`: lowercase, no stopwords, length > 2."""
    return [w for _, w in terms_pos(text)]


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


@dataclass
class Context:
    """What every check gets: the prompt, who's asking, where they are,
    and shared memory. `terms` is computed once here so every check works
    from the same tokenization."""
    prompt: str
    session_id: str
    cwd: str = ""  # basename of the working directory = current Project name
    state: dict = field(default_factory=dict)
    terms: list = None  # [(position, word)] from terms_pos(prompt)

    def __post_init__(self):
        if self.terms is None:
            self.terms = terms_pos(self.prompt)


CHECKS: list = []


def check(fn):
    """Register `fn(ctx) -> str | None` to run on every prompt."""
    CHECKS.append(fn)
    return fn


# ================================================================
# Runtime plumbing: state file, logs
# ================================================================

def _load_state(session_id: str) -> dict:
    try:
        return json.loads((_STATE_DIR / f"{session_id}.json").read_text())
    except Exception:
        return {}


def _save_state(session_id: str, state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    (_STATE_DIR / f"{session_id}.json").write_text(json.dumps(state))


def log_decision(entry: dict) -> None:
    """Append one line to injections.jsonl — the threshold-tuning dataset."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        entry["ts"] = int(time.time())
        with open(_STATE_DIR / "injections.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _log_error(where: str, exc: Exception) -> None:
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_STATE_DIR / "errors.log", "a") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} in {where}\n")
            f.write("".join(traceback.format_exception(exc)))
    except Exception:
        pass


# ================================================================
# Entry point — always exit 0
# ================================================================

def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip().startswith("{") else {}
        ctx = Context(
            prompt=(data.get("prompt") if data else raw) or "",
            session_id=data.get("session_id", "") if data else "",
            cwd=Path(data.get("cwd", "")).name if data else "",
        )
        if ctx.session_id:
            ctx.state = _load_state(ctx.session_id)

        out = []
        for fn in CHECKS:
            try:
                result = fn(ctx)
                if result:
                    out.append(result)
            except Exception as exc:
                _log_error(fn.__name__, exc)  # this check failed; others still run

        if ctx.session_id:
            _save_state(ctx.session_id, ctx.state)
        if out:
            print("\n\n".join(out))
    except Exception as exc:
        _log_error("runtime", exc)  # fail open: never degrade the session
