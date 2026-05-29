// Neo4j evidence traversal verification queries
// Generated: 2026-05-06 22:49:28
// Mode: READ_ONLY_VERIFICATION
// Contains only MATCH/RETURN read queries. No password or row dumps are recorded.

// node_label_counts: Basic graph state
// Purpose: Count nodes by label
MATCH (n)
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;

// relationship_type_counts: Basic graph state
// Purpose: Count relationships by type
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(r) AS count
ORDER BY count DESC;

// rule_source_text_missing: Basic graph state
// Purpose: Count Rule nodes with missing source_text
MATCH (r:Rule)
WHERE r.source_text IS NULL OR trim(r.source_text) = ""
RETURN count(r) AS missing_source_text_rules;

// rule_without_source: Basic graph state
// Purpose: Count Rule nodes without EXTRACTED_FROM
MATCH (r:Rule)
WHERE NOT (r)-[:EXTRACTED_FROM]->(:SourceNode)
RETURN count(r) AS rules_without_source;

// source_node_unresolved: Basic graph state
// Purpose: Count SourceNode nodes without RESOLVES_TO
MATCH (s:SourceNode)
WHERE NOT (s)-[:RESOLVES_TO]->()
RETURN count(s) AS unresolved_source_nodes;

// requirement_evidence: Evidence traversal
// Purpose: Rule to Requirement to source evidence
MATCH (r:Rule)-[:HAS_REQUIREMENT]->(req:Requirement)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(anchor)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  r.law_name AS law_name,
  r.article_no AS article_no,
  r.annex_title AS annex_title,
  r.source_text AS source_text,
  req.required_action AS evidence_text,
  labels(anchor) AS anchor_labels,
  anchor
LIMIT 10;

// threshold_evidence: Evidence traversal
// Purpose: Rule to Threshold to source evidence
MATCH (r:Rule)-[:HAS_THRESHOLD]->(th:Threshold)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(anchor)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  r.law_name AS law_name,
  r.article_no AS article_no,
  r.annex_title AS annex_title,
  r.source_text AS source_text,
  coalesce(th.raw_expression, th.unit) AS evidence_text,
  th.unit AS unit,
  labels(anchor) AS anchor_labels,
  anchor
LIMIT 10;

// exception_evidence: Evidence traversal
// Purpose: Rule to Exception to source evidence
MATCH (r:Rule)-[:HAS_EXCEPTION]->(ex:Exception)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
OPTIONAL MATCH (src)-[:RESOLVES_TO]->(anchor)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  r.law_name AS law_name,
  r.article_no AS article_no,
  r.annex_title AS annex_title,
  r.source_text AS source_text,
  ex.exception_type AS exception_type,
  coalesce(ex.condition_text, ex.effect_text, ex.source_text) AS evidence_text,
  labels(anchor) AS anchor_labels,
  anchor
LIMIT 10;

// entity_evidence: Evidence traversal
// Purpose: Rule to EntityType evidence
MATCH (r:Rule)-[e:RELATED_ENTITY]->(ent:EntityType)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  r.law_name AS law_name,
  r.article_no AS article_no,
  r.source_text AS source_text,
  e.rel AS entity_rel,
  ent.entity_name AS evidence_text,
  ent.entity_category AS entity_category
LIMIT 10;

// list_item_evidence: Evidence traversal
// Purpose: Rule to ListItem evidence
MATCH (r:Rule)-[:HAS_LIST_ITEM]->(li:ListItem)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  r.law_name AS law_name,
  r.article_no AS article_no,
  r.annex_title AS annex_title,
  r.source_text AS source_text,
  li.list_item_type AS list_item_type,
  li.item_text AS evidence_text,
  src.annex_title AS source_annex_title
LIMIT 10;

// unlinked_list_item_source_evidence: Evidence traversal
// Purpose: ListItem source metadata evidence without direct Rule edge
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL
RETURN
  li.list_item_id AS list_item_id,
  li.list_item_type AS list_item_type,
  li.item_text AS evidence_text,
  li.source_node_id AS source_node_id,
  li.law_name AS law_name,
  li.article_no AS article_no,
  li.annex_title AS annex_title,
  li.source_context_text AS source_context_text
LIMIT 20;

// rule_to_rule_reasoning: Evidence traversal
// Purpose: Rule to Rule reasoning expansion
MATCH (r1:Rule)-[e:RELATED_RULE]->(r2:Rule)
RETURN
  r1.rule_id AS from_rule_id,
  r1.rule_type AS from_type,
  r1.rule_subtype AS from_subtype,
  e.rel AS rel,
  r2.rule_id AS to_rule_id,
  r2.rule_type AS to_type,
  r2.rule_subtype AS to_subtype,
  r1.source_text AS from_source_text,
  r2.source_text AS to_source_text
LIMIT 20;

// source_node_resolution_evidence: Evidence traversal
// Purpose: Rule to SourceNode to actual source anchor
MATCH (r:Rule)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  src.source_node_id AS source_node_id,
  src.source_node_type AS source_node_type,
  src.law_name AS law_name,
  src.article_no AS article_no,
  src.annex_title AS annex_title,
  r.source_text AS source_text,
  labels(anchor) AS anchor_labels,
  anchor
LIMIT 20;

// law_heading_article: Source hierarchy
// Purpose: Law to Heading to Article traversal
MATCH (law:Law)-[:CONTAINS]->(h:Heading)-[:CONTAINS]->(a:Article)
RETURN
  law.law_name AS law_name,
  h.text AS heading_title,
  a.article_no_display AS article_no,
  a.title AS article_title
LIMIT 20;

// article_paragraph_item_subitem: Source hierarchy
// Purpose: Article to Paragraph to Item to Subitem traversal
MATCH (a:Article)-[:CONTAINS]->(p:Paragraph)
OPTIONAL MATCH (p)-[:CONTAINS]->(i:Item)
OPTIONAL MATCH (i)-[:CONTAINS]->(s:Subitem)
RETURN
  a.article_no_display AS article_no,
  a.text AS article_text,
  p.text AS paragraph_text,
  i.text AS item_text,
  s.text AS subitem_text
LIMIT 20;

// annex_article: Source hierarchy
// Purpose: Annex to Article traversal
MATCH (ann:Annex)-[:RELATED_TO_ARTICLE]->(a:Article)
RETURN
  ann.annex_id AS annex_id,
  ann.annex_title AS annex_title,
  a.article_no_display AS article_no,
  a.title AS article_title,
  a.law_name AS law_name
LIMIT 20;

// annex_logical_row_cell: Source hierarchy
// Purpose: Annex to LogicalRow to LogicalCell traversal
MATCH (ann:Annex)-[:HAS_LOGICAL_ROW]->(lr:LogicalRow)-[:HAS_LOGICAL_CELL]->(lc:LogicalCell)
RETURN
  ann.annex_id AS annex_id,
  ann.annex_title AS annex_title,
  lr.logical_row_id AS logical_row_id,
  lr.source_text AS row_text,
  lc.logical_cell_id AS logical_cell_id,
  lc.source_text AS cell_text
LIMIT 20;

// annex_note: Source hierarchy
// Purpose: Annex to AnnexNote traversal
MATCH (ann:Annex)-[:HAS_NOTE]->(note:AnnexNote)
RETURN
  ann.annex_id AS annex_id,
  ann.annex_title AS annex_title,
  note.note_id AS note_id,
  note.source_text AS note_text
LIMIT 20;

// education_time_evidence: Intent-specific evidence
// Purpose: Education-related threshold evidence pack
MATCH (r:Rule)-[:HAS_THRESHOLD]->(th:Threshold)
WHERE r.rule_subtype CONTAINS "EDUCATION"
   OR r.source_text CONTAINS "??"
   OR r.annex_title CONTAINS "??"
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  coalesce(th.raw_expression, th.unit) AS threshold,
  th.unit AS unit,
  r.source_text AS source_text,
  src.law_name AS law_name,
  src.article_no AS article_no,
  src.annex_title AS annex_title
LIMIT 20;

// inspection_list_evidence: Intent-specific evidence
// Purpose: Inspection/list ListItem evidence pack
MATCH (li:ListItem)
WHERE li.list_item_type IN ["EQUIPMENT_ITEM", "INSPECTION_ITEM"]
   OR li.item_text CONTAINS "???"
   OR li.source_context_text CONTAINS "????"
RETURN
  li.list_item_id AS list_item_id,
  li.list_item_type AS list_item_type,
  li.item_text AS item_text,
  li.law_name AS law_name,
  li.article_no AS article_no,
  li.annex_title AS annex_title,
  li.source_context_text AS source_context_text
LIMIT 30;

// penalty_evidence: Intent-specific evidence
// Purpose: Penalty rule evidence pack
MATCH (r:Rule)
WHERE r.rule_type = "PENALTY"
   OR r.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE"]
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
OPTIONAL MATCH (r)-[e:RELATED_RULE]->(related:Rule)
RETURN
  r.rule_id AS penalty_rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  r.penalty_text AS penalty_text,
  r.source_text AS source_text,
  src.law_name AS law_name,
  src.article_no AS article_no,
  collect(DISTINCT {rel:e.rel, related_rule_id:related.rule_id, related_type:related.rule_type})[0..5] AS related_rules
LIMIT 20;

// applicability_exception_evidence: Intent-specific evidence
// Purpose: Applicability and exception evidence pack
MATCH (r:Rule)-[:HAS_EXCEPTION]->(ex:Exception)
OPTIONAL MATCH (r)-[:HAS_THRESHOLD]->(th:Threshold)
OPTIONAL MATCH (r)-[:HAS_TEMPORAL_CONDITION]->(tmp:TemporalRule)
OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
RETURN
  r.rule_id AS rule_id,
  r.rule_type AS rule_type,
  r.rule_subtype AS rule_subtype,
  ex.exception_type AS exception_type,
  ex.condition_text AS exception_condition,
  coalesce(th.raw_expression, th.unit) AS threshold,
  tmp.condition_text AS temporal_condition,
  r.source_text AS source_text,
  src.law_name AS law_name,
  src.article_no AS article_no,
  src.annex_title AS annex_title
LIMIT 20;

// unknown_count: Quality signal
// Purpose: UNKNOWN rule_type/subtype count
MATCH (r:Rule)
WHERE r.rule_type = "UNKNOWN" OR r.rule_subtype = "UNKNOWN"
RETURN count(r) AS unknown_rule_count;

// needs_review_count: Quality signal
// Purpose: needs_review count
MATCH (r:Rule)
WHERE r.needs_review = true OR r.needs_review = "true" OR r.needs_review = "TRUE"
RETURN count(r) AS needs_review_count;

// list_items_without_direct_rule_edge: Quality signal
// Purpose: ListItems without direct HAS_LIST_ITEM Rule edge
MATCH (li:ListItem)
WHERE NOT (:Rule)-[:HAS_LIST_ITEM]->(li)
RETURN count(li) AS list_items_without_direct_rule_edge;

// source_node_type_distribution: Quality signal
// Purpose: SourceNode distribution by source_node_type
MATCH (s:SourceNode)
RETURN s.source_node_type AS source_node_type, count(*) AS count
ORDER BY count DESC;

