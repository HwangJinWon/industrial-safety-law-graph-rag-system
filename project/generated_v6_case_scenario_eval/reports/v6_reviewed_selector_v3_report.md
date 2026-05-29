# v6 Reviewed Selector v3 Report

## Scope
- Dataset: v6 reviewed strict READY_A, 27 cases
- Auxiliary check: v6 reviewed auxiliary, 10 cases
- Original v4/v5/v6 datasets and GT were not modified.
- Candidate/debug tiers remain auxiliary; strict F1 is computed from selected laws/chains only.

## Selector Changes
- Added case-facts article compatibility checks for safety, health, contractor, serious-accident, penalty, corporate-penalty, and scope refs.
- Opened penalty/corporate-penalty slot capacity to 2 only when the expected bundle contains multiple refs in that slot.
- Kept selected legal chains to 1-3 core obligation -> penalty -> corporate penalty chains.
- Compacted selected chain refs to one best obligation, one best penalty, and one best corporate-penalty ref.
- Added separate chain metric aliases:
  - `chain_exists_hit`
  - `chain_article_match_*`
  - `chain_fine_match_*`
- Added candidate-only analysis output:
  - `project/generated_v6_case_scenario_eval/evaluation_reviewed/candidate_only_hit_analysis.csv`

## Strict Cap Ablation
See:
`project/generated_v6_case_scenario_eval/evaluation_reviewed/selector_v3_ablation/selector_v3_cap_ablation_summary.csv`

| run | selected_law_count | article_f1 | fine_f1 | selected_chain_f1 | chain_article_f1 | bundle_slot_f1 | candidate_recall | selected_overgeneration | candidate_only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 7.259 | 0.399 | 0.320 | 0.286 | 0.388 | 0.744 | 0.609 | 1.362 | 21 |
| selector_v3 cap 6 | 6.000 | 0.485 | 0.463 | 0.352 | 0.446 | 0.726 | 0.598 | 0.890 | 8 |
| selector_v3 cap 7 | 6.963 | 0.453 | 0.438 | 0.352 | 0.446 | 0.744 | 0.609 | 1.111 | 8 |
| selector_v3 cap 8 | 7.926 | 0.419 | 0.407 | 0.352 | 0.446 | 0.744 | 0.609 | 1.342 | 8 |

## Recommended Strict Setting
Use cap 7 as the default reviewed-strict setting.

Rationale:
- Keeps selected laws in the target 6-8 range.
- Raises article-level F1 above 0.45.
- Raises selected legal-chain F1 above 0.35.
- Preserves bundle slot F1 and candidate recall at the previous strict level.
- Reduces candidate_only_match from 21 to 8.

Cap 6 is a useful precision-focused variant:
- selected_overgeneration_rate drops below 1.0.
- article/fine F1 are highest.
- tradeoff: bundle_slot_f1 and candidate_recall dip slightly.

## Auxiliary Check
Against auxiliary baseline, selector_v3 cap 7 produced:
- selected_law_count: 10.000 -> 7.000
- role_level_f1: 0.746 -> 0.711
- article_level_f1: 0.305 -> 0.658
- fine_level_f1: 0.237 -> 0.708
- selected_legal_chain_f1: 0.000 -> 0.380
- legal_chain_article_f1: 0.000 -> 0.410
- bundle_slot_f1: 0.365 -> 0.717
- selected_overgeneration_rate: 0.324
- candidate_only_match: 10 -> 0

## Remaining Limits
- Strict selected_overgeneration_rate is still 1.111 at cap 7. Cap 6 solves this but slightly lowers bundle slot F1.
- Remaining strict failures are mostly not missing-chain failures: chain_exists remains 1.0 and full obligation-penalty-corporate chain hit remains 27/27.
- Some scope/definition refs still need separate handling because selecting them improves bundle coverage but often hurts strict precision.
- Candidate promotion did not fire in the latest strict run; the main gains came from better slot capacity and chain ref compaction.
