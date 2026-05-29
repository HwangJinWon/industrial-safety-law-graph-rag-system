# Graph Query Layer Design Note

## Purpose

`graph_query_layer.py` is the first implementation step toward the Evidence Pack Assembler. It provides read-only Cypher wrappers for Neo4j `graph.v1` and returns JSON-serializable Python `dict`/`list` results.

This layer does not:

- generate answers
- call an LLM
- connect FastAPI
- modify Neo4j data
- rerun retrieval evaluation

## Read-Only Principle

All queries pass through `run_read_query()`, which blocks Cypher containing write-oriented keywords:

- `CREATE`
- `MERGE`
- `SET`
- `DELETE`
- `DETACH`
- `REMOVE`
- `DROP`
- `CALL db.create`
- `CALL apoc.create`
- `CALL apoc.merge`
- `LOAD CSV`

The target database must be `.env` `NEO4J_DATABASE=graph.v1`. The password is used only for connection and is not logged.

## Implemented Methods

- `get_graph_counts()`
- `get_rule_evidence_pack_by_rule_id(rule_id)`
- `search_rules_by_keyword(keyword, limit)`
- `search_rules_by_intent_keywords(query, intent, limit)`
- `get_requirement_evidence(limit)`
- `get_threshold_evidence(limit)`
- `get_exception_evidence(limit)`
- `get_penalty_evidence(limit)`
- `get_listitem_evidence(keyword, limit)`
- `get_education_time_evidence(limit)`
- `get_inspection_list_evidence(limit)`
- `get_source_context_for_rule(rule_id)`
- `get_annex_context_for_listitem(list_item_id)`

## Intent Coverage

Current beta support:

- `obligation_check`: Rule/Requirement/Entity/Source paths
- `safety_measure_lookup`: keyword Rule search plus requirement/threshold evidence
- `education_time_lookup`: Rule + Threshold path, education keywords
- `education_content_lookup`: delegated to ListItem evidence path
- `appointment_requirement`: keyword Rule search
- `document_requirement`: keyword Rule search
- `penalty_lookup`: Penalty Rule + RELATED_RULE path
- `applicability_check`: keyword Rule search with exception/scope bias
- `definition_lookup`: definition subtype bias
- `inspection_requirement` / `list_lookup`: ListItem path

## ListItem Handling

ListItem evidence uses `ITEM_RESOLVES_TO` as the primary path:

```text
ListItem -> ITEM_RESOLVES_TO -> Paragraph / Item / Subitem / LogicalRow / LogicalCell / AnnexNote
```

This is important because direct `Rule -> HAS_LIST_ITEM` coverage is only 31 relationships, while `ITEM_RESOLVES_TO` covers all 3604 ListItem nodes.

## Current Scope

The layer is intentionally small and conservative:

- CONTAINS-based keyword search only
- simple Python-side scoring
- no full-text index usage yet
- no answer generation
- no citation formatter implementation
- no claim checking implementation

## Next Step

The next module should be `evidence_pack_assembler.py`, built on top of this query layer. It should combine Rule-centered, SourceNode-centered, Annex-centered, and ListItem-centered evidence into a single normalized evidence pack before any LLM answer generation is introduced.
