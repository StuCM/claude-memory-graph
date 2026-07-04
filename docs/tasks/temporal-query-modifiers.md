# Task: temporal query modifiers

Status: **planned** · Owner: Stuart · Created: 2026-07-04 · Size: S

## Goal

Tense words in the planner's modifier lexicon compile to valid-time filters:
*currently* → open edges (default) · *used to / former* → closed `worldChange` edges ·
*last year / before X* → valid-time overlap FILTER. "Who used to work on quartz?"
becomes mechanically answerable.

## Depends

[[query-planner-v0]] · [[bitemporal-links]] (the timestamps must exist first).

## Test

Golden questions over a fixture graph with one closed and one open `worksOn` edge.
