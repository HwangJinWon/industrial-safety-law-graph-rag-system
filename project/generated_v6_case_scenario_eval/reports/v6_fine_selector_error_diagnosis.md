# v6 Fine Selector Error Diagnosis

## Question
Why does the fine selector still miss paragraph/item/subitem refs when article-family retrieval is high?

## Data Used
- Result CSV:
  - `project/generated_v6_case_scenario_eval/evaluation_reviewed/fine_selector_diagnosis/strict_cap7_exact_first/case_scenario_api_results.csv`
- Dataset:
  - `project/generated_v6_case_scenario_eval/review_upgrade/v6_reviewed_case_scenario_eval_ready.json`
- Law ref index:
  - `project/generated_v4_current_strict/fine_grained/law_ref_index.csv`

## Key Finding
The dominant issue is not current-law mapping and not that statutes fail to encode the field situation.

The main issues are:
1. mixed GT granularity inside the same article family,
2. redundant parent/child GT refs,
3. selected-tier compression to article representatives,
4. a smaller number of genuine fine-selector choices.

## Same-Article Fine Misses After Exact-First Matching

Remaining same-article but not hierarchical-compatible misses:
- total: 21
- 산업안전보건법 제173조: 18
- 산업안전보건법 제38조: 2
- 중대재해처벌법 제6조: 1

Top pair patterns:
- GT `산업안전보건법 제173조` vs selected `산업안전보건법 제173조 제1호`: 12
- GT `산업안전보건법 제173조` vs selected `산업안전보건법 제173조 제2호`: 11
- GT `산업안전보건법 제173조 제2호` vs selected `산업안전보건법 제173조 제1호`: 6
- GT `산업안전보건법 제38조 제3항 제1호` vs selected `산업안전보건법 제38조`: 2
- GT `중대재해처벌법 제6조` vs selected `중대재해처벌법 제6조 제1항`: 1

## Law-Text Interpretation

### 산업안전보건법 제173조
Article 173 is the corporate penalty provision.

The fine-grained split is meaningful:
- 제173조 제1호: 제167조 제1항의 경우
- 제173조 제2호: 제168조부터 제172조까지의 경우

For death cases where the relevant OSHA penalty is `제167조 제1항`, selecting `제173조 제1호` is legally natural.

Many reviewed GT bundles include a broad corporate penalty set:
- `제173조`
- `제173조 제1호`
- `제173조 제2호`

When the selector picks only `제173조 제1호`, it is often not a true legal mistake. It is a compact selected answer choosing the death/167(1) branch, while the GT also expects the broad article and/or the alternative branch.

### 산업안전보건법 제38조
Article 38 is the safety-measure obligation.

The fine-grained split is meaningful:
- 제38조 제1항: machinery/equipment, explosive/flammable substances, electricity/heat/energy risks
- 제38조 제2항: excavation, quarrying, loading/unloading, logging, transport, heavy objects, etc.
- 제38조 제3항 제1호: places with fall risk
- 제38조 제3항 제2호: collapse risk

The selector currently compresses obligation refs to the representative article (`제38조`) for selected_laws. So misses such as GT `제38조 제3항 제1호` vs selected `제38조` are primarily a selected-tier compression choice, not inability to retrieve the fine ref.

### 중대재해처벌법 제6조
Article 6 is the penalty provision.

The fine-grained split is meaningful:
- 제6조 제1항: death-type serious industrial accident under 제2조 제2호 가목
- 제6조 제2항: injury/disease-type serious industrial accident under 제2조 제2호 나목/다목
- 제6조 제3항: recidivism aggravation

For death cases, selecting `제6조 제1항` when GT includes broad `제6조` is a useful specialization, not a selector error.

## Diagnosis By Cause

### A. Evaluation/GT Granularity Mismatch
Cases where GT contains parent article and child refs together cause one selected child ref to be insufficient under one-to-one scoring.

Example:
- GT: `제173조`, `제173조 제1호`, `제173조 제2호`
- selected: `제173조 제1호`

This is not the same as selecting a wrong law. It means the selected answer compacted the corporate penalty branch.

### B. Selected-Tier Compression
For obligation provisions such as `제38조`, selector intentionally keeps article-level representatives in selected_laws. This improves compactness and article-level precision but lowers strict fine recall.

### C. Real Fine Selector Error
The genuine fine selector issue is narrower:
- Some GT expects both `제173조 제1호` and `제173조 제2호`, but the selected answer keeps only one branch.
- If the case actually contains both death/167(1) and non-167 penalty branches, selected_laws may need both.
- If the case is purely death/167(1), keeping only `제173조 제1호` is reasonable and the GT is broad.

## Conclusion
The fine-level drop is not mainly because the law text cannot represent the field situation.

It is mostly due to:
- GT bundles mixing broad article refs and fine child refs,
- selected answer compression,
- one-to-many parent/child relation not fully represented by exact F1,
- and a smaller remaining need for branch-aware corporate-penalty selection.

The next implementation target should be:
1. keep `article_level_f1` and `selected_hierarchical_compatible_f1` as fair selected metrics,
2. add a branch-aware selected policy for `제173조`:
   - death + `제167조 제1항` -> prioritize `제173조 제1호`
   - non-death/general penalty `제168~제172조` -> prioritize `제173조 제2호`
   - if GT/case bundle expects both branches, allow both under corporate_penalty cap,
3. keep `제38조` as article-level selected by default, but expose child refs in supporting/candidate unless the task is explicitly fine-grained detail selection.
