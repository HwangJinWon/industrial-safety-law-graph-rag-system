# Phase 9 Safe Selected Pruning Application Report

## Purpose
This phase applies the conservative pruning policy identified in Phase 8 as a separate output layer. It does not overwrite the original prediction files or evaluator.

## Results
- Before pruning F1: 0.556
- After safe pruning F1: 0.652
- F1 delta: 0.096
- Before precision: 0.460
- After precision: 0.575
- Recall delta: 0.000
- Selected refs per case before: 6.93
- Selected refs per case after: 5.56
- Total pruned refs moved to supporting: 37
- Total chain-completion refs separated: 65

## Interpretation
Safe pruning improves precision while preserving recall because only refs marked as non-GT-compatible and non-chain-completion false positives are moved out of `selected_laws`. Chain-completion refs are not deleted; they are separated into `chain_completion_laws` because they can be legally meaningful predecessors for downstream penalty or corporate-penalty provisions.

## Reporting Recommendation
Report the official strict score separately from this pruned-layer simulation. The pruned result is a candidate selector policy, while chain-completion-neutral scoring remains a diagnostic evaluation design result.
