"""Session-state helpers for the hook extensions, and the state home.

The session state itself now lives in the plugin's mod (hooks/register.js):
it passes `core` and each extension's dict in with every call and stores
what comes back. What stays here is what Python owns — advancing `core`
from a hook payload, and the append-only logs every report reads.

State home: MEMORY_GRAPH_STATE, else the legacy CLAUDE_HOOK_KIT_HOME, else
~/.claude/memory-graph/state. A ~/.claude/hook-kit folder from before
hook-kit was retired is renamed into place on first use, so the tuning logs
(injections.jsonl, explicit-recalls.jsonl, capture.jsonl) carry over.

All writes fail open: logging must never break a hook.
"""

import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .text import terms, user_text

STATE_HOME_ENV = "MEMORY_GRAPH_STATE"
# Kept so existing setups and tests that set it keep working.
HOOK_KIT_HOME_ENV = "CLAUDE_HOOK_KIT_HOME"


def state_home() -> Path:
    for name in (STATE_HOME_ENV, HOOK_KIT_HOME_ENV):
        env = os.environ.get(name)
        if env:
            return Path(env)
    home = Path.home() / ".claude" / "memory-graph" / "state"
    legacy = Path.home() / ".claude" / "hook-kit"
    if not home.exists() and legacy.is_dir():
        try:
            home.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(home)
        except OSError:
            return legacy
    return home


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def project_of(cwd: str) -> str:
    """The session's project name — the identity everything keys on
    (priming, proximity, context-file grouping). Resolution order:

    1. MEMORY_GRAPH_PROJECT (or the legacy CLAUDE_HOOK_KIT_PROJECT) —
       explicit override (monorepos, or a repo cloned under a different
       directory name than its Project node);
    2. the git repo ROOT's basename — a session started in a subdirectory
       (~/dev/charcoal/frontend) still belongs to 'charcoal';
    3. the cwd basename — non-repo directories keep today's behaviour.
    """
    override = os.environ.get("MEMORY_GRAPH_PROJECT") or os.environ.get("CLAUDE_HOOK_KIT_PROJECT")
    if override:
        return override
    path = Path(cwd)
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():  # dir in a checkout, file in a worktree
            return candidate.name
    return path.name


def _transcript_usage(path_str: str) -> dict | None:
    """Token usage from the transcript's most recent assistant message —
    the tail only (last 64KB), so per-dispatch cost stays in milliseconds.
    context_tokens = the model's current context size (input + cache reads
    + cache writes of the last turn). Fail open: absent/garbled -> None."""
    if not path_str:
        return None
    try:
        with open(path_str, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536))
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        usage = (entry.get("message") or {}).get("usage") if isinstance(entry, dict) else None
        if entry.get("type") == "assistant" and isinstance(usage, dict):
            context = (usage.get("input_tokens", 0)
                       + usage.get("cache_read_input_tokens", 0)
                       + usage.get("cache_creation_input_tokens", 0))
            return {"context_tokens": context,
                    "last_output_tokens": usage.get("output_tokens", 0)}
    return None


def advance_core(core: dict, event: str, payload: dict) -> dict:
    """Advance the session's core state for one hook event, in place, and
    return it. The mod holds `core` between calls; this is the one place it
    is computed, so every extension reads the same counters.

    - project: git-root identity (project_of), refreshed every event
    - prompt_count / significant_prompt_count: a prompt is significant when
      real terms survive stopwording — bare "thanks"/"ok" don't advance the
      cadence the nudges key off
    - context_tokens / last_output_tokens: read from the transcript's tail
      (derive, don't duplicate); absent or garbled leaves the last value
    """
    core.setdefault("session_id", payload.get("session_id", "") or "default")
    core.setdefault("started_at", _now())
    cwd = payload.get("cwd") or os.getcwd()
    core["cwd"] = cwd
    core["project"] = project_of(cwd)
    core.setdefault("prompt_count", 0)
    core.setdefault("significant_prompt_count", 0)
    core.setdefault("events", {})
    core["events"][event] = core["events"].get(event, 0) + 1
    if event == "UserPromptSubmit":
        core["prompt_count"] += 1
        if terms(user_text(payload.get("prompt", "") or "")):
            core["significant_prompt_count"] += 1
        core["last_prompt_at"] = _now()
    usage = _transcript_usage(payload.get("transcript_path", "") or "")
    if usage:
        core.update(usage)
    core["updated_at"] = _now()
    return core


# ---------------------------------------------------------------------------
# Append-only logs in the state home — shared by the dispatcher and extensions
# ---------------------------------------------------------------------------

def append_jsonl(filename: str, entry: dict) -> None:
    """Append one timestamped line to <state-home>/<filename> — e.g. the
    recall extension's injections.jsonl threshold-tuning dataset. Best-effort:
    logging must never break a hook."""
    try:
        home = state_home()
        home.mkdir(parents=True, exist_ok=True)
        entry = {**entry, "ts": int(time.time())}
        with open(home / filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def log_error(where: str, exc: BaseException) -> None:
    """Append a traceback to <state-home>/errors.log. A crashing extension
    never reaches the session; this is where its evidence goes."""
    try:
        home = state_home()
        home.mkdir(parents=True, exist_ok=True)
        with open(home / "errors.log", "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} in {where}\n")
            f.write("".join(traceback.format_exception(exc)))
    except Exception:
        pass
