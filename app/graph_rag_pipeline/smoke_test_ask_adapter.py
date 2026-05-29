#!/usr/bin/env python
"""Smoke test the Graph-RAG /ask adapter by direct function calls."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from graph_rag_pipeline.ask_adapter import ask_graph_rag  # noqa: E402


TEST_CASES = [
    ("안전관리자는 어떤 기준으로 선임해야 하나?", None),
    ("정기 안전보건교육은 몇 시간 해야 하나?", None),
    ("안전검사 대상 기계에는 어떤 것들이 있나?", None),
    ("위험성평가 결과를 근로자에게 알려야 하나?", None),
    ("과태료가 부과되는 경우는 무엇인가?", None),
    ("적용 제외되는 경우가 있나?", None),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Graph-RAG ask adapter")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()
    root = Path(args.root_dir).resolve()
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "evidence_traversal"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "ask_adapter_smoke_test_report.txt"
    samples_path = out_dir / "ask_adapter_smoke_test_samples.json"
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summaries: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    errors: list[str] = []
    for query, intent in TEST_CASES:
        payload: dict[str, Any] = {
            "question": query,
            "mode": "qa",
            "chat_history": [],
            "options": {"include_evidence": True, "include_debug": False, "top_k": 5, "use_llm": False},
        }
        if intent:
            payload["intent"] = intent
        response = ask_graph_rag(payload, root)
        summary = {
            "query": query,
            "intent": response.get("intent"),
            "status": response.get("status"),
            "evidence_readiness": response.get("evidence_readiness"),
            "answer_policy": response.get("answer_policy"),
            "answer_present": bool(response.get("answer")),
            "citations_count": len(response.get("citations") or []),
            "evidence_chips_count": len(response.get("evidence_chips") or []),
            "evidences_count": len(response.get("evidences") or []),
            "claim_check_present": bool(response.get("claim_check")),
            "llm_used": (response.get("debug") or {}).get("llm_used"),
        }
        summaries.append(summary)
        samples.append(response)
        if not response.get("answer"):
            errors.append(f"{query}: answer missing")
        if not response.get("evidences"):
            errors.append(f"{query}: legacy evidences missing")
        if not (response.get("citations") or response.get("evidence_chips")):
            errors.append(f"{query}: citations/evidence_chips missing")
        if not response.get("claim_check"):
            errors.append(f"{query}: claim_check missing")
        if (response.get("debug") or {}).get("llm_used"):
            errors.append(f"{query}: LLM was used")
        if query.startswith("위험성평가") and response.get("answer_policy") != "INDIRECT_ONLY_RESPONSE":
            errors.append("risk assessment notice query did not return INDIRECT_ONLY_RESPONSE")
    final_status = "PASS" if not errors else "FAIL"
    report = [
        "Ask Adapter Smoke Test Report",
        "=============================",
        f"- created_at: {started}",
        f"- root_dir: {root}",
        "- mode: DIRECT_FUNCTION_SMOKE_TEST",
        "- llm_used: false",
        "- neo4j_write_executed: false",
        f"- final_status: {final_status}",
        "",
        "Query Results:",
    ]
    for summary in summaries:
        report.extend(
            [
                f"- query: {summary['query']}",
                f"  intent: {summary['intent']}",
                f"  status: {summary['status']}",
                f"  evidence_readiness: {summary['evidence_readiness']}",
                f"  answer_policy: {summary['answer_policy']}",
                f"  answer_present: {summary['answer_present']}",
                f"  citations_count: {summary['citations_count']}",
                f"  evidence_chips_count: {summary['evidence_chips_count']}",
                f"  evidences_count: {summary['evidences_count']}",
                f"  claim_check_present: {summary['claim_check_present']}",
            ]
        )
    report.extend(["", "Errors:"])
    report.extend([f"- {error}" for error in errors] or ["- none"])
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    samples_path.write_text(
        json.dumps(
            {
                "created_at": started,
                "mode": "DIRECT_FUNCTION_SMOKE_TEST",
                "llm_used": False,
                "neo4j_write_executed": False,
                "summaries": summaries,
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Smoke test report: {report_path}")
    print(f"Smoke test samples: {samples_path}")
    print(f"Status: {final_status}")
    return 0 if final_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
