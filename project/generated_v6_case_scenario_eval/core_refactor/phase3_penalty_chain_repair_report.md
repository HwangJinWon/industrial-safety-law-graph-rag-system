# Phase 3 Penalty Chain Connection Repair Report

## 1. 목적
Phase 2 이후 가장 큰 실패 원인은 `chain_connection_failure`였다. 이번 단계는 retrieval 확장이 아니라 selected legal chain의 obligation -> penalty -> corporate penalty 연결을 복구하는 작업이다.

## 2. Phase 2 기준 상태
Strict selected_core_f1 phase2: 0.581
Auxiliary selected_core_f1 phase2: 0.811

Phase 2 chain failure counts:
{
  "candidate_fine_missing": 18,
  "selected_promotion_failure": 6,
  "chain_connection_failure": 32,
  "chain_fine_granularity_mismatch": 13,
  "candidate_article_missing": 3
}

## 3. chain_connection_failure 세부 유형 분석
Failure taxonomy counts:
{
  "obligation_selected_but_penalty_not_connected": 12,
  "old_current_mapping_chain_ambiguity": 13,
  "penalty_selected_but_corporate_not_connected": 7
}

Auto-fix allowed rows: 19 / 32

Review-only rows are left when candidate article/fine is missing, old-current mapping is ambiguous, or detail/supporting refs appear to be acting as core chain refs.

## 4. chain repair rule
- obligation -> penalty: OSHA death/contractor obligations connect to Article 167(1) when present in selected/candidate pool.
- serious accident obligation -> penalty: Serious Accident Act Article 4/5 connects to Article 6(1) when present.
- penalty -> corporate: Article 167(1) connects only to Article 173 item 1; Article 168-172 connects only to Article 173 item 2.
- article-level -> fine-level: when article chain is already aligned and candidate fine refs exist, fine refs are preferred.
- supporting detail refs are not used as selected core chains unless clearly core.

## 5. 재평가 결과
Strict:
- selected_core_f1 phase3: 0.581
- selected_core_precision phase3: 0.482
- selected_core_recall phase3: 0.814
- selected_penalty_article_match phase3: 0.407
- selected_penalty_fine_match phase3: 0.407
- fine_chain_match_rate phase3: 0.259
- selected_overgeneration phase3: 0.935

Auxiliary:
- selected_core_f1 phase3: 0.811
- selected_core_precision phase3: 0.717
- selected_core_recall phase3: 0.938
- selected_penalty_article_match phase3: 1.000
- selected_penalty_fine_match phase3: 1.000
- selected_overgeneration phase3: 0.290

## 6. 제173조 처리 결과
Article 173 is only connected through a selected/candidate penalty chain.

- Article 167(1) -> Article 173 item 1 is enforced by rule R3.
- Article 168-172 -> Article 173 item 2 is enforced by rule R4.
- No unconditional Article 173 selected insertion is used.
- Penalty-to-corporate connection rate strict: 1.000
- Penalty-to-corporate connection rate auxiliary: 1.000

## 7. 남은 실패 유형
Failure before/after:
[
  {
    "failure_type": "candidate_article_missing",
    "before": 3,
    "after": 3
  },
  {
    "failure_type": "candidate_fine_missing",
    "before": 18,
    "after": 16
  },
  {
    "failure_type": "chain_connection_failure",
    "before": 32,
    "after": 15
  },
  {
    "failure_type": "chain_fine_granularity_mismatch",
    "before": 13,
    "after": 23
  },
  {
    "failure_type": "selected_promotion_failure",
    "before": 6,
    "after": 6
  }
]

Remaining issues are separated into candidate fine missing, candidate article missing, selected promotion failure, chain fine granularity mismatch, and chain connection failure.

## 8. 결론
Phase 3 repairs selected legal chain connection where candidate/selected core refs already support it. It avoids case-id hardcoding and avoids unconditional Article 173 insertion. Remaining failures are now more clearly attributable to candidate generation or fine granularity rather than only chain connection.
