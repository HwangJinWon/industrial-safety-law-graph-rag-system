"""Rule-based query router for domain extractors."""

from __future__ import annotations

import re
from typing import Any


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def classify_query_type(question: str, chat_history: list[Any] | None = None) -> dict[str, Any]:
    q = str(question or "").strip()
    compact = compact_text(q)
    is_followup = _is_followup(compact)

    if compact in {"안녕", "안녕하세요", "하이", "hi", "hello"} or any(
        token in compact for token in ("사용법", "도움말", "뭐할수있어", "예시질문", "질문예시")
    ):
        return {"intent": "smalltalk", "confidence": "HIGH", "reason": "smalltalk/help pattern", "is_followup": False}

    if any(token in compact for token in ("내가확인하라고", "그래서답이뭐야", "결론이뭐야", "다시말해", "뭘해야해")):
        return {
            "intent": "followup_clarification",
            "confidence": "HIGH",
            "reason": "clarification follow-up pattern",
            "is_followup": True,
        }

    if _education_time_query(compact, chat_history):
        return {"intent": "education_time", "confidence": "HIGH", "reason": "education/time terms", "is_followup": is_followup}

    if _case_application_query(compact):
        return {
            "intent": "case_application",
            "confidence": "HIGH",
            "reason": "case application or obligation-penalty chain terms",
            "is_followup": is_followup,
        }

    if any(token in compact for token in ("과태료", "벌칙", "처벌", "벌금", "징역", "미준수")):
        return {"intent": "penalty", "confidence": "HIGH", "reason": "penalty terms", "is_followup": is_followup}

    if any(token in compact for token in ("적용제외", "제외", "예외", "면제", "적용하지")):
        return {"intent": "exception", "confidence": "HIGH", "reason": "exception/applicability terms", "is_followup": is_followup}

    if (
        any(token in compact for token in ("안전검사", "유해위험방지계획서"))
        and any(token in compact for token in ("대상", "어떤", "목록", "종류", "기계"))
    ):
        return {"intent": "list_lookup", "confidence": "HIGH", "reason": "list target terms", "is_followup": is_followup}

    if any(token in compact for token in ("추락", "낙하물", "감전", "밀폐공간", "화기작업", "중량물")) and any(
        token in compact for token in ("조치", "확인", "방지", "해야")
    ):
        return {"intent": "safety_measure", "confidence": "HIGH", "reason": "safety measure terms", "is_followup": is_followup}

    if any(token in compact for token in ("해야하나", "알려야", "고지", "통보", "의무", "무엇을해야", "기준", "조치", "실시")):
        return {"intent": "obligation", "confidence": "MEDIUM", "reason": "obligation terms", "is_followup": is_followup}

    return {"intent": "unknown_or_ambiguous", "confidence": "LOW", "reason": "no strong route", "is_followup": is_followup}


def _education_time_query(compact: str, chat_history: list[Any] | None) -> bool:
    if "교육" in compact and ("시간" in compact or "몇시간" in compact):
        return True
    if any(token in compact for token in ("정기교육", "채용시교육", "특별교육", "관리감독자교육")):
        return True
    if any(token in compact for token in ("사무직", "비사무직", "관리감독자")) and _history_has_education_time(chat_history):
        return True
    return False


def _case_application_query(compact: str) -> bool:
    accident_terms = (
        "추락",
        "붕괴",
        "낙하",
        "화재",
        "폭발",
        "감전",
        "질식",
        "끼임",
        "협착",
        "충돌",
        "전도",
        "크레인",
        "비계",
        "굴착",
        "중량물",
        "중대재해",
        "중대산업재해",
        "사망",
        "상해",
    )
    obligation_terms = ("예방", "안전조치", "보건조치", "조치", "의무", "책임", "법령", "조문", "검토")
    penalty_terms = ("처벌", "벌칙", "벌금", "징역", "양벌", "중대재해처벌법")
    case_terms = ("사건", "판례", "적용", "책임주체", "도급", "경영책임자", "사업주", "근로자", "종사자")
    has_accident = any(term in compact for term in accident_terms)
    has_obligation = any(term in compact for term in obligation_terms)
    has_penalty = any(term in compact for term in penalty_terms)
    has_case = any(term in compact for term in case_terms)
    return (has_accident and has_obligation and (has_case or "법령" in compact or "조문" in compact)) or (
        has_obligation and has_penalty and has_case
    )


def _history_has_education_time(chat_history: list[Any] | None) -> bool:
    for msg in (chat_history or [])[-8:]:
        if isinstance(msg, dict):
            text = str(msg.get("content") or msg.get("text") or "")
        else:
            text = str(getattr(msg, "content", "") or getattr(msg, "text", ""))
        compact = compact_text(text)
        if "교육" in compact and "시간" in compact:
            return True
    return False


def _is_followup(compact: str) -> bool:
    return len(compact) <= 30 and any(
        token in compact
        for token in (
            "그럼",
            "그건",
            "이건",
            "그경우",
            "이경우",
            "어떤데",
            "그러면",
            "비사무직은",
            "사무직은",
            "관리감독자는",
        )
    )
