// ListItem -> SourceNode dry-run/read-only review queries
// Generated: 2026-05-06 23:08:25
// Mode: READ_ONLY_VERIFICATION. No write queries, no password, no row dumps.

// list_item_count
// Purpose: ListItem count
MATCH (li:ListItem) RETURN count(li) AS list_item_count;

// source_node_count
// Purpose: SourceNode count
MATCH (s:SourceNode) RETURN count(s) AS source_node_count;

// source_node_id_coverage
// Purpose: ListItem source_node_id coverage
MATCH (li:ListItem)
RETURN
  count(li) AS total,
  count(CASE WHEN li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> "" THEN 1 END) AS with_source_node_id,
  count(CASE WHEN li.source_node_id IS NULL OR trim(li.source_node_id) = "" THEN 1 END) AS without_source_node_id;

// source_node_matchability
// Purpose: Direct SourceNode matchability
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
OPTIONAL MATCH (s:SourceNode {source_node_id: li.source_node_id})
RETURN
  count(li) AS list_items_with_source_node_id,
  count(s) AS matched_source_nodes,
  count(li) - count(s) AS unmatched_count;

// duplicate_pair_count
// Purpose: Duplicate ListItem/SourceNode pair count
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
WITH li.list_item_id AS list_item_id, li.source_node_id AS source_node_id, count(*) AS c
WHERE c > 1
RETURN count(*) AS duplicate_pair_count;

// list_item_type_distribution
// Purpose: ListItem type distribution
MATCH (li:ListItem) RETURN li.list_item_type AS list_item_type, count(*) AS count ORDER BY count DESC;

// source_node_type_distribution
// Purpose: SourceNode type distribution for direct matches
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
OPTIONAL MATCH (s:SourceNode {source_node_id: li.source_node_id})
RETURN s.source_node_type AS source_node_type, count(*) AS count
ORDER BY count DESC;

// annex_title_top20
// Purpose: annex_title top 20
MATCH (li:ListItem) RETURN li.annex_title AS annex_title, count(*) AS count ORDER BY count DESC LIMIT 20;

// sample_matching_results
// Purpose: Direct SourceNode matching samples
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
MATCH (s:SourceNode {source_node_id: li.source_node_id})
RETURN
  li.list_item_id AS list_item_id,
  li.list_item_type AS list_item_type,
  li.item_text AS item_text,
  li.source_node_id AS source_node_id,
  li.annex_title AS annex_title,
  s.source_node_type AS source_node_type,
  s.source_text AS source_text
LIMIT 30;

// unmatched_samples
// Purpose: Direct SourceNode unmatched samples
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
OPTIONAL MATCH (s:SourceNode {source_node_id: li.source_node_id})
WHERE s IS NULL
RETURN
  li.list_item_id AS list_item_id,
  li.list_item_type AS list_item_type,
  li.item_text AS item_text,
  li.source_node_id AS source_node_id,
  li.annex_title AS annex_title
LIMIT 30;

// source_anchor_match_distribution
// Purpose: Source anchor match distribution for ListItem.source_node_id
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
OPTIONAL MATCH (p:Paragraph {paragraph_id: li.source_node_id})
OPTIONAL MATCH (i:Item {item_id: li.source_node_id})
OPTIONAL MATCH (s:Subitem {subitem_id: li.source_node_id})
OPTIONAL MATCH (lr:LogicalRow {logical_row_id: li.source_node_id})
OPTIONAL MATCH (lc:LogicalCell {logical_cell_id: li.source_node_id})
OPTIONAL MATCH (n:AnnexNote {note_id: li.source_node_id})
RETURN
  count(p) AS paragraph_matches,
  count(i) AS item_matches,
  count(s) AS subitem_matches,
  count(lr) AS logical_row_matches,
  count(lc) AS logical_cell_matches,
  count(n) AS annex_note_matches;

// source_anchor_sample
// Purpose: Source anchor matching samples
MATCH (li:ListItem)
WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ""
OPTIONAL MATCH (p:Paragraph {paragraph_id: li.source_node_id})
OPTIONAL MATCH (i:Item {item_id: li.source_node_id})
OPTIONAL MATCH (s:Subitem {subitem_id: li.source_node_id})
OPTIONAL MATCH (lr:LogicalRow {logical_row_id: li.source_node_id})
OPTIONAL MATCH (lc:LogicalCell {logical_cell_id: li.source_node_id})
OPTIONAL MATCH (n:AnnexNote {note_id: li.source_node_id})
WITH li, coalesce(p, i, s, lr, lc, n) AS anchor,
     CASE
       WHEN p IS NOT NULL THEN 'Paragraph'
       WHEN i IS NOT NULL THEN 'Item'
       WHEN s IS NOT NULL THEN 'Subitem'
       WHEN lr IS NOT NULL THEN 'LogicalRow'
       WHEN lc IS NOT NULL THEN 'LogicalCell'
       WHEN n IS NOT NULL THEN 'AnnexNote'
       ELSE 'UNMATCHED_ANCHOR'
     END AS anchor_label
RETURN
  li.list_item_id AS list_item_id,
  li.list_item_type AS list_item_type,
  li.item_text AS item_text,
  li.source_node_id AS source_node_id,
  li.annex_title AS annex_title,
  anchor_label AS anchor_label,
  coalesce(anchor.source_text, anchor.text, anchor.clean_source_text) AS anchor_text
LIMIT 30;

