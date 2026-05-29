"""Obligation and safety-measure extractor."""

from __future__ import annotations

import re
from typing import Any

from graph_rag_pipeline.extractors.answer_contract import ExtractedAnswer
from graph_rag_pipeline.extractors.base import BaseExtractor


class ObligationExtractor(BaseExtractor):
    intent = "obligation"

    def run(self) -> dict[str, Any]:
        candidates = self._load_candidates()
        obligations = self._extract_obligations(candidates)
        sources = [self.source(item) for item in candidates[:5]]
        if obligations:
            return ExtractedAnswer(
                handled=True,
                intent=self.context.get("query_intent") or self.intent,
                answer_level="DIRECT_EVIDENCE_FOUND",
                direct_answer="확인된 근거에 따르면 다음 조치 또는 의무를 확인해야 합니다.",
                extracted_items=obligations[:8],
                sources=sources,
                warnings=[],
                next_checks=["각 조치가 현장 작업 조건에 실제로 적용되는지 확인하세요."],
                confidence="MEDIUM",
                block_random_fallback=False,
            ).to_dict()
        return ExtractedAnswer(handled=False, intent=self.context.get("query_intent") or self.intent, failure_reason="no_obligation_sentence").to_dict()

    def _load_candidates(self) -> list[dict[str, Any]]:
        rows = []
        if self.graph and hasattr(self.graph, "find_obligation_sources"):
            try:
                rows = self.graph.find_obligation_sources(self.question, 30)
            except Exception:  # noqa: BLE001
                rows = []
        return rows + self.evidence_candidates

    def _extract_obligations(self, candidates: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        markers = ("하여야 한다", "조치하여야 한다", "확인하여야 한다", "설치하여야 한다", "지급하여야 한다", "실시하여야 한다")
        for item in candidates:
            text = self.text_of(item)
            for sentence in re.split(r"(?<=[.。])|\n", text):
                clean = re.sub(r"\s+", " ", sentence).strip()
                if any(marker in clean for marker in markers) and 12 <= len(clean) <= 220 and clean not in seen:
                    seen.add(clean)
                    result.append(clean)
        return result

