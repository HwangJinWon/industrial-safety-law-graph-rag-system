# Phase 5-B Policy-Adjusted Evaluation Report

## 1. 목적
Phase 5-A에서 확인된 산업안전보건법 제173조 branch ambiguity를 평가 정책에 반영했다. GT와 prediction은 수정하지 않았고, 기존 strict metric과 policy-adjusted metric을 분리해 산출했다.

## 2. 배경
Phase 1~5-A를 통해 남은 fine mismatch가 candidate/retrieval 문제가 아니라 제173조 branch ambiguity와 제38조 GT fine review 문제임을 확인했다.

## 3. Policy-adjusted evaluation rules
- Corporate penalty branch ambiguity: Article 173 item mismatch는 prediction branch가 selected penalty branch와 일관적이고 GT branch가 ambiguous/suspect이면 fine strict 오답과 분리한다.
- Prediction branch consistency: Article 167(1) -> Article 173 item 1은 valid corporate branch로 본다.
- Article 173 item 2: Article 168-172 penalty branch가 selected/high-confidence일 때만 selected 정당화.
- Article 38 fine branch: PRED_FINE_SUPPORTED / REVIEW_GT_FINE은 article-level obligation match로 별도 처리하고 strict fine은 diagnostic으로 유지.
- Original metric and policy-adjusted metric are reported separately.

## 4. Strict 결과
- original selected_core_f1: 0.581
- policy-adjusted selected_core_f1: 0.581
- original precision/recall: 0.482 / 0.814
- policy precision/recall: 0.482 / 0.814
- original fine_chain_match_rate: 0.259
- policy fine_chain_match_rate: 0.741
- corporate branch consistency rate: 0.407
- ambiguity adjustment count: 0.481

## 5. Auxiliary 결과
- original selected_core_f1: 0.811
- policy-adjusted selected_core_f1: 0.811
- original precision/recall: 0.717 / 0.938
- policy precision/recall: 0.717 / 0.938
- original fine_chain_match_rate: 0.900
- policy fine_chain_match_rate: 1.000
- corporate branch consistency rate: 1.000
- ambiguity adjustment count: 1.000

## 6. Ambiguity adjustment 분석
Total policy adjustment targets: 23

Article 173 branch ambiguity is separated from direct prediction error when prediction branch is consistent with selected penalty and GT branch is old-current ambiguous or internally suspect. Article 38 fine review targets are counted as article-level obligation matches in the policy-adjusted metric.

## 7. 해석
Policy-adjusted score 상승은 시스템 개선이 아니라 평가 기준 정교화 효과다. Prediction이 제167조 제1항 -> 제173조 제1호 branch와 일관적이었다는 점을 별도 지표로 보고한다.

## 8. 논문/보고서용 권장 표현
“Fine-grained mismatches involving Article 173 were not treated as direct prediction errors when the predicted corporate-penalty subparagraph was consistent with the selected penalty article and the ground-truth branch was marked as old-current mapping ambiguous or internally inconsistent. In such cases, we preserved the original GT but reported an additional policy-adjusted metric that evaluates corporate penalty at the article level and separately reports branch consistency.”

“산업안전보건법 제173조 제1호/제2호 관련 fine-level mismatch 중 일부는 예측 오류라기보다 구법-현행법 세부 호 대응 및 GT branch 확정의 불확실성에서 비롯된 것으로 판단하였다. 따라서 원본 GT는 유지하되, 해당 케이스에 대해 fine-level strict 지표와 별도로 article-level corporate penalty match 및 branch consistency 지표를 병행 보고하였다.”

## 9. 남은 한계
- GT branch를 실제로 수정한 것은 아니다.
- 법률 전문가 또는 원문 기반 수동 검토가 여전히 필요하다.
- 제38조 fine branch는 case facts가 충분하지 않으면 fine-level 자동 판단이 어렵다.
- policy-adjusted metric은 supplementary metric으로 제시해야 한다.

## 10. 다음 단계 제안
- Phase 5-C: GT branch manual review package 생성
- 제173조 branch review 대상 원문/evidence pack 묶기
- 제38조 2건 원문 사실관계와 GT fine 근거 비교
- 논문 평가표에는 original strict, policy-adjusted, article-level, branch consistency를 함께 제시
