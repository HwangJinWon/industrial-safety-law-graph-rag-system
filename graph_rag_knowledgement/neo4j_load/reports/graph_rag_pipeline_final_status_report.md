# Graph-RAG Pipeline Final Status Report

## 1. Project Purpose

This project builds a Graph-RAG system for Korean occupational safety law materials, including the Occupational Safety and Health Act family and Serious Accident Punishment Act related sources.

The current pipeline connects a loaded Neo4j `graph.v1` knowledge graph to read-only graph retrieval, structured evidence assembly, citation formatting, claim-readiness checking, deterministic template answer generation, and a frontend-compatible `/ask` response adapter.

## 2. Neo4j Load State

- target database: `graph.v1`
- core load status: `LOAD_PASS_WITH_WARNINGS`
- source hierarchy loaded
- `ListItem -> ITEM_RESOLVES_TO -> source anchor` loaded
- Rule count: 8,858
- SourceNode count: 8,858
- `EXTRACTED_FROM`: 8,858
- `RESOLVES_TO`: 8,858
- `ITEM_RESOLVES_TO`: 3,604
- Rule source_text missing: 0
- rules without source: 0
- unresolved SourceNode: 0

## 3. GraphQueryLayer State

- implemented: `05_code/graph_rag_pipeline/graph_query_layer.py`
- smoke test: PASS
- mode: read-only Neo4j query wrapper
- write queries are blocked by guard logic

## 4. EvidencePackAssembler State

- implemented: `05_code/graph_rag_pipeline/evidence_pack_assembler.py`
- smoke test: PASS
- produces structured evidence packs with:
  - primary_evidence
  - supporting_evidence
  - citation_candidates
  - warnings
  - missing_evidence
  - evidence_readiness

## 5. CitationFormatter State

- implemented: `05_code/graph_rag_pipeline/citation_formatter.py`
- smoke test: PASS
- outputs:
  - Graph-RAG `citations[]`
  - frontend `evidence_chips[]`
  - legacy frontend `evidences[]`

## 6. ClaimChecker State

- implemented: `05_code/graph_rag_pipeline/claim_check.py`
- smoke test: PASS
- outputs:
  - claim_check_status
  - answer_policy
  - issues
  - badges
  - summary

## 7. AnswerGenerator State

- implemented: `05_code/graph_rag_pipeline/answer_generator.py`
- smoke test: PASS
- current mode: deterministic template answer only
- `use_llm` default: false
- no LLM call was made
- `INDIRECT_ONLY_RESPONSE` policy is enforced

## 8. FastAPI /ask State

- implemented adapter: `05_code/graph_rag_pipeline/ask_adapter.py`
- direct smoke test: PASS
- no previous FastAPI `/ask` implementation was found in the searched Python files
- adapter accepts:
  - query
  - question
  - message
  - mode
  - intent
  - chat_history
  - options
- adapter returns:
  - answer
  - intent
  - status
  - evidence_readiness
  - answer_policy
  - claim_check
  - citations
  - evidence_chips
  - legacy evidences
  - warnings
  - missing_evidence
  - evidence_pack summary or full debug pack
  - debug

## 9. Frontend Connection State

- frontend path: `05_code/frontend reference`
- modified files:
  - `src/App.jsx`
  - `src/index.css`
- existing request shape remains compatible:
  - `question`
  - `mode = qa`
  - `chat_history`
- existing response display remains compatible:
  - `answer`
  - `evidences[0].law_name`
  - `evidences[0].title`
  - `evidences[0].node_id`
- added display support:
  - readiness badges
  - answer_policy badges
  - claim_check badges
  - warnings
  - missing evidence
  - evidence chips
- build status: PASS_WITH_WARNINGS because `node_modules` is absent and `vite` is unavailable; dependency installation was intentionally not run.

## 10. Supported Question Types

Current smoke-tested intents:

- appointment_requirement
- education_time_lookup
- inspection_requirement
- obligation_check
- penalty_lookup
- applicability_check

## 11. INDIRECT_ONLY Handling

The query `위험성평가 결과를 근로자에게 알려야 하나?` remains protected:

- source coverage audit found no direct evidence
- evidence_readiness: `INDIRECT_ONLY`
- claim_check_status: `RESTRICTED`
- answer_policy: `INDIRECT_ONLY_RESPONSE`
- template answer explicitly states that direct statutory evidence was not found and only indirect evidence is available

## 12. Remaining Warnings

- Some graph quality signals remain, including UNKNOWN and needs_review records.
- Several smoke queries return `ALLOW_WITH_CAUTION`, which is expected.
- Frontend build was not run successfully because dependencies are not installed.
- `/law/{nodeId}` source detail compatibility endpoint has not been fully wired to the new adapter.
- LLM answer generation is intentionally not implemented.

## 13. Limitations

- Template answers are not final production legal prose.
- FastAPI server runtime launch was not tested.
- Frontend visual behavior was not browser-verified because build dependencies were unavailable.
- No full retrieval evaluation was rerun.
- PhysicalTable/PhysicalRow/PhysicalCell remain out of the current graph serving path.

## 14. Research / Paper Notes

Useful discussion points:

- staged construction of Document Graph, Reasoning Graph, and source anchors
- evidence_readiness as an answer-generation guardrail
- handling of indirect evidence and source coverage limitations
- dual response schema for frontend compatibility and Graph-RAG transparency
- list evidence improvement through `ITEM_RESOLVES_TO`

## 15. Final Conclusion

The Graph-RAG pipeline is now connected through a read-only evidence path:

Neo4j graph.v1 -> GraphQueryLayer -> EvidencePackAssembler -> CitationFormatter -> ClaimChecker -> AnswerGenerator -> /ask adapter -> frontend-compatible response.

Current final state:

- backend direct smoke tests: PASS
- E2E `/ask` schema smoke test: PASS
- frontend update: PASS_WITH_WARNINGS
- LLM used: false
- Neo4j write during pipeline build: none
- password value logged: no
