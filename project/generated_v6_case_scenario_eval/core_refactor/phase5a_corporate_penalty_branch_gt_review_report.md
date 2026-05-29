# Phase 5-A Corporate Penalty Branch Ground-Truth Review Report

## 1. 목적
Phase 4 이후 남은 fine mismatch 대부분은 산업안전보건법 제173조 제1호/제2호 branch 문제였다. 이번 단계는 성능 개선이 아니라 GT branch 일관성 감사다.

## 2. 배경
Phase 1~4에서 selected core/supporting/full bundle을 분리했고, chain connection failure를 줄였으며, candidate/article/fine missing이 0인 상태까지 분리했다. 남은 문제는 wrong sibling fine ref다.

## 3. 제173조 branch rule
- 산업안전보건법 제167조 제1항 -> 산업안전보건법 제173조 제1호
- 산업안전보건법 제168조~제172조 -> 산업안전보건법 제173조 제2호

이 rule은 현행법 기준 branch consistency check용이다. 구법-현행법 mapping에서는 fine-level ambiguity를 인정해야 한다.

## 4. GT branch consistency 결과
{
  "OLD_CURRENT_FINE_AMBIGUOUS": 12,
  "INCONSISTENT_OR_MAPPING_AMBIGUOUS": 9
}

Branch review labels:
{
  "PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT": 21
}

## 5. Prediction branch consistency 결과
{
  "CONSISTENT": 21
}

Prediction이 selected penalty branch와 일관적인 경우에는 GT branch를 먼저 검토해야 한다. Prediction branch가 GT와 다르다는 이유만으로 즉시 오답 처리하지 않는다.

## 6. 평가 정책 제안
{
  "REVIEW_GT_BRANCH": 21
}

Fine-level strict는 GT penalty와 GT corporate branch가 함께 일관적인 경우에 유지한다. 구법-현행법 fine branch가 불명확하거나 GT branch가 suspect이면 corporate penalty는 article-level only 또는 GT review로 보낸다.

## 7. 제38조 fine branch 2건 검토
Obligation branch review count: 2

Labels:
{
  "PRED_FINE_SUPPORTED": 2
}

제38조 fine branch는 사실관계로 위험유형이 충분히 특정될 때만 fine-level selected로 유지하고, 그렇지 않으면 article-level selected + supporting evidence가 적절하다.

## 8. Phase 5-B 제안
- 자동 수정은 `VALID_GT_BRANCH_PRED_WRONG`에 한정
- `PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT`는 GT review 대상
- `OLD_CURRENT_FINE_AMBIGUOUS_ARTICLE_ONLY`는 article-level 평가 전환 검토
- 제173조 제2호는 제168~172 penalty branch가 있을 때만 selected

## 9. 결론
남은 fine mismatch는 단순 retrieval/selector 오류가 아니라 branch-level evaluation design 문제다. 자동 보정보다 GT branch consistency와 평가 granularity 조정이 먼저 필요하다.
