# AnswerGenerator Implementation Note

## Purpose

`answer_generator.py` implements deterministic template answer generation from:

1. `EvidencePackAssembler`
2. `CitationFormatter`
3. `ClaimChecker`

It is the final step before a future FastAPI `/ask` adapter. This implementation does not call an LLM.

## Safety Rules

- default `use_llm = False`
- smoke test uses `use_llm = False`
- no Neo4j write
- no CSV modification
- no loader modification
- no frontend modification
- no external model call
- no law name, article number, education hour, penalty, or obligation is invented

## Class

`AnswerGenerator`

Implemented methods:

- `generate(evidence_pack, citations, claim_check)`
- `generate_template_answer(evidence_pack, citations, claim_check)`
- `generate_llm_answer(evidence_pack, citations, claim_check)`
- `build_prompt(evidence_pack, citations, claim_check)`
- `enforce_policy(draft_answer, evidence_pack, claim_check)`

`generate_llm_answer()` is intentionally disabled and returns a non-LLM response. It exists only as a future extension point.

## answer_policy Behavior

- `ALLOW_DIRECT_ANSWER`: produces a template answer based on available evidence and citations.
- `ALLOW_WITH_CAUTION`: produces a template answer with caution notes.
- `INDIRECT_ONLY_RESPONSE`: forbids a direct yes/no legal conclusion and inserts the direct-evidence-missing guardrail sentence.
- `REFUSE_OR_REQUEST_MORE_EVIDENCE`: produces an insufficient-evidence response.

## Template Structure

The generated answer is structured as:

1. `[결론]`
2. `[근거]`
3. `[주의]`, when needed
4. `[근거 조항]`

Evidence previews are limited and citations are capped to a small number so the template does not dump raw graph data.

## INDIRECT_ONLY Guardrail

The risk-assessment notice query must remain restricted:

`answer_policy = INDIRECT_ONLY_RESPONSE`

The generated answer includes:

`현재 KB에서는 해당 의무를 직접 뒷받침하는 조문 근거는 확인되지 않았고, 간접 근거만 확인됩니다.`

## Smoke Test

Command:

```powershell
python -B 05_code\graph_rag_pipeline\smoke_test_answer_generator.py --root-dir .
```

Expected:

- all 6 smoke queries produce an answer
- citations are present
- LLM is not used
- risk-assessment notice query remains `INDIRECT_ONLY_RESPONSE`

Output:

- `graph_rag_knowledgement/neo4j_load/evidence_traversal/answer_generator_smoke_test_report.txt`
- `graph_rag_knowledgement/neo4j_load/evidence_traversal/answer_generator_smoke_test_samples.json`

## Next Step

Implement a FastAPI `/ask` adapter that keeps the existing frontend request/response compatibility while returning the richer Graph-RAG fields.
