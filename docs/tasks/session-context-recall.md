# Task: session-context recall — index the log, inject only what the prompt needs

Status: **planned (design)** · Owner: Stuart · Created: 2026-07-07 · Size: M
Depends: [[structured-context-entries]] (the entry parser is the indexer).

## The idea (2026-07-07)

The context file is currently write-only during a session: the model appends, distill
reads later, and nothing reads it back *while the session runs*. Meanwhile the gate
already owns exactly the machinery this needs — a no-LLM lexical scorer, per-prompt
triggering, thresholds, a session memo, an injection log. Point that machinery at the
context entries themselves: index the session log in state, score entries against each
prompt, and inject only the relevant ones. Context stays small; recovery of a relevant
earlier point costs a few lines, not a re-read or a re-derivation.

## What this actually buys (and what it can't)

**Deliberate limit first: hooks add context; they cannot remove it.** The harness owns
the window and the transcript — a hook-based system cannot run the session on a small
managed window (that is an agent-architecture decision: external memory with a
harness-controlled window, à la MemGPT). What we control is what gets *added* and when.
The savings are real but indirect:

1. **Closes the undistilled-recall hole.** The gate only reads the graph, so knowledge
   captured in context files this week but not yet distilled is unrecallable — the
   freshest memories are the least visible. Indexing undistilled entries makes the log
   recallable the moment it is written.
2. **Post-compaction recovery.** Compaction summarises away the detail; today the model
   re-derives it (a dig: thousands of tool-result tokens) or re-reads the whole file.
   Scored re-injection returns the two relevant entries for the current prompt instead.
3. **Cheap handoffs.** Picking up another session's work today means reading its whole
   context file into the window. With entry-level injection, a handoff costs only the
   entries the current prompt actually touches.
4. **Avoided digs.** A trace entry recalled at prompt time pre-empts the grep session
   that would have re-derived it — the dig counter's savings, brought forward.

## Design — corpus, eligibility, trigger

**Corpus.** Parse entries from active (undistilled) context files for the current
project — the [[structured-context-entries]] parser is the indexer; narrative bullets
join as plain text docs. Each entry becomes a scoring doc (`terms`, `name_terms` from
the head line, `bigrams`) exactly like a graph node. Corpus size is dozens of entries —
scan cost is noise next to the existing graph scan.

**Eligibility — the duplication rule.** An entry is only injectable when its authoring
context is *gone*:
- entries from **other sessions' files**: always eligible (that's the handoff case);
- entries from **this session's file**: eligible only after a compaction
  (`core.events["PreCompact"] > 0` — already counted by hook-kit). Before compaction the
  model still has the conversation that produced the entry; injecting it back is pure
  duplication.

**Trigger.** Same `UserPromptSubmit` gate, same thresholds (ABS_MIN/MARGIN/TOP_N budget
shared with graph injection so total injection stays bounded), same session memo so an
entry injects once. Score session entries alongside graph docs; when both fire, graph
nodes win ties (vetted beats unvetted). Injected entries are labelled for what they are:

```
Session log (undistilled — verify before acting):
- [2026-07-06 14:32] Decision: Use pyoxigraph over rdflib — rationale: …  (from claude-memory-graph__2026-07-06_19-01.md)
```

**State, not graph.** The entry index is derived and disposable (rebuilt from files on
demand, cached in the hook-kit state home keyed by file mtimes) — indexes never live in
the graph. The files remain the source of truth; distill's lifecycle is untouched, and
a distilled/archived file simply leaves the corpus.

## The loss-of-information risk (named in the idea) — why it stays bounded

- **Additive only.** Nothing is removed from the window; a scoring miss means the status
  quo (the model can still read the file — every injection carries the file path).
- **Fail toward silence** inherits the gate's bias: a wrong injection costs trust and
  tokens; a miss costs nothing new.
- **The miss detector extends for free:** a model that explicitly Reads a context file
  right after the session-corpus scorer stayed silent is a logged false negative — same
  join as `claude-memory-graph misses`, new source.

## Implementation sketch

1. `gate/session_corpus.py`: `entries(project) -> list[doc]` — parse + cache by mtime;
   eligibility filter takes (session_file, precompact_count).
2. `RecallExtension.on_user_prompt_submit`: extend the candidate pool with session docs
   (flagged `source: "log"`), shared scoring, labelled injection section.
3. Config: `LOG_ABS_MIN` (default = ABS_MIN; tune separately if unvetted entries need a
   higher bar), everything else shared.
4. Tests: eligibility (own-session pre/post compaction, other-session), scoring parity,
   memo, label + path in injection, mtime cache invalidation, distilled files drop out.

## Open questions

- **Does the log need its own threshold?** Start shared; the injection log will say —
  false positives from unvetted entries argue for a higher `LOG_ABS_MIN`.
- **Transcript as corpus?** Indexing the raw transcript (not just the curated log) would
  catch uncaptured detail — but it is exactly the unvetted, high-volume corpus the
  capture rubric exists to filter. The log is the curated view; index the log, and let
  the Stop block keep the log honest. Revisit only if miss data shows the log too thin.
- **Small-window mode?** True managed-context operation (model runs lean, harness pages
  context in) is an Agent SDK build, not a hook: the harness would own compaction and
  this index would be its paging table. This task keeps that door open — same index,
  different consumer.
