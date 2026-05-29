"""Optional LLM polishing for deterministic Graph-RAG answers."""

from __future__ import annotations

import json
import re
from typing import Any

from graph_rag_pipeline.llm.openai_client import api_key_available, call_polish_llm
from graph_rag_pipeline.llm.post_check import validate_polished_answer


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b:?\s*"
)

SYSTEM_PROMPT = """너는 산업안전 법령 Graph-RAG 시스템의 답변 편집자다.
너는 법령 판단자가 아니다.
제공된 Graph-RAG 초안과 근거만 사용해 답변을 자연스럽게 다듬어라.
citations에 없는 법령명, 조문번호, 처벌 내용을 만들지 마라.
answer_policy와 evidence_readiness를 반드시 따라라.
INDIRECT_ONLY_RESPONSE이면 직접 의무를 단정하지 마라.
candidate penalty는 확정 처벌로 표현하지 마라.
question_interpretation이 제공되면 답변 첫 부분에 자연스럽게 반영하라.
original_question이 짧거나 애매해도 rewritten_question과 question_interpretation을 기준으로 답변하라.
질문 해석을 확정할 수 없으면 "질문을 다음 의미로 이해했습니다" 수준으로 표현하라.
교육시간 값이 근거에서 명확하지 않으면 임의로 숫자를 만들지 마라.
내부 ID, UUID, source_node_id, rule_id, list_item_id, warning code를 출력하지 마라.

출력 형식은 반드시 다음과 같다.

[결론]
...

[근거]
- ...
- ...

[주의]
...

[다음 확인]
...
"""


def polish_answer(payload: dict[str, Any]) -> dict[str, Any]:
    deterministic_answer = str(payload.get("deterministic_answer") or "")
    if not api_key_available():
        return {
            "answer": deterministic_answer,
            "llm_used": False,
            "llm_fallback_reason": "missing_openai_api_key",
            "post_check_notes": [],
        }

    safe_payload = build_safe_payload(payload)
    user_prompt = json.dumps(safe_payload, ensure_ascii=False, indent=2)
    polished = call_polish_llm(SYSTEM_PROMPT, user_prompt)
    if not polished:
        return {
            "answer": deterministic_answer,
            "llm_used": False,
            "llm_fallback_reason": "llm_call_failed",
            "post_check_notes": [],
        }

    ok, notes = validate_polished_answer(polished, payload)
    if not ok:
        return {
            "answer": deterministic_answer,
            "llm_used": False,
            "llm_fallback_reason": "post_check_failed:" + ",".join(notes[:5]),
            "post_check_notes": notes,
        }

    return {
        "answer": polished.strip(),
        "llm_used": True,
        "llm_fallback_reason": "",
        "post_check_notes": notes,
    }


def build_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": strip_internal_ids(payload.get("question")),
        "original_question": strip_internal_ids(payload.get("original_question")),
        "rewritten_question": strip_internal_ids(payload.get("rewritten_question")),
        "question_interpretation": strip_internal_ids(payload.get("question_interpretation")),
        "answer_policy": payload.get("answer_policy"),
        "evidence_readiness": payload.get("evidence_readiness"),
        "deterministic_answer": strip_internal_ids(payload.get("deterministic_answer")),
        "citations": [safe_citation(citation) for citation in (payload.get("citations") or [])[:8]],
        "evidence_chips": [safe_chip(chip) for chip in (payload.get("evidence_chips") or [])[:8]],
        "warnings": [format_user_warning(warning) for warning in (payload.get("warnings") or [])[:6]],
        "missing_evidence": [safe_missing(item) for item in (payload.get("missing_evidence") or [])[:6]],
        "penalties": [safe_penalty(item, confirmed=True) for item in (payload.get("penalties") or [])[:5]],
        "candidate_penalties": [safe_penalty(item, confirmed=False) for item in (payload.get("candidate_penalties") or [])[:5]],
        "domain_result": safe_domain_result(payload.get("domain_result") or {}),
        "editor_rules": [
            "근거에 없는 법령명, 조문번호, 처벌 내용을 추가하지 않는다.",
            "후보 처벌은 확정 처벌처럼 쓰지 않는다.",
            "간접 근거만 확인된 답변은 직접 의무를 단정하지 않는다.",
        ],
    }


def safe_domain_result(domain_result: Any) -> dict[str, Any]:
    if not isinstance(domain_result, dict):
        return {}
    return {
        "handled": bool(domain_result.get("handled")),
        "intent": strip_internal_ids(domain_result.get("intent")),
        "answer_level": strip_internal_ids(domain_result.get("answer_level")),
        "question_interpretation": strip_internal_ids(domain_result.get("question_interpretation")),
        "direct_answer": strip_internal_ids(domain_result.get("direct_answer")),
        "extracted_items": domain_result.get("extracted_items") or [],
        "warnings": [strip_internal_ids(item) for item in (domain_result.get("warnings") or [])[:5]],
        "next_checks": [strip_internal_ids(item) for item in (domain_result.get("next_checks") or [])[:5]],
        "confidence": strip_internal_ids(domain_result.get("confidence")),
        "block_random_fallback": bool(domain_result.get("block_random_fallback")),
    }


def safe_citation(citation: Any) -> dict[str, Any]:
    if not isinstance(citation, dict):
        return {"citation_text": strip_internal_ids(citation)}
    return {
        "citation_text": strip_internal_ids(citation.get("citation_text")),
        "law_name": strip_internal_ids(citation.get("law_name")),
        "article_no": strip_internal_ids(citation.get("article_no")),
        "annex_title": strip_internal_ids(citation.get("annex_title")),
        "evidence_kind": strip_internal_ids(citation.get("evidence_kind") or citation.get("type")),
        "preview": preview(citation.get("source_text_preview") or citation.get("preview") or citation.get("source_text"), 200),
    }


def safe_chip(chip: Any) -> dict[str, Any]:
    if not isinstance(chip, dict):
        return {"label": strip_internal_ids(chip)}
    return {
        "label": strip_internal_ids(chip.get("label") or chip.get("citation_text")),
        "law_name": strip_internal_ids(chip.get("law_name")),
        "article_no": strip_internal_ids(chip.get("article_no")),
        "annex_title": strip_internal_ids(chip.get("annex_title")),
        "type": strip_internal_ids(chip.get("type") or chip.get("evidence_kind")),
        "preview": preview(chip.get("preview") or chip.get("source_text"), 200),
    }


def safe_penalty(item: Any, confirmed: bool) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "text": preview(item, 200),
            "is_confirmed": confirmed,
            "notice": "직접 연결된 처벌 근거입니다." if confirmed else "후보 처벌 근거이며 확정 결론이 아닙니다.",
        }
    return {
        "law_name": strip_internal_ids(item.get("law_name")),
        "article_no": strip_internal_ids(item.get("article_no")),
        "title": strip_internal_ids(item.get("title") or item.get("citation_text")),
        "preview": preview(item.get("preview") or item.get("text"), 200),
        "match_type": strip_internal_ids(item.get("match_type")),
        "confidence": strip_internal_ids(item.get("confidence")),
        "is_confirmed": confirmed,
        "notice": (
            "직접 연결된 처벌 관련 근거입니다. 실제 적용 여부는 사실관계와 함께 검토해야 합니다."
            if confirmed
            else "조항 번호 참조 등을 기준으로 찾은 후보입니다. 직접 연결된 처벌 결론이 아니며 확정이 아닙니다."
        ),
    }


def safe_missing(item: Any) -> str:
    if isinstance(item, str):
        return strip_internal_ids(item)
    if isinstance(item, dict):
        return strip_internal_ids(
            item.get("label") or item.get("description") or item.get("reason") or item.get("evidence_type")
        )
    return "추가 근거 항목"


def format_user_warning(warning: Any) -> str:
    if isinstance(warning, dict):
        warning_type = str(warning.get("warning_type") or "")
        message = str(warning.get("message") or "")
    else:
        warning_type = ""
        message = str(warning or "")
    source = f"{warning_type} {message}"
    if "THRESHOLD_MISSING" in source:
        return "교육시간 등 수치 기준이 구조화된 값으로 분리되지 않았습니다. 정확한 시간·금액·기간은 연결된 별표 또는 조문 원문에서 확인해야 합니다."
    if "DIRECT_PENALTY_NOT_FOUND" in source:
        return "현재 연결된 근거에서는 직접 처벌 조항이 확인되지 않았습니다."
    if "CANDIDATE_PENALTY_REQUIRES_REVIEW" in source:
        return "관련 가능성이 있는 벌칙·과태료 조항 후보가 있으나, 확정 처벌 결론은 아닙니다."
    return "일부 근거는 적용 조건 또는 예외 확인이 필요합니다."


def strip_internal_ids(value: Any) -> str:
    text = UUID_RE.sub("", str(value or ""))
    text = re.sub(r"warning:\s*[A-Z_]+\s*-\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(?:source_node_id|source_anchor_id|rule_id|list_item_id)\s*[:=]\s*\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(?:THRESHOLD_MISSING|DIRECT_PENALTY_NOT_FOUND|CANDIDATE_PENALTY_REQUIRES_REVIEW)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def preview(value: Any, max_length: int) -> str:
    text = strip_internal_ids(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."
