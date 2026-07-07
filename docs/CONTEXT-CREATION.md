# Context creation — the session write-ahead log

Status: **protocol exists ([hooks/context-protocol.md](../hooks/context-protocol.md)); reliability
layer not yet implemented.** One of the two creation subsystems — see
[DISTILL-CREATION.md](DISTILL-CREATION.md) for the other, and why they are deliberately split.

## Objective: completeness, not quality

Context creation and distill creation were one blurred pipeline; they are now separate subsystems
because they optimise for opposite things:

| | Context creation | Distill creation |
|---|---|---|
| Objective | **Don't lose anything** | **Don't pollute the graph** |
| Failure mode | a decision evaporates with the session | a junk node degrades every future recall |
| Bias | over-capture; churn is fine | under-promote; churn is filtered out |
| Store | append-only markdown, one file per session | the RDF graph |
| Consumer | the distiller (and any LLM picking up a handoff) | retrieval, forever |

The context file is a **write-ahead log**: cheap, narrative, tolerant of mid-session wrongness —
because distillation reads it *with hindsight* and promotes only what survived. Rules that
belong to graph *judgment* (dedup checks, promotion decisions, naming deliberation) do **not**
apply here; applying them mid-session is friction exactly when capture should be frictionless.
Graph *structure* is different: writing a graph-worthy point in graph shape is transcription
the in-session model does nearly for free — see the structured-entry format below and
[tasks/structured-context-entries](tasks/structured-context-entries.md).

## The rules for context notes

- **When to write:** at session start (frontmatter + what the user wants); then after any
  exchange where a decision was made, a problem was solved, the user corrected or stated a
  preference, an architectural choice was discussed, something non-obvious was discovered, or
  scope changed.
- **What a note looks like:** one timestamped bullet, categorised
  (`Decision:` / `Problem:` / `User preference:` / `Discovery:` / `Scope:`), with the *why*
  attached. Reference file paths instead of pasting code. Graph-worthy points additionally
  carry indented `key: value` lines mirroring the graph shape (properties, `relation:
  Model/name` links, `concepts:`) — structure is transcription, not judgment, and it is
  nearly free at write time while re-deriving it at distill time costs a whole LLM pass
  (see [tasks/structured-context-entries](tasks/structured-context-entries.md)).
- **What not to write:** routine actions, anything reconstructible from code/git, full snippets.
- **Wrongness is allowed:** record the current belief; if it reverses later, record the
  reversal too. Distill keeps the final understanding; the churn is the log doing its job.
- **Lifecycle:** max 5 active files; archive (never delete) after distillation; never archive
  undistilled files.

## The reliability problem (why orchestration exists)

The protocol currently *instructs* the model to keep the log updated ("if 3+ meaningful
exchanges have happened since your last update, you are overdue") — which is the same
instruction-decay failure retrieval had: compliance drops as the session grows, and a session
that dies uncaptured loses exactly the knowledge the whole system exists for.

The fix is the same one retrieval got: move the trigger out of the model. The orchestration
layer ([ORCHESTRATION.md](ORCHESTRATION.md)) counts prompts and checks the context file's
mtime; when activity has outrun the log, it **blocks the Stop event** with a mechanical
"write the context file now" — the model must act on it before the turn may finish. (The first
version injected the nudge alongside the user's prompt; live sessions showed it losing the
priority contest with the actual ask. A Stop block arrives when there is nothing else to do
and cannot be skipped; the cadence is keyed to observed writes, so an ignored block simply
fires again at the next stop; `stop_hook_active` ensures a block never chains into a loop
within a turn.)
Session-end and pre-compaction hooks are the backstop: flush before the context that would
have written the log disappears.
