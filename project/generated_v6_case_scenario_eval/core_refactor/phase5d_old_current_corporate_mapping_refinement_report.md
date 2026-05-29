# Phase 5-D Old-to-Current Corporate Penalty Mapping Refinement Report

## 1. 목적
이번 단계는 구법 양벌규정과 현행 산업안전보건법 제173조의 대응을 정교화하는 단계다. GT, prediction, 기존 evaluator는 수정하지 않았다.

## 2. 배경
Phase 5-A/B/C에서 제173조 제1호/제2호 mismatch는 prediction error가 아니라 branch ambiguity에 가깝다는 점을 확인했다. 특히 prediction은 대체로 제167조 제1항 -> 제173조 제1호 흐름과 일관적이었다. 문제는 구법 양벌규정을 현행 제173조 제2호까지 과도하게 fine mapping했을 가능성이다.

## 3. Old-current Mapping Issue
구 산업안전보건법 제71조 같은 구법 양벌규정은 현행 산업안전보건법 제173조 article-level로 대응시키는 것이 안전하다. 제173조 제1호/제2호는 구법 양벌규정 자체에서 직접 확정하지 않고, 현행 penalty branch에 따라 별도 resolver가 결정해야 한다.

## 4. Corporate Branch Resolver Rule
- 현행 penalty가 산업안전보건법 제167조 제1항이면 제173조 제1호
- 현행 penalty가 제168조, 제169조, 제170조, 제171조, 제172조 계열이면 제173조 제2호
- penalty branch가 불명확하면 제173조 article-level only
- 제173조 제2호를 제1호로 직접 치환하지 않고, old-current mapping layer에서는 제173조 article-level로 낮춘 뒤 penalty-based resolver를 적용한다.

## 5. Refined Mapping Layer
`phase5d_refined_corporate_mapping_layer.csv`는 원본 GT를 대체하지 않는 별도 refined layer다. 모든 행은 `affects_original_gt=false`이며, `reviewer_decision`과 `reviewer_note`는 빈 값으로 남겼다.

## 6. Evaluation Simulation
- total Article 173 branch cases: 21
- article-level match count: 21
- branch-consistent prediction count: 21
- likely old-current fine branch overmapped count: 21
- old-current branch ambiguous count: 0
- true prediction branch error count: 0
- original weighted fine_chain_match_rate: 0.43243243243243246
- phase5b policy-adjusted fine_chain_match_rate: 0.8108108108108109
- phase5d refined-policy fine_chain_match_rate: 0.8108108108108109

이 변화는 모델 개선이 아니라 mapping/evaluation policy refinement 효과다.

## 7. Recommended Evaluation Policy
구법 양벌규정은 현행 제173조 article-level까지만 직접 매핑한다. corporate fine branch는 현행 penalty branch resolver로 결정한다. old-current fine branch ambiguity는 article-level corporate match로 평가하고, overmapping 의심 케이스는 reviewed_eval_layer 후보로 둔다. 수동 검토 전까지 원본 GT는 수정하지 않는다.

## 8. Remaining Limitations
실제 법령 개정 이력 원문 확인과 법률 전문가 검토가 필요하다. refined layer는 원본 GT를 대체하지 않는다. 구법-현행법 fine branch 대응은 모든 케이스에서 자동 확정할 수 없다.

## 9. Next Steps
reviewer_decision이 채워진 뒤 reviewed_eval_layer를 생성하고, old-current mapping review package를 확장한다. 제173조 high-priority case부터 검토하고, 논문/보고서에는 original, policy-adjusted, refined-policy metric을 분리 제시한다.
