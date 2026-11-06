---
id: 011
slug: vocab-layers
status: done
branch: crew/011-vocab-layers
model: opus
env: laptop
work: vocab-layers
files:
  - packages/ceist/
  - vocabularies/
gate: pass
gateSha: 20727b585c7e2ec0930d90f308df761c6d1097fe
gateAt: 2026-11-06T15:34:23.882Z
rounds: 1
---

# Vocabularies in two layers: a base per graph, and a client layer on top

## Goal
Ceist loads a vocabulary as a **base layer per graph** plus an optional **client layer**:
- **The base layer** lives in its own place, keyed by graph id: `vocabularies/base/<graph-id>/` at the repo root. It holds what comes from the graph or schema alone: type words, field and link phrasings, nodegroup groups.
- **The client layer** is a folder the site owns, for example `starches-demo/ask/vocab/`. It holds what comes from that client: value-label variants and synonyms, value combos (such as the period combos), record-name aliases, and the client's own phrasings.

Ceist merges the two. The client layer may **add** phrases and entries. Anything that would change or remove a base phrase is listed in a merge report and is never applied silently. The demo then runs on the HER base (re-keyed by graph id) plus a client layer that holds what `ask.py` hard-codes today (`EXTRA_TYPE_WORDS`, `RELATION_FORMS`, `PERIODS`/`GROUPS` combos).

## Why now
Stu, 2026-11-06: "split vocab to what is very much the graph or schema and what is additional vocab based on the data and values. This means we could invest larger time on building the base graph vocab and a smaller time adjusting for client data". On where the base lives: "in its own place keyed by graph id".

## Background
- **Today:**
  - A bundle is per model, `ceist.vocab/2`, written per nodegroup with a `manifest.json` (task 003, `slicing.py`, `bundle.py`).
  - The HER bundle is in `packages/ceist/bench/her/vocab/*.json`, keyed by model *name*.
  - The demo re-keys it to its own model names in `starches-demo/ask/ask.py` `her_bundle()`, because its graphs are the HER graphs renamed (`HER_NAMES`). Keying by graph id makes renames free.
- **The demo graphs keep HER's graph ids?** Check this first: compare `starches-demo/prebuild/graphs/resource_models/*.json` graphids with the HER graphs the bench uses. If they differ, write down the mapping you need and how the demo supplies it, in one place.
- **Keep the existing loaders working.** Today's single bundle and a vocab folder load as before; layering is opt-in.
- **Move the HER bundle's schema-only content into `vocabularies/base/<graph-id>/`.** Keep `bench/her/vocab` as it is (the HER gate depends on it) unless you can point the gate at the new place with no plan diffs.
- **Do not edit `starches-demo`.** In Worker notes, give the exact `ask.py` change for the orchestrator to apply: load the base by graph id plus `ask/vocab/` as the client layer, and drop the hard-coded dicts. Also give the client-layer files themselves, written under `<worktree>/bench-demo-client/` (or a path you choose inside `files:`), for the orchestrator to copy.

## Out of scope
The pipeline (task 012) and the refine loop (013).

## Definition of done
- [ ] Unit tests:
  - a base plus a client layer merge;
  - a client phrase that is added appears;
  - a client entry that would override a base phrase is reported and not applied;
  - loading by graph id finds the base whatever the model is named.
- [ ] With the patched `ask.py` (applied in a temp copy of the demo's `ask/`, not in place), the question bank exits 0 and its counts are unchanged.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- `packages/ceist/src/ceist/bundle.py`: `layered(graphs, base_dir, client_dir)` builds a bundle from `base_dir/<graph id>/` (split by nodegroup) plus a client layer (split layout keyed by model name; its manifest's `base` maps a model to the base graph id). The client only adds; a phrase, group role/answer or type word that would change the base's is left out and returned in the merge report. `_model_dir` factored out of `read_vocab` (it also skips a manifest.json inside a model folder). Existing loaders unchanged.
- `packages/ceist/tests/test_layers.py`: the four DoD cases, end to end through `interpret`.
- `vocabularies/base/<HER graph id>/`: the 16 HER models' split vocab (`bench/her/vocab/<Model>/`) plus a per-graph manifest.json (name, nodegroups, hashes). `bench/her/vocab` and the HER gate untouched.
- **Spec gap, decided:** the base drops "monuments" from 7 link entries (it is the Monument type's own word). The demo's `her_bundle()` already did this; a client layer cannot remove a base phrase, and without the drop 9 bank questions regress.
- **Graph ids differ:** demo graphs are uuid5-style (e.g. Monument 062f4e2c-…) vs HER (076f9381-…). The mapping lives in one place: the client layer's `manifest.json`, `models.<name>.base`.
- **Client layer for the demo:** `packages/ceist/bench/demo/vocab/` -> copy to `starches-demo/ask/vocab/`. Holds EXTRA_TYPE_WORDS + place/places (manifest type_words), RELATION_FORMS (link entries per model with that alias), GROUPS period combos (Monument/construction_phases.json). Value synonyms and record-name aliases have no loader hook today and the demo hard-codes none, so not added.
- Merge report on the demo, one line: `Monument: 'features' means component_type in the base, actor in the client; not applied` (today relation_forms added it; the bank is unchanged without it).
- **Question bank** (patched ask.py in /home/stuart/.cache/tmp-011/demo/ask, demo venv python, PYTHONPATH=worktree src, CEIST_BASE=worktree vocabularies/base): before and after identical, exit 0: answer/right 58, answer/refused 1, refuse/right 6, refuse/wrong 1, answer-later/wrong 2, answer-later/refused-should-answer 19. questions.json unchanged (nothing fixed).
- **HER plans / memory_ask:** no grounding, plan or ArchesVocabulary change, so no plan diffs expected; `tests/test_planner.py` passes in the gate. `bench/her_plans.py` not run (needs an arches-her clone). No change for `memory_ask`.
- **ask.py patch** (also at /home/stuart/.cache/tmp-011/ask.patch). Default BASE follows the existing HER default path; set CEIST_BASE to override:

```diff
--- ask.orig.py	2026-11-06 15:28:47.719095880 +0000
+++ ask.py	2026-11-06 15:31:51.545029496 +0000
@@ -10,8 +10,8 @@
 
 import ros_madair
 from ceist import interpret, narrate
-from ceist.arches import ArchesVocabulary
-from ceist.bundle import kind_of
+from ceist.arches import ArchesVocabulary, graph_doc
+from ceist.bundle import layered
 from ceist.config import chain, load
 from ceist.readback import check
 from ceist.rosmadair import Unsupported, _scoped_by_model, compile_plan, linked_from, read_back
@@ -22,43 +22,9 @@
 SNAPSHOT = str(HERE / "snapshot")
 ORIGINS = {"http://localhost:1313", "http://127.0.0.1:1313"}
 CAP = 200
-# PROVENANCE.json: the demo's models are HER models under new names
-# Phrasings this dataset needs beyond the HER bundle (found by trying paraphrases)
-EXTRA_TYPE_WORDS = {"story": "Tale", "stories": "Tale"}
-RELATION_FORMS = {"parent_story": ["come from", "comes from", "in"],
-                  "named_location": ["in"],
-                  "actor": ["tell of", "tells of", "involve", "involves", "feature", "features"]}
-HER_NAMES = {"Monument": "Monument", "Place": "Site", "Person": "Figure",
-             "Organization": "Group", "Heritage Story": "Tale", "Artefact": "Object"}
-# The NI SMR periods (myths-arches PERIODS). A period word names a monument's construction
-# phase and takes the type after it onto the same tile: "medieval raths" is one phase, Medieval
-# and Rath. Needs Ceist with group grounding; one without it ignores "groups".
-PERIODS = ["Uncertain", "Early Christian", "Prehistoric", "Post-Medieval", "Modern", "Bronze Age", "Medieval",
-           "Neolithic", "Medieval/Late Medieval", "Late Medieval", "Early Medieval", "Mesolithic",
-           "Neolithic/Bronze Age", "Iron Age", "Early Christian/Medieval", "Late Bronze Age", "Early Bronze Age",
-           "Middle Bronze Age", "Mesolithic/Neolithic", "Late Neolithic", "Early Neolithic",
-           "Late Bronze Age/Iron Age", "12th Century", "13th Century", "14th Century", "15th Century",
-           "16th Century", "17th Century", "18th Century", "18th/19th Century", "19th Century", "20th Century"]
-GROUPS = {"Monument": {"construction_phases": {
-    "phrases": [],
-    "nodes": {"monument_type": {"role": "type"}, "cultural_period": {"role": "other"}},
-    "combos": [{"phrases": [p.lower()], "set": {"cultural_period": p}} for p in PERIODS]}}}
-
-
-def her_bundle(graphs_dir: Path) -> dict:
-    """The HER vocabulary bundle, re-keyed to the demo's model names."""
-    models = {}
-    for p in graphs_dir.glob("*.json"):
-        doc = json.loads(p.read_text())
-        g = doc["graph"][0] if "graph" in doc else doc
-        models[g["name"]["en"]] = {n["alias"]: {"kind": kind_of(n)} for n in g["nodes"] if n.get("alias")}
-    out = {}
-    for her, demo in HER_NAMES.items():
-        entries = json.loads((HER / "vocab" / f"{her}.json").read_text())["entries"]
-        # "monuments" names the Monument type, not the HER link to one: "which scheduled monuments …"
-        entries = [dict(e, phrases=[x for x in e["phrases"] if x != "monuments"]) for e in entries]
-        out[demo] = {"nodes": models[demo], "entries": entries, "groups": GROUPS.get(demo, {})}
-    return {"format": "ceist.vocab/1", "models": out}
+# The HER base vocabulary, keyed by HER graph id; vocab/ is this site's layer on top
+# (its manifest maps each model to its HER graph, as the models are HER models renamed)
+BASE = Path(os.environ.get("CEIST_BASE", HERE / "../../claude-memory-graph-foundation/vocabularies/base"))
 
 
 def record_index(defs: Path) -> dict[str, tuple[str, str]]:
@@ -171,9 +137,11 @@
 
 def startup():
     t = time.time()
-    vocab = ArchesVocabulary.from_data_dir(HERE / "data", bundle=her_bundle(HERE / "data" / "graphs"),
-                                           extra_type_words={"place": "Site", "places": "Site", **EXTRA_TYPE_WORDS},
-                                           relation_forms=RELATION_FORMS)
+    graphs = [graph_doc(p) for p in sorted((HERE / "data" / "graphs").glob("*.json"))]
+    bundle, report = layered(graphs, BASE, HERE / "vocab")
+    for line in report:
+        print(f"vocab: {line}", file=sys.stderr)
+    vocab = ArchesVocabulary.from_data_dir(HERE / "data", bundle=bundle)
     # bge-small only settles leftover words; on the demo questions it changes no answer, and it supplies "did you mean"
     cfg = load(HER / "ceist-bge.toml")
     records = record_index(SITE / "static" / "definitions" / "business_data")
```

## Graph writes proposed
- Decision: Ceist vocabularies are layered: a base per graph id under `vocabularies/base/<graph id>/` (schema only) and a site-owned client layer that may only add; conflicts go to a merge report, never applied. A renamed or re-id'd site maps its models to base graph ids in the client manifest (`base`).
- Pattern: a link phrase equal to a model's own type word ("monuments") shadows the type in grounding; keep it out of the base.

## Review rounds
- Round 1: PASS. Minor, not acted on: a client phrase with the same meaning as the base is appended again (harmless); a type word claimed by two base graphs is won by the later one silently (no HER base has type words).
