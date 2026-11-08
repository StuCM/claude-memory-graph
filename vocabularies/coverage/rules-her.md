# Rule-based vocabulary build: her

Graphs: /home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models. No LLM.

72 elements with a missing item a rule can phrase; review dropped 13 phrases; 65 went to the gate; 59 accepted.

## Accepted

| layer | element | rule | phrases |
| --- | --- | --- | --- |
| ontology | class E21 | class word | person, people |
| ontology | class E18 | class word | physical thing, physical things |
| ontology | class E74 | class word | group, groups |
| ontology | property P67i | forward | referred to by |
| ontology | property P14 | inverse | who performed |
| ontology | property P75i | forward, inverse | possessed by, who possesses |
| ontology | property P10 | forward | falls within |
| ontology | property P107 | forward | current or former member |
| ontology | property P49 | forward | former or current keeper |
| ontology | property P59i | forward | located on or within |
| ontology | property P165i | forward | incorporated in |
| ontology | property P122 | forward | borders with |
| ontology | property P11 | forward, inverse | had participant, who participated in |
| ontology | property P92 | forward | brought into existence |
| ontology | property P117 | forward | occurs during |
| ontology | property P16 | forward | used specific object |
| ontology | property P51 | forward | former or current owner |
| ontology | property P96 | forward, inverse | by mother, who gave birth |
| ontology | property P97 | forward | from father |
| base | link Activity.archive_holder | inverse, verb | holds archive, hold archive, who holds archive |
| base | date Activity.date_of_last_update | other order, verb | last update date, updated |
| base | link Activity.repository_owner | inverse, verb | owns repository, own repository, repository owned by, who owns repository |
| base | date Application Area.date_of_last_update | other order, verb | last update date, updated |
| base | link Area.archive_holder | inverse, verb | holds archive, hold archive, who holds archive |
| base | link Area.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | date Area.date_of_last_update | other order, verb | last update date, updated |
| base | link Artefact.repository_owner | inverse, verb | owns repository, own repository, repository owned by, who owns repository |
| base | date Artefact.date_of_last_update | other order, verb | last update date, updated |
| base | link Artefact.producer | inverse, verb | produces, produce, who produces |
| base | link Bibliographic Source.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | date Bibliographic Source.date_of_last_update | other order, verb | last update date, updated |
| base | link Consultation.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | link Consultation.owner | inverse, verb | owns, own, who owns |
| base | date Consultation.date_of_last_update | other order, verb | last update date, updated |
| base | link Digital Object.creator | inverse, verb | creates, create, who creates |
| base | date Digital Object.date_of_last_update | other order, verb | last update date, updated |
| base | link Digital Object.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | link Heritage Story.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | date Heritage Story.date_of_last_update | other order, verb | last update date, updated |
| base | link Historic Aircraft.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | link Historic Aircraft.archive_holder | inverse, verb | holds archive, hold archive, who holds archive |
| base | date Historic Aircraft.date_of_last_update | other order, verb | last update date, updated |
| base | date Historic Landscape Characterization.date_of_last_update | other order, verb | last update date, updated |
| base | link Maritime Vessel.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | link Maritime Vessel.archive_holder | inverse, verb | holds archive, hold archive, who holds archive |
| base | link Maritime Vessel.owner | inverse, verb | owns, own, who owns |
| base | link Maritime Vessel.builder | inverse, verb | builds, build, who builds |
| base | date Maritime Vessel.date_of_last_update | other order, verb | last update date, updated |
| base | link Monument.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | date Monument.date_of_last_update | other order, verb | last update date, updated |
| base | link Monument.archive_holder | inverse, verb | holds archive, hold archive, who holds archive |
| base | link Organization.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | date Organization.date_of_last_update | other order, verb | last update date, updated |
| base | date Period.date_of_last_update | other order, verb | last update date, updated |
| base | type Person | type word | people |
| base | date Person.date_of_death | verb | die |
| base | date Person.date_of_last_update | other order, verb | last update date, updated |
| base | link Person.copyright_holder | inverse, verb | holds copyright, hold copyright, copyright held by, who holds copyright |
| base | date Place.date_of_last_update | other order, verb | last update date, updated |

## Rejected by the gate

| layer | element | phrases | why |
| --- | --- | --- | --- |
| ontology | class E4 | period, periods | bench: adds no right answer |
| ontology | class E27 | site, sites | bench: worse on 1, e.g. her: what is the site type of Golquorn? |
| ontology | class E22 | human-made object, human-made objects | bench: worse on 2, e.g. catalina: what is the object classification of Ruvdrith? |
| ontology | property P140 | assigned attribute to | bench: worse on 10, e.g. catalina: how many artefacts have Mavzabel as assigned attribute to? |
| ontology | property P129i | subject of | bench: worse on 2, e.g. catalina: how many heritage stories are subject of Sendrith? |
| ontology | property P67 | refers to | bench: adds no right answer |

## Dropped by review

| element | phrase | why |
| --- | --- | --- |
| link Artefact.copyright_holder | holds copyright | could name two elements: also proposed for link Artefact.copyright_holder_n1 |
| link Artefact.copyright_holder | hold copyright | could name two elements: also proposed for link Artefact.copyright_holder_n1 |
| link Artefact.copyright_holder | copyright held by | could name two elements: also proposed for link Artefact.copyright_holder_n1 |
| link Artefact.copyright_holder | who holds copyright | could name two elements: also proposed for link Artefact.copyright_holder_n1 |
| link Artefact.copyright_holder_n1 | holds copyright | could name two elements: also proposed for link Artefact.copyright_holder |
| link Artefact.copyright_holder_n1 | hold copyright | could name two elements: also proposed for link Artefact.copyright_holder |
| link Artefact.copyright_holder_n1 | copyright held by | could name two elements: also proposed for link Artefact.copyright_holder |
| link Artefact.copyright_holder_n1 | who holds copyright | could name two elements: also proposed for link Artefact.copyright_holder |
| property P106i | forms part of | could name two elements: already link Monument.parent_monument_or_area |
| property P129 | about | too generic |
| property P148i | component of | could name two elements: already link Monument.parent_monument_or_area |
| property P89i | contains | could name two elements: already link Area.associated_monument_area_or_artefact, link Historic Landscape Characterization.monument_area_or_artefact |
| property P9i | forms part of | could name two elements: already link Monument.parent_monument_or_area |

## Gate checks

- bench: 59 pass alone and together
- demo bank: nothing worse with the 59 passing
- HER plans: 125/125 answers as reviewed

Bench counts: right / wrong reading / refused / right refusal / wrong.

| set | mode | before | after |
| --- | --- | --- | --- |
| lingo | ontology | 33 / 0 / 5 / 2 / 0 | 39 / 0 / 7 / 2 / 0 |
| catalina | ontology | 653 / 0 / 164 / 54 / 0 | 726 / 0 / 191 / 54 / 0 |
| her | ontology | 524 / 0 / 70 / 48 / 0 | 594 / 0 / 86 / 48 / 0 |
| her | ontology+base | 688 / 0 / 100 / 50 / 0 | 844 / 0 / 125 / 51 / 0 |

Demo bank before: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}

Demo bank after: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}
