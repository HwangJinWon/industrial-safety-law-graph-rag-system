#!/usr/bin/env python
"""Smoke test CitationFormatter and ClaimChecker.

This script builds evidence packs, formats citations/evidence chips/legacy
evidences, and checks answer-readiness. It does not generate answers, call an
LLM, or write to Neo4j.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from graph_rag_pipeline.citation_formatter import CitationFormatter  # noqa: E402
from graph_rag_pipeline.claim_check import ClaimChecker  # noqa: E402
from graph_rag_pipeline.evidence_pack_assembler import EvidencePackAssembler, preview_text  # noqa: E402


TEST_CASES = [
    ("안전관리자는 어떤 기준으로 선임해야 하나?", "appointment_requirement"),
    ("정기 안전보건교육은 몇 시간 해야 하나?", "education_time_lookup"),
    ("안전검사 대상 기계에는 어떤 것들이 있나?", "inspection_requirement"),
    ("위험성평가 결과를 근로자에게 알려야 하나?", "obligation_check"),
    ("과태료가 부과되는 경우는 무엇인가?", "penalty_lookup"),
    ("적용 제외되는 경우가 있나?", "applicability_check"),
]


def summarize(
    query: str,
    intent: str,
    pack: dict,
    citations: list[dict],
    chips: list[dict],
    legacy_evidences: list[dict],
    check: dict,
) -> dict[str, Any]:
    return {
        "query": query,
        "intent": intent,
        "pack_status": pack.get("status"),
        "evidence_readiness": pack.get("evidence_readiness"),
        "formatted_citation_count": len(citations),
        "evidence_chips_count": len(chips),
        "legacy_evidences_count": len(legacy_evidences),
        "claim_check_status": check.get("claim_check_status"),
        "answer_policy": check.get("answer_policy"),
        "badge_count": len(check.get("badges") or []),
        "issue_count": len(check.get("issues") or []),
        "high_severity_issue_count": (check.get("summary") or {}).get("high_severity_issue_count", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test citation formatting and claim checking")
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "evidence_traversal"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "citation_claim_check_smoke_test_report.txt"
    samples_path = out_dir / "citation_claim_check_smoke_test_samples.json"
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    formatter = CitationFormatter()
    checker = ClaimChecker()
    assembler: EvidencePackAssembler | None = None
    summaries: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        assembler = EvidencePackAssembler(root)
        env = assembler.query_layer.env
        for query, intent in TEST_CASES:
            pack = assembler.assemble(query, intent, args.limit)
            citations = formatter.format_pack_citations(pack)
            chips = formatter.build_evidence_chips(pack, citations)
            legacy_evidences = formatter.build_legacy_evidences(pack, citations)
            check = checker.check_pack(pack, citations)
            summaries.append(summarize(query, intent, pack, citations, chips, legacy_evidences, check))
            samples.append(
                preview_text(
                    {
                        "query": query,
                        "intent": intent,
                        "evidence_pack_status": pack.get("status"),
                        "evidence_readiness": pack.get("evidence_readiness"),
                        "citations": citations,
                        "evidence_chips": chips,
                        "legacy_evidences": legacy_evidences,
                        "claim_check": check,
                    },
                    700,
                )
            )

            if not pack.get("primary_evidence"):
                errors.append(f"{intent}: no primary evidence")
            if not citations:
                errors.append(f"{intent}: no formatted citations")
            if not chips:
                errors.append(f"{intent}: no evidence chips")
            if not legacy_evidences:
                errors.append(f"{intent}: no legacy evidences")
            if not check:
                errors.append(f"{intent}: no claim check result")
            if intent == "obligation_check" and check.get("answer_policy") != "INDIRECT_ONLY_RESPONSE":
                errors.append(f"{intent}: expected INDIRECT_ONLY_RESPONSE, got {check.get('answer_policy')}")
            if intent != "obligation_check" and check.get("answer_policy") not in {
                "ALLOW_DIRECT_ANSWER",
                "ALLOW_WITH_CAUTION",
            }:
                errors.append(f"{intent}: unexpected answer policy {check.get('answer_policy')}")

        final_status = "PASS" if not errors else "FAIL"
        report = [
            "Citation and Claim Check Smoke Test Report",
            "==========================================",
            f"- created_at: {started}",
            f"- root_dir: {root}",
            f"- target_uri: {env.get('NEO4J_URI')}",
            f"- target_database: {env.get('NEO4J_DATABASE')}",
            f"- user: {env.get('NEO4J_USER')}",
            "- mode: READ_ONLY_CITATION_CLAIM_CHECK_SMOKE_TEST",
            "- llm_used: false",
            "- neo4j_write_executed: false",
            "- natural_language_answer_generated: false",
            f"- final_status: {final_status}",
            "",
            "Query Results:",
        ]
        for summary in summaries:
            report.extend(
                [
                    f"- query: {summary['query']}",
                    f"  intent: {summary['intent']}",
                    f"  pack_status: {summary['pack_status']}",
                    f"  evidence_readiness: {summary['evidence_readiness']}",
                    f"  formatted_citation_count: {summary['formatted_citation_count']}",
                    f"  evidence_chips_count: {summary['evidence_chips_count']}",
                    f"  legacy_evidences_count: {summary['legacy_evidences_count']}",
                    f"  claim_check_status: {summary['claim_check_status']}",
                    f"  answer_policy: {summary['answer_policy']}",
                    f"  badge_count: {summary['badge_count']}",
                    f"  issue_count: {summary['issue_count']}",
                    f"  high_severity_issue_count: {summary['high_severity_issue_count']}",
                ]
            )
        report.extend(["", "Errors:"])
        report.extend([f"- {error}" for error in errors] or ["- none"])
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        samples_path.write_text(
            json.dumps(
                {
                    "created_at": started,
                    "mode": "READ_ONLY_CITATION_CLAIM_CHECK_SMOKE_TEST",
                    "llm_used": False,
                    "neo4j_write_executed": False,
                    "natural_language_answer_generated": False,
                    "summaries": summaries,
                    "samples": samples,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        secret = env.get("NEO4J_PASSWORD", "")
        if secret:
            for path in (report_path, samples_path):
                if secret in path.read_text(encoding="utf-8", errors="ignore"):
                    raise RuntimeError(f"secret leaked into smoke test output: {path}")

        print(f"Smoke test report: {report_path}")
        print(f"Smoke test samples: {samples_path}")
        print(f"Status: {final_status}")
        return 0 if final_status == "PASS" else 1
    finally:
        if assembler is not None:
            assembler.close()


if __name__ == "__main__":
    raise SystemExit(main())
