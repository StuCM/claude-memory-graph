# CRM as the lid of last resort: a measurement

Read-only check, 2026-11-09. No LLM run. Scripts in the session scratchpad (`crmlid.py`, `demoq.py`, `sim.py`, `sup.py`); the
CRM hierarchy is read from `vocabularies/ontology/cidoc-crm/source/` (v6.2 + CRMsci 1.2.3, `rdfs:subClassOf` closure).

Graph sets (as `bench/ontology/run.py:28-30` and the demo's `ask.py:startup` load them):

| set | path | models | links | relations (`relations()`) |
|---|---|---|---|---|
| demo | `starches-demo/ask/data/graphs` | 6 | 58 | 35 |
| HER | `~/.cache/tmp-003/arches-her/.../resource_models` | 16 | 137 | 55 |
| Catalina | `catalina-graphs/output/graphs/resource_models` | 23 | 464 | 211 |

## 0. The lid already exists

| where | what it does |
|---|---|
| `src/ceist/arches.py:170` | `_crm[model] = (root class, {link alias: class})` per model |
| `src/ceist/crm.py:131-143` | `link_ranges`: a link's class is the **node's own `ontologyclass`**, else E39/E53 from the property's role (`_ROLE_RANGE`, :106). It never reads the property's range. |
| `src/ceist/crm.py:96-104` | `PARENTS`: a hand list of about 25 classes, not the RDFS |
| `src/ceist/crm.py:119-123` | `clash(a, b)`: neither class is a kind of the other. **A class not in `PARENTS` never clashes**, so E1, E70, E77, E78, E92, ZE13 and S20 all pass. |
| `src/ceist/arches.py:389-396` | `_crm_targets`: when the config names no graph, the models whose root doesn't clash. **When no model fits, it returns the empty set, and that means "any".** |
| `src/ceist/arches.py:307, 366` | that set becomes the link's `ends` entry. `range` (:309) is taken **only** from the configured graphs. |

How assembly treats a link with no restriction today:

| step | code | an end that is empty or "any" | an end narrowed by CRM |
|---|---|---|---|
| a phrase between two named pieces | `assemble.py:134-139` → `Relation.joins`, `vocabulary.py:59-64` | joins any target | joins only the CRM set |
| one piece named, the other end left implicit | `assemble.py:152` (`r.targets`) | no implicit end is offered from that side | one implicit end per CRM model |
| implicit join, where no phrase links two parts | `assemble.py:177-196` (`b.type in r.range`) | **never used** | **never used**, because `range` holds the configured graphs only |

The domain is never empty: it is the models that hold the link (`arches.py:308`).

## 1. Links that leave their target graphs unset

| set | relations with ≥1 unrestricted end | relations with empty `range` | unrestricted ends (model × link) | still "any" after today's lid |
|---|---|---|---|---|
| demo | 17 / 35 | 17 | 32 | 17 |
| HER | **0 / 55** | 0 | 0 | 0 |
| Catalina | 66 / 211 | 63 | 128 | 35 (ZE13, E1, or P3 on a node with no class) |

HER sets `config.graphs` on every link, so no lid is needed there.

## 2. Would CRM narrow them? (strict test: the root class ⊑ the class)

Columns: **today** is the size of `_crm_targets` ("any" means empty, or all N). **CRM P-range** means roots ⊑ the RDFS range of the node's `parentproperty`. **Node class** means roots ⊑ the node's own `ontologyclass`.

Summary over unrestricted ends:

| set | P-range narrows | P-range allows all | P-range allows none | property not in the RDFS | node class narrows | node class allows none |
|---|---|---|---|---|---|---|
| demo (32) | 22 | 2 (P67 → E1) | 6 (E5/E7, no event model) | 2 (`P01`, a typo) | 15 | 17 |
| Catalina (128) | 50 | 8 (P140/P17/P67/P129 → E1) | 0 | **70** (ZP\*, MP1, P02 custom; P3 → literal) | 89 | 37 (ZE13, D1) |

D1 (CRMdig) is not in the sources, so it counts as unknown. `crm.py:100` hand-codes D1 ⊑ E73.


#### demo (N = 6 models)

| alias | held by | P → CRM range | node class | today (`_crm_targets`) | CRM P-range ⇒ models (n/N) | node class ⇒ n/N |
|---|---|---|---|---|---|---|
| associated_activities | Figure, Group | P11i → E5 | E7 | any | none (0/6) | 0/6 |
| associated_activities | Monument, Object | P12i → E5 | E7 | any | none (0/6) | 0/6 |
| associated_activities | Tale | P67 → E1 | E7 | any | all known (6/6) | 0/6 |
| digital_file_s_ | Figure, Group, Tale | P67i → E89 | D1 | any | Tale (1/6) | 0/6 |
| digital_file_s_ | Monument | P12 → E77 | D1 | any | Figure, Group, Monument, Object, Tale (5/6) | 0/6 |
| digital_file_s_ | Object | P129i → E89 | D1 | any | Tale (1/6) | 0/6 |
| bibliographic_source_citation | Figure, Group, Monument, Object | P67i → E89 | E73 | 1 | Tale (1/6) | 1/6 |
| bibliographic_source_citation | Tale | P129i → E89 | E73 | 1 | Tale (1/6) | 1/6 |
| associated_consultations | Figure | P11i → E5 | E7 | any | none (0/6) | 0/6 |
| associated_consultations | Monument | P16i → E7 | E7 | any | none (0/6) | 0/6 |
| named_location | Monument, Object | P89i → E53 | E53 | 1 | Site (1/6) | 1/6 |
| use_phase_period | Monument | P10 → E92 | E4 | any | Figure, Monument, Object (3/6) | 0/6 |
| digital_file_s__n1 | Monument, Object | P129i → E89 | D1 | any | Tale (1/6) | 0/6 |
| cultural_period | Object | P10 → E92 | E4 | any | Figure, Monument, Object (3/6) | 0/6 |
| statement_creation_carried_out_by | Site | P14 → E39 | E39 | 2 | Figure, Group (2/6) | 2/6 |
| statement_creation_digital_reference | Site | P16 → E70 | E73 | 1 | Figure, Monument, Object, Tale (4/6) | 1/6 |
| statement_creation_textual_reference | Site | P16 → E70 | E33 | 1 | Figure, Monument, Object, Tale (4/6) | 1/6 |
| textual_source | Site | P01 → ? | E73 | 1 | n/a (P01 not in RDFS) (0/6) | 1/6 |
| source_n1 | Site | P67i → E89 | E33 | 1 | Tale (1/6) | 1/6 |
| source | Site | P67i → E89 | E33 | 1 | Tale (1/6) | 1/6 |
| source_n2 | Site | P67i → E89 | E33 | 1 | Tale (1/6) | 1/6 |
| digital_source | Site | P01 → ? | E73 | 1 | n/a (P01 not in RDFS) (0/6) | 1/6 |
| temporal_coverage | Tale | P67 → E1 | E4 | any | all known (6/6) | 0/6 |

#### catalina (N = 23 models)

| alias | held by | P → CRM range | node class | today (`_crm_targets`) | CRM P-range ⇒ models (n/N) | node class ⇒ n/N |
|---|---|---|---|---|---|---|
| archive_object_title | 5 models | P3 → literal | - | any | n/a (literal range) (0/23) | 0/23 |
| rar_approved_by_value | 11 models | P107 → E39 | E21 | 4 | Group, Organization, Person (3/23) | 1/23 |
| rar_input_by_value | 11 models | P107 → E39 | E21 | 4 | Group, Organization, Person (3/23) | 1/23 |
| associated_monument_area_or_artefact | Archive Source | P140 → E1 | E18 | 9 | all known (21/23) | 8/23 |
| associated_archive | Artefact | P140 → E1 | E18 | 9 | all known (21/23) | 8/23 |
| creator | Mātauranga | P02 → ? | E39 | 5 | n/a (P02 not in RDFS) (0/23) | 3/23 |
| appellative-status-holds-for | Event, Mātauranga, Tikanga, Whenua | ZP4 → ? | E74 | 4 | n/a (ZP4 not in RDFS) (0/23) | 2/23 |
| appellative-status-event-context | Event, Mātauranga, Tikanga, Whenua | ZP75 → ? | E5 | 6 | n/a (ZP75 not in RDFS) (0/23) | 3/23 |
| appellative-status-initiating-act | Event, Mātauranga, Tikanga, Whenua | ZP42i → ? | ZE13 | any | n/a (ZP42i not in RDFS) (0/23) | 0/23 |
| appellative-status-terminating-act | Event, Mātauranga, Tikanga, Whenua | ZP52i → ? | ZE13 | any | n/a (ZP52i not in RDFS) (0/23) | 0/23 |
| bibliographic-source | Event, Whenua | P67i → E89 | E73 | 7 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 4/23 |
| classificatory-status-holds-for | Event, Mātauranga, Tikanga, Whenua | ZP4 → ? | E74 | 4 | n/a (ZP4 not in RDFS) (0/23) | 2/23 |
| classificatory-status-event-context | Event, Mātauranga, Tikanga, Whenua | ZP75 → ? | E5 | 6 | n/a (ZP75 not in RDFS) (0/23) | 3/23 |
| classificatory-status-initiating-act | Event, Mātauranga, Tikanga, Whenua | ZP42i → ? | ZE13 | any | n/a (ZP42i not in RDFS) (0/23) | 0/23 |
| classificatory-status-terminating-act | Event, Mātauranga, Tikanga, Whenua | ZP52i → ? | ZE13 | any | n/a (ZP52i not in RDFS) (0/23) | 0/23 |
| function-status-holds-for | Event, Whenua | ZP4 → ? | E74 | 4 | n/a (ZP4 not in RDFS) (0/23) | 2/23 |
| function-status-event-context | Event, Whenua | ZP75 → ? | E5 | 6 | n/a (ZP75 not in RDFS) (0/23) | 3/23 |
| function-status-initiating-act | Event, Whenua | ZP42i → ? | ZE13 | any | n/a (ZP42i not in RDFS) (0/23) | 0/23 |
| function-status-terminating-act | Event, Whenua | ZP52i → ? | ZE13 | any | n/a (ZP52i not in RDFS) (0/23) | 0/23 |
| named-locations | Event | P89i → E53 | E53 | 5 | Application Area, Area, Historic Landscape Characterization, Place, Whenua (5/23) | 5/23 |
| evental-locative-status-ascribed-place | Event, Tikanga | ZP77 → ? | E53 | 5 | n/a (ZP77 not in RDFS) (0/23) | 5/23 |
| evental-locative-status-holds-for | Event, Tikanga | ZP4 → ? | E74 | 4 | n/a (ZP4 not in RDFS) (0/23) | 2/23 |
| evental-locative-status-event-context | Event, Tikanga | ZP75 → ? | E5 | 6 | n/a (ZP75 not in RDFS) (0/23) | 3/23 |
| evental-locative-status-initiating-act | Event, Tikanga | ZP42i → ? | ZE13 | any | n/a (ZP42i not in RDFS) (0/23) | 0/23 |
| evental-locative-status-terminating-act | Event, Tikanga | ZP52i → ? | ZE13 | any | n/a (ZP52i not in RDFS) (0/23) | 0/23 |
| source-reference-particular | Event, Tikanga, Whenua | P129i → E89 | E33 | 6 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 4/23 |
| associated-monuments-and-areas | Event | P17 → E1 | E18 | 9 | all known (21/23) | 8/23 |
| activity-instrument-used | Event, Tikanga | P16 → E70 | E22 | 6 | Archive Source, Area, Artefact, Bibliographic Source, Heritage Place, Heritage Story, Historic Aircraft, Maritime Vessel, Mātauranga, Person, Registry, Whenua (12/23) | 1/23 |
| digital-files | Event, Mātauranga | P67i → E89 | D1 | 3 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 0/23 |
| translation | Mātauranga | P73 → E33 | E33 | 6 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 4/23 |
| bibliographic-source-citation | Mātauranga | P129i → E89 | E73 | 7 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 4/23 |
| critical-reading-actor | Mātauranga | P14 → E39 | E39 | 5 | Group, Organization, Person (3/23) | 3/23 |
| parent-story | Mātauranga | P148i → E89 | E33 | 6 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 4/23 |
| temporal-coverage | Mātauranga | P67 → E1 | E4 | 6 | all known (21/23) | 4/23 |
| heritage-associated-activities | Mātauranga | P67 → E1 | E7 | 6 | all known (21/23) | 2/23 |
| heritage-story-monument-area-or-artefact | Mātauranga | P129 → E1 | E18 | 9 | all known (21/23) | 8/23 |
| entity-intended | Mātauranga | P129 → E1 | E1 | any | all known (21/23) | 21/23 |
| profession_activity_used_object | Person | P16 → E70 | E22 | 6 | Archive Source, Area, Artefact, Bibliographic Source, Heritage Place, Heritage Story, Historic Aircraft, Maritime Vessel, Mātauranga, Person, Registry, Whenua (12/23) | 1/23 |
| statement_creation_digital_reference | Person | P16 → E70 | E73 | 7 | Archive Source, Area, Artefact, Bibliographic Source, Heritage Place, Heritage Story, Historic Aircraft, Maritime Vessel, Mātauranga, Person, Registry, Whenua (12/23) | 4/23 |
| activity-actor | Tikanga | P14 → E39 | E39 | 5 | Group, Organization, Person (3/23) | 3/23 |
| promise-to | Tikanga | ZP117 → ? | E39 | 5 | n/a (ZP117 not in RDFS) (0/23) | 3/23 |
| promissory-subject | Tikanga | ZP89 → ? | E22 | 6 | n/a (ZP89 not in RDFS) (0/23) | 1/23 |
| promise-upon | Tikanga | ZP118 → ? | E39 | 5 | n/a (ZP118 not in RDFS) (0/23) | 3/23 |
| declarative-custody-transfer-object-transferred | Tikanga | P30 → E18 | E18 | 9 | Area, Artefact, Heritage Place, Historic Aircraft, Maritime Vessel, Person, Registry, Whenua (8/23) | 8/23 |
| custody_received_by | Tikanga | P29 → E39 | E39 | 5 | Group, Organization, Person (3/23) | 3/23 |
| custody_surrendered_by | Tikanga | P28 → E39 | E39 | 5 | Group, Organization, Person (3/23) | 3/23 |
| source-reference-general | Tikanga | P67i → E89 | E33 | 6 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 4/23 |
| parent-area | Whenua | P59i → E18 | E27 | 5 | Area, Artefact, Heritage Place, Historic Aircraft, Maritime Vessel, Person, Registry, Whenua (8/23) | 2/23 |
| whakapapa-status-ascribed-ancestor | Whenua | MP1 → ? | E1 | any | n/a (MP1 not in RDFS) (0/23) | 21/23 |
| construction-cultural-period | Whenua | P10 → E92 | E4 | 6 | Activity, Area, Artefact, Event, Field Assessment, Heritage Place, Historic Aircraft, Maritime Vessel, Period, Person, Registry, Whenua (12/23) | 4/23 |
| use-phase-period | Whenua | P10 → E92 | E4 | 6 | Activity, Area, Artefact, Event, Field Assessment, Heritage Place, Historic Aircraft, Maritime Vessel, Period, Person, Registry, Whenua (12/23) | 4/23 |
| designation-digital-files | Whenua | P12 → E77 | D1 | 3 | Archive Source, Area, Artefact, Bibliographic Source, Group, Heritage Place, Heritage Story, Historic Aircraft, Maritime Vessel, Mātauranga, Organization, Person, Registry, Whenua (14/23) | 0/23 |
| physical-locative-status-ascribed-place | Whenua | ZP77 → ? | E53 | 5 | n/a (ZP77 not in RDFS) (0/23) | 5/23 |
| physical-locative-status-holds-for | Whenua | ZP4 → ? | E74 | 4 | n/a (ZP4 not in RDFS) (0/23) | 2/23 |
| physical-locative-status-event-context | Whenua | ZP75 → ? | E5 | 6 | n/a (ZP75 not in RDFS) (0/23) | 3/23 |
| physical-locative-status-initiating-act | Whenua | ZP42i → ? | ZE13 | any | n/a (ZP42i not in RDFS) (0/23) | 0/23 |
| physical-locative-status-terminating-act | Whenua | ZP52i → ? | ZE13 | any | n/a (ZP52i not in RDFS) (0/23) | 0/23 |
| custodial-status-custodian | Whenua | ZP21 → ? | E39 | 5 | n/a (ZP21 not in RDFS) (0/23) | 3/23 |
| custodial-status-holds-for | Whenua | ZP4 → ? | E74 | 4 | n/a (ZP4 not in RDFS) (0/23) | 2/23 |
| custodial-status-event-context | Whenua | ZP75 → ? | E5 | 6 | n/a (ZP75 not in RDFS) (0/23) | 3/23 |
| custodial-initiating-declarative-transfer | Whenua | ZP42i → ? | ZE13 | any | n/a (ZP42i not in RDFS) (0/23) | 0/23 |
| custodial-terminating-declarative-transfer | Whenua | ZP52i → ? | ZE13 | any | n/a (ZP52i not in RDFS) (0/23) | 0/23 |
| area-associated-activities | Whenua | P12i → E5 | E7 | 6 | Activity, Event, Field Assessment (3/23) | 2/23 |
| area-associated-consultations | Whenua | P16i → E7 | E7 | 6 | Activity, Field Assessment (2/23) | 2/23 |
| associated-monument-area-or-artefact | Whenua | P140 → E1 | E18 | 9 | all known (21/23) | 8/23 |
| area-digital-files | Whenua | P129i → E89 | D1 | 3 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga (4/23) | 0/23 |

What today's lid gets wrong on Catalina, set against full RDFS:

| link | today | full RDFS (node class) | why |
|---|---|---|---|
| `named-locations` (P89i → E53) | App Area, HLC, Place, **Registry, Tikanga** | App Area, **Area**, HLC, Place, **Whenua** | E27 ⊑ E53 holds only via CRMsci S20, which `PARENTS` lacks. E78 and ZE13 are missing from `PARENTS`, so they never clash. |
| `rar_approved_by_value` (E21) | Heritage Place, Person, Registry, Tikanga | Person | the test runs both ways, so the supertype E18 passes. Registry and Tikanga leak. |
| `digital-files` (D1) | Digital Object, Registry, Tikanga | (Digital Object, once D1 is known) | leak |

Registry (E78) and Tikanga (ZE13) leak into **every** narrowed set on Catalina.

### Measured effect on questions

| bank | questions | whose readings use an unrestricted link | via an end today's lid narrows | via an "any" end | changed by a full-RDFS lid |
|---|---|---|---|---|---|
| demo `bench/demo/questions.json` | 90 | 35 | 34 (`named_location` → Site) | 1 | **1, a regression** |
| HER `bench/her/cases.json` | 125 | 0 | – | – | 0 (nothing unrestricted) |
| Catalina | no bank | – | – | – | – |

The regression is "what period is Navan Fort?", which is right today. Its answer, "Show the cultural period of Monument …", rides on a spurious reading: `Object.cultural_period` → Monument.
- With a node-class lid (E4, no model) it has **0 readings and refuses**.
- With a P-range lid (P10 → E92: Figure, Monument, Object) it becomes **"Find Objects whose cultural period is Monument 'Navan Fort'"**, which is wrong.

## 3. Cross-graph: models under one CRM superclass

| superclass | demo (6) | HER (16) | Catalina (23) |
|---|---|---|---|
| E39 Actor | Figure, Group | Organization, Person | Group, Organization, Person |
| E53 Place | Site | App Area, Area†, HLC, Place | App Area, Area†, HLC, Place, Whenua† |
| E24 Human-Made Thing | Object | Artefact, Hist. Aircraft, Maritime Vessel | + Registry (E78) |
| E18 Physical Thing | Figure, Monument, Object | 6, incl. **Person** | 8, incl. **Person, Registry** |
| E73 Info. Object | Tale | Bibliographic Source, Heritage Story | + Archive Source, Mātauranga |
| E5 Event | – | Activity, Consultation | Activity, Event, Field Assessment |
| E70 Thing | 4 | 8 | 12, incl. Person |
| E92 Spacetime Volume | 3 | 9 | 12, incl. Person, Activity |
| E77 Persistent Item | 5 | 9 | 14 |
| E1 | 6 | 15 (not D1) | 21 (not D1 or ZE13) |

† E27 Site ⊑ E53 only through CRMsci (`S20_Physical_Feature`).

Phrases that would reach several models:

| phrase | CRM path | models (Catalina) |
|---|---|---|
| "who" / "people or groups" | root ⊑ E39 | Person, Group, Organization. This is already used for "who" in `arches.py:585`. |
| "where" / "places" | root ⊑ E53 | 5 models. This is already used for place fields in `arches.py:507`. |
| "objects" / "things made" | root ⊑ E24 | Artefact, Aircraft, Vessel, **Registry** |
| "sources" / "documents" | root ⊑ E73 | Archive Source, Bibliographic Source, Heritage Story, Mātauranga |
| "events" | root ⊑ E5 | Activity, Event, Field Assessment |
| "things associated with a person" | Person ← P14/P107/P29 (E39 links, 3 targets) **or** P140/P67/P129 (E1, every model) | E39 links are precise. The "associated" links (P67/P129/P140) are E1, so every model qualifies. |

## 4. Verdict

**Don't build a bigger lid now.** The lid already exists (`arches.py:389`), and on the measured banks tightening it only costs:
- HER: 0 / 125 questions affected.
- demo: 1 / 90 affected, and that change is a regression.
- Catalina: 128 unrestricted ends, but no question bank to measure against.

Cheap fixes, if Catalina matters:

| fix | where | effect |
|---|---|---|
| read the hierarchy from the RDFS (with CRMsci) instead of `PARENTS` | `crm.py:96` | stops Registry/Tikanga leaking. Area and Whenua become Places. |
| test one way (root ⊑ class), not "no clash" | `crm.py:119` | E21 links stop admitting E18 Heritage Place |
| an empty CRM set means "none", not "any" | `arches.py:393-396`, `vocabulary.py:62` | 17 demo ends and the ZE13/D1 ends. **Fix the Navan Fort reading first.** |

Where CRM is too permissive to help:

| range | share of unrestricted ends | why it doesn't narrow |
|---|---|---|
| E1 (P67 refers to, P129 is about, P140 assigned attribute to, P17) | demo 2, Catalina 8 by P-range | every model qualifies |
| E70 (P16 used specific object) | Catalina 4 | 12/23, including Person |
| E92 (P10 falls within) | demo 2, Catalina 2 | Person and Activity qualify for a "period" |
| E77 (P12) | demo 1, Catalina 1 | 14/23 |
| custom ZP\*/MP1/P02/P01, P3 → literal | demo 2, Catalina **70** | not in the RDFS at all |
| ZE13 / D1 roots | Catalina 2 models | unknown classes. They "never clash" today, so they leak. |

The node class is the better signal than the property range: on Catalina it narrows 89 ends against 50 for P-range. It only falls short where the node class is itself E1 or unknown.
