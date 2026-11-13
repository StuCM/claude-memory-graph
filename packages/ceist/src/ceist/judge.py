"""An LLM marks what each reading of a question means, from Ceist's own narration (bench/run.py only:
never at question time). A disagreement with the count check goes to `settle`, which may answer "unclear"."""

import json

from .pipeline import Runner, _key

PROMPT_VERSION = "1"
BATCH = 20
VERDICTS = ("exact", "wider", "narrower", "wrong", "right refusal", "missed")
SETTLED = VERDICTS + ("unclear",)

_MEANINGS = """\
- exact: the reading asks what the question asks.
- wider: the reading also takes in things the question did not ask for (a condition dropped, a broader type).
- narrower: the reading leaves out things the question asked for (a condition added, a narrower type).
- wrong: the reading asks something else, even if its count happens to match.
- right refusal: Ceist refused, and the question cannot be answered from the data or is not a question.
- missed: Ceist refused, and the question could have been answered."""

PROMPT = """\
You mark whether a question-answering tool understood each question. The tool turns a question into a \
structured query and narrates that query in plain words (its "narration"), or refuses. Judge the narration \
against the question as a careful reader would, not against any count.

Verdicts:
{meanings}

Each input has an id, the question, the narration (null when refused) and, when refused, the reason. \
A "hint" is a hint only.

Reply with ONLY one JSON object, one verdict per id:
{{"verdicts": [{{"id": "<id>", "verdict": "<one of: {names}>", "reason": "<one short sentence>"}}]}}
Check that your reply parses as JSON.

INPUT:
{payload}
"""

SETTLE_PROMPT = """\
A tool answers questions about a dataset by reading each one as a structured query. An earlier judgement \
of this reading disagrees with the check that compared the query's count to an expected count. Settle it.

Verdicts:
{meanings}
- unclear: after the extra facts below you still cannot say; a person must look.

Facts: the question, the narration (null when refused), the refusal reason, the expected count and the note \
on it, what the reading returned, the first judgement and its reason. A matching count can be luck, and a \
mismatch can be a wrong expectation.

Reply with ONLY one JSON object:
{{"verdict": "<one of: {names}>", "reason": "<one short sentence>"}}
Check that your reply parses as JSON.

INPUT:
{payload}
"""


def _payload(item: dict, keys: tuple) -> dict:
    return {k: item[k] for k in keys if item.get(k) is not None}


def _check_batch(ids: list[str]):
    def check(reply) -> list[str]:
        rows = reply.get("verdicts") if isinstance(reply, dict) else None
        if not isinstance(rows, list):
            return ['the reply must be {"verdicts": [...]}']
        errors, seen = [], set()
        for r in rows:
            if not (isinstance(r, dict) and isinstance(r.get("reason"), str)):
                errors.append("each verdict needs an id, a verdict and a reason")
            elif r.get("verdict") not in VERDICTS:
                errors.append(f"{r.get('id')}: verdict must be one of {', '.join(VERDICTS)}")
            else:
                seen.add(str(r.get("id")))
        return errors + [f"no verdict for id {i}" for i in ids if i not in seen]
    return check


def judge(items: list[dict], runner: Runner, model: str) -> list[dict]:
    """A verdict {id, verdict, reason} for each item, in batches of 20; a batch the LLM fails is left out."""
    out = []
    for i in range(0, len(items), BATCH):
        batch = [_payload(x, ("id", "question", "narration", "refused", "hint")) for x in items[i:i + BATCH]]
        ids = [x["id"] for x in batch]
        payload = json.dumps(batch, ensure_ascii=False, indent=1)
        prompt = PROMPT.format(meanings=_MEANINGS, names=", ".join(VERDICTS), payload=payload)
        reply = runner.ask(_key("judge", PROMPT_VERSION, model, payload), prompt, _check_batch(ids),
                           {"kind": "judge", "model": model, "ids": ids})
        if reply:
            out += [{"id": str(r["id"]), "verdict": r["verdict"], "reason": r["reason"]}
                    for r in reply["verdicts"] if str(r["id"]) in ids]
    return out


def settle(item: dict, runner: Runner, model: str) -> dict | None:
    """The second judgement of a disagreement: a verdict (or "unclear") and its reason; None if the LLM fails."""
    keys = ("question", "narration", "refused", "expected", "note", "got", "first", "first_reason")
    payload = json.dumps(_payload(item, keys), ensure_ascii=False, indent=1)
    prompt = SETTLE_PROMPT.format(meanings=_MEANINGS, names=", ".join(SETTLED), payload=payload)

    def check(reply) -> list[str]:
        if isinstance(reply, dict) and reply.get("verdict") in SETTLED and isinstance(reply.get("reason"), str):
            return []
        return [f'the reply must be {{"verdict": one of {", ".join(SETTLED)}, "reason": "..."}}']

    reply = runner.ask(_key("settle", PROMPT_VERSION, model, payload), prompt, check,
                       {"kind": "settle", "model": model, "id": item["id"]})
    return {"id": item["id"], "verdict": reply["verdict"], "reason": reply["reason"]} if reply else None
