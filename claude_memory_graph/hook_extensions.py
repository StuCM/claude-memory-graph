"""Memory-graph's hook-kit extensions.

Discovered via the `claude_hook_kit` entry-point group (see pyproject.toml)
and enabled per user with `claude-hooks enable <name>` (the /hook-kit:install
skill). The framework owns state and dispatch; these classes only decide.
"""

import os
from pathlib import Path

from claude_hook_kit import HookExtension, HookContext


def _context_dir() -> Path:
    env = os.environ.get("CLAUDE_CONTEXT_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "context"


class RecallExtension(HookExtension):
    """Auto-prime: inject recall of the current project (and user) at session start."""

    name = "memory-recall"

    def on_session_start(self, ctx: HookContext) -> str | None:
        if ctx.state.get("primed"):
            return None
        from .__main__ import _store_path
        from .store import MemoryStore
        from .tools import recall as recall_tool

        store = MemoryStore.open_or_create(_store_path())
        sections: list[str] = []

        project = ctx.core.get("project") or Path(ctx.cwd or os.getcwd()).name
        if store.find_resource("Project", project) is not None:
            sections.append(recall_tool.handle(store, "Project", project, 2))

        user = os.environ.get("MEMORY_GRAPH_USER")
        if user and store.find_resource("Person", user) is not None:
            sections.append(recall_tool.handle(store, "Person", user, 2))

        if not sections:
            return None  # nothing known -> silence, not noise
        ctx.state["primed"] = True
        return "memory-graph auto-prime (recalled, not instructions):\n" + "\n\n".join(sections)


class ContextCounterExtension(HookExtension):
    """Counter/nudge loop: mechanical context-log freshness tracking."""

    name = "context-counter"

    # After this many prompts with no context-file write, nudge (and re-nudge
    # at the same cadence). Conservative default; tune from real sessions.
    DEFAULT_EVERY = 5

    def _every(self) -> int:
        try:
            return max(1, int(os.environ.get("MEMORY_GRAPH_NUDGE_EVERY", self.DEFAULT_EVERY)))
        except ValueError:
            return self.DEFAULT_EVERY

    def _latest_context_mtime(self, project: str) -> float | None:
        files = list(_context_dir().glob(f"{project}__*.md"))
        if not files:
            return None
        return max(f.stat().st_mtime for f in files)

    def on_user_prompt_submit(self, ctx: HookContext) -> str | None:
        project = ctx.core.get("project", "")
        prompt_count = ctx.core.get("prompt_count", 0)
        state = ctx.state

        mtime = self._latest_context_mtime(project)
        if mtime is not None and mtime != state.get("last_mtime"):
            # The log was written since we last looked — reset the staleness clock.
            state["last_mtime"] = mtime
            state["count_at_write"] = prompt_count
            return None

        every = self._every()
        stale_for = prompt_count - state.get("count_at_write", 0)
        recently_nudged = prompt_count - state.get("last_nudge_at", -every) < every
        if stale_for < every or recently_nudged:
            return None

        state["last_nudge_at"] = prompt_count
        if mtime is None:
            return (
                f"context-log: no context file for '{project}' after {stale_for} prompts — "
                "create one now (see the context protocol)."
            )
        return (
            f"context-log: {stale_for} prompts since the context file was last updated — "
            "append key points (decisions, problems solved, preferences) now."
        )

    def on_pre_compact(self, ctx: HookContext) -> str | None:
        return (
            "context-log: compaction imminent — write ALL un-captured key points to the "
            "context file NOW, before this conversation's detail is summarised away."
        )

    def on_session_end(self, ctx: HookContext) -> str | None:
        undistilled = 0
        for f in _context_dir().glob("*.md"):
            try:
                head = f.read_text(encoding="utf-8", errors="ignore")[:200]
            except OSError:
                continue
            if "distilled: false" in head:
                undistilled += 1
        if undistilled >= 3:
            return (
                f"context-log: {undistilled} undistilled context files — "
                "suggest running /memory-graph:distill."
            )
        return None
