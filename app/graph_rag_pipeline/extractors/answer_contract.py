"""Shared answer contract for domain-specific extractors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedAnswer:
    handled: bool = False
    intent: str = ""
    answer_level: str = "NOT_FOUND"
    question_interpretation: str = ""
    direct_answer: str = ""
    extracted_items: list[Any] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    next_checks: list[str] = field(default_factory=list)
    confidence: str = "LOW"
    failure_reason: str | None = None
    block_random_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "handled": self.handled,
            "intent": self.intent,
            "answer_level": self.answer_level,
            "question_interpretation": self.question_interpretation,
            "direct_answer": self.direct_answer,
            "extracted_items": self.extracted_items,
            "sources": self.sources,
            "warnings": self.warnings,
            "next_checks": self.next_checks,
            "confidence": self.confidence,
            "failure_reason": self.failure_reason,
            "block_random_fallback": self.block_random_fallback,
        }


def source_from_evidence(item: dict[str, Any]) -> dict[str, Any]:
    source_anchor = item.get("source_anchor") or {}
    node_id = (
        item.get("rule_id")
        or item.get("list_item_id")
        or item.get("node_id")
        or (source_anchor.get("id") if isinstance(source_anchor, dict) else "")
    )
    return {
        "law_name": item.get("law_name") or "",
        "article_no": item.get("article_no") or "",
        "title": item.get("annex_title") or item.get("resolved_annex_title") or item.get("title") or "",
        "source_text": item.get("source_text") or item.get("source_text_preview") or item.get("item_text") or "",
        "node_id": node_id or "",
        "evidence_kind": item.get("evidence_kind") or "",
    }

