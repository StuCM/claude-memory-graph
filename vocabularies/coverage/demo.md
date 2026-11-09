# Vocabulary coverage: demo

Present: the vocabulary holds the item. Set aside: it doesn't, with a recorded reason. Explained = present + set aside. The ontology is weighted by CRM node counts; overall counts items.

| layer | items | present % | explained % |
| --- | --- | --- | --- |
| ontology | 338 | 9.8 | 99.8 |
| base | 443 | 74.7 | 87.8 |
| client | 991 | 97.8 | 100.0 |
| overall | 1772 | 80.6 | 96.6 |

## ontology

| element | item | present | set aside | missing |
| --- | --- | --- | --- | --- |
| class | class word | 8 | 108 | 0 |
| path | composed | 21 | 0 | 4 |
| path | phrasing | 81 | 63 | 3 |
| property | forward | 15 | 11 | 0 |
| property | inverse | 3 | 21 | 0 |

Missing (7, heaviest first; the first 7):

- path link E18 P129i (1): phrasing
- path link E22 P129i (1): phrasing
- path link P94i E65 P14 (1): composed 'created by'
- path date P94i E65 P4 (1): composed 'created'
- path date P94i E65 P4 (1): composed 'date of creation'
- path date P94i E65 P4 (1): composed 'creation date'
- path property E33 P72 (1): phrasing

Set aside, by reason:

- 78: no model's root is this class
- 45: the LLM skipped it
- 19: outside CIDOC-CRM and CRMsci
- 18: label splitting
- 16: a link's phrasings read both ways in Ceist, so an inverse phrasing would read backwards on the same link; only an actor's "who …" form is safe
- 9: the gate rejected
- 7: gate
- 5: the inverse's CRM label is not a plain verb
- 3: a CRM label too long to be said in a question
- 3: review

## base

| element | item | present | set aside | missing |
| --- | --- | --- | --- | --- |
| date | label | 79 | 0 | 0 |
| date | other order | 7 | 5 | 0 |
| date | verb | 37 | 5 | 38 |
| link | inverse | 9 | 41 | 8 |
| link | label | 58 | 0 | 0 |
| link | noun | 56 | 1 | 1 |
| link | verb | 69 | 0 | 7 |
| type | type word | 16 | 6 | 0 |

Missing (54, heaviest first; the first 40):

- date Figure.creation_end_date (1): verb
- date Figure.update_end_date (1): verb
- link Figure.mother (1): inverse
- link Figure.actor (1): inverse
- date Figure.associated_actor_end_date (1): verb
- link Figure.father (1): inverse
- date Group.creation_end_date (1): verb
- date Group.update_end_date (1): verb
- link Group.parent_organization (1): inverse
- link Group.associated_actors (1): inverse
- date Monument.scientific_date_end_date (1): verb
- date Monument.when_determined_end_date (1): verb
- date Monument.creation_end_date (1): verb
- date Monument.update_end_date (1): verb
- date Monument.designation_end_date (1): verb
- date Monument.construction_phase_end_date (1): verb
- date Monument.authorization_end_date (1): verb
- date Monument.area_status_end_date (1): verb
- date Monument.land_use_assessment_end_date (1): verb
- date Monument.update_end_date_n1 (1): verb
- date Monument.compilation_end_date (1): verb
- link Monument.actor (1): inverse
- date Monument.associated_actor_end_date (1): verb
- date Monument.use_phase_end_date (1): verb
- date Object.to_date (1): verb
- date Object.scientific_date_end_date (1): verb
- date Object.when_determined_end_date (1): verb
- date Object.creation_end_date (1): verb
- date Object.update_end_date (1): verb
- date Object.date_of_assessment_end (1): verb
- date Object.authorization_end_date (1): verb
- date Object.area_status_end_date (1): verb
- date Object.land_use_assessment_end_date (1): verb
- date Object.update_end_date_n1 (1): verb
- date Object.compilation_end_date (1): verb
- link Site.statement_creation_carried_out_by (1): inverse
- date Site.statement_creation_time_end_of_the_end (1): verb
- link Site.statement_creation_digital_reference (1): verb
- link Site.statement_creation_textual_reference (1): verb
- date Site.statement_creation_time_begin_of_the_end (1): verb

Set aside, by reason:

- 41: a link's phrasings read both ways in Ceist, so an inverse phrasing would read backwards on the same link; only an actor's "who …" form is safe
- 10: audit metadata
- 7: gate

## client

| element | item | present | set aside | missing |
| --- | --- | --- | --- | --- |
| value | alternative label | 489 | 0 | 0 |
| value | plural | 480 | 22 | 0 |

Set aside, by reason:

- 22: not a count noun

## Where the phrasings live

Per graph: phrasings the bundle takes from the ontology layer (the CRM path's base meaning) and from the graph's own base and client layers (the delta its node names add).

| graph | ontology | own | ontology % |
| --- | --- | --- | --- |
| Figure | 116 | 365 | 24.1 |
| Group | 121 | 201 | 37.6 |
| Monument | 330 | 834 | 28.4 |
| Object | 234 | 470 | 33.2 |
| Site | 37 | 0 | 100.0 |
| Tale | 131 | 337 | 28.0 |

Every base and client phrasing, by where `vocab crm-first` left it (crm-first.json):

| layer | promotable | promotable longer path | ambiguous path | non-CRM | site-specific | clash | gate-rejected | not applied | already in ontology |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 846 | 628 | 3326 | 2 | 799 | 791 | 962 | 4 | 147 |
| client | 1 | 0 | 18 | 0 | 34 | 3 | 0 | 0 | 1 |
