# CRM-first: which graph- and client-layer phrasings the ontology layer can carry

Read-only check, 2026-11-09. No LLM run. Scripts: `crmfirst.py` (classify) and `report.py` (tables) in the session
scratchpad (`/tmp/claude-1000/-home-stuart-git-fat-arches-quartz-starches-starches-next/8d382a9a-c222-45bf-b7c3-0df02ffd80af/scratchpad/`).
Input for task 053.

Graph sets, loaded as `bench/ontology/run.py:27-46` (`graph_docs`) loads them:

| set | models | role here |
|---|---|---|
| HER (`~/.cache/tmp-003/arches-her/…/resource_models`) | 16 | the graphs behind `vocabularies/base/<graph id>/` (all 16 base ids are HER ids) |
| demo (`starches-demo/ask/data/graphs`) | 6 | the client layer's graphs (`bench/demo/vocab/manifest.json` maps them to base ids) |
| Catalina (`catalina-graphs/output/graphs/resource_models`) | 23 | no vocabulary of its own; uniqueness test and gain |
| lingo (`arches-lingo/…/resource_models`) | 6 | no vocabulary of its own; uniqueness test and gain |

A **phrasing** is one string in a base or client group file: an entry phrase (`entries[].phrases`), a nodegroup phrase
(`group.phrases`) or a combo phrase (`group.combos[].phrases`). Base: 7,505 (6,714 entry, 789 combo, 2 group). Client: 1,512, read from the working tree, where
`bench/demo/vocab/Monument/construction_phases.json` is modified and `designation_and_protection_assignment.json` and
`use_phase.json` are untracked; they hold nearly all of the 1,487 client combos.

## 1. How the layers key a phrasing (code read)

| what | where | effect for this check |
|---|---|---|
| a node's CRM chain | `src/ceist/crm.py:150` `chains` | `[root class, prop, class, …, prop, node class]`, `-` for a missing class or property |
| which nodes the ontology layer phrases | `src/ceist/crm.py:177-213` `ontology_entries` | links, dates and **controlled** properties only; a plain field (string, number, geojson) is skipped at `crm.py:190` |
| a date's key | `src/ceist/crm.py:174, 192-196` | only a P82a or P82 end of an E52 time-span; the key is the event's path down to P4 (`… E12 P4`) |
| path match | `src/ceist/crm.py:216-221` `_ends_with` | the chain without the node class, or with it, **ends with** the path; `^` anchors at the root |
| the key a proposal is written on | `src/ceist/ontology_vocab.py:99` `path_of` | up to 3 tokens ending at the property into the node |
| applying the layer | `src/ceist/bundle.py:234-279` `layered`, `:282` `_add_ontology` | ontology under the base; **a phrase that fits two nodes of one model is dropped**; a base phrase wins |
| base layer | `src/ceist/bundle.py:224` `_model_dir`, `:325` `_fit` | entries keyed by node alias; combos by nodegroup and value labels |
| the clash test | `src/ceist/ontology_vocab.py:376-392` `review` | generic (`generic.json`), shared by sibling paths (`_share`, `:331`), already on another path that it does not extend (`_extends`, `:312`), bare noun on a non-unique path (`_unique_in_models`, `:324`) |

## 2. Counts

### Per layer

| layer | promotable | promotable longer path | ambiguous path | non-CRM | site-specific | clash | already in ontology | total |
|---|---|---|---|---|---|---|---|---|
| base (16 HER graphs) | 1,272 | 1,122 | 3,360 | 54 | 789 | 770 | 138 | 7,505 |
| client (demo) | 1 | 0 | 18 | 0 | 1,489 | 3 | 1 | 1,512 |

Two extra columns beyond the five asked for: **clash** (single-meaning, but the review clash test rejects the phrase) and
**already in ontology** (the node already gets that phrase from `phrases.json` today; the base copy is redundant).
Client: `county` and `counties` (`bench/demo/vocab/Monument/named_locations.json:8-9`) come out promotable on
`P89 E53 P89i` mechanically, and are moved to site-specific by hand: a local administrative term.

### Base layer per graph

| graph | promotable | promotable longer path | ambiguous path | non-CRM | site-specific | clash | already in ontology | total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Activity | 58 | 55 | 226 | 0 | 92 | 19 | 9 | 459 |
| Application Area | 44 | 34 | 184 | 0 | 0 | 30 | 0 | 292 |
| Area | 116 | 94 | 283 | 0 | 121 | 97 | 20 | 731 |
| Artefact | 110 | 97 | 228 | 0 | 35 | 88 | 29 | 587 |
| Bibliographic Source | 24 | 32 | 122 | 0 | 0 | 23 | 1 | 202 |
| Consultation | 99 | 76 | 330 | 11 | 32 | 33 | 1 | 582 |
| Digital Object | 31 | 17 | 80 | 0 | 0 | 41 | 1 | 170 |
| Heritage Story | 50 | 93 | 142 | 0 | 61 | 48 | 6 | 400 |
| Historic Aircraft | 176 | 122 | 329 | 12 | 131 | 87 | 11 | 868 |
| Historic Landscape Characterization | 68 | 57 | 189 | 0 | 0 | 49 | 3 | 366 |
| Maritime Vessel | 190 | 117 | 307 | 11 | 110 | 50 | 15 | 800 |
| Monument | 183 | 162 | 330 | 2 | 179 | 91 | 25 | 972 |
| Organization | 41 | 39 | 122 | 9 | 0 | 41 | 9 | 261 |
| Period | 28 | 22 | 116 | 9 | 0 | 22 | 1 | 198 |
| Person | 41 | 82 | 211 | 0 | 28 | 43 | 7 | 412 |
| Place | 13 | 23 | 161 | 0 | 0 | 8 | 0 | 205 |

### Base layer per node kind

`field` = a plain property that `crm.py:190` skips today; `concept` = a controlled property it carries.

| class | link | date | concept | field | combo/group |
| --- | --- | --- | --- | --- | --- |
| promotable | 427 | 196 | 426 | 223 | 0 |
| promotable longer path | 150 | 97 | 290 | 585 | 0 |
| ambiguous path | 230 | 574 | 975 | 1581 | 0 |
| non-CRM | 0 | 52 | 0 | 0 | 2 |
| site-specific | 0 | 0 | 0 | 0 | 789 |
| clash | 289 | 79 | 135 | 267 | 0 |
| already in ontology | 82 | 37 | 19 | 0 | 0 |

### Sub-reasons

| bucket | count | note |
|---|---|---|
| ambiguous: the source model itself has ≥2 nodes on the whole chain (with node class) | 2,843 | no CRM path can split them, e.g. 9 `P106 E41 P3` address parts in Monument |
| ambiguous: unique in HER/demo, 2+ nodes in another set | 535 | of which 52 only because of Catalina (Person `date_of_birth`/`date_of_death`, `name` on Event/Heritage Story, Artefact `monument_area_or_artefact`) |
| ambiguous: cross-graph split (the path's source nodes in different graphs share no phrase and no alias) | 353 on 11 paths | see §5; 3 of the 11 look like one meaning |
| non-CRM: date on a P82b, P81b or P3 end with no P82a/P82 begin | 52 | Maritime Vessel `date_of_arrival`, `expected_date_of_arrival`; Consultation `completion_date`; Historic Aircraft `date_of_loss`; Organization `end_date`; Period `earliest_possible_end_date`. CRM, but `crm.py:174` keys only P82a/P82 |
| non-CRM: nodegroup phrase | 2 | the ontology layer has no group kind |
| non-CRM: custom property (ZP\*, MP1, P0\*) | **0** | HER uses standard CRM throughout; the custom properties sit in Catalina and lingo, which have no vocabulary |
| site-specific: value-qualified combo (base) | 789 | `role_type: Architect`, `construction_phase_type: Alteration`, …; the value labels are HER thesaurus terms |
| clash: sibling promotion (same phrase promoted on a path that neither extends) | 657 | `description`, `caption`, `notes` on several `… E33 P3` paths; the widest path keeps it |
| clash: on an existing ontology path | 84 | e.g. `contains` already on `P89i` |
| clash: generic.json | 32 | `about` 14, `category`, `use`, `type`, `in` |
| promotable (both kinds) that are plain fields | 808 | need `ontology_entries` to admit non-controlled properties (`crm.py:190`) and `questions.templated` to template them |
| promotable whose path is the whole chain from the root | 335 | HER-shaped; reach only HER, the demo and Catalina's HER clones |
| promotable with the same phrase (near form) on the same path in another graph | 1,326 of 2,394 | the strong evidence |
| distinct promotable (path, phrase) | 1,409 on 217 paths | reaching 1,241 nodes across the four sets |

## 3. Top 20 promotable paths by node reach

Reach = nodes the path reaches across all four sets (at most one per model by construction). Graphs = models per set.
Agreeing = phrasings whose phrase (or near form) sits on the same path in another graph's layer.

| path | kind | class | reach | her/demo/cat/lingo | phrasings | agreeing | example phrases | from |
|---|---|---|---|---|---|---|---|---|
| `P67i D1 P2` | concept | promotable | 41 | 16/5/20/0 | 100 | 100 | validation, validation status, record checked, needs work, quality check | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/audit_metadata.json:68 |
| `D1 P67i E33 P3` | field | longer path | 38 | 16/5/17/0 | 64 | 64 | audit note, audit notes, record notes, editorial note, editorial notes | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/audit_metadata.json:58 |
| `P1 E42 P71i` | concept | promotable | 36 | 14/4/18/0 | 53 | 53 | cross reference source, which database, reference source, external database, source of external reference | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/external_cross_references.json:20 |
| `P1 E42 P67i E73 P3` | field | longer path | 33 | 14/4/15/0 | 29 | 29 | cross reference note, cross reference notes, external reference note, note on cross reference | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/external_cross_references.json:30 |
| `P94i D10 P33` | concept | promotable | 28 | 12/3/13/0 | 46 | 46 | coordinate system, projection, spatial reference system, crs, osgb36 | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/coordinate_system.json:7 |
| `P67 D1 P1 E41 P3` | field | longer path | 28 | 12/3/13/0 | 33 | 33 | base map, current base map, base mapping, background map, which base map | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/current_base_map.json:7 |
| `SP6 P129i E33 P3` | field | longer path | 28 | 12/3/13/0 | 44 | 44 | spatial notes, spatial metadata, geometry notes, mapping notes | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/spatial_metadata_descriptions.json:7 |
| `SP6 P140i E13 P4` | date | longer path | 28 | 12/3/13/0 | 53 | 53 | spatial record authorized, date of authorization, spatial record authorised, date of authorisation, when was the mapping authorised | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/spatial_record_authorization.json:7 |
| `SP6 P140i E13 P2` | concept | longer path | 28 | 12/3/13/0 | 39 | 39 | authorization status, authorisation status, spatial authorization, mapping approved, awaiting authorization | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/spatial_record_authorization.json:19 |
| `E13 P14 E21 P1 E41 P3` | field | longer path | 28 | 12/3/13/0 | 39 | 39 | authorised by, authorized by, authorizer, spatial record authorised by, authoriser | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/spatial_record_authorization.json:28 |
| `E73 P129i E33 P3` | field | longer path | 26 | 10/5/11/0 | 27 | 26 | source comment, citation comment, citation note, note on source, source notes | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/bibliographic_source_citation.json:54 |
| `E73 P1 E42 P3` | field | longer path | 26 | 10/5/11/0 | 15 | 15 | source number, citation number, source reference number | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/bibliographic_source_citation.json:63 |
| `E36 P104 E30 P75i` | link | longer path | 24 | 9/5/10/0 | 73 | 69 | holds copyright, hold copyright, copyright held by, who holds copyright, who owns the copyright | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/images.json:33 |
| `E36 P104 E30 P2` | concept | longer path | 24 | 9/5/10/0 | 56 | 51 | copyright, licence, license, rights, creative commons | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/images.json:48 |
| `E36 P104 E30 P67i E33 P3` | field | longer path | 24 | 9/5/10/0 | 20 | 19 | copyright note, copyright notes, copyright statement, rights statement, credit line | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/images.json:63 |
| `P89 E53 P1 E41 P3` | concept | longer path | 19 | 8/2/9/0 | 75 | 74 | borough, district, council area, administrative area, which borough | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/localities_administrative_areas.json:7 |
| `E13 P67i E33 P3` | field | longer path | 16 | 6/2/8/0 | 11 | 10 | area reference, area assignment reference, area reference value, area reference note | vocabularies/base/343cc20c-2c5a-11e8-90fa-0242ac120005/area_assignment.json:36 |
| `E53 P140i E13 P141` | date | longer path | 15 | 6/2/7/0 | 20 | 17 | area status date, status since, area status since, status assigned, area status from | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/area_assignment.json:7 |
| `P141 E33 P3` | field | promotable | 15 | 6/2/7/0 | 16 | 16 | land use notes, land use note, notes on land use | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/land_use_classification_assignment.json:56 |
| `P141i E13 P141` | date | promotable | 15 | 6/2/7/0 | 2 | 2 | when was land use assessed | vocabularies/base/343cc20c-2c5a-11e8-90fa-0242ac120005/land_use_classification_assignment.json:9 |

035's two longer paths both come out as promotable longer path: `SP6 P140i E13 P4` (53 phrasings, reach 28) and
`E53 P140i E13 P141` (the "dated to" / status-since family, 20 phrasings, reach 15).

## 4. Examples

| class | graph.node | kind | phrase | 3-token key | result | where |
|---|---|---|---|---|---|---|
| promotable | Maritime Vessel.cargo_type | concept | cargo | `P25 E19 P2` | P25 E19 P2 | vocabularies/base/49bac32e-5464-11e9-a6e2-000d3ab1e588/voyages.json:66 |
| promotable | Monument.risk_status | concept | at risk | `P140i E17 P41` | P140i E17 P41 | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/designation_and_protection_assignment.json:92 |
| promotable | Application Area.associated_application_area | link | related application areas | `E53 P89i` | E53 P89i | vocabularies/base/42ce82f6-83bf-11ea-b1e8-f875a44e0e11/associated_application_area.json:7 |
| promotable | Area.use_phase_start_date | date | when was it used | `P12i E5 P4` | P12i E5 P4 | vocabularies/base/979aaf0b-7042-11ea-9674-287fcf6a5e72/use_phase.json:9 |
| promotable (client) | Tale.parent_story | link | come from | `E33 P148i` | E33 P148i | packages/ceist/bench/demo/vocab/Tale/parent_story.json:7 |
| promotable longer path | Person.copyright_holder | link | copyright owner | `P104 E30 P75i` | E36 P104 E30 P75i | vocabularies/base/22477f01-1a44-11e9-b0a9-000d3ab1e588/images.json:33 |
| promotable longer path | Historic Aircraft.area_name | concept | borough | `P1 E41 P3` | P89 E53 P1 E41 P3 | vocabularies/base/b8032b00-594d-11e9-9cf0-18cf5eb368c4/localities_administrative_areas.json:7 |
| ambiguous path | Monument.town_or_city_value | field | town | `P106 E41 P3` | 9 nodes on the whole chain in Monument (and its demo and Catalina copies) | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/addresses.json:32 |
| ambiguous path | Monument.main_construction_material | concept | material | `O18i E11 P126` | 2 nodes per model (main and other material) | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/construction_phases.json:73 |
| ambiguous path | Person.date_of_birth | date | born | `P98i E67 P4` | unique in HER; 2 in Catalina Person | vocabularies/base/22477f01-1a44-11e9-b0a9-000d3ab1e588/birth.json:7 |
| ambiguous path | Monument.location_description | field | location | `P67i E33 P3` | cross-graph: `E53 P67i E33 P3` is `description` in another graph | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/location_descriptions.json:7 |
| ambiguous path (client) | Tale.actor | link | tells of | `P9 E7 P14` | cross-graph split (actor / attendee); also a demo idiom | packages/ceist/bench/demo/vocab/Tale/associated_actors.json:8 |
| non-CRM | Historic Aircraft.date_of_loss | date | lost | — | date on a P82b end only | vocabularies/base/b8032b00-594d-11e9-9cf0-18cf5eb368c4/flights.json:26 |
| non-CRM | Monument.construction_phases | group | construction phase | — | nodegroup phrase | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/construction_phases.json:26 |
| site-specific | Heritage Story.role_type | combo | author | — | combo `{"role_type": "Author"}` | vocabularies/base/0add0e11-99aa-11ea-9ab8-f875a44e0e11/associated_actors.json:57 |
| site-specific (client) | Monument.cultural_period | combo | 12c | — | combo `{"cultural_period": "12th Century"}` | packages/ceist/bench/demo/vocab/Monument/construction_phases.json:225 |
| site-specific (client) | Monument.named_location | link | county | `P89 E53 P89i` | local term (by hand) | packages/ceist/bench/demo/vocab/Monument/named_locations.json:8 |
| clash | Historic Landscape Characterization.monument_area_or_artefact | link | contains | `P141i E13 P140` | already on `P89i` | vocabularies/base/934cd7f0-480a-11ea-9240-c4d9877d154e/associated_monuments_areas_and_artefacts.json:18 |
| clash | Artefact.caption_note | field | image caption | `P129i E33 P3` | sibling promotion kept on `E36 P67i E33 P3` | vocabularies/base/343cc20c-2c5a-11e8-90fa-0242ac120005/images.json:33 |
| clash (client) | Tale.parent_story | link | in | `E33 P148i` | generic.json | packages/ceist/bench/demo/vocab/Tale/parent_story.json:9 |
| already in ontology | Monument.construction_phase_start_date | date | built | `O18i E11 P4` | applied today | vocabularies/base/076f9381-7b00-11e9-8d6b-80000b44d1d9/construction_phases.json:7 |
| already in ontology | Maritime Vessel.owner | link | owned by | `E24 P51` | applied today | vocabularies/base/49bac32e-5464-11e9-a6e2-000d3ab1e588/owner.json:23 |

## 5. Cross-graph splits (11 paths, 353 phrasings held back)

| path | kind | source nodes | verdict by eye |
|---|---|---|---|
| `P9 E7 P14` | link | actor, attendee | **probably one meaning** (involvement); 4 phrases already on it in `phrases.json` |
| `P9 E7 P4` | date | associated_actor_start_date, date | probably one meaning |
| `E11 P41i E17 P42` | concept | area_type, maritime_vessel_type, monument_type | one meaning ("type"), phrased per graph: promote only the shared ones |
| `E53 P67i E33 P3` | field | description, location_description | split |
| `P106 E33 P3` | field | description, standard_deviation_note | split |
| `P141 E42 P3` | field | page_s_, reference | split |
| `P108i E12 P4` | date | date_of_publication, from_date | split |
| `E7 P67i E33 P3` | field | activity_description, subject | split |
| `E7 P140i E13 P141` | concept | contested_heritage, record_status | split |
| `E7 P15` | link | associated_activities, related_monuments_and_areas | split |
| `E7 P7 E53 P1 E41 P3` | field | area_name, full_address | split |

## 6. Fresh-graph gain estimate

Distinct promotable (path, phrase) pairs whose path reaches a node in the set; a (node, phrase) application counts
only if `crm.ontology_entries` does not give that node that phrase today. Questions: one template question per
application (`questions.templated`, `src/ceist/questions.py:391-453`: a date or concept phrase gives a "when was" or
"what is the … of" question, a link phrase a "which … have" question; preposition-final concept phrases give none).
An upper bound: `templated` drops a question whose text has two targets, and a link needs a target model.

| set | (path, phrase) pairs present | carried today (link/date/concept) | new applications, carried | + plain fields | est. new questions, carried | + plain fields | models |
|---|---|---|---|---|---|---|---|
| **Catalina** | 1,401 | 996 | 2,797 | 1,390 | ~2,760 | ~1,310 | 21 of 23 |
| **lingo** | 18 | 18 | 32 | 0 | ~32 | 0 | 2 of 6 (Concept, Scheme) |
| HER (ontology-only mode) | 1,409 | 996 | 2,466 | 1,338 | ~2,440 | ~1,260 | 16 |
| demo (ontology-only mode) | 824 | 532 | 809 | 499 | ~800 | ~470 | 6 |

- Today's Catalina bench, ontology mode, holds 836 template questions (`vocabularies/ontology/cidoc-crm/build-report.md:249`).
  Most of the gain lands on Catalina's HER clones; the independent models gain too: Field Assessment 255, Heritage Place 489,
  Archive Source 119, Event 114, Mātauranga 85, Whenua 77, Registry 10 applications (carried + fields).
- lingo gains only 3 paths: `P94i E65 P14`, `P94i E65 P4`, `P140i E13 P14`. Its custom ZP\* properties carry most of its
  nodes, and no HER phrasing sits on them. CRM-first will not move lingo much.

## 7. Method (for 053 to implement exactly)

1. **Load** the four sets with `bench/ontology/run.py:graph_docs`. For each node with an alias, take `crm.chains(g)[alias]`.
   Kind: `date` and `link` from `bundle.kind_of`; `prop` for a non-semantic property (concept/reference = carried today;
   anything else = plain field). Semantic nodes are skipped.
2. **Keyed tokens.** Non-date: the chain without the node class (`chain[:-1]`). Date: `chain[:-3]` when
   `chain[-3] == "E52"` and `chain[-2] in {P82a, P82}`, else **non-CRM (date end only)**. These are the tokens
   `crm.ontology_entries` matches (`crm.py:192-196`).
3. **Phrasings.** For every group file under `vocabularies/base/<gid>/` (graph = the HER graph with that id) and
   `bench/demo/vocab/<Model>/` (graph = the demo graph of that name): every entry phrase, group phrase and combo phrase.
   A combo phrase or an entry with a `qualifier` → **site-specific (value-qualified)**. A group phrase → **non-CRM (no group kind)**.
4. **Non-CRM:** the last keyed token (the property into the node, or P4 for a date) is `-` or not standard:
   standard = `^(E|P|O|S|SP|L|D|Q|R|F)\d+[a-z]?i?$`, excluding `P0\d` (P01, P02). ZP\*/MP\* fail it.
5. **Path search.** From `L = min(3, len(keyed))` (the `path_of` key) up to `len(keyed)`: try `keyed[-L:]`, then
   `keyed[-L:] + [node class]` (not for dates). Stop if the suffix holds a non-standard token. For each candidate, count
   in every model of every set the nodes of the same kind it matches (`crm._ends_with` semantics: keyed tokens end with it,
   or, non-date, keyed + class does; date, `keyed[:-1]` does). The first candidate with **at most one node in every model**
   wins. Found at the 3-token key, no class → **promotable**; else → **promotable longer path**. None → **ambiguous path**
   (record which models had 2+).
   Do not shorten below 3 tokens: `E5 P4` was unique but carried "inhabited" onto every E5 time-span.
6. **Already there:** the phrase (lower-cased) is in what `crm.ontology_entries(g, phrases.json)` gives that node today → **already in ontology**.
7. **Clash** (as `ontology_vocab.review`, `:381-390`): phrase in `generic.json`; or the phrase is on an existing
   `phrases.json` path `q` with `not _extends(path, q)` → **clash**.
8. **Cross-graph split:** group the remaining promotable phrasings by (path, kind). Join two source nodes (graph id, alias)
   when they share a normalised phrase (lower-case, a trailing `s` dropped on words over 3 letters) or the same alias. More
   than one group → every phrasing on that path → **ambiguous path (cross-graph)**. Review §5 by hand; 3 are one meaning.
9. **Sibling promotions:** a phrase promoted on two paths that neither extends → keep the path with the larger reach, the
   rest → **clash** (what `_share` and the step 7 test would do once the first is accepted).
10. **Evidence:** count other (graph id, layer) pairs holding the same normalised phrase on the same chosen path.
11. **Client by hand:** local terms (`county`, `counties`) → site-specific.
12. **Gain:** as §6.

Caveats for 053:
- 808 promotable phrasings are plain fields: promoting them needs `crm.py:190` to admit non-controlled properties, and the
  bench to template them. Without that, the carried figure is 1,586 phrasings (1,272 + 1,122 − 808).
- 335 promotable paths are the whole chain from the root: in effect HER-shaped, valid only where a graph copies HER.
- 138 "already in ontology" base phrasings can be dropped from the base now, after checking `layered`'s report shows that
  `_add_ontology` does not drop them as fitting two nodes.
- The test proves the path has one meaning per model; it does not judge the phrase (e.g. `at risk` on `P140i E17 P41`, a
  value-like word on a field). The gate (`ceist vocab ontology --accept`) remains the judge.
