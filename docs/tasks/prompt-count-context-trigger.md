# Task: deterministic context-write trigger (prompt counter)

Status: **done — escalated to a Stop block (2026-07-06)** · Owner: Stuart · Created: 2026-07-02
Counting still shares the `UserPromptSubmit` hook with [[prompt-gated-recall]];
the trigger itself now fires on `Stop`.

> **Escalation note (2026-07-06).** The open question below — "model may ignore the
> nudge" — happened in live sessions: injected alongside the user's prompt, the nudge
> lost the priority contest with the actual ask. The trigger moved from
> `UserPromptSubmit` injection to the `Stop` hook: when the log is overdue, the
> dispatcher emits `{"decision": "block", "reason": "write the context file now"}`,
> which the model must satisfy before the turn may finish. The cadence is keyed to
> observed writes (mtime), not to the block itself — an ignored block fires again at
> every following stop until the log is written. `stop_hook_active` guards against
> chained blocks within a turn.
>
> **Second escalation (2026-07-07).** Live sessions showed blocks the model couldn't
> act on: the reason said "per the context protocol", but by the time Stop fires the
> session-start protocol has decayed or been compacted away — the block had no
> context. The reason is now self-contained (exact file path + entry format inline),
> and the fallback below is implemented: when no context file exists, the hook stamps
> it (frontmatter + Key Points header) before blocking, recording the stamp's mtime so
> it never counts as a model write. The artifact exists for handoff even on a
> non-compliant session.
> (`ContextCounterExtension.on_stop` in gate/nudge.py; `format_response` in
> hook-kit's dispatcher.)

## Goal

Make conversation-context recording fire on a **deterministic schedule**, not on
the model remembering to. Today `context-protocol.md` asks the model to both
*count* ("append after every significant interaction… overdue at 3+") and
*write* — and it reliably forgets the counting. Move the counting into the hook;
leave the writing to the model (only it has the conversation to distill).

## Root cause / why a "singleton" is a state file

A `UserPromptSubmit` hook is a **fresh subprocess per prompt** — no in-memory
object survives between prompts. The counter must persist to disk, keyed by
`session_id` (passed in the hook's stdin JSON):

```
~/.claude/memory-graph/state/<session_id>.json
{ "significant": 7, "last_nudge_at": 6 }
```

## What's deterministic vs model's job

- **Hook (deterministic):** count *significant* prompts; when
  `significant - last_nudge_at >= N`, inject a nudge and record `last_nudge_at`.
- **Model (unchanged):** on seeing the nudge, append to the context file per
  `context-protocol.md`. The hook can't do this — it has only the current
  prompt, and the context file is a distillation of the whole conversation.

**Significance filter:** reuse `gate._terms(prompt)`; count a prompt if it yields
**any** real terms (non-empty after stopwords). Add acknowledgement words to the
gate's `_STOP` set so bare "thanks" / "yes" / "ok" reduce to empty and don't
count:

```python
_STOP |= {"thanks", "thank", "yes", "yep", "ok", "okay", "sure", "no", "nope", "please"}
```

## Skeleton (folds into the shared hook)

Add to `claude_memory_graph/gate.py` (same process as recall — one subprocess,
one stdin read):

```python
import json
from pathlib import Path
from . import gate  # _terms lives here

N_TURNS   = 3     # nudge every N significant prompts (matches protocol's "3+")
_STATE_DIR = Path.home() / ".claude/memory-graph/state"

def context_nudge(session_id: str, prompt: str) -> str | None:
    if not session_id or not gate._terms(prompt):
        return None                      # bare thanks/yes/ok -> don't count, don't nudge
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    f = _STATE_DIR / f"{session_id}.json"
    st = json.loads(f.read_text()) if f.exists() else {"significant": 0, "last_nudge_at": 0}
    st["significant"] += 1
    if st["significant"] - st["last_nudge_at"] >= N_TURNS:
        st["last_nudge_at"] = st["significant"]
        f.write_text(json.dumps(st))
        return (f"[context] {st['significant']} significant exchanges since last "
                f"context update — you are overdue. Append the decisions/problems/"
                f"preferences since your last entry to the session context file per "
                f"the context protocol, then continue.")
    f.write_text(json.dumps(st))
    return None
```

Wire it into `main()` after the recall block:

```python
    data = json.loads(raw) if raw.strip().startswith("{") else {}
    prompt = data.get("prompt", raw) or ""
    session_id = data.get("session_id", "")
    # ... recall injection (prints if confident) ...
    nudge = context_nudge(session_id, prompt)
    if nudge:
        print(nudge)
```

## Test

`tests/test_context_trigger.py` — pin the counting/threshold logic:

```python
def test_nudge_fires_on_third_significant_turn(tmp_path, monkeypatch):
    import claude_memory_graph.gate as g
    monkeypatch.setattr(g, "_STATE_DIR", tmp_path)   # or inject via arg
    sid = "sess-1"
    assert g.context_nudge(sid, "design the dc03 harness merge") is None
    assert g.context_nudge(sid, "fix the csv export path bug") is None
    assert g.context_nudge(sid, "add the print view route") is not None   # 3rd -> nudge
    assert g.context_nudge(sid, "thanks") is None                        # trivial, no count
```

## Open questions

- **N default = 3** to match the protocol's "3+ meaningful exchanges". Tunable.
- **Reset semantics:** counter resets `last_nudge_at`, not `significant`, so the
  cadence is "every N since last nudge" for the whole session. Fine — session
  files are disposable; add a SessionEnd cleanup only if the state dir grows.
- **Distill interaction:** this only triggers *context-file* writes; long-term
  graph distillation stays a separate manual/`/distill` step. Don't auto-distill
  from here.
- **Model may ignore the nudge.** It's still a soft instruction the model can
  skip. If that proves unreliable, escalate: have the hook itself stamp an empty
  dated context file so at least the artifact exists for the model to fill.
