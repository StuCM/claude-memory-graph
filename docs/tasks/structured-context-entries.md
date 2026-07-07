# Task: structured context entries → mechanical distill

Status: **phase 1 done (protocol + skill); phase 2 planned (parser)** · Owner: Stuart ·
Created: 2026-07-06 · Size: M

## The observed problem (2026-07-06 session)

Distill pays for the same knowledge twice. The in-session model writes prose bullets
(LLM write #1). A later distill session re-reads every undistilled file, re-derives
models, names, properties, aliases, concepts and links from that prose, and emits them
as dozens of sequential MCP calls — in practice three separate phases: create the
resources, create the concepts, then the joining links (LLM write #2). Long and
token-intensive for content the first model already held in richer form than the prose
it wrote down.

## The insight

What distill spends its tokens on is **re-derivation**, and re-derivation is only needed
because the context format throws the structure away. At the moment a key point is
recorded, the in-session model has the whole conversation *and is already composing the
bullet* — asking it to write the bullet in graph shape costs a couple of short extra
lines. Asking a second session to reconstruct that shape from prose costs an entire LLM
pass over every file.

So: move **structure** to write time; keep **judgment** at distill time. This refines
(not reverses) the CONTEXT-CREATION doctrine that graph-quality rules don't apply
mid-session. That doctrine targets *judgment* friction — naming deliberation, dedup
checks, promotion decisions — and those stay out of the session. Emitting the property
lines the model would eventually have to produce as tool-call arguments anyway is
transcription, not deliberation; doing it while the knowledge is in context is the cheap
moment.

## The format (phase 1 — protocol change, shipped)

Entries stay markdown and human-skimmable. The first line is unchanged from the current
protocol; a *structured* entry adds indented `key: value` continuation lines that mirror
the MCP call arguments:

```markdown
- [14:32] Decision: Use pyoxigraph over rdflib
  rationale: native quad store; rdflib named-graph handling too slow
  affects: Project/claude-memory-graph
  concepts: rdf, storage
  aliases: rdf store choice, oxigraph
```

Grammar — deliberately regular enough to parse without an LLM:

- **Head line** `- [HH:MM] <Type>: <name>` — `<Type>` is a graph model (`Decision`,
  `Pattern`, `Task`, `Technology`, …) or a narrative category (`Problem:`, `Scope:`,
  `Note:`). A bullet with **no continuation lines is narrative-only** — the frictionless
  capture lane is untouched; wrongness and churn remain welcome.
- **Property line** `  <prop>: <value>` — camelCase property, one-to-two-sentence value
  (`rationale`, `outcome`, `description`, `example`, `aliases`, …).
- **Link line** — a property line whose key is a relation and whose value is
  `<Model>/<name>` (`affects: Project/claude-memory-graph`,
  `supersedes: Decision/Use rdflib`).
- **`concepts:`** — comma list; shorthand for Concept links (the associative index).
- **Category mapping** for narrative heads that get structure later: Problem → Pattern
  (fix in `description`), User preference → Preference concept + `hasPreference` link,
  Discovery → Pattern, Scope → log-only.
- **Churn resolves mechanically**: re-stating the same `<Type>: <name>` later in the
  session overrides earlier values (last-writer-wins at fold time). A reversal writes
  `supersedes:` — write time is exactly when the model *knows* it is reversing.

Even before any parser exists this pays off: the /distill skill stops re-deriving and
starts transcribing — its step 2 collapses to "fold the structured entries", and its
tool calls proceed **per entry** (node, then its concepts and links, together) instead
of three graph-wide phases.

## Phase 2 — the mechanical distiller (no LLM)

`claude-memory-graph distill` (CLI, same package as the store — no MCP round trips, no
tokens):

1. **Parse** structured entries from `distilled: false` files (regex per line type;
   unparseable lines fall to the narrative residue).
2. **Fold** by `(model, name)`: last value per property wins; union links/concepts;
   apply the category mapping.
3. **Aim** (absorbs [[distill-two-pass-dedup]] for this lane): `search.py` each name
   against the graph; a similar hit switches to the update path. The server-side
   duplicate guard stays the backstop.
4. **Apply** in-process through the same handlers the MCP tools use
   (`handle_resource` / `handle_concept` / `handle_link`), nodes before links — the hard
   capture rules (name lint, required properties, provenance) run unchanged.
5. **Mark** `distilled: true`, archive, report — plus a list of narrative-only bullets
   left behind for an (optional, now small) LLM pass via the /distill skill.

Sketch:

```python
# claude_memory_graph/distill.py
HEAD = re.compile(r"^- \[(\d\d:\d\d)\] (\w[\w ]*): (.+)$")
PROP = re.compile(r"^  (\w+): (.+)$")
LINK_VALUE = re.compile(r"^([A-Z]\w+)/(.+)$")   # value shaped Model/name -> link

def parse(text) -> list[Entry]: ...            # bullets -> Entry(model, name, props, links)
def fold(entries) -> dict[tuple, Entry]: ...   # (model, name) -> merged, last-writer-wins
def apply(store, folded, source) -> Report: ...# aim -> handle_resource/concept/link
```

Token accounting: today ≈ bullets + (re-read all files + ~3–5 LLM-generated tool calls
per node). After ≈ bullets + ~2 extra lines per structured bullet + **zero** for the
mechanical lane. The second LLM write stage exists only for the narrative residue, and
its cost scales with the residue, not with the session.

Knock-on: this is what makes [[auto-distill]] safe — a deterministic lane can run
headlessly at SessionEnd without delegating promotion judgment to an unattended LLM;
only the residue waits for a human-invoked /distill.

## Open questions

- **Relation vocabulary at write time.** The writer may use a relation the ontology
  lacks. Parser behaviour: report it into the residue (skill lane decides whether to
  extend the ontology with verb forms) rather than fail the file.
- **How hard to push structure in the protocol?** Current stance: structured entries are
  the norm for graph-worthy categories (Decision/Pattern/preference), narrative stays
  legal everywhere. Revisit after a few sessions: if structure compliance decays the way
  counting did, the Stop-hook reason can name the expected shape.
- **RDF beyond our store?** The fold output is already subject–predicate–object; if
  sharing needs it, a `--ttl` flag emitting Turtle against base.ttl is a small step.
