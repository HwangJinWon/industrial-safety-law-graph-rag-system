# Phase 6 Report-Ready Interpretation

## 1. Evaluation design summary

### Korean
본 평가는 단순 법령 QA가 아니라 판례/사고 상황을 입력했을 때 적용 가능한 의무 조문, 처벌 조문, 양벌규정, 그리고 obligation -> penalty -> corporate penalty legal chain을 복원하는 case-scenario evaluation이다. 평가 과정에서는 compact selected answer와 full legal bundle을 동일하게 취급하지 않고, selected core, supporting bundle, full bundle diagnostic, candidate recall을 분리했다.

### English
This evaluation is not a simple statute-QA benchmark. It is a case-scenario evaluation that tests whether the system can reconstruct applicable obligation provisions, penalty provisions, corporate-penalty provisions, and the obligation-to-penalty-to-corporate-penalty legal chain from precedent or accident facts. We separate selected-core evaluation, supporting-bundle recovery, full-bundle diagnostics, and candidate recall.

## 2. Main findings

### Korean
초기 fine-level F1 저하는 selector 실패만으로 설명되지 않았다. 단계별 오류 분해를 통해 평가 구조 문제, selected 과생성, candidate fine recall, chain connection, branch ambiguity, old-current fine branch overmapping을 분리했다. strict selected_core_f1은 0.553에서 0.581로 개선되었고, auxiliary selected_core_f1은 soft-cap recall guard 이후 0.811로 회복되었다. corporate penalty attachment는 strict/auxiliary 모두 1.000으로 안정화되었다. original strict fine_chain_match_rate는 0.259였으나, 제173조 branch ambiguity를 분리한 policy-adjusted 기준에서는 0.741로 해석되었다. Phase 5-D refined mapping audit에서는 제173조 branch case 21건이 likely old-current fine branch overmapped로 분류되었다. 이 상승은 prediction 수정이 아니라 evaluation granularity 및 old-current mapping interpretation adjustment이다.

### English
The initially low fine-level F1 was not explained by selector failure alone. Through staged error decomposition, we separated evaluation-design mismatch, selected-reference overgeneration, candidate fine recall, chain-connection failures, branch ambiguity, and old-current fine-branch overmapping. Strict selected_core_f1 improved from 0.553 to 0.581, while auxiliary selected_core_f1 recovered to 0.811 after the soft-cap recall guard. Corporate penalty attachment stabilized at 1.000 for both strict and auxiliary splits. The original strict fine_chain_match_rate was 0.259, but after separating Article 173 branch ambiguity, the policy-adjusted interpretation was 0.741. Phase 5-D classified 21 Article 173 branch cases as likely old-current fine-branch overmapping. This increase is an evaluation-granularity and old-current mapping interpretation adjustment, not a prediction improvement.

## 3. Recommended wording for paper/report

The initially low fine-level F1 was not solely caused by retrieval or selector failure. Through staged error decomposition, we found that the major sources of apparent error were: mismatch between compact selected answers and full legal bundles, overgeneration in selected references, incomplete fine-grained candidate generation, legal-chain connection failures, and fine-level branch ambiguity in corporate penalty provisions. In particular, the remaining Article 173 mismatches were classified as likely old-to-current fine-branch overmapping rather than prediction branch errors. After separating selected-core evaluation from supporting-bundle recovery, branch-ambiguity diagnostics, and refined old-current mapping interpretation, the system showed stable core legal-chain construction performance, while the remaining mismatches were concentrated in manually reviewable GT branch ambiguity cases.

초기 fine-level F1 저하는 단순 검색 또는 selector 실패만으로 설명되지 않았다. 단계별 오류 분해 결과, compact selected answer와 full legal bundle 간 평가 불일치, selected ref 과생성, fine-grained candidate 누락, legal chain 연결 실패, 그리고 양벌규정 fine branch ambiguity가 주요 원인으로 확인되었다. 특히 산업안전보건법 제173조 관련 남은 mismatch는 prediction branch error라기보다 구법-현행법 fine branch overmapping 문제로 분류되었다. selected-core 평가, supporting-bundle 평가, policy-adjusted branch consistency 평가, refined old-current mapping 해석을 분리한 결과, 시스템의 핵심 법리 chain 구성 능력은 안정적으로 나타났으며, 남은 오류는 대부분 수동 검토가 필요한 GT branch ambiguity로 좁혀졌다.

## 4. Cautionary notes

- Policy-adjusted score must not be interpreted as model improvement.
- Refined-policy score must not be interpreted as model improvement.
- The original GT was not modified.
- The refined mapping layer does not replace original GT.
- Policy-adjusted/refined-policy metrics are supplementary diagnostics.
- Article 173 subparagraph matching may involve old-current mapping ambiguity.
- The 23 manual-review-pending targets should be managed through a reviewed_eval_layer.

## 5. Next steps

- Create a reviewed_eval_layer after reviewer_decision fields are filled.
- Manage original GT and reviewed_eval_layer separately.
- Prioritize legal expert review for high-priority Article 173 cases.
- Review the two Article 38 fine-branch cases.
- Report original strict, policy-adjusted, refined-policy, article-level, branch consistency, and manual-review-pending counts together.
