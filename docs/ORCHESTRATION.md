# Orchestration — the reliability layer

Status: **v0 implemented as [hook-kit](../hook-kit/)** — a standalone, zero-dependency package
(`claude-hook-kit`, own plugin, memory-graph depends on it). It provides the `HookExtension`
base class, the dispatcher CLI (`claude-hooks dispatch <Event>`, wired into hooks.json),
framework-maintained **core session state** (session id, cwd/project, prompt count, event
counts, timestamps) plus per-extension namespaced state (session and global scopes), and
enable/disable via `claude-hooks enable <name>` (surfaced as the `/hook-kit:install` skill).
Extensions are discovered from any installed package via `claude_hook_kit` entry points and
run out of the box when marked `enabled_by_default`; explicit enable/disable always wins.
Memory-graph's prompt gate (`claude_memory_graph/gate/`) now consists of two such extensions:
`memory-recall` (scored per-prompt ambient injection — IDF, phrase and coverage evidence,
project-proximity prior — plus session-start auto-prime) and `context-counter`
(significant-prompt cadence with write-detection reset, enforced by **blocking the Stop
event** when the log is overdue; PreCompact/SessionEnd flush, distill suggestion). Gate tuning stays in `~/.claude/memory-graph/gate.json`; state, the
injection log, and error logs live in the hook-kit home (`~/.claude/hook-kit`). Observability — every log field, the miss report, and how to act on each verdict — is
documented in [TUNING.md](TUNING.md). The design below remains the reference for behaviour. The third subsystem: retrieval decides *what*,
creation decides *what's worth keeping* — orchestration makes both happen **reliably**, by
hooking into the client, counting prompts, and firing the right action at the right moment
without depending on the model remembering to.

## Why it's a separate subsystem

Both other subsystems have already hit the same failure: instructions injected at session start
decay as context grows. Retrieval's answer was the ambient analyzer; context creation's answer
is mechanical nudges. Both answers need the same machinery — hook adapters, a per-session state
file, prompt counting — so that machinery is one subsystem, not two implementations.

## Hook points (Claude Code adapter)

| Hook | Fires | Orchestration uses it for |
|---|---|---|
| `SessionStart` | session begins | prime: recall Project (cwd) + Person, inject results; init session state; inject the context-protocol (as today) |
| `UserPromptSubmit` | every user prompt | increment prompt count; run the retrieval analyzer (inject memories) |
| `Stop` | model finishes a turn | check context-log freshness; when overdue, **block the stop** (`{"decision": "block"}`) with "write the context file now" — the model must act before it may finish. `stop_hook_active` guards the follow-up stop, so a block never chains |
| `PreCompact` | context about to be summarised | **flush point**: inject "update the context file NOW" — last chance before the session's memory of itself degrades |
| `SessionEnd` | session closes | if undistilled files ≥ threshold, surface "run /memory-graph:distill"; final state save |

Other MCP clients get the same behaviours through their own thin adapters; everything below the
hook surface (state, counting, analyzer, thresholds) is client-agnostic.

## Session state

A small JSON file per session (`~/.claude/memory-graph/sessions/<session-id>.json`):

- `promptCount` — total prompts this session
- `lastContextWrite` — mtime of the session's context file when last checked
- `promptsSinceContextWrite` — the staleness counter driving nudges
- `injectedNodes` — the retrieval analyzer's per-session memo (no re-injection)
- `injectionLog` — appended decisions (fired/silent, scores, nodes) for threshold tuning

State lives outside the graph deliberately: it's operational, per-session, and disposable —
never memory.

## The two reliability loops

**Injection loop (retrieval):** every prompt → analyzer runs (lexical ground → score →
threshold) → inject memories or stay silent → memo + log updated. Deterministic cadence: the
analyzer runs on *every* prompt; whether it *speaks* is the scored decision. Counting prompts is
what makes "silence" meaningful data rather than a gap.

**Capture loop (context creation):** every prompt advances the significant count; at every
`Stop`, when the context file's mtime shows no write for N significant prompts, the hook
**blocks the stop** with a one-line mechanical reason: *"context-log: N exchanges since last
update — append key points now."* The block lands at the one moment it can't be deprioritised:
the turn's work is done, and the model must satisfy the reason before it may finish. (v0
injected the nudge at `UserPromptSubmit`; live sessions showed the model treating it as lower
priority than the user's actual ask and skipping it — the injection channel is advisory, the
Stop channel is not.) `PreCompact` and `SessionEnd` are the backstops: flush before the
in-context knowledge that would write the log is summarised away or lost.

Distill triggering closes the loop: undistilled-file count ≥ 3 (checked at `SessionStart` and
`SessionEnd`) → surface the suggestion. Distill itself stays a human-invoked skill — promotion
to the graph is a quality gate, and quality gates deserve a human in the loop until the rules
in [DISTILL-CREATION.md](DISTILL-CREATION.md) have earned trust.

## Design rules

- **Hooks are dumb; decisions are scored.** A hook never contains policy — it calls the
  analyzer/counter and relays the answer. Policy (thresholds, N, budgets) lives in one config
  the state file references, tunable without touching hook scripts.
- **Milliseconds or nothing.** Every per-prompt action shares the analyzer's latency budget; a
  slow check gets dropped, not awaited.
- **Fail open.** If the state file is missing/corrupt or the store is unreachable, hooks do
  nothing — the session must never degrade because the memory layer hiccuped.
- **Count, don't guess.** Nudge/distill thresholds key on counted prompts and file mtimes —
  observable facts — not on the model's sense of time.

## Phasing

1. Session state file + prompt counting + `SessionStart` priming (retrieval phase 1 rides on
   this).
2. Context-freshness nudges + `PreCompact`/`SessionEnd` flush + distill-threshold surfacing.
3. Injection log feeds threshold tuning; nudge cadence tuned from real sessions.
