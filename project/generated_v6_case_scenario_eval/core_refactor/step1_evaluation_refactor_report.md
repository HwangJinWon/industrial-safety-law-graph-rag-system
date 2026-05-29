# STEP 1 Evaluation Refactor Report

## Why Existing Fine F1 Was Low
The selected answer is compact and chain-oriented, while the GT bundle contains core statutes, definitions, scope provisions, detail rules, enforcement decree/rule details, and management-system references.

Therefore, comparing selected refs against the full GT bundle mixes two tasks:
- direct answer citation selection
- broad supporting bundle recovery

## New Metric Separation
- Full bundle F1: diagnostic only
- Selected core F1: main direct-answer metric
- Supporting bundle recall: evidence/support recovery metric
- Candidate recall: retrieval/evidence-pack upper-bound metric

## Strict Summary
- full_fine_soft_f1: 0.516
- selected_core_compatible_f1: 0.578
- selected_core_article_f1: 0.541
- supporting_compatible_recall: 0.364

## Ambiguous Refs
{}
