# v6 Reviewed Selector Update

## Scope
- Dataset: v6 reviewed strict READY_A, 27 cases
- Policy: selected laws are compressed by case type and article priority; candidate laws/chains remain auxiliary review data.
- Selected legal chains are capped to 1-3 core obligation -> penalty chains.

## Latest Strict Result
- selected_law_count: 7.259
- selected_chain_count: 3.000
- role_level_f1: 0.495
- article_level_f1: 0.399
- fine_level_f1: 0.320
- selected_legal_chain_f1: 0.286
- legal_chain_article_f1: 0.388
- legal_chain_fine_f1: 0.286
- bundle_slot_f1: 0.744
- selected_overgeneration_rate: 1.362
- auxiliary candidate_overgeneration_rate: 1.860

## Baseline Comparison
- article_level_f1: 0.226 -> 0.399
- fine_level_f1: 0.179 -> 0.320
- selected_legal_chain_f1: 0.099 -> 0.286
- bundle_slot_f1: 0.319 -> 0.744

## Cap Ablation
See `selector_ablation/selector_cap_ablation_summary.csv`. Cap 8 is selected because it produced the best article-level F1 while keeping the average selected law count between 6 and 8.

## Remaining Risk
Candidate recall is still much higher than selected exact recall, so many answers still contain the right law only in auxiliary/candidate pools. The next step is to move high-confidence candidate-only hits into selected by case-specific selectors, not by increasing the cap.
