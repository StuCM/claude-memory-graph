---
title: claude-memory-graph
description: Persistent, structured long-term memory for Claude Code — an RDF knowledge graph with ambient recall and mechanical capture.
---

# claude-memory-graph

A knowledge-graph memory for Claude Code. Facts are stored as typed resources
(Project, Decision, Pattern, Person, …) linked across projects, so recall can follow
chains instead of grepping notes. A plugin mod makes it ambient: relevant memories are
injected as you prompt, and each session keeps a context log that is distilled into
the graph without an LLM.

## Start here

| If you want to… | Read |
|---|---|
| install it and see it working | the [README](https://github.com/StuCM/claude-memory-graph#install) |
| know what it's doing at runtime, debug it, tune it | [Handbook](HANDBOOK.md) |
| read the injection log and act on misses | [Tuning](TUNING.md) |
| let a colleague query a project, or reach your memory remotely | [Remote access](REMOTE.md) |
| find out whether the graph beats Claude's built-in memory for you | [The 10-question comparison](COMPARE.md) |
| look up a term | [Glossary](GLOSSARY.md) |

## How it works

The system has three subsystems, each with its own design doc:

- **Retrieval** — deciding *what* to put in front of the model:
  [Retrieval](RETRIEVAL.md), [Query planning](QUERY-PLANNING.md),
  [Context window](CONTEXT-WINDOW.md).
- **Creation** — deciding *what's worth keeping*:
  [Context creation](CONTEXT-CREATION.md) (the session log) and
  [Distill creation](DISTILL-CREATION.md) (log → graph).
- **Orchestration** — making both happen reliably, without the model having to
  remember: [Orchestration](ORCHESTRATION.md).

[System](SYSTEM.md) ties them together (requirements, tests, technologies) and
[Architecture](ARCHITECTURE.md) has the diagrams.

## Further out

Design explorations, not built: [Roadmap](future/ROADMAP.md),
[team sharing](future/SHARING.md), [federation](future/FEDERATION.md),
[a code graph](future/CODE-GRAPH.md). Superseded designs live in
[archive](archive/CAPTURE.md).
