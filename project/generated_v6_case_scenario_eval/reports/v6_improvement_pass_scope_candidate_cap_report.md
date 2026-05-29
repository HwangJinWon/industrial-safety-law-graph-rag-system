# v6 Improvement Pass: Scope + Candidate Cap

## What Changed
- Added granularity-compatible article diagnostics in `project/eval_adapter.py`.
- Added case-facts based supporting refs for scope/definition, serious-accident detail, health/detail, and contractor refs.
- Applied tier-level candidate/supporting ref caps so broad backend expansions do not flood evaluation tiers.
- Limited backend bundle completion to preserve multiple fine-grained rows per article while capping rows per requested article.

## Strict Cap 7 Results

| run | article F1 | fine F1 | chain F1 | bundle slot F1 | candidate fine recall | candidate article recall | selected+supporting article recall | supporting count | candidate count | candidate_only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| selector_v3_cap7 | 0.453 | 0.438 | 0.352 | 0.744 | 0.609 | 0.828 | 0.828 | 31.48 | 17.74 | 8 |
| backend_fine_expansion | 0.455 | 0.438 | 0.352 | 0.768 | 0.629 | 0.828 | 0.828 | 39.48 | 25.74 | 8 |
| scope_candidate_cap | 0.455 | 0.438 | 0.352 | 0.762 | 0.629 | 0.893 | 0.889 | 8.96 | 19.74 | 10 |

## Diagnosis
- The case-facts supporting policy improves article-level candidate coverage substantially.
- The tier cap reduces supporting/candidate tier size compared with raw backend fine expansion.
- selected metrics remain stable because selected selector cap 7 filters the expanded supporting/candidate pool.
- exact candidate-only failures increased from 8 to 10 because the remaining misses are mostly fine-grained exact refs, especially mixed article/item GT around corporate penalties.

## Keep / Reconsider
Keep:
- granularity-compatible diagnostics
- candidate/supporting tier caps
- backend same-article fine row preservation
- case-facts supporting policy for article-level coverage

Reconsider before making this the default:
- case-facts supporting policy should stay supporting-only.
- exact candidate-only count is slightly worse than selector_v3_cap7.
- `candidate_article_recall` is the main improved metric; `candidate_fine_recall` remains the next bottleneck.

## Next Concrete Fix
- Handle mixed article/item GT around `산업안전보건법 제173조` explicitly in evaluation, or keep it as article-compatible rather than strict-fine success.
- Add targeted fine-edge selection for corporate penalty article families instead of broad completion expansion.
- Keep cap 7 as selected default; use scope_candidate_cap outputs as diagnostic/retrieval-coverage mode.
