// ListItem source anchor dry-run queries and future execute templates
// created_at: 2026-05-06 23:15:49
// credential note: password value intentionally omitted
// dry-run only; no write query was executed in this task

// Read-only count: total ListItem
MATCH (li:ListItem) RETURN count(li) AS list_item_count;

// Read-only count: source_node_id coverage
MATCH (li:ListItem)
RETURN count(li) AS total,
  count(CASE WHEN li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> '' THEN 1 END) AS with_source_node_id,
  count(CASE WHEN li.source_node_id IS NULL OR trim(li.source_node_id) = '' THEN 1 END) AS without_source_node_id;

// Read-only plan query shape: match each target label by primary id
// Paragraph planned count
MATCH (li:ListItem) WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ''
MATCH (anchor:Paragraph {paragraph_id: li.source_node_id})
RETURN count(li) AS planned_count;

// Future execute template: ListItem -> Paragraph
// planned row count: 35
UNWIND $rows AS row
MATCH (li:ListItem {list_item_id: row.list_item_id})
MATCH (anchor:Paragraph {paragraph_id: row.target_id})
MERGE (li)-[r:ITEM_RESOLVES_TO {source_node_type: "Paragraph"}]->(anchor)
SET r.source_node_id = row.source_node_id;

// Item planned count
MATCH (li:ListItem) WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ''
MATCH (anchor:Item {item_id: li.source_node_id})
RETURN count(li) AS planned_count;

// Future execute template: ListItem -> Item
// planned row count: 482
UNWIND $rows AS row
MATCH (li:ListItem {list_item_id: row.list_item_id})
MATCH (anchor:Item {item_id: row.target_id})
MERGE (li)-[r:ITEM_RESOLVES_TO {source_node_type: "Item"}]->(anchor)
SET r.source_node_id = row.source_node_id;

// Subitem planned count
MATCH (li:ListItem) WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ''
MATCH (anchor:Subitem {subitem_id: li.source_node_id})
RETURN count(li) AS planned_count;

// Future execute template: ListItem -> Subitem
// planned row count: 49
UNWIND $rows AS row
MATCH (li:ListItem {list_item_id: row.list_item_id})
MATCH (anchor:Subitem {subitem_id: row.target_id})
MERGE (li)-[r:ITEM_RESOLVES_TO {source_node_type: "Subitem"}]->(anchor)
SET r.source_node_id = row.source_node_id;

// LogicalRow planned count
MATCH (li:ListItem) WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ''
MATCH (anchor:LogicalRow {logical_row_id: li.source_node_id})
RETURN count(li) AS planned_count;

// Future execute template: ListItem -> LogicalRow
// planned row count: 1529
UNWIND $rows AS row
MATCH (li:ListItem {list_item_id: row.list_item_id})
MATCH (anchor:LogicalRow {logical_row_id: row.target_id})
MERGE (li)-[r:ITEM_RESOLVES_TO {source_node_type: "LogicalRow"}]->(anchor)
SET r.source_node_id = row.source_node_id;

// LogicalCell planned count
MATCH (li:ListItem) WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ''
MATCH (anchor:LogicalCell {logical_cell_id: li.source_node_id})
RETURN count(li) AS planned_count;

// Future execute template: ListItem -> LogicalCell
// planned row count: 1495
UNWIND $rows AS row
MATCH (li:ListItem {list_item_id: row.list_item_id})
MATCH (anchor:LogicalCell {logical_cell_id: row.target_id})
MERGE (li)-[r:ITEM_RESOLVES_TO {source_node_type: "LogicalCell"}]->(anchor)
SET r.source_node_id = row.source_node_id;

// AnnexNote planned count
MATCH (li:ListItem) WHERE li.source_node_id IS NOT NULL AND trim(li.source_node_id) <> ''
MATCH (anchor:AnnexNote {note_id: li.source_node_id})
RETURN count(li) AS planned_count;

// Future execute template: ListItem -> AnnexNote
// planned row count: 14
UNWIND $rows AS row
MATCH (li:ListItem {list_item_id: row.list_item_id})
MATCH (anchor:AnnexNote {note_id: row.target_id})
MERGE (li)-[r:ITEM_RESOLVES_TO {source_node_type: "AnnexNote"}]->(anchor)
SET r.source_node_id = row.source_node_id;

// Read-only ambiguity check concept
// A source_node_id matching more than one target label is ambiguous and must be excluded from execute.
// ambiguous multi-label match count from dry-run: 0
// unmatched count from dry-run: 0
// duplicate pair count from dry-run: 0
