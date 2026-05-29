#!/usr/bin/env python
"""Smoke test for the read-only graph query layer."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from graph_rag_pipeline.graph_query_layer import GraphQueryError, GraphQueryLayer  # noqa: E402


def preview_text(value: Any, limit: int = 300) -> Any:
    if isinstance(value, str):
        text = value.replace("\r", " ").replace("\n", " ").strip()
        return text[: limit - 3] + "..." if len(text) > limit else text
    if isinstance(value, list):
        return [preview_text(v, limit) for v in value[:20]]
    if isinstance(value, dict):
        return {k: preview_text(v, limit) for k, v in value.items()}
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test GraphQueryLayer")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "evidence_traversal"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "graph_query_layer_smoke_test_report.txt"
    samples_path = out_dir / "graph_query_layer_smoke_test_samples.json"

    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    samples: dict[str, Any] = {"created_at": started, "mode": "READ_ONLY_SMOKE_TEST"}
    statuses: dict[str, str] = {}
    errors: list[str] = []

    layer: GraphQueryLayer | None = None
    try:
        layer = GraphQueryLayer(root)
        counts = layer.get_graph_counts()
        samples["graph_counts"] = counts
        statuses["graph_counts"] = "PASS" if counts.get("total_nodes", 0) > 0 else "FAIL"

        checks = [
            ("requirement_evidence", lambda: layer.get_requirement_evidence(5)),
            ("threshold_evidence", lambda: layer.get_threshold_evidence(5)),
            ("exception_evidence", lambda: layer.get_exception_evidence(5)),
            ("listitem_evidence", lambda: layer.get_listitem_evidence(limit=10)),
            ("education_time_evidence", lambda: layer.get_education_time_evidence(10)),
            ("inspection_list_evidence", lambda: layer.get_inspection_list_evidence(10)),
            ("penalty_evidence", lambda: layer.get_penalty_evidence(10)),
        ]
        for name, fn in checks:
            try:
                rows = fn()
                samples[name] = preview_text(rows)
                statuses[name] = "PASS" if rows else "WARN_EMPTY"
            except Exception as exc:  # noqa: BLE001
                statuses[name] = "FAIL"
                errors.append(f"{name}: {type(exc).__name__}: {exc}")

        keyword_results = {}
        for keyword in ("교육", "안전검사", "크레인", "과태료", "안전관리자", "위험성평가"):
            try:
                rows = layer.search_rules_by_keyword(keyword, 5)
                keyword_results[keyword] = preview_text(rows)
                statuses[f"keyword:{keyword}"] = "PASS" if rows else "WARN_EMPTY"
            except Exception as exc:  # noqa: BLE001
                statuses[f"keyword:{keyword}"] = "FAIL"
                errors.append(f"keyword {keyword}: {type(exc).__name__}: {exc}")
        samples["keyword_search"] = keyword_results

        try:
            layer.run_read_query("CREATE (n:ShouldBeBlocked) RETURN n")
            statuses["read_only_guard"] = "FAIL"
            errors.append("read-only guard did not block CREATE query")
        except GraphQueryError:
            statuses["read_only_guard"] = "PASS"

        status = "PASS" if not errors and all(v in {"PASS", "WARN_EMPTY"} for v in statuses.values()) else "FAIL"
        report = [
            "Graph Query Layer Smoke Test Report",
            "===================================",
            f"- created_at: {started}",
            f"- root_dir: {root}",
            f"- target_uri: {layer.env['NEO4J_URI']}",
            f"- target_database: {layer.env['NEO4J_DATABASE']}",
            f"- user: {layer.env['NEO4J_USER']}",
            "- credential_note: password value intentionally omitted",
            "- mode: READ_ONLY_SMOKE_TEST",
            f"- final_status: {status}",
            "",
            "Graph counts:",
            f"- total_nodes: {counts.get('total_nodes')}",
            f"- total_relationships: {counts.get('total_relationships')}",
            f"- missing_source_text_rules: {counts.get('missing_source_text_rules')}",
            f"- rules_without_source: {counts.get('rules_without_source')}",
            f"- unresolved_source_nodes: {counts.get('unresolved_source_nodes')}",
            f"- item_resolves_to_count: {counts.get('item_resolves_to_count')}",
            "",
            "Check statuses:",
        ]
        report.extend(f"- {k}: {v}" for k, v in statuses.items())
        report.extend(["", "Errors:"])
        report.extend([f"- {e}" for e in errors] or ["- none"])
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        samples_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")

        secret = layer.env.get("NEO4J_PASSWORD", "")
        if secret:
            for path in (report_path, samples_path):
                if secret in path.read_text(encoding="utf-8", errors="ignore"):
                    raise RuntimeError(f"password leaked into smoke test output: {path}")
        print(f"Smoke test report: {report_path}")
        print(f"Smoke test samples: {samples_path}")
        print(f"Status: {status}")
        return 0 if status == "PASS" else 1
    finally:
        if layer is not None:
            layer.close()


if __name__ == "__main__":
    raise SystemExit(main())
