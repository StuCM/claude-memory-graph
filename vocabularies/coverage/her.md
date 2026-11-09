# Vocabulary coverage: her

Present: the vocabulary holds the item. Set aside: it doesn't, with a recorded reason. Explained = present + set aside. The ontology is weighted by CRM node counts; overall counts items.

| layer | items | present % | explained % |
| --- | --- | --- | --- |
| ontology | 496 | 9.4 | 100.0 |
| base | 1189 | 77.5 | 87.6 |
| overall | 1685 | 67.7 | 91.0 |

## ontology

| element | item | present | set aside | missing |
| --- | --- | --- | --- | --- |
| class | class word | 8 | 120 | 0 |
| path | composed | 29 | 15 | 0 |
| path | phrasing | 151 | 91 | 4 |
| property | forward | 28 | 11 | 0 |
| property | inverse | 4 | 35 | 0 |

Missing (4, heaviest first; the first 4):

- path property E33 P72 (2): phrasing
- path link E53 P129i (1): phrasing
- path link E22 P129i (1): phrasing
- path link E18 P129i (1): phrasing

Set aside, by reason:

- 80: no model's root is this class
- 59: the LLM skipped it
- 29: a link's phrasings read both ways in Ceist, so an inverse phrasing would read backwards on the same link; only an actor's "who …" form is safe
- 24: outside CIDOC-CRM and CRMsci
- 20: label splitting
- 17: gate
- 16: the gate rejected
- 11: review
- 6: could name two models
- 6: the inverse's CRM label is not a plain verb
- 4: a CRM label too long to be said in a question

## base

| element | item | present | set aside | missing |
| --- | --- | --- | --- | --- |
| date | label | 262 | 0 | 0 |
| date | other order | 20 | 16 | 0 |
| date | verb | 124 | 16 | 123 |
| link | inverse | 24 | 88 | 25 |
| link | label | 137 | 0 | 0 |
| link | noun | 137 | 0 | 0 |
| link | verb | 185 | 0 | 0 |
| type | type word | 32 | 0 | 0 |

Missing (148, heaviest first; the first 40):

- link Activity.actor (1): inverse
- date Activity.associated_actor_end_date (1): verb
- date Activity.activity_end_date (1): verb
- date Activity.creation_end_date (1): verb
- date Activity.update_end_date (1): verb
- date Activity.area_status_end_date (1): verb
- date Activity.land_use_assessment_end_date (1): verb
- date Activity.authorization_end_date (1): verb
- date Activity.update_end_date_n1 (1): verb
- date Activity.compilation_end_date (1): verb
- date Application Area.update_end_date (1): verb
- date Application Area.compilation_end_date (1): verb
- date Application Area.authorization_end_date (1): verb
- date Application Area.creation_end_date (1): verb
- date Application Area.update_end_date_n1 (1): verb
- date Area.update_end_date (1): verb
- date Area.compilation_end_date (1): verb
- date Area.authorization_end_date (1): verb
- date Area.construction_phase_end_date (1): verb
- date Area.scientific_date_end_date (1): verb
- date Area.when_determined_end_date (1): verb
- date Area.designation_end_date (1): verb
- link Area.actor (1): inverse
- date Area.associated_actor_end_date (1): verb
- date Area.area_status_end_date (1): verb
- date Area.land_use_assessment_end_date (1): verb
- date Area.use_phase_end_date (1): verb
- date Area.creation_end_date (1): verb
- date Area.update_end_date_n1 (1): verb
- date Artefact.to_date (1): verb
- date Artefact.scientific_date_end_date (1): verb
- date Artefact.when_determined_end_date (1): verb
- date Artefact.creation_end_date (1): verb
- date Artefact.update_end_date (1): verb
- date Artefact.date_of_assessment_end (1): verb
- date Artefact.authorization_end_date (1): verb
- date Artefact.area_status_end_date (1): verb
- date Artefact.land_use_assessment_end_date (1): verb
- date Artefact.update_end_date_n1 (1): verb
- date Artefact.compilation_end_date (1): verb

Set aside, by reason:

- 88: a link's phrasings read both ways in Ceist, so an inverse phrasing would read backwards on the same link; only an actor's "who …" form is safe
- 32: audit metadata

## Where the phrasings live

Per graph: phrasings the bundle takes from the ontology layer (the CRM path's base meaning) and from the graph's own base and client layers (the delta its node names add).

| graph | ontology | own | ontology % |
| --- | --- | --- | --- |
| Activity | 151 | 394 | 27.7 |
| Application Area | 105 | 247 | 29.8 |
| Area | 327 | 589 | 35.7 |
| Artefact | 234 | 469 | 33.3 |
| Bibliographic Source | 45 | 197 | 18.6 |
| Consultation | 199 | 488 | 29.0 |
| Digital Object | 42 | 147 | 22.2 |
| Heritage Story | 131 | 330 | 28.4 |
| Historic Aircraft | 347 | 689 | 33.5 |
| Historic Landscape Characterization | 125 | 286 | 30.4 |
| Maritime Vessel | 420 | 585 | 41.8 |
| Monument | 349 | 795 | 30.5 |
| Organization | 121 | 201 | 37.6 |
| Period | 57 | 171 | 25.0 |
| Person | 116 | 359 | 24.4 |
| Place | 42 | 187 | 18.3 |

Every base and client phrasing, by where `vocab crm-first` left it (crm-first.json):

| layer | promotable | promotable longer path | ambiguous path | non-CRM | site-specific | clash | gate-rejected | not applied | already in ontology |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 846 | 628 | 3326 | 2 | 799 | 791 | 962 | 4 | 147 |
| client | 1 | 0 | 18 | 0 | 34 | 3 | 0 | 0 | 1 |
