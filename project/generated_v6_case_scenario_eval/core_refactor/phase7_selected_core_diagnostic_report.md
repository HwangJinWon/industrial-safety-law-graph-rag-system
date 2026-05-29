# Phase 7 Selected Core F1 Diagnostic Report

## Purpose
This phase explains why strict selected_core_f1 remains low and provides a diagnostic chain-completion-adjusted metric. It does not modify GT, predictions, or the original evaluator.

## Finding
Several low-F1 strict cases contain only downstream corporate-penalty refs in GT, especially Article 173, while selected output includes the obligation and penalty predecessors required to explain that corporate penalty chain. Under the original selected_core metric, these chain-completion refs are counted as false positives.

## Metrics
- Official Phase 3 strict selected_core_f1: 0.5814706898040233
- Reconstructed original selected_core_f1: 0.5558814642147976
- Chain-completion-adjusted selected_core_f1: 0.7216249799583133
- Reconstructed original precision: 0.4597295708406819
- Adjusted precision: 0.7020576131687243
- Recall retained: 0.806496178718401
- Average neutral chain-completion refs per case: 2.4074074074074074

## Interpretation
The adjusted score is not a model improvement. It shows that part of the low strict selected_core_f1 is caused by evaluation granularity: selected answers include legally meaningful chain predecessors that are absent from the strict GT core. This should be reported as a diagnostic or supplementary metric, not as the primary strict metric.

## Recommended Next Step
Create a reviewed_eval_layer after legal review that distinguishes direct GT core refs from chain-completion explanatory refs. Until then, keep the original strict selected_core_f1 and report this adjusted metric as evidence that the bottleneck is partly evaluation design.
