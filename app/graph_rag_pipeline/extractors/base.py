"""Base helpers for rule-based domain extractors."""

from __future__ import annotations

import re
from typing import Any

from graph_rag_pipeline.extractors.answer_contract import source_from_evidence


TIME_RE = re.compile(r"(매반기\s*)?\d+\s*시간\s*이상|\d+\s*시간")


class BaseExtractor:
    intent = "unknown"

    def __init__(self, question: str, graph_query_layer: Any = None, evidence_candidates: list[dict] | None = None, context: dict | None = None):
        self.question = question or ""
        self.graph = graph_query_layer
        self.evidence_candidates = evidence_candidates or []
        self.context = context or {}

    def run(self) -> dict[str, Any]:
        raise NotImplementedError

    def text_of(self, item: dict[str, Any]) -> str:
        source_anchor = item.get("source_anchor") or {}
        parts = [
            item.get("law_name"),
            item.get("article_no"),
            item.get("annex_title"),
            item.get("resolved_annex_title"),
            item.get("source_text"),
            item.get("source_text_preview"),
            item.get("source_context_text"),
            item.get("source_context_text_preview"),
            item.get("item_text"),
            source_anchor.get("source_text") if isinstance(source_anchor, dict) else "",
            source_anchor.get("source_text_preview") if isinstance(source_anchor, dict) else "",
        ]
        if item.get("logical_row"):
            parts.append((item.get("logical_row") or {}).get("source_text"))
        for cell in item.get("logical_cells") or []:
            if isinstance(cell, dict):
                parts.append(cell.get("source_text"))
        return " ".join(str(part or "") for part in parts)

    def preview(self, text: str, limit: int = 220) -> str:
        clean = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(clean) <= limit:
            return clean
        return clean[: limit - 3].rstrip() + "..."

    def source(self, item: dict[str, Any]) -> dict[str, Any]:
        return source_from_evidence(item)

