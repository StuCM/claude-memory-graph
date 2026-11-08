# Ontology build report

Graphs: /home/stuart/.cache/tmp-003/arches-her/arches_her/pkg/graphs/resource_models, /home/stuart/git/fat/arches/catalina/catalina-graphs/output/graphs/resource_models, /home/stuart/git/fat/arches/arches-lingo/arches_lingo/pkg/graphs/resource_models, /home/stuart/git/personal/starches-demo/ask/data/graphs.

Estimate: 257 paths (6971 nodes), 257 cached: 0 calls, up to 0 with retries, about $0.00 (--max-calls 300)

Generated: 100 proposals, 157 skipped by the LLM → vocabularies/ontology/cidoc-crm/proposed.json; LLM calls 0; 257 paths from the cache; 0 failed

Proposed: 100 paths with phrasings; 157 skipped by the LLM; not proposed: 220 already phrased, 814 outside CIDOC-CRM and CRMsci.

## Review

107 proposals reviewed: 59 kept whole, 35 trimmed, 13 dropped.

| verdict | kind | path | kept | dropped |
| --- | --- | --- | --- | --- |
| trimmed | property | P104 E30 P2 | licensed under, rights status, type of rights | licence (a bare noun, and the path reaches several fields in a model); license (a bare noun, and the path reaches several fields in a model) |
| kept | property | P126 E57 P2 | material type, type of material, material category, class of material |  |
| kept | property | P106 E33 P72 | language, written in, in the language |  |
| trimmed | property | O18i E11 P126 | built of, built from, constructed of | material (too generic) |
| kept | property | O18i E11 P33 | construction technique, building technique, construction method, built using |  |
| trimmed | property | P8i E7 P2 | event type, activity type | events held (too generic); activities held (too generic) |
| kept | property | P40 E54 P2 | dimension type, type of measurement, dimension measured |  |
| trimmed | property | E7 P2 | type of activity, kind of activity | activity type (shared by 4 sibling paths; kept on P8i E7 P2) |
| kept | property | E74 P2 | organisation type, organization type, type of organisation, kind of group |  |
| trimmed | link | E33 P67i | referenced in | referred to in (shared by 2 sibling paths; kept on P67i); cited in (shared by 2 sibling paths; kept on P67i); references (clash: already on P67i E73) |
| kept | property | O18i E11 P2 | modification type, alteration type, type of alteration, type of work |  |
| dropped | property | E33 P72 |  | language (shared by 2 sibling paths; kept on P106 E33 P72); written in (shared by 2 sibling paths; kept on P106 E33 P72); in the language (shared by 2 sibling paths; kept on P106 E33 P72) |
| kept | link | O18i E11 P10 | built during, constructed during, construction period |  |
| trimmed | link | E21 P11i | participant in | involved in (too generic); took part in (shared by 2 sibling paths; kept on P11i); participated in (shared by 2 sibling paths; kept on P11i) |
| kept | property | E24 P2 | object type, type of object, kind of object |  |
| kept | link | E24 P8i | witnessed, scene of, site of |  |
| kept | property | O19i S19 P32 | recovery method, method of recovery, found using, discovery method, recovered by |  |
| trimmed | property | P108i E12 P32 | production technique, made using, method of manufacture | technique (a bare noun, and the path reaches several fields in a model) |
| dropped | link | E33 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); discussed in (shared by 2 sibling paths; kept on P129i); written about in (shared by 6 sibling paths; kept on P129i) |
| dropped | link | E53 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); described in (shared by 6 sibling paths; kept on P129i); the subject of (shared by 6 sibling paths; kept on P129i); documented in (shared by 6 sibling paths; kept on P129i) |
| kept | property | E53 P2 | place type, type of place, site type, kind of place |  |
| kept | property | O18i E11 P32 | construction technique, construction method, building technique, built using |  |
| kept | property | P31 E24 P2 | type of object modified, kind of thing altered, modified object type |  |
| kept | property | P31 E24 P45 | material of object modified, material altered, modified object material |  |
| trimmed | property | P45 E57 P2 | kind of material | material type (shared by 2 sibling paths; kept on P126 E57 P2); material category (shared by 2 sibling paths; kept on P126 E57 P2) |
| kept | link | P94i E65 P16 | based on, drawn from, made using, source material |  |
| dropped | link | E27 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); described in (shared by 6 sibling paths; kept on P129i); the subject of (shared by 6 sibling paths; kept on P129i); documented in (shared by 6 sibling paths; kept on P129i) |
| kept | property | E33 P103 | intended for, intended use, purpose, meant for |  |
| trimmed | link | E33 P67 | refers to, makes reference to | mentions (clash: already on P129 E18) |
| dropped | link | E18 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); described in (shared by 6 sibling paths; kept on P129i); the subject of (shared by 6 sibling paths; kept on P129i); documented in (shared by 6 sibling paths; kept on P129i) |
| dropped | link | E22 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); described in (shared by 6 sibling paths; kept on P129i); the subject of (shared by 6 sibling paths; kept on P129i); documented in (shared by 6 sibling paths; kept on P129i) |
| trimmed | link | E24 P67i | mentioned in | referred to in (shared by 2 sibling paths; kept on P67i); cited in (shared by 2 sibling paths; kept on P67i) |
| kept | link | E7 P15 | influenced by, inspired by, influence |  |
| kept | property | P107 E21 P2 | member type, type of member, kind of member |  |
| kept | property | P12i E13 P32 | analysis technique, method of analysis, analysed using, examination method |  |
| kept | property | E4 P2 | period type, type of period, kind of period |  |
| kept | property | P129i E29 P2 | plan type, type of plan, design type, kind of plan |  |
| trimmed | property | P17 E33 P2 | motivated by, prompted by | motivation (too generic); reason (a bare noun, and the path reaches several fields in a model) |
| trimmed | property | P7 E53 P2 | location type | place type (shared by 2 sibling paths; kept on E53 P2); type of place (shared by 2 sibling paths; kept on E53 P2); kind of place (shared by 2 sibling paths; kept on E53 P2) |
| kept | property | P93i E81 P2 | transformation type, type of transformation, transformed into, converted into |  |
| trimmed | property | P94 E33 P2 | text type, type of text, kind of text | genre (a bare noun, and the path reaches several fields in a model) |
| trimmed | link | E33 P129 | on the subject of, deals with | about (too generic); subject (too generic) |
| trimmed | link | E18 P12i | took part in, witnessed | was at (too generic); present at (shared by 3 sibling paths; kept on P12i) |
| trimmed | link | E18 P16i | used in, used during, employed in | used for (shared by 2 sibling paths; kept on P16i) |
| trimmed | property | E18 P2 | type of thing | object type (shared by 3 sibling paths; kept on E24 P2); type of object (shared by 3 sibling paths; kept on E24 P2); kind of object (shared by 3 sibling paths; kept on E24 P2) |
| dropped | link | E22 P12i |  | was at (too generic); present at (shared by 3 sibling paths; kept on P12i); featured in (shared by 2 sibling paths; kept on P12i) |
| trimmed | property | E22 P2 | object classification | object type (shared by 3 sibling paths; kept on E24 P2); type of object (shared by 3 sibling paths; kept on E24 P2); kind of object (shared by 3 sibling paths; kept on E24 P2) |
| kept | link | E27 P12i | scene of, site of, venue for |  |
| dropped | link | E27 P16i |  | use (too generic); used for (shared by 2 sibling paths; kept on P16i); used as (clash: already on P12i E5 P41i E17 P42) |
| kept | link | E27 P59i | located on, found on |  |
| dropped | link | E74 P11i |  | involved in (too generic); took part in (shared by 2 sibling paths; kept on P11i); participated in (shared by 2 sibling paths; kept on P11i) |
| trimmed | property | P11i E7 P2 | took part in, participated in | activity type (shared by 4 sibling paths; kept on P8i E7 P2); type of activity (shared by 3 sibling paths; kept on E7 P2) |
| kept | property | P128 E34 P72 | inscription language, language of the inscription, inscribed in, inscription in |  |
| kept | date | P34i E14 P4 | assessed, condition assessed, date of assessment, surveyed |  |
| kept | property | P35 E3 P2 | condition, state of preservation, condition state, state |  |
| kept | property | P73 E33 P72 | translated into, translation language, language of translation |  |
| dropped | link | E24 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); written about in (shared by 6 sibling paths; kept on P129i); described in (shared by 6 sibling paths; kept on P129i); documented in (shared by 6 sibling paths; kept on P129i) |
| dropped | link | E7 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); written about in (shared by 6 sibling paths; kept on P129i); described in (shared by 6 sibling paths; kept on P129i); documented in (shared by 6 sibling paths; kept on P129i) |
| trimmed | link | E24 P12i | used at | involved in (too generic); present at (shared by 3 sibling paths; kept on P12i); featured in (shared by 2 sibling paths; kept on P12i) |
| trimmed | property | E27 P2 | type of site, kind of site | site type (shared by 2 sibling paths; kept on E53 P2) |
| trimmed | link | E33 P106i | excerpt from, extract from | forms part of (clash: already on P46i) |
| trimmed | link | E4 P10 | sub-period of, phase of | falls within (clash: already on E53 P89 E53) |
| kept | date | E4 P4 | date range, spanned, lasted, period dates |  |
| kept | link | E53 P53i | location of, site of, home to, houses |  |
| kept | link | E53 P7i | witnessed, scene of, setting of, periods witnessed |  |
| kept | link | E7 P118 | overlapped with, overlaps in time with, concurrent with, contemporary with |  |
| kept | property | E7 P16 | tools used, equipment used, used in the activity, instruments used |  |
| trimmed | link | E7 P17 | reason for | motivation (too generic); motivated by (shared by 2 sibling paths; kept on P17); prompted by (shared by 2 sibling paths; kept on P17) |
| kept | link | E7 P17i | motivated, prompted, led to |  |
| kept | property | P25 E19 P2 | object moved, type of object moved, moved object type |  |
| trimmed | property | P41i E17 P42 | classified as | type (too generic); kind (too generic); classification (too generic); category (too generic) |
| kept | link | P9 E7 P11 | participant, participants, attended by, with participation of |  |
| kept | date | P93i E81 P4 | transformed, converted, date transformed, transformation date |  |
| kept | link | P93i E81 P92 | transformed into, converted into, turned into, became |  |
| trimmed | link | E21 P129i | biography | subject of (shared by 10 sibling paths; kept on P129i); written about in (shared by 6 sibling paths; kept on P129i); the subject of (shared by 6 sibling paths; kept on P129i) |
| trimmed | property | E33 P129 | topic, subject matter | subject (too generic); about (too generic) |
| dropped | link | E4 P129i |  | subject of (shared by 10 sibling paths; kept on P129i); discussed in (shared by 2 sibling paths; kept on P129i); written about in (shared by 6 sibling paths; kept on P129i); the subject of (shared by 6 sibling paths; kept on P129i) |
| trimmed | link | E5 P16 | made use of, instruments used | used (too generic); objects used (shared by 2 sibling paths; kept on P16) |
| trimmed | link | E5 P17 | occasioned by, reason | motivation (too generic); motivated by (shared by 2 sibling paths; kept on P17); prompted by (shared by 2 sibling paths; kept on P17) |
| kept | date | E5 P4 | happened, took place, occurred, event date |  |
| kept | link | E5 P67i | documented in, described in, recorded in |  |
| kept | link | E7 P14 | carried out by, conducted by, undertaken by, led by |  |
| trimmed | link | E7 P16 | equipment used | used (too generic); made use of (shared by 3 sibling paths; kept on E5 P16); objects used (shared by 2 sibling paths; kept on P16) |
| trimmed | link | E74 P129i | featured in | subject of (shared by 10 sibling paths; kept on P129i); written about in (shared by 6 sibling paths; kept on P129i) |
| kept | property | O18i E11 P10 | altered during, modified during, period of alteration |  |
| kept | link | P100i E69 P117 | died during, death during |  |
| kept | property | P100i E69 P2 | manner of death, type of death, kind of death, died of |  |
| kept | link | P100i E69 P67i | death recorded in, death documented in, death mentioned in |  |
| kept | link | P100i E69 P7 | died in, died at, place of death |  |
| trimmed | property | P129i E30 P2 | type of right, rights type, copyright status | licence (shared by 2 sibling paths; kept on P104 E30 P2); license (shared by 2 sibling paths; kept on P104 E30 P2) |
| kept | link | P14i E7 P117 | active during, worked during |  |
| dropped | link | P14i E7 P16 |  | used (too generic); made use of (shared by 3 sibling paths; kept on E5 P16) |
| trimmed | property | P14i E7 P2 | activity, activities | activity type (shared by 4 sibling paths; kept on P8i E7 P2); type of activity (shared by 3 sibling paths; kept on E7 P2) |
| trimmed | property | P14i E7 P32 | techniques used, works in, practised technique, practiced technique | technique (shared by 2 sibling paths; kept on P108i E12 P32) |
| kept | date | P14i E7 P4 | active, flourished, date active, period of activity |  |
| kept | link | P14i E7 P7 | active in, worked in, place of activity |  |
| kept | link | P98i E67 P117 | born during, born in the period, period of birth |  |
| kept | property | P98i E67 P2 | type of birth, birth type, kind of birth |  |
| kept | link | P98i E67 P67i | birth recorded in, birth record, birth certificate |  |
| kept | link | P98i E67 P7 | born in, born at, place of birth, birthplace |  |
| trimmed | link | P67i | referred to in | cited in (clash: already on P67i E73) |
| kept | link | P11i | took part in, participated in |  |
| kept | link | P129i | subject of, discussed in, written about in, described in, the subject of, documented in |  |
| kept | link | P12i | present at, featured in |  |
| kept | link | P16i | used for |  |
| kept | link | P17 | motivated by, prompted by |  |
| kept | link | P16 | objects used |  |

### Needs a hand phrasing

Date paths reaching 10 or more nodes that the LLM skipped:

| path | nodes | the LLM's reason |
| --- | --- | --- |
| P4 E52 P86i | 44 | Structural nesting of one time-span inside another; it is not a question about when anything happened, so it is too general to mean one thing. |
| P140i E13 P4 | 37 | Date an attribute was assigned to the thing. That is record-keeping about an assessment, not about the thing itself. |
| P140i E13 P141 | 23 | Any value assigned in a generic attribute assignment. Too general to mean one thing. |
| P9 E7 P4 | 20 | Time-span of some unspecified sub-activity of a period or event. Too general to mean one thing. |
| P140i E17 P17 | 18 | What motivated a classification act. This is cataloguing provenance, not something people ask about the thing. |
| P141i E13 P141 | 15 | Other values assigned in the same generic attribute assignment. This is audit metadata and too general. |

## Rejected by the gate

| kind | path | phrases | why |
| --- | --- | --- | --- |
| property | O18i E11 P126 | built of, built from, constructed of | bench: adds no right answer |
| property | O18i E11 P33 | construction technique, building technique, construction method, built using | bench: adds no right answer |
| property | E7 P2 | type of activity, kind of activity | bench: adds no right answer |
| link | E21 P11i | participant in | bench: adds no right answer |
| property | O19i S19 P32 | recovery method, method of recovery, found using, discovery method, recovered by | bench: adds no right answer |
| property | P108i E12 P32 | production technique, made using, method of manufacture | bench: adds no right answer |
| property | O18i E11 P32 | construction technique, construction method, building technique, built using | bench: worse on 2, e.g. her: what is the construction method of Mavdrith? |
| link | E33 P67 | refers to, makes reference to | bench: adds no right answer |
| link | E24 P67i | mentioned in | bench: adds no right answer |
| property | P107 E21 P2 | member type, type of member, kind of member | bench: adds no right answer |
| property | E4 P2 | period type, type of period, kind of period | bench: adds no right answer |
| property | P129i E29 P2 | plan type, type of plan, design type, kind of plan | bench: adds no right answer |
| property | P17 E33 P2 | motivated by, prompted by | bench: adds no right answer |
| property | P7 E53 P2 | location type | bench: adds no right answer |
| property | P93i E81 P2 | transformation type, type of transformation, transformed into, converted into | bench: adds no right answer |
| property | P94 E33 P2 | text type, type of text, kind of text | bench: adds no right answer |
| property | E18 P2 | type of thing | bench: worse on 2, e.g. catalina: what is the type of Mavquorn? |
| property | P11i E7 P2 | took part in, participated in | bench: adds no right answer |
| property | P73 E33 P72 | translated into, translation language, language of translation | bench: adds no right answer |
| link | E33 P106i | excerpt from, extract from | bench: adds no right answer |
| date | E4 P4 | date range, spanned, lasted, period dates | bench: adds no right answer |
| link | P9 E7 P11 | participant, participants, attended by, with participation of | bench: worse on 1, e.g. her: which consultations were attended by Brynquorn? |
| property | O18i E11 P10 | altered during, modified during, period of alteration | bench: adds no right answer |
| property | P14i E7 P2 | activity, activities | bench: worse on 2, e.g. catalina: what is the activities of Mavzabel? |
| link | P129i | subject of, discussed in, written about in, described in, the subject of, documented in | bench: worse on 7, e.g. catalina: how many heritage stories are subject of Sendrith? |

## Accepted into phrases.json

| kind | path | phrases |
| --- | --- | --- |
| property | P104 E30 P2 | licensed under, rights status, type of rights |
| property | P126 E57 P2 | material type, type of material, material category, class of material |
| property | P106 E33 P72 | language, written in, in the language |
| property | P8i E7 P2 | event type, activity type |
| property | P40 E54 P2 | dimension type, type of measurement, dimension measured |
| property | E74 P2 | organisation type, organization type, type of organisation, kind of group |
| link | E33 P67i | referenced in |
| property | O18i E11 P2 | modification type, alteration type, type of alteration, type of work |
| link | O18i E11 P10 | built during, constructed during, construction period |
| property | E24 P2 | object type, type of object, kind of object |
| link | E24 P8i | witnessed, scene of, site of |
| property | E53 P2 | place type, type of place, site type, kind of place |
| property | P31 E24 P2 | type of object modified, kind of thing altered, modified object type |
| property | P31 E24 P45 | material of object modified, material altered, modified object material |
| property | P45 E57 P2 | kind of material |
| link | P94i E65 P16 | based on, drawn from, made using, source material |
| property | E33 P103 | intended for, intended use, purpose, meant for |
| link | E7 P15 | influenced by, inspired by, influence |
| property | P12i E13 P32 | analysis technique, method of analysis, analysed using, examination method |
| link | E33 P129 | on the subject of, deals with |
| link | E18 P12i | took part in, witnessed |
| link | E18 P16i | used in, used during, employed in |
| property | E22 P2 | object classification |
| link | E27 P12i | scene of, site of, venue for |
| link | E27 P59i | located on, found on |
| property | P128 E34 P72 | inscription language, language of the inscription, inscribed in, inscription in |
| date | P34i E14 P4 | assessed, condition assessed, date of assessment, surveyed |
| property | P35 E3 P2 | condition, state of preservation, condition state, state |
| link | E24 P12i | used at |
| property | E27 P2 | type of site, kind of site |
| link | E4 P10 | sub-period of, phase of |
| link | E53 P53i | location of, site of, home to, houses |
| link | E53 P7i | witnessed, scene of, setting of, periods witnessed |
| link | E7 P118 | overlapped with, overlaps in time with, concurrent with, contemporary with |
| property | E7 P16 | tools used, equipment used, used in the activity, instruments used |
| link | E7 P17 | reason for |
| link | E7 P17i | motivated, prompted, led to |
| property | P25 E19 P2 | object moved, type of object moved, moved object type |
| property | P41i E17 P42 | classified as |
| date | P93i E81 P4 | transformed, converted, date transformed, transformation date |
| link | P93i E81 P92 | transformed into, converted into, turned into, became |
| link | E21 P129i | biography |
| property | E33 P129 | topic, subject matter |
| link | E5 P16 | made use of, instruments used |
| link | E5 P17 | occasioned by, reason |
| date | E5 P4 | happened, took place, occurred, event date |
| link | E5 P67i | documented in, described in, recorded in |
| link | E7 P14 | carried out by, conducted by, undertaken by, led by |
| link | E7 P16 | equipment used |
| link | E74 P129i | featured in |
| link | P100i E69 P117 | died during, death during |
| property | P100i E69 P2 | manner of death, type of death, kind of death, died of |
| link | P100i E69 P67i | death recorded in, death documented in, death mentioned in |
| link | P100i E69 P7 | died in, died at, place of death |
| property | P129i E30 P2 | type of right, rights type, copyright status |
| link | P14i E7 P117 | active during, worked during |
| property | P14i E7 P32 | techniques used, works in, practised technique, practiced technique |
| date | P14i E7 P4 | active, flourished, date active, period of activity |
| link | P14i E7 P7 | active in, worked in, place of activity |
| link | P98i E67 P117 | born during, born in the period, period of birth |
| property | P98i E67 P2 | type of birth, birth type, kind of birth |
| link | P98i E67 P67i | birth recorded in, birth record, birth certificate |
| link | P98i E67 P7 | born in, born at, place of birth, birthplace |
| link | P67i | referred to in |
| link | P11i | took part in, participated in |
| link | P12i | present at, featured in |
| link | P16i | used for |
| link | P17 | motivated by, prompted by |
| link | P16 | objects used |

## Bench and demo bank

Bench counts: right / wrong reading / refused / right refusal / wrong.

| set | mode | before | after |
| --- | --- | --- | --- |
| lingo | ontology | 22 / 0 / 0 / 2 / 0 | 33 / 0 / 5 / 2 / 0 |
| catalina | ontology | 298 / 0 / 39 / 25 / 0 | 646 / 0 / 143 / 47 / 0 |
| her | ontology | 257 / 0 / 8 / 26 / 0 | 518 / 0 / 52 / 42 / 0 |
| her | ontology+base | 253 / 0 / 12 / 26 / 0 | 508 / 0 / 62 / 42 / 0 |

Demo bank before: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}

Demo bank after: {('answer', 'right'): 71, ('answer', 'refused'): 1, ('refuse', 'right'): 7, ('answer-later', 'refused-should-answer'): 11}

- bench: 69 pass alone and together
- demo bank: unchanged with the 69 passing
- HER plans: 125/125 answers as reviewed

## Cost

| stage | calls | from the cache | input | cache read | cache write | output | dollars |
| --- | --- | --- | --- | --- | --- | --- | --- |
| total | 0 | 0 | 0 | 0 | 0 | 0 | $0.00 |

Dollars are API list prices; on a Claude subscription they are usage, not a bill.

## The estimate against past runs

| run | stage | model | calls | input est | input actual | output est | output actual | dollars est | dollars actual | error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| /home/stuart/.cache/tmp-033/ontology-run | ontology | ? | 26 | 74974 | estimated, not measured | 52000 | | $1.34 | | |
