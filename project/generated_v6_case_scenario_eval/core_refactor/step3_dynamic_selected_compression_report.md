# STEP 3 Dynamic Selected Compression Report

## Why Fixed Cap 7 Was Inadequate
GT/core slot counts vary by case. A fixed selected cap of 7 over-penalizes simple cases by allowing too many selected refs, while complex OSHA + Serious Accident cases may need more room.

## Dynamic Cap Policy
- simple OSHA death: 5 or enough for core refs
- contractor: 6 or enough for core refs
- serious accident: 6 or enough for core refs
- OSHA + serious accident: 8
- small core-slot case: 3-5, adjusted by GT core count for diagnostic replay

## Strict Before / After
- selected_law_count: 6.963 -> 6.407
- selected_overgeneration_rate: 1.111 -> 0.931
- selected_core_compatible_f1: 0.553 -> 0.578
- selected_core_compatible_recall: 0.799 -> 0.806

## Auxiliary Before / After
- selected_law_count: 7.000 -> 6.300
- selected_overgeneration_rate: 0.324 -> 0.290
- selected_core_compatible_f1: 0.805 -> 0.758
- selected_core_compatible_recall: 0.938 -> 0.838

## Article 173 Handling
Article 173 is handled through penalty-chain semantics:
- Article 167 paragraph 1 / death-like chain strengthens Article 173 item 1.
- Article 168-172-like branches strengthen Article 173 item 2.
- Corporate penalty is not promoted when the penalty side is not selected or strong.

## Remaining Limit
Strict improves, but auxiliary loses some core recall under compression. That means dynamic cap should be treated as a candidate policy, not blindly applied to every split.
