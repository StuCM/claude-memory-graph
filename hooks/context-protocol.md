# Memory Graph: Recall First (memory-graph plugin)

Before re-deriving knowledge with codebase searches, big greps, or re-investigation, check the memory graph:

- **At the start of substantive work**: `memory_recall` the current project (model Project, name = working-directory basename, depth 2) and the user. This surfaces past decisions, known gotchas, constraints, and preferences in one call.
- **Before investigating a problem**: `memory_recall`/`memory_query` for related Patterns and Decisions — a gotcha may already be recorded with its fix and rationale.
- **Scope discipline**: the graph answers *why/what-do-we-know* questions (decisions, rationale, gotchas, preferences, project relationships). Code-structure questions (where is X defined, who calls Y) still belong to code search tools.
- If recall returns nothing relevant, proceed normally — and consider whether what you then learn belongs in the graph.

# Conversation Context Tracking (memory-graph plugin)

Maintain a running context file during every conversation. It serves two purposes:
1. **Handoff** — any LLM can read it to pick up in-progress work
2. **Distillation** — `/memory-graph:distill` extracts key knowledge into the long-term memory graph

## When to write
- **Start of conversation:** create the file with frontmatter and a brief note on what the user wants
- **After every significant interaction**, append. Significant means: a decision was made, a problem was solved, the user corrected you or stated a preference, an architectural choice was discussed, something non-obvious was discovered, or the scope changed
- You MUST update the file regularly, not just once at the start. If 3+ meaningful exchanges have happened since your last update, you are overdue

## File format
Location: `~/.claude/context/<project-name>__YYYY-MM-DD_HH-MM.md` where `<project-name>` is the basename of the working directory. Single global directory — do NOT create context dirs inside project repos.

```markdown
---
created: YYYY-MM-DDTHH:MM
distilled: false
summary: "<one-line summary, updated as the session evolves>"
---

## Key Points

- [HH:MM] Decision: chose X over Y because Z
- [HH:MM] Problem: encountered X, resolved by Y
- [HH:MM] User preference: prefers X approach
```

## What to capture
Decisions and their rationale (the *why*), problems and their fixes, user preferences and corrections, non-obvious discoveries, scope changes. Do NOT capture routine actions, anything obvious from code/git history, or full code snippets (reference file paths instead).

Facts with zero churn risk — an explicit user correction or stated preference — may additionally be written straight to the memory graph (memory_store_resource / memory_store_concept + memory_link) at the moment they happen. Everything else goes through distillation.

## Lifecycle
- Maximum 5 active context files in `~/.claude/context/`
- Never delete context files — archive to `~/.claude/context/archive/`
- When creating a new file would exceed the limit, archive the oldest `distilled: true` file
- Never archive a `distilled: false` file; if 3+ undistilled files have accumulated, suggest the user run `/memory-graph:distill`
