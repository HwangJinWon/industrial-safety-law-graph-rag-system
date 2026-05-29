# v6 Hierarchical Compatible Evaluation

## Change
Added hierarchical-compatible matching without changing GT:

- GT article + prediction paragraph/item/subitem under the same article = compatible hit
- GT paragraph/item + prediction parent article = compatible hit
- same article but different child refs = not compatible
- strict fine exact metrics remain unchanged

Implemented in:
- `project/eval_adapter.py`
- `project/evaluate_v6_case_scenario.py`

Output:
- `project/generated_v6_case_scenario_eval/evaluation_reviewed/hierarchical_compatible/strict_cap7_local/`

## Strict Cap 7 Result

| metric | value |
|---|---:|
| selected fine exact F1 | 0.438 |
| selected hierarchical compatible F1 | 0.469 |
| article-level F1 | 0.455 |
| selected legal-chain F1 | 0.352 |
| candidate fine recall | 0.629 |
| candidate article recall | 0.893 |
| bundle slot F1 | 0.762 |

## Interpretation
The hierarchical-compatible metric confirms that some strict fine misses are actually parent-child granularity mismatches.

The gain is real but moderate:
- fine exact F1: 0.438
- hierarchical compatible F1: 0.469
- delta: +0.030

So the evaluation was somewhat undercounting valid article -> child predictions, but this is not the only bottleneck. Remaining errors still include:
- missing or wrong corporate-penalty child refs
- scope/detail refs absent from exact pool
- selected overgeneration and selected/candidate tier separation

## Recommended Use
Keep all three selected-law metrics:
- `article_level_f1`: article-family correctness
- `selected_hierarchical_compatible_f1`: parent-child compatible correctness
- `fine_level_f1`: strict exact fine-grained correctness

Do not replace strict fine F1; use hierarchical-compatible F1 as the fair middle metric.
