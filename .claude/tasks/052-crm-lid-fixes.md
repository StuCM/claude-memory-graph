---
id: 052
slug: crm-lid-fixes
status: draft
branch: crew/052-crm-lid-fixes
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/crm.py
  - packages/ceist/src/ceist/arches.py
---

# Stub: three small fixes to the CRM fallback lid (when Catalina or another loosely configured graph matters)

From `packages/ceist/CRM-LID-CHECK.md` (2026-11-09):
1. Read the class hierarchy from the RDFS files in `vocabularies/ontology/cidoc-crm/source/`, not from the hand-written `PARENTS` (crm.py:96). The hand list misses E78, ZE13 and the S20 places.
2. Test one way (the root class falls within the link's class), not "no clash" both ways (crm.py:119).
3. Treat "no model fits" as none, not as any (arches.py:389-396). Investigate the "What period is Navan Fort?" reading first: a property-range lid turned that refusal into a wrong answer.

Also: implicit joins in assemble.py:196 ignore CRM-narrowed targets.

Measure on the demo bank and HER plans (no change expected) and on Catalina's fresh-graph bench.
