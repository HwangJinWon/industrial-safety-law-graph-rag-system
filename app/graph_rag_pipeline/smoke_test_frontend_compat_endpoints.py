#!/usr/bin/env python
"""Smoke test frontend compatibility endpoints on ask_adapter FastAPI app."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from graph_rag_pipeline.ask_adapter import app  # noqa: E402


ASK_QUERIES = [
    "정기 안전보건교육은 몇 시간 해야 하나?",
    "위험성평가 결과를 근로자에게 알려야 하나?",
    "과태료가 부과되는 경우는 무엇인가?",
]

BROKEN_PATTERNS = [
    "援",
    "媛",
    "꾪",
    "蹂",
    "덉",
    "쟾",
    "룊",
    "쇨",
    "낅",
    "?꾪",
    "?곗",
    "?덉",
    "?묒",
]

RISK_DIRECT_ASSERTIONS = [
    "반드시 알려야 합니다",
    "고지해야 합니다",
    "알려야 합니다",
]

RISK_LIMITING_PHRASES = [
    "직접 근거",
    "간접 근거",
    "제한",
]

UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def has_broken_text(value: Any) -> bool:
    text = str(value or "")
    return any(pattern in text for pattern in BROKEN_PATTERNS)


def add_broken_text_errors(prefix: str, obj: dict[str, Any], fields: tuple[str, ...], errors: list[str]) -> None:
    for field in fields:
        value = obj.get(field)
        if isinstance(value, str) and has_broken_text(value):
            errors.append(f"{prefix}: broken Korean text in {field}")


def warning_key(warning: dict[str, Any]) -> tuple[str, str]:
    return (str(warning.get("warning_type") or ""), str(warning.get("message") or ""))


def validate_ask_schema(name: str, ask: dict[str, Any] | None, errors: list[str]) -> None:
    ask = ask or {}
    for field in (
        "answer",
        "evidences",
        "citations",
        "evidence_chips",
        "claim_check",
        "answer_policy",
        "evidence_readiness",
        "warnings",
        "missing_evidence",
    ):
        if field not in ask:
            errors.append(f"{name}: missing /ask field {field}")
    if not isinstance(ask.get("claim_check"), dict):
        errors.append(f"{name}: claim_check must be a dict")
    for list_field in ("evidences", "citations", "evidence_chips", "warnings", "missing_evidence"):
        if list_field in ask and not isinstance(ask.get(list_field), list):
            errors.append(f"{name}: {list_field} must be a list")
    claim_policy = (ask.get("claim_check") or {}).get("answer_policy")
    if claim_policy and ask.get("answer_policy") and claim_policy != ask.get("answer_policy"):
        errors.append(f"{name}: claim_check.answer_policy conflicts with top-level answer_policy")
    warning_keys = [warning_key(warning) for warning in ask.get("warnings") or [] if isinstance(warning, dict)]
    if len(warning_keys) != len(set(warning_keys)):
        errors.append(f"{name}: duplicate warnings found")
    for warning in ask.get("warnings") or []:
        if isinstance(warning, dict):
            add_broken_text_errors(f"{name} warning", warning, ("message",), errors)
        elif has_broken_text(warning):
            errors.append(f"{name}: broken Korean text in warning")
    for missing in ask.get("missing_evidence") or []:
        if isinstance(missing, dict):
            add_broken_text_errors(
                f"{name} missing_evidence",
                missing,
                ("message", "label", "description", "reason", "missing_type"),
                errors,
            )
        elif has_broken_text(missing):
            errors.append(f"{name}: broken Korean text in missing_evidence")
    for idx, chip in enumerate(ask.get("evidence_chips") or []):
        if not isinstance(chip, dict):
            errors.append(f"{name}: evidence_chips[{idx}] must be a dict")
            continue
        if not (
            chip.get("label")
            or chip.get("citation_text")
            or chip.get("law_name")
            or chip.get("article_no")
            or chip.get("annex_title")
            or chip.get("type")
            or chip.get("evidence_kind")
        ):
            errors.append(f"{name}: evidence_chips[{idx}] lacks display fields")
        if not (
            chip.get("source_node_id")
            or chip.get("source_anchor_id")
            or chip.get("rule_id")
            or chip.get("list_item_id")
            or chip.get("node_id")
        ):
            # Some chips may be non-clickable, so this is recorded as a schema warning only when all chips miss ids.
            continue
    chips = ask.get("evidence_chips") or []
    if chips and not any(
        chip.get("source_node_id")
        or chip.get("source_anchor_id")
        or chip.get("rule_id")
        or chip.get("list_item_id")
        or chip.get("node_id")
        for chip in chips
        if isinstance(chip, dict)
    ):
        errors.append(f"{name}: no evidence chip has a detail id")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test frontend compatibility endpoints")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()
    root = Path(args.root_dir).resolve()
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "evidence_traversal"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = root / "graph_rag_knowledgement" / "neo4j_load" / "reports" / "frontend_compat_endpoint_implementation_report.txt"
    linking_report_path = root / "graph_rag_knowledgement" / "neo4j_load" / "reports" / "site_checklist_evidence_linking_report.txt"
    samples_path = out_dir / "frontend_compat_endpoint_smoke_test_samples.json"
    linking_samples_path = out_dir / "site_checklist_evidence_linking_samples.json"
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    client = TestClient(app)
    errors: list[str] = []
    quality_warnings: list[str] = []
    summaries: list[dict[str, Any]] = []
    samples: dict[str, Any] = {}

    def record(name: str, response, required: tuple[str, ...] = ()):
        ok = response.status_code
        data = response.json() if response.content else None
        missing = []
        if isinstance(data, dict):
            missing = [field for field in required if field not in data]
        elif required:
            missing = list(required)
        summaries.append({"name": name, "status_code": ok, "missing_fields": missing})
        samples[name] = data
        if ok >= 400:
            errors.append(f"{name}: unexpected status {ok}")
        for field in missing:
            errors.append(f"{name}: missing field {field}")
        return data

    record("GET /health", client.get("/health"), ("status", "service", "graph_db", "llm_used_default"))

    smalltalk = record(
        "POST /ask smalltalk",
        client.post("/ask", json={"question": "안녕", "mode": "qa", "chat_history": []}),
        (
            "answer",
            "evidences",
            "citations",
            "evidence_chips",
            "claim_check",
            "answer_policy",
            "evidence_readiness",
            "warnings",
            "missing_evidence",
            "debug",
        ),
    )
    if (smalltalk or {}).get("answer_policy") != "NO_LEGAL_CLAIM":
        errors.append("smalltalk: expected answer_policy NO_LEGAL_CLAIM")
    if (smalltalk or {}).get("evidence_readiness") != "NOT_APPLICABLE":
        errors.append("smalltalk: expected evidence_readiness NOT_APPLICABLE")
    for field in ("citations", "evidence_chips", "evidences"):
        if (smalltalk or {}).get(field) != []:
            errors.append(f"smalltalk: expected empty {field}")
    if (smalltalk or {}).get("intent") != "smalltalk_or_help":
        errors.append("smalltalk: expected intent smalltalk_or_help")
    if ((smalltalk or {}).get("debug") or {}).get("route") != "smalltalk_or_help":
        errors.append("smalltalk: expected debug.route smalltalk_or_help")

    checklist_payload = {
        "site_name": "테스트 현장",
        "industry": "건설업",
        "work_types": ["고소작업", "밀폐공간"],
        "environments": ["실외"],
        "hazards": ["추락", "낙하물"],
        "equipment": [],
        "worker_count": 10,
        "subcontract": None,
        "safety_state": {"안전난간 설치": False, "보호구 지급": True},
        "special_notes": "",
    }
    checklist = record(
        "POST /site-checklist-ui",
        client.post("/site-checklist-ui", json=checklist_payload),
        ("answer", "items", "evidences"),
    )
    if not isinstance((checklist or {}).get("items"), list) or not (checklist or {}).get("items"):
        errors.append("POST /site-checklist-ui: items must be a non-empty list")
    checklist_items = (checklist or {}).get("items") or []
    if len(checklist_items) < 3:
        errors.append("POST /site-checklist-ui: expected at least 3 checklist items")
    linked_items = [item for item in checklist_items if item.get("law_node_id") or item.get("node_id")]
    evidence_items = [item for item in checklist_items if item.get("evidences")]
    if not linked_items:
        errors.append("POST /site-checklist-ui: expected at least one item with law_node_id or node_id")
    if not evidence_items:
        errors.append("POST /site-checklist-ui: expected at least one item with non-empty evidences")
    for item in checklist_items:
        add_broken_text_errors(
            f"POST /site-checklist-ui item {item.get('id')}",
            item,
            ("title", "text", "description", "law_title"),
            errors,
        )
        for warning in (item.get("warnings") or []) + (item.get("penalty_warnings") or []):
            add_broken_text_errors(
                f"POST /site-checklist-ui item {item.get('id')} warning",
                warning,
                ("message",),
                errors,
            )

    for query in ASK_QUERIES:
        ask = record(
            f"POST /ask {query}",
            client.post("/ask", json={"question": query, "mode": "qa", "chat_history": []}),
            (
                "answer",
                "evidences",
                "citations",
                "evidence_chips",
                "claim_check",
                "answer_policy",
                "evidence_readiness",
                "warnings",
                "missing_evidence",
            ),
        )
        validate_ask_schema(f"POST /ask {query}", ask, errors)
        answer = str((ask or {}).get("answer") or "")
        if "warning:" in answer.lower():
            errors.append(f"POST /ask {query}: answer exposes warning log")
        if "THRESHOLD_MISSING" in answer:
            errors.append(f"POST /ask {query}: answer exposes THRESHOLD_MISSING")
        if UUID_PATTERN.search(answer):
            errors.append(f"POST /ask {query}: answer exposes UUID")
        if query.startswith("정기 안전보건교육"):
            if (ask or {}).get("query_intent") != "education_time":
                errors.append("education query: expected query_intent education_time")
            if (ask or {}).get("domain_extractor_used") is not True:
                errors.append("education query: expected domain extractor")
            if "[결론]" not in answer and "결론" not in answer:
                errors.append("education query: answer should include conclusion section")
            if not any(term in answer for term in ("제26조", "별표", "교육대상", "교육구분")):
                errors.append("education query: answer should explain article/annex or target/category check")
            if any(term in answer for term in ("건강진단", "유해물질", "보호구", "금지유해물질")):
                errors.append("education query: answer contains unrelated evidence terms")
        if query.startswith("위험성평가"):
            if (ask or {}).get("answer_policy") != "INDIRECT_ONLY_RESPONSE":
                errors.append("risk assessment answer_policy mismatch")
            if (ask or {}).get("evidence_readiness") != "INDIRECT_ONLY":
                errors.append("risk assessment evidence_readiness mismatch")
            if ((ask or {}).get("claim_check") or {}).get("answer_policy") != "INDIRECT_ONLY_RESPONSE":
                errors.append("risk assessment claim_check answer_policy mismatch")
            if any(phrase in answer for phrase in RISK_DIRECT_ASSERTIONS):
                errors.append("risk assessment answer contains direct obligation assertion")
            if not any(phrase in answer for phrase in RISK_LIMITING_PHRASES):
                quality_warnings.append("risk assessment answer does not clearly mention direct/indirect/limited evidence")
        if query.startswith("과태료"):
            if (ask or {}).get("query_intent") != "penalty":
                errors.append("penalty query: expected query_intent penalty")
            if (ask or {}).get("domain_extractor_used") is not True:
                errors.append("penalty query: expected domain extractor")
            if not (ask or {}).get("answer"):
                errors.append("penalty query: missing answer")
            if not ((ask or {}).get("citations") or (ask or {}).get("evidence_chips")):
                errors.append("penalty query: expected citations or evidence_chips")
            if (ask or {}).get("answer_policy") not in {"ALLOW_DIRECT_ANSWER", "ALLOW_WITH_CAUTION"}:
                errors.append(f"penalty query: unexpected answer_policy {(ask or {}).get('answer_policy')}")
            answer = str((ask or {}).get("answer") or "")
            if "후보 처벌은 확정" in answer or "후보 벌칙은 확정" in answer:
                errors.append("penalty query: candidate penalty is phrased as confirmed")

    first_turn = record(
        "POST /ask multi-turn first",
        client.post("/ask", json={"question": "정기 안전보건교육은 몇 시간 해야 하나?", "mode": "qa", "chat_history": []}),
        ("answer", "answer_policy", "evidence_readiness"),
    )
    second_turn = record(
        "POST /ask multi-turn followup",
        client.post(
            "/ask",
            json={
                "question": "비사무직의 경우는 어떤데?",
                "mode": "qa",
                "chat_history": [
                    {"role": "user", "content": "정기 안전보건교육은 몇 시간 해야 하나?"},
                    {"role": "assistant", "content": (first_turn or {}).get("answer") or ""},
                ],
            },
        ),
        ("answer", "answer_policy", "evidence_readiness", "rewritten_question", "question_context_used"),
    )
    followup_answer = str((second_turn or {}).get("answer") or "")
    followup_rewritten = str((second_turn or {}).get("rewritten_question") or "")
    if (second_turn or {}).get("question_context_used") is not True:
        errors.append("multi-turn followup: expected question_context_used true")
    if "비사무직" not in followup_rewritten:
        errors.append("multi-turn followup: rewritten_question should include 비사무직")
    if "정기 안전보건교육" not in followup_rewritten and "교육시간" not in followup_rewritten:
        errors.append("multi-turn followup: rewritten_question should preserve education-time context")
    if "교육교재" in followup_answer and not any(term in followup_answer for term in ("교육시간", "별표", "제26조")):
        errors.append("multi-turn followup: answer appears dominated by education-material evidence")
    if "warning:" in followup_answer.lower() or "THRESHOLD_MISSING" in followup_answer:
        errors.append("multi-turn followup: answer exposes internal warning")
    if UUID_PATTERN.search(followup_answer):
        errors.append("multi-turn followup: answer exposes UUID")

    all_targets_followup = record(
        "POST /ask multi-turn education all-targets followup",
        client.post(
            "/ask",
            json={
                "question": "그냥 다 알려줘봐",
                "mode": "qa",
                "chat_history": [
                    {"role": "user", "content": "정기 안전보건교육은 몇 시간 해야 하나?"},
                    {"role": "assistant", "content": (first_turn or {}).get("answer") or ""},
                ],
            },
        ),
        ("answer", "query_intent", "rewritten_question", "question_context_used", "domain_extractor_used"),
    )
    all_targets_answer = str((all_targets_followup or {}).get("answer") or "")
    all_targets_rewritten = str((all_targets_followup or {}).get("rewritten_question") or "")
    if (all_targets_followup or {}).get("question_context_used") is not True:
        errors.append("all-targets education followup: expected question_context_used true")
    for term in ("사무직", "비사무직", "관리감독자"):
        if term not in all_targets_rewritten:
            errors.append(f"all-targets education followup: rewritten question should include {term}")
    for term in ("사무직 근로자", "비사무직 근로자", "관리감독자"):
        if term not in all_targets_answer:
            errors.append(f"all-targets education followup: answer should mention {term}")
    if not any(term in all_targets_answer for term in ("별표 4", "교육과정별 교육시간")):
        errors.append("all-targets education followup: answer should mention 별표 4 or 교육과정별 교육시간")
    if any(term in all_targets_answer for term in ("중대재해 처벌 등에 관한 법률", "건강진단", "유해물질", "보호구", "금지유해물질")):
        errors.append("all-targets education followup: answer contains unrelated fallback evidence")
    if (
        "warning:" in all_targets_answer.lower()
        or "THRESHOLD_MISSING" in all_targets_answer
        or "Education time evidence candidate has no threshold" in all_targets_answer
        or "Many evidence candidates were found; top-k ambiguity is possible" in all_targets_answer
    ):
        errors.append("all-targets education followup: answer exposes internal warning")

    education_followup2 = record(
        "POST /ask multi-turn education natural followup",
        client.post(
            "/ask",
            json={
                "question": "그럼 비사무직을 정기 교육을 어떻게 해야되는데",
                "mode": "qa",
                "chat_history": [
                    {"role": "user", "content": "정기 안전보건교육은 몇 시간 해야 하나?"},
                    {"role": "assistant", "content": (first_turn or {}).get("answer") or ""},
                ],
            },
        ),
        ("answer", "query_intent", "rewritten_question", "question_context_used", "domain_extractor_used"),
    )
    education_followup2_answer = str((education_followup2 or {}).get("answer") or "")
    if (education_followup2 or {}).get("question_context_used") is not True:
        errors.append("natural education followup: expected question_context_used true")
    if "비사무직" not in str((education_followup2 or {}).get("rewritten_question") or ""):
        errors.append("natural education followup: rewritten question should include 비사무직")
    if "비사무직" not in education_followup2_answer:
        errors.append("natural education followup: answer should mention 비사무직")
    if not any(term in education_followup2_answer for term in ("교육시간", "별표 4", "별표", "제26조")):
        errors.append("natural education followup: answer should mention education-time evidence")
    if any(term in education_followup2_answer for term in ("건강진단", "유해물질", "보호구", "금지유해물질")):
        errors.append("natural education followup: answer contains unrelated evidence terms")

    complaint_followup = record(
        "POST /ask multi-turn complaint followup",
        client.post(
            "/ask",
            json={
                "question": "내가 확인하라고?",
                "mode": "qa",
                "chat_history": [
                    {"role": "user", "content": "정기 안전보건교육은 몇 시간 해야 하나?"},
                    {"role": "assistant", "content": (first_turn or {}).get("answer") or ""},
                    {"role": "user", "content": "그럼 비사무직을 정기 교육을 어떻게 해야되는데"},
                    {"role": "assistant", "content": education_followup2_answer},
                ],
            },
        ),
        ("answer", "query_intent", "rewritten_question", "question_context_used", "domain_extractor_used"),
    )
    complaint_answer = str((complaint_followup or {}).get("answer") or "")
    if (complaint_followup or {}).get("question_context_used") is not True:
        errors.append("complaint followup: expected context carry-over")
    if not any(term in complaint_answer for term in ("비사무직", "정기 안전보건교육", "별표 4", "별표")):
        errors.append("complaint followup: answer should stay in previous education-time context")
    if any(term in complaint_answer for term in ("건강진단", "유해물질", "보호구", "금지유해물질")):
        errors.append("complaint followup: answer contains unrelated evidence terms")

    list_lookup = record(
        "POST /ask list lookup domain",
        client.post("/ask", json={"question": "안전검사 대상 기계에는 어떤 것들이 있나?", "mode": "qa", "chat_history": []}),
        ("answer", "query_intent", "domain_extractor_used"),
    )
    list_answer = str((list_lookup or {}).get("answer") or "")
    if (list_lookup or {}).get("query_intent") != "list_lookup":
        errors.append("list lookup: expected query_intent list_lookup")
    if (list_lookup or {}).get("domain_extractor_used") is not True:
        errors.append("list lookup: expected domain extractor")
    if not any(term in list_answer for term in ("대상", "목록", "크레인", "프레스", "리프트")):
        errors.append("list lookup: answer should include target/list terms")

    record("GET /projects", client.get("/projects"))
    record("POST /projects", client.post("/projects", json={"name": "테스트 프로젝트"}), ("id",))
    record("GET /history/checklists", client.get("/history/checklists"))
    record("POST /history/checklists", client.post("/history/checklists", json={"summary": "테스트"}), ("id",))
    record("GET /history/chats", client.get("/history/chats"))
    record("POST /history/chats", client.post("/history/chats", json={"question": "q", "answer": "a"}), ("id",))
    record("GET /history/exports", client.get("/history/exports"))
    record("POST /history/exports", client.post("/history/exports", json={"format": "pdf"}), ("id",))

    linked_node_id = None
    for item in linked_items:
        linked_node_id = item.get("law_node_id") or item.get("node_id")
        if linked_node_id:
            break
    # /law/{nodeId} should not crash; linked ids should normally resolve, unknown ids may return 404.
    law_response = client.get(f"/law/{linked_node_id}" if linked_node_id else "/law/nonexistent-compat-test-node")
    summaries.append(
        {
            "name": "GET /law/{nodeId}",
            "status_code": law_response.status_code,
            "missing_fields": [],
            "node_id": linked_node_id,
        }
    )
    samples["GET /law/{nodeId}"] = law_response.json()
    if law_response.status_code not in {200, 404}:
        errors.append(f"GET /law/{{nodeId}}: unexpected status {law_response.status_code}")
    if law_response.status_code == 200:
        law_detail = law_response.json()
        if not (law_detail.get("title") or law_detail.get("law_name") or law_detail.get("article_no")):
            errors.append("GET /law/{nodeId}: expected title or law_name/article_no")
        if not (law_detail.get("source_text") or law_detail.get("preview")):
            errors.append("GET /law/{nodeId}: expected source_text or preview")
        if not (law_detail.get("citations") or law_detail.get("law_name") or law_detail.get("article_no")):
            errors.append("GET /law/{nodeId}: expected citations or fallback law_name/article_no")
        warning_keys = [
            (warning.get("warning_type"), warning.get("message"))
            for warning in (law_detail.get("warnings") or [])
        ]
        if len(warning_keys) != len(set(warning_keys)):
            errors.append("GET /law/{nodeId}: duplicate warnings found")
        citation_keys = [
            (
                citation.get("citation_text"),
                citation.get("source_anchor_id"),
                citation.get("source_node_id"),
            )
            for citation in (law_detail.get("citations") or [])
        ]
        if len(citation_keys) != len(set(citation_keys)):
            errors.append("GET /law/{nodeId}: duplicate citations found")
        if law_detail.get("summary") and law_detail.get("source_text"):
            if law_detail.get("summary") == law_detail.get("source_text"):
                errors.append("GET /law/{nodeId}: summary must not equal source_text")
        add_broken_text_errors(
            "GET /law/{nodeId}",
            law_detail,
            ("summary", "why_relevant", "title"),
            errors,
        )
        if "Graph-RAG evidence lookup" in str(law_detail.get("why_relevant") or ""):
            errors.append("GET /law/{nodeId}: why_relevant contains developer wording")
        for warning in law_detail.get("warnings") or []:
            add_broken_text_errors("GET /law/{nodeId} warning", warning, ("message",), errors)
        for idx, candidate in enumerate(law_detail.get("candidate_penalties") or []):
            for field in ("match_type", "confidence", "candidate_notice"):
                if not candidate.get(field):
                    errors.append(f"GET /law/{{nodeId}} candidate_penalties[{idx}]: missing {field}")
            if candidate.get("is_confirmed") is not False:
                errors.append(f"GET /law/{{nodeId}} candidate_penalties[{idx}]: is_confirmed must be false")
            add_broken_text_errors(
                f"GET /law/{{nodeId}} candidate_penalties[{idx}]",
                candidate,
                ("candidate_notice", "match_reason", "title", "citation_text"),
                errors,
            )
        for idx, penalty in enumerate(law_detail.get("penalties") or []):
            if "is_confirmed" in penalty and penalty.get("is_confirmed") is not True:
                errors.append(f"GET /law/{{nodeId}} penalties[{idx}]: is_confirmed must be true")

    final_status = "PASS" if not errors else "FAIL"
    report = [
        "Frontend Compatibility Endpoint Implementation Report",
        "====================================================",
        f"- created_at: {started}",
        f"- root_dir: {root}",
        "- modified_file: 05_code/graph_rag_pipeline/ask_adapter.py",
        "- created_smoke_test: 05_code/graph_rag_pipeline/smoke_test_frontend_compat_endpoints.py",
        "- llm_used: false",
        "- neo4j_write_executed: false",
        f"- final_status: {final_status}",
        "",
        "Implemented endpoints:",
        "- GET /health",
        "- POST /ask",
        "- POST /site-checklist-ui",
        "- GET /projects",
        "- POST /projects",
        "- GET /history/checklists",
        "- POST /history/checklists",
        "- GET /history/chats",
        "- POST /history/chats",
        "- GET /history/exports",
        "- POST /history/exports",
        "- GET /law/{nodeId}",
        "",
        "Frontend run command:",
        "- python -m uvicorn graph_rag_pipeline.ask_adapter:app --app-dir 05_code --host 127.0.0.1 --port 8000",
        "",
        "Smoke results:",
    ]
    for summary in summaries:
        report.append(f"- {summary['name']}: status={summary['status_code']}, missing={summary['missing_fields']}")
    report.extend(["", "Errors:"])
    report.extend([f"- {error}" for error in errors] or ["- none"])
    report.extend(["", "Quality warnings:"])
    report.extend([f"- {warning}" for warning in quality_warnings] or ["- none"])
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    linking_report = [
        "Site Checklist Evidence Linking Report",
        "======================================",
        f"- created_at: {started}",
        f"- final_status: {final_status}",
        "- modified_file: 05_code/graph_rag_pipeline/ask_adapter.py",
        "- smoke_test: 05_code/graph_rag_pipeline/smoke_test_frontend_compat_endpoints.py",
        "- neo4j_write_executed: false",
        "- llm_used: false",
        f"- checklist_item_count: {len(checklist_items)}",
        f"- linked_item_count: {len(linked_items)}",
        f"- evidence_non_empty_item_count: {len(evidence_items)}",
        f"- first_linked_node_id: {linked_node_id}",
        f"- law_detail_status: {law_response.status_code}",
        f"- law_detail_has_text: {bool((samples.get('GET /law/{nodeId}') or {}).get('source_text') or (samples.get('GET /law/{nodeId}') or {}).get('preview'))}",
        f"- law_detail_citation_count: {len((samples.get('GET /law/{nodeId}') or {}).get('citations') or [])}",
        f"- law_detail_warning_count: {len((samples.get('GET /law/{nodeId}') or {}).get('warnings') or [])}",
        "",
        "Item summary:",
    ]
    for item in checklist_items:
        linking_report.append(
            "- "
            f"id={item.get('id')}, "
            f"node_id={item.get('node_id')}, "
            f"law_node_id={item.get('law_node_id')}, "
            f"evidences={len(item.get('evidences') or [])}, "
            f"readiness={item.get('evidence_readiness')}, "
            f"policy={item.get('answer_policy')}"
        )
    linking_report.extend(["", "Errors:"])
    linking_report.extend([f"- {error}" for error in errors] or ["- none"])
    linking_report.extend(["", "Quality warnings:"])
    linking_report.extend([f"- {warning}" for warning in quality_warnings] or ["- none"])
    linking_report_path.write_text("\n".join(linking_report) + "\n", encoding="utf-8")
    samples_path.write_text(
        json.dumps(
            {
                "created_at": started,
                "final_status": final_status,
                "llm_used": False,
                "neo4j_write_executed": False,
                "summaries": summaries,
                "quality_warnings": quality_warnings,
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    linking_samples_path.write_text(
        json.dumps(
            {
                "created_at": started,
                "final_status": final_status,
                "checklist": checklist,
                "linked_node_id": linked_node_id,
                "law_detail_status": law_response.status_code,
                "law_detail_sample": samples.get("GET /law/{nodeId}"),
                "quality_warnings": quality_warnings,
                "llm_used": False,
                "neo4j_write_executed": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Smoke test report: {report_path}")
    print(f"Evidence linking report: {linking_report_path}")
    print(f"Smoke test samples: {samples_path}")
    print(f"Evidence linking samples: {linking_samples_path}")
    print(f"Status: {final_status}")
    strengthening_report_path = (
        root
        / "graph_rag_knowledgement"
        / "neo4j_load"
        / "reports"
        / "penalty_frontend_improvement"
        / "step_09_smoke_test_strengthening_report.txt"
    )
    strengthening_report_path.write_text(
        "\n".join(
            [
                "Step 09 Smoke Test Strengthening Report",
                "=======================================",
                f"created_at: {started}",
                f"final_status: {final_status}",
                "",
                "Added validations:",
                "- Broken Korean/mojibake checks on user-facing checklist and law detail fields.",
                "- Candidate penalty schema checks for match_type, confidence, candidate_notice, and is_confirmed=false.",
                "- Direct penalty is_confirmed=true check where present.",
                "- Risk assessment notice guardrail checks for INDIRECT_ONLY_RESPONSE and non-assertive phrasing.",
                "- Penalty lookup answer/citation/policy checks.",
                "- /law detail checks for duplicate warnings/citations and non-developer why_relevant wording.",
                "",
                "Errors:",
                *([f"- {error}" for error in errors] or ["- none"]),
                "",
                "Quality warnings:",
                *([f"- {warning}" for warning in quality_warnings] or ["- none"]),
                "",
                "Safety:",
                "- Neo4j write executed: false",
                "- LLM call executed: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Strengthening report: {strengthening_report_path}")
    return 0 if final_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
