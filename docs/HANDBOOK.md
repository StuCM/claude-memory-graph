# The operator's handbook — run, watch, debug, tune

Everything else in `docs/` explains *why* the system is shaped this way. This doc is the
*how*: what each piece is doing at runtime, where its code and logs live, the terminology
with examples, the setup steps, the tuning playbook, and how to work *with* it day to day.

CLI note: examples use `claude-memory-graph …` and `claude-hooks …` as commands. From a
repo checkout that's `uv run claude-memory-graph …` / `uv run claude-hooks …`; to have
them on PATH permanently: `uv tool install .` and `uv tool install ./hook-kit`.

---

## 1. The machine, piece by piece

Each row: what it does, when it runs, where the code is, and how to see it working.

### hook-kit — the plumbing everything rides on
Claude Code fires hook events (SessionStart, UserPromptSubmit, PostToolUse, Stop,
PreCompact, SessionEnd); each one runs `hooks/dispatch.sh`, which calls hook-kit's
dispatcher. The dispatcher maintains **core session state** (prompt counts, project,
event counts, transcript telemetry) in `~/.claude/hook-kit/sessions/<session_id>.json`,
then runs every enabled extension and formats the output for that event's channel (plain
stdout for injection events, block-JSON for Stop, additionalContext-JSON for PreCompact).
- Code: `hook-kit/claude_hook_kit/` (`dispatch.py`, `state.py`, `extension.py`, `registry.py`)
- See it: `claude-hooks list` (what's enabled) · `claude-hooks state <session_id>` (live
  counters) · `cat ~/.claude/hook-kit/errors.log` (crashes — extensions fail open, so
  this file is the only place a broken extension is visible)
- Poke it by hand (this is your main debugging tool — every behaviour below can be
  triggered from a terminal):
  ```sh
  echo '{"session_id":"debug","cwd":"'$PWD'","prompt":"why pyoxigraph?"}' \
      | claude-hooks dispatch UserPromptSubmit
  echo '{"session_id":"debug","cwd":"'$PWD'"}' | claude-hooks dispatch Stop
  ```

### Session-start prime — memory arrives before you ask
On SessionStart, recalls the current Project (cwd basename) and, if `MEMORY_GRAPH_USER`
is set, your Person node — depth 2, so orientation Patterns, Decisions, and their links
arrive as the session's opening context. Silent when the graph doesn't know the project.
- Code: `claude_memory_graph/gate/recall.py` → `on_session_start`

### The ambient recall gate — graph layer
Every prompt is tokenized and scored against every live graph node (IDF-weighted word
overlap, ×3 for name hits, phrase bonuses, project-proximity boost). Confident matches
inject; everything else is silence — and **both outcomes are logged**, which is what makes
tuning possible.
- Code: `gate/recall.py` → `on_user_prompt_submit` · Log: `~/.claude/hook-kit/injections.jsonl`
- Example: prompt "why did we pick pyoxigraph over rdflib?" → injects
  `Decision 'Use pyoxigraph over rdflib': rationale … (affects→ Project '…')`.

### Session-log recall — the PRIMARY layer
Same prompt, second corpus: entries parsed from **undistilled context files**. This is
what makes knowledge recallable the moment it's written, before any distill. Eligibility
prevents duplication: another session's files always qualify (handoff); your own
session's file only after a compaction (before that, the conversation that wrote it is
still in context). Shares the injection budget with the graph layer; graph wins ties.
- Code: `gate/session_corpus.py` + `gate/recall.py` → `_log_recall`
- Log: `injections.jsonl` lines with `"kind": "log"`
- Example injection:
  ```
  Session log (undistilled — verify before acting):
  - [charcoal__2026-07-06_19-01.md] Decision: Use pinia stores — rationale: strict layout…
  ```

### The context counter — capture, enforced
Four behaviours in one extension (`gate/nudge.py`):
1. **Stop block (cadence):** counts significant prompts; when the context file is ≥
   `N_TURNS` behind the count, the Stop hook returns `{"decision":"block","reason":…}` —
   the model must write the log before it may finish. Keyed to the file's mtime, so an
   ignored block re-fires every turn until a real write happens. The reason is
   self-contained (exact path + entry format), and if no file exists the hook **stamps**
   one so the artifact always exists.
2. **Dig counter:** PostToolUse counts file-inspection calls (Grep/Glob/Read +
   search-shaped Bash) per turn. A turn past `DIG_THRESHOLD` was an investigation → the
   Stop block also asks for a *trace* entry (the finding + the question-as-aliases).
3. **Pressure escalation:** past `PRESSURE_TOKENS` of context, ANY uncaptured exchange
   blocks — compaction is near.
4. **Flush points:** PreCompact steers the compaction summary (carry forward uncaptured
   points; point at the context file); SessionEnd suggests distill at ≥3 undistilled files.
- See it: `claude-hooks state <id>` → extension `context-counter` (`written_at`,
  `last_mtime`, `dig_turn`/`dig_count`).

### The context file — the write-ahead log
`~/.claude/context/<project>__YYYY-MM-DD_HH-MM.md`. Two entry shapes: narrative one-liners
(anything goes) and **structured entries** (graph-shaped, mechanically promotable):
```markdown
- [14:32] Decision: Use pyoxigraph over rdflib
  rationale: native quad store; rdflib named-graph handling too slow
  affects: Project/claude-memory-graph
  concepts: rdf, storage
  aliases: rdf store choice, oxigraph
```
- Format spec: `hooks/context-protocol.md` (injected each SessionStart)
- Parser: `claude_memory_graph/context_entries.py`

### Mechanical distill — promotion without an LLM
`claude-memory-graph distill` parses structured entries, **folds** repeats (latest values
win — mid-session churn resolves itself), and applies them through the same handlers the
MCP tools use, hard capture rules unchanged. Anything questionable is **refused to the
residue** (never forced): narrative bullets, duplicate-guard hits, unknown relations,
missing required properties — each reported with `file:line`. A file archives only when
nothing was left behind; otherwise it stays active for the skill.
- Code: `claude_memory_graph/distill.py` · Skill for the residue: `skills/distill/SKILL.md`
- **Run it between sessions** — a live MCP server's next save would overwrite CLI writes.

### The graph + MCP server
pyoxigraph store at `~/.claude/memory-graph/store/graph.nq` (human-readable NQuads — you
can literally `grep` your memory). Typed resources in per-instance named graphs, reified
links with **two clocks** (see §2), hard capture rules at the write path, code-anchor
drift flags at recall.
- Code: `store.py`, `capture_rules.py`, `tools/`, `base.ttl` (the ontology)

### The query planner
`claude-memory-graph ask "what decisions affect charcoal?"` grounds the words against the
graph's own lexicon (names, aliases, relation verb forms) and composes SPARQL; `--explain`
shows the grounding table and the query. Its decisions log to `ask-decisions.jsonl`;
`claude-memory-graph asks` reports outcomes and vocabulary gaps.
- Code: `claude_memory_graph/planner.py`

### The instruments
- **Pulse** (`claude-memory-graph pulse [--days N]`) — **start here**: one screen answering
  "is memory reaching my sessions?" — primes, graph/log injections with top nodes, capture
  enforcement (blocks/digs/observed writes), explicit recalls, the miss headline, and the
  distill backlog. Every zero comes with a diagnosis line.
- **Gap finder** (`claude-memory-graph gaps`; top candidates also appended to
  `memory_reflect`): mechanical link candidates — orphans, concept-less nodes, and
  unlinked pairs sharing rare vocabulary, with the shared words as evidence. The reflect
  skill judges this list; detection is never the LLM's job.
- **Miss detector** (`claude-memory-graph misses`): joins gate silences with the model's
  explicit recalls — every "gate said nothing, model went to the shelf and found it" is a
  labelled false negative, with a suggested fix (threshold vs vocabulary).
- **Coverage harness** (`claude-memory-graph coverage --transcripts ~/.claude/projects`):
  what fraction of your real question-prompts the grounder can ground.
- Field-by-field log reference: [TUNING.md](TUNING.md).

---

## 2. Terminology, with examples

- **Significant prompt** — a prompt with real words left after stopwording. "thanks" and
  "ok" advance nothing; "fix the csv export path" counts. Drives the Stop-block cadence.
- **Stop block** — the hook returning `{"decision":"block","reason":"…"}` at turn end;
  the model must satisfy the reason before finishing. Our enforcement channel.
- **`stop_hook_active`** — flag on the stop that *follows* a block. The dispatcher never
  blocks it — that's the infinite-loop guard. If you see two blocks in a row across
  *turns*, that's the write-keyed cadence working, not the guard failing.
- **Dig / trace** — a dig is a turn that needed many file inspections (e.g. 12 greps to
  find the state write path). The trace is the finding stored as
  `Pattern kind: trace`, with the *question phrasings as aliases* so the next session's
  question matches before the greps start.
- **Orientation memory** — convention-level "how/where things live":
  `Pattern "hook-kit state layout", kind: storage, anchorPath: hook-kit/claude_hook_kit/state.py`.
  Passes the keep test because re-deriving it means reading several files.
- **Structured entry / narrative entry** — see the format above. Structured = the
  mechanical lane can promote it. Narrative = residue, LLM lane.
- **Fold** — merging repeated `Type: name` bullets, latest value per property winning.
  Writing `- [15:30] Decision: Use pyoxigraph over rdflib` + `outcome: shipped` later in
  a session *updates* the earlier entry at distill time.
- **Residue** — what mechanical distill refuses: e.g.
  `charcoal__…md:12 [Problem: flaky mtime test] — narrative entry (LLM lane)`.
- **Eligibility** — the session-log recall rule: an entry can inject only when its
  authoring context is gone (other session's file, or own file after compaction).
- **Miss vs capture gap** — miss: gate silent, model explicitly recalled it, *and it was
  there* (retrieval's fault). Capture gap: model looked and found nothing (capture's
  fault — nothing to tune, something to write down).
- **Two clocks (bi-temporal links)** — `linkValidFrom/linkValidUntil` = when the fact was
  true in the world; `linkInvalidatedAt` + `invalidationKind` = when we revised belief.
  `worldChange` (was true, ended: job change) vs `correction` (never true: mis-captured).
  Adding `employedBy Acme` auto-closes an open `employedBy Flax and Teal` — nothing
  deleted, the old edge gets bounded. Recall shows only open edges.
- **Code anchor / drift flag** — `anchorPath` + `anchorCommit` on a code memory; recall
  appends `(code changed since a1b2c3d)` when that path has newer commits. Read as
  "true as of that commit".
- **Auto-prime** — the SessionStart injection of Project/Person recall.
- **IDF** — inverse document frequency: rare words score high ("pyoxigraph"), common
  words barely count ("store"). Why distinctive names matter in prompts *and* node names.

### Transcript telemetry (your question)
Claude Code writes every session to a JSONL **transcript** (`~/.claude/projects/...`),
and each assistant message in it records exact token usage. On every hook dispatch,
hook-kit reads just the transcript's *tail* (last 64KB — milliseconds) and puts the
numbers into core state:
- `context_tokens` — the model's current context size (input + cache reads + cache
  writes of the last turn). This is how the hooks know how full the window is.
- `last_output_tokens` — the last turn's output spend.
It exists so decisions that depend on context pressure are **measured, not guessed**: the
Stop block escalates past `PRESSURE_TOKENS` (capture everything now — compaction is
close), and it's the phase-0 instrument for the deferred context-window work. See it:
`claude-hooks state <session_id>` → `context_tokens`. Fail-open: no transcript, no
fields, no error.

---

## 3. Getting it running (checklist)

1. **Install/update the plugins** (hooks config is read at session start — new hooks
   need a plugin update AND a fresh session):
   ```sh
   claude plugin marketplace add <repo-url-or-path>
   claude plugin install memory-graph@claude-memory-graph --scope user   # pulls hook-kit
   ```
2. **Optional env** (set in your shell profile): `MEMORY_GRAPH_USER="Stuart Marshall"`
   (enables Person auto-prime) · `MEMORY_GRAPH_PATH` / `CLAUDE_CONTEXT_DIR` /
   `CLAUDE_HOOK_KIT_HOME` to relocate data (defaults under `~/.claude/`).
3. **Verify in a fresh session**: `/hooks` should list SessionStart, UserPromptSubmit,
   PostToolUse, Stop, PreCompact, SessionEnd. Then from a terminal:
   ```sh
   claude-hooks list                    # both extensions [enabled]
   echo '{"session_id":"t","cwd":"'$PWD'","prompt":"test one two"}' \
       | claude-hooks dispatch UserPromptSubmit
   claude-hooks state t                 # counters advanced
   ```
4. **Seed the graph** so priming has something to say: in a session, tell Claude a few
   durable facts ("we chose X because Y — store that"), or run `/memory-graph:distill`
   on your first context files.
5. **Work normally for a few days.** The logs accumulate on their own.

## 4. Watching it (the logs)

```sh
claude-memory-graph pulse                # ONE SCREEN: is memory reaching sessions?
claude-hooks log                         # last 20 gate decisions, pretty-printed
claude-hooks log -f                      # follow live while you work in another pane
claude-hooks log explicit-recalls.jsonl  # every explicit memory tool call
claude-hooks state <session_id>          # counters, dig state, context_tokens
claude-memory-graph misses               # retrieval false negatives, graded, with fixes
claude-memory-graph asks                 # planner outcomes + vocabulary gaps
claude-memory-graph coverage --transcripts ~/.claude/projects
cat ~/.claude/hook-kit/errors.log        # extension crashes (fail-open evidence)
```
`INJECT` lines you'd call irrelevant are false positives — note them; silences followed
by you asking Claude to "check memory" are misses — `misses` catches those automatically.

## 5. Tuning playbook — symptom → knob

All knobs live in **`~/.claude/memory-graph/gate.json`** (create it; picked up next
prompt, no restart). Defaults in `gate/runtime.py`.

| Symptom | Knob | Direction |
|---|---|---|
| Irrelevant memories injected | `ABS_MIN` (3.0) / `MARGIN` (1.5) | raise |
| `misses` says "threshold miss — scored 2.7 vs 3.0" | `ABS_MIN` | lower to what the report suggests |
| `misses` says "vocabulary miss" | not a knob | add `aliases`/concept links to that node |
| Stop block nags during genuinely note-free stretches | `N_TURNS` (3) | raise |
| Refactor-heavy turns flagged as digs | `DIG_THRESHOLD` (8) | raise |
| Real investigations don't trigger the trace ask | `DIG_THRESHOLD` | lower carefully |
| Session-log injections noisy (unvetted entries) | `LOG_ABS_MIN` (3.0) | raise above `ABS_MIN` |
| Pressure escalation too early/late | `PRESSURE_TOKENS` (140000) | move |
| Wrong-project memories outrank current project | `PROX_BOOST` (1.5) | raise |

Rule of thumb from TUNING.md: false negatives label themselves (the miss detector);
false positives need your eyes on `claude-hooks log`. The gate is biased toward silence,
so most tuning pressure should come from the miss report, not from gut feel.

## 6. How to prompt so the system works with you

- **Use distinctive names.** Matching is lexical: "why did we pick *pyoxigraph*?" recalls;
  "why did we pick that library?" can't. Same rule applies to what you *store* — the
  name is the identity and the strongest retrieval key.
- **State corrections and preferences explicitly** ("no — always use uv, not pip").
  Explicit corrections are the zero-churn facts that may be written straight to the graph.
- **Let the Stop block do its job.** When a turn ends with "append the key points…",
  that write IS the memory system working — don't wave it off. If it keeps firing,
  the log genuinely is behind.
- **Ask *why/what-do-we-know* questions of memory; *where/how* questions of code tools.**
  For structural questions about the graph itself, `claude-memory-graph ask "…" --explain`.
- **Handoffs need no ceremony**: start a session in the project directory; prime +
  session-log recall bring the relevant slice. To pull more, ask Claude to
  `memory_recall` the project at depth 2 or read the context file the injection names.
- **After a reversal**, say so plainly ("we're abandoning X for Y") — that's what writes
  the `supersedes:` line and closes the old edge instead of leaving two truths.

## 7. When to run what (cadence)

| When | Command | Why |
|---|---|---|
| Start of a work block | *(nothing)* | prime + recall are automatic |
| Whenever you wonder "is this on?" | `claude-memory-graph pulse` | injections, enforcement, backlog — zeros come with diagnoses |
| Weekly, or when a visualisation shows loose nodes | `claude-memory-graph gaps` → `/memory-graph:reflect` | mechanical candidates → LLM judges and links |
| End of a session / few sessions | `claude-memory-graph distill` | promote structured entries, zero tokens |
| When distill reports residue | `/memory-graph:distill` in a session | LLM pass over the leftovers only |
| Weekly, or after a "why didn't it remember?" moment | `claude-memory-graph misses` | evidence-based threshold/alias fixes |
| Weekly | `claude-hooks log -n 50` | eyeball false positives |
| After ~a week of sessions | `claude-memory-graph coverage --transcripts ~/.claude/projects` | is the lexical grounder enough? (the embeddings go/no-go metric) |
| When `ask` answers feel wrong | `claude-memory-graph asks` | misgrounding suspects, vocabulary gaps |
| Any weirdness | `claude-hooks state <id>` + `errors.log` | counters + crash evidence |

## 8. Debugging recipes

- **Nothing ever injects** → `claude-memory-graph reflect` (is there anything in the
  graph?); `claude-hooks list` (extensions enabled?); manual `dispatch UserPromptSubmit`
  with a prompt containing an exact node name; check `MEMORY_GRAPH_PATH` matches between
  the MCP server and the gate.
- **Stop block never fires** → `/hooks` shows Stop? (plugin updated + fresh session?);
  manual `dispatch Stop` after 3 significant `dispatch UserPromptSubmit`s; check
  `context-counter` state — a moving `last_mtime` means write-detection thinks the log
  is fresh (is something else touching the context dir?).
- **Stop block fires but no file appears** → it stamps on *overdue*, so check the block's
  reason names a path, then check permissions on `CLAUDE_CONTEXT_DIR`.
- **`distill` reports 0 files** → files must match `<project>__*.md` and contain
  `distilled: false` in the first 300 bytes; `--project` filters by cwd basename.
- **`distill` refused something you want stored** → the residue line says exactly why
  (missing rationale, similar existing name, unknown relation); fix the entry or let the
  skill lane judge it.
- **Session-log recall silent when it shouldn't be** → own-session files need a
  compaction first (that's the eligibility rule, not a bug); check the file's mtime is
  *older* than the current session for the handoff case; check `injections.jsonl`
  `kind:"log"` lines for the scores it saw.
- **An extension broke** → sessions degrade to normal Claude (fail-open, by design);
  the traceback is in `~/.claude/hook-kit/errors.log`.
