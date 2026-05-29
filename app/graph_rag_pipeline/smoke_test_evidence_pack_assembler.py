#!/usr/bin/env python
"""Smoke test for EvidencePackAssembler."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from graph_rag_pipeline.evidence_pack_assembler import EvidencePackAssembler, preview_text  # noqa: E402


TEST_CASES = [
    ("안전관리자는 어떤 기준으로 선임해야 하나?", "appointment_requirement"),
    ("정기 안전보건교육은 몇 시간 해야 하나?", "education_time_lookup"),
    ("안전검사 대상 기계에는 어떤 것들이 있나?", "inspection_requirement"),
    ("위험성평가 결과를 근로자에게 알려야 하나?", "obligation_check"),
    ("과태료가 부과되는 경우는 무엇인가?", "penalty_lookup"),
    ("적용 제외되는 경우가 있나?", "applicability_check"),
]


def summarize_pack(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": pack.get("query"),
        "intent": pack.get("intent"),
        "pack_type": pack.get("pack_type"),
        "status": pack.get("status"),
        "evidence_readiness": pack.get("evidence_readiness"),
        "primary_evidence_count": len(pack.get("primary_evidence") or []),
        "supporting_evidence_count": len(pack.get("supporting_evidence") or []),
        "citation_candidate_count": len(pack.get("citation_candidates") or []),
        "warning_count": len(pack.get("warnings") or []),
        "missing_evidence_count": len(pack.get("missing_evidence") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test EvidencePackAssembler")
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "evidence_traversal"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "evidence_pack_assembler_smoke_test_report.txt"
    samples_path = out_dir / "evidence_pack_assembler_smoke_test_samples.json"

    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assembler: EvidencePackAssembler | None = None
    packs: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        assembler = EvidencePackAssembler(root)
        for query, intent in TEST_CASES:
            pack = assembler.assemble(query, intent, args.limit)
            packs.append(preview_text(pack, 500))
            summary = summarize_pack(pack)
            summaries.append(summary)
            if pack.get("status") not in {"OK", "OK_WITH_WARNINGS"}:
                errors.append(f"{intent}: status={pack.get('status')}")
            if not pack.get("primary_evidence"):
                errors.append(f"{intent}: no primary evidence")
            if not pack.get("citation_candidates") and not pack.get("warnings"):
                errors.append(f"{intent}: no citation candidates and no warning")
        final_status = "PASS" if not errors else "FAIL"
        report = [
            "Evidence Pack Assembler Smoke Test Report",
            "========================================",
            f"- created_at: {started}",
            f"- root_dir: {root}",
            f"- target_uri: {assembler.query_layer.env['NEO4J_URI']}",
            f"- target_database: {assembler.query_layer.env['NEO4J_DATABASE']}",
            f"- user: {assembler.query_layer.env['NEO4J_USER']}",
            "- credential_note: password value intentionally omitted",
            "- mode: READ_ONLY_EVIDENCE_PACK_SMOKE_TEST",
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
                    f"  pack_type: {summary['pack_type']}",
                    f"  status: {summary['status']}",
                    f"  evidence_readiness: {summary['evidence_readiness']}",
                    f"  primary_evidence_count: {summary['primary_evidence_count']}",
                    f"  citation_candidate_count: {summary['citation_candidate_count']}",
                    f"  warning_count: {summary['warning_count']}",
                    f"  missing_evidence_count: {summary['missing_evidence_count']}",
                ]
            )
        report.extend(["", "Errors:"])
        report.extend([f"- {e}" for e in errors] or ["- none"])
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        samples_path.write_text(
            json.dumps(
                {
                    "created_at": started,
                    "mode": "READ_ONLY_EVIDENCE_PACK_SMOKE_TEST",
                    "llm_used": False,
                    "packs": packs,
                    "summaries": summaries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        secret = assembler.query_layer.env.get("NEO4J_PASSWORD", "")
        if secret:
            for path in (report_path, samples_path):
                if secret in path.read_text(encoding="utf-8", errors="ignore"):
                    raise RuntimeError(f"password leaked into smoke test output: {path}")
        print(f"Smoke test report: {report_path}")
        print(f"Smoke test samples: {samples_path}")
        print(f"Status: {final_status}")
        return 0 if final_status == "PASS" else 1
    finally:
        if assembler is not None:
            assembler.close()


if __name__ == "__main__":
    raise SystemExit(main())
