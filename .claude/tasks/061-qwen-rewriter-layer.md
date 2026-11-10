---
id: 061
slug: qwen-rewriter-layer
status: draft
branch: crew/061-qwen-rewriter-layer
model: opus
env: laptop
work: ceist-port
files:
  - packages/ceist/
---

# Stub: a Qwen rewriter in front of Ceist, constrained to Ceist's own wording

After 059, 060, the Sonnet base layer and the retest on Phil's data. Stu, 2026-11-10: "then after that lets look at building the qwen layer in to restructure for ceist".

The design is from the aonach assessment (`/home/stuart/git/fat/aonach-responder-assessment.md` §4, tiered design):
- **It fires only when Ceist refuses or asks "did you mean".** The normal route is unchanged.
- **Qwen rewrites the question into Ceist's canonical wording**, under a GBNF grammar generated from the site's vocabulary and narration templates: the sentences Ceist can read (OVERNIGHT canonical utterances; Shin et al. 2021 constrained decoding, credited in `PRIOR-ART.md`). It **never emits the plan or query directly**: read-back only checks plan ↔ query, so a plan straight from the model could drop a "not".
- **Ceist grounds the rewrite as usual,** and answers only if it gives exactly one reading. The narration is shown for confirmation ("I understood: …"). An LLM mistake is a visible wrong paraphrase, never a silent wrong filter.
- **Reuse Phil's runtime:** `greasan-ask`'s llama.cpp + GBNF (`llama.rs`) and Qwen2.5-0.5B GGUF (491 MB). Compare with a larger local or hosted model (tier 2) on cost and accuracy.
- **Tiers:** 0 static (no model), 1 on-device (Tauri), 2 hosted (opt-in). A browser build stays tier 0.

Measure it on the responder practice set, then on the frozen 39 once, and on the demo's generated hold-out. Report right / wrong / refused / "confirmed rewrite", and the latency per question.
