# Vocabulary coverage: her

Present: the vocabulary holds the item. Set aside: it doesn't, with a recorded reason. Explained = present + set aside. The ontology is weighted by CRM node counts; overall counts items.

| layer | items | present % | explained % |
| --- | --- | --- | --- |
| ontology | 452 | 7.2 | 99.9 |
| base | 1189 | 77.5 | 87.6 |
| overall | 1641 | 64.8 | 90.6 |

## ontology

| element | item | present | set aside | missing |
| --- | --- | --- | --- | --- |
| class | class word | 8 | 120 | 0 |
| path | phrasing | 103 | 137 | 6 |
| property | forward | 28 | 11 | 0 |
| property | inverse | 4 | 35 | 0 |

Missing (6, heaviest first; the first 6):

- path property E33 P72 (2): phrasing
- path link E53 P129i (1): phrasing
- path link E27 P129i (1): phrasing
- path link E22 P129i (1): phrasing
- path link E33 P129i (1): phrasing
- path link E18 P129i (1): phrasing

Set aside, by reason:

- 102: the LLM skipped it
- 80: no model's root is this class
- 29: a link's phrasings read both ways in Ceist, so an inverse phrasing would read backwards on the same link; only an actor's "who …" form is safe
- 25: outside CIDOC-CRM and CRMsci
- 20: label splitting
- 18: the gate rejected
- 9: gate
- 6: could name two models
- 6: the inverse's CRM label is not a plain verb
- 4: a CRM label too long to be said in a question
- 4: review

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
