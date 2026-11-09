---
id: 054
slug: pluggable-ontologies
status: draft
branch: crew/054-pluggable-ontologies
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/src/ceist/
  - vocabularies/ontology/
---

# Stub: the ontology layer for any RDFS/OWL ontology, not only CIDOC-CRM

After 053. Stu, 2026-11-09: "we can iterate and build vocabs for various ontologies. I truly feel this tool has so many uses across a wide variety of areas."

Settled (Stu, 2026-11-09):
- **one vocabulary per ontology**, in `vocabularies/ontology/<name>/`;
- an extension or profile (CRMsci over CRM, Linked Art over CRM) holds only its additions and names its parent;
- a site declares its ontology, and the build stacks ontology (with its parent) → graph delta → site terms into one runtime vocabulary.

To decide when specced:
- What is CRM-specific today: `crm.py`'s hand-written PARENTS, the CRM/CRMsci file loading, the path keys, and the O-codes. A generic version reads the class and property hierarchy and labels from any RDFS/OWL file into `vocabularies/ontology/<name>/`.
- **A second ontology, to prove it is general.** Candidates:
  - the memory graph's own ontology, whose relations already carry verb forms (`memory_link` `new_relation_verb_forms`), making it the cheapest test;
  - Linked Art (CRM-based, for museums);
  - schema.org, SKOS or PROV.
- How a site declares which ontology its graphs use.

Measure: the memory graph's planner tests and `memory_ask` answers using the generic ontology layer, against today's.
