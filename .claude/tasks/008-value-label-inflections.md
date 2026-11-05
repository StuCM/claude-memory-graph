---
id: 008
slug: value-label-inflections
status: draft
---

# Values match plural and simple inflected forms of their labels

Stub, 2026-11-05: controlled values match exact labels only, so "raths" misses "Rath" unless the list carries a plural altLabel. Add the plural and simple inflected forms at load time, as type words already get (`plurals()`), with the word-roots option. Guard against clashes such as a value "Feature" swallowing the verb "feature". Possibly the grounder should prefer a relation or verb reading when a value word sits where a verb belongs. Check on HER (`bench/her_plans.py`) and the demo.
