---
name: distill
description: Distill conversation context files into the long-term memory graph. Use when the user says "distill", "distill context", "save this to memory", or when 3+ undistilled context files have accumulated.
---

# Distill Conversation Context into the Memory Graph

Spawn the `memory-graph:distiller` agent with the Agent tool, in the foreground. Pass it the skill's ARGUMENTS verbatim as the files to process, or "all undistilled context files" when there are none.

Relay its report to the user in a few lines. Do not repeat the graph writes yourself: running them in the agent is what keeps their tool output out of this conversation's context.
