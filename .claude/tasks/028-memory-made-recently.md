---
id: 028
slug: memory-made-recently
status: draft
branch: crew/028-memory-made-recently
model: opus
env: laptop
files:
  - claude_memory_graph/
---

# The memory graph reads "made/decided recently" as the creation date

Stub, 2026-11-08, from task 024's Worker notes. After 024, "what decisions were made recently?" narrates "Find Decisions mentioning 'made', most recent first". The memory planner then says it ignored 'made' and lists the decisions. A memory whose text contains "made" would narrow the list: it's visible in the narration, but it isn't what the question means.

The fix belongs in the memory vocabulary (`claude_memory_graph/`), not in Ceist:
- "made", "decided", "created" or "added" next to "recently" (or "when") means the creation date (`createdAt`);
- "recent" ordering currently uses `updatedAt`; decide which a bare "recent" should mean.

Check `tests/test_planner.py`, and add cases for "what decisions were made recently?" and "which decisions did we make?".
