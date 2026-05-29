# Neo4j Schema Draft Before First Load

## 1. Purpose

This document defines the draft Neo4j schema for the first graph load of the industrial safety legal Graph-RAG project.

The purpose of the first Neo4j load is not to build a fully complete legal document browser. The purpose is to load the minimum graph structure required for Graph-RAG retrieval, source-grounded evidence expansion, and later answer generation.

The current CSV-based knowledge base contains three major graph layers:

1. Document Graph
   - Law, Heading, Article, Paragraph, Item, Subitem, Addendum
   - Original source structure of legal body text

2. Annex Source Graph
   - Annex, AnnexSection, PhysicalTable, PhysicalRow, PhysicalCell, LogicalRow, LogicalCell, AnnexNote
   - Original and reasoning-oriented structure of annexes, tables, forms, and notes

3. Reasoning Graph
   - Rule, Requirement, Threshold, Exception, TemporalRule, EntityType, ListItem
   - Meaning-level legal reasoning nodes extracted from body text and annex sources

The first Neo4j load should use a balanced strategy:

```text
First load:
Reasoning Graph
+ SourceNode placeholder
+ major source anchor nodes
  - Article
  - Paragraph
  - Item
  - Subitem
  - Addendum
  - Annex
  - LogicalRow
  - LogicalCell
  - AnnexNote

Second load:
PhysicalTable
PhysicalRow
PhysicalCell
rich physical source hierarchy
full document/annex browsing structure
```

This balanced strategy is recommended because Graph-RAG answer generation requires both reasoning evidence and source citation. Loading only reasoning nodes would make source traversal weak. Loading every physical table/row/cell in the first pass would make initial debugging unnecessarily complex.

No Neo4j loader has been implemented yet, and no Neo4j load has been executed at the time of this schema draft.

---

## 2. First-Load Design Principle

The first-load graph should support the following tasks:

1. Retrieve legal Rule candidates for a user query.
2. Expand a Rule into Requirement, Threshold, Exception, TemporalRule, EntityType, and ListItem evidence.
3. Preserve original source traceability through SourceNode and source anchor nodes.
4. Retrieve legal citation information such as law_name, article_no, annex_title, and source_text.
5. Support annex/list-based questions using LogicalRow and LogicalCell.
6. Avoid loading unnecessary physical table structures before the reasoning/evidence pipeline is verified.

The first-load schema should therefore prioritize:

```text
Rule-centered retrieval
Source-grounded evidence
Parent context expansion
Annex logical evidence
Load-time validation
Reproducibility from CSV
```

The first-load schema should not prioritize:

```text
Full physical table reconstruction
UI-level document browsing
Manual edits inside Neo4j
Complete legal knowledge finalization
```

CSV files remain the source of truth. If data errors are found after Neo4j loading, they should be exported as review items and patched back into CSV before reloading.

---

## 3. First-Load Node Labels

## 3.1 Reasoning node labels

These labels come directly from `reasoning_graph/nodes/`.

### Rule

Source file:

```text
reasoning_graph/nodes/nodes_rule.csv
```

Role:
- Central legal reasoning node.
- Represents obligations, prohibitions, penalties, definitions, procedures, exceptions, qualifications, safety standards, etc.
- Primary retrieval target.

### Requirement

Source file:

```text
reasoning_graph/nodes/nodes_requirement.csv
```

Role:
- Represents required actions extracted from Rule.
- Used for obligation, document, appointment, safety measure, and reporting questions.

### Threshold

Source file:

```text
reasoning_graph/nodes/nodes_threshold.csv
```

Role:
- Represents numeric, time, frequency, amount, distance, weight, headcount, or deadline criteria.
- Used for education time, retention period, applicability threshold, and safety standard questions.

### Exception

Source file:

```text
reasoning_graph/nodes/nodes_exception.csv
```

Role:
- Represents exception, exclusion, modification, and scope exclusion evidence.
- Used for applicability and exception questions.

### TemporalRule

Source file:

```text
reasoning_graph/nodes/nodes_temporal_rule.csv
```

Role:
- Represents effective date, transitional provision, grace period, addendum, and temporal applicability evidence.

### EntityType

Source file:

```text
reasoning_graph/nodes/nodes_entity_type.csv
```

Role:
- Represents legal actors, target subjects, roles, and affected entities.
- Examples: 사업주, 근로자, 도급인, 관계수급인, 안전관리자, 보건관리자, 경영책임자.

### ListItem

Source file:

```text
reasoning_graph/nodes/nodes_list_item.csv
```

Role:
- Represents list-like legal evidence such as equipment names, work types, substances, diseases, inspection items, form fields, and qualification items.
- Used especially for annex/list questions.

---

## 3.2 Source placeholder node label

### SourceNode

Source file:

```text
Derived from reasoning_graph/edges/edges_rule_source.csv
and source fields inside nodes_rule.csv
```

Role:
- Generic placeholder for the original source node referenced by a Rule.
- Used to avoid losing source traceability even when actual Document Graph or Annex node resolution is incomplete.
- Acts as an intermediate anchor between Rule and actual source graph nodes.

Recommended key:

```text
source_node_id
```

Recommended properties:

```text
source_node_id
source_node_type
source_text
source_context_text
parent_source_node_id
parent_source_node_type
law_name
article_no
annex_id
annex_no
annex_title
source_origin
```

Recommended relationship:

```text
(:Rule)-[:EXTRACTED_FROM]->(:SourceNode)
```

Later, SourceNode can resolve to actual source anchor nodes:

```text
(:SourceNode)-[:RESOLVES_TO]->(:Article)
(:SourceNode)-[:RESOLVES_TO]->(:Paragraph)
(:SourceNode)-[:RESOLVES_TO]->(:Item)
(:SourceNode)-[:RESOLVES_TO]->(:Subitem)
(:SourceNode)-[:RESOLVES_TO]->(:LogicalRow)
(:SourceNode)-[:RESOLVES_TO]->(:LogicalCell)
(:SourceNode)-[:RESOLVES_TO]->(:AnnexNote)
```

---

## 3.3 First-load source anchor labels

The first-load source graph should include major source anchor nodes needed for citation and evidence-pack construction.

### Law

Source file:

```text
document_graph/nodes/nodes_law.csv
```

Role:
- Top-level legal source node.
- Identifies the law name and version context.

### Article

Source file:

```text
document_graph/nodes/nodes_article.csv
```

Role:
- Core citation-level source node.
- Most legal answers cite law name and article number.

### Paragraph

Source file:

```text
document_graph/nodes/nodes_paragraph.csv
```

Role:
- Source node for article-level paragraphs or clauses.
- Often contains common obligation frame such as “사업주는 다음 각 호의 조치를 하여야 한다”.

### Item

Source file:

```text
document_graph/nodes/nodes_item.csv
```

Role:
- Source node for item-level legal text.
- Often contains detailed requirements, standards, or list-like clauses.

### Subitem

Source file:

```text
document_graph/nodes/nodes_subitem.csv
```

Role:
- Source node for fine-grained legal text below item.
- Used for detailed safety standards or itemized requirements.

### Addendum

Source file:

```text
document_graph/nodes/nodes_addendum.csv
```

Role:
- Source node for addendum, effective date, transitional provisions, and temporal context.

### Annex

Source file:

```text
document_graph/source_annex/annexes.csv
```

Role:
- Top-level annex/source table node.
- Used for annex citation and related-article expansion.

### LogicalRow

Source file:

```text
document_graph/source_annex/annex_logical_rows.csv
```

Role:
- Reasoning-oriented row unit.
- Used for annex/list evidence such as inspection target equipment, education contents, health examination items, qualifications, and form fields.

### LogicalCell

Source file:

```text
document_graph/source_annex/annex_logical_cells.csv
```

Role:
- Cell-level logical evidence within LogicalRow.
- Used to expose specific values, item names, criteria, descriptions, or notes.

### AnnexNote

Source file:

```text
document_graph/source_annex/annex_notes.csv
```

Role:
- Represents notes, remarks, writing instructions, applicability notes, or explanatory clauses inside annexes.

---

## 3.4 Second-load source labels

These labels are valuable for full source reconstruction but can be deferred until after the first reasoning/evidence pipeline is verified.

### PhysicalTable

Source file:

```text
document_graph/source_annex/annex_physical_tables.csv
```

### PhysicalRow

Source file:

```text
document_graph/source_annex/annex_physical_rows.csv
```

### PhysicalCell

Source file:

```text
document_graph/source_annex/annex_physical_cells.csv
```

Reason for deferral:
- Physical table structures are important for audit and source reconstruction.
- However, first answer generation can begin with LogicalRow/LogicalCell evidence.
- Loading physical structures in the first pass increases loader complexity and debugging burden.

---

## 4. Relationship Types

## 4.1 Reasoning graph relationships

These relationships come directly from `reasoning_graph/edges/`.

### EXTRACTED_FROM

Source file:

```text
reasoning_graph/edges/edges_rule_source.csv
```

Recommended first-load pattern:

```text
(:Rule)-[:EXTRACTED_FROM]->(:SourceNode)
```

Possible later pattern:

```text
(:Rule)-[:EXTRACTED_FROM]->(:Article)
(:Rule)-[:EXTRACTED_FROM]->(:Paragraph)
(:Rule)-[:EXTRACTED_FROM]->(:Item)
(:Rule)-[:EXTRACTED_FROM]->(:Subitem)
(:Rule)-[:EXTRACTED_FROM]->(:LogicalRow)
(:Rule)-[:EXTRACTED_FROM]->(:LogicalCell)
```

### HAS_REQUIREMENT

Source file:

```text
reasoning_graph/edges/edges_rule_requirement.csv
```

Pattern:

```text
(:Rule)-[:HAS_REQUIREMENT]->(:Requirement)
```

### HAS_THRESHOLD

Source file:

```text
reasoning_graph/edges/edges_rule_threshold.csv
```

Pattern:

```text
(:Rule)-[:HAS_THRESHOLD]->(:Threshold)
```

### HAS_EXCEPTION

Source file:

```text
reasoning_graph/edges/edges_rule_exception.csv
```

Pattern:

```text
(:Rule)-[:HAS_EXCEPTION]->(:Exception)
```

### HAS_TEMPORAL_CONDITION

Source file:

```text
reasoning_graph/edges/edges_rule_temporal.csv
```

Pattern:

```text
(:Rule)-[:HAS_TEMPORAL_CONDITION]->(:TemporalRule)
```

### APPLIES_TO / TARGETS / REQUIRES_ROLE

Source file:

```text
reasoning_graph/edges/edges_rule_entity.csv
```

Recommended handling:
- Preserve the original `rel` property.
- If possible, map stable relationship labels:
  - APPLIES_TO
  - TARGETS
  - REQUIRES_ROLE
- If relationship labels are inconsistent, load as `RELATED_ENTITY` with `rel` as property in the first pass.

### HAS_LIST_ITEM

Source file:

```text
reasoning_graph/edges/edges_rule_list_item.csv
```

Pattern:

```text
(:Rule)-[:HAS_LIST_ITEM]->(:ListItem)
```

### Rule-to-Rule reasoning relationships

Source file:

```text
reasoning_graph/edges/edges_rule_reasoning.csv
```

Possible relationship types:

```text
REFERS_TO
DELEGATES_TO
APPLIES_PENALTY_FOR
APPLIES_BY_ANALOGY
REQUIRES_PREREQUISITE
RULE_DETAIL_DEFINED_IN_ANNEX
RULE_SUPPORTED_BY_ANNEX
RULE_DELEGATES_DETAIL_TO_ANNEX
ANNEX_RULE_REFINES_ARTICLE_RULE
```

Recommended first-load handling:
- If rel values are stable and valid Neo4j relationship names, load them as relationship types.
- Otherwise, load them as `RELATED_TO` and preserve the original rel as a property.

Example:

```text
(:Rule)-[:RELATED_TO {rel: "RULE_SUPPORTED_BY_ANNEX"}]->(:Rule)
```

---

## 4.2 Source resolution relationships

### RESOLVES_TO

Generated relationship:

```text
(:SourceNode)-[:RESOLVES_TO]->(:Article)
(:SourceNode)-[:RESOLVES_TO]->(:Paragraph)
(:SourceNode)-[:RESOLVES_TO]->(:Item)
(:SourceNode)-[:RESOLVES_TO]->(:Subitem)
(:SourceNode)-[:RESOLVES_TO]->(:Addendum)
(:SourceNode)-[:RESOLVES_TO]->(:LogicalRow)
(:SourceNode)-[:RESOLVES_TO]->(:LogicalCell)
(:SourceNode)-[:RESOLVES_TO]->(:AnnexNote)
```

Purpose:
- Connect generic source references to actual source graph nodes.
- Keep first-load robust even when some source IDs cannot be resolved.
- Allow unresolved SourceNode to still carry source_text and citation information.

Recommended properties:

```text
resolution_method
resolution_confidence
resolved_node_label
```

---

## 4.3 Document Graph relationships

### CONTAINS

Source files may include:

```text
document_graph/edges/edges_contains.csv
document_graph/edges/edges_law_hierarchy.csv
```

Pattern:

```text
(:Law)-[:CONTAINS]->(:Heading)
(:Heading)-[:CONTAINS]->(:Article)
(:Article)-[:CONTAINS]->(:Paragraph)
(:Paragraph)-[:CONTAINS]->(:Item)
(:Item)-[:CONTAINS]->(:Subitem)
(:Law)-[:CONTAINS]->(:Addendum)
```

Note:
- If both `edges_contains.csv` and `edges_law_hierarchy.csv` exist, the loader should check whether they duplicate the same hierarchy before loading both.

### REFERS_TO_SOURCE

Source files may include:

```text
document_graph/edges/edges_article_references.csv
document_graph/edges/edges_refers.csv
```

Pattern:

```text
(:Article)-[:REFERS_TO_SOURCE]->(:Article)
```

or generic:

```text
(:SourceNode)-[:REFERS_TO_SOURCE]->(:SourceNode)
```

Note:
- Use carefully because broad reference expansion can increase overmatch.

---

## 4.4 Annex Source Graph relationships

### RELATED_TO_ARTICLE

Source file:

```text
document_graph/source_annex/edges_annex_to_articles.csv
```

Pattern:

```text
(:Annex)-[:RELATED_TO_ARTICLE]->(:Article)
```

### HAS_LOGICAL_ROW

Source files may include:

```text
document_graph/source_annex/edges_physical_table_to_logical_rows.csv
```

or logical row parent metadata in `annex_logical_rows.csv`.

Recommended pattern:

```text
(:Annex)-[:HAS_LOGICAL_ROW]->(:LogicalRow)
```

or if section/table hierarchy is loaded:

```text
(:Annex)-[:CONTAINS]->(:AnnexSection)
(:AnnexSection)-[:CONTAINS]->(:LogicalRow)
```

### HAS_LOGICAL_CELL

Source file:

```text
document_graph/source_annex/edges_logical_row_to_logical_cells.csv
```

Pattern:

```text
(:LogicalRow)-[:HAS_LOGICAL_CELL]->(:LogicalCell)
```

### HAS_NOTE

Source files may include:

```text
document_graph/source_annex/edges_section_to_notes.csv
```

or note parent metadata in `annex_notes.csv`.

Pattern:

```text
(:Annex)-[:HAS_NOTE]->(:AnnexNote)
(:LogicalRow)-[:HAS_NOTE]->(:AnnexNote)
```

Exact relationship direction should be confirmed from actual CSV headers.

---

## 5. Node Properties

## 5.1 Rule properties

Actual columns in `nodes_rule.csv` include:

```text
rule_id
rule_type
rule_subtype
target_subject
target_object
condition_text
requirement_text
exception_text
penalty_text
source_node_type
source_node_id
parent_source_node_type
parent_source_node_id
source_context_text
source_text
law_version_id
law_name
article_id
article_no
paragraph_no
heading_context
annex_id
annex_no
annex_title
related_article_id
query_intents_json
confidence
needs_review
extraction_method
```

Recommended required properties:

```text
rule_id
rule_type
rule_subtype
source_node_id
source_text
law_name
article_no
annex_title
confidence
needs_review
```

Note:
- `source_text` must be preserved.
- `needs_review` should not prevent loading.
- UNKNOWN types should be loaded but flagged.

---

## 5.2 Requirement properties

Actual columns in `nodes_requirement.csv` include:

```text
requirement_id
rule_id
requirement_type
required_action
target_object
required_count
required_unit
source_node_id
source_text
confidence
needs_review
```

Recommended required properties:

```text
requirement_id
rule_id
required_action
source_text
source_node_id
```

---

## 5.3 Threshold properties

Actual columns in `nodes_threshold.csv` include:

```text
threshold_id
rule_id
attribute
operator
value_min
value_max
value_exact
unit
raw_expression
source_node_id
```

Recommended required properties:

```text
threshold_id
raw_expression
unit
operator
source_node_id
```

Note:
- `raw_expression` must not be used alone in final answers.
- Always present threshold together with source_text or Rule context.

---

## 5.4 Exception properties

Actual columns in `nodes_exception.csv` include:

```text
exception_id
rule_id
exception_type
condition_text
effect_text
scope
source_node_id
source_text
```

Recommended required properties:

```text
exception_id
exception_type
condition_text
effect_text
source_text
```

---

## 5.5 TemporalRule properties

Actual columns in `nodes_temporal_rule.csv` include:

```text
temporal_rule_id
rule_id
temporal_type
condition_text
effective_from
effective_until
target_subject
target_article_no
source_node_id
law_version_id
```

Recommended required properties:

```text
temporal_rule_id
temporal_type
condition_text
effective_from
effective_until
source_node_id
```

---

## 5.6 EntityType properties

Actual columns in `nodes_entity_type.csv` include:

```text
entity_type_id
entity_category
entity_name
synonyms
source_node_ids
```

Recommended required properties:

```text
entity_type_id
entity_name
entity_category
```

---

## 5.7 ListItem properties

Actual columns in `nodes_list_item.csv` include:

```text
list_item_id
list_item_type
item_text
source_node_type
source_node_id
parent_source_node_type
parent_source_node_id
source_context_text
law_version_id
law_name
article_id
article_no
annex_id
annex_no
annex_title
source_rule_id
needs_review
move_reason
```

Recommended required properties:

```text
list_item_id
list_item_type
item_text
source_node_id
source_context_text
law_name
article_no
annex_title
source_rule_id
needs_review
```

Note:
- ListItem should usually be used with parent Rule and source context.
- ListItem alone is often insufficient as answer evidence.

---

## 5.8 SourceNode properties

Generated from Rule source information and `edges_rule_source.csv`.

Recommended properties:

```text
source_node_id
source_node_type
source_text
source_context_text
parent_source_node_id
parent_source_node_type
law_name
article_no
annex_id
annex_no
annex_title
source_origin
resolved
resolved_label
```

Recommended ID:

```text
source_node_id
```

If multiple Rule rows reference the same source_node_id with slightly different context fields, the loader should preserve the richest non-empty source_text/source_context_text or store alternatives as a list-like property only if supported safely.

---

## 5.9 Source anchor properties

Actual properties should be confirmed from CSV headers. Recommended draft properties are:

### Law

```text
node_id or law_id
law_name
law_version_id
effective_date
raw_metadata
```

### Article

```text
node_id or article_id
law_name
law_version_id
article_no
article_title
source_text
heading_context
```

### Paragraph

```text
node_id or paragraph_id
article_id
law_name
article_no
paragraph_no
source_text
source_context_text
```

### Item

```text
node_id or item_id
parent_node_id
article_id
law_name
article_no
item_no
source_text
source_context_text
```

### Subitem

```text
node_id or subitem_id
parent_node_id
article_id
law_name
article_no
subitem_no
source_text
source_context_text
```

### Addendum

```text
node_id or addendum_id
law_name
law_version_id
source_text
addendum_title
temporal_context
```

### Annex

```text
annex_id
annex_no
annex_title
law_name
related_article_id
source_text_raw
clean_text
```

### LogicalRow

```text
logical_row_id
annex_id
annex_title
row_text
source_text
row_index
section_id
```

### LogicalCell

```text
logical_cell_id
logical_row_id
annex_id
column_name
cell_text
source_text
```

### AnnexNote

```text
note_id
annex_id
section_id
note_text
source_text
```

If the actual CSV headers differ, the loader should map actual columns rather than assuming these names.

---

## 6. Relationship Properties

## 6.1 Rule-child edge properties

### edges_rule_requirement.csv

```text
from_rule_id
to_requirement_id
rel
```

### edges_rule_threshold.csv

```text
from_rule_id
to_threshold_id
rel
threshold_role
```

### edges_rule_exception.csv

```text
from_rule_id
to_exception_id
rel
```

### edges_rule_temporal.csv

```text
from_rule_id
to_temporal_id
rel
```

### edges_rule_entity.csv

```text
from_rule_id
to_entity_type_id
rel
```

### edges_rule_list_item.csv

```text
from_rule_id
to_list_item_id
rel
needs_review
```

### edges_rule_source.csv

```text
from_rule_id
to_node_id
to_node_type
rel
```

### edges_rule_reasoning.csv

```text
from_rule_id
to_rule_id
rel
reasoning_note
source_edge_id
```

---

## 7. Recommended Uniqueness Constraints

## 7.1 Reasoning nodes

```cypher
CREATE CONSTRAINT rule_id_unique IF NOT EXISTS
FOR (n:Rule) REQUIRE n.rule_id IS UNIQUE;

CREATE CONSTRAINT requirement_id_unique IF NOT EXISTS
FOR (n:Requirement) REQUIRE n.requirement_id IS UNIQUE;

CREATE CONSTRAINT threshold_id_unique IF NOT EXISTS
FOR (n:Threshold) REQUIRE n.threshold_id IS UNIQUE;

CREATE CONSTRAINT exception_id_unique IF NOT EXISTS
FOR (n:Exception) REQUIRE n.exception_id IS UNIQUE;

CREATE CONSTRAINT temporal_rule_id_unique IF NOT EXISTS
FOR (n:TemporalRule) REQUIRE n.temporal_rule_id IS UNIQUE;

CREATE CONSTRAINT entity_type_id_unique IF NOT EXISTS
FOR (n:EntityType) REQUIRE n.entity_type_id IS UNIQUE;

CREATE CONSTRAINT list_item_id_unique IF NOT EXISTS
FOR (n:ListItem) REQUIRE n.list_item_id IS UNIQUE;
```

## 7.2 Source placeholder

```cypher
CREATE CONSTRAINT source_node_id_unique IF NOT EXISTS
FOR (n:SourceNode) REQUIRE n.source_node_id IS UNIQUE;
```

## 7.3 Source anchors

Actual ID field names should be confirmed before implementation.

```cypher
CREATE CONSTRAINT law_node_id_unique IF NOT EXISTS
FOR (n:Law) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT article_node_id_unique IF NOT EXISTS
FOR (n:Article) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT paragraph_node_id_unique IF NOT EXISTS
FOR (n:Paragraph) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT item_node_id_unique IF NOT EXISTS
FOR (n:Item) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT subitem_node_id_unique IF NOT EXISTS
FOR (n:Subitem) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT addendum_node_id_unique IF NOT EXISTS
FOR (n:Addendum) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT annex_id_unique IF NOT EXISTS
FOR (n:Annex) REQUIRE n.annex_id IS UNIQUE;

CREATE CONSTRAINT logical_row_id_unique IF NOT EXISTS
FOR (n:LogicalRow) REQUIRE n.logical_row_id IS UNIQUE;

CREATE CONSTRAINT logical_cell_id_unique IF NOT EXISTS
FOR (n:LogicalCell) REQUIRE n.logical_cell_id IS UNIQUE;

CREATE CONSTRAINT annex_note_id_unique IF NOT EXISTS
FOR (n:AnnexNote) REQUIRE n.note_id IS UNIQUE;
```

If actual source graph files do not use `node_id`, the loader should adapt constraints to the actual ID columns.

---

## 8. Recommended Indexes

## 8.1 Rule indexes

```cypher
CREATE INDEX rule_law_name_index IF NOT EXISTS
FOR (n:Rule) ON (n.law_name);

CREATE INDEX rule_article_no_index IF NOT EXISTS
FOR (n:Rule) ON (n.article_no);

CREATE INDEX rule_type_index IF NOT EXISTS
FOR (n:Rule) ON (n.rule_type);

CREATE INDEX rule_subtype_index IF NOT EXISTS
FOR (n:Rule) ON (n.rule_subtype);

CREATE INDEX rule_annex_title_index IF NOT EXISTS
FOR (n:Rule) ON (n.annex_title);

CREATE INDEX rule_source_node_id_index IF NOT EXISTS
FOR (n:Rule) ON (n.source_node_id);
```

## 8.2 ListItem indexes

```cypher
CREATE INDEX list_item_type_index IF NOT EXISTS
FOR (n:ListItem) ON (n.list_item_type);

CREATE INDEX list_item_law_name_index IF NOT EXISTS
FOR (n:ListItem) ON (n.law_name);

CREATE INDEX list_item_article_no_index IF NOT EXISTS
FOR (n:ListItem) ON (n.article_no);

CREATE INDEX list_item_annex_title_index IF NOT EXISTS
FOR (n:ListItem) ON (n.annex_title);
```

## 8.3 Source indexes

```cypher
CREATE INDEX source_node_law_name_index IF NOT EXISTS
FOR (n:SourceNode) ON (n.law_name);

CREATE INDEX source_node_article_no_index IF NOT EXISTS
FOR (n:SourceNode) ON (n.article_no);

CREATE INDEX source_node_annex_title_index IF NOT EXISTS
FOR (n:SourceNode) ON (n.annex_title);
```

## 8.4 Entity indexes

```cypher
CREATE INDEX entity_name_index IF NOT EXISTS
FOR (n:EntityType) ON (n.entity_name);
```

---

## 9. Full-Text Index Recommendations

Full-text indexes should be considered after first load validation.

Recommended fields:

```text
Rule.source_text
Rule.source_context_text
Rule.requirement_text
Rule.condition_text
Rule.exception_text
Rule.penalty_text
Requirement.source_text
Requirement.required_action
Threshold.raw_expression
Exception.source_text
Exception.condition_text
ListItem.item_text
ListItem.source_context_text
SourceNode.source_text
SourceNode.source_context_text
LogicalRow.source_text
LogicalCell.source_text
AnnexNote.source_text
```

Example Cypher draft:

```cypher
CREATE FULLTEXT INDEX rule_text_fulltext IF NOT EXISTS
FOR (n:Rule)
ON EACH [n.source_text, n.source_context_text, n.requirement_text, n.condition_text, n.exception_text, n.penalty_text];

CREATE FULLTEXT INDEX source_text_fulltext IF NOT EXISTS
FOR (n:SourceNode)
ON EACH [n.source_text, n.source_context_text];

CREATE FULLTEXT INDEX list_item_fulltext IF NOT EXISTS
FOR (n:ListItem)
ON EACH [n.item_text, n.source_context_text];
```

Exact full-text index syntax depends on Neo4j version.

---

## 10. Load Priority

## 10.1 First-load priority

Recommended first-load order:

1. Create constraints and indexes.
2. Load reasoning nodes:
   - Rule
   - Requirement
   - Threshold
   - Exception
   - TemporalRule
   - EntityType
   - ListItem
3. Generate/load SourceNode placeholders.
4. Load source anchor nodes:
   - Law
   - Article
   - Paragraph
   - Item
   - Subitem
   - Addendum
   - Annex
   - LogicalRow
   - LogicalCell
   - AnnexNote
5. Load Rule-child edges:
   - HAS_REQUIREMENT
   - HAS_THRESHOLD
   - HAS_EXCEPTION
   - HAS_TEMPORAL_CONDITION
   - entity relationships
   - HAS_LIST_ITEM
6. Load Rule-source edges:
   - Rule → SourceNode
7. Resolve SourceNode to actual source anchors where possible:
   - SourceNode → Article/Paragraph/Item/Subitem/Addendum/LogicalRow/LogicalCell/AnnexNote
8. Load selected source hierarchy edges:
   - Article → Paragraph
   - Paragraph → Item
   - Item → Subitem
   - Annex → LogicalRow
   - LogicalRow → LogicalCell
   - Annex → AnnexNote
9. Load Rule-to-Rule reasoning edges.
10. Run post-load validation Cypher queries.

## 10.2 Second-load priority

Second-load targets:

1. PhysicalTable
2. PhysicalRow
3. PhysicalCell
4. Physical-to-logical source traceability edges
5. Rich Law/Heading/Article browsing hierarchy
6. Additional source reference edges
7. UI-oriented document browsing features

---

## 11. Evidence Pack Traversal Examples

## 11.1 Basic Rule evidence pack

```cypher
MATCH (r:Rule {rule_id: $rule_id})
OPTIONAL MATCH (r)-[:HAS_REQUIREMENT]->(req:Requirement)
OPTIONAL MATCH (r)-[:HAS_THRESHOLD]->(th:Threshold)
OPTIONAL MATCH (r)-[:HAS_EXCEPTION]->(ex:Exception)
OPTIONAL MATCH (r)-[:HAS_TEMPORAL_CONDITION]->(tmp:TemporalRule)
OPTIONAL MATCH (r)-[:HAS_LIST_ITEM]->(li:ListItem)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
RETURN
  r,
  collect(DISTINCT req) AS requirements,
  collect(DISTINCT th) AS thresholds,
  collect(DISTINCT ex) AS exceptions,
  collect(DISTINCT tmp) AS temporal_rules,
  collect(DISTINCT li) AS list_items,
  collect(DISTINCT src) AS sources;
```

## 11.2 Source resolution evidence

```cypher
MATCH (r:Rule {rule_id: $rule_id})-[:EXTRACTED_FROM]->(src:SourceNode)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(a:Article)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(p:Paragraph)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(i:Item)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(s:Subitem)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(lr:LogicalRow)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(lc:LogicalCell)
RETURN src, a, p, i, s, lr, lc;
```

## 11.3 Annex/list evidence expansion

```cypher
MATCH (r:Rule {rule_id: $rule_id})
OPTIONAL MATCH (r)-[:HAS_LIST_ITEM]->(li:ListItem)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(lr:LogicalRow)
OPTIONAL MATCH (lr)-[:HAS_LOGICAL_CELL]->(lc:LogicalCell)
RETURN r, collect(DISTINCT li) AS list_items, collect(DISTINCT lr) AS logical_rows, collect(DISTINCT lc) AS logical_cells;
```

## 11.4 Penalty-related expansion

```cypher
MATCH (r:Rule {rule_id: $rule_id})
OPTIONAL MATCH (r)-[:APPLIES_PENALTY_FOR|RELATED_TO]->(related:Rule)
WHERE related.rule_type = "PENALTY" OR related.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE"]
RETURN r, collect(DISTINCT related) AS penalty_rules;
```

If `edges_rule_reasoning.rel` is loaded as a property on `RELATED_TO`, use:

```cypher
MATCH (r:Rule {rule_id: $rule_id})-[e:RELATED_TO]->(related:Rule)
WHERE e.rel = "APPLIES_PENALTY_FOR"
RETURN r, related, e;
```

## 11.5 Applicability/exception evidence

```cypher
MATCH (r:Rule {rule_id: $rule_id})
OPTIONAL MATCH (r)-[:HAS_EXCEPTION]->(ex:Exception)
OPTIONAL MATCH (r)-[:HAS_THRESHOLD]->(th:Threshold)
OPTIONAL MATCH (r)-[:HAS_TEMPORAL_CONDITION]->(tmp:TemporalRule)
OPTIONAL MATCH (r)-[:APPLIES_TO|TARGETS]->(ent:EntityType)
RETURN r, collect(DISTINCT ex), collect(DISTINCT th), collect(DISTINCT tmp), collect(DISTINCT ent);
```

---

## 12. Post-Load Validation Queries

## 12.1 Node counts

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(*) AS count
ORDER BY count DESC;
```

## 12.2 Rule count

```cypher
MATCH (r:Rule)
RETURN count(r) AS rule_count;
```

Expected count after warning fix:

```text
Rule: 8,858
```

## 12.3 Requirement and Threshold counts

Expected after warning fix:

```text
Requirement: 3,639
Threshold: 1,782
```

Validation query:

```cypher
MATCH (req:Requirement)
WITH count(req) AS requirement_count
MATCH (th:Threshold)
RETURN requirement_count, count(th) AS threshold_count;
```

## 12.4 Orphan Rule-child edges

```cypher
MATCH (r:Rule)-[e:HAS_REQUIREMENT]->(req:Requirement)
RETURN count(e) AS requirement_edges;
```

Run equivalent checks for:

```text
HAS_THRESHOLD
HAS_EXCEPTION
HAS_TEMPORAL_CONDITION
HAS_LIST_ITEM
```

## 12.5 Source traceability check

```cypher
MATCH (r:Rule)
WHERE r.source_text IS NULL OR trim(r.source_text) = ""
RETURN count(r) AS missing_source_text_rules;
```

Expected:

```text
0
```

## 12.6 SourceNode resolution coverage

```cypher
MATCH (src:SourceNode)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(target)
RETURN
  count(src) AS total_sources,
  count(target) AS resolved_links,
  count(DISTINCT src) AS distinct_sources;
```

A SourceNode may remain unresolved in the first load as long as it preserves source_text and citation metadata.

## 12.7 Unknown and review signals

```cypher
MATCH (r:Rule)
WHERE r.rule_type = "UNKNOWN" OR r.rule_subtype = "UNKNOWN" OR r.needs_review = true
RETURN count(r) AS review_signal_rules;
```

These are not load blockers. They should be retained as quality signals.

---

## 13. Answer Evidence Pack Requirements by Intent

The loader should preserve enough structure to support intent-specific evidence packs.

## 13.1 obligation_check

Required evidence:

```text
Rule
Requirement or Rule.requirement_text fallback
SourceNode
Article/Paragraph/Item context
EntityType if available
```

## 13.2 safety_measure_lookup

Required evidence:

```text
Rule
Requirement
Threshold if safety criterion is numeric
SourceNode
Article/Item/Subitem context
```

## 13.3 education_time_lookup

Required evidence:

```text
Rule
Threshold
Requirement or education rule text
Annex/LogicalRow if time is table-based
SourceNode
```

## 13.4 education_content_lookup

Required evidence:

```text
Rule
ListItem or LogicalRow/LogicalCell
Annex title
SourceNode
```

## 13.5 inspection_requirement / annex_list_lookup

Required evidence:

```text
Rule
ListItem
Annex
LogicalRow
LogicalCell
SourceNode
```

## 13.6 applicability_check / exception_lookup

Required evidence:

```text
Rule
Exception
Threshold if condition-based
TemporalRule if date/effective-date-based
EntityType if target-based
SourceNode
```

## 13.7 penalty_lookup

Required evidence:

```text
Penalty Rule
Related obligation/prohibition Rule if available
SourceNode
Article context
```

---

## 14. Open Issues

## 14.1 Source node resolution

`edges_rule_source.to_node_id` points to source graph IDs. The loader must decide how to resolve these IDs to actual Document/Annex source nodes.

Recommended approach:
- Always create SourceNode.
- Resolve to actual Article/Paragraph/Item/Subitem/LogicalRow/LogicalCell where ID matching is clear.
- Keep unresolved SourceNode if matching is uncertain.

## 14.2 Source graph CSV schema confirmation

Some source graph file names and edge file roles may overlap.

Examples:

```text
edges_contains.csv
edges_law_hierarchy.csv
edges_law_rel.csv
edges_law_relations.csv
```

The loader should inspect headers and sample rows before loading all source edges.

## 14.3 UNKNOWN and needs_review nodes

UNKNOWN and needs_review nodes should be loaded. They should not be dropped. They are useful quality signals and may support future manual review or fallback evidence.

## 14.4 Requirement/Threshold gaps

Some OBLIGATION rules still lack separate Requirement nodes. Some threshold-like texts still lack Threshold nodes. This is not a load blocker. Answer pack should fall back to Rule.requirement_text, Rule.source_text, or source_context_text.

## 14.5 Reasoning edge strength

Rule-to-rule reasoning edges have different semantic strengths. Relationship types such as RULE_SUPPORTED_BY_ANNEX are stronger than broad REFERS_TO. Traversal and answer generation should respect relationship strength.

## 14.6 Physical source loading

PhysicalTable, PhysicalRow, and PhysicalCell should be second-load targets unless precise table reconstruction is required in the first UI prototype.

---

## 15. Summary

The recommended first Neo4j load should not be limited to reasoning nodes only. It should load the Reasoning Graph together with SourceNode and selected source anchor nodes needed for citation and evidence-pack construction.

Recommended first-load scope:

```text
Rule
Requirement
Threshold
Exception
TemporalRule
EntityType
ListItem
SourceNode
Law
Article
Paragraph
Item
Subitem
Addendum
Annex
LogicalRow
LogicalCell
AnnexNote
```

Recommended second-load scope:

```text
PhysicalTable
PhysicalRow
PhysicalCell
rich document/annex browsing hierarchy
physical-to-logical source traceability edges
```

The graph is structurally ready for a first load with warnings. Remaining warnings are not blockers. They should be treated as quality signals for evidence-pack design, manual review, and later extraction refinement.
