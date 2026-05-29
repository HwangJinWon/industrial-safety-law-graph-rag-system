# V6 Case Scenario Evaluation

## Evaluation Setup
Input is a structured case_scenario prompt derived from each case's facts. GT is expected_legal_bundle; B-grade mappings are excluded.

## Main Metrics
- sample_count: 40
- selected_fine_grained_exact_f1: 0.061
- selected_fine_grained_soft_f1: 0.103
- selected_legal_chain_f1: 0.034
- bundle_slot_f1: 0.167
- full_obligation_penalty_corporate_chain_hit: 40
- candidate_recall: 0.189
- candidate_overgeneration_rate: 2.407

## Interpretation
This is not question rewriting. It measures whether the system can reconstruct a legal bundle from case facts.
