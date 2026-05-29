"""Penalty extractor that keeps confirmed and candidate penalties separate."""

from __future__ import annotations

from typing import Any

from graph_rag_pipeline.extractors.answer_contract import ExtractedAnswer
from graph_rag_pipeline.extractors.base import BaseExtractor


class PenaltyExtractor(BaseExtractor):
    intent = "penalty"

    def run(self) -> dict[str, Any]:
        candidates = self._load_candidates()
        items = []
        sources = []
        for item in candidates[:10]:
            text = self.text_of(item)
            if any(term in text for term in ("과태료", "벌칙", "벌금", "징역", "처벌")):
                items.append(
                    {
                        "text": self.preview(text, 260),
                        "is_confirmed": item.get("is_confirmed", item.get("rule_type") == "PENALTY"),
                        "match_type": item.get("match_type") or item.get("rule_subtype") or "",
                    }
                )
                sources.append(self.source(item))
        if items:
            return ExtractedAnswer(
                handled=True,
                intent=self.intent,
                answer_level="RULE_FOUND",
                direct_answer="직접 연결된 처벌 근거와 관련 가능성이 있는 후보 처벌 근거를 구분해 확인해야 합니다.",
                extracted_items=items[:8],
                sources=sources[:5],
                warnings=["후보 처벌 근거는 확정 처벌 결론이 아니며 별도 원문 검토가 필요합니다."],
                next_checks=["위반 조항과 벌칙·과태료 조항이 직접 연결되는지 확인하세요."],
                confidence="MEDIUM",
                block_random_fallback=True,
            ).to_dict()
        return ExtractedAnswer(handled=False, intent=self.intent, failure_reason="no_penalty_evidence").to_dict()

    def _load_candidates(self) -> list[dict[str, Any]]:
        rows = []
        if self.graph and hasattr(self.graph, "find_penalty_sources"):
            try:
                rows = self.graph.find_penalty_sources(self.question, 30)
            except Exception:  # noqa: BLE001
                rows = []
        return rows + self.evidence_candidates

