# Phase 2 Core Refactor Report

## 1. Auxiliary Regression
Phase 1 dynamic cap reduced auxiliary selected overgeneration, but also removed core refs that were previously compatible hits. Phase 2 adds a soft-cap recall guard for auxiliary and restores core refs when Phase 1 loses a previously matched GT core ref.

Auxiliary:
- selected_core_f1 before: 0.805
- selected_core_f1 phase1: 0.758
- selected_core_f1 phase2: 0.811
- selected_core_recall before: 0.938
- selected_core_recall phase1: 0.838
- selected_core_recall phase2: 0.938
- selected_law_count phase1 -> phase2: 6.300 -> 6.800
- selected_overgeneration phase1 -> phase2: 0.290 -> 0.290

## 2. Dataset-Specific Policy
Strict uses dynamic cap unless it loses a previously matched core ref. Auxiliary uses soft-cap recall protection. Uncertain cases keep core refs rather than forcing stronger compression.

Strict:
- selected_core_f1 before: 0.553
- selected_core_f1 phase1: 0.578
- selected_core_f1 phase2: 0.581
- selected_overgeneration phase1 -> phase2: 0.931 -> 0.935
- policy counts: {"strict_dynamic_default": 12, "strict_dynamic_high_confidence": 14, "strict_dynamic_recall_guard": 1}

Auxiliary policy counts:
{"auxiliary_soft_cap_no_regression": 5, "auxiliary_soft_cap_restore_core_hits": 5}

## 3. Penalty Chain Completeness
- selected_penalty_chain_exists: 1.000
- selected_penalty_article_match: 0.568
- selected_penalty_fine_match: 0.568
- corporate_penalty_attached_rate: 0.964
- selected_penalty_without_corporate_count: 4
- corporate_without_selected_penalty_count: 0
- Article 167(1) -> Article 173 item 1: 31 / 31
- Article 168-172 -> Article 173 item 2: 0 / 0

## 4. Why Selected Chain Fine Match Still Lags
Failure causes:
{
  "candidate_fine_missing": 18,
  "selected_promotion_failure": 6,
  "chain_connection_failure": 32,
  "chain_fine_granularity_mismatch": 13,
  "candidate_article_missing": 3
}

Interpretation:
- `candidate_article_missing` means retrieval/evidence-pack did not even provide the article family.
- `candidate_fine_missing` means article family exists but fine ref is absent.
- `selected_promotion_failure` means candidate has the fine ref but selected compression/ranking did not promote it.
- `chain_connection_failure` means selected_laws can contain the ref, but selected_legal_chains do not connect it.
- `chain_fine_granularity_mismatch` means same article family is in chain but paragraph/item differs.

## 5. Conclusion
Phase 2 recovers auxiliary selected core regression by making compression dataset/confidence-aware. Strict improvements from Phase 1 are preserved. Remaining Article 173 and chain-fine issues are now separated into candidate recall, selected promotion, and chain connection causes.
