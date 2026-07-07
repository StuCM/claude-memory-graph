# Context-window management — removing, not just adding

Status: **exploration, researched against platform docs 2026-07** (sources at the end).
Companion to [tasks/session-context-recall](tasks/session-context-recall.md): that task pages
relevant context *in*; this explores taking stale context *out*. Together they are a managed
window: small live context, everything else recallable.

## The constraint that shapes everything

**Hooks are strictly additive.** No Claude Code hook can rewrite, truncate, or drop
conversation history or tool results — they inject context, block, or surface stderr. So a
context-window *manager* cannot be a hook extension; it has to sit at one of three other
levels: steer the compactor, edit server-side via the API, or own the loop entirely. "Could
be a separate plugin" is right — but it is a separate *component* (a local API shim), not a
hooks.json plugin.

## Mechanism map (what exists, July 2026)

| Mechanism | Who controls it | What it removes | Usable from |
|---|---|---|---|
| **Auto-compact / `/compact`** | Claude Code, opaque | oldest tool results first, then summarises conversation | steering only: `/compact focus on X`, a `Compact Instructions` section in CLAUDE.md, PreCompact `additionalContext` |
| **API context editing** (beta `context-management-2025-06-27`) | request parameter | `clear_tool_uses_20250919`: old tool results (server-side, client history intact; `trigger`/`keep`/`clear_at_least`/`exclude_tools`); `clear_thinking_20251015`: old thinking blocks | raw API calls — **Claude Code does not expose it** |
| **Memory tool** (`memory_20250818`) | model + client handler | nothing (it *preserves* to files before clears) | raw API / SDK |
| **Agent SDK** | harness author | no message-list editing in the SDK itself; compaction is server-side | would call the raw API for context editing |
| **Local proxy** (`ANTHROPIC_BASE_URL`) | us | whatever we rewrite in `/v1/messages` — most simply, *inject the context-editing beta into stock Claude Code's requests* | any client |

## The design: clear the raw, keep the distilled

The memory system is what makes aggressive clearing *safe*. Tool results are the bulk of a
session's tokens, and they are exactly what our capture discipline already distills: a dig's
20 grep outputs become one trace entry; a decision's exploration becomes one Decision bullet.
Once the entry is written (and the Stop block ensures it is), the raw tool results are
redundant — clearing them loses nothing that matters, and
[session-context-recall](tasks/session-context-recall.md) pages the distilled form back in
when a prompt needs it.

So the division of labour:

- **The window manager removes the raw** — old tool results, old thinking — mechanically,
  by token pressure.
- **The memory system preserves the meaning** — context entries (Stop-block enforced),
  the graph (distill), scored re-injection (recall + session-context-recall).
- **The dig counter is the safety interlock**: a turn's tool results should only be cheap
  to clear if its finding was captured. Pressure-aware escalation (transcript-telemetry)
  can tighten the Stop block as clearing gets close.

## Phasing

**0 — Measure ([tasks/transcript-telemetry](tasks/transcript-telemetry.md)).** Read
`context_tokens` from the transcript tail into core state. Without this, every clearing
decision is blind; with it, the Stop block can escalate before compaction and the numbers
below stop being guesses.

**1 — Steer the native compactor (plugin-native, cheap).** Two immediate items:
- A `Compact Instructions` section (CLAUDE.md / context-protocol): *preserve un-captured
  decisions, problems, preferences; the context file at `<path>` is the durable record —
  prefer pointing at it over re-summarising what it already holds.*
- **Fix the PreCompact flush.** Our current flush message goes to plain stdout, which is
  likely a no-op for PreCompact (only `hookSpecificOutput.additionalContext` reaches the
  compactor — needs a live test). And there is no model turn before compaction, so
  "write the file NOW" arrives too late by construction: the PreCompact payload should
  instead *steer the summary* ("the summary MUST carry forward these uncaptured points…").
  The real flush point is the Stop block, which already exists.

**2 — The window-manager shim (the "separate plugin").** A local proxy on
`ANTHROPIC_BASE_URL` that injects the `context-management-2025-06-27` beta header and a
`context_management.edits` config into stock Claude Code's requests:
- `clear_tool_uses_20250919` with `keep: 3` recent tool uses, `exclude_tools` for the
  memory-graph MCP tools (recalled memories must not be cleared),
  `clear_at_least: 5000+` tokens so each clear amortises its prompt-cache miss;
- clearing is **server-side**, so tool_use/tool_result pairing and message validity are
  the API's problem, not ours — the shim only adds a header and a JSON block;
- ships as its own component in this repo (own config, own logs), off by default.

**3 — The SDK harness (endgame, separate product).** Own the loop via the Agent SDK: model
runs on a deliberately small window; the session-context-recall index is the paging table;
the memory tool persists what the model itself wants kept. Most control, most work — only
worth building if phase 2's numbers show clearing + re-injection genuinely beats
auto-compact.

## Risks

- **Losing relevant information** — the named risk, and the whole reason capture comes
  first: nothing is cleared that wasn't distillable, everything cleared is re-derivable
  (re-run the tool) or re-injectable (the entry). `exclude_tools` protects recalled
  memories; `keep` protects the working set.
- **Cache economics.** Every clear rewrites history upstream of the cache → one full-cost
  read. That is the *same* cost compaction pays; `clear_at_least` tunes the trade. Phase 0
  telemetry decides whether the shim actually saves money for our session shapes.
- **Beta churn.** Context-editing parameter names carry dates (`_20250919`); the shim must
  fail open — proxy errors or API rejection → pass the request through untouched.
- **Unverified:** whether PreCompact `additionalContext` reaches the summariser (test
  live); thinking-block signature constraints under client-side rewriting (moot if we stay
  server-side, which is the plan).

## Sources

Claude Code: hooks, context-window, settings, prompt-caching docs (code.claude.com, 2026-07).
API: context-editing (`clear_tool_uses_20250919`, `clear_thinking_20251015`, beta
`context-management-2025-06-27`), memory tool (`memory_20250818`) (platform.claude.com).
Agent SDK sessions docs: no client-side message-list editing.
