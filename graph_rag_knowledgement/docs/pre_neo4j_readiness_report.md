# Pre-Neo4j Readiness Report

## 1. Report Purpose

This document summarizes the readiness status of the industrial safety legal Graph-RAG knowledge base before the first Neo4j load.

The purpose of this report is to clarify whether the current CSV-based knowledge base is structurally ready for Neo4j loading, and to separate the following issues:

1. Load-blocking structural issues
2. Non-blocking graph quality warnings
3. Retrieval evaluation issues
4. Source-based query generation issues
5. Evidence-pack design issues
6. Tasks that must be handled before Neo4j loading
7. Tasks that can be handled after Neo4j loading

This report reflects the current state after the refined evaluation set was created and after the conservative pre-Neo4j warning fix was applied.

Important distinction:

```text
Neo4j load readiness ≠ final answer generation readiness
```

The current graph is structurally ready for a first Neo4j load with warnings. However, final Graph-RAG answer generation still requires evidence-pack design, source traversal, citation formatting, and claim checking.

---

## 2. Current Project State

The project has completed the first major preprocessing phase.

Completed components:

```text
1. Legal body Document Graph construction
2. Annex/appendix/source table graph construction
3. Physical row/cell and logical row/cell separation
4. Reasoning Graph node generation
5. Rule / Requirement / Threshold / Exception / TemporalRule / EntityType / ListItem separation
6. Rule-source and Rule-child edge generation
7. Rule-to-rule reasoning edge generation
8. UNKNOWN / missing extraction / list item / exception audits
9. Conservative pre-Neo4j warning fix
10. Curated retrieval evaluation
11. Source-based stress test
12. Refined evaluation set construction
13. Answerable audit
14. Pre-Neo4j graph readiness audit
15. Neo4j schema draft preparation
```

Not yet completed:

```text
1. Neo4j loader implementation
2. Neo4j database load
3. Graph retrieval API implementation
4. Evidence Pack Builder implementation
5. LLM answer generation pipeline
6. Claim check module
7. Citation formatter
8. End-to-end answer evaluation
```

Therefore, the current project status should be described as:

```text
Preprocessing completed and first Neo4j load ready with warnings.
```

It should not be described as:

```text
Completed legal QA system.
Production-ready legal compliance system.
Final answer accuracy validated system.
```

---

## 3. Knowledge Base Layers

The current knowledge base consists of three major graph layers.

## 3.1 Document Graph

Document Graph preserves the original legal body structure.

Main structure:

```text
Law
→ Heading
→ Article
→ Paragraph
→ Item
→ Subitem
→ Addendum
```

Purpose:

```text
- Preserve legal hierarchy
- Preserve source_node_id and source_text
- Provide article-level citation
- Provide parent context for item/subitem-based reasoning
- Provide source evidence for Reasoning Graph nodes
```

## 3.2 Annex Source Graph

Annex Source Graph preserves annexes, tables, forms, notes, and list-like legal evidence.

Main structure:

```text
Annex
→ AnnexSection
→ PhysicalTable
→ PhysicalRow
→ PhysicalCell
→ LogicalRow
→ LogicalCell
→ AnnexNote
```

Purpose:

```text
- Preserve annex source traceability
- Separate physical table structure from logical reasoning rows/cells
- Support list-based questions
- Support education, inspection, health examination, qualification, document/form evidence
```

## 3.3 Reasoning Graph

Reasoning Graph contains meaning-level legal reasoning nodes.

Main node types:

```text
Rule
Requirement
Threshold
Exception
TemporalRule
EntityType
ListItem
```

Purpose:

```text
- Support Graph-RAG retrieval
- Separate legal obligations, thresholds, exceptions, temporal conditions, entities, and list items
- Connect rules to original source nodes
- Provide structured evidence for answer generation
```

---

## 4. Curated 100 Retrieval Evaluation

A curated evaluation set of 100 representative legal questions was used to validate the initial retrieval pipeline.

Final curated 100 result:

```text
Top-1 hit: 89/100
Top-3 hit: 97/100
Top-5 hit: 100/100
queries_without_matches: 0
failed_query_ids: none
```

Interpretation:

```text
- Retrieval is stable on manually designed representative questions.
- The graph can retrieve relevant candidates for major legal question types.
- This result should be interpreted as retrieval hit performance, not final answer accuracy.
```

Important caution:

```text
Top-5 100/100 does not mean answer accuracy is 100%.
It only means expected retrieval candidates were found within Top-5 under the curated evaluation criteria.
```

---

## 5. Source-Based Extended Stress Test

To test broader legal source coverage, 300 source-based query candidates were generated from the original legal source and reasoning graph.

Candidate generation summary:

```text
Total generated candidates: 300
Included in extended stress test: 287
Excluded before extended test: 13
Extended test total: 387
= curated 100 + source-based 287
```

Initial extended stress test result:

```text
Total queries: 387
Top-1: 265/387
Top-3: 282/387
Top-5: 290/387
queries_without_matches: 0
Top-5 failed query count: 97
possible_overmatch_count: 805
```

Interpretation:

```text
- The source-based stress test was much broader and noisier than the curated 100 set.
- Lower performance was not solely a retrieval ranking problem.
- Failure audit showed many cases caused by query generation issues, strict expected metadata, source-query mismatch, and broad/ambiguous generated questions.
```

Major failure causes identified:

```text
SOURCE_EXISTS_BUT_RANK_LOW
EXPECTED_TOO_STRICT
SOURCE_QUERY_MISMATCH
QUERY_AMBIGUOUS
ARTICLE_MISMATCH
APPLICABILITY_ASPECT_MIXED
INSPECTION_LIST_MISMATCH
BROAD_SAFETY_OVERMATCH
SUBTYPE_COMPATIBILITY_MISSING
```

Conclusion:

```text
The raw 387 source-based stress test should be treated as both a retrieval stress test and a generated-query quality audit, not as a final evaluation set.
```

---

## 6. Source-Based Query Quality Audit and Refined Evaluation Set

The source-based generated questions were audited to remove unsuitable evaluation cases.

Quality audit result:

```text
KEEP: 217
KEEP_BUT_REVIEW: 0
FIX_EXPECTED_METADATA: 17
FIX_QUERY_TEXT: 53
EXCLUDE_FROM_EVAL: 13
```

Refined evaluation set:

```text
Curated queries: 100
Retained source-based queries: 209
Excluded source-based queries: 78
Total refined queries: 309
```

The excluded queries were not treated as retrieval failures. They were removed because they had issues such as:

```text
- expected metadata uncertainty
- source-query mismatch
- unnatural generated query text
- overly broad query scope
- weak or missing expected keywords
- insufficient source context
```

This refined set is currently the most appropriate retrieval evaluation set for the pre-Neo4j stage.

---

## 7. Refined 309 Retrieval Evaluation

Refined evaluation result before conservative warning fix:

```text
Top-1: 265/309
Top-3: 282/309
Top-5: 290/309
queries_without_matches: 0
possible_overmatch_count: 428
```

Failed Top-5 query count:

```text
19
```

Failed query IDs:

```text
Q219,Q223,Q258,Q259,Q263,Q264,Q265,Q266,Q267,Q268,
Q276,Q277,Q281,Q292,Q294,Q295,Q297,Q299,Q306
```

Interpretation:

```text
- After removing low-quality generated queries, retrieval performance recovered significantly.
- Top-3 exceeded 91%.
- Top-5 reached approximately 93.85%.
- Remaining failures are concentrated in inspection/list, safety measure, and education-related cases.
```

Intent-level weak points:

```text
inspection_requirement
safety_measure_lookup
education_time_lookup
```

These weak points suggest that future improvement should focus on evidence-pack design and annex/list traversal rather than only ranking weights.

---

## 8. Conservative Pre-Neo4j Warning Fix

A conservative warning fix was performed before Neo4j loading.

The goal was not to remove all warnings. The goal was to safely add high-confidence Requirement and Threshold evidence without degrading retrieval.

Applied patch:

```text
Requirement nodes: +5
Rule-Requirement edges: +5
Threshold nodes: +150
Rule-Threshold edges: +150
```

Not applied:

```text
UNKNOWN subtype update
```

Reason:

```text
UNKNOWN subtype update was previewed and tested, but it was rolled back because of possible retrieval regression.
```

Backup location:

```text
06_archive/pre_neo4j_warning_fix_backup
```

The final graph CSV state includes the Requirement and Threshold additions, but does not include the UNKNOWN subtype update.

---

## 9. Refined Retrieval After Warning Fix

After the conservative warning fix, refined evaluation was rerun.

Before/after comparison:

```text
Top-1: 265/309 → 266/309
Top-3: 282/309 → 282/309
Top-5: 290/309 → 290/309
queries_without_matches: 0 → 0
possible_overmatch_count: 428 → 427
```

Interpretation:

```text
- The warning fix did not degrade Top-3 or Top-5 retrieval performance.
- Top-1 improved by one query.
- possible_overmatch_count decreased slightly.
- The patch was safe from a retrieval performance perspective.
```

This confirms that the conservative patch strategy was appropriate.

---

## 10. Answerable Audit

Retrieval hit and answerability are different.

Retrieval hit checks whether expected metadata appears within Top-k results. Answerable audit estimates whether the retrieved evidence can support a usable answer.

Answerable audit before warning fix:

```text
Top-1 answerable: 221/309
Top-3 answerable: 252/309
Top-5 answerable: 268/309
Top-10 answerable: 276/309
dangerous_wrong_answer_risk: 19
```

Answerable audit after warning fix:

```text
Top-1 answerable: 222/309
Top-3 answerable: 256/309
Top-5 answerable: 272/309
Top-10 answerable: 280/309
dangerous_wrong_answer_risk: 20
```

Interpretation:

```text
- Requirement and Threshold additions improved answerability estimates.
- Top-5 answerable improved from 268 to 272.
- Top-10 answerable improved from 276 to 280.
- dangerous_wrong_answer_risk increased from 19 to 20, but this should be treated as one additional review signal, not as proof of major regression.
```

Important caution:

```text
Answerable audit is an automatic estimate.
It is not final answer accuracy.
```

Implication:

```text
The next stage must implement an Evidence Pack Builder.
Raw Top-k retrieval results should not be passed directly to the answer generator.
```

---

## 11. Graph CSV Readiness After Warning Fix

The final after-warning-fix graph readiness audit reports:

```text
Readiness: READY_WITH_WARNINGS
Blocking issue: none
```

Key node counts:

```text
nodes_rule.csv: 8,858
nodes_requirement.csv: 3,639
nodes_threshold.csv: 1,782
nodes_exception.csv: 647
nodes_temporal_rule.csv: 227
nodes_entity_type.csv: 586
nodes_list_item.csv: 3,604
```

Key edge counts:

```text
edges_rule_source.csv: 8,858
edges_rule_requirement.csv: 3,639
edges_rule_threshold.csv: 1,782
edges_rule_exception.csv: 647
edges_rule_temporal.csv: 227
edges_rule_entity.csv: 7,550
edges_rule_list_item.csv: 3,604
edges_rule_reasoning.csv: 5,893
```

Structural checks:

```text
orphan edge count: 0
duplicate id count: 0
missing rule source_text count: 0
high-degree rule count: 0
```

This means that no blocking structural problem was found for the first Neo4j load.

---

## 12. Remaining Warnings

The graph remains READY_WITH_WARNINGS because several non-blocking warnings remain.

After warning fix:

```text
OBLIGATION without Requirement: 607
threshold-related without Threshold node: 1210
UNKNOWN rule type/subtype: 1995
needs_review or low confidence: 1026
```

These warnings should be interpreted carefully.

## 12.1 OBLIGATION without Requirement

Not every OBLIGATION must have a separate Requirement node. Some rules already carry requirement_text or require parent/list context.

Recommended handling:

```text
- Load as-is.
- Use Requirement node when available.
- Fall back to Rule.requirement_text or Rule.source_text when Requirement is missing.
- Prioritize manual review only when affected by failed retrieval or answerable risk.
```

## 12.2 Threshold-related without Threshold

Many numeric-looking texts are not legal thresholds. Some are article numbers, annex numbers, form numbers, or structural references.

Recommended handling:

```text
- Do not auto-create thresholds for all numeric expressions.
- Use existing Threshold nodes where available.
- Fall back to source_text for ambiguous threshold-like questions.
- Prioritize real user query failures.
```

## 12.3 UNKNOWN rule type/subtype

UNKNOWN is not automatically an error.

It may indicate:

```text
- ambiguous legal fragment
- table/list fragment
- source context required
- reference-only clause
- extraction confidence too low
```

Recommended handling:

```text
- Load UNKNOWN nodes.
- Preserve confidence and needs_review.
- Avoid forcing them into arbitrary classes before loading.
```

## 12.4 needs_review / low confidence

needs_review is a quality signal, not a blocker.

Recommended handling:

```text
- Load needs_review nodes.
- Use them conservatively in answer generation.
- Expose or internally track review status.
```

---

## 13. Neo4j Load Readiness Decision

Final readiness decision:

```text
READY_WITH_WARNINGS
```

Load blockers:

```text
none
```

The graph is structurally ready for the first Neo4j load.

However, the first load should follow a balanced strategy:

```text
Load:
- Reasoning Graph
- SourceNode placeholder
- major source anchor nodes
  - Article
  - Paragraph
  - Item
  - Subitem
  - Addendum
  - Annex
  - LogicalRow
  - LogicalCell
  - AnnexNote

Defer:
- PhysicalTable
- PhysicalRow
- PhysicalCell
- full physical source reconstruction
```

This strategy is recommended because answer generation requires citation and source context, but full physical table reconstruction is not necessary for the first Graph-RAG pipeline test.

---

## 14. Why Not Load Everything at Once?

It is technically possible to load the entire Document Graph, Annex Source Graph, and Reasoning Graph at once.

However, a staged first-load strategy is safer because:

```text
1. Reasoning Graph is the core retrieval target.
2. Source anchors are enough for initial citation and evidence expansion.
3. Physical table structures increase loader complexity.
4. Debugging source-node resolution is easier in stages.
5. First priority is to validate Rule → Evidence Pack → Answer generation flow.
6. Full source reconstruction can be added after the reasoning/evidence path works.
```

Recommended practical strategy:

```text
Phase 1:
Reasoning Graph + SourceNode + Article/Paragraph/Item/Subitem + Annex/LogicalRow/LogicalCell/AnnexNote

Phase 2:
PhysicalTable/PhysicalRow/PhysicalCell + full annex/source browsing

Phase 3:
Graph retrieval API + Evidence Pack Builder + answer generation
```

---

## 15. Evidence Pack Requirements Before Answer Generation

Neo4j loading alone is not enough. Before answer generation, the system must implement intent-specific evidence pack rules.

Examples:

## 15.1 education_time_lookup

Required evidence:

```text
Rule
Threshold
Requirement or education rule text
SourceText
Annex/LogicalRow if table-based
```

## 15.2 inspection_requirement

Required evidence:

```text
Rule
ListItem
Annex
LogicalRow
LogicalCell
SourceText
```

## 15.3 applicability_check

Required evidence:

```text
Rule
Exception
SCOPE_EXCLUSION if relevant
Threshold if condition-based
TemporalRule if date-based
EntityType if target-based
SourceText
```

## 15.4 safety_measure_lookup

Required evidence:

```text
Rule
Requirement
hazard/work/equipment/action context
SourceText
Article/Item/Subitem context
```

## 15.5 penalty_lookup

Required evidence:

```text
Penalty Rule
Related obligation/prohibition Rule
SourceText
Article context
```

The answer generator should receive evidence packs, not raw Top-k rows.

---

## 16. Tasks Required Before Neo4j Loader Implementation

Before implementing the loader, the following decisions should be made.

```text
1. Confirm SourceNode placeholder strategy.
2. Confirm whether Article/Paragraph/Item/Subitem are included in first load.
3. Confirm Annex/LogicalRow/LogicalCell/AnnexNote first-load scope.
4. Confirm PhysicalRow/PhysicalCell deferral.
5. Confirm relationship type mapping for edges_rule_reasoning.csv.
6. Confirm how unresolved SourceNode should be handled.
7. Confirm whether UNKNOWN and needs_review nodes are loaded with flags.
```

Recommended decisions:

```text
- Use SourceNode placeholder.
- Include major source anchors in first load.
- Defer physical table structures.
- Load UNKNOWN and needs_review nodes.
- Preserve confidence and needs_review as properties.
- Do not manually edit Neo4j data; patch CSV and reload when data errors are found.
```

---

## 17. Recommended Next Sequence

Recommended sequence after this report:

```text
1. Finalize first-load schema.
2. Implement Neo4j loader with dry-run validation.
3. Load constraints and indexes.
4. Load reasoning nodes.
5. Load SourceNode placeholders.
6. Load major source anchor nodes.
7. Load reasoning edges.
8. Load source resolution edges.
9. Run post-load validation queries.
10. Implement graph retrieval functions.
11. Implement Evidence Pack Builder.
12. Connect /ask pipeline.
13. Implement answer generator with evidence-only prompt.
14. Implement claim check and citation formatter.
15. Run end-to-end answer evaluation.
```

---

## 18. Statements Suitable for Team or Paper Writing

Possible accurate statements:

```text
- We constructed a source-grounded legal reasoning graph from Korean occupational safety and serious accident punishment laws.
- The graph separates legal rules, requirements, thresholds, exceptions, temporal conditions, entities, and list items.
- All reasoning nodes preserve source traceability through source_node_id and source_text.
- We evaluated retrieval using both curated representative queries and source-based refined queries.
- The final refined pre-load evaluation achieved Top-3 282/309 and Top-5 290/309.
- A pre-Neo4j readiness audit found no orphan edges, duplicate IDs, or missing rule source_text.
```

Statements to avoid:

```text
- The legal QA system is complete.
- The system achieved 100% answer accuracy.
- The graph is production-ready.
- All legal questions can be answered.
- Retrieval hit equals answer accuracy.
```

---

## 19. Final Conclusion

The current CSV-based knowledge base is structurally ready for the first Neo4j load.

Final state:

```text
Preprocessing: completed for first-load purpose
Readiness: READY_WITH_WARNINGS
Blocking issues: none
Retrieval refined Top-5: 290/309
After-warning-fix answerable Top-5 estimate: 272/309
```

The remaining warnings should not block the first load. They should be treated as quality signals for evidence-pack design, manual review prioritization, and future graph refinement.

The next major development step is to implement a staged Neo4j loader using a balanced first-load strategy:

```text
Reasoning Graph
+ SourceNode
+ major source anchors
```

followed by graph retrieval and evidence pack construction.
