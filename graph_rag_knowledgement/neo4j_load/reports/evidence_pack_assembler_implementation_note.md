# Evidence Pack Assembler Implementation Note

## 구현 목적

`EvidencePackAssembler`는 `GraphQueryLayer` 위에서 사용자 query와 intent를 받아 답변 생성 전 단계의 structured evidence pack JSON을 만든다.

이번 구현은 evidence pack 생성까지만 포함한다. 자연어 답변 생성, LLM 호출, FastAPI 연결, UI 연결은 포함하지 않는다.

## 현재 구현 범위

- query와 intent 입력
- intent별 rule-centered/listitem-centered/mixed pack 선택
- Rule 후보 검색 및 Rule evidence expansion
- ListItem 후보 검색 및 `ITEM_RESOLVES_TO` source anchor expansion
- citation candidate beta 생성
- warning 생성
- missing_evidence 생성
- JSON 직렬화 가능한 dict 반환
- smoke test report/sample JSON 생성

## 지원 intent

- `obligation_check`
- `safety_measure_lookup`
- `education_time_lookup`
- `appointment_requirement`
- `document_requirement`
- `penalty_lookup`
- `applicability_check`
- `definition_lookup`
- `inspection_requirement`
- `list_lookup`
- `education_content_lookup`

## Pack 전략

### Rule-centered

Rule 중심 intent는 `search_rules_by_intent_keywords()`로 후보를 찾고, 각 Rule에 대해 `get_rule_evidence_pack_by_rule_id()`로 Requirement, Threshold, Exception, TemporalRule, EntityType, SourceNode, SourceAnchor, RelatedRule을 확장한다.

### ListItem-centered

ListItem 중심 intent는 `get_listitem_evidence()`를 사용한다. 핵심 경로는 다음과 같다.

```text
ListItem -> ITEM_RESOLVES_TO -> Paragraph / Item / Subitem / LogicalRow / LogicalCell / AnnexNote
```

### Mixed

- `education_time_lookup`: Rule + Threshold를 primary로, ListItem/Annex evidence를 supporting으로 사용
- `inspection_requirement`: ListItem evidence를 primary로, Rule evidence를 supporting으로 사용
- `safety_measure_lookup`: Rule evidence를 primary로, ListItem evidence를 supporting으로 사용

## ITEM_RESOLVES_TO 활용 방식

`ITEM_RESOLVES_TO`는 ListItem 3604개 전체를 source anchor에 연결한다. direct `HAS_LIST_ITEM`이 31개뿐인 현재 graph에서 목록형 질의의 핵심 evidence path다.

## warning / missing_evidence 설계

Warning 예:

- needs_review
- UNKNOWN rule_type/subtype
- education_time_lookup인데 threshold 없음
- penalty_lookup인데 related rule 없음
- applicability_check인데 exception/threshold/temporal/entity 부족
- ListItem source anchor 없음
- citation candidate 없음
- top-k ambiguity 가능성

Missing evidence 예:

- primary evidence 없음
- education time threshold 없음
- penalty related violation rule 없음
- inspection/list query인데 ListItem 없음
- ListItem source anchor 없음

## Smoke Test 결과

Smoke test 파일:

- `graph_rag_knowledgement/neo4j_load/evidence_traversal/evidence_pack_assembler_smoke_test_report.txt`
- `graph_rag_knowledgement/neo4j_load/evidence_traversal/evidence_pack_assembler_smoke_test_samples.json`

테스트 query:

- 안전관리자는 어떤 기준으로 선임해야 하나?
- 정기 안전보건교육은 몇 시간 해야 하나?
- 안전검사 대상 기계에는 어떤 것들이 있나?
- 위험성평가 결과를 근로자에게 알려야 하나?
- 과태료가 부과되는 경우는 무엇인가?
- 적용 제외되는 경우가 있나?

PASS 기준:

- evidence pack dict 반환
- status가 `OK` 또는 `OK_WITH_WARNINGS`
- primary evidence 1개 이상
- citation candidate 1개 이상 또는 citation warning 존재
- LLM 사용 없음
- Neo4j write 없음

실행 결과:

- final_status: PASS
- appointment_requirement: OK, primary evidence 5, citation candidates 5
- education_time_lookup: OK_WITH_WARNINGS, primary evidence 5, citation candidates 7
- inspection_requirement: OK_WITH_WARNINGS, primary evidence 10, citation candidates 10
- obligation_check: OK, primary evidence 5, citation candidates 5
- penalty_lookup: OK_WITH_WARNINGS, primary evidence 5, citation candidates 5
- applicability_check: OK, primary evidence 5, citation candidates 5

## 아직 하지 않은 것

- answer generation
- LLM 호출
- claim check
- citation formatter 분리
- FastAPI 연결
- UI 연결
- end-to-end answer evaluation
- production ranking/scoring 최적화

## 다음 단계

1. smoke test 결과를 기준으로 intent별 evidence 품질을 검토한다.
2. `citation_formatter.py`를 분리해 조문/항/호/별표 citation을 정교화한다.
3. `claim_check.py`를 설계해 evidence 없는 답변을 차단한다.
4. 이후에만 FastAPI `/ask` 연결과 answer generation 계층을 붙인다.
