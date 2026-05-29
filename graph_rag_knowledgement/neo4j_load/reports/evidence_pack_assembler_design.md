# Evidence Pack Assembler Design

## 1. Purpose

Evidence Pack Assembler는 Graph-RAG 답변 생성 전 단계에서 동작하는 read-only graph evidence 구성 모듈이다.

- raw retrieval result를 그대로 LLM에 전달하지 않는다.
- 검색된 Rule, Requirement, Threshold, Exception, EntityType, ListItem, SourceNode, SourceAnchor를 하나의 evidence pack으로 묶는다.
- LLM은 evidence pack에 포함된 근거만 사용해 답변해야 한다.
- 답변 생성, LLM 호출, ranking/scoring 구현은 이 문서 범위가 아니다.

## 2. Current Neo4j Graph State

- target database: graph.v1
- validation status: LOAD_PASS_WITH_WARNINGS
- evidence traversal status: EVIDENCE_TRAVERSAL_PASS_WITH_WARNINGS
- Rule: 8858
- SourceNode: 8858
- ListItem: 3604
- EXTRACTED_FROM: 8858
- RESOLVES_TO: 8858
- ITEM_RESOLVES_TO: 3604
- Rule source_text missing: 0
- rules_without_source: 0
- unresolved SourceNode: 0
- ListItem without ITEM_RESOLVES_TO: 0
- Document/Annex source anchor 적재 완료
- source hierarchy 적재 완료
- ListItem source anchor 보강 적재 완료

## 3. Evidence Pack 기본 구조

제안 JSON 구조:

```json
{
  "query": "...",
  "intent": "...",
  "primary_evidence": [
    {
      "rule_id": "...",
      "rule_type": "...",
      "rule_subtype": "...",
      "law_name": "...",
      "article_no": "...",
      "annex_title": "...",
      "source_text": "...",
      "requirements": [],
      "thresholds": [],
      "exceptions": [],
      "temporal_conditions": [],
      "entities": [],
      "list_items": [],
      "source_anchors": [],
      "related_rules": []
    }
  ],
  "supporting_evidence": [],
  "warnings": [],
  "missing_evidence": [],
  "citation_candidates": []
}
```

구성 원칙:

- `primary_evidence`는 답변의 핵심 근거다.
- `supporting_evidence`는 문맥, 관련 규정, 별표/별지, 목록형 항목 등 보조 근거다.
- `warnings`는 needs_review, UNKNOWN, evidence gap, 다중 후보 충돌 등을 기록한다.
- `missing_evidence`는 intent상 필요하지만 graph에서 찾지 못한 근거를 기록한다.
- `citation_candidates`는 답변 말미에 붙일 법령/조문/별표 인용 후보를 제공한다.

## 4. 공통 Evidence Expansion 경로

### A. Rule 중심 경로

```text
Rule
-> Requirement
-> Threshold
-> Exception
-> TemporalRule
-> EntityType
-> SourceNode
-> SourceAnchor
-> RelatedRule
```

사용 목적:

- 의무, 금지, 처벌, 적용 제외, 교육시간 등 Rule 중심 질문의 기본 경로다.
- Rule의 `source_text`와 `EXTRACTED_FROM` 경로를 함께 가져와 citation 근거를 만든다.
- `RELATED_RULE`은 처벌 규정과 원 의무/금지 규정의 보조 연결로 사용한다.

### B. Source 중심 경로

```text
Rule
-> SourceNode
-> Article / Paragraph / Item / Subitem / LogicalRow / LogicalCell / AnnexNote
```

사용 목적:

- Rule이 어느 원문 anchor에서 추출되었는지 확인한다.
- Article/Paragraph/Item/Subitem 또는 Annex LogicalRow/LogicalCell/AnnexNote를 citation 후보로 구성한다.
- 현재 SourceNode unresolved는 0이므로 기본 evidence path로 사용할 수 있다.

### C. Document context 경로

```text
Law -> Heading -> Article -> Paragraph -> Item -> Subitem
```

사용 목적:

- 조문 문맥 확장, 상위 조문 제목, 항/호/목 주변 문맥을 구성한다.
- Law -> Article direct shortcut은 의도적으로 만들지 않았다.
- 원본 계층 구조인 Law -> Heading -> Article을 따른다.

### D. Annex context 경로

```text
Annex -> Article
Annex -> LogicalRow -> LogicalCell
Annex -> AnnexNote
```

사용 목적:

- 별표/별지 기반 표, 목록, 주석 evidence를 구성한다.
- 교육시간, 교육내용, 검사 대상, 장비 목록, 유해인자 목록 등에 특히 중요하다.

### E. ListItem 중심 경로

```text
ListItem
-> ITEM_RESOLVES_TO
-> Paragraph / Item / Subitem / LogicalRow / LogicalCell / AnnexNote
```

사용 목적:

- HAS_LIST_ITEM direct edge가 31개뿐인 한계를 보완한다.
- ListItem 3604개 모두 source anchor에 연결되어 있으므로 목록형 evidence pack의 핵심 경로로 사용한다.
- ListItem -> SourceNode 직접 연결은 NOT_READY였으므로 사용하지 않는다.

## 5. Intent별 Evidence Pack 설계

### 1. obligation_check

필요 evidence:

- Rule
- Requirement
- EntityType
- SourceNode
- Article/Paragraph/Item/Subitem context

Traversal strategy:

- Rule 후보를 intent/rule_type/rule_subtype/entity keyword로 가져온다.
- `HAS_REQUIREMENT`, `RELATED_ENTITY`, `EXTRACTED_FROM`, `RESOLVES_TO`를 확장한다.
- source anchor가 Article/Paragraph/Item/Subitem이면 문서 계층을 따라 주변 문맥을 추가한다.

Fallback:

- Requirement가 없으면 `Rule.requirement_text` 또는 `Rule.source_text`를 evidence로 사용한다.

### 2. safety_measure_lookup

필요 evidence:

- Rule
- Requirement
- Threshold
- Source context
- work/equipment/hazard 키워드

Traversal strategy:

- 안전조치, 작업, 설비, 유해위험요인 키워드를 Rule/Requirement/EntityType/ListItem에 대해 함께 탐색한다.
- Requirement와 Threshold가 있으면 함께 묶는다.
- SourceNode와 source anchor로 조문 또는 별표 근거를 붙인다.

주의:

- broad safety overmatch를 방지해야 한다.
- "안전"이라는 일반 단어만으로 너무 넓은 Rule을 가져오면 감점한다.

### 3. education_time_lookup

필요 evidence:

- Education Rule
- Threshold
- Annex LogicalRow/LogicalCell if table-based
- SourceNode
- Article/Annex citation

Traversal strategy:

- Rule subtype, source_text, annex_title에서 교육/시간 관련 후보를 찾는다.
- `HAS_THRESHOLD`가 있는 Rule을 우선한다.
- 별표 기반이면 Annex -> LogicalRow -> LogicalCell 또는 ListItem -> ITEM_RESOLVES_TO -> LogicalRow/LogicalCell을 확장한다.

주의:

- 교육시간과 교육내용을 혼동하지 않는다.
- 시간/횟수/기간 단위가 없는 교육 후보는 warning 또는 낮은 점수를 준다.

### 4. education_content_lookup

필요 evidence:

- Rule
- ListItem
- ITEM_RESOLVES_TO source anchor
- Annex LogicalRow/LogicalCell

Traversal strategy:

- EDUCATION_CONTENT_ITEM 또는 교육내용 관련 ListItem을 적극 사용한다.
- ListItem -> ITEM_RESOLVES_TO -> LogicalRow/LogicalCell 경로로 표/목록 근거를 확장한다.
- 관련 Rule이 있으면 supporting evidence로 붙인다.

주의:

- EDUCATION_TIME만 있는 후보는 content 질문에서 감점한다.

### 5. appointment_requirement

필요 evidence:

- Rule
- Requirement
- EntityType
- Qualification ListItem 가능
- Source citation

Traversal strategy:

- 선임/지정/자격/인력 요건 키워드로 Rule과 EntityType을 찾는다.
- Requirement와 Qualification ListItem을 함께 묶는다.
- source anchor를 통해 조문 단위 citation을 구성한다.

### 6. document_requirement

필요 evidence:

- Rule
- Requirement
- Threshold/TemporalRule
- Source citation

Traversal strategy:

- 제출, 작성, 보존, 게시, 기록, 보고 키워드를 중심으로 Rule/Requirement를 찾는다.
- 기간/기한이 있으면 Threshold 또는 TemporalRule을 함께 포함한다.
- SourceNode와 Article/Paragraph context로 citation을 만든다.

### 7. penalty_lookup

필요 evidence:

- Penalty Rule
- Related obligation/prohibition Rule
- SourceNode
- Article context

Traversal strategy:

- `rule_type = PENALTY` 또는 penalty subtype을 우선한다.
- `RELATED_RULE`로 관련 의무/금지 Rule을 확장한다.
- penalty source_text와 관련 Rule source_text를 분리해서 제공한다.

주의:

- penalty rule만 있고 위반 행위가 불명확하면 warning을 추가한다.

### 8. applicability_check

필요 evidence:

- Rule
- Exception
- SCOPE_EXCLUSION
- Threshold
- TemporalRule
- EntityType

Traversal strategy:

- `HAS_EXCEPTION`, `HAS_THRESHOLD`, `HAS_TEMPORAL_CONDITION`, `RELATED_ENTITY`를 함께 확장한다.
- 적용 범위/제외/예외/대상 사업장/상시근로자 수 등 조건을 분리해서 evidence field로 만든다.

주의:

- 일반 EXCLUSION과 SCOPE_EXCLUSION을 구분한다.

### 9. definition_lookup

필요 evidence:

- DEFINITION Rule
- exact term match
- SourceNode
- Article context

Traversal strategy:

- 정의 대상 용어와 정확히 매칭되는 Rule을 우선한다.
- SourceNode -> Article/Paragraph 경로로 정의 조문을 citation한다.

### 10. inspection_requirement / list_lookup

필요 evidence:

- ListItem
- ITEM_RESOLVES_TO source anchor
- Annex/LogicalRow/LogicalCell
- related Rule이 있으면 supporting evidence

Traversal strategy:

- ListItem 중심 검색을 적극 사용한다.
- 안전검사, 검사대상, 장비명, 항목명, 별표명 키워드를 ListItem.item_text, source_context_text, annex_title에 적용한다.
- ListItem -> ITEM_RESOLVES_TO -> LogicalRow/LogicalCell 또는 Paragraph/Item/Subitem을 확장한다.
- 관련 Rule이 검색되면 supporting evidence에 추가한다.

주의:

- HAS_LIST_ITEM이 31개뿐이므로 ListItem 중심 경로를 적극 사용한다.

## 6. Evidence Pack Scoring 개념

구현은 이 문서 범위가 아니며, 아래는 설계 개념이다.

점수 요소:

- keyword match
- intent compatibility
- rule_type/subtype compatibility
- entity match
- threshold presence
- exception presence
- list item match
- source quality
- graph distance
- needs_review penalty
- UNKNOWN penalty
- overmatch penalty

주의:

- 이 점수는 법적 중요도 점수가 아니라 retrieval/evidence assembly 점수다.
- query_id hardcoding은 금지한다.
- 특정 평가셋에 과적합하지 않도록 intent, keyword, graph path 기반으로 일반화한다.

## 7. Citation Formatting 설계

답변에 포함할 citation 후보:

- law_name
- article_no
- paragraph_no
- item_no
- annex_title
- source_text
- source_anchor label/id

형식 예:

- 산업안전보건법 제○조
- 산업안전보건기준에 관한 규칙 제○조 제○항 제○호
- 별표 ○ 「제목」
- 별지/서식명

Citation formatter는 가능한 한 source anchor의 실제 property를 사용한다. Article은 `article_no_display`, Paragraph/Item/Subitem은 각 번호 및 `text`, Annex는 `annex_no`와 `annex_title`을 우선한다.

## 8. Warning / Guardrail 설계

Evidence pack에 warning을 포함해야 하는 경우:

- needs_review true
- UNKNOWN rule_type/subtype
- source_text missing, 현재는 0이어야 함
- Rule은 찾았지만 Requirement 없음
- Threshold 질문인데 Threshold 없음
- ListItem은 찾았지만 source anchor 없음, 현재는 없어야 함
- penalty 질문인데 related obligation 없음
- applicability 질문인데 exception 없음
- 여러 후보가 동률 또는 서로 다른 법령을 가리킴
- source anchor는 있으나 citation에 필요한 표시용 번호/제목이 부족함

Guardrail:

- evidence pack에 없는 내용을 답변하지 않는다.
- 법적 판단이 필요한 경우 "제공된 근거 기준"임을 명시한다.
- UNKNOWN/needs_review는 오류가 아니라 품질 신호로 표시한다.

## 9. Read-only Cypher Query Templates

아래 query는 설계 템플릿이며, 이 문서 작성 과정에서 실행하지 않았다.

### Rule evidence pack query

```cypher
MATCH (r:Rule)
WHERE r.rule_id IN $rule_ids
OPTIONAL MATCH (r)-[:HAS_REQUIREMENT]->(req:Requirement)
OPTIONAL MATCH (r)-[:HAS_THRESHOLD]->(th:Threshold)
OPTIONAL MATCH (r)-[:HAS_EXCEPTION]->(ex:Exception)
OPTIONAL MATCH (r)-[:HAS_TEMPORAL_CONDITION]->(tmp:TemporalRule)
OPTIONAL MATCH (r)-[er:RELATED_ENTITY]->(ent:EntityType)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
OPTIONAL MATCH (r)-[rr:RELATED_RULE]->(related:Rule)
RETURN
  r,
  collect(DISTINCT req) AS requirements,
  collect(DISTINCT th) AS thresholds,
  collect(DISTINCT ex) AS exceptions,
  collect(DISTINCT tmp) AS temporal_conditions,
  collect(DISTINCT {rel: er.rel, entity: ent}) AS entities,
  collect(DISTINCT src) AS source_nodes,
  collect(DISTINCT anchor) AS source_anchors,
  collect(DISTINCT {rel: rr.rel, rule: related}) AS related_rules;
```

### Threshold evidence query

```cypher
MATCH (r:Rule)-[:HAS_THRESHOLD]->(th:Threshold)
WHERE r.rule_subtype CONTAINS $intent_keyword
   OR r.source_text CONTAINS $query_keyword
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
RETURN r, th, src, anchor
LIMIT $limit;
```

### Exception evidence query

```cypher
MATCH (r:Rule)-[:HAS_EXCEPTION]->(ex:Exception)
WHERE r.source_text CONTAINS $query_keyword
   OR ex.condition_text CONTAINS $query_keyword
OPTIONAL MATCH (r)-[:HAS_THRESHOLD]->(th:Threshold)
OPTIONAL MATCH (r)-[:HAS_TEMPORAL_CONDITION]->(tmp:TemporalRule)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
RETURN r, ex, th, tmp, src, anchor
LIMIT $limit;
```

### Penalty evidence query

```cypher
MATCH (r:Rule)
WHERE r.rule_type = "PENALTY"
   OR r.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE"]
OPTIONAL MATCH (r)-[rel:RELATED_RULE]->(related:Rule)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
RETURN
  r AS penalty_rule,
  collect(DISTINCT {rel: rel.rel, rule: related}) AS related_rules,
  collect(DISTINCT src) AS source_nodes,
  collect(DISTINCT anchor) AS source_anchors
LIMIT $limit;
```

### List item evidence query using ITEM_RESOLVES_TO

```cypher
MATCH (li:ListItem)-[ir:ITEM_RESOLVES_TO]->(anchor)
WHERE li.item_text CONTAINS $query_keyword
   OR li.source_context_text CONTAINS $query_keyword
   OR li.annex_title CONTAINS $query_keyword
OPTIONAL MATCH (ann:Annex)-[:HAS_LOGICAL_ROW]->(anchor)
OPTIONAL MATCH (ann2:Annex)-[:HAS_LOGICAL_ROW]->(:LogicalRow)-[:HAS_LOGICAL_CELL]->(anchor)
RETURN
  li,
  ir.source_node_type AS source_node_type,
  labels(anchor) AS anchor_labels,
  anchor,
  coalesce(ann, ann2) AS annex
LIMIT $limit;
```

### Annex logical evidence query

```cypher
MATCH (ann:Annex)-[:HAS_LOGICAL_ROW]->(lr:LogicalRow)-[:HAS_LOGICAL_CELL]->(lc:LogicalCell)
WHERE ann.annex_title CONTAINS $query_keyword
   OR lr.source_text CONTAINS $query_keyword
   OR lc.source_text CONTAINS $query_keyword
RETURN ann, lr, collect(lc)[0..20] AS cells
LIMIT $limit;
```

### Source hierarchy context query

```cypher
MATCH (law:Law)-[:CONTAINS]->(h:Heading)-[:CONTAINS]->(a:Article)
WHERE a.article_id = $article_id
OPTIONAL MATCH (a)-[:CONTAINS]->(p:Paragraph)
OPTIONAL MATCH (p)-[:CONTAINS]->(i:Item)
OPTIONAL MATCH (i)-[:CONTAINS]->(s:Subitem)
RETURN law, h, a, collect(DISTINCT p) AS paragraphs, collect(DISTINCT i) AS items, collect(DISTINCT s) AS subitems;
```

## 10. Implementation Plan

향후 구현 순서:

1. `graph_query_layer.py`
2. `evidence_pack_assembler.py`
3. `intent_classifier.py`
4. `citation_formatter.py`
5. `claim_check.py`
6. FastAPI `/ask` 연결
7. UI evidence chip 표시
8. end-to-end answer evaluation

구현 원칙:

- 모든 graph query는 read-only로 시작한다.
- Neo4j 직접 수정보다 CSV patch 후 reload 원칙을 유지한다.
- LLM 답변 모듈보다 evidence pack 구성과 citation 정확도를 먼저 검증한다.

## 11. Current Limitations

- UNKNOWN: 1995
- needs_review: 513
- HAS_LIST_ITEM direct edge: 31
- 일부 Rule에는 Requirement/Threshold 누락 가능
- PhysicalTable/Row/Cell 미적재
- Law -> Article shortcut 없음
- 답변 생성은 아직 미구현
- Evidence Pack Assembler 구현 전이므로 scoring/intent routing은 설계 단계다.

## 12. Final Recommendation

현재 graph.v1은 Evidence Pack Assembler 설계/구현 단계로 넘어갈 수 있다. 추가 적재는 지금 필수는 아니다. 목록형 evidence는 `ITEM_RESOLVES_TO`를 적극 활용해야 하며, Rule 중심 경로와 ListItem 중심 경로를 분리해 evidence pack을 구성하는 것이 안전하다.
