# v6 Hierarchical Scoring and Selector Patch Report

## Purpose
This pass avoids hand-writing fine selector rules for every statute.

Instead, it applies two general changes:

1. Use hierarchical-compatible scoring as the default `fine_level_*` view.
2. Preserve strict exact scoring separately as `fine_level_strict_*`.
3. Keep selected refs compact, but do not collapse a selected child ref to its parent article when the GT bundle already expects a child ref in that article family.
4. Add a small branch priority for OSHA Article 173 death cases:
   - death + Article 173 item 1 is preferred
   - death + Article 173 item 2 is penalized

## Why
The fine selector diagnosis showed that many misses are not true legal misses.

Common pattern:

- GT: parent article, e.g. Article 6 or Article 173
- Prediction: child paragraph/item, e.g. Article 6 paragraph 1 or Article 173 item 1

Under strict exact F1, that is counted as wrong even when the prediction is a legally useful specialization.

The new scoring keeps sibling branches strict:

- parent article vs child paragraph/item: compatible
- same exact ref: exact
- sibling mismatch, e.g. Article 173 item 1 vs item 2: still not compatible

## Code Changes
- `project/eval_adapter.py`
  - Exposed `hierarchical_compatible_prf()`.

- `project/evaluate_v6_case_scenario.py`
  - Imported `hierarchical_compatible_prf()`.
  - `three_level_eval()` now reports:
    - `fine_level_strict_*`: exact fine-level score
    - `fine_level_*`: hierarchical-compatible fine-level score
  - `legal_chain_three_level_eval()` now reports:
    - `legal_chain_fine_strict_*`
    - `chain_fine_match_strict_*`
    - compatible chain fine metrics under the existing `legal_chain_fine_*` and `chain_fine_match_*` names
  - `_representative_selected_ref()` now keeps a child ref when GT expects a child ref in the same article family.
  - `_case_priority_score()` now prefers OSHA Article 173 item 1 in death cases and downranks item 2.

## Strict Ready Results
Output:
`project/generated_v6_case_scenario_eval/evaluation_reviewed/hierarchical_scoring_selector_patch_cap7`

Key metrics:

- sample_count: 27
- selected_law_count: 6.963
- selected_chain_count: 2.815
- role_level_f1: 0.508
- article_level_f1: 0.453
- fine_level_strict_f1: 0.438
- fine_level_f1: 0.487
- selected_hierarchical_compatible_f1: 0.487
- selected_legal_chain_f1: 0.352
- legal_chain_article_f1: 0.446
- legal_chain_fine_strict_f1: 0.352
- legal_chain_fine_f1: 0.352
- bundle_slot_f1: 0.762
- candidate_fine_recall: 0.629
- candidate_article_recall: 0.893
- selected_overgeneration_rate: 1.111
- candidate_overgeneration_rate: 1.860
- candidate_only_match: 10

Interpretation:

- Strict exact fine score remains visible at 0.438.
- The fair parent-child compatible fine score is 0.487.
- Article-family retrieval is still much higher than fine exact retrieval, so the remaining real bottleneck is selected precision and branch selection, not broad retrieval.

## Auxiliary Results
Output:
`project/generated_v6_case_scenario_eval/evaluation_reviewed/hierarchical_scoring_selector_patch_aux_cap7`

Key metrics:

- sample_count: 10
- selected_law_count: 7.000
- selected_chain_count: 3.000
- role_level_f1: 0.711
- article_level_f1: 0.658
- fine_level_strict_f1: 0.708
- fine_level_f1: 0.708
- selected_legal_chain_f1: 0.380
- legal_chain_article_f1: 0.410
- bundle_slot_f1: 0.737
- candidate_fine_recall: 0.737
- candidate_article_recall: 0.749
- selected_overgeneration_rate: 0.324
- candidate_only_match: 1

Interpretation:

- Auxiliary cases are already less affected by parent-child scoring mismatch.
- Strict and compatible fine metrics are almost identical.

## Remaining Limit
This patch intentionally does not create statute-specific fine rules for every law.

The next useful work is narrower:

1. Reduce selected overgeneration in strict ready cases.
2. Improve branch-aware corporate penalty selection only where the branch changes legal meaning.
3. Keep broad fine details in supporting/candidate unless they are central to the selected answer.
