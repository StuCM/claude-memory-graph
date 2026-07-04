"""Check: context-file write reminder (deterministic prompt counter).

The context protocol asks the model to update the session context file
"every 3+ meaningful exchanges" — and the model reliably forgets to
count. This check moves the COUNTING out of the model: it counts
significant prompts (any prompt with real terms left after stopwords;
bare "thanks"/"yes"/"ok" don't count) in the shared session state, and
every N_TURNS injects a reminder at exactly the moment it's actionable.
The WRITING stays the model's job — only it has the conversation.

N_TURNS comes from runtime.config() (~/.claude/memory-graph/gate.json).
"""

from .runtime import Context, check, config


@check
def context_nudge(ctx: Context) -> str | None:
    if not ctx.session_id or not ctx.terms:
        return None  # bare thanks/yes/ok -> don't count, don't nudge
    ctx.state["significant"] = ctx.state.get("significant", 0) + 1
    if ctx.state["significant"] - ctx.state.get("last_nudge_at", 0) >= config()["N_TURNS"]:
        ctx.state["last_nudge_at"] = ctx.state["significant"]
        return (f"[context] {ctx.state['significant']} significant exchanges since "
                "last context update — you are overdue. Append the decisions/"
                "problems/preferences since your last entry to the session context "
                "file per the context protocol, then continue.")
    return None
