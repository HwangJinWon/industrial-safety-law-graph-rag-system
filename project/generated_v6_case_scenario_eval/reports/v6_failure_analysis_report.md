# V6 Failure Analysis

## Failure Type Counts
`{"candidate_only_match": 11, "selected_scope_definition_missing": 4, "selected_corporate_penalty_missing": 12, "unknown": 12, "selected_penalty_missing": 1}`

## Example Cases
- 1: 산업안전보건법위반·업무상과실치사·중대재해처벌등에관한법률위반(산업재해치사) / candidate_only_match
- 2: 산업안전보건법위반·업무상과실치사·중대재해처벌등에관한법률위반(산업재해치사) / candidate_only_match
- 3: 산업안전보건법위반·업무상과실치사·중대재해처벌등에관한법률위반(산업재해치사) / selected_scope_definition_missing
- 4: 산업안전보건법위반·업무상과실치사·중대재해처벌등에관한법률위반(산업재해치사) / candidate_only_match
- 5: 산업안전보건법위반·업무상과실치사·중대재해처벌등에관한법률위반(산업재해치사) / candidate_only_match
- 6: 산업안전보건법위반·중대재해처벌등에관한법률위반(산업재해치사)[중대재해 처벌 등에 관한 법률 부칙 제1조 제1항 단서의 ‘상시 근로자가 50명 미만인 사업 또는 사업장’의 해석이 문제된 사건] / candidate_only_match
- 7: 업무상과실치사·산업안전보건법위반·중대재해처벌등에관한법률위반(산업재해치사) / candidate_only_match
- 8: 업무상과실치사·산업안전보건법위반·중대재해처벌등에관한법률위반(산업재해치사) / candidate_only_match
- 13: 산업안전보건법위반 / selected_corporate_penalty_missing
- 14: 산업안전보건법 위반·업무상과실치사 / selected_corporate_penalty_missing
- 15: 산업안전보건법 위반 / unknown
- 21: 업무상과실치사·업무상과실치상·산업안전보건법위반 / selected_corporate_penalty_missing
- 22: 업무상과실치사·업무상과실치상·산업안전보건법위반 / selected_corporate_penalty_missing
- 26: 업무상과실치사·업무상과실치상·산업안전보건법위반 / selected_corporate_penalty_missing
- 27: 증거인멸·산업안전보건법위반 / selected_corporate_penalty_missing

## Common Causes
- case facts are still automatically extracted and may be incomplete.
- B-grade old-current mappings are excluded, so some expected bundles are intentionally sparse.
- selected selector remains conservative; some correct refs may stay in supporting/candidate.
