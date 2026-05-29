// audit_1_risk_and_worker
MATCH (r:Rule)
WHERE (r.source_text CONTAINS "위험성평가" OR r.source_context_text CONTAINS "위험성평가" OR r.requirement_text CONTAINS "위험성평가")
  AND (r.source_text CONTAINS "근로자" OR r.source_context_text CONTAINS "근로자" OR r.requirement_text CONTAINS "근로자")
RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
  r.law_name AS law_name, r.article_no AS article_no, r.source_text AS source_text,
  r.source_context_text AS source_context_text, r.requirement_text AS requirement_text
LIMIT 50;

// audit_2_risk_and_notice
MATCH (r:Rule)
WHERE (r.source_text CONTAINS "위험성평가" OR r.source_context_text CONTAINS "위험성평가" OR r.requirement_text CONTAINS "위험성평가")
  AND (r.source_text CONTAINS "알" OR r.source_text CONTAINS "고지" OR r.source_text CONTAINS "주지" OR r.source_text CONTAINS "통보"
   OR r.source_context_text CONTAINS "알" OR r.source_context_text CONTAINS "고지" OR r.source_context_text CONTAINS "주지" OR r.source_context_text CONTAINS "통보"
   OR r.requirement_text CONTAINS "알" OR r.requirement_text CONTAINS "고지" OR r.requirement_text CONTAINS "주지" OR r.requirement_text CONTAINS "통보")
RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
  r.law_name AS law_name, r.article_no AS article_no, r.source_text AS source_text,
  r.source_context_text AS source_context_text, r.requirement_text AS requirement_text
LIMIT 50;

// audit_3_risk_result_worker_anchor
MATCH (r:Rule)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
WHERE (r.source_text CONTAINS "위험성평가" OR r.source_context_text CONTAINS "위험성평가" OR anchor.source_text CONTAINS "위험성평가")
  AND (r.source_text CONTAINS "결과" OR r.source_context_text CONTAINS "결과" OR anchor.source_text CONTAINS "결과")
  AND (r.source_text CONTAINS "근로자" OR r.source_context_text CONTAINS "근로자" OR anchor.source_text CONTAINS "근로자")
RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
  src.source_node_id AS source_node_id, src.source_text AS source_text,
  labels(anchor) AS anchor_labels, anchor.source_text AS anchor_text,
  r.law_name AS law_name, r.article_no AS article_no
LIMIT 50;

// audit_4_source_hierarchy_context
MATCH (r:Rule)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
WHERE r.source_text CONTAINS "위험성평가" OR r.source_context_text CONTAINS "위험성평가"
OPTIONAL MATCH (law:Law)-[:CONTAINS]->(h:Heading)-[:CONTAINS]->(a:Article)
OPTIONAL MATCH (a)-[:CONTAINS]->(p:Paragraph)
OPTIONAL MATCH (p)-[:CONTAINS]->(i:Item)
OPTIONAL MATCH (i)-[:CONTAINS]->(s:Subitem)
WHERE elementId(anchor) = elementId(a) OR elementId(anchor) = elementId(p) OR elementId(anchor) = elementId(i) OR elementId(anchor) = elementId(s)
RETURN r.rule_id AS rule_id, r.source_text AS rule_text, labels(anchor) AS anchor_labels,
  anchor.source_text AS anchor_text, law.law_name AS law_name, h.title AS heading_title,
  a.article_no AS article_no, a.title AS article_title, p.source_text AS paragraph_text,
  i.source_text AS item_text, s.source_text AS subitem_text
LIMIT 50;