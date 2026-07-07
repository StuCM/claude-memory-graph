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

Two lessons from live sessions are baked into the block itself:
- **Self-contained reasons.** The block fires deep into sessions where
  the session-start protocol has decayed or been compacted away — so the
  reason names the exact file path and carries the entry format inline,
  never "per the context protocol".
- **The hook stamps the file.** When no context file exists for the
  project, the hook creates it (frontmatter + Key Points header) before
  blocking: the artifact exists for other sessions to see even if the
  model never complies, and the block points at a concrete path. The
  stamp's own mtime is recorded so it is not mistaken for a model write —
  the cadence stays overdue until the model actually appends.

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
from datetime import datetime
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

    def _latest_file(self, project: str) -> Path | None:
        files = list(_context_dir().glob(f"{project}__*.md"))
        if not files:
            return None
        return max(files, key=lambda f: f.stat().st_mtime)

    def _stamp_file(self, ctx: HookContext) -> Path:
        """Create the session's context file mechanically — the escalation the
        original task predicted: if the model isn't writing the log, at least
        the artifact exists, sessions can see it, and the block can point at a
        concrete path. Records the stamped mtime so our own write is not read
        as a model write (written_at stays put; the cadence stays overdue)."""
        directory = _context_dir()
        directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        path = directory / f"{ctx.project}__{now.strftime('%Y-%m-%d_%H-%M')}.md"
        if not path.exists():
            path.write_text(
                f"---\ncreated: {now.strftime('%Y-%m-%dT%H:%M')}\n"
                f"distilled: false\nsummary: \"\"\n---\n\n## Key Points\n\n",
                encoding="utf-8",
            )
        ctx.state["last_mtime"] = path.stat().st_mtime
        return path

    # The block must be SELF-CONTAINED: it fires deep into sessions where the
    # session-start protocol has decayed or been compacted away, so it names
    # the exact file and carries the entry format inline — never "per the
    # context protocol".
    _FORMAT_HINT = (
        "One '- [HH:MM] Type: point' bullet per key point (Decision / Problem / "
        "User preference / Discovery / Scope); attach the why. Graph-worthy points "
        "add indented 'key: value' lines (rationale/description, links as "
        "'relation: Model/name', concepts:, aliases:). Skip routine actions and "
        "anything derivable from code or git."
    )

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

        latest = self._latest_file(ctx.project)
        if latest is not None:
            mtime = latest.stat().st_mtime
            if mtime != state.get("last_mtime"):
                # The log was written since we last looked — reset the cadence
                # (and trust the dig turn's write to have carried its finding).
                state["last_mtime"] = mtime
                state["written_at"] = significant
                return None

        overdue = significant - state.get("written_at", 0)
        dig = self._dig_count(ctx)
        cadence_due = overdue >= config()["N_TURNS"]
        dig_due = dig >= config()["DIG_THRESHOLD"]
        if not (cadence_due or dig_due):
            return None

        path = latest if latest is not None else self._stamp_file(ctx)
        reasons = []
        if cadence_due:
            reasons.append(
                f"[context] {overdue} significant exchanges are uncaptured. Before "
                f"finishing this turn, append the key points from the conversation "
                f"since your last entry to {path}. {self._FORMAT_HINT}")
        if dig_due:
            reasons.append(
                f"[context] this turn took {dig} file-inspection calls to answer "
                f"— an investigation worth keeping. Before finishing, record the "
                f"finding in {path} as a structured trace entry: a Pattern bullet "
                "with kind: trace, the path/flow (file paths and symbols) in the "
                "description, the question phrasings as aliases, and an anchorPath "
                "— so memory can short-circuit the next dig.")
        return "\n\n".join(reasons)

    def on_pre_compact(self, ctx: HookContext) -> str | None:
        path = self._latest_file(ctx.project) or self._stamp_file(ctx)
        return (f"[context] compaction imminent — write ALL un-captured key points to "
                f"{path} NOW, before this conversation's detail is summarised away. "
                f"{self._FORMAT_HINT}")

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
