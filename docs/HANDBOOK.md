# The operator's handbook — run, watch, debug, tune

Everything else in `docs/` explains *why* the system is shaped this way. This doc is the
*how*: what each piece is doing at runtime, where its code and logs live, the terminology
with examples, the setup steps, the tuning playbook, and how to work *with* it day to day.

CLI note: examples use `claude-memory-graph …` as the command. From a repo checkout that's
`uv run claude-memory-graph …`; to have it on PATH permanently: `uv tool install .`.

---

## 1. The machine, piece by piece

Each row: what it does, when it runs, where the code is, and how to see it working.

### The mod — the plumbing everything rides on
The plugin's mod ([hooks/register.ts](../hooks/register.ts)) loads with the plugin in every
Claude Code session (2.1.287+) and does the routing:
- **in-process, no process started:** session state (in the engine's `$.state`, so it
  survives a mod reload), counting digs on every Read/Grep/Glob/Bash, pre-approving writes
  to the context log, steering compaction, and the pane;
- **one Python call** per prompt, per Stop, and at session start/end:
  `python -m claude_memory_graph.hookrun`, stateless — the session state goes in on stdin
  and comes back in the reply, and the mod stores it. Python advances the **core
  counters** (prompt counts, project, transcript telemetry) and runs the three
  extensions: `memory-recall`, `context-counter`, and `graph-review` (opt-in).
- Code: `hooks/register.ts` (the mod) · `claude_memory_graph/hookrun.py` (the call) ·
  `claude_memory_graph/hookcore/` (core counters, state home, tokenizer)
- See it: the pane (`/graph-panel`) — **State** tab for the live counters and the last
  Python error, **Injected** tab for everything put in front of the model. Crashes also
  go to `~/.claude/memory-graph/state/errors.log` (extensions fail open, so a broken one
  is visible only there and in the pane).
- Poke it by hand — every behaviour below can be triggered from a terminal:
  ```sh
  claude-memory-graph gate "why pyoxigraph?" --project "$(basename "$PWD")"   # prompt decision, no side effects
  echo '{"event":"Stop","payload":{"cwd":"'$PWD'"},"core":{"significant_prompt_count":3}}' \
      | python -m claude_memory_graph.hookrun                                    # one event, as the mod sends it
  ```

### Project identity — how a session knows where it is
Everything project-scoped (priming, the proximity boost, context-file grouping,
session-log recall, distill's `--project`) keys on ONE name, resolved per session:
1. `MEMORY_GRAPH_PROJECT` env — explicit override (monorepos; a repo cloned under a
   different directory name);
2. the **git repo root's** basename — a session started in `~/dev/charcoal/frontend`
   still belongs to `charcoal`;
3. the cwd basename (non-repo directories).
The convention that makes recall line up: **a Project node's `name` is the repo
directory's basename.** If they diverge (renamed checkout), set the override — a
mismatch is silent: no prime, no proximity, a phantom context-file group. Check what a
session resolved in the pane's **State** tab → `project`.

### Session-start prime — memory arrives before you ask
On SessionStart, recalls the current Project (see project identity above) and, if
`MEMORY_GRAPH_USER` is set, your Person node — depth 2, so orientation Patterns,
Decisions, and their links arrive as the session's opening context. Silent when the
graph doesn't know the project.
- Code: `claude_memory_graph/gate/recall.py` → `on_session_start`

### The ambient recall gate — graph layer
Every prompt is tokenized and scored against every live graph node (IDF-weighted word
overlap, ×3 for name hits, phrase bonuses, project-proximity boost). Confident matches
inject; everything else is silence — and **both outcomes are logged**, which is what makes
tuning possible.
- Code: `gate/recall.py` → `on_user_prompt_submit` · Log: `~/.claude/memory-graph/state/injections.jsonl`
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
- See it: the pane's **State** tab (uncaptured turns, digs this turn); the raw fields
  (`written_at`, `last_mtime`, `dig_turn`/`dig_count`) are in the mod's session state.

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

### Mechanical distill — promotion without an LLM, now automatic
Distill parses structured entries, **folds** repeats (latest values win — mid-session
churn resolves itself), and applies them through the same handlers the MCP tools use,
hard capture rules unchanged. Anything questionable is **refused to the residue** (never
forced): narrative bullets, duplicate-guard hits, unknown relations, missing required
properties — each reported with `file:line`.
- **Automatic (the default path):** every MCP server start (= every new session) runs a
  promote-only pass — no marking, no archiving, idempotent (upserts + idempotent links),
  self-healing, fail-open, logged to `capture.jsonl`. You do nothing.
  Disable: `MEMORY_GRAPH_AUTO_DISTILL=0`.
- **In a session: the `memory_distill` MCP tool** (what the /distill skill calls first) —
  same code, and the form that also marks + archives clean files.
- **From a terminal: `claude-memory-graph distill`** — only on PATH from a repo checkout
  (`uv run …`) or after `uv tool install`; **plugin installs don't put the CLI on PATH**.
- Code: `claude_memory_graph/distill.py` · Agent for the residue: `agents/distiller.md` (spawned by `skills/distill/SKILL.md`)

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

**Start every "why isn't it doing anything?" with one command:**
```sh
claude-memory-graph doctor
```
It checks the three things that break silently and look identical — hooks not firing
(stale plugin), the CLI and plugin reading different paths (a set env var), and an empty
or link-less graph — prints the exact paths it inspected, and ends with a prioritised
diagnosis and the specific fix. If it says everything's wired, *then* reach for the
per-question instruments below.

**Which instrument answers which question** (they don't feed each other):

| You did | It logged to | Read it with |
|---|---|---|
| worked in a session (prompts) | `injections.jsonl` (fired AND silent) | `pulse`, `misses`, `claude-memory-graph log` |
| the model called a memory tool in-session | `explicit-recalls.jsonl` | `misses` (the join) |
| ran `ask` (planner) anywhere | `ask-decisions.jsonl` | `asks` — **never** `misses` |
| wondered "what would this prompt inject?" | nothing — side-effect-free | `gate "<prompt>"` |

A miss requires two in-session events: the gate stayed silent on a prompt AND the model
then explicitly recalled the thing. Terminal `ask` runs touch neither — few misses after
running `ask` is expected, not a wiring gap.

- **Gate preview** (`claude-memory-graph gate "<prompt>" [--project P]`) — the REAL
  injection decision for a prompt, shown with its work: terms, per-candidate scores,
  thresholds, both layers, and the inject/silent verdict with the reason. Writes no
  logs, no memo — experiment freely. **`memory_search` is not this**: search is the
  fuzzy entry-point finder (no thresholds, no proximity, no session-log layer, concepts
  included) — good for "does the graph know anything about X?", wrong for predicting
  injections.
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
- **Graph viewer** (`claude-memory-graph viz`): renders the whole graph as a
  self-contained interactive HTML page (force layout, type filters, search,
  per-node detail) and opens it in the browser. Read-only snapshot — rerun to
  refresh. `--out PATH` / `--no-open` for scripting.
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
  `Pattern "Session state layout", kind: storage, anchorPath: claude_memory_graph/hookcore/state.py`.
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
and each assistant message in it records exact token usage. On every hook event the mod sends,
the Python side reads just the transcript's *tail* (last 64KB — milliseconds) and puts the
numbers into core state:
- `context_tokens` — the model's current context size (input + cache reads + cache
  writes of the last turn). This is how the hooks know how full the window is.
- `last_output_tokens` — the last turn's output spend.
It exists so decisions that depend on context pressure are **measured, not guessed**: the
Stop block escalates past `PRESSURE_TOKENS` (capture everything now — compaction is
close), and it's the phase-0 instrument for the deferred context-window work. See it:
the pane's **State** tab → context tokens. Fail-open: no transcript, no
fields, no error.

---

## 3. Getting it running (checklist)

1. **Install or update the plugin** (needs Claude Code 2.1.287+ and `uv`):
   ```sh
   claude plugin marketplace add StuCM/claude-memory-graph
   claude plugin install memory-graph@claude-memory-graph --scope user
   ```
   Upgrading from 0.13 or earlier: remove the memory-graph entries from the `"hooks"`
   block of `~/.claude/settings.json` and uninstall `hook-kit` — `doctor` flags leftovers.
2. **Optional env** (set in your shell profile): `MEMORY_GRAPH_USER="Stuart Marshall"`
   (enables Person auto-prime) · `MEMORY_GRAPH_PATH` / `CLAUDE_CONTEXT_DIR` /
   `MEMORY_GRAPH_STATE` to relocate data (defaults under `~/.claude/`) ·
   `MEMORY_GRAPH_PROJECT` to override the project name.
3. **Verify in a fresh session**: send a prompt, then open `/graph-panel` — the **State**
   tab should show the project and a prompt count, with no error. From a terminal,
   `claude-memory-graph doctor` gives one verdict for the whole setup.
4. **Seed the graph** so priming has something to say: in a session, tell Claude a few
   durable facts ("we chose X because Y — store that"), or run `/memory-graph:distill`
   on your first context files.
5. **Work normally for a few days.** The logs accumulate on their own.

## 4. Watching it (the logs)

```sh
claude-memory-graph pulse                # ONE SCREEN: is memory reaching sessions?
claude-memory-graph dashboard            # same + trends, as HTML (open the printed path)
claude-memory-graph gate "my prompt"     # what WOULD this prompt inject, and why?
claude-memory-graph serve --token S      # share this memory over HTTP (see README)
claude-memory-graph log                  # last 20 gate decisions, pretty-printed
claude-memory-graph log -f               # follow live while you work in another pane
claude-memory-graph log explicit-recalls.jsonl  # every explicit memory tool call
claude-memory-graph misses               # retrieval false negatives, graded, with fixes
claude-memory-graph asks                 # planner outcomes + vocabulary gaps
claude-memory-graph coverage --transcripts ~/.claude/projects
cat ~/.claude/memory-graph/state/errors.log  # extension crashes (fail-open evidence)
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
| A paraphrase you'd expect to match stays silent (log: `sem_top` just under 0.40) | `SEM_MIN` (0.40) | lower a little; better, add a symptom-style alias to that memory |
| Memories injected "by meaning" that aren't relevant (log: `"via": "semantic"`) | `SEM_MIN` / `SEM_GAP` (0.08) | raise |
| Prompts feel slow, or you want word matching only | `SEMANTIC` (true) | `false` |
| You'd rather the injection carried the memory's content and an explicit recall call | `INJECT_STYLE` ("pointer") | `"full"` |
| Silent on a topic you've distilled heavily (log: high `top`, `rest` ≈ `top`) | `CLUSTER_FACTOR` (3.0) | lower — a tied group scoring ≥ this × `ABS_MIN` injects its head plus a "+N similar" pointer |
| "+N similar" pointers on matches you'd call generic | `CLUSTER_FACTOR` | raise |
| Session-start prime too long / too short | `PRIME_MAX_CHARS` (3000) | move — decisions/patterns/constraints rank first; the rest sit behind a "+N more" pointer |

Rule of thumb from TUNING.md: false negatives label themselves (the miss detector);
false positives need your eyes on `claude-memory-graph log`. The gate is biased toward silence,
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
| End of a session | *(nothing)* | structured entries auto-promote at the next session's start |
| Occasionally (weekly-ish) | `claude-memory-graph dashboard` → open the printed HTML | the whole picture: payouts, enforcement, gaps, backlog |
| When pulse/dashboard shows residue piling up | `/memory-graph:distill` in a session | LLM pass over narrative leftovers + archive clean files |
| Weekly, or after a "why didn't it remember?" moment | `claude-memory-graph misses` | evidence-based threshold/alias fixes |
| Weekly | `claude-memory-graph log -n 50` | eyeball false positives |
| After ~a week of sessions | `claude-memory-graph coverage --transcripts ~/.claude/projects` | is the lexical grounder enough? (the embeddings go/no-go metric) |
| When `ask` answers feel wrong | `claude-memory-graph asks` | misgrounding suspects, vocabulary gaps |
| Any weirdness | the pane's **State** tab + `errors.log` | counters + crash evidence |

## 8. Debugging recipes

- **Nothing ever injects** → `claude-memory-graph reflect` (is there anything in the
  graph?); `claude-memory-graph gate "<a prompt naming a node exactly>"`;
  the pane's **State** tab for a Python error; check `MEMORY_GRAPH_PATH` matches between
  the MCP server and the gate.
- **Stop block never fires** → plugin updated, fresh session, and the pane's **State**
  tab counting uncaptured turns? Run a Stop by hand with `hookrun` (above) and
  `"core": {"significant_prompt_count": 3}`; check
  `context-counter` state — a moving `last_mtime` means write-detection thinks the log
  is fresh (is something else touching the context dir?).
- **Stop block fires but no file appears** → it stamps on *overdue*, so check the block's
  reason names a path, then check permissions on `CLAUDE_CONTEXT_DIR`.
- **"Nothing traverses / nothing records / no memory at all"** → `claude-memory-graph
  doctor` first — it diagnoses the whole class (dead hooks, path mismatch, empty/orphan
  graph) in one shot with the fix. Note: there is **no derived code graph** (horizon
  feature) — a grep-heavy turn writes a *trace* entry that distills to a `Pattern
  (kind: trace)`; look for those in `reflect`, not for a code graph.
- **A session says "claude-memory-graph: command not found" / "tools not installed"** →
  expected: plugin installs run the server via `uvx --from` and put NO CLI on PATH. In a
  session the model should call the `memory_distill` tool (same code, safer); the CLI is
  for terminals, via a repo checkout (`uv run …`) or `uv tool install`.
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
  the traceback is in `~/.claude/memory-graph/state/errors.log` and the pane's
  **State** tab.
