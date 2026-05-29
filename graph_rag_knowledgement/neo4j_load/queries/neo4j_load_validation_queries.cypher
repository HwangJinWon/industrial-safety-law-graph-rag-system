// Neo4j load validation queries
// credential note: password value intentionally omitted

// node_label_counts
MATCH (n) RETURN labels(n) AS labels, count(n) AS count ORDER BY labels;

// relationship_type_counts
MATCH ()-[r]->() RETURN type(r) AS relationship_type, count(r) AS count ORDER BY relationship_type;

// rule_count
MATCH (n:Rule) RETURN count(n) AS count;

// requirement_threshold_count
MATCH (req:Requirement) WITH count(req) AS requirement_count MATCH (th:Threshold) RETURN requirement_count, count(th) AS threshold_count;

// rule_missing_source_text
MATCH (r:Rule) WHERE r.source_text IS NULL OR trim(r.source_text) = '' RETURN count(r) AS count;

// rule_without_extracted_from
MATCH (r:Rule) WHERE NOT (r)-[:EXTRACTED_FROM]->(:SourceNode) RETURN count(r) AS count;

// source_node_count
MATCH (s:SourceNode) RETURN count(s) AS count;

// unresolved_source_node_count
MATCH (s:SourceNode) WHERE NOT (s)-[:RESOLVES_TO]->() RETURN count(s) AS count;

// unknown_rule_count
MATCH (r:Rule) WHERE r.rule_type = 'UNKNOWN' OR r.rule_subtype = 'UNKNOWN' RETURN count(r) AS count;

// needs_review_count
MATCH (r:Rule) WHERE r.needs_review = true RETURN count(r) AS count;

// sample_evidence_pack
MATCH (r:Rule)-[:EXTRACTED_FROM]->(s:SourceNode) OPTIONAL MATCH (r)-[:HAS_REQUIREMENT]->(req:Requirement) RETURN r.rule_id AS rule_id, s.source_node_id AS source_node_id, collect(req.requirement_id)[0..5] AS requirements LIMIT 10;
