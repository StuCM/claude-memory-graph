# Task: ceist — ground phrases to node groups (tile-scoped conditions)

Status: planned · Owner: Stuart · Created: 2026-11-04 · Size: L

## Goal

Questions like "monuments damaged in a fire", "also known as Victoria Dock",
"designed by Ada" each describe **one tile**: one event or fact held in one
nodegroup (a phase with its type, cause and dates; a name with its use type; an
actor with a role). Ground such phrases to a **nodegroup first**, then fill the
group's nodes from the rest of the phrase, and emit **one tile-scoped
condition**. This replaces the one special case that exists today
(`LinkTo.qualifier`) with a general mechanism. It also gives chained queries a
clean unit: each hop is a link plus the tile conditions around it.

No LLM at query time. Groups, their phrasings and the roles of their nodes are
built offline from the schema only (see [[ceist-vocab-pipeline]]).

## Findings that motivate it (checked 2026-11-04)

Run against the test fixture (`tests/arches_fixture.py`), current `main`:

| Question | Result |
|---|---|
| "find all buildings that were damaged in a fire" | refused: coverage 50% < 60% (safe) |
| "find all **listed** buildings that were damaged in a fire" | **answered with every listed building**: coverage hits 60%, "damaged in a fire" dropped with no note |

1. **Silent drop.** `COVERAGE_MIN` is the only guard. One grounded word lifts
   coverage over the line, and the phrase that actually constrains the answer
   is discarded. The answer is wider than asked, and wrong.
2. **Qualified entries on non-link nodes are discarded.** `ArchesVocabulary._absorb`
   sends every qualified bundle entry to `_qualified_relations`, which drops any
   entry whose node isn't a link (it only increments `skipped_qualified`). So the
   HER entry `"burnt down" / "demolished" → construction_phase_start_date +
   construction_phase_type = Destruction` never becomes a date form. Shown with a
   one-entry bundle: `skipped_qualified: 1`, date forms unchanged.
3. **Names are a single string from the Arches descriptor.** `_entity` reads
   `descriptors[lang].name` (falling back to `resourceinstance.name`, then the
   UUID). The node is chosen by the graph's descriptor function in Arches, not
   by ceist, and alternative names are never indexed.
4. **The HER bundle loses name types.** Monument maps "alternative name" /
   "former name" to `monument_name` with no qualifier. Organization maps them
   to `organization_name_use_type` as a plain property, which constrains
   nothing.

## Design

### 0. Never drop a constraining phrase without saying so (do first, ships alone)

If a content phrase is left unplaced after grounding, either refuse ("couldn't
place 'damaged in a fire'") or answer with an explicit relaxation note. The
coverage threshold alone must not decide. Applies to every backend.

### 1. `OnTile` in the plan

```python
@dataclass
class OnTile:
    group: str                      # nodegroup alias (what a backend scopes by)
    conditions: list[Condition]     # all must hold on ONE tile of that group
```

- `LinkTo(…, qualifier=HasValue)` becomes `OnTile(g, [LinkTo(…), HasValue(…)])`.
  Keep `qualifier` as a compatibility shim until readback and narration move over.
- Compile: Rós Madair → `{"on_tile": [...]}` (`rosmadair.py:95`). Arches Search →
  a `scope: "TILE"` group (`arches_search.py:126`). alizarin → per-entry
  evaluation (generalise `_entry_holds`).
- **Nested nodegroups:** HER groups have child groups (a phase with child
  actor or cause tiles). "Same tile" must mean the tile plus its
  ancestor/descendant tiles. Check what `on_tile` and the TILE scope do with
  parent/child tiles **before** relying on either. alizarin's `Tiles` must
  record `parenttile_id`.
- Readback (`read_back`) and `narrate` learn `OnTile` ("whose construction phase
  is Destruction, caused by Fire, after 1950").

### 2. Group-level vocabulary

The bundle gains `groups` per model (format bump to `ceist.vocab/2`; v1 still loads):

```json
"groups": {
  "construction_phase": {
    "phrases": ["damaged", "burnt down", "fire damage", "altered", "rebuilt"],
    "nodes": {
      "construction_phase_type":       {"role": "type"},
      "construction_phase_cause":      {"role": "cause"},
      "construction_phase_start_date": {"role": "date", "end_node": "construction_phase_end_date"},
      "construction_phase_actor":      {"role": "actor"}
    },
    "combos": [
      {"phrases": ["burnt down", "destroyed by fire"],
       "set": {"construction_phase_type": "Destruction", "construction_phase_cause": "Fire"}},
      {"phrases": ["damaged"], "set": {"construction_phase_type": "Damage"}}
    ],
    "answers": {"when": "construction_phase_start_date", "who": "construction_phase_actor"}
  }
}
```

(Node names are illustrative. Check them against the real HER descriptions.)
Existing qualified entries become `combos`. `validate` checks every node, value
and role against the description.

### 3. Grounding: phrase → group → nodes → `OnTile`

1. The grounder segments the question into slots, as now. Each leftover chunk
   is a candidate group phrase.
2. Match the chunk to groups (exact, then vectors over the whole chunk),
   restricted to the subject's model. Keep the **top 2–3** with scores.
3. For each candidate group, fill its nodes from the remaining words: values
   from that node's own collection only (so "fire" can't land on "Fire Station"
   in monument types), dates to the group's date role, "by X" to its actor
   link, names to its name node.
4. **Accept a group only if it absorbs the chunk.** If no candidate places every
   content word, offer "did you mean" or refuse. Never drop a word (step 0).
5. A date or anchor in the same clause attaches to the group it sits with
   ("damaged by fire **after 1950**" → the phase's date, not a model-wide date).

### 4. Typed names (a group like any other)

```toml
[vocabulary.names.Monument]
node = "monument_name"
type = "monument_name_use_type"
primary = ["Primary"]          # labels: unverified against HER's collection
```

- Index **every** name tile on the entity with its type:
  `extra["names"] = [(text, type), …]`. The display name is the primary-typed
  name, then the descriptor, then the first name. Models without config keep the
  descriptor behaviour. Warn at load when a model's entities fall back to UUIDs.
- **Plain name query** ("listed buildings on Victoria Dock"): match any name.
  When the match came through an alternative name, flag it in the answer:
  "Victoria Dock → Monument 'Leeds Dock' (alternative name)". Primary names
  rank slightly above alternatives, so a name shared across records resolves
  to the record where it is primary.
- **Typed name query** ("also known as X", "formerly called X", "alternative
  name X"): **only** tiles whose type is Alternative (or narrower) match.
  Untyped name tiles do not match. An exact or near-exact name resolves at
  grounding time against the index, to a set of ids, so it works on all three
  backends unchanged. Partial text ("alternative name contains 'Dock'") is
  `OnTile(name_group, [Contains(name), HasValue(type, Alternative)])`: alizarin
  only, and the other backends raise `Unsupported` until they can scope text to
  a tile.

### 5. Chained queries

Each hop of a chain ("monuments designed by architects who worked for the
council and were damaged by fire") is a `LinkTo` whose target is a sub-`Plan`.
Tile conditions attach to the hop they sit in. The grounder must keep
group candidates per hop and not merge them across the whole question.

## Order

1. Step 0 (silent drop) with tests. Small, and it fixes wrong answers today.
2. `OnTile` in the plan plus the compilers and alizarin; move `LinkTo.qualifier` onto it.
   Check backend behaviour with parent/child tiles.
3. `ceist.vocab/2` groups and combos; migrate existing qualified entries.
4. Grounder: group candidates, node filling, the absorb gate.
5. Typed names.
6. Chains: group candidates per hop.

## Depends

[[ceist-vocab-pipeline]] produces the group vocabulary (step 3 can be hand-written
for the fixture first). The HER model descriptions (`ceist vocab describe`
output) are needed to check group structures. They aren't in the repo.

## Test

- Fixture gains a phase group (type, cause, dates; one child tile) and a name group
  (name and use type, several tiles per record).
- "listed buildings damaged in a fire" no longer returns every listed building.
- "burnt down before 1950" → `OnTile(phase, [type=Destruction, cause=Fire, date<1950])`,
  compiled identically by all three backends (where supported) and read back.
- A record whose Destruction phase and Fire cause are on **different** tiles does not match.
- Plain name query via an alternative name returns the record, flagged. "Also known as"
  excludes records whose only match is a primary or untyped name.
- End-to-end eval cases (question → expected conditions, not just phrase → node):
  fire damage, alternative names, multi-group and chained questions, with
  right/dangerous measured before and after. The `cases.json` format today is
  phrase-level and needs an extension.
