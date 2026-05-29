# Pre-Neo4j Warning Fix Report

## 1. Report Purpose

This document summarizes the conservative warning audit and fix performed before the first Neo4j load.

The purpose of this task was not to make every warning disappear. The purpose was to safely improve graph evidence quality before loading the CSV-based knowledge base into Neo4j.

The warning fix focused on the following principle:

```text
Fix only high-confidence, source-grounded, structurally safe issues.
Leave ambiguous cases as review items.
Do not force classification for uncertain legal fragments.
Do not modify retrieval ranking/scoring logic.
Do not create a Neo4j loader or run Neo4j loading in this step.
```

The final result remains:

```text
READY_WITH_WARNINGS
```

However, no structural blocking issue was found.

This report should be read together with:

```text
pre_neo4j_readiness_report.md
pre_neo4j_graph_readiness_summary_after_warning_fix.txt
pre_neo4j_warning_fix_comparison.txt
```

---

## 2. Scope of This Task

## 2.1 What was done

The following tasks were performed:

```text
1. Audited pre-Neo4j graph warnings.
2. Generated detailed review CSV files.
3. Identified high-confidence Requirement patch candidates.
4. Identified high-confidence Threshold patch candidates.
5. Created patch preview.
6. Applied only safe Requirement/Threshold patches.
7. Backed up original CSV files before modification.
8. Reran graph readiness audit.
9. Reran refined retrieval evaluation.
10. Reran answerable audit.
11. Compared before/after results.
```

## 2.2 What was not done

The following tasks were intentionally not performed:

```text
1. Neo4j loader was not created.
2. Neo4j load was not executed.
3. Retrieval ranking/scoring logic was not modified.
4. Query-specific hardcoding was not added.
5. Original law/annex JSON files were not modified.
6. Low-confidence UNKNOWN rules were not forced into specific classes.
7. ListItem candidates were not automatically moved.
8. Exception/list item files were not automatically rewritten.
9. All warnings were not forced to zero.
```

This conservative scope was intentional. The project prioritizes traceability and reproducibility over artificially clean statistics.

---

## 3. Warning State Before Fix

Before warning fix, the graph readiness audit reported:

```text
Readiness: READY_WITH_WARNINGS
Blocking issue: none
```

Main warning counts:

```text
OBLIGATION without Requirement: 612
threshold-related without Threshold node: 1227
UNKNOWN rule type/subtype: 1995
needs_review or low confidence signal: 1026
```

Structural checks:

```text
orphan edge count: 0
duplicate id count: 0
missing rule source_text count: 0
high-degree rule count: 0
```

Interpretation:

```text
- The graph was already structurally loadable.
- The warnings indicated evidence-quality and review-priority issues.
- The warnings were not Neo4j load blockers.
```

---

## 4. Warning Audit Results

A detailed warning audit was performed using:

```text
05_code/extractor/audit_reasoning_graph_warnings.py
```

The audit created detailed review files under:

```text
03_reviews_audits/pre_neo4j_warning_audits/
```

## 4.1 Obligation without Requirement

Audit result:

```text
Total: 612
Auto-fixable: 5
Manual review: 607
```

Interpretation:

```text
Only 5 cases were safe enough for automatic Requirement creation.
The remaining 607 cases were left for review because many obligations require parent context, list context, or manual interpretation.
```

Why not fix all 612?

```text
- Some OBLIGATION rules already contain usable requirement_text.
- Some require parent paragraph or item context.
- Some are broad procedural/legal statements.
- Some may be mislabeled or ambiguous.
- Mechanical requirement generation could add noisy or duplicated evidence.
```

## 4.2 Threshold-related without Threshold

Audit result:

```text
Total threshold-like candidates: 5917
Auto-fixable: 657
Manual review: 398
False positive candidates: 4862
```

Important interpretation:

```text
The raw number 5917 does not mean 5917 real threshold errors.
Most numeric-looking expressions were false positives such as article numbers, paragraph numbers, item numbers, annex numbers, form numbers, or legal references.
```

Only a subset was safe for automated patching.

## 4.3 UNKNOWN rule type/subtype

Audit result:

```text
Total UNKNOWN rule type/subtype: 1995
Auto-fixable preview candidates: 528
ListItem candidates: 1039
Manual review: 428
```

Interpretation:

```text
Many UNKNOWN nodes were not necessarily errors.
A large portion appeared to be list-item-like fragments, table/list fragments, or ambiguous legal text.
```

A limited UNKNOWN subtype update was previewed but later rolled back because of possible retrieval regression.

## 4.4 Low-confidence / needs_review

Audit result:

```text
Total low-confidence or needs_review signals: 513
Manual review: 513
```

Interpretation:

```text
These were intentionally kept as review signals.
They should not be blindly converted into confident graph nodes.
```

---

## 5. Patch Preview

A patch preview was created before applying any CSV modification.

Patch preview summary:

```text
ADD_REQUIREMENT_NODE: 5
ADD_RULE_REQUIREMENT_EDGE: 5
ADD_THRESHOLD_NODE: 150
ADD_RULE_THRESHOLD_EDGE: 150
UPDATE_RULE_SUBTYPE: 100 previewed
```

The preview file was generated as:

```text
03_reviews_audits/pre_neo4j_warning_audits/pre_neo4j_warning_patch_preview.csv
```

The preview step was important because it allowed potentially risky changes to be inspected before being applied.

---

## 6. Final Applied Patch

The final applied patch retained only structurally safe additions.

Final applied patch:

```text
Requirement nodes: +5
Rule-Requirement edges: +5
Threshold nodes: +150
Rule-Threshold edges: +150
```

The following patch was not retained:

```text
UPDATE_RULE_SUBTYPE
```

Reason for rollback:

```text
UNKNOWN subtype update was previewed and tested, but it had possible retrieval regression risk.
Therefore nodes_rule.csv was restored from backup for subtype updates.
```

Final modified graph CSV files:

```text
02_reasoning_graph/nodes/nodes_requirement.csv
02_reasoning_graph/nodes/nodes_threshold.csv
02_reasoning_graph/edges/edges_rule_requirement.csv
02_reasoning_graph/edges/edges_rule_threshold.csv
```

`nodes_rule.csv` was restored for the subtype update and no final UNKNOWN subtype update was retained.

---

## 7. Backup

Before applying graph CSV modifications, backups were created under:

```text
06_archive/pre_neo4j_warning_fix_backup/
```

Backup files:

```text
nodes_requirement.csv
nodes_threshold.csv
nodes_rule.csv
edges_rule_requirement.csv
edges_rule_threshold.csv
```

This preserves reproducibility and allows reverting risky changes.

---

## 8. Warning State After Fix

After the final applied patch, the readiness audit was rerun.

After-warning-fix readiness:

```text
READY_WITH_WARNINGS
```

Blocking issue:

```text
none
```

Warning before/after comparison:

```text
OBLIGATION without Requirement: 612 → 607
threshold-related without Threshold node: 1227 → 1210
UNKNOWN rule type/subtype: 1995 → 1995
needs_review or low confidence: 1026 → 1026
orphan edge count: 0 → 0
duplicate id count: 0 → 0
missing source_text count: 0 → 0
```

Interpretation:

```text
- Requirement and Threshold connectivity improved slightly.
- UNKNOWN and needs_review counts were intentionally preserved.
- No structural regression occurred.
- The graph remains loadable with warnings.
```

Important caution:

```text
Remaining warnings are not all errors.
They are quality signals for review, fallback handling, and evidence-pack design.
```

---

## 9. Readiness After Fix

After-warning-fix graph readiness summary:

```text
Readiness: READY_WITH_WARNINGS
Must Fix Before Load: none
```

Key node counts after fix:

```text
nodes_rule.csv: 8,858
nodes_requirement.csv: 3,639
nodes_threshold.csv: 1,782
nodes_exception.csv: 647
nodes_temporal_rule.csv: 227
nodes_entity_type.csv: 586
nodes_list_item.csv: 3,604
```

Key edge counts after fix:

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

Conclusion:

```text
The graph is structurally ready for the first Neo4j load.
```

---

## 10. Refined Retrieval Before/After

After warning fix, the refined retrieval evaluation was rerun.

Refined evaluation set:

```text
Total queries: 309
= curated 100
+ refined source-based 209
```

Before/after result:

```text
Top-1: 265/309 → 266/309
Top-3: 282/309 → 282/309
Top-5: 290/309 → 290/309
queries_without_matches: 0 → 0
possible_overmatch_count: 428 → 427
```

Interpretation:

```text
- The warning fix did not harm Top-3 or Top-5 retrieval.
- Top-1 improved by one case.
- possible_overmatch_count slightly decreased.
- The conservative patch was safe from a retrieval perspective.
```

This supports the decision to apply only high-confidence Requirement and Threshold patches.

---

## 11. Answerable Audit Before/After

Answerable audit was also rerun after the warning fix.

Before/after result:

```text
Top-1 answerable: 221/309 → 222/309
Top-3 answerable: 252/309 → 256/309
Top-5 answerable: 268/309 → 272/309
Top-10 answerable: 276/309 → 280/309
dangerous_wrong_answer_risk: 19 → 20
```

Interpretation:

```text
- The added Requirement and Threshold evidence improved answerability estimates.
- Top-5 answerable improved by 4 cases.
- Top-10 answerable improved by 4 cases.
- dangerous_wrong_answer_risk increased by 1, but this should be treated as an additional review signal rather than a major regression.
```

Important caution:

```text
Answerable audit is an automatic estimate.
It is not final answer accuracy.
```

Implication:

```text
The next stage should focus on Evidence Pack Builder design rather than additional broad automatic CSV patching.
```

---

## 12. Manual Review Files Remaining

The warning audit generated several manual review files.

Major remaining review files:

```text
review_obligation_requirement_manual_review.csv: 607
review_threshold_manual_review.csv: 398
review_threshold_false_positive_candidates.csv: 4862
review_unknown_manual_review.csv: 428
review_unknown_to_list_item_candidates.csv: 1039
review_low_confidence_reason_classification.csv: 513
```

These files should not be interpreted as mandatory cleanup queues before Neo4j loading.

Recommended interpretation:

```text
They are review pools.
They should be prioritized based on retrieval failures, answerability risks, and evidence-pack gaps.
```

Recommended priority order:

```text
1. Items connected to refined failed queries
2. Items connected to dangerous_wrong_answer_risk
3. Items blocking inspection/list/annex evidence
4. Items blocking education_time or threshold answers
5. Items affecting high-frequency user intents
6. Remaining low-priority manual review candidates
```

Do not attempt to manually clear all files before Neo4j loading.

---

## 13. Why Remaining Warnings Should Not Block Loading

The graph remains READY_WITH_WARNINGS, but this is acceptable for first load.

## 13.1 OBLIGATION without Requirement

Remaining count:

```text
607
```

Reason not blocking:

```text
- Not all obligations require separate Requirement nodes.
- Rule.requirement_text or Rule.source_text can serve as fallback evidence.
- Some require parent context or manual review.
```

## 13.2 Threshold-related without Threshold

Remaining count:

```text
1210
```

Reason not blocking:

```text
- Many numeric expressions are not true thresholds.
- Some thresholds are context-dependent.
- Over-adding thresholds can damage precision.
```

## 13.3 UNKNOWN rule type/subtype

Remaining count:

```text
1995
```

Reason not blocking:

```text
- UNKNOWN preserves uncertainty rather than forcing wrong labels.
- Many UNKNOWN items may be list fragments or ambiguous source fragments.
- They can be loaded with needs_review/confidence properties.
```

## 13.4 needs_review / low confidence

Remaining count:

```text
1026
```

Reason not blocking:

```text
- needs_review is a quality signal.
- It can be used during answer generation to apply caution.
- Dropping these nodes would reduce traceability and future auditability.
```

---

## 14. Neo4j Load Readiness Interpretation

After warning fix, the graph is ready for first Neo4j load under the following assumptions:

```text
1. CSV remains the source of truth.
2. Neo4j is treated as an execution and retrieval layer.
3. UNKNOWN and needs_review nodes are loaded, not dropped.
4. SourceNode placeholder is used for robust source traceability.
5. Major source anchors are loaded in the first load.
6. Physical table structures can be loaded in a later phase.
```

Recommended first-load strategy:

```text
Reasoning Graph
+ SourceNode
+ major source anchor nodes:
  - Article
  - Paragraph
  - Item
  - Subitem
  - Addendum
  - Annex
  - LogicalRow
  - LogicalCell
  - AnnexNote
```

Recommended second-load targets:

```text
PhysicalTable
PhysicalRow
PhysicalCell
full physical annex reconstruction
rich document browsing hierarchy
```

---

## 15. What Should Be Handled Before Loader Implementation

Before implementing the Neo4j loader, the following should be decided:

```text
1. SourceNode placeholder schema
2. SourceNode to actual source anchor resolution strategy
3. Whether Article/Paragraph/Item/Subitem are included in first load
4. Whether Annex/LogicalRow/LogicalCell/AnnexNote are included in first load
5. Whether PhysicalTable/PhysicalRow/PhysicalCell are deferred
6. Relationship mapping for edges_rule_reasoning.csv
7. How to load dynamic relationship types safely
8. How to handle unresolved source_node_id
9. How to preserve confidence and needs_review flags
10. Post-load validation query set
```

Recommended decision:

```text
Use a balanced first-load strategy:
Reasoning Graph + SourceNode + major source anchors.
```

---

## 16. What Should Be Handled After Neo4j Load

The following tasks are better handled after the first Neo4j load:

```text
1. Evidence Pack Builder implementation
2. Intent-specific graph traversal
3. Annex/list evidence expansion
4. Penalty-to-obligation expansion
5. Exception and SCOPE_EXCLUSION expansion
6. Threshold context formatting
7. Source citation formatting
8. Claim check design
9. Answer generation prompt design
10. UI evidence chip design
11. Cypher-based retrieval experiments
12. Physical source reconstruction loading
```

These tasks require graph traversal experiments and should not delay the first load unnecessarily.

---

## 17. Impact on Paper/Report Writing

This warning fix process can be described in a paper or technical report as a conservative quality control step.

Possible statement:

```text
Before Neo4j loading, we performed a graph readiness audit and conservatively patched only high-confidence missing Requirement and Threshold evidence. Ambiguous UNKNOWN and low-confidence nodes were retained as review signals rather than forcefully reclassified.
```

More detailed statement:

```text
The pre-load audit found no orphan edges, duplicate identifiers, or missing source text. We therefore treated the graph as structurally loadable. Remaining warnings were categorized as non-blocking quality signals for evidence-pack construction and manual review.
```

Avoid saying:

```text
All warnings were fixed.
The graph is error-free.
The legal QA system is complete.
Answer accuracy improved to a final validated level.
```

---

## 18. Final Conclusion

The conservative pre-Neo4j warning fix was successful.

Final result:

```text
Readiness: READY_WITH_WARNINGS
Load blockers: none
Requirement nodes: +5
Threshold nodes: +150
Top-5 retrieval: maintained at 290/309
Top-5 answerable estimate: improved from 268/309 to 272/309
```

The remaining warnings should not block the first Neo4j load.

They should be handled as follows:

```text
- Load them with confidence and needs_review properties.
- Use them cautiously in evidence pack construction.
- Prioritize manual review based on retrieval failures and answerability risks.
- Patch CSV source of truth when confirmed issues are found.
- Reload Neo4j from CSV rather than manually editing Neo4j as the source of truth.
```

The next recommended step is:

```text
Implement a staged Neo4j loader using the balanced first-load strategy:
Reasoning Graph + SourceNode + major source anchors.
```
