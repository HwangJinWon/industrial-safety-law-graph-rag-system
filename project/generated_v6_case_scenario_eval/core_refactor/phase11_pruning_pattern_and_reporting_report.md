# Phase 11 Pruning Pattern and Reporting Package

## Purpose
This phase summarizes why selected pruning improves strict F1 and prepares a defensible reporting table.

## Pattern Counts
- other_overselection: 8
- cross_law_overselection: 2
- obligation_slot_overselection: 11
- full_chain_overselection: 6

## Recommended Reporting
Do not collapse all scores into a single main number. Use the official conservative score as the baseline and report safe-pruned/direct-selected metrics as layer-separated analyses.

## Reporting Table
| Metric | Score | Use | Caution |
|---|---:|---|---|
| Strict selected-core F1 | 0.5814706898040233 | main conservative result | Counts chain-completion refs as false positives when absent from GT core. |
| Safe-pruned selected-core F1 | 0.6522231883342995 | ablation / improved selected layer | Does not overwrite original predictions; removes only safe false positives. |
| Direct-selected F1 | 0.8863168724279838 | supplementary main table if direct vs chain layers are explained | Valid only with chain_completion_laws reported separately. |
| Chain-completion-neutral F1 | 0.7216249799583133 | error analysis | Not a model improvement score. |
| Corporate penalty attached rate | 1.0 | legal chain completeness | Attachment does not by itself prove fine-branch correctness. |
| Strict fine-chain match rate, policy-adjusted | 0.7407407407407407 | supplementary metric | Reflects evaluation granularity adjustment, not prediction modification. |
| Manual review pending count | 23 | limitations / review package | Requires legal expert or source review before GT revision. |
