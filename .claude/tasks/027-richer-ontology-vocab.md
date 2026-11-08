---
id: 027
slug: richer-ontology-vocab
status: draft
branch: crew/027-richer-ontology-vocab
model: opus
env: laptop
work: ceist-ontology
depends: [025, 026]
files:
  - packages/ceist/
  - vocabularies/
---

# A much richer CIDOC-CRM vocabulary layer

Draft, 2026-11-08. Stu: "Do we want to flesh out the ontology vocab as well? I imagine we can build a much richer one, cidoc CRM is vast."

Direction to confirm when speccing properly, after 026's results:
- **Priority by use, not by size of CRM:** CRM has roughly 80 classes and 160 properties. Rank the CRM *paths* real graphs use (023's audit, 026's graphs, more packages over time) and cover those first. A phrasing nobody's graph reaches is wasted.
- **A build tool, run once:** `ceist vocab ontology` generates phrasings per CRM path from the CRM's own labels and scope notes (public, no client data). It is reviewed by a person and merged into `vocabularies/ontology/cidoc-crm/`. It is built and tested with stubs; Stu runs the live pass when he chooses. It's small: a few hundred short calls on Sonnet, a few dollars at API prices.
- **Gated by the refine loop and 026's bench:** a new ontology phrase is kept only if it adds answers on the fresh-graph bench and breaks nothing on the HER plans or the demo bank.
- **Extensions:** check which CRM version and extensions the graphs use (CRMsci, CRMarchaeo, Linked Art for lingo), and whether they need their own small layers.
- **Property nodes** (P2/E55 "what kind of", P45 "made of") depend on task 025.
