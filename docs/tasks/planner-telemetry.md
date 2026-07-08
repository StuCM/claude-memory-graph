# Task: planner telemetry + verb-form self-correction

Status: **done** (2026-07-08) · Owner: Stuart · Created: 2026-07-08 · Size: S

## Goal

Close the lexicon self-correction loop the planner was missing: evidence of
misgrounding, and a write path to fix it.

1. **Evidence** — every `ask` appends one line to `ask-decisions.jsonl` in the
   hook-kit home (mirrors the gate's `injections.jsonl`): question, wh-word,
   grounded relations *with the verb form that fired*, types, anchor, coverage,
   uncovered terms, outcome (`answered/direct/statement/refused/low-coverage/
   no-subject/no-rows`), row count.
2. **Report** — `claude-memory-graph asks` (read-only CLI) joins the log into
   two curation signals: *misgrounding suspects* (a verb form that fires but its
   asks always end dry — e.g. prose "under" colliding with `partOf`) and
   *vocabulary gaps* (terms nothing grounds in failed asks).
3. **Write path** — `memory_amend_relation` MCP tool (writes stay MCP-only):
   add verb forms to any relation; remove only from LLM-added relations —
   removing a base-ontology form from the store would silently resurrect on the
   next base.ttl version bump, so built-ins are corrected in base.ttl itself.
4. **Loop closure** — reflect skill step 6 runs the report and applies the fixes.

## Depends

[[query-planner-v0]] (the telemetry source) · [[verb-forms-ontology]].

## Test

`tests/test_amend_telemetry.py`: added form grounds immediately; base-relation
removal refused; LLM-added removal works; every ask logs one entry; dry verb
form flagged as suspect; ungrounded terms flagged as gaps.
