# Phase 5-C Manual Review Package Report

## 1. Purpose
Phase 5-C does not improve scores or edit the GT. It packages branch-ambiguous references so a human reviewer can inspect case facts, GT refs, prediction refs, branch consistency, old-current mapping basis, and relevant law text in one place.

GT, prediction outputs, and the original evaluator were not modified.

## 2. Background
Phase 1 separated selected core, supporting bundle, full bundle diagnostics, and candidate recall. Phase 2 reduced strict overgeneration while preserving auxiliary recall. Phase 3 repaired obligation to penalty to corporate penalty chain connectivity. Phase 4 showed that the remaining fine mismatches were not candidate missing problems. Phase 5-A and 5-B showed that Article 173 branch mismatches are mostly GT branch ambiguity rather than prediction branch errors.

Prediction branch wrong count remains `0`.

## 3. Review Targets
- Total review targets: `23`
- Corporate penalty branch review: `21`
- Obligation fine review: `2`
- By dataset: `{"strict": 13, "auxiliary": 10}`
- By priority: `{"HIGH": 21, "MEDIUM": 2}`

## 4. Corporate Penalty Branch Review Package
The corporate package contains Article 173 branch targets, GT penalty/corporate refs, prediction penalty/corporate refs, candidate penalty/corporate refs, old-current mapping evidence, current law text when available, review questions, options, and a recommended default decision.

Recommended decisions are suggestions only. `reviewer_decision` and `reviewer_note` are intentionally blank.

## 5. Obligation Fine Branch Review Package
The obligation package covers the two Article 38 fine-branch cases. It records whether case facts support the GT fine branch, prediction fine branch, or article-level treatment.

## 6. Review Decision Schema
The decision schema defines review outcomes such as `KEEP_GT_FINE_STRICT`, `ARTICLE_LEVEL_ONLY`, `GT_FINE_BRANCH_REVISE_RECOMMENDED`, `EXCLUDE_CORPORATE_FINE_FROM_STRICT`, and `NEED_LEGAL_EXPERT_REVIEW`.

All decision codes keep `affects_original_gt=false`; follow-up changes should live in a reviewed evaluation layer.

## 7. How To Use
Reviewers should open the manual review package CSV files, inspect each row, and fill only `reviewer_decision` and `reviewer_note`. The original GT should remain unchanged. A later reviewed evaluation layer can consume the completed decisions.

## 8. Next Steps
- Create a reviewed evaluation layer after reviewer decisions are filled.
- Keep original strict, policy-adjusted, article-level, branch consistency, and manual-review-pending counts separate in reports.
- Prioritize high-priority Article 173 branch ambiguity cases, then inspect the two Article 38 fine-branch cases.

## 9. Conclusion
The remaining issue is not primarily retrieval or selector failure. It is GT branch ambiguity and fine granularity review. Phase 5-C converts that ambiguity into a manual review workflow while preserving the original dataset and evaluation artifacts.
