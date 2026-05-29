#!/usr/bin/env python
"""Smoke test deterministic AnswerGenerator.

This test does not call an LLM and does not write to Neo4j.
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

from graph_rag_pipeline.answer_generator import AnswerGenerator  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test AnswerGenerator")
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "evidence_traversal"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "answer_generator_smoke_test_report.txt"
    samples_path = out_dir / "answer_generator_smoke_test_samples.json"
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    assembler: EvidencePackAssembler | None = None
    formatter = CitationFormatter()
    checker = ClaimChecker()
    summaries: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        assembler = EvidencePackAssembler(root)
        generator = AnswerGenerator(root, use_llm=False)
        env = assembler.query_layer.env
        for query, intent in TEST_CASES:
            pack = assembler.assemble(query, intent, args.limit)
            citations = formatter.format_pack_citations(pack)
            claim_check = checker.check_pack(pack, citations)
            generated = generator.generate(pack, citations, claim_check)
            answer = generated.get("answer") or ""
            summary = {
                "query": query,
                "intent": intent,
                "pack_status": pack.get("status"),
                "evidence_readiness": pack.get("evidence_readiness"),
                "answer_policy": generated.get("answer_policy"),
                "claim_check_status": generated.get("claim_check_status"),
                "answer_length": len(answer),
                "citation_count": len(citations),
                "llm_used": generated.get("llm_used"),
                "policy_enforced": generated.get("policy_enforced"),
            }
            summaries.append(summary)
            samples.append(
                preview_text(
                    {
                        "query": query,
                        "intent": intent,
                        "claim_check": claim_check,
                        "generated": generated,
                    },
                    900,
                )
            )
            if not answer:
                errors.append(f"{intent}: answer missing")
            if not citations:
                errors.append(f"{intent}: citations missing")
            if generated.get("llm_used"):
                errors.append(f"{intent}: llm_used must be false")
            if intent == "obligation_check":
                if generated.get("answer_policy") != "INDIRECT_ONLY_RESPONSE":
                    errors.append(f"{intent}: expected INDIRECT_ONLY_RESPONSE")
                if "직접 뒷받침하는 조문 근거는 확인되지 않았고" not in answer:
                    errors.append(f"{intent}: indirect-only guardrail sentence missing")
        final_status = "PASS" if not errors else "FAIL"
        report = [
            "AnswerGenerator Smoke Test Report",
            "=================================",
            f"- created_at: {started}",
            f"- root_dir: {root}",
            f"- target_uri: {env.get('NEO4J_URI')}",
            f"- target_database: {env.get('NEO4J_DATABASE')}",
            f"- user: {env.get('NEO4J_USER')}",
            "- mode: TEMPLATE_ANSWER_SMOKE_TEST",
            "- use_llm: false",
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
                    f"  pack_status: {summary['pack_status']}",
                    f"  evidence_readiness: {summary['evidence_readiness']}",
                    f"  claim_check_status: {summary['claim_check_status']}",
                    f"  answer_policy: {summary['answer_policy']}",
                    f"  answer_length: {summary['answer_length']}",
                    f"  citation_count: {summary['citation_count']}",
                    f"  policy_enforced: {summary['policy_enforced']}",
                ]
            )
        report.extend(["", "Errors:"])
        report.extend([f"- {error}" for error in errors] or ["- none"])
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        samples_path.write_text(
            json.dumps(
                {
                    "created_at": started,
                    "mode": "TEMPLATE_ANSWER_SMOKE_TEST",
                    "use_llm": False,
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
        secret = env.get("NEO4J_PASSWORD", "")
        if secret:
            for path in (report_path, samples_path):
                if secret in path.read_text(encoding="utf-8", errors="ignore"):
                    raise RuntimeError(f"secret leaked into answer generator output: {path}")
        print(f"Smoke test report: {report_path}")
        print(f"Smoke test samples: {samples_path}")
        print(f"Status: {final_status}")
        return 0 if final_status == "PASS" else 1
    finally:
        if assembler is not None:
            assembler.close()


if __name__ == "__main__":
    raise SystemExit(main())
