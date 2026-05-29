"""Citation and frontend evidence formatting for Graph-RAG evidence packs.

This module is deliberately pure Python formatting logic. It does not query
Neo4j, generate answers, or call an LLM.
"""

from __future__ import annotations

import re
from typing import Any


ANCHOR_ID_KEYS = (
    "source_anchor_id",
    "article_id",
    "paragraph_id",
    "item_id",
    "subitem_id",
    "logical_row_id",
    "logical_cell_id",
    "note_id",
    "annex_note_id",
    "annex_id",
    "addendum_id",
    "heading_id",
    "law_version_id",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


class CitationFormatter:
    def __init__(self):
        pass

    def format_pack_citations(self, evidence_pack: dict) -> list[dict]:
        citations: list[dict] = []
        for candidate in evidence_pack.get("citation_candidates") or []:
            if isinstance(candidate, dict):
                citations.append(self.format_evidence_citation(candidate))
        for item in self._all_evidence_items(evidence_pack):
            citations.append(self.format_evidence_citation(item))
            citations.extend(self._format_nested_citations(item))
        return self.deduplicate_citations([c for c in citations if c])

    def format_evidence_citation(self, evidence_item: dict) -> dict:
        source_anchor = evidence_item.get("source_anchor") or {}
        citation = evidence_item.get("citation") or {}
        law_name = (
            evidence_item.get("law_name")
            or citation.get("law_name")
            or source_anchor.get("law_name")
            or self._first_nested_value(evidence_item.get("source_nodes"), "law_name")
            or self._first_nested_value(evidence_item.get("source_anchors"), "law_name")
        )
        article_no = (
            evidence_item.get("article_no")
            or citation.get("article_no")
            or source_anchor.get("article_no")
            or self._first_nested_value(evidence_item.get("source_nodes"), "article_no")
            or self._first_nested_value(evidence_item.get("source_anchors"), "article_no")
        )
        annex_title = (
            evidence_item.get("annex_title")
            or evidence_item.get("resolved_annex_title")
            or citation.get("annex_title")
            or source_anchor.get("annex_title")
        )
        source_anchor_label = (
            evidence_item.get("source_anchor_label")
            or citation.get("source_anchor_label")
            or source_anchor.get("label")
            or self._first_label(source_anchor.get("_labels"))
        )
        source_anchor_id = (
            evidence_item.get("source_anchor_id")
            or citation.get("source_anchor_id")
            or source_anchor.get("id")
            or self._anchor_id(source_anchor)
        )
        source_node_id = (
            evidence_item.get("source_node_id")
            or citation.get("source_node_id")
            or self._first_nested_value(evidence_item.get("source_nodes"), "source_node_id")
        )
        rule_id = evidence_item.get("rule_id") or citation.get("rule_id")
        list_item_id = evidence_item.get("list_item_id") or citation.get("list_item_id")
        source_text = (
            evidence_item.get("source_text")
            or evidence_item.get("source_text_preview")
            or evidence_item.get("source_context_text")
            or evidence_item.get("source_context_text_preview")
            or evidence_item.get("item_text")
            or source_anchor.get("source_text")
            or source_anchor.get("source_text_preview")
            or citation.get("source_text_preview")
        )
        citation_text = evidence_item.get("citation_text") or citation.get("citation_text")
        if not citation_text:
            citation_text = self.build_citation_text(
                law_name=law_name,
                article_no=article_no,
                paragraph_no=evidence_item.get("paragraph_no") or citation.get("paragraph_no"),
                item_no=evidence_item.get("item_no") or citation.get("item_no"),
                subitem_no=evidence_item.get("subitem_no") or citation.get("subitem_no"),
                annex_title=annex_title,
                source_anchor_label=source_anchor_label,
                source_anchor_id=source_anchor_id,
            )
        return {
            "citation_text": citation_text,
            "law_name": _text(law_name),
            "article_no": self._normalize_article_no(article_no),
            "paragraph_no": _text(evidence_item.get("paragraph_no") or citation.get("paragraph_no")),
            "item_no": _text(evidence_item.get("item_no") or citation.get("item_no")),
            "subitem_no": _text(evidence_item.get("subitem_no") or citation.get("subitem_no")),
            "annex_title": _text(annex_title),
            "source_anchor_label": _text(source_anchor_label),
            "source_anchor_id": _text(source_anchor_id),
            "source_node_id": _text(source_node_id),
            "rule_id": _text(rule_id),
            "list_item_id": _text(list_item_id),
            "source_text_preview": self.make_source_preview(source_text),
            "evidence_kind": evidence_item.get("evidence_kind") or self._infer_evidence_kind(evidence_item),
            "confidence": self._citation_confidence(law_name, article_no, annex_title, source_anchor_id),
        }

    def build_citation_text(
        self,
        law_name: str | None = None,
        article_no: str | None = None,
        paragraph_no: str | None = None,
        item_no: str | None = None,
        subitem_no: str | None = None,
        annex_title: str | None = None,
        source_anchor_label: str | None = None,
        source_anchor_id: str | None = None,
    ) -> str:
        law_name = _text(law_name)
        article_no = self._normalize_article_no(article_no)
        paragraph_no = _text(paragraph_no)
        item_no = _text(item_no)
        subitem_no = _text(subitem_no)
        annex_title = _text(annex_title)
        source_anchor_label = _text(source_anchor_label)
        source_anchor_id = _text(source_anchor_id)
        article_parts = [part for part in (article_no, paragraph_no, item_no, subitem_no) if part]
        article_text = " ".join(article_parts)
        if law_name and article_text and annex_title:
            return f"{law_name} {article_text} / {annex_title}"
        if law_name and article_text:
            return f"{law_name} {article_text}"
        if law_name and annex_title:
            return f"{law_name} {annex_title}"
        if annex_title:
            return annex_title
        if source_anchor_label and source_anchor_id:
            return f"{source_anchor_label}:{source_anchor_id}"
        return "근거 위치 미확인"

    def deduplicate_citations(self, citations: list[dict]) -> list[dict]:
        seen: set[tuple[str, ...]] = set()
        result: list[dict] = []
        for citation in citations:
            key = (
                citation.get("law_name") or "",
                citation.get("article_no") or "",
                citation.get("annex_title") or "",
                citation.get("source_anchor_label") or "",
                citation.get("source_anchor_id") or "",
                citation.get("rule_id") or "",
                citation.get("list_item_id") or "",
                citation.get("citation_text") or "",
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(citation)
        return result

    def make_source_preview(self, text: str | None, max_len: int = 300) -> str:
        if not text:
            return ""
        clean = " ".join(str(text).replace("\r", " ").replace("\n", " ").split())
        return clean[: max_len - 3] + "..." if len(clean) > max_len else clean

    def build_evidence_chips(self, evidence_pack: dict, citations: list[dict] | None = None) -> list[dict]:
        citations = citations if citations is not None else self.format_pack_citations(evidence_pack)
        readiness = evidence_pack.get("evidence_readiness")
        warning_ids = self._warning_related_ids(evidence_pack)
        chips: list[dict] = []
        for citation in citations:
            chip_id = (
                citation.get("rule_id")
                or citation.get("list_item_id")
                or citation.get("source_node_id")
                or citation.get("source_anchor_id")
                or citation.get("citation_text")
            )
            severity = "indirect" if readiness == "INDIRECT_ONLY" else "normal"
            if chip_id in warning_ids:
                severity = "warning"
            chip_type = self._chip_type(citation)
            label = self._chip_label(citation)
            chips.append(
                {
                    "id": chip_id or "",
                    "label": label,
                    "type": chip_type,
                    "law_name": citation.get("law_name") or "",
                    "article_no": citation.get("article_no") or "",
                    "annex_title": citation.get("annex_title") or "",
                    "source_node_id": citation.get("source_node_id") or "",
                    "source_anchor_id": citation.get("source_anchor_id") or "",
                    "source_anchor_label": citation.get("source_anchor_label") or "",
                    "rule_id": citation.get("rule_id") or "",
                    "list_item_id": citation.get("list_item_id") or "",
                    "preview": citation.get("source_text_preview") or "",
                    "severity": severity,
                    "clickable": bool(
                        citation.get("source_node_id")
                        or citation.get("source_anchor_id")
                        or citation.get("rule_id")
                        or citation.get("list_item_id")
                    ),
                }
            )
        return self._dedupe_chips(chips)

    def build_legacy_evidences(self, evidence_pack: dict, citations: list[dict] | None = None) -> list[dict]:
        citations = citations if citations is not None else self.format_pack_citations(evidence_pack)
        evidences: list[dict] = []
        for citation in citations:
            node_id = (
                citation.get("source_node_id")
                or citation.get("source_anchor_id")
                or citation.get("rule_id")
                or citation.get("list_item_id")
                or ""
            )
            title = citation.get("citation_text") or citation.get("annex_title") or citation.get("article_no") or ""
            evidences.append(
                {
                    "law_name": citation.get("law_name") or "",
                    "title": title,
                    "node_id": node_id,
                    "source_text": citation.get("source_text_preview") or "",
                    "score": None,
                    "type": citation.get("evidence_kind") or "unknown",
                }
            )
        return self._dedupe_legacy_evidences(evidences)

    def _all_evidence_items(self, evidence_pack: dict) -> list[dict]:
        items: list[dict] = []
        for key in ("primary_evidence", "supporting_evidence"):
            for item in evidence_pack.get(key) or []:
                if isinstance(item, dict):
                    items.append(item)
        return items

    def _format_nested_citations(self, item: dict) -> list[dict]:
        citations: list[dict] = []
        for source_node in item.get("source_nodes") or []:
            if isinstance(source_node, dict):
                nested = {
                    "evidence_kind": "source",
                    "law_name": item.get("law_name") or source_node.get("law_name"),
                    "article_no": item.get("article_no") or source_node.get("article_no"),
                    "annex_title": item.get("annex_title") or source_node.get("annex_title"),
                    "source_node_id": source_node.get("source_node_id"),
                    "source_text": source_node.get("source_text"),
                }
                citations.append(self.format_evidence_citation(nested))
        for anchor in item.get("source_anchors") or []:
            if isinstance(anchor, dict):
                nested = {
                    "evidence_kind": "source",
                    "law_name": item.get("law_name") or anchor.get("law_name"),
                    "article_no": item.get("article_no") or anchor.get("article_no"),
                    "annex_title": item.get("annex_title") or anchor.get("annex_title"),
                    "source_anchor_label": self._first_label(anchor.get("_labels")) or item.get("source_anchor_label"),
                    "source_anchor_id": self._anchor_id(anchor),
                    "source_text": anchor.get("source_text") or anchor.get("text"),
                }
                citations.append(self.format_evidence_citation(nested))
        for list_item in item.get("list_items") or []:
            if isinstance(list_item, dict):
                nested = {
                    "evidence_kind": "list_item",
                    "law_name": item.get("law_name") or list_item.get("law_name"),
                    "article_no": item.get("article_no") or list_item.get("article_no"),
                    "annex_title": item.get("annex_title") or list_item.get("annex_title"),
                    "list_item_id": list_item.get("list_item_id"),
                    "source_text": list_item.get("item_text") or list_item.get("source_text"),
                }
                citations.append(self.format_evidence_citation(nested))
        return citations

    def _normalize_article_no(self, article_no: Any) -> str:
        value = _text(article_no)
        if re.fullmatch(r"\d+", value):
            return f"제{value}조"
        return value

    def _infer_evidence_kind(self, item: dict) -> str:
        if item.get("evidence_kind"):
            return str(item["evidence_kind"])
        if item.get("rule_id"):
            return "rule"
        if item.get("list_item_id"):
            return "list_item"
        if item.get("threshold_id"):
            return "threshold"
        if item.get("exception_id"):
            return "exception"
        if item.get("source_anchor_id") or item.get("source_anchor_label"):
            return "source"
        return "unknown"

    def _citation_confidence(self, law_name: Any, article_no: Any, annex_title: Any, source_anchor_id: Any) -> str:
        if law_name and (article_no or annex_title):
            return "high"
        if law_name or article_no or annex_title or source_anchor_id:
            return "medium"
        return "low"

    def _first_nested_value(self, values: Any, key: str) -> str:
        if not isinstance(values, list):
            return ""
        for value in values:
            if isinstance(value, dict) and value.get(key):
                return str(value[key])
        return ""

    def _first_label(self, labels: Any) -> str:
        if isinstance(labels, list) and labels:
            return str(labels[0])
        if isinstance(labels, str):
            return labels
        return ""

    def _anchor_id(self, anchor: dict) -> str:
        for key in ANCHOR_ID_KEYS:
            if anchor.get(key):
                return str(anchor[key])
        return ""

    def _warning_related_ids(self, evidence_pack: dict) -> set[str]:
        related: set[str] = set()
        for warning in evidence_pack.get("warnings") or []:
            if isinstance(warning, dict) and warning.get("related_id"):
                related.add(str(warning["related_id"]))
        return related

    def _chip_type(self, citation: dict) -> str:
        kind = citation.get("evidence_kind") or "unknown"
        if kind in {"rule", "list_item", "source", "threshold", "exception"}:
            return kind
        label = citation.get("source_anchor_label") or ""
        if label == "Annex":
            return "annex"
        if label in {"Article", "Paragraph", "Item", "Subitem"}:
            return "article"
        return "unknown"

    def _chip_label(self, citation: dict) -> str:
        if citation.get("citation_text"):
            return str(citation["citation_text"])
        if citation.get("annex_title"):
            return str(citation["annex_title"])
        if citation.get("law_name") and citation.get("article_no"):
            return f"{citation['law_name']} {citation['article_no']}"
        if citation.get("source_anchor_label") and citation.get("source_anchor_id"):
            return f"{citation['source_anchor_label']}:{citation['source_anchor_id']}"
        return "근거 위치 미확인"

    def _dedupe_chips(self, chips: list[dict]) -> list[dict]:
        seen: set[tuple[str, str, str]] = set()
        result: list[dict] = []
        for chip in chips:
            key = (chip.get("id") or "", chip.get("label") or "", chip.get("type") or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(chip)
        return result

    def _dedupe_legacy_evidences(self, evidences: list[dict]) -> list[dict]:
        seen: set[tuple[str, str, str]] = set()
        result: list[dict] = []
        for evidence in evidences:
            key = (evidence.get("law_name") or "", evidence.get("title") or "", evidence.get("node_id") or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(evidence)
        return result
