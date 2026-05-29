"""FastAPI-compatible /ask adapter for the read-only Graph-RAG pipeline."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from graph_rag_pipeline.answer_generator import AnswerGenerator
from graph_rag_pipeline.citation_formatter import CitationFormatter
from graph_rag_pipeline.claim_check import ClaimChecker
from graph_rag_pipeline.evidence_pack_assembler import EvidencePackAssembler
from graph_rag_pipeline.extractors import run_domain_extractor
from graph_rag_pipeline.extractors.followup_rewriter import rewrite_followup_question as rewrite_followup_for_domain
from graph_rag_pipeline.extractors.router import classify_query_type
from graph_rag_pipeline.graph_query_layer import GraphQueryLayer


try:  # FastAPI is optional for direct smoke tests.
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except Exception:  # noqa: BLE001
    FastAPI = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    CORSMiddleware = None  # type: ignore[assignment]


PROJECTS: list[dict[str, Any]] = []
HISTORY: dict[str, list[dict[str, Any]]] = {"checklists": [], "chats": [], "exports": []}


INTENT_KEYWORDS = (
    ("education_time_lookup", ("교육", "시간", "몇 시간", "안전보건교육", "정기교육", "특별교육")),
    ("inspection_requirement", ("안전검사", "대상 기계", "크레인", "리프트", "곤돌라", "프레스", "전단기")),
    ("penalty_lookup", ("과태료", "벌금", "벌칙", "처벌", "부과")),
    ("applicability_check", ("적용 제외", "제외", "예외", "미적용")),
    ("appointment_requirement", ("선임", "자격", "기준", "안전관리자", "보건관리자")),
    ("definition_lookup", ("정의", "뜻", "무엇인가")),
)


def is_smalltalk_or_help_query(question: str) -> bool:
    q = (question or "").strip().lower()
    compact = re.sub(r"\s+", "", q)
    if not compact:
        return False

    greetings = {"안녕", "안녕하세요", "하이", "hi", "hello", "헬로"}
    if compact in greetings:
        return True

    # Keep this intentionally narrow. Legal questions such as "안전관리자는 뭐야?"
    # must still go through the Graph-RAG pipeline.
    help_patterns = (
        "뭐할수있어",
        "무엇을할수있어",
        "사용법",
        "도움말",
        "예시질문",
        "질문예시",
        "어떻게써",
        "어떻게사용",
        "너뭐야",
        "뭐하는시스템",
    )
    return len(compact) <= 30 and any(pattern in compact for pattern in help_patterns)


def build_smalltalk_or_help_response(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": (
            "안녕하세요. 산업안전 법령 QA를 도와드릴 수 있습니다.\n\n"
            "예를 들어 다음과 같이 질문할 수 있습니다.\n"
            "- 정기 안전보건교육은 몇 시간 해야 하나요?\n"
            "- 안전관리자는 어떤 기준으로 선임해야 하나요?\n"
            "- 안전검사 대상 기계에는 어떤 것들이 있나요?\n"
            "- 위험성평가 결과를 근로자에게 알려야 하나요?\n"
            "- 과태료가 부과되는 경우는 무엇인가요?\n\n"
            "일반 대화보다는 산업안전 법령, 체크리스트, 처벌 후보, 적용 제외 여부처럼 근거가 필요한 질문에 적합합니다."
        ),
        "mode": request.get("mode") or "qa",
        "intent": "smalltalk_or_help",
        "status": "OK",
        "evidence_readiness": "NOT_APPLICABLE",
        "answer_policy": "NO_LEGAL_CLAIM",
        "claim_check": {
            "answer_policy": "NO_LEGAL_CLAIM",
            "claim_check_status": "NOT_APPLICABLE",
            "badges": [],
            "issues": [],
        },
        "citations": [],
        "evidence_chips": [],
        "evidences": [],
        "warnings": [],
        "missing_evidence": [],
        "evidence_pack": {
            "primary_evidence_count": 0,
            "supporting_evidence_count": 0,
        },
        "debug": {
            "llm_used": False,
            "llm_polish_mode": False,
            "llm_fallback_reason": "not_applicable",
            "route": "smalltalk_or_help",
            "graph_db": "graph.v1",
        },
    }


def parse_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def normalize_ask_request(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload.get("query") or payload.get("question") or payload.get("message") or ""
    query = str(query).strip()
    options = payload.get("options") or {}
    use_llm_polish = options.get("use_llm_polish", payload.get("use_llm_polish"))
    return {
        "query": query,
        "mode": payload.get("mode") or "qa",
        "intent": payload.get("intent"),
        "chat_history": payload.get("chat_history") or [],
        "options": {
            "include_evidence": options.get("include_evidence", True),
            "include_debug": options.get("include_debug", False),
            "top_k": int(options.get("top_k", 5) or 5),
            "use_llm": bool(options.get("use_llm", False)),
            "use_llm_polish": parse_optional_bool(use_llm_polish),
        },
    }


def classify_intent(query: str) -> str:
    compact = " ".join(str(query or "").split())
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in compact for keyword in keywords):
            if intent == "education_time_lookup" and "교육" not in compact:
                continue
            return intent
    return "obligation_check"


def map_query_intent_to_graph_intent(query_intent: str, question: str) -> str:
    if query_intent == "education_time":
        return "education_time_lookup"
    if query_intent == "list_lookup":
        return "inspection_requirement" if ("안전검사" in question or "기계" in question) else "list_lookup"
    if query_intent == "penalty":
        return "penalty_lookup"
    if query_intent == "case_application":
        return "obligation_penalty_chain"
    if query_intent in {"exception", "applicability"}:
        return "applicability_check"
    if query_intent == "safety_measure":
        return "safety_measure_lookup"
    if query_intent == "obligation":
        return "obligation_check"
    return classify_intent(question)


def is_followup_question(question: str) -> bool:
    q = (question or "").strip()
    compact = q.replace(" ", "")
    followup_markers = [
        "그럼",
        "그건",
        "이건",
        "그경우",
        "그경우는",
        "이경우",
        "비사무직의경우",
        "사무직의경우",
        "관리감독자는",
        "그럼비사무직",
        "비사무직은",
        "사무직은",
        "관리감독자의경우",
        "그때는",
        "그럼몇",
        "어떤데",
        "그러면",
    ]
    if len(compact) <= 30 and any(marker in compact for marker in followup_markers):
        return True
    if len(compact) <= 20 and any(token in compact for token in ("사무직", "비사무직", "관리감독자", "특별교육", "채용시", "채용")):
        return True
    return False


def extract_previous_user_question(chat_history: list[Any], current_question: str) -> str:
    current = str(current_question or "").strip()
    for msg in reversed((chat_history or [])[-8:]):
        if isinstance(msg, dict):
            role = msg.get("role") or ""
            text = msg.get("content") or msg.get("text") or msg.get("message") or ""
        else:
            role = getattr(msg, "role", "")
            text = getattr(msg, "content", "") or getattr(msg, "text", "")
        text = str(text or "").strip()
        if role == "user" and text and text != current:
            return text
    return ""


def rewrite_followup_question(question: str, chat_history: list[Any]) -> dict[str, Any]:
    original = str(question or "").strip()
    previous = extract_previous_user_question(chat_history, original)
    if not original or not previous or not is_followup_question(original):
        return {
            "question_for_retrieval": original,
            "question_context_used": False,
            "question_interpretation": "",
            "previous_question": previous,
        }

    prev_compact = previous.replace(" ", "")
    curr_compact = original.replace(" ", "")
    previous_is_education_time = (
        ("정기안전보건교육" in prev_compact or "안전보건교육" in prev_compact or "교육" in prev_compact)
        and "시간" in prev_compact
    )
    if previous_is_education_time:
        if "비사무직" in curr_compact:
            return {
                "question_for_retrieval": "비사무직 근로자의 정기 안전보건교육 시간은 몇 시간인가?",
                "question_context_used": True,
                "question_interpretation": "이전 질문을 반영해 비사무직 근로자의 정기 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "previous_question": previous,
            }
        if "사무직" in curr_compact:
            return {
                "question_for_retrieval": "사무직 근로자의 정기 안전보건교육 시간은 몇 시간인가?",
                "question_context_used": True,
                "question_interpretation": "이전 질문을 반영해 사무직 근로자의 정기 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "previous_question": previous,
            }
        if "관리감독자" in curr_compact:
            return {
                "question_for_retrieval": "관리감독자의 정기 안전보건교육 시간은 몇 시간인가?",
                "question_context_used": True,
                "question_interpretation": "이전 질문을 반영해 관리감독자의 정기 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "previous_question": previous,
            }
        if "특별교육" in curr_compact:
            return {
                "question_for_retrieval": "특별교육의 교육시간은 몇 시간인가?",
                "question_context_used": True,
                "question_interpretation": "이전 질문을 반영해 특별교육의 교육시간을 묻는 것으로 해석했습니다.",
                "previous_question": previous,
            }
        if "채용" in curr_compact or "채용시" in curr_compact:
            return {
                "question_for_retrieval": "채용 시 안전보건교육 시간은 몇 시간인가?",
                "question_context_used": True,
                "question_interpretation": "이전 질문을 반영해 채용 시 안전보건교육 시간을 묻는 것으로 해석했습니다.",
                "previous_question": previous,
            }

    return {
        "question_for_retrieval": original,
        "question_context_used": False,
        "question_interpretation": "",
        "previous_question": previous,
    }


def dedupe_message_items(items: list[Any] | None) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items or []:
        if isinstance(item, dict):
            key = "|".join(
                str(item.get(field) or "")
                for field in ("warning_type", "missing_type", "message", "label", "description", "reason")
            )
        else:
            key = str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


class AskAdapter:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).resolve()

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = normalize_ask_request(payload)
        if not request["query"]:
            raise ValueError("query/question/message is required")
        if request["mode"] != "qa":
            request["mode"] = "qa"
        if is_smalltalk_or_help_query(request["query"]):
            return build_smalltalk_or_help_response(request)
        rewrite_result = rewrite_followup_for_domain(request["query"], request.get("chat_history") or [])
        question_for_retrieval = rewrite_result["question_for_retrieval"]
        route = classify_query_type(question_for_retrieval, request.get("chat_history") or [])
        query_intent = route.get("intent") or "unknown_or_ambiguous"
        intent = request["intent"] or map_query_intent_to_graph_intent(query_intent, question_for_retrieval)
        top_k = request["options"]["top_k"]
        include_debug = request["options"]["include_debug"]
        use_llm = request["options"]["use_llm"]
        use_llm_polish = request["options"]["use_llm_polish"]

        assembler: EvidencePackAssembler | None = None
        try:
            assembler = EvidencePackAssembler(self.root_dir)
            pack = assembler.assemble(question_for_retrieval, intent, top_k)
            pack["original_query"] = request["query"]
            pack["rewritten_query"] = question_for_retrieval
            pack["question_context_used"] = bool(rewrite_result["question_context_used"])
            pack["question_interpretation"] = rewrite_result["question_interpretation"]
            pack["previous_question"] = rewrite_result["previous_question"]
            pack["query_intent"] = query_intent
            pack["query_route"] = route
            formatter = CitationFormatter()
            citations = formatter.format_pack_citations(pack)
            evidence_chips = formatter.build_evidence_chips(pack, citations)
            legacy_evidences = formatter.build_legacy_evidences(pack, citations)
            claim_check = ClaimChecker().check_pack(pack, citations)
            evidence_candidates = (pack.get("primary_evidence") or []) + (pack.get("supporting_evidence") or [])
            if claim_check.get("answer_policy") == "INDIRECT_ONLY_RESPONSE":
                domain_result = {
                    "handled": False,
                    "intent": query_intent,
                    "answer_level": "INDIRECT_ONLY",
                    "question_interpretation": rewrite_result["question_interpretation"],
                    "direct_answer": "",
                    "extracted_items": [],
                    "sources": [],
                    "warnings": ["직접 근거가 확인되지 않아 도메인 extractor 답변을 생성하지 않았습니다."],
                    "next_checks": [],
                    "confidence": "LOW",
                    "failure_reason": "indirect_only_guardrail",
                    "block_random_fallback": True,
                }
            else:
                domain_result = run_domain_extractor(
                    query_intent,
                    question_for_retrieval,
                    assembler.query_layer,
                    evidence_candidates,
                    {
                        **rewrite_result,
                        "query_route": route,
                        "query_intent": query_intent,
                        "answer_policy": claim_check.get("answer_policy"),
                        "evidence_readiness": pack.get("evidence_readiness"),
                    },
                )
            pack["domain_result"] = domain_result
            generated = AnswerGenerator(
                self.root_dir,
                use_llm=use_llm,
                use_llm_polish=use_llm_polish,
            ).generate(pack, citations, claim_check)

            response = {
                "answer": generated.get("answer") or "",
                "mode": "qa",
                "intent": intent,
                "status": pack.get("status") or "ERROR",
                "evidence_readiness": pack.get("evidence_readiness") or "NOT_READY",
                "answer_policy": claim_check.get("answer_policy"),
                "query_intent": query_intent,
                "original_question": request["query"],
                "rewritten_question": question_for_retrieval,
                "question_context_used": bool(rewrite_result["question_context_used"]),
                "question_interpretation": rewrite_result["question_interpretation"],
                "domain_extractor_used": bool(domain_result.get("handled")),
                "domain_answer_level": domain_result.get("answer_level") or "",
                "domain_confidence": domain_result.get("confidence") or "",
                "domain_failure_reason": domain_result.get("failure_reason") or "",
                "claim_check": claim_check,
                "citations": citations,
                "evidence_chips": evidence_chips,
                "evidences": legacy_evidences,
                "warnings": dedupe_message_items(pack.get("warnings") or []),
                "missing_evidence": dedupe_message_items(pack.get("missing_evidence") or []),
                "debug": {
                    "llm_used": bool(generated.get("llm_used")),
                    "llm_polish_mode": bool(generated.get("llm_polish_mode")),
                    "llm_fallback_reason": generated.get("llm_fallback_reason") or "",
                    "graph_db": "graph.v1",
                    "primary_evidence_count": len(pack.get("primary_evidence") or []),
                    "supporting_evidence_count": len(pack.get("supporting_evidence") or []),
                    "citation_count": len(citations),
                    "legacy_evidence_count": len(legacy_evidences),
                    "query_field_normalized": "query",
                    "original_question": request["query"],
                    "rewritten_question": question_for_retrieval,
                    "question_context_used": bool(rewrite_result["question_context_used"]),
                    "question_interpretation": rewrite_result["question_interpretation"],
                    "query_intent": query_intent,
                    "query_route_reason": route.get("reason"),
                    "domain_extractor_used": bool(domain_result.get("handled")),
                    "domain_answer_level": domain_result.get("answer_level") or "",
                    "domain_confidence": domain_result.get("confidence") or "",
                    "domain_failure_reason": domain_result.get("failure_reason") or "",
                },
            }
            if include_debug:
                response["evidence_pack"] = pack
            else:
                response["evidence_pack"] = {
                    "primary_evidence_count": len(pack.get("primary_evidence") or []),
                    "supporting_evidence_count": len(pack.get("supporting_evidence") or []),
                }
            return response
        finally:
            if assembler is not None:
                assembler.close()


def ask_graph_rag(payload: dict[str, Any], root_dir: str | Path = ".") -> dict[str, Any]:
    return AskAdapter(root_dir).ask(payload)


def build_graph_rag_response_for_query(
    query: str,
    intent: str,
    root_dir: str | Path = ".",
    top_k: int = 3,
    include_debug: bool = False,
) -> dict[str, Any]:
    return ask_graph_rag(
        {
            "query": query,
            "mode": "qa",
            "intent": intent,
            "chat_history": [],
            "options": {
                "include_evidence": True,
                "include_debug": include_debug,
                "top_k": top_k,
                "use_llm": False,
            },
        },
        root_dir,
    )


def checklist_evidence_query(item: dict[str, Any]) -> tuple[str, str]:
    item_id = str(item.get("id") or "")
    mapping = {
        "compat-risk-assessment": ("위험성평가를 실시해야 하나?", "obligation_check"),
        "compat-education-tbm": ("정기 안전보건교육은 몇 시간 해야 하나?", "education_time_lookup"),
        "compat-fall-prevention": ("고소작업 추락 방지 조치에는 무엇이 있나?", "safety_measure_lookup"),
        "compat-falling-object": ("낙하물 방지 조치에는 무엇이 있나?", "safety_measure_lookup"),
        "compat-electric": ("전기작업 감전 방지 조치에는 무엇이 있나?", "safety_measure_lookup"),
        "compat-confined-space": ("밀폐공간 작업 전 산소 및 유해가스 측정 기준은 무엇인가?", "obligation_check"),
    }
    if item_id in mapping:
        return mapping[item_id]
    return ("작업 전 안전보건 조치 의무는 무엇인가?", "obligation_check")


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def evidence_node_id(response: dict[str, Any]) -> str | None:
    chips = response.get("evidence_chips") or []
    legacy = response.get("evidences") or []
    if chips:
        chip = chips[0] or {}
        return first_non_empty(
            chip.get("source_node_id"),
            chip.get("source_anchor_id"),
            chip.get("rule_id"),
            chip.get("list_item_id"),
        )
    if legacy:
        return first_non_empty((legacy[0] or {}).get("node_id"))
    return None


def evidence_law_title(response: dict[str, Any], fallback: str) -> str:
    citations = response.get("citations") or []
    chips = response.get("evidence_chips") or []
    legacy = response.get("evidences") or []
    return first_non_empty(
        (citations[0] or {}).get("citation_text") if citations else None,
        (chips[0] or {}).get("label") if chips else None,
        (legacy[0] or {}).get("title") if legacy else None,
        fallback,
    )


def build_checklist_evidences(response: dict[str, Any]) -> list[dict[str, Any]]:
    legacy = response.get("evidences") or []
    if legacy:
        return legacy[:3]
    citations = response.get("citations") or []
    evidences: list[dict[str, Any]] = []
    for citation in citations[:3]:
        node_id = first_non_empty(
            citation.get("source_node_id"),
            citation.get("source_anchor_id"),
            citation.get("rule_id"),
            citation.get("list_item_id"),
        )
        evidences.append(
            {
                "law_name": citation.get("law_name") or "",
                "title": citation.get("citation_text") or citation.get("annex_title") or "",
                "node_id": node_id,
                "source_text": citation.get("source_text_preview") or "",
                "score": None,
                "type": citation.get("evidence_kind") or "source",
            }
        )
    return evidences


def attach_graph_rag_evidence_to_checklist(
    items: list[dict[str, Any]],
    root_dir: str | Path = ".",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    global_warnings: list[dict[str, Any]] = []
    for item in items:
        item.setdefault("warnings", [])
        query, intent = checklist_evidence_query(item)
        item["evidence_query"] = query
        item["evidence_intent"] = intent
        try:
            response = build_graph_rag_response_for_query(query, intent, root_dir, top_k=3)
            node_id = evidence_node_id(response)
            evidences = build_checklist_evidences(response)
            item["law_node_id"] = node_id
            item["node_id"] = node_id
            item["law_title"] = evidence_law_title(response, item.get("law_title") or "")
            item["evidences"] = evidences
            item["evidence_readiness"] = response.get("evidence_readiness") or "NOT_READY"
            item["answer_policy"] = response.get("answer_policy") or "REFUSE_OR_REQUEST_MORE_EVIDENCE"
            item["penalties"] = []
            item["candidate_penalties"] = []
            item["penalty_warnings"] = []
            if node_id:
                try:
                    detail = read_law_detail(str(node_id), root_dir)
                    item["penalties"] = detail.get("penalties") or []
                    item["candidate_penalties"] = detail.get("candidate_penalties") or []
                    item["penalty_warnings"] = [
                        warning
                        for warning in (detail.get("warnings") or [])
                        if warning.get("warning_type")
                        in {"DIRECT_PENALTY_NOT_FOUND", "CANDIDATE_PENALTY_REQUIRES_REVIEW"}
                    ]
                except Exception as exc:  # noqa: BLE001
                    item["penalty_warnings"].append(
                        {
                            "warning_type": "CHECKLIST_PENALTY_LOOKUP_FAILED",
                            "severity": "medium",
                            "message": f"{type(exc).__name__}: {exc}",
                        }
                    )
            if not node_id:
                item["warnings"].append(
                    {
                        "warning_type": "CHECKLIST_EVIDENCE_NODE_ID_MISSING",
                        "severity": "medium",
                        "message": "이 compatibility 체크리스트 항목에 연결할 수 있는 구체적인 근거 node_id가 확인되지 않았습니다.",
                    }
                )
            if not evidences:
                item["warnings"].append(
                    {
                        "warning_type": "CHECKLIST_EVIDENCE_EMPTY",
                        "severity": "medium",
                        "message": "이 compatibility 체크리스트 항목에 표시할 수 있는 legacy evidences 항목이 없습니다.",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            item["evidence_readiness"] = "NOT_READY"
            item["answer_policy"] = "REFUSE_OR_REQUEST_MORE_EVIDENCE"
            item["warnings"].append(
                {
                    "warning_type": "CHECKLIST_EVIDENCE_LOOKUP_FAILED",
                    "severity": "high",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            global_warnings.append(
                {
                    "warning_type": "CHECKLIST_EVIDENCE_LOOKUP_FAILED",
                    "severity": "high",
                    "item_id": item.get("id"),
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
    return items, global_warnings


def build_compat_checklist(payload: dict[str, Any], root_dir: str | Path = ".") -> dict[str, Any]:
    hazards = [str(v) for v in payload.get("hazards") or []]
    work_types = [str(v) for v in payload.get("work_types") or []]
    safety_state = payload.get("safety_state") or {}
    items: list[dict[str, Any]] = []

    def add_item(item_id: str, title: str, description: str, risk: str, law_title: str):
        if any(item["id"] == item_id for item in items):
            return
        items.append(
            {
                "id": item_id,
                "title": title,
                "text": f"{title} - {description}",
                "description": description,
                "risk": risk,
                "law_title": law_title,
                "law_node_id": None,
                "node_id": None,
                "completed": False,
                "evidences": [],
            }
        )

    add_item(
        "compat-risk-assessment",
        "사전 위험성평가 실시 여부 확인",
        "작업 전 위험요인을 확인하고 필요한 예방조치를 검토했는지 확인합니다.",
        "high",
        "산업안전보건법 관련 위험성평가 근거",
    )
    add_item(
        "compat-education-tbm",
        "작업 전 안전보건교육 및 TBM 실시 여부 확인",
        "작업내용, 위험요인, 보호구, 비상조치를 작업자에게 공유했는지 확인합니다.",
        "mid",
        "산업안전보건법 관련 안전보건교육 근거",
    )

    joined_hazards = " ".join(hazards)
    joined_work_types = " ".join(work_types)
    if "추락" in joined_hazards or "고소" in joined_work_types or "고소작업" in joined_work_types:
        add_item(
            "compat-fall-prevention",
            "추락방지 조치 확인",
            "안전난간, 작업발판, 안전대 등 추락 예방조치가 준비되었는지 확인합니다.",
            "high",
            "산업안전보건법 관련 추락방지 근거",
        )
    if "낙하" in joined_hazards or "낙하물" in joined_hazards:
        add_item(
            "compat-falling-object",
            "낙하물 방지 및 출입통제 확인",
            "낙하물 방지망, 적재 상태, 하부 출입통제 조치를 확인합니다.",
            "high",
            "산업안전보건법 관련 낙하물 방지 근거",
        )
    if "감전" in joined_hazards or "전기" in joined_work_types or "전기작업" in joined_work_types:
        add_item(
            "compat-electric",
            "전기작업 전원차단 및 절연보호구 확인",
            "전원차단, 잠금표시, 절연보호구 등 전기 안전조치를 확인합니다.",
            "high",
            "산업안전보건법 관련 전기작업 안전 근거",
        )
    if "밀폐" in joined_work_types or "밀폐공간" in joined_work_types:
        add_item(
            "compat-confined-space",
            "밀폐공간 산소 및 유해가스 측정 확인",
            "출입 전 산소농도와 유해가스 측정, 감시자 배치, 환기 상태를 확인합니다.",
            "high",
            "산업안전보건법 관련 밀폐공간 작업 근거",
        )

    for index, (label, value) in enumerate(safety_state.items(), start=1):
        if value is False and len(items) < 7:
            add_item(
                f"compat-safety-state-{index}",
                f"미완료 안전조치 확인: {label}",
                "현장 안전상태 입력에서 미완료로 표시된 항목을 우선 점검합니다.",
                "mid",
                "입력 현장조건 기반 compatibility 점검 항목",
            )

    items = items[:7]
    items, evidence_warnings = attach_graph_rag_evidence_to_checklist(items, root_dir)
    answer = (
        "입력한 현장 조건을 기준으로 기본 안전 점검 항목을 생성했습니다. "
        "본 결과는 1차 compatibility checklist이며, 세부 법령 근거 기반 체크리스트는 "
        "후속 Graph-RAG checklist pipeline에서 보강됩니다."
    )
    linked_item_count = sum(1 for item in items if item.get("node_id") or item.get("law_node_id"))
    evidence_item_count = sum(1 for item in items if item.get("evidences"))
    return {
        "answer": answer,
        "items": items,
        "evidences": [evidence for item in items for evidence in (item.get("evidences") or [])][:10],
        "warnings": evidence_warnings,
        "debug": {
            "adapter_type": "compatibility_checklist",
            "llm_used": False,
            "graph_db": "graph.v1",
            "item_count": len(items),
            "linked_item_count": linked_item_count,
            "evidence_item_count": evidence_item_count,
        },
    }


def add_memory_row(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload or {})
    row.setdefault("id", f"{kind}-{len(HISTORY[kind]) + 1}")
    row.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    HISTORY[kind].append(row)
    return row


def add_project(payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload or {})
    row.setdefault("id", f"project-{len(PROJECTS) + 1}")
    row.setdefault("createdAt", datetime.now().date().isoformat())
    PROJECTS.append(row)
    return row


def text_preview(text: str | None, max_len: int = 500) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def normalized_text_key(text: str | None, max_len: int = 120) -> str:
    return " ".join(str(text or "").split())[:max_len]


def friendly_source_label(label: str) -> str:
    labels = {
        "LogicalRow": "별표 표 행 근거",
        "LogicalCell": "별표 표 셀 근거",
        "AnnexNote": "별표 주석 근거",
        "Annex": "별표 근거",
        "Article": "조문 근거",
        "Paragraph": "항 단위 근거",
        "Item": "호 단위 근거",
        "Subitem": "목 단위 근거",
        "SourceNode": "원문 근거",
        "Rule": "규칙 근거",
        "ListItem": "목록 항목 근거",
    }
    return labels.get(label, "근거 위치")


def detail_summary_for(label: str, node: dict[str, Any], source_text: str) -> str:
    article_no = node.get("article_no") or ""
    annex_title = node.get("annex_title") or ""
    if label in {"LogicalRow", "LogicalCell"}:
        if annex_title:
            return f"해당 근거는 {annex_title}의 표 형식 자료 중 관련 행입니다. 체크리스트 항목과 관련된 교육내용, 점검사항 또는 기준을 확인하는 데 사용됩니다."
        return "해당 근거는 별표 또는 표 형식 자료의 관련 행입니다. 체크리스트 항목과 관련된 교육내용, 점검사항 또는 기준을 확인하는 데 사용됩니다."
    if label in {"Article", "Paragraph", "Item", "Subitem", "SourceNode"}:
        if article_no:
            return f"해당 근거는 {article_no}와 연결된 원문으로, 체크리스트 항목과 관련된 의무 또는 기준을 확인하는 데 사용됩니다."
        return "해당 근거는 체크리스트 항목과 관련된 의무 또는 기준을 확인하기 위한 법령 원문입니다."
    if label == "Rule":
        return "해당 규칙은 체크리스트 항목과 관련된 의무, 요건 또는 판단 근거를 구조화한 근거입니다."
    if label == "ListItem":
        return "해당 근거는 목록형 질문이나 점검 항목과 관련된 법령상 목록 항목입니다."
    return "해당 근거는 입력된 현장 조건 또는 체크리스트 항목과 관련된 법령 근거입니다."


def dedupe_dicts_by(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not item:
            continue
        key_parts = [str(item.get(key) or "") for key in keys]
        key = "|".join(key_parts) or repr(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def dedupe_requirements(requirements: list[dict[str, Any]], source_text: str) -> list[dict[str, Any]]:
    source_key = normalized_text_key(source_text)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for requirement in requirements:
        text = requirement.get("preview") or requirement.get("text") or ""
        key = normalized_text_key(text)
        if not key or key == source_key or key in seen:
            continue
        seen.add(key)
        requirement["preview"] = text_preview(text, 200)
        result.append(requirement)
    return result


def node_primary_id(node: dict[str, Any], fallback: str = "") -> str:
    for key in (
        "source_node_id",
        "rule_id",
        "list_item_id",
        "article_id",
        "paragraph_id",
        "item_id",
        "subitem_id",
        "logical_row_id",
        "logical_cell_id",
        "note_id",
        "annex_note_id",
        "annex_id",
    ):
        if node.get(key):
            return str(node.get(key))
    return fallback


def citation_text_for_detail(node: dict[str, Any], label: str, node_id: str) -> str:
    law_name = node.get("law_name") or ""
    article_no = node.get("article_no") or ""
    annex_title = node.get("annex_title") or ""
    if law_name and article_no and annex_title:
        return f"{law_name} {article_no} / {annex_title}"
    if law_name and article_no:
        return f"{law_name} {article_no}"
    if law_name and annex_title:
        return f"{law_name} {annex_title}"
    if annex_title:
        return str(annex_title)
    return friendly_source_label(label)


def fallback_citation(node: dict[str, Any], label: str, node_id: str, source_text: str) -> dict[str, Any]:
    anchor_id = node_primary_id(node, node_id)
    return {
        "citation_text": citation_text_for_detail(node, label, node_id),
        "law_name": node.get("law_name") or "",
        "article_no": node.get("article_no") or "",
        "annex_title": node.get("annex_title") or "",
        "source_anchor_label": label if label not in {"Rule", "SourceNode", "ListItem"} else "",
        "source_anchor_id": anchor_id if label not in {"Rule", "SourceNode", "ListItem"} else "",
        "source_node_id": node.get("source_node_id") or "",
        "rule_id": node.get("rule_id") or "",
        "list_item_id": node.get("list_item_id") or "",
        "source_text_preview": text_preview(source_text, 300),
        "evidence_kind": "rule" if label == "Rule" else "list_item" if label == "ListItem" else "source",
        "confidence": "medium",
    }


def compact_requirement(requirement: dict[str, Any]) -> dict[str, Any]:
    text = (
        requirement.get("required_action")
        or requirement.get("requirement_text")
        or requirement.get("source_text")
        or requirement.get("condition_text")
        or ""
    )
    return {
        "requirement_id": requirement.get("requirement_id") or "",
        "text": text,
        "preview": text_preview(text, 300),
    }


def compact_penalty(rule: dict[str, Any]) -> dict[str, Any]:
    text = rule.get("penalty_text") or rule.get("source_text") or ""
    law_name = rule.get("law_name") or ""
    article_no = rule.get("article_no") or ""
    citation_text = " ".join(str(v) for v in (law_name, article_no) if v)
    return {
        "rule_id": rule.get("rule_id") or "",
        "source_node_id": rule.get("source_node_id") or "",
        "rule_type": rule.get("rule_type") or "",
        "rule_subtype": rule.get("rule_subtype") or "",
        "law_name": law_name,
        "article_no": article_no,
        "title": citation_text,
        "citation_text": citation_text,
        "text": text,
        "preview": text_preview(text, 300),
        "match_type": "DIRECT_LINKED",
        "confidence": "high",
        "is_confirmed": True,
    }


def compact_candidate_penalty(rule: dict[str, Any], match_type: str, confidence: str, match_reason: str) -> dict[str, Any]:
    item = compact_penalty(rule)
    item.update(
        {
            "match_type": match_type,
            "confidence": confidence,
            "match_reason": match_reason,
            "candidate_notice": "이 항목은 조항 번호 참조를 기준으로 찾은 후보 처벌 근거입니다. 직접 연결된 처벌 근거가 아니므로 실제 적용 여부는 원문과 별도 벌칙·과태료 조항을 함께 검토해야 합니다.",
            "is_confirmed": False,
        }
    )
    return item


def candidate_penalties_for_law_article(
    query_layer: GraphQueryLayer,
    law_name: str | None,
    article_no: str | None,
    exclude_rule_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    law_name = str(law_name or "").strip()
    article_no = str(article_no or "").strip()
    if not article_no:
        return []
    rows = query_layer.run_read_query(
        """
        MATCH (p:Rule)
        WHERE (p.rule_type = "PENALTY"
            OR p.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE", "PENALTY_IMPRISONMENT"]
            OR p.penalty_text IS NOT NULL)
          AND ($law_name = "" OR p.law_name = $law_name)
          AND (coalesce(p.penalty_text, "") CONTAINS $article_no OR coalesce(p.source_text, "") CONTAINS $article_no)
        RETURN DISTINCT p AS penalty_rule
        LIMIT 8
        """,
        {"law_name": law_name, "article_no": article_no},
    )
    exclude_rule_ids = exclude_rule_ids or set()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        rule = row.get("penalty_rule") or {}
        if str(rule.get("rule_id") or "") in exclude_rule_ids:
            continue
        candidates.append(
            compact_candidate_penalty(
                rule,
                "ARTICLE_REFERENCE_MATCH",
                "medium",
                f"{article_no} 조항 번호가 벌칙·과태료 규정의 본문에서 언급됩니다.",
            )
        )
    return candidates


def read_law_detail(node_id: str, root_dir: str | Path = ".") -> dict[str, Any]:
    query_layer: GraphQueryLayer | None = None
    try:
        query_layer = GraphQueryLayer(Path(root_dir).resolve())
        lookup_specs = [
            ("SourceNode", "source_node_id"),
            ("Rule", "rule_id"),
            ("ListItem", "list_item_id"),
            ("Article", "article_id"),
            ("Paragraph", "paragraph_id"),
            ("Item", "item_id"),
            ("Subitem", "subitem_id"),
            ("LogicalRow", "logical_row_id"),
            ("LogicalCell", "logical_cell_id"),
            ("AnnexNote", "note_id"),
            ("AnnexNote", "annex_note_id"),
            ("Annex", "annex_id"),
        ]
        rows: list[dict[str, Any]] = []
        for label_name, property_name in lookup_specs:
            rows = query_layer.run_read_query(
                f"""
                MATCH (n:{label_name})
                WHERE toString(n.{property_name}) = $node_id
                RETURN labels(n) AS labels, n AS node
                LIMIT 1
                """,
                {"node_id": str(node_id)},
            )
            if rows:
                break
        if not rows:
            raise KeyError(node_id)
        row = rows[0]
        node = row.get("node") or {}
        labels = row.get("labels") or []
        label = labels[0] if labels else "Node"
        source_text = (
            node.get("source_text")
            or node.get("source_context_text")
            or node.get("requirement_text")
            or node.get("condition_text")
            or node.get("penalty_text")
            or node.get("text")
            or node.get("item_text")
            or ""
        )
        title = (
            node.get("title")
            or node.get("law_name")
            or node.get("annex_title")
            or node.get("rule_id")
            or node.get("list_item_id")
            or str(node_id)
        )
        requirements: list[dict[str, Any]] = []
        penalties: list[dict[str, Any]] = []
        candidate_penalties: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        related_sources: list[dict[str, Any]] = []
        context = {"parent": [], "children": []}

        if label == "Rule" and node.get("rule_id"):
            pack = query_layer.get_rule_evidence_pack_by_rule_id(str(node.get("rule_id")))
            requirements = [compact_requirement(req) for req in pack.get("requirements", [])[:10]]
            for source_node in pack.get("source_nodes", [])[:5]:
                related_sources.append(fallback_citation(source_node, "SourceNode", node_primary_id(source_node), source_node.get("source_text") or ""))
            for anchor in pack.get("source_anchors", [])[:5]:
                anchor_label = (anchor.get("_labels") or ["SourceAnchor"])[0]
                related_sources.append(fallback_citation(anchor, anchor_label, node_primary_id(anchor), anchor.get("source_text") or ""))
            if node.get("penalty_text"):
                penalties.append(compact_penalty(node))
            penalty_rows = query_layer.run_read_query(
                """
                MATCH (:Rule {rule_id: $rule_id})-[rel:RELATED_RULE]-(p:Rule)
                WHERE p.rule_type = "PENALTY"
                   OR p.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE", "PENALTY_IMPRISONMENT"]
                   OR p.penalty_text IS NOT NULL
                RETURN DISTINCT p AS penalty_rule
                LIMIT 5
                """,
                {"rule_id": str(node.get("rule_id"))},
            )
            penalties.extend([compact_penalty(row.get("penalty_rule") or {}) for row in penalty_rows])
            candidate_penalties.extend(
                candidate_penalties_for_law_article(
                    query_layer,
                    node.get("law_name"),
                    node.get("article_no"),
                    {str(item.get("rule_id") or "") for item in penalties},
                )
            )

        elif label == "SourceNode":
            related_rows = query_layer.run_read_query(
                """
                MATCH (src:SourceNode {source_node_id: $node_id})
                OPTIONAL MATCH (src)-[:RESOLVES_TO]->(anchor)
                OPTIONAL MATCH (r:Rule)-[:EXTRACTED_FROM]->(src)
                OPTIONAL MATCH (r)-[:HAS_REQUIREMENT]->(req:Requirement)
                OPTIONAL MATCH (r)-[rel:RELATED_RULE]-(p:Rule)
                WHERE p IS NULL
                   OR p.rule_type = "PENALTY"
                   OR p.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE", "PENALTY_IMPRISONMENT"]
                   OR p.penalty_text IS NOT NULL
                RETURN collect(DISTINCT r)[0..5] AS rules,
                       collect(DISTINCT req)[0..10] AS requirements,
                       collect(DISTINCT p)[0..5] AS penalty_rules,
                       labels(anchor) AS anchor_labels,
                       anchor AS anchor
                LIMIT 1
                """,
                {"node_id": str(node_id)},
            )
            if related_rows:
                rel = related_rows[0]
                requirements = [compact_requirement(req) for req in rel.get("requirements", []) if req][:10]
                penalties = [compact_penalty(rule) for rule in rel.get("penalty_rules", []) if rule][:5]
                for rule in rel.get("rules", [])[:5]:
                    candidate_penalties.extend(
                        candidate_penalties_for_law_article(
                            query_layer,
                            rule.get("law_name") or node.get("law_name"),
                            rule.get("article_no") or node.get("article_no"),
                            {str(item.get("rule_id") or "") for item in penalties},
                        )
                    )
                anchor = rel.get("anchor") or {}
                if anchor:
                    anchor_label = (rel.get("anchor_labels") or ["SourceAnchor"])[0]
                    related_sources.append(fallback_citation(anchor, anchor_label, node_primary_id(anchor), anchor.get("source_text") or ""))
                    if not source_text:
                        source_text = anchor.get("source_text") or ""
                    candidate_penalties.extend(
                        candidate_penalties_for_law_article(
                            query_layer,
                            anchor.get("law_name") or node.get("law_name"),
                            anchor.get("article_no") or node.get("article_no"),
                            {str(item.get("rule_id") or "") for item in penalties},
                        )
                    )

        elif label == "ListItem" and node.get("list_item_id"):
            related_rows = query_layer.run_read_query(
                """
                MATCH (li:ListItem {list_item_id: $list_item_id})
                OPTIONAL MATCH (li)-[:ITEM_RESOLVES_TO]->(anchor)
                RETURN labels(anchor) AS anchor_labels, anchor AS anchor
                LIMIT 1
                """,
                {"list_item_id": str(node.get("list_item_id"))},
            )
            if related_rows:
                anchor = related_rows[0].get("anchor") or {}
                if anchor:
                    anchor_label = (related_rows[0].get("anchor_labels") or ["SourceAnchor"])[0]
                    related_sources.append(fallback_citation(anchor, anchor_label, node_primary_id(anchor), anchor.get("source_text") or ""))
                    if not source_text:
                        source_text = anchor.get("source_text") or ""
                    candidate_penalties.extend(
                        candidate_penalties_for_law_article(
                            query_layer,
                            anchor.get("law_name") or node.get("law_name"),
                            anchor.get("article_no") or node.get("article_no"),
                            {str(item.get("rule_id") or "") for item in penalties},
                        )
                    )

        else:
            related_rows = query_layer.run_read_query(
                """
                MATCH (src:SourceNode)-[:RESOLVES_TO]->(anchor)
                WHERE any(key IN keys(anchor) WHERE toString(anchor[key]) = $node_id)
                OPTIONAL MATCH (r:Rule)-[:EXTRACTED_FROM]->(src)
                OPTIONAL MATCH (r)-[:HAS_REQUIREMENT]->(req:Requirement)
                OPTIONAL MATCH (r)-[rel:RELATED_RULE]-(p:Rule)
                WHERE p IS NULL
                   OR p.rule_type = "PENALTY"
                   OR p.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE", "PENALTY_IMPRISONMENT"]
                   OR p.penalty_text IS NOT NULL
                RETURN collect(DISTINCT src)[0..5] AS source_nodes,
                       collect(DISTINCT r)[0..5] AS rules,
                       collect(DISTINCT req)[0..10] AS requirements,
                       collect(DISTINCT p)[0..5] AS penalty_rules
                LIMIT 1
                """,
                {"node_id": str(node_id)},
            )
            if related_rows:
                rel = related_rows[0]
                requirements = [compact_requirement(req) for req in rel.get("requirements", []) if req][:10]
                penalties = [compact_penalty(rule) for rule in rel.get("penalty_rules", []) if rule][:5]
                for rule in rel.get("rules", [])[:5]:
                    candidate_penalties.extend(
                        candidate_penalties_for_law_article(
                            query_layer,
                            rule.get("law_name") or node.get("law_name"),
                            rule.get("article_no") or node.get("article_no"),
                            {str(item.get("rule_id") or "") for item in penalties},
                        )
                    )
                candidate_penalties.extend(
                    candidate_penalties_for_law_article(
                        query_layer,
                        node.get("law_name"),
                        node.get("article_no"),
                        {str(item.get("rule_id") or "") for item in penalties},
                    )
                )
                for src in rel.get("source_nodes", [])[:5]:
                    related_sources.append(fallback_citation(src, "SourceNode", node_primary_id(src), src.get("source_text") or ""))

        if not penalties and candidate_penalties:
            warnings.append(
                {
                    "warning_type": "DIRECT_PENALTY_NOT_FOUND",
                    "severity": "medium",
                    "message": "현재 연결된 근거에서는 직접 처벌 조항이 확인되지 않았습니다. 다만 관련 가능성이 있는 벌칙·과태료 조항 후보가 있어 별도 검토가 필요합니다.",
                }
            )
            warnings.append(
                {
                    "warning_type": "CANDIDATE_PENALTY_REQUIRES_REVIEW",
                    "severity": "medium",
                    "message": "관련 가능성이 있는 벌칙·과태료 조항 후보가 확인되었습니다. 조항 번호 참조를 기준으로 찾은 후보이므로 실제 적용 여부는 원문과 별도 벌칙·과태료 조항을 함께 검토해야 합니다.",
                }
            )
        elif not penalties:
            warnings.append(
                {
                    "warning_type": "DIRECT_PENALTY_NOT_FOUND",
                    "severity": "medium",
                    "message": "현재 연결된 근거에서는 직접 처벌 조항이 확인되지 않았습니다. 처벌 여부는 별도의 벌칙·과태료 조항과 함께 검토해야 합니다.",
                }
            )

        citations = [fallback_citation(node, label, str(node_id), source_text)]
        for related in related_sources:
            if related.get("citation_text") != citations[0].get("citation_text") or related.get("source_anchor_id"):
                citations.append(related)
        requirements = dedupe_requirements(requirements, source_text)
        penalties = dedupe_dicts_by(penalties, ("rule_id", "article_no", "preview"))
        candidate_penalties = dedupe_dicts_by(candidate_penalties, ("rule_id", "article_no", "preview", "match_type"))
        warnings = dedupe_dicts_by(warnings, ("warning_type", "message"))
        related_sources = dedupe_dicts_by(related_sources, ("citation_text", "source_anchor_id", "source_node_id"))
        citations = dedupe_dicts_by(citations, ("citation_text", "source_anchor_id", "source_node_id", "rule_id", "list_item_id"))
        summary = detail_summary_for(label, node, source_text)
        why_relevant = "이 항목은 입력된 현장 조건과 관련된 안전보건 기준을 확인하기 위해 연결된 근거입니다."
        return {
            "id": str(node_id),
            "node_id": str(node_id),
            "type": label,
            "label": label,
            "title": title,
            "law_name": node.get("law_name") or "",
            "article_no": node.get("article_no") or "",
            "annex_title": node.get("annex_title") or "",
            "source_text": source_text,
            "preview": text_preview(source_text, 500),
            "summary": summary,
            "why_relevant": why_relevant,
            "requirements": requirements,
            "penalties": penalties,
            "candidate_penalties": candidate_penalties[:5],
            "citations": citations[:10],
            "related_sources": related_sources[:10],
            "warnings": warnings,
            "text": source_text,
            "article_text": source_text,
            "context": context,
            "children": context["children"],
            "neighbors": [],
        }
    finally:
        if query_layer is not None:
            query_layer.close()


if FastAPI is not None:
    app = FastAPI(title="Graph-RAG Ask Adapter")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_endpoint() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "graph-rag-ask-adapter",
            "graph_db": "graph.v1",
            "llm_used_default": False,
        }

    @app.post("/ask")
    def ask_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return ask_graph_rag(payload, Path.cwd())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/site-checklist-ui")
    def site_checklist_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return build_compat_checklist(payload, Path.cwd())

    @app.get("/projects")
    def list_projects_endpoint() -> list[dict[str, Any]]:
        return PROJECTS

    @app.post("/projects")
    def create_project_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return add_project(payload)

    @app.get("/history/checklists")
    def list_checklist_history_endpoint() -> list[dict[str, Any]]:
        return HISTORY["checklists"]

    @app.post("/history/checklists")
    def save_checklist_history_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return add_memory_row("checklists", payload)

    @app.get("/history/chats")
    def list_chat_history_endpoint() -> list[dict[str, Any]]:
        return HISTORY["chats"]

    @app.post("/history/chats")
    def save_chat_history_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return add_memory_row("chats", payload)

    @app.get("/history/exports")
    def list_export_history_endpoint() -> list[dict[str, Any]]:
        return HISTORY["exports"]

    @app.post("/history/exports")
    def save_export_history_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return add_memory_row("exports", payload)

    @app.get("/law/{node_id}")
    def law_detail_endpoint(node_id: str) -> dict[str, Any]:
        try:
            return read_law_detail(node_id, Path.cwd())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"source detail not found: {node_id}") from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=404,
                detail=f"source detail unavailable for compatibility lookup: {node_id}",
            ) from exc

else:
    app = None

