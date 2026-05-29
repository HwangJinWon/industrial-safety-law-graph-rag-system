# v6 Candidate Pool Upper-Bound Report

## Scope
- Dataset: v6 reviewed strict READY_A, 27 cases
- Selector setting: selector_v3 cap 7
- Evaluation outputs:
  - `evaluation_reviewed/selector_v3_ablation/cap7_upper_bound/`
  - `evaluation_reviewed/selector_v3_ablation/cap7_backend_fine_expansion_local/`
- Original GT and reviewed datasets were not modified.

## Metric Split
`candidate_recall` previously measured exact fine-grained hits in the union of selected, supporting, and candidate tiers.

New diagnostic metrics:
- `candidate_fine_recall`: exact fine-grained candidate-pool recall. Same as legacy `candidate_recall`.
- `candidate_article_recall`: candidate-pool recall after reducing refs to law + article.
- `selected_article_recall`: selected-only article recall.
- `selected_supporting_article_recall`: selected + supporting article recall.
- `candidate_fine_missing`: GT refs absent from selected + supporting + candidate exactly.
- `candidate_article_missing`: GT refs whose law + article are absent from selected + supporting + candidate.

## Baseline Diagnosis After Metric Split
Selector v3 cap 7 with upper-bound metrics:
- candidate_fine_recall: 0.609
- candidate_article_recall: 0.828
- selected_article_recall: 0.779
- selected_supporting_article_recall: 0.828
- article_level_f1: 0.453
- fine_level_f1: 0.438

Interpretation:
- The candidate pool is already near the 0.85 article-level retrieval target.
- The main upper-bound gap is fine-grained exactness, not article-family retrieval.
- Many failures are article-level GT vs paragraph/item-level evidence refs, especially around penalty/corporate-penalty provisions.

## Pool-Missing Analysis
Generated:
- `evaluation_reviewed/candidate_pool_missing_analysis.csv`
- `evaluation_reviewed/candidate_pool_missing_analysis.summary.json`

Top missing slots:
- corporate_penalty: 9
- definition_or_scope: 7
- detail_rule: 7
- procedure_or_management: 5
- penalty: 1

Top missing article families:
- 산업안전보건법 제173조: 9
- 산업안전보건법 제2조: 5
- 산업안전보건기준에 관한 규칙 제619조: 3
- 중대재해처벌법 시행령 제4조: 2
- 산업안전보건법 제13조: 2
- 산업안전보건법 제31조: 2
- 산업안전보건법 제14조: 2
- 산업안전보건법 제5조: 2

## Backend Change
Updated:
- `05_code/graph_rag_pipeline/evidence_pack_assembler.py`

Change:
- `_fetch_bundle_completion_items()` now preserves multiple fine-grained rows under the same law/article instead of keeping only the first article-level row.
- It also attempts to add parent article candidates for fetched completion refs.

Local strict reevaluation after backend fine expansion:
- candidate_fine_recall: 0.609 -> 0.629
- candidate_article_recall: 0.828 -> 0.828
- bundle_slot_f1: 0.744 -> 0.768
- article_level_f1: 0.453 -> 0.455
- fine_level_f1: 0.438 -> 0.438
- selected_legal_chain_f1: 0.352 -> 0.352
- candidate_overgeneration_rate: 1.860 -> 4.186

Interpretation:
- Backend completion expansion modestly improves exact candidate recall and bundle slot coverage.
- It substantially increases auxiliary candidate overgeneration, so it should remain a candidate/supporting expansion, not selected-tier promotion.
- selected metrics remain stable because selector_v3 cap 7 filters the expanded pool.

## Next Recommended Fix
Do not treat `candidate_fine_recall=0.609` as the only retrieval upper bound in the paper. Report both:
- article-level retrieval upper bound: `candidate_article_recall=0.828`
- fine-grained exact upper bound: `candidate_fine_recall=0.629`

For the next engineering pass:
- Add controlled parent-article aliases at evaluation/reporting time for mixed article-level GT only, or normalize GT granularity before fine-level strict scoring.
- Keep strict fine-level F1 separate from article-level F1.
- Target remaining actual article misses: scope/definition and detail-rule refs such as 산업안전보건법 제2조, 산업안전보건기준에 관한 규칙 제619조, and 중대재해처벌법 시행령 제4조.
