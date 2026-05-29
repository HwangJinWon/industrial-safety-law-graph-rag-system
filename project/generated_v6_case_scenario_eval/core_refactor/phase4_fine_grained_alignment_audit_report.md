# Phase 4 Fine-Grained Reference Alignment Audit Report

## 1. 목적
Phase 3 이후 chain disconnection은 줄었지만 fine granularity mismatch가 증가했다. 이번 단계는 성능을 억지로 올리는 것이 아니라 fine mismatch의 원인을 분리하는 진단 단계다.

## 2. 현재 상태
- chain_connection_failure: 32 -> 15
- corporate_penalty_attached_rate: strict 1.000, auxiliary 1.000
- chain_fine_granularity_mismatch: 13 -> 23

## 3. fine mismatch 대상 추출 방법
`phase3_repaired_selected_chains.csv`의 repaired selected chain refs와 각 split의 GT core refs를 비교했다. Hierarchical-compatible matching에서 missing으로 남았지만 같은 article family가 chain에 존재하는 ref만 fine granularity mismatch 대상으로 추출했다. strict/auxiliary는 dataset_type 컬럼으로 구분했고, ref parsing은 `parse_fine_grained_law_ref()`를 사용했다.

## 4. fine mismatch 유형 분포
Total mismatch count: 23

By dataset:
{
  "strict": 13,
  "auxiliary": 10
}

By mismatch type:
{
  "ARTICLE_MATCH_WRONG_PARAGRAPH": 2,
  "CORPORATE_FINE_MISSING": 21,
  "WRONG_SIBLING_FINE_REF": 21
}

By law/article:
{
  "산업안전보건법 제38조": 2,
  "산업안전보건법 제173조": 21
}

## 5. 자동 수정 가능성 분석
- auto-fix allowed: 0
- review required: 23
- candidate fine missing: 0
- candidate article missing: 0
- old-current mapping ambiguous: 0

Auto-fix should be limited to low-risk penalty/corporate fine alignment where candidate already contains the GT fine ref and the case facts support the branch.

## 6. penalty/corporate fine alignment 우선순위
- 산업안전보건법 제167조 제1항
- 산업안전보건법 제173조 제1호
- 중대재해처벌법 제6조 제1항/제2항
- 중대재해처벌법 제7조는 세부 호가 불확실하면 selected 자동 승격 금지

## 7. 제38조/제39조 fine ref 자동 보정 위험성
제38조/제39조는 항/호에 따라 위험 유형과 의무 내용이 달라진다. 사실관계가 추락/붕괴/기계위험/보건위험을 충분히 특정하지 않으면 fine-level 자동 보정은 위험하다. 이 경우 article-level selected와 supporting evidence를 유지하는 편이 안전하다.

## 8. Phase 5 제안
1. penalty/corporate fine alignment만 제한적으로 자동 보정
2. 제167조 제1항 / 제173조 제1호 / 중처법 제6조 제1항 중심
3. 제38조/제39조 fine ref는 근거 부족 시 자동 승격 금지
4. detail rule은 selected core가 아니라 supporting으로 유지
5. old-current ambiguous case는 review-only 유지
6. candidate missing은 retrieval/evidence-pack 개선 대상으로 분리

## 9. 결론
현재 병목은 chain connection 자체가 아니라 fine-grained alignment다. 모든 fine mismatch를 자동으로 고치는 것은 위험하며, penalty/corporate fine부터 제한적으로 고치는 것이 안전하다.
