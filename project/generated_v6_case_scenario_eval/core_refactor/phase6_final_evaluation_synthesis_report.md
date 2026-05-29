# Phase 6 Final Evaluation Synthesis Report

## 1. Purpose
This report synthesizes Phase 1 through Phase 5-D. It is not an additional performance-improvement step and does not modify GT, predictions, or the original evaluator.

## 2. Dataset and evaluation setup
- Original cases: 69
- Reviewed strict: 27
- Auxiliary: 10
- Review-only: 3
- Manual review targets: 23

The task is case-scenario evaluation: reconstructing legal obligations, penalties, corporate penalties, and legal chains from precedent or accident facts.

## 3. Why the initial F1 was low
The early fine-level F1 was not a single selector problem. The decomposition separated evaluation-design mismatch, selected overgeneration, candidate fine recall limits, chain connection failure, fine branch ambiguity, old-current fine branch overmapping, and GT granularity issues.

## 4. Phase-by-phase findings
Phase 1 separated selected core/supporting/full bundle/candidate metrics. Phase 2 reduced overgeneration while protecting auxiliary recall. Phase 3 stabilized obligation -> penalty -> corporate penalty chains. Phase 4 showed remaining fine mismatches were not candidate/article missing. Phase 5-A found prediction branch consistency. Phase 5-B separated policy-adjusted evaluation. Phase 5-C produced manual review packages. Phase 5-D refined old-current corporate mapping.

## 5. Final metrics
Strict selected_core_f1 is 0.5814706898040233; auxiliary selected_core_f1 is 0.8109324009324009. Corporate penalty attachment is 1.0 for strict and 1.0 for auxiliary. See `phase6_final_evaluation_summary_table.csv` for the full table.

## 6. Interpretation of policy-adjusted and refined-policy metrics
Policy-adjusted metrics are not prediction updates. Refined-policy metrics are also not prediction updates; they clarify old-current mapping rationale. Strict fine_chain_match_rate changes from 0.25925925925925924 to 0.7407407407407407. Weighted original fine_chain_match_rate changes from 0.43243243243243246 to refined-policy 0.8108108108108109. This is an evaluation/mapping interpretation effect.

## 7. Old-current corporate mapping refinement
Old corporate penalty provisions map to current Article 173 at article level. Article 167(1) resolves to Article 173 subparagraph 1. Articles 168-172 resolve to Article 173 subparagraph 2. If the penalty branch is unclear, Article 173 remains article-level only. Article 173 subparagraph 2 was not directly replaced with subparagraph 1. Phase 5-D found 21 likely old-current fine branch overmapped cases.

## 8. Manual review package
- Total review targets: 23
- Article 173: 21
- Article 38: 2
- HIGH priority: 21
- MEDIUM priority: 2
- Recommended decisions: {"ARTICLE_LEVEL_ONLY": 12, "GT_FINE_BRANCH_REVISE_RECOMMENDED": 11}

`reviewer_decision` fields remain blank.

## 9. Recommended reporting structure
Report original strict selected_core_f1, auxiliary selected_core_f1, candidate recall, selected overgeneration, corporate penalty attached rate, original fine_chain_match_rate, policy-adjusted fine_chain_match_rate, refined-policy fine_chain_match_rate, branch consistency rate, and manual review pending count together.

## 10. Limitations
The original GT was not modified. Branch ambiguity remains pending until manual review. Policy-adjusted/refined-policy metrics are supplementary. Article 38 fine branch depends on fact specificity. Old-current fine-level mapping requires expert review.

## 11. Next steps
Create a reviewed_eval_layer, perform legal expert review, prioritize high-priority Article 173 cases, review the two Article 38 fine-branch cases, and prepare the final paper evaluation table.
