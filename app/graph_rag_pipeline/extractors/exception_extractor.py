"""Exception/applicability extractor."""

from __future__ import annotations

import re
from typing import Any

from graph_rag_pipeline.extractors.answer_contract import ExtractedAnswer
from graph_rag_pipeline.extractors.base import BaseExtractor


class ExceptionExtractor(BaseExtractor):
    intent = "exception"

    def run(self) -> dict[str, Any]:
        candidates = self._load_candidates()
        items = self._extract_exceptions(candidates)
        sources = [self.source(item) for item in candidates[:5]]
        if items:
            return ExtractedAnswer(
                handled=True,
                intent=self.intent,
                answer_level="RULE_FOUND",
                direct_answer="적용 제외 또는 예외 가능성이 있는 조건은 다음과 같습니다.",
                extracted_items=items[:8],
                sources=sources,
                warnings=["예외는 조건부로만 적용될 수 있으므로 현장 조건과 원문을 함께 확인해야 합니다."],
                next_checks=["예외 조건의 대상, 기간, 업종, 규모 요건을 확인하세요."],
                confidence="MEDIUM",
                block_random_fallback=True,
            ).to_dict()
        return ExtractedAnswer(handled=False, intent=self.intent, failure_reason="no_exception_sentence").to_dict()

    def _load_candidates(self) -> list[dict[str, Any]]:
        rows = []
        if self.graph and hasattr(self.graph, "find_exception_sources"):
            try:
                rows = self.graph.find_exception_sources(self.question, 30)
            except Exception:  # noqa: BLE001
                rows = []
        return rows + self.evidence_candidates

    def _extract_exceptions(self, candidates: list[dict[str, Any]]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            text = self.text_of(item)
            for sentence in re.split(r"(?<=[.。])|\n", text):
                clean = re.sub(r"\s+", " ", sentence).strip()
                if any(term in clean for term in ("다만", "제외", "적용하지 아니", "면제", "예외")) and 8 <= len(clean) <= 220:
                    if clean not in seen:
                        seen.add(clean)
                        result.append(clean)
        return result

