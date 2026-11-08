---
id: 034
slug: data-layer-cross-model-lists
status: draft
branch: crew/034-data-layer-cross-model-lists
model: opus
env: laptop
work: vocab-training
files:
  - packages/ceist/
---

# The data layer sends each list once per run, across models

Draft, 2026-11-08, from task 032's notes. HER has **94** distinct lists across all models (16,595 labels), against 480 counted per model (72,551 labels). After 032 the data layer sends each list once per *model* (HER: 1,810 → 403 calls, about $40.72 → $10.15 estimated). Sending each list once per *run* would cut it further. It needs a prompt that covers several models, with seeds and value combos kept per model. Measure the estimate before and after on HER and Catalina. No live LLM runs.
