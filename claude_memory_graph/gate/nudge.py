"""Extension: context-file write reminder (deterministic prompt counter).

The context protocol asks the model to update the session context file
"every 3+ meaningful exchanges" — and the model reliably forgets to
count. This extension moves the COUNTING out of the model: the framework
counts significant prompts (any prompt with real terms left after
stopwords; bare "thanks"/"yes"/"ok" don't count) in core session state,
and every N_TURNS this extension injects a reminder at exactly the moment
it's actionable. The WRITING stays the model's job — only it has the
conversation.

Two refinements over pure counting:
- an observed context-file write (mtime change) resets the cadence — a
  model that just updated the log isn't overdue;
- PreCompact and SessionEnd are flush points: last chances to capture
  before the in-context knowledge that would write the log is summarised
  away or lost, plus the distill suggestion when undistilled files pile up.

N_TURNS comes from runtime.config() (~/.claude/memory-graph/gate.json).
"""

import os
from pathlib import Path

from claude_hook_kit import HookContext, HookExtension

from .runtime import config


def _context_dir() -> Path:
    env = os.environ.get("CLAUDE_CONTEXT_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "context"


class ContextCounterExtension(HookExtension):
    """Context-log cadence: significant-prompt counting, write detection, flush points."""

    name = "context-counter"
    enabled_by_default = True

    def _latest_mtime(self, project: str) -> float | None:
        files = list(_context_dir().glob(f"{project}__*.md"))
        if not files:
            return None
        return max(f.stat().st_mtime for f in files)

    def on_user_prompt_submit(self, ctx: HookContext) -> str | None:
        if not ctx.terms_pos:
            return None  # bare thanks/yes/ok -> don't nudge
        state = ctx.state
        significant = ctx.core.get("significant_prompt_count", 0)

        mtime = self._latest_mtime(ctx.project)
        if mtime is not None and mtime != state.get("last_mtime"):
            # The log was written since we last looked — reset the cadence.
            state["last_mtime"] = mtime
            state["written_at"] = significant
            return None

        baseline = max(state.get("last_nudge_at", 0), state.get("written_at", 0))
        overdue = significant - baseline
        if overdue < config()["N_TURNS"]:
            return None
        state["last_nudge_at"] = significant
        return (f"[context] {overdue} significant exchanges since "
                "last context update — you are overdue. Append the decisions/"
                "problems/preferences since your last entry to the session context "
                "file per the context protocol, then continue.")

    def on_pre_compact(self, ctx: HookContext) -> str | None:
        return ("[context] compaction imminent — write ALL un-captured key points to the "
                "context file NOW, before this conversation's detail is summarised away.")

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
            return (f"[context] {undistilled} undistilled context files — "
                    "suggest running /memory-graph:distill.")
        return None
