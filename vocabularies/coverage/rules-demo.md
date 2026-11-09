# Rule-based vocabulary build: demo

Graphs: /home/stuart/git/personal/starches-demo/ask/data/graphs. No LLM.

15 elements with a missing item a rule can phrase; review dropped 3 phrases; 12 went to the gate; 3 accepted.

## Accepted

| layer | element | rule | phrases |
| --- | --- | --- | --- |
| ontology | class E33 | class word | linguistic object, linguistic objects |
| ontology | property P89i | forward | contains |
| base | link Object.copyright_holder_n1 | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |

## Rejected by the gate

| layer | element | phrases | why |
| --- | --- | --- | --- |
| ontology | class E53 | place, places | bench: adds no right answer |
| ontology | class E22 | human-made object, human-made objects | bench: worse on 2, e.g. catalina: what is the object classification of Ruvdrith? |
| ontology | property P140 | assigned attribute to | bench: worse on 10, e.g. catalina: how many artefacts have Mavzabel as assigned attribute to? |
| ontology | property P129i | subject of | bench: worse on 2, e.g. catalina: how many heritage stories are subject of Sendrith? |
| ontology | property P67 | refers to | bench: adds no right answer |
| base | type Group | organization, organizations | bench: adds no right answer |
| base | type Object | artefact, artefacts | bench: adds no right answer |
| base | link Site.part_of | parts of | bench: adds no right answer |
| base | type Tale | heritage story, heritage stories | bench: adds no right answer |

## Dropped by review

| element | phrase | why |
| --- | --- | --- |
| property P129 | about | too generic |
| property P148i | component of | could name two elements: already link Monument.parent_monument_or_area |
| property P89 | falls within | could name two elements: already link Monument.use_phase_period, link Object.cultural_period, link Site.part_of |

## Gate checks

- bench: 3 pass alone and together
- demo bank: nothing worse with the 3 passing
- HER plans: 125/125 answers as reviewed

Bench counts: right / wrong reading / refused / right refusal / wrong.

| set | mode | before | after |
| --- | --- | --- | --- |
| lingo | ontology | 39 / 0 / 7 / 2 / 0 | 41 / 0 / 7 / 2 / 0 |
| catalina | ontology | 726 / 0 / 191 / 54 / 0 | 732 / 0 / 192 / 54 / 0 |
| her | ontology | 594 / 0 / 86 / 48 / 0 | 600 / 0 / 86 / 48 / 0 |
| her | ontology+base | 588 / 0 / 97 / 48 / 0 | 598 / 0 / 97 / 48 / 0 |

Demo bank before: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}

Demo bank after: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}
