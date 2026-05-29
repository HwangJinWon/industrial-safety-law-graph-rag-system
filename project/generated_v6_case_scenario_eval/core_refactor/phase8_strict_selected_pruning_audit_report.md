# Phase 8 Strict Selected Pruning Audit

## Purpose
This phase separates strict selected-core false positives into safe pruning candidates, risky article-family mismatches, and chain-completion refs that should be treated as explanatory or supporting evidence. It does not modify GT, predictions, or the evaluator.

## Summary
- Current reconstructed strict selected-core F1: 0.556
- Conservative safe-pruned F1 simulation: 0.652
- Chain-completion-neutral adjusted F1: 0.722
- Oracle-pruned upper-bound F1: 0.886
- Current selected core refs per case: 6.93
- Safe-pruned selected core refs per case: 5.56
- Average safe prune refs per case: 1.37
- Average neutral chain-completion refs per case: 2.41

## Interpretation
The strict score is low for two different reasons. Some selected refs are genuine false positives that can be moved to supporting or candidate evidence. A larger portion are chain-completion refs: obligation or penalty predecessors needed to explain downstream penalty or corporate-penalty GT refs. These should not be silently deleted. They should either remain in selected legal chains or move to an explicit chain-completion/supporting layer.

## Recommended Implementation Rule
Use slot-based selected pruning only for refs marked `PRUNE_TO_SUPPORTING_OR_CANDIDATE`. Keep chain-completion refs out of false-positive scoring through a reviewed evaluation layer rather than forcing the selector to drop legally meaningful predecessors.
