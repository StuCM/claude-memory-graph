---
id: 019
slug: name-matching
status: done
branch: crew/019-name-matching
model: opus
env: laptop
work: tier1-fixes
files:
  - packages/ceist/
gate: pass
gateSha: c85511dab4c70788e54a670fb276bccb55ccdd0c
gateAt: 2026-11-06T20:12:33.460Z
rounds: 1
---

# Match part of a record's name

## Goal
- "show all monuments whose name starts with Cat", "which monuments have fort in the name?" and "which monuments are called Lismahon?" answer by matching record names. Names are already held locally: `vocab.names`, 18,820 in the demo.
- It narrates as "Find Monuments whose name starts with 'Cat'", and combines with other conditions: Rós Madair resolves the rest, then the name filter intersects.
- Case-insensitive, matching words or prefixes.

## Why now
Stu, 2026-11-06: "apply all the fixes we mentioned". Proposed on 2026-11-05 as the name half of text matching. Text inside descriptions stays out of scope.

## Background
- `ground.py` has no text condition today. The `Contains` and `Mention` plan nodes exist for the memory graph's free text, behind `free_text` (010). **Don't re-open free text for Arches vocabularies.** Add a name-only condition that is explicit in the grammar ("name starts with", "in the name", "called").
- The quoted word is the only free text allowed, and only in that slot.

## Definition of done
- [ ] Unit tests: starts with, contains, called, combined with a county, and a bare unknown word still refusing.
- [ ] In the question bank, the Cat question answers. Check the count by hand against `vocab.names`, and update with `--write`.

## Checks every task in this group shares
- **The question bank:** `packages/ceist/bench/demo/questions.json` (87 questions; each says whether it should answer, refuse, or answer once a feature exists). Run it through the demo with your code:
  `cd /home/stuart/git/personal/starches-demo/ask && PYTHONPATH=<worktree>/packages/ceist/src uv run python <worktree>/packages/ceist/bench/demo/run_bank.py`
  It must exit 0: nothing that was right may stop being right, and no new wrong answer. Rerun with `--write` to update the file for the questions your task fixes, and commit it. Put the before and after counts in Worker notes.
- **HER plans** (`bench/her_plans.py`): every diff is justified and re-pinned deliberately. `tests/test_planner.py` passes, and Worker notes say what changed for `memory_ask`.
- **The gate passes.** Machine load: one heavy suite at a time, `TMPDIR=/home/stuart/.cache/tmp-<id>`, never `git add -A` or `git stash`, no servers left running, no pushes. Never run `claude -p` yourself.

## Worker notes
- `ground.py`: new `NameGround` and `_name_match`, gated by the vocabulary flag `name_match` (only `ArchesVocabulary` sets it). Three grammar slots: "(whose|with a) name starts/begins with X" (prefix), "X in the/their/its name" (word) and "called X" (word). X is one word, optionally quoted. Its words are consumed and the span is `taken` before anything else grounds, so nothing else can claim them. A negator scopes over the name match as it does over any other condition.
- `plan.py`: new `NameMatch(term, mode)` with `holds(name)`, which is case-insensitive: a prefix of the whole name, or one of its words split on `[a-z0-9'-]`. `_attach_name` puts it on the plan of the type named just before it (else the subject). `_detail` treats a name match as "more besides".
- `narrate.py`: "whose name starts with 'Cat'" and "whose name has the word 'fort'", plus the negated forms.
- `rosmadair.py`: top-level name matches go to `Compiled.names`, not into the IR. The base query runs unlimited, and `keep_named(ids, compiled, vocab)` filters it on `vocab.names`. `read_back` adds the names back, so `check` is unchanged. A name match inside a hop, or combined with a group-by, raises Unsupported. `ask()` handles it.
- `alizarin.py` filters on `vocab.names`. `arches_search.py` raises Unsupported, so it never skips the condition silently. `__init__` exports NameMatch, and the `vocabulary.py` doc covers the flag.
- Tests (`test_arches.py`): CASES_NAMES (starts with, in the name, called, with a site, negated) runs through Alizarin and Rós Madair end to end. `test_name_matching` covers narration, read-back, no limit, Arches Search refusing, a bare unknown word and a two-word "called" still refusing, and the nested case being Unsupported.
- **Bank** (real demo data and vocab, through a copy of ask.py with the patch below): before 66 answer/right, 1 answer/refused, 7 refuse/right, 13 answer-later refused. After 67 / 1 / 7 / 12, exit 0. The Cat question is now `expect: answer`, `count: 3`, updated with `--write`. Checked by hand against `vocab.names`: the Monument names starting with "cat" are Catherwood'S Fort, Cat'S Causeway and Cathedral Hill. Cathbad (a Figure) and Cath Maige Tuired (a Tale) are excluded by type. Also through the demo: "fort in the name" gives 329 (329 by hand), "called Lismahon" gives 1 (Lismahon, Ballykinler Lower), and "in County Down have fort in the name" gives 86.
- **Demo ask.py patch** (needed, or a name match is silently dropped in the demo): add `keep_named` to the `ceist.rosmadair` import, and after `ids |= linked_from(reader, plan, vocab)` add `ids = keep_named(ids, compiled, vocab)`.
- HER plans (2.0 and 1.1, the archived CI-ref pkgs from tmp-016, bundles rebuilt): 125/125 each, no diffs. "What's the place called?" has no word after "called", so it doesn't match.
- memory_ask: unchanged. MemoryVocabulary doesn't set `name_match`, and test_planner passes (gate: root 564 passed, ceist 259 passed).
- Not done: "called Cat" doesn't match "Cat's Causeway" (word mode keeps the apostrophe), which errs narrow. Multi-word names ("called Navan Fort") refuse.
- **Rebased onto ceist-foundation after 018 (near) merged.** There were conflicts in alizarin, ground, narrate, plan and rosmadair; I resolved them by hand, keeping both `Near`/`keep_near` and `NameMatch`/`keep_named`. Since 018, alizarin's `_filter` raises TypeError on an unknown condition, so the NameMatch branch sits before it. **Near + name is supported:** both are client-side filters on the resolved ids, so they intersect. Tests (`test_near_and_a_name_match_both_hold`, plus a line in `test_end_to_end_near`) cover the narration, read-back, Alizarin and Rós Madair. In the demo, "which monuments near Armagh have fort in the name?" gives 4 (161 near, then by hand: Haughey'S Fort, Knockaconey Fort, Navan Fort, The Hospice Or Fort Of The Guests).
- **After the rebase:** bank (with the 018-patched live ask.py plus the patch below) went from 67/1/7/12 (the post-018 baseline) to 68 answer/right, 1 answer/refused, 7 refuse/right, 11 answer-later refused, 0 wrong, exit 0. HER plans 2.0 and 1.1 are 125/125 each with no diffs. The gate passed on c85511d (ceist 270 passed).
- **Demo patch against the current live ask.py** (supersedes the one above), also at `/home/stuart/.cache/tmp-019/ask-name.patch`: add `keep_named` to the `ceist.rosmadair` import, and replace `ids = keep_near(ids, compiled, vocab)` with `ids = keep_named(keep_near(ids, compiled, vocab), compiled, vocab)`.

## Graph writes proposed
- Pattern: a condition Rós Madair's IR can't hold, but that the client can check per record (name matching on `vocab.names`), is kept beside the query in `Compiled` and filtered after resolve. The base query must then run without a limit, and read-back must re-add the condition. Every runner (rosmadair.ask, the demo's ask.py) must call the filter.

## Review rounds
- Round 1: PASS. Non-blocking: word mode won't match "Cat's" for "called Cat" (narrow, never wider).
- Round 2 (after rebase onto ceist-foundation e3c8a81): PASS. 017, 018 and 020 intact. 270 tests pass with the Rós Madair emitter. Merge clean. Non-blocking: the name+group-by refusal has no test of its own.
