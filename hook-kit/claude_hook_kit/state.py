"""Session state for hook extensions.

Layout under the state home (default ~/.claude/hook-kit, override with
CLAUDE_HOOK_KIT_HOME):

    config.json                  enabled-extension list
    global.json                  cross-session extension state, namespaced
    sessions/<session_id>.json   per-session state:
        core          framework-maintained (never written by extensions)
        extensions    one namespace per extension name

All writes are atomic (tmp + rename). All reads fail open: a missing or
corrupt file is an empty state, never an error — the session must not
degrade because the memory layer hiccuped.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

HOOK_KIT_HOME_ENV = "CLAUDE_HOOK_KIT_HOME"


def state_home() -> Path:
    env = os.environ.get(HOOK_KIT_HOME_ENV)
    if env:
        return Path(env)
    return Path.home() / ".claude" / "hook-kit"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    tmp.replace(path)


class StateStore:
    """Per-session state plus a global scope, namespaced per extension."""

    def __init__(self, session_id: str, home: Path | None = None):
        self.home = home or state_home()
        self.session_id = session_id or "default"
        self._session_path = self.home / "sessions" / f"{self.session_id}.json"
        self._global_path = self.home / "global.json"
        self._session = _read_json(self._session_path)
        self._global = _read_json(self._global_path)
        self._session.setdefault("core", {})
        self._session.setdefault("extensions", {})
        self._global.setdefault("extensions", {})

    # -- core state: maintained by the dispatcher, read by extensions --------

    @property
    def core(self) -> dict:
        return self._session["core"]

    def touch_core(self, event: str, payload: dict) -> None:
        """Advance framework-maintained state for this event. The one place
        core state is written; extensions get it read-only by convention."""
        core = self.core
        core.setdefault("session_id", self.session_id)
        core.setdefault("started_at", _now())
        cwd = payload.get("cwd") or os.getcwd()
        core["cwd"] = cwd
        core["project"] = Path(cwd).name
        core.setdefault("prompt_count", 0)
        core.setdefault("events", {})
        core["events"][event] = core["events"].get(event, 0) + 1
        if event == "UserPromptSubmit":
            core["prompt_count"] += 1
            core["last_prompt_at"] = _now()
        core["updated_at"] = _now()

    # -- extension state ------------------------------------------------------

    def extension(self, name: str) -> dict:
        return self._session["extensions"].setdefault(name, {})

    def global_extension(self, name: str) -> dict:
        return self._global["extensions"].setdefault(name, {})

    # -- persistence -----------------------------------------------------------

    def save(self) -> None:
        _write_json(self._session_path, self._session)
        _write_json(self._global_path, self._global)
