---
id: 060
slug: numeric-comparisons
status: approved
branch: crew/060-numeric-comparisons
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/
  - packages/ceist/tests/
---

# Stub: numeric comparisons ("capacity over 200", "taller than 30 metres", "worth over 5 crore")

The reverse test (`/home/stuart/git/fat/aonach-responder-assessment.md` §2b) found this to be Ceist's biggest gap on Phil's responder data: about 10 of the 25 answerable questions compare a number field. Ceist has no reader for it. aonach gets some right ("shelters with room for 200"), but includes boundary values ("taller than 30 m" counted the four buildings at exactly 30 m).

To decide when specced:
- a numeric reader;
- which fields are numbers, from the graph datatypes;
- the phrasings "over", "under", "at least", "more than", "between", "taller than", "room for";
- strict versus inclusive bounds, stated in the narration;
- units, reusing Phil's `numbers.rs` units and money ("crore", "lakh") with credit;
- the plan condition, and Rós Madair's `range`.

Measure it on the responder set. Wrong answers stay at 0.
