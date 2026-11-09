# Rule-based vocabulary build: her

Graphs: /home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models. No LLM.

10 elements with a missing item a rule can phrase; review dropped 7 phrases; 7 went to the gate; 3 accepted.

## Accepted

| layer | element | rule | phrases |
| --- | --- | --- | --- |
| ontology | path date P108i E12 P4 | composed | date of production, production date |
| ontology | path date P132 E11 P4 | composed | modified |
| ontology | path date P16i E9 P4 | composed | moved, date of move, move date |

## Rejected by the gate

| layer | element | phrases | why |
| --- | --- | --- | --- |
| ontology | path property P9 E65 P2 | creation type, type of creation | bench: adds no right answer |
| ontology | path property P93i E81 P2 | transformation type, type of transformation | bench: adds no right answer |
| ontology | path property P132 E11 P2 | modification type, type of modification | bench: adds no right answer |
| ontology | path property P16i E9 P2 | move type, type of move | bench: adds no right answer |

## Dropped by review

| element | phrase | why |
| --- | --- | --- |
| path date P132 E11 P4 | date of modification | could name two elements: already date Area.construction_phase_start_date, date Monument.construction_phase_start_date |
| path date P132 E11 P4 | modification date | could name two elements: already date Area.construction_phase_start_date, date Monument.construction_phase_start_date |
| path date P94i E65 P4 | created | could name two elements: already date Artefact.from_date, date Digital Object.start_date, date Organization.start_date |
| path date P94i E65 P4 | date of creation | could name two elements: already date Digital Object.start_date |
| path date P94i E65 P4 | creation date | could name two elements: already date Activity.creation_date, date Application Area.creation_date, date Area.creation_date |
| path link P17i E65 P14 | created by | could name two elements: already link Digital Object.creator |
| path link P94i E65 P14 | created by | could name two elements: already link Digital Object.creator |

## Gate checks

- bench: 3 pass alone and together
- demo bank: nothing worse with the 3 passing
- HER plans: 125/125 answers as reviewed

Bench counts: right / wrong reading / refused / right refusal / wrong.

| set | mode | before | after |
| --- | --- | --- | --- |
| lingo | ontology | 85 / 0 / 7 / 2 / 0 | 85 / 0 / 7 / 2 / 0 |
| catalina | ontology | 2628 / 0 / 786 / 117 / 0 | 2638 / 0 / 786 / 119 / 0 |
| her | ontology | 2289 / 0 / 632 / 110 / 0 | 2299 / 0 / 632 / 112 / 0 |
| her | ontology+base | 2210 / 0 / 711 / 110 / 0 | 2219 / 0 / 712 / 112 / 0 |

Demo bank before: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}

Demo bank after: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}
