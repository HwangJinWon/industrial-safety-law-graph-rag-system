"""Rule-based follow-up question rewriting.

The rewriter is intentionally deterministic. It only carries over context when
the previous user turn is clearly about the same legal task, so an ambiguous
short follow-up does not trigger a fresh unrelated retrieval.
"""

from __future__ import annotations

import re
from typing import Any


def compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def extract_previous_user_questions(chat_history: list[Any], current_question: str) -> list[str]:
    current = str(current_question or "").strip()
    questions: list[str] = []
    for msg in reversed((chat_history or [])[-12:]):
        if isinstance(msg, dict):
            role = msg.get("role") or ""
            text = msg.get("content") or msg.get("text") or msg.get("message") or ""
        else:
            role = getattr(msg, "role", "")
            text = getattr(msg, "content", "") or getattr(msg, "text", "")
        text = str(text or "").strip()
        if role == "user" and text and text != current:
            questions.append(text)
    return questions


def rewrite_followup_question(question: str, chat_history: list[Any] | None) -> dict[str, Any]:
    original = str(question or "").strip()
    previous_questions = extract_previous_user_questions(chat_history or [], original)
    previous = previous_questions[0] if previous_questions else ""
    current = compact(original)
    history_blob = compact(" ".join(previous_questions))

    result = {
        "original_question": original,
        "rewritten_question": original,
        "question_for_retrieval": original,
        "question_context_used": False,
        "question_interpretation": "",
        "previous_question": previous,
        "followup_type": "",
        "block_random_fallback": False,
    }
    if not original or not previous_questions:
        return result

    history_is_education_time = _looks_like_education_time(history_blob)
    if history_is_education_time:
        if _is_all_targets_request(current):
            return _education_rewrite(
                result,
                "사무직, 비사무직, 관리감독자의 정기 안전보건교육 시간은 각각 몇 시간인가?",
                "이전 교육시간 질문을 반영해 사무직, 비사무직, 관리감독자별 정기 안전보건교육 시간을 모두 묻는 것으로 해석했습니다.",
                "education_all_targets_followup",
                block=True,
            )
        if "비사무직" in current:
            return _education_rewrite(
                result,
                "비사무직 근로자의 정기 안전보건교육 시간은 몇 시간인가?",
                "이전 질문을 반영해 비사무직 근로자의 정기 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "target_followup",
                block=True,
            )
        if "사무직" in current:
            return _education_rewrite(
                result,
                "사무직 근로자의 정기 안전보건교육 시간은 몇 시간인가?",
                "이전 질문을 반영해 사무직 근로자의 정기 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "target_followup",
                block=True,
            )
        if "관리감독자" in current:
            return _education_rewrite(
                result,
                "관리감독자의 정기 안전보건교육 시간은 몇 시간인가?",
                "이전 질문을 반영해 관리감독자의 정기 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "target_followup",
                block=True,
            )
        if "특별교육" in current:
            return _education_rewrite(
                result,
                "특별교육의 교육시간은 몇 시간인가?",
                "이전 교육시간 질문을 반영해 특별교육 시간을 묻는 것으로 해석했습니다.",
                "education_type_followup",
                block=True,
            )
        if "채용" in current or "채용시" in current:
            return _education_rewrite(
                result,
                "채용 시 안전보건교육 시간은 몇 시간인가?",
                "이전 교육시간 질문을 반영해 채용 시 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "education_type_followup",
                block=True,
            )
        if _is_clarification_request(current):
            return _education_rewrite(
                result,
                previous,
                "앞선 교육시간 답변이 직접적이지 않아 더 구체적인 답을 요구한 것으로 해석했습니다.",
                "clarification_request",
                block=True,
            )

    if _has_followup_shape(current) and any(token in history_blob for token in ("과태료", "벌칙", "처벌", "벌금")):
        result.update(
            {
                "question_context_used": True,
                "followup_type": "penalty_followup",
                "block_random_fallback": _is_clarification_request(current),
                "question_interpretation": "이전 처벌 관련 질문의 맥락을 이어 묻는 것으로 해석했습니다.",
                "rewritten_question": previous,
                "question_for_retrieval": previous,
            }
        )
    elif _has_followup_shape(current) and any(token in history_blob for token in ("적용제외", "예외", "면제")):
        result.update(
            {
                "question_context_used": True,
                "followup_type": "exception_followup",
                "block_random_fallback": _is_clarification_request(current),
                "question_interpretation": "이전 적용 제외 또는 예외 질문의 맥락을 이어 묻는 것으로 해석했습니다.",
                "rewritten_question": previous,
                "question_for_retrieval": previous,
            }
        )
    return result


def _looks_like_education_time(text: str) -> bool:
    return "교육" in text and any(token in text for token in ("시간", "몇시간", "정기안전보건교육", "안전보건교육"))


def _is_all_targets_request(current: str) -> bool:
    all_markers = (
        "그냥다알려줘",
        "다알려줘",
        "전체알려줘",
        "전부알려줘",
        "그럼다알려줘",
        "한번에알려줘",
        "한번에알려",
        "다말해줘",
        "전체",
        "전부",
        "각각",
        "내가확인하라고",
        "그래서답이뭐야",
        "결론이뭐야",
    )
    return any(marker in current for marker in all_markers)


def _is_clarification_request(current: str) -> bool:
    markers = ("내가확인하라고", "그래서답이뭐야", "결론이뭐야", "다시말해", "뭘해야해", "무슨말이야")
    return any(marker in current for marker in markers)


def _has_followup_shape(current: str) -> bool:
    if len(current) > 35:
        return False
    markers = ("그럼", "그건", "이건", "그경우", "이경우", "그때는", "그러면", "어떤데", "그럼몇")
    return any(marker in current for marker in markers) or _is_clarification_request(current)


def _education_rewrite(
    result: dict[str, Any],
    rewritten: str,
    interpretation: str,
    followup_type: str,
    block: bool = False,
) -> dict[str, Any]:
    result.update(
        {
            "rewritten_question": rewritten,
            "question_for_retrieval": rewritten,
            "question_context_used": True,
            "question_interpretation": interpretation,
            "followup_type": followup_type,
            "block_random_fallback": block,
        }
    )
    return result
