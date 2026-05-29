# v6 Core Refactor Evaluation Report

## 1. 목적
기존 F1 저하 원인을 selector 단일 문제가 아니라 평가 구조, selected 과생성, candidate fine recall 문제로 분리했다.

## 2. 기존 문제 진단
- strict GT refs 총합: 141
- strict selected refs 총합: 188
- compatible 기준 missing GT refs: 57
- exact 기준 selected overgenerated refs: 112
- candidate_fine_missing: 50
- candidate_article_missing: 17
- candidate_article_recall: 0.893
- candidate_fine_recall: 0.629

## 3. STEP 1: 평가 구조 재분리 결과
selected core / supporting / candidate를 분리했다.

- Full bundle F1: 전체 GT bundle 복원 관점의 진단 지표
- Selected core F1: 답변에 직접 포함되어야 할 핵심 법리 선택 성능
- Supporting bundle recall: 정의/범위/세부기준/시행령/규칙 근거를 보조 evidence로 복원하는 성능
- Candidate recall: selector 이전 단계의 retrieval/evidence-pack 성능

Strict selected core:
- selected_core_exact_f1: 0.523
- selected_core_compatible_f1: 0.578
- selected_core_article_f1: 0.541

Auxiliary selected core:
- selected_core_exact_f1: 0.758
- selected_core_compatible_f1: 0.758
- selected_core_article_f1: 0.771

## 4. STEP 2: candidate fine recall 보강 결과
Fine expansion은 selected로 바로 승격하지 않고 candidate/supporting 후보로만 둔다.

Strict:
- candidate_fine_recall: 0.629 -> 0.703
- candidate_article_recall: 0.868 -> 0.868
- candidate_fine_missing: 1.852 -> 1.370
- candidate_article_missing: 0.630 -> 0.630
- candidate_pool_size: 33.667 -> 34.148
- candidate_overgeneration_rate_after: 7.404
- missing type counts before: {"corporate_penalty_fine_missing": 17, "article_family_missing": 17, "definition_scope_fine_missing": 9, "article_family_hit_but_fine_missing": 3, "detail_rule_fine_missing": 2, "penalty_fine_missing": 2}
- expansion reason counts: {"supporting_definition_article_family_hit": 9, "core_article_family_hit": 2, "supporting_enforcement_decree_detail_article_family_hit": 2}

Auxiliary:
- candidate_fine_recall: 0.737 -> 0.749
- candidate_article_recall: 0.705 -> 0.705
- candidate_fine_missing: 1.800 -> 1.700
- candidate_article_missing: 1.700 -> 1.700
- candidate_pool_size: 33.900 -> 34.000
- candidate_overgeneration_rate_after: 4.318

## 5. STEP 3: dynamic selected compression 결과
Fixed cap 7은 GT/core slot이 적은 사건에서 과하다. Dynamic cap은 사건별 core slot 수와 사건 유형을 기준으로 3~8 사이를 적용했다.

Strict:
- selected_law_count: 6.963 -> 6.407
- selected_overgeneration_rate: 1.111 -> 0.931
- selected_core_compatible_f1: 0.553 -> 0.578
- selected_core_compatible_recall: 0.799 -> 0.806

제173조는 penalty-chain 성격을 기준으로 candidate expansion 및 selected rank에서 처리했다. 사망 + 제167조 제1항 성격이면 제173조 제1호를 강화하고, 제2호는 사망 사건에서 낮춘다.

## 6. 최종 before/after 비교
Strict 27건:
- full_fine_exact_f1: 0.469
- full_fine_soft_f1: 0.516
- full_article_f1: 0.478
- selected_core_compatible_f1: 0.578
- supporting_compatible_recall: 0.364
- candidate_fine_recall: 0.703
- selected_overgeneration_rate: 0.931

Auxiliary 10건:
- full_fine_exact_f1: 0.667
- full_fine_soft_f1: 0.667
- full_article_f1: 0.667
- selected_core_compatible_f1: 0.758
- supporting_compatible_recall: 0.133
- candidate_fine_recall: 0.749
- selected_overgeneration_rate: 0.290

## 7. 남은 실패 유형
- candidate에도 없는 article family
- fine ref는 있으나 role 분류 실패
- supporting/detail rule이 selected로 올라오는 문제
- 제173조 chain 연결 실패
- 중처법 scope/definition 판단 실패
- 구법-현행법 mapping 애매한 케이스

Remaining ambiguous refs:
{}

## 8. 다음 작업 제안
- case type classifier 개선
- fine ref expansion rule 정교화
- supporting evidence UI 분리
- penalty/corporate chain graph edge 보강
- review-only case 32, 34, 65 수동 검토
