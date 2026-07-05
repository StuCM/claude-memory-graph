# Task: <private> exclusion tags (learning from claude-mem)

Status: **planned** · Owner: Stuart · Created: 2026-07-05 · Size: S

## Goal

claude-mem lets users wrap content in `<private>` tags to exclude it from storage. Adopt the
same contract across our whole capture path:

- **Context protocol**: content inside `<private>…</private>` in a prompt is never written to
  context files.
- **Distill/ingest**: never promote private-tagged content to the graph.
- **Gate**: the analyzer strips private spans before tokenizing (never matches on them, never
  logs their terms to injections.jsonl).

## Why

Cheap, user-controlled redaction at the moment of capture — and it compounds for us: our
sharing/federation model is only as trustworthy as capture-time hygiene, and an explicit
exclusion primitive is simpler to trust than any retroactive redaction.

## Test

pytest: tagged span absent from gate terms and logs; distill instructions updated; tag spanning
multiple lines handled; unclosed tag fails safe (everything after the open tag excluded).
