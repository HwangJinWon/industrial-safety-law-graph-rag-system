// Neo4j load query log
// created_at: 2026-05-06 22:39:32
// phase: validate
// credential note: password value intentionally omitted

// Constraints and indexes
CREATE CONSTRAINT rule_rule_id_unique IF NOT EXISTS FOR (n:Rule) REQUIRE n.rule_id IS UNIQUE;
CREATE CONSTRAINT requirement_requirement_id_unique IF NOT EXISTS FOR (n:Requirement) REQUIRE n.requirement_id IS UNIQUE;
CREATE CONSTRAINT threshold_threshold_id_unique IF NOT EXISTS FOR (n:Threshold) REQUIRE n.threshold_id IS UNIQUE;
CREATE CONSTRAINT exception_exception_id_unique IF NOT EXISTS FOR (n:Exception) REQUIRE n.exception_id IS UNIQUE;
CREATE CONSTRAINT temporalrule_temporal_rule_id_unique IF NOT EXISTS FOR (n:TemporalRule) REQUIRE n.temporal_rule_id IS UNIQUE;
CREATE CONSTRAINT entitytype_entity_type_id_unique IF NOT EXISTS FOR (n:EntityType) REQUIRE n.entity_type_id IS UNIQUE;
CREATE CONSTRAINT listitem_list_item_id_unique IF NOT EXISTS FOR (n:ListItem) REQUIRE n.list_item_id IS UNIQUE;
CREATE CONSTRAINT sourcenode_source_node_id_unique IF NOT EXISTS FOR (n:SourceNode) REQUIRE n.source_node_id IS UNIQUE;
CREATE CONSTRAINT law_law_version_id_unique IF NOT EXISTS FOR (n:Law) REQUIRE n.law_version_id IS UNIQUE;
CREATE CONSTRAINT heading_heading_id_unique IF NOT EXISTS FOR (n:Heading) REQUIRE n.heading_id IS UNIQUE;
CREATE CONSTRAINT article_article_id_unique IF NOT EXISTS FOR (n:Article) REQUIRE n.article_id IS UNIQUE;
CREATE CONSTRAINT paragraph_paragraph_id_unique IF NOT EXISTS FOR (n:Paragraph) REQUIRE n.paragraph_id IS UNIQUE;
CREATE CONSTRAINT item_item_id_unique IF NOT EXISTS FOR (n:Item) REQUIRE n.item_id IS UNIQUE;
CREATE CONSTRAINT subitem_subitem_id_unique IF NOT EXISTS FOR (n:Subitem) REQUIRE n.subitem_id IS UNIQUE;
CREATE CONSTRAINT addendum_addendum_id_unique IF NOT EXISTS FOR (n:Addendum) REQUIRE n.addendum_id IS UNIQUE;
CREATE CONSTRAINT annex_annex_id_unique IF NOT EXISTS FOR (n:Annex) REQUIRE n.annex_id IS UNIQUE;
CREATE CONSTRAINT logicalrow_logical_row_id_unique IF NOT EXISTS FOR (n:LogicalRow) REQUIRE n.logical_row_id IS UNIQUE;
CREATE CONSTRAINT logicalcell_logical_cell_id_unique IF NOT EXISTS FOR (n:LogicalCell) REQUIRE n.logical_cell_id IS UNIQUE;
CREATE CONSTRAINT annexnote_note_id_unique IF NOT EXISTS FOR (n:AnnexNote) REQUIRE n.note_id IS UNIQUE;
CREATE INDEX rule_law_name_index IF NOT EXISTS FOR (n:Rule) ON (n.law_name);
CREATE INDEX rule_article_no_index IF NOT EXISTS FOR (n:Rule) ON (n.article_no);
CREATE INDEX rule_rule_type_index IF NOT EXISTS FOR (n:Rule) ON (n.rule_type);
CREATE INDEX rule_rule_subtype_index IF NOT EXISTS FOR (n:Rule) ON (n.rule_subtype);
CREATE INDEX rule_annex_title_index IF NOT EXISTS FOR (n:Rule) ON (n.annex_title);
CREATE INDEX listitem_item_text_index IF NOT EXISTS FOR (n:ListItem) ON (n.item_text);
CREATE INDEX listitem_list_item_type_index IF NOT EXISTS FOR (n:ListItem) ON (n.list_item_type);
CREATE INDEX sourcenode_law_name_index IF NOT EXISTS FOR (n:SourceNode) ON (n.law_name);
CREATE INDEX sourcenode_article_no_index IF NOT EXISTS FOR (n:SourceNode) ON (n.article_no);
CREATE INDEX sourcenode_annex_title_index IF NOT EXISTS FOR (n:SourceNode) ON (n.annex_title);

// source CSV: reasoning_graph/nodes/nodes_rule.csv
// planned row count: 8858
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Rule {rule_id: row.rule_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_requirement.csv
// planned row count: 3639
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Requirement {requirement_id: row.requirement_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_threshold.csv
// planned row count: 1782
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Threshold {threshold_id: row.threshold_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_exception.csv
// planned row count: 647
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Exception {exception_id: row.exception_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_temporal_rule.csv
// planned row count: 227
// executed row count: 0
UNWIND $rows AS row
MERGE (n:TemporalRule {temporal_rule_id: row.temporal_rule_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_entity_type.csv
// planned row count: 586
// executed row count: 0
UNWIND $rows AS row
MERGE (n:EntityType {entity_type_id: row.entity_type_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_list_item.csv
// planned row count: 3604
// executed row count: 0
UNWIND $rows AS row
MERGE (n:ListItem {list_item_id: row.list_item_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_law.csv
// planned row count: 6
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Law {law_version_id: row.law_version_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_heading.csv
// planned row count: 194
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Heading {heading_id: row.heading_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_article.csv
// planned row count: 1270
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Article {article_id: row.article_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_paragraph.csv
// planned row count: 2567
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Paragraph {paragraph_id: row.paragraph_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_item.csv
// planned row count: 2957
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Item {item_id: row.item_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_subitem.csv
// planned row count: 513
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Subitem {subitem_id: row.subitem_id})
SET n += row;

// source CSV: document_graph/nodes/nodes_addendum.csv
// planned row count: 81
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Addendum {addendum_id: row.addendum_id})
SET n += row;

// source CSV: document_graph/source_annex/annexes.csv
// planned row count: 201
// executed row count: 0
UNWIND $rows AS row
MERGE (n:Annex {annex_id: row.annex_id})
SET n += row;

// source CSV: document_graph/source_annex/annex_logical_rows.csv
// planned row count: 7972
// executed row count: 0
UNWIND $rows AS row
MERGE (n:LogicalRow {logical_row_id: row.logical_row_id})
SET n += row;

// source CSV: document_graph/source_annex/annex_logical_cells.csv
// planned row count: 16741
// executed row count: 0
UNWIND $rows AS row
MERGE (n:LogicalCell {logical_cell_id: row.logical_cell_id})
SET n += row;

// source CSV: document_graph/source_annex/annex_notes.csv
// planned row count: 119
// executed row count: 0
UNWIND $rows AS row
MERGE (n:AnnexNote {note_id: row.note_id})
SET n += row;

// source CSV: reasoning_graph/nodes/nodes_rule.csv
// planned row count: 0
// executed row count: 0
UNWIND $rows AS row
MERGE (n:SourceNode {source_node_id: row.source_node_id})
SET n += row;

// source CSV: reasoning_graph/edges/edges_rule_requirement.csv
// planned row count: 3639
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:Requirement {requirement_id: row.to_requirement_id})
MERGE (a)-[r:HAS_REQUIREMENT]->(b)
SET r += {rel: row.rel};

// source CSV: reasoning_graph/edges/edges_rule_threshold.csv
// planned row count: 1782
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:Threshold {threshold_id: row.to_threshold_id})
MERGE (a)-[r:HAS_THRESHOLD]->(b)
SET r += {rel: row.rel, threshold_role: row.threshold_role};

// source CSV: reasoning_graph/edges/edges_rule_exception.csv
// planned row count: 647
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:Exception {exception_id: row.to_exception_id})
MERGE (a)-[r:HAS_EXCEPTION]->(b)
SET r += {rel: row.rel};

// source CSV: reasoning_graph/edges/edges_rule_temporal.csv
// planned row count: 279
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:TemporalRule {temporal_rule_id: row.to_temporal_id})
MERGE (a)-[r:HAS_TEMPORAL_CONDITION]->(b)
SET r += {rel: row.rel};

// source CSV: reasoning_graph/edges/edges_rule_entity.csv
// planned row count: 8973
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:EntityType {entity_type_id: row.to_entity_type_id})
MERGE (a)-[r:RELATED_ENTITY]->(b)
SET r += {rel: row.rel};

// source CSV: reasoning_graph/edges/edges_rule_list_item.csv
// planned row count: 3604
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:ListItem {list_item_id: row.to_list_item_id})
MERGE (a)-[r:HAS_LIST_ITEM]->(b)
SET r += {rel: row.rel, needs_review: row.needs_review};

// source CSV: reasoning_graph/edges/edges_rule_reasoning.csv
// planned row count: 5907
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:Rule {rule_id: row.to_rule_id})
MERGE (a)-[r:RELATED_RULE]->(b)
SET r += {rel: row.rel, reasoning_note: row.reasoning_note, source_edge_id: row.source_edge_id};

// source CSV: reasoning_graph/edges/edges_rule_source.csv
// planned row count: 8858
// executed row count: 0
UNWIND $rows AS row
MATCH (a:Rule {rule_id: row.from_rule_id})
MATCH (b:SourceNode {source_node_id: row.to_node_id})
MERGE (a)-[r:EXTRACTED_FROM]->(b)
SET r += {rel: row.rel, to_node_type: row.to_node_type};

// SourceNode RESOLVES_TO template: SourceNode -> Article
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 0
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:Article {article_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> Paragraph
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 2090
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:Paragraph {paragraph_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> Item
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 2099
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:Item {item_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> Subitem
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 375
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:Subitem {subitem_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> Addendum
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 0
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:Addendum {addendum_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> Annex
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 0
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:Annex {annex_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> LogicalRow
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 2337
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:LogicalRow {logical_row_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> LogicalCell
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 1859
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:LogicalCell {logical_cell_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// SourceNode RESOLVES_TO template: SourceNode -> AnnexNote
// source: SourceNode.source_node_id matched to source anchor primary id
// planned row count: 98
// executed row count: 0
UNWIND $rows AS row
MATCH (s:SourceNode {source_node_id: row.source_node_id})
MATCH (a:AnnexNote {note_id: row.target_id})
MERGE (s)-[:RESOLVES_TO]->(a);

// Source hierarchy template: Annex -> LogicalRow
// source CSV: document_graph/source_annex/annex_logical_rows.csv
UNWIND $rows AS row
MATCH (a:Annex {annex_id: row.annex_id})
MATCH (b:LogicalRow {logical_row_id: row.logical_row_id})
MERGE (a)-[:HAS_LOGICAL_ROW]->(b);

// Source hierarchy template: LogicalRow -> LogicalCell
// source CSV: document_graph/source_annex/annex_logical_cells.csv
UNWIND $rows AS row
MATCH (a:LogicalRow {logical_row_id: row.logical_row_id})
MATCH (b:LogicalCell {logical_cell_id: row.logical_cell_id})
MERGE (a)-[:HAS_LOGICAL_CELL]->(b);
