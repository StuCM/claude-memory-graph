---
id: 063
slug: bge-stretch-wrong-answers
status: approved
branch: crew/063-bge-stretch-wrong-answers
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/src/ceist/ground/leftovers.py
  - packages/ceist/src/ceist/matching.py
  - packages/ceist/tests/
  - packages/ceist/bench/her/ceist-bge.toml
---

# The bge matcher must not turn a leftover word into a wrong answer

059 found a **wrong answer** under the demo's bge config (`bench/her/ceist-bge.toml`, threshold 0.3). On the responder practice set, "buildings in the flood footprint" was answered as muster-point buildings: bge stretched the leftover words "flood footprint" to a phrase 059's setup had added. With exact matching it refuses. This breaks never-guess, so it comes before any more vocabulary growth.

- Reproduce it with 059's harness (`/home/stuart/.cache/tmp-059/h/score_setup.py`, the practice set `/home/stuart/.cache/tmp-aonach/responder-practice.json`).
- Find why `_match_leftovers` accepted it:
  - the threshold;
  - the gap between the best and next candidate;
  - a slot where a near miss shouldn't be accepted at all.
- Fix it at the root, so a bge match only places a word when it is genuinely unambiguous.
- Measure bge against exact on the demo bank, the generated sets, the reorder set and both responder sets. **Wrong answers must be 0 under both configs.** Say what bge still adds; if nothing measurable, recommend dropping it from the demo config.

Background:
- the graph Pattern "bge can't rescue awkward refusals" (bge separates poorly: wrong picks score as high as right ones);
- STATUS.md §4.

No `claude -p` or live LLM runs. Run `ponytail-review` before review. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-063`, never `git add -A` or `git stash`, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
