# Rós Madair: workarounds in ceist

This file lists what ceist works around, or refuses, because of how Rós Madair behaves today. Each entry can be raised as an issue on Rós Madair. Rós Madair itself has not been changed.

Each entry says what we saw, how it was confirmed, what ceist does about it, and what would let ceist drop that workaround.

The tests ran against Rós Madair at the version cloned on 2026-10-27, with Python bindings `ros_madair` 0.1.0a30 and `ros-madair-emit` built from the same checkout. The fixture is `packages/ceist/tests/arches_fixture.py`: 2 Sites, 2 People and 3 Buildings.

## 1. A query without a model-tied filter is not limited to its `model` (bug)

**Seen:** these four queries each return every record in the snapshot (7 resources: Sites, People and Buildings), not the 3 Buildings:
- `{"model": "<Building graph id>", "measures": ["select_ids"]}`
- the same query with `"where": {"all": []}`
- both of those with `count_records`

So "how many buildings are there?" answers 7.

**How it was confirmed:** run through the Python bindings (`Reader.resolve` and `Reader.count`) on the fixture snapshot.

**Also affected (from reading the source, not tested):** `backlink`. In `ros-madair-compile` the `Expr::Backlink` SQL is `SELECT DISTINCT src_resource … FROM edges_rev WHERE target_resource = …`, with no model condition. So `{"model": Building, "where": {"backlink": …}}` can return a Site or a Person that links to the target.

**What ceist does:** in `ceist.rosmadair.ask`, when no conjunct names a node of the model (no filter, or a `backlink` only), it resolves the IDs and keeps only the model's records, using the IDs from the vocabulary's business data. For counts it does the same instead of using `count_records`.

**To drop it:** scope every query to `model`, including a missing or vacuous `where` and `backlink`.

## 2. `not` over a link is refused (limitation)

**Seen:** `{"not": {"has_link": …}}` is rejected with `NegatedCoarsePredicate`, because `has_link` compiles chunk-coarse. Yet `Reader.resolve` returns exact results for a positive `has_link` (the end-to-end tests check names exactly).

**What ceist does:** at the top level, "buildings not designed by Ada" becomes two queries: all Buildings (plus any other conditions), minus the Buildings whose `architect` links to Ada. A negated link inside a hop ("sites with buildings not designed by Ada") is refused by name, because it can't be subtracted at the top level.

**To drop it:** exact negation of `has_link` and `on_link`, for example by verifying on hydrated tiles as the positive case appears to do, or a `not_link` predicate.

## 3. No way to walk a link backwards along a named path (limitation)

**Seen:** the IR walks links forward only (`has_link` and `on_link` from the model that holds the node). `backlink` goes backwards but has no `path`, and isn't scoped to a model (see 1).

**What ceist does:** it refuses by name questions like "which sites have buildings designed by Ada?". That needs Sites that a Building's `site` node points at, where the Building matches a sub-filter. The refusal suggests asking from the other side. ceist's Alizarin and Arches Search outputs both answer it.

**To drop it:** an inverse link predicate, e.g. `{"linked_from": {"model", "path", "where"}}` meaning "records that a `model` record's `path` points at, where that record matches `where`". This could reuse the reverse edge index that `backlink` already uses.

## 4. `quantize_date` isn't exposed to Python (drift risk)

**Seen:** `range` takes endpoints that are already quantized (days since 1970, from Alizarin's `quantize_date`), but neither the `ros_madair` nor the `alizarin` Python package exposes that function.

**What ceist does:** it mirrors the function in `ceist.dates.days()`, using proleptic Gregorian days since 1970-01-01, the same as Hinnant's `days_from_civil`. The end-to-end date tests against a real snapshot pass, so the two currently agree. But if the emitter's encoding ever changes, ceist's date queries would silently miss their boundaries.

**To drop it:** expose `quantize_date` (and ideally `explain`) in the Python bindings.

## 5. `range` needs both ends (minor)

**Seen:** `Range { path, lo: i64, hi: i64 }` has no open end.

**What ceist does:** "before 1900" sends `lo = -1_000_000_000` (and "after" sends `hi = +1_000_000_000`) as stand-ins for "unbounded". Read-back treats anything beyond ±10⁹ days as open.

**To drop it:** make `lo` and `hi` optional.

## 6. The snapshot doesn't carry the schema (minor)

**Seen:** `Reader.resolve` and `Reader.count` need a `ros_madair.Graph` built from the graph JSON, which the snapshot directory doesn't include.

**What ceist does:** it builds each `Graph` from the vocabulary's data_dir (`vocab.model(type).doc`). So answering a question needs both the snapshot and the data_dir it was emitted from.

**To drop it:** have the emitter write the graphs into the snapshot, or have `Reader` load them.

## Not workarounds: things ceist refuses because the substrate doesn't index them

- Free-text conditions (the substrate indexes concepts, ranges, geometry and links, not text).
- "Most recent" (there's no update-time column).

These are refused by name, and the runner moves on to a looser version of the question or says what it couldn't do.
