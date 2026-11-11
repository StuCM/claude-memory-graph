---
id: 062
slug: llm-via-ant-with-cap
status: approved
branch: crew/062-llm-via-ant-with-cap
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/src/ceist/pipeline.py
  - packages/ceist/src/ceist/cost.py
  - packages/ceist/src/ceist/cli.py
  - packages/ceist/src/ceist/prices.py
  - packages/ceist/tests/
  - packages/ceist/VOCAB-TRAINING.md
---

# Build-time LLM calls through the `ant` CLI on API credits, with a hard dollar cap that must be given

## Goal
Stu, 2026-11-10/11: use his API credits (about $105, with a $50 spend limit set on the account) for vocabulary builds, to spare the weekly subscription limit, **without any risk of an accidental charge**. He is logged in with the Anthropic CLI, `ant` (v2.9.0, OAuth profile `default`, scope `user:inference`). Today every LLM call goes through `claude -p` (`pipeline.py` `CLAUDE`), which uses his subscription and adds about 33k tokens of system prompt per call.

1. **An `ant` backend:** `--llm ant` on every command that makes LLM calls:
   - `vocab pipeline`;
   - `vocab ontology build` / propose;
   - `questions generate`;
   - 059's `setup --llm` and paraphrase fill.

   Each call runs `ant messages create` as a subprocess, with the same prompts `claude -p` gets but **no Claude Code system prompt**. **Ceist never reads, stores or passes a token:** `ant` holds the auth. Parse the reply and its `usage`.
2. **A hard dollar cap that must be given.** `--llm ant` refuses to start without `--max-dollars N`.
   - **Before every call,** add the worst case for that call (input tokens + `max_tokens` output, at the model's price from `prices.py`) to the run's spend so far, as recorded in the cost ledger. If it would pass N, stop cleanly, saying what was done and what wasn't.
   - **Record the real cost** from `usage` after each call.
   - Print the estimate (`vocab estimate`, now **without** the `claude -p` overhead for `ant`) and the cap before the first call.
3. **`claude -p` stays the default.** `ant` is only used when asked for. `--llm-cmd` stubs keep working, for tests.
4. **Tests** use a fake `ant` on PATH that returns canned JSON with `usage`:
   - refusal without `--max-dollars`;
   - stopping before a call that would pass the cap;
   - the ledger recording real usage;
   - no token ever appearing in argv, logs or the ledger.
5. **`VOCAB-TRAINING.md`:** how to use `ant`, and the safety layers. The account's own spend limit and auto-reload setting are Stu's; the tool's cap sits inside them.

## Background
- **Read first:** `pipeline.py` (`CLAUDE`, the LLM class around line 289, the JSON parsing), `cost.py` (the ledger, estimates), `prices.py`, and 030's and 059's Worker notes.
- `ant messages create --help` lists the flags (`--model`, `--max-tokens`, `--message`, and so on).
- **Make no live `ant` call in this task:** use the fake only. Stu approves the first live run separately (the Sonnet base layer for Phil's graphs, with a cap).
- Run `ponytail-review` before the review round. Follow Stu's code style rules (`~/.claude/CLAUDE.md`), with descriptive names.
- This runs after 059 (both touch `cost.py` and `cli.py`).

## Definition of done
- [ ] The `ant` backend, the required cap and the ledger are tested with a fake `ant`. No token appears anywhere Ceist writes.
- [ ] `VOCAB-TRAINING.md` is updated.
- [ ] The gate passes. Machine load: at most 2 processes, `TMPDIR=/home/stuart/.cache/tmp-062`, never `git add -A` or `git stash`, no servers left running, no pushes.

## Worker notes

## Graph writes proposed

## Review rounds
