"""Extension: periodic graph self-review.

The project already computes a lot of numbers — gaps (orphans, conceptless
nodes, sentence-shaped names), coverage, misses, pulse. Every one of them
was only ever read when a human remembered to look, which is why the
naming rule drifted for two months and the grounding metric sat unrun
since July. This extension supplies the missing half: the *timer*.

Division of labour, unchanged from the rest of the system — **detection is
mechanical, judgment is the LLM's**. The hook computes nothing new; it
reuses gaps.analyse and hands the headline numbers to a session with an
instruction to act. Renaming a node, linking two nodes, deciding a metric
has drifted: all judgment, all the model's, all through tools that already
exist.

Why a Stop block rather than a SessionStart line: the same reason the
context nudge escalated to one. A line injected at session start competes
with the user's actual request and loses. This fires at most once every
REVIEW_EVERY_DAYS (cross-session state), and only when there is something
to say — a clean graph is silent.

ponytail: an ignored ask still resets the clock, so a skipped review costs
a full period. Key it to observed graph mutations if that proves too lossy.
"""

import time

from claude_hook_kit import HookContext, HookExtension, append_jsonl

from .nudge import _context_dir
from .runtime import config, store_dir


class ReviewExtension(HookExtension):
    """Periodic graph self-review: mechanical numbers, model judgment."""

    name = "graph-review"
    enabled_by_default = False

    def _due(self, ctx: HookContext) -> bool:
        period = config()["REVIEW_EVERY_DAYS"] * 86400
        last = ctx.global_state.get("last_review", 0)
        return time.time() - last >= period

    def _shape(self, ctx: HookContext) -> tuple[int, int]:
        """Capture-side quality, alongside the graph-side detectors: the
        structured share is what decides how much of the log can ever be
        promoted without an LLM."""
        try:
            from ..context_entries import shape_stats
            window = time.time() - config()["REVIEW_EVERY_DAYS"] * 86400
            return shape_stats(_context_dir(), since=window)
        except Exception:
            return 0, 0

    def on_stop(self, ctx: HookContext) -> str | None:
        if ctx.stop_hook_active or ctx.state.get("reviewed") or not self._due(ctx):
            return None
        try:
            from ..gaps import analyse
            from ..store import MemoryStore
            gaps = analyse(MemoryStore.open_or_create(store_dir()), limit=5)
        except Exception:
            return None  # fail open: a broken report never blocks a session

        findings = []
        structured, narrative = self._shape(ctx)
        total = structured + narrative
        if total:
            share = structured / total
            if share < config()["CAPTURE_SHAPE_MIN"]:
                findings.append(
                    f"only {share:.0%} of the {total} entries in the active "
                    f"context log use the structured shape — narrative bullets "
                    "cannot be promoted mechanically, so they become distill "
                    "residue and pin their file open. Re-read the entry format "
                    "in the Stop block and use it")
        if gaps.long_name_total:
            worst = "; ".join(f"{w}w '{n}'" for w, _m, n in gaps.long_names[:3])
            findings.append(
                f"{gaps.long_name_total} node names are over the word ceiling "
                f"(worst: {worst}) — every word of a name joins the retrieval "
                "vocabulary, so these make recall noisier for every other node")
        if gaps.orphans:
            findings.append(
                f"{len(gaps.orphans)} orphan node(s) with no links at all — "
                "unreachable by traversal")
        if gaps.conceptless:
            findings.append(
                f"{len(gaps.conceptless)} node(s) with no concept link — "
                "invisible to associative recall")
        if gaps.suggestions:
            findings.append(
                f"{len(gaps.suggestions)} unlinked pair(s) sharing rare "
                "vocabulary — traversals the graph is silently missing")
        if not findings:
            ctx.global_state["last_review"] = time.time()
            return None  # nothing to say; don't spend a turn saying it

        ctx.state["reviewed"] = True
        ctx.global_state["last_review"] = time.time()
        append_jsonl("capture.jsonl", {
            "kind": "review", "findings": len(findings),
            "long_names": gaps.long_name_total, "orphans": len(gaps.orphans),
            "session": ctx.core.get("session_id", ""), "project": ctx.project})
        bullets = "\n".join(f"- {f}" for f in findings)
        return (f"[review] {config()['REVIEW_EVERY_DAYS']}-day memory-graph "
                f"health check — the mechanical detectors found:\n{bullets}\n\n"
                "Before finishing this turn, run the /memory-graph:reflect skill "
                "and fix the worst handful — memory_rename for over-long names, "
                "memory_link / memory_store_concept for the rest — then get back "
                "to the user's task. Fix a handful, not all of it; this fires "
                "again next period.\n"
                "Renaming goes through memory_rename ONLY. memory_store_resource "
                "upserts BY NAME, so storing a shorter name creates a second, "
                "linkless node and leaves the original in place.")
