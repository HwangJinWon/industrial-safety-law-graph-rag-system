# Phase 10 Direct Selected vs Chain-Completion Split Report

## Purpose
This phase tests whether selected references can be made stricter by separating direct answer refs from chain-completion refs. It keeps chain-completion refs in a separate layer rather than deleting them.

## Results
- Safe-pruned F1: 0.652
- Direct-selected F1: 0.886
- Direct-selected precision: 1.000
- Direct-selected recall: 0.806
- Recall delta from safe-pruned: 0.000
- Direct selected refs per case: 3.15
- Remaining direct overgenerated refs per case: 0.00
- Chain-completion refs preserved: 65
- Recall-loss cases: 0
- Corporate penalty attached rate retained: 1.000

## Interpretation
Direct-selected F1 is the cleanest high score for a strict answer-reference layer, but it depends on reporting chain-completion refs separately. This is defensible only if the paper clearly distinguishes direct citations from legal-chain explanatory refs.

## Recommended Reporting
Use three rows:
1. Official strict selected-core F1.
2. Safe-pruned selected-core F1.
3. Direct-selected F1 with chain-completion refs reported separately.
