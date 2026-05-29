# Citation and Claim Check Implementation Note

## 1. Purpose

This note documents the implementation of `citation_formatter.py` and `claim_check.py` before answer generation.

The modules prepare structured Graph-RAG evidence for a future answer generator. They do not generate natural-language answers, call an LLM, write to Neo4j, modify CSV files, edit the loader, or modify frontend code.

## 2. CitationFormatter

`CitationFormatter` converts an Evidence Pack into three frontend/backend-ready structures:

1. `citations[]` for Graph-RAG legal citation display
2. `evidence_chips[]` for frontend evidence chips
3. `evidences[]` legacy alias for the current frontend

Implemented methods:

- `format_pack_citations(evidence_pack)`
- `format_evidence_citation(evidence_item)`
- `build_citation_text(...)`
- `deduplicate_citations(citations)`
- `make_source_preview(text, max_len=300)`
- `build_evidence_chips(evidence_pack, citations=None)`
- `build_legacy_evidences(evidence_pack, citations=None)`

## 3. citations[] Structure

Each citation uses this structure:

```json
{
  "citation_text": "...",
  "law_name": "...",
  "article_no": "...",
  "paragraph_no": "...",
  "item_no": "...",
  "subitem_no": "...",
  "annex_title": "...",
  "source_anchor_label": "...",
  "source_anchor_id": "...",
  "source_node_id": "...",
  "rule_id": "...",
  "list_item_id": "...",
  "source_text_preview": "...",
  "evidence_kind": "rule | list_item | source | threshold | exception | unknown",
  "confidence": "high | medium | low"
}
```

Citation text is built only from fields present in the evidence. The formatter does not invent missing law names, article numbers, paragraph numbers, or annex titles.

## 4. evidence_chips[] Structure

`build_evidence_chips()` creates frontend-oriented chip records:

```json
{
  "id": "...",
  "label": "...",
  "type": "rule | list_item | source | threshold | exception | annex | article | unknown",
  "law_name": "...",
  "article_no": "...",
  "annex_title": "...",
  "source_node_id": "...",
  "source_anchor_id": "...",
  "source_anchor_label": "...",
  "rule_id": "...",
  "list_item_id": "...",
  "preview": "...",
  "severity": "normal | warning | indirect",
  "clickable": true
}
```

Severity behavior:

- `INDIRECT_ONLY` evidence packs produce `severity = "indirect"`
- Evidence with a matching warning `related_id` produces `severity = "warning"`
- Otherwise `severity = "normal"`

## 5. Legacy evidences[] Compatibility

The current frontend reads:

- `evidences[0].law_name`
- `evidences[0].title`
- `evidences[0].node_id`

`build_legacy_evidences()` converts Graph-RAG citations into the current frontend-compatible alias:

```json
{
  "law_name": "...",
  "title": "...",
  "node_id": "...",
  "source_text": "...",
  "score": null,
  "type": "rule | list_item | source | unknown"
}
```

`node_id` priority:

1. `source_node_id`
2. `source_anchor_id`
3. `rule_id`
4. `list_item_id`

This allows the existing frontend to keep rendering at least the first evidence reference while the richer Graph-RAG UI is added later.

## 6. ClaimChecker

`ClaimChecker` decides whether an Evidence Pack is ready for a later answer generator.

Implemented methods:

- `check_pack(evidence_pack, citations=None)`
- `check_intent_requirements(evidence_pack)`
- `check_directness(evidence_pack)`
- `check_citations(evidence_pack, citations=None)`
- `determine_answer_policy(evidence_pack, issues)`
- `summarize_check(evidence_pack, issues, citations=None)`
- `build_badges(claim_check_result)`

The checker returns:

```json
{
  "query": "...",
  "intent": "...",
  "pack_status": "...",
  "evidence_readiness": "...",
  "claim_check_status": "PASS | PASS_WITH_WARNINGS | RESTRICTED | FAIL",
  "answer_policy": "ALLOW_DIRECT_ANSWER | ALLOW_WITH_CAUTION | INDIRECT_ONLY_RESPONSE | REFUSE_OR_REQUEST_MORE_EVIDENCE",
  "issues": [],
  "badges": [],
  "summary": {
    "primary_evidence_count": 0,
    "citation_count": 0,
    "warning_count": 0,
    "missing_evidence_count": 0,
    "high_severity_issue_count": 0
  }
}
```

## 7. answer_policy Definition

- `ALLOW_DIRECT_ANSWER`: direct answer generation is allowed because evidence and citations are sufficient.
- `ALLOW_WITH_CAUTION`: answer generation can proceed, but warnings should be shown.
- `INDIRECT_ONLY_RESPONSE`: direct evidence is missing; answer wording must be limited to indirect-evidence status.
- `REFUSE_OR_REQUEST_MORE_EVIDENCE`: evidence is too weak or missing for answer generation.

## 8. Intent-Level Checks

The checker applies conservative intent-level requirements:

- `appointment_requirement`: Rule evidence, requirement/source evidence, role or entity context, citation
- `education_time_lookup`: threshold or time expression, education context, citation
- `inspection_requirement` / `list_lookup`: ListItem evidence, ITEM_RESOLVES_TO source anchor, item text, citation or annex context
- `obligation_check`: Rule evidence, requirement/source evidence, direct obligation source, citation
- `penalty_lookup`: penalty Rule or penalty text, citation, and preferably related violation Rule
- `applicability_check`: exception/scope/threshold/temporal/entity evidence plus citation
- `definition_lookup`: Definition Rule/source evidence plus citation

## 9. INDIRECT_ONLY Guardrail

For the risk-assessment notice query, the Evidence Pack Assembler emits:

- `evidence_readiness = INDIRECT_ONLY`
- warning `DIRECT_EVIDENCE_NOT_FOUND`
- missing evidence `DIRECT_OBLIGATION_SOURCE`

`ClaimChecker` maps this to:

- `claim_check_status = RESTRICTED`
- `answer_policy = INDIRECT_ONLY_RESPONSE`

This prevents a later answer generator from making a direct affirmative or negative legal claim when only indirect source coverage is available.

## 10. Smoke Test Result

Smoke test command:

```powershell
python -B 05_code\graph_rag_pipeline\smoke_test_citation_and_claim_check.py --root-dir .
```

Result:

- final_status: PASS
- Neo4j write executed: false
- LLM used: false
- natural-language answer generated: false

Summary by query:

| intent | formatted citations | evidence chips | legacy evidences | claim_check_status | answer_policy |
|---|---:|---:|---:|---|---|
| appointment_requirement | 15 | 15 | 10 | PASS | ALLOW_DIRECT_ANSWER |
| education_time_lookup | 22 | 22 | 16 | PASS_WITH_WARNINGS | ALLOW_WITH_CAUTION |
| inspection_requirement | 18 | 18 | 8 | PASS_WITH_WARNINGS | ALLOW_WITH_CAUTION |
| obligation_check | 12 | 10 | 7 | RESTRICTED | INDIRECT_ONLY_RESPONSE |
| penalty_lookup | 9 | 9 | 7 | PASS_WITH_WARNINGS | ALLOW_WITH_CAUTION |
| applicability_check | 15 | 15 | 10 | PASS | ALLOW_DIRECT_ANSWER |

Output files:

- `graph_rag_knowledgement/neo4j_load/evidence_traversal/citation_claim_check_smoke_test_report.txt`
- `graph_rag_knowledgement/neo4j_load/evidence_traversal/citation_claim_check_smoke_test_samples.json`

## 11. Not Implemented

- Natural-language answer generation
- LLM calls
- FastAPI integration
- UI integration
- Post-hoc claim checking of generated prose
- Advanced Korean legal citation grammar

## 12. Next Step

The next module can be `answer_generator.py`. It should consume `answer_policy` and must restrict direct answers when the policy is `INDIRECT_ONLY_RESPONSE` or `REFUSE_OR_REQUEST_MORE_EVIDENCE`.
