"""Education-time extractor for safety-law QA.

This extractor blocks random fallback. If a question is about education time,
the answer must come from education-time evidence such as 시행규칙 제26조 or
별표 4. It must not be filled with unrelated law evidence.
"""

from __future__ import annotations

import re
from typing import Any

from graph_rag_pipeline.extractors.answer_contract import ExtractedAnswer
from graph_rag_pipeline.extractors.base import BaseExtractor


TIME_RE = re.compile(r"(?:매\s*반기|연간)?\s*\d+\s*시간\s*이상|\d+\s*시간")
UNRELATED_TERMS = (
    "중대재해 처벌 등에 관한 법률",
    "건강진단",
    "유해물질",
    "보호구",
    "금지유해물질",
    "교육교재",
    "인력ㆍ시설 및 장비",
    "인력·시설 및 장비",
)


class EducationTimeExtractor(BaseExtractor):
    intent = "education_time"

    def run(self) -> dict[str, Any]:
        education_type = self._education_type()
        candidates = self._load_candidates()
        ranked = sorted(candidates, key=self._score, reverse=True)
        strong = [item for item in ranked if self._score(item) > 0 and not self._is_unrelated(item)][:10]
        sources = [self.source(item) for item in strong[:5]]

        if self._all_targets():
            return self._all_target_answer(education_type, strong, sources)

        target = self._target()
        if not target:
            return ExtractedAnswer(
                handled=True,
                intent=self.intent,
                answer_level="NEED_CLARIFICATION",
                question_interpretation="교육시간 질문이지만 교육대상이 명확하지 않습니다.",
                direct_answer=(
                    "정기 안전보건교육 시간은 교육대상에 따라 다릅니다. 사무직 근로자, 비사무직 근로자, "
                    "관리감독자 중 누구에 대한 교육인지 먼저 구분해야 합니다."
                ),
                sources=sources,
                warnings=["교육대상 조건이 빠져 있어 시간 값을 하나로 단정하지 않습니다."],
                next_checks=[
                    "사무직/비사무직/관리감독자 중 해당 대상을 먼저 구분하세요.",
                    "정기교육인지, 채용 시 교육인지, 특별교육인지 확인하세요.",
                ],
                confidence="MEDIUM",
                block_random_fallback=True,
            ).to_dict()

        item = self._extract_item_for_target(target, education_type, strong)
        answer_level = "VALUE_FOUND" if item["time_value"] else "TABLE_FOUND_VALUE_NOT_EXTRACTED"
        direct_answer = (
            f"{target}의 {education_type} 교육시간은 {item['time_value']}입니다."
            if item["time_value"]
            else (
                f"{target}의 {education_type} 교육시간은 시행규칙 제26조 및 별표 4에서 확인해야 하지만, "
                "현재 시스템이 별표에서 시간 값을 안정적으로 추출하지 못했습니다. "
                "임의의 다른 법령 근거로 답하지 않겠습니다."
            )
        )
        return ExtractedAnswer(
            handled=True,
            intent=self.intent,
            answer_level=answer_level,
            question_interpretation=self.context.get("question_interpretation") or "",
            direct_answer=direct_answer,
            extracted_items=[item],
            sources=sources,
            warnings=[
                "시간 값이 자동 추출되지 않은 항목은 별표 4의 해당 행을 직접 확인해야 합니다."
                if not item["time_value"]
                else "교육시간은 교육대상과 교육구분에 따라 달라질 수 있으므로 별표 4 원문도 함께 확인하세요."
            ],
            next_checks=[
                "실제 대상이 사무직/비사무직/관리감독자 중 어디에 해당하는지 확인하세요.",
                "정기교육 외에 채용 시 교육 또는 특별교육인지 확인하세요.",
                "교육 면제 또는 단축 조건이 있는지 확인하세요.",
            ],
            confidence="HIGH" if item["time_value"] else ("MEDIUM" if sources else "LOW"),
            failure_reason="" if item["time_value"] else "time_value_not_extracted",
            block_random_fallback=True,
        ).to_dict()

    def _all_target_answer(
        self,
        education_type: str,
        strong: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        targets = ["사무직 근로자", "비사무직 근로자", "관리감독자"]
        extracted_items = [self._extract_item_for_target(target, education_type, strong) for target in targets]
        any_value = any(item.get("time_value") for item in extracted_items)
        return ExtractedAnswer(
            handled=True,
            intent=self.intent,
            answer_level="VALUE_FOUND" if any_value else "TABLE_FOUND_VALUE_NOT_EXTRACTED",
            question_interpretation=self.context.get("question_interpretation") or "",
            direct_answer=(
                "정기 안전보건교육 시간은 교육대상별로 다릅니다. 아래는 별표 4 기준으로 확인해야 하는 "
                "대상별 정기교육 시간입니다."
            ),
            extracted_items=extracted_items,
            sources=sources,
            warnings=[
                "시간 값이 자동 추출되지 않은 항목은 별표 4의 해당 행을 직접 확인해야 합니다. "
                "다만, 질문과 무관한 다른 법령 근거로 답하지 않습니다."
            ],
            next_checks=[
                "실제 대상이 사무직/비사무직/관리감독자 중 어디에 해당하는지 확인하세요.",
                "정기교육 외에 채용 시 교육 또는 특별교육인지 확인하세요.",
                "교육 면제 또는 단축 조건이 있는지 확인하세요.",
            ],
            confidence="HIGH" if any_value else ("MEDIUM" if sources else "LOW"),
            failure_reason="" if any_value else "time_value_not_extracted",
            block_random_fallback=True,
        ).to_dict()

    def _extract_item_for_target(
        self,
        target: str,
        education_type: str,
        strong: list[dict[str, Any]],
    ) -> dict[str, Any]:
        time_value = None
        source_title = "안전보건교육 교육과정별 교육시간"
        for item in strong:
            match = self._extract_time(item, target, education_type)
            if match:
                time_value = match
                source_title = (
                    item.get("annex_title")
                    or item.get("resolved_annex_title")
                    or item.get("title")
                    or source_title
                )
                break
        return {
            "target": target,
            "education_type": education_type,
            "time_value": time_value,
            "source_title": source_title,
            "status": "VALUE_FOUND" if time_value else "VALUE_NOT_EXTRACTED",
        }

    def _load_candidates(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.graph and hasattr(self.graph, "find_education_time_sources"):
            try:
                rows = self.graph.find_education_time_sources(self.question, 50)
            except Exception:  # noqa: BLE001
                rows = []
        return rows + self.evidence_candidates

    def _all_targets(self) -> bool:
        compact = self._compact_question()
        if all(term in compact for term in ("사무직", "비사무직", "관리감독자")):
            return True
        return any(term in compact for term in ("다알려줘", "전체", "전부", "각각", "모두"))

    def _target(self) -> str:
        compact = self._compact_question()
        if "비사무직" in compact:
            return "비사무직 근로자"
        if "사무직" in compact:
            return "사무직 근로자"
        if "관리감독자" in compact:
            return "관리감독자"
        if "건설일용" in compact:
            return "건설 일용근로자"
        if "특별교육" in compact:
            return "특별교육 대상 근로자"
        return ""

    def _education_type(self) -> str:
        compact = self._compact_question()
        if "특별교육" in compact:
            return "특별교육"
        if "채용" in compact:
            return "채용 시 안전보건교육"
        if "건설업기초" in compact:
            return "건설업 기초안전보건교육"
        return "정기교육"

    def _score(self, item: dict[str, Any]) -> int:
        text = self.text_of(item)
        compact = re.sub(r"\s+", "", text)
        score = 0
        weighted_terms = (
            ("교육과정별교육시간", 12),
            ("별표4", 12),
            ("교육시간", 8),
            ("교육대상", 6),
            ("교육구분", 6),
            ("제26조", 5),
            ("시간", 4),
            ("매반기", 3),
            ("연간", 3),
        )
        for term, weight in weighted_terms:
            if term in compact:
                score += weight
        for term in ("비사무직", "사무직", "관리감독자", "특별교육", "채용"):
            if term in self.question and term in text:
                score += 6
        if self._is_unrelated(item):
            score -= 20
        return score

    def _is_unrelated(self, item: dict[str, Any]) -> bool:
        text = self.text_of(item)
        compact = re.sub(r"\s+", "", text)
        has_education_time_signal = any(term in compact for term in ("교육시간", "별표4", "제26조", "교육과정별교육시간"))
        return any(term in text for term in UNRELATED_TERMS) and not has_education_time_signal

    def _extract_time(self, item: dict[str, Any], target: str, education_type: str) -> str:
        text = self.text_of(item)
        if not text:
            return ""
        target_core = target.replace(" 근로자", "").replace(" 대상", "")
        windows = self._windows(text, [target, target_core, education_type, "정기교육", "교육시간"])
        for window in windows:
            if target_core and target_core not in window and education_type not in window:
                continue
            match = TIME_RE.search(window)
            if match:
                return re.sub(r"\s+", " ", match.group(0)).strip()
        if any(term in text for term in ("교육시간", "별표 4", "별표4", "교육과정별 교육시간")):
            match = TIME_RE.search(text)
            if match:
                return re.sub(r"\s+", " ", match.group(0)).strip()
        return ""

    def _windows(self, text: str, terms: list[str]) -> list[str]:
        windows: list[str] = []
        for term in terms:
            if not term:
                continue
            idx = text.find(term)
            if idx >= 0:
                windows.append(text[max(0, idx - 350) : idx + 350])
        return windows or [text[:700]]

    def _compact_question(self) -> str:
        return re.sub(r"\s+", "", self.question)
