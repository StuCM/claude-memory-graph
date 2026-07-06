"""Extension: context-file write reminder (deterministic prompt counter).

The context protocol asks the model to update the session context file
"every 3+ meaningful exchanges" — and the model reliably forgets to
count. This extension moves the COUNTING out of the model: the framework
counts significant prompts (any prompt with real terms left after
stopwords; bare "thanks"/"yes"/"ok" don't count) in core session state.
The WRITING stays the model's job — only it has the conversation.

The reminder fires on Stop, not UserPromptSubmit. Injecting alongside the
user's prompt proved unreliable: the nudge competes with the actual ask
and the model deprioritises it. A Stop block can't be deprioritised — the
turn's work is done, and the model must satisfy the reason before it may
finish.

The cadence is keyed to WRITES, not to our own nagging: the baseline is
the significant count at the last observed context-file write (mtime
change), and every Stop while the log is >= N_TURNS behind blocks again.
A block that gets ignored doesn't buy the model N more quiet turns — the
next turn's Stop blocks too, until a write is observed. stop_hook_active
bounds it within a turn (one block per stop, never chained).

The dig detector rides the same Stop block: PostToolUse counts
file-inspection calls (Grep/Glob/Read, plus search-shaped Bash) per turn,
and a turn that crossed DIG_THRESHOLD was an investigation — knowledge a
future session would have to re-pay for. The Stop reason then asks for a
trace entry (docs/tasks/code-memory-rules.md) naming the finding, the
question phrasings as aliases, and an anchorPath. One ask per dig turn:
whether the model recorded it isn't observable the way the log's mtime
is, so the dig nag never repeats — the cadence block is the backstop.

PreCompact and SessionEnd remain flush points: last chances to capture
before the in-context knowledge that would write the log is summarised
away or lost, plus the distill suggestion when undistilled files pile up.

N_TURNS and DIG_THRESHOLD come from runtime.config()
(~/.claude/memory-graph/gate.json).
"""

import os
import re
from pathlib import Path

from claude_hook_kit import HookContext, HookExtension

from .runtime import config


def _context_dir() -> Path:
    env = os.environ.get("CLAUDE_CONTEXT_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "context"


# File-inspection tools that make up a dig. Bash counts only when the
# command itself is search/read-shaped — builds and test runs are not digs.
_DIG_TOOLS = {"Grep", "Glob", "Read"}
_DIG_BASH = re.compile(r"\b(rg|grep|find|fd|ag|cat|head|tail|tree|ls)\b")


def _is_dig_call(tool_name: str, payload: dict) -> bool:
    if tool_name in _DIG_TOOLS:
        return True
    if tool_name == "Bash":
        command = (payload.get("tool_input") or {}).get("command", "") or ""
        return bool(_DIG_BASH.search(command))
    return False


class ContextCounterExtension(HookExtension):
    """Context-log cadence: significant-prompt counting, write detection, flush points."""

    name = "context-counter"
    enabled_by_default = True

    def _latest_mtime(self, project: str) -> float | None:
        files = list(_context_dir().glob(f"{project}__*.md"))
        if not files:
            return None
        return max(f.stat().st_mtime for f in files)

    def on_post_tool_use(self, ctx: HookContext) -> str | None:
        if not _is_dig_call(ctx.tool_name, ctx.payload):
            return None
        turn = ctx.core.get("prompt_count", 0)
        if ctx.state.get("dig_turn") != turn:
            ctx.state["dig_turn"] = turn
            ctx.state["dig_count"] = 0
        ctx.state["dig_count"] = ctx.state.get("dig_count", 0) + 1
        return None  # counting only; the Stop hook decides whether to speak

    def _dig_count(self, ctx: HookContext) -> int:
        if ctx.state.get("dig_turn") != ctx.core.get("prompt_count", 0):
            return 0  # counter belongs to an earlier turn
        return ctx.state.get("dig_count", 0)

    def on_stop(self, ctx: HookContext) -> str | None:
        if ctx.stop_hook_active:
            return None  # this stop already follows our block — let it through
        state = ctx.state
        significant = ctx.core.get("significant_prompt_count", 0)

        mtime = self._latest_mtime(ctx.project)
        if mtime is not None and mtime != state.get("last_mtime"):
            # The log was written since we last looked — reset the cadence
            # (and trust the dig turn's write to have carried its finding).
            state["last_mtime"] = mtime
            state["written_at"] = significant
            return None

        reasons = []
        overdue = significant - state.get("written_at", 0)
        if overdue >= config()["N_TURNS"]:
            reasons.append(
                f"[context] {overdue} significant exchanges since the context "
                "file was last updated. Before finishing this turn, append the "
                "decisions/problems/preferences from the conversation since your "
                "last entry to the session context file per the context protocol.")
        dig = self._dig_count(ctx)
        if dig >= config()["DIG_THRESHOLD"]:
            reasons.append(
                f"[context] this turn took {dig} file-inspection calls to answer "
                "— an investigation worth keeping. Before finishing, record the "
                "finding as a structured trace entry in the session context file: "
                "a Pattern with kind: trace, the path/flow (file paths and symbols) "
                "in the description, the question phrasings as aliases, and an "
                "anchorPath — so memory can short-circuit the next dig.")
        return "\n\n".join(reasons) if reasons else None

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
