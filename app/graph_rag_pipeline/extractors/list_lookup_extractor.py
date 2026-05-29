"""List lookup extractor."""

from __future__ import annotations

import re
from typing import Any

from graph_rag_pipeline.extractors.answer_contract import ExtractedAnswer
from graph_rag_pipeline.extractors.base import BaseExtractor


class ListLookupExtractor(BaseExtractor):
    intent = "list_lookup"

    def run(self) -> dict[str, Any]:
        candidates = self._load_candidates()
        items = self._extract_items(candidates)
        sources = [self.source(item) for item in candidates[:5]]
        if items:
            return ExtractedAnswer(
                handled=True,
                intent=self.intent,
                answer_level="LIST_FOUND",
                direct_answer="연결된 별표 또는 목록 근거에서 대상 항목을 확인했습니다.",
                extracted_items=items[:20],
                sources=sources,
                warnings=[],
                next_checks=["실제 장비명, 용량, 설치 상태가 대상 목록과 일치하는지 확인하세요."],
                confidence="HIGH" if len(items) >= 3 else "MEDIUM",
                block_random_fallback=True,
            ).to_dict()
        return ExtractedAnswer(
            handled=True,
            intent=self.intent,
            answer_level="NOT_FOUND",
            direct_answer="목록 근거는 확인했지만 항목 추출이 불완전합니다. 무관한 근거로 대상을 단정하지 않겠습니다.",
            sources=sources,
            warnings=["목록 항목 추출이 충분하지 않습니다."],
            next_checks=["연결된 별표 또는 목록 원문을 확인하세요."],
            confidence="LOW",
            failure_reason="list_items_not_extracted",
            block_random_fallback=True,
        ).to_dict()

    def _load_candidates(self) -> list[dict[str, Any]]:
        rows = []
        if self.graph and hasattr(self.graph, "find_list_sources"):
            try:
                rows = self.graph.find_list_sources(self.question, 50)
            except Exception:  # noqa: BLE001
                rows = []
        return rows + self.evidence_candidates

    def _extract_items(self, candidates: list[dict[str, Any]]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            text = item.get("item_text") or item.get("source_text") or item.get("source_text_preview") or self.text_of(item)
            for piece in re.split(r"\s*(?:,|ㆍ|·|/|\n|[0-9]+\.)\s*", str(text or "")):
                clean = re.sub(r"\s+", " ", piece).strip(" -:;")
                if 2 <= len(clean) <= 40 and clean not in seen:
                    if any(skip in clean for skip in ("법 ", "제", "따라", "경우", "한다")) and len(clean) > 18:
                        continue
                    seen.add(clean)
                    result.append(clean)
        return result

