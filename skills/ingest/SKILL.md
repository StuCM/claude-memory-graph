---
name: ingest
description: Distill arbitrary markdown documents (an issues repo, ADRs, postmortems, notes — not session context files) into the long-term memory graph. Use when the user says "ingest <path>", "distill this repo/directory/file into memory", or points at documents outside ~/.claude/context/.
---

# Ingest Documents into the Memory Graph

Distill a directory (or explicit list) of markdown documents into the memory-graph MCP server.
Same extraction discipline as `/memory-graph:distill`, different source: these are documents you
do not own the lifecycle of — so **never modify the source files** (no frontmatter edits, no
moving to archive). Ingestion state lives in the graph itself, via provenance.

## Steps

### 1. Scope
The user names a directory, repo, or files. Glob `**/*.md` beneath a directory. Tell the user
the file count before starting; for large sets (>~30 files), process in batches and report per
batch. Skip files that are clearly navigation/boilerplate (index pages, templates, licences).

### 2. Skip what's already ingested
Every node created by ingestion carries a `sourceDocument` property (see step 4). Before
processing a file, check for it:

```sparql
SELECT ?name WHERE { GRAPH ?g { ?n mem:sourceDocument "<repo-or-dir-name>/<relative-path>" .
                                ?n mem:name ?name } }
```

If nodes exist for that path, skip the file — unless the user asked to re-ingest, in which case
prefer updating those existing nodes over creating new ones.

### 3. Extract — the capture rubric applies unchanged
A candidate fact earns a node only if it is **durable** (useful beyond the document), **not
derivable** (the *why*, the gotcha, the constraint — not what a diff or the doc's mere existence
already says), and **reachable** (you can link it to a Project, Technology, Person, or concept).
Quality over quantity: a fixed typo is not a memory; a recurring failure mode with its root
cause is. For an issues repo specifically:

| Document content | Maps to |
|---|---|
| Recurring problem, root cause, workaround/fix | **Pattern** (`description`, `example`, `appliesWhen`) |
| Open/unresolved issue that future work must respect | **Task** (`status`, `context`) |
| A choice made and its reasoning (ADR-shaped) | **Decision** (`rationale`, `outcome`, `date`, `status`) |
| Hard limits, compliance, environment facts | **Constraint** concept, linked to affected Projects |
| Systems/tools the documents reveal are in play | **Technology**, linked to the Project |

Favour the document set's *final* understanding: if issue 12 supersedes issue 7's diagnosis,
store the corrected version (and use the `supersedes` flow if both are worth keeping).

### 4. Store — with provenance
Use the standard tools (`memory_store_resource`, `memory_store_concept`, `memory_link`), naming
conventions and terse property values as in the distill skill, plus on **every node created or
substantially updated from a document**:

- `sourceDocument`: `<repo-or-dir-name>/<relative-path>` — this is also the re-ingest ledger
- `sourceKind`: e.g. `issue-report`, `adr`, `postmortem`, `notes`
- `aliases`: the 2–3 phrasings a future prompt would plausibly use for this knowledge — and link
  every node to at least one concept (concepts are the associative index for future recall)

Before creating any node, check for near-duplicates the graph may already hold from sessions
(`memory_recall` the obvious names; `memory_query` with `CONTAINS` on key terms) — an issue
report often describes a gotcha that a past session already stored. Update the existing node
(add `sourceDocument` alongside) rather than minting a twin.

Link everything: at minimum each ingested node → its Project. A node you cannot link probably
failed the rubric.

### 5. Report
Terse summary: files scanned / skipped-as-ingested / skipped-as-noise, nodes created and updated
by model, links created, and any documents that contained *nothing* durable (so the user knows
they were considered, not missed).
