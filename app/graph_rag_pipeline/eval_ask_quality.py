#!/usr/bin/env python
"""Evaluate /ask quality with a fixed industrial safety law question set.

This is an offline deterministic evaluator. It uses FastAPI TestClient against
the local app and does not call an LLM or perform Neo4j writes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from graph_rag_pipeline.ask_adapter import app  # noqa: E402


UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
INTERNAL_WARNING_MARKERS = (
    "warning:",
    "THRESHOLD_MISSING",
    "Use an indirect-only",
    "candidate has no threshold",
    "source_node_id",
    "rule_id",
    "list_item_id",
)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def contains_any(haystack: str, needles: list[str]) -> bool:
    if not needles:
        return True
    return any(needle and needle in haystack for needle in needles)


def stringify_evidence(response: dict[str, Any]) -> str:
    parts = [response.get("answer") or ""]
    for field in ("citations", "evidence_chips", "evidences"):
        for item in response.get(field) or []:
            parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return "\n".join(parts)


def evaluate_case(client: TestClient, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.post("/ask", json={"question": case["question"], "mode": "qa", "chat_history": []})
    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        data = {"answer": response.text, "status_code": response.status_code}

    answer = str(data.get("answer") or "")
    evidence_text = stringify_evidence(data)
    expected_policies = as_list(case.get("expected_answer_policy"))
    expected_readiness = as_list(case.get("expected_evidence_readiness"))
    expected_intent = case.get("expected_intent") or ""
    actual_intent = data.get("intent") or (data.get("debug") or {}).get("intent") or ""
    actual_policy = data.get("answer_policy") or ""
    actual_readiness = data.get("evidence_readiness") or ""

    intent_ok = not expected_intent or actual_intent == expected_intent
    policy_ok = actual_policy in expected_policies
    readiness_ok = actual_readiness in expected_readiness
    leaked_internal_warning = any(marker in answer for marker in INTERNAL_WARNING_MARKERS)
    leaked_uuid = bool(UUID_RE.search(answer))

    category = case.get("category") or ""
    if category == "smalltalk":
        has_required_terms = True
    else:
        has_required_terms = contains_any(evidence_text, as_list(case.get("must_include_any")))

    must_not = as_list(case.get("must_not_include"))
    guardrail_ok = True
    if case.get("guardrail"):
        guardrail_ok = policy_ok and readiness_ok and not any(term and term in answer for term in must_not)

    score = 0
    score += 1 if policy_ok else 0
    score += 1 if readiness_ok else 0
    score += 1 if has_required_terms else 0
    score += 1 if not leaked_internal_warning else 0
    score += 1 if not leaked_uuid else 0
    if case.get("guardrail") and not guardrail_ok:
        score = min(score, 2)

    final_pass = policy_ok and readiness_ok and not leaked_internal_warning and not leaked_uuid and guardrail_ok
    if category != "smalltalk":
        final_pass = final_pass and has_required_terms

    failure_reasons: list[str] = []
    if response.status_code >= 400:
        failure_reasons.append(f"http_status={response.status_code}")
    if not intent_ok:
        failure_reasons.append(f"intent expected {expected_intent}, got {actual_intent}")
    if not policy_ok:
        failure_reasons.append(f"policy expected {expected_policies}, got {actual_policy}")
    if not readiness_ok:
        failure_reasons.append(f"readiness expected {expected_readiness}, got {actual_readiness}")
    if not has_required_terms:
        failure_reasons.append("required terms not found in answer/evidence")
    if leaked_internal_warning:
        failure_reasons.append("internal warning leaked")
    if leaked_uuid:
        failure_reasons.append("uuid leaked")
    if not guardrail_ok:
        failure_reasons.append("guardrail failed")

    if category == "smalltalk":
        if data.get("citations") != [] or data.get("evidence_chips") != [] or data.get("evidences") != []:
            final_pass = False
            failure_reasons.append("smalltalk should not return graph evidence")

    row = {
        "id": case.get("id"),
        "category": category,
        "question": case.get("question"),
        "expected_intent": expected_intent,
        "actual_intent": actual_intent,
        "intent_ok": intent_ok,
        "expected_answer_policy": "|".join(str(x) for x in expected_policies),
        "actual_answer_policy": actual_policy,
        "policy_ok": policy_ok,
        "expected_evidence_readiness": "|".join(str(x) for x in expected_readiness),
        "actual_evidence_readiness": actual_readiness,
        "readiness_ok": readiness_ok,
        "citation_count": len(data.get("citations") or []),
        "evidence_chip_count": len(data.get("evidence_chips") or []),
        "evidence_count": len(data.get("evidences") or []),
        "has_required_terms": has_required_terms,
        "leaked_internal_warning": leaked_internal_warning,
        "leaked_uuid": leaked_uuid,
        "guardrail_ok": guardrail_ok,
        "answer_length": len(answer),
        "answer_quality_score": score,
        "final_pass": final_pass,
        "failure_reason": "; ".join(failure_reasons),
    }

    sample = {
        "case": case,
        "status_code": response.status_code,
        "response": data,
        "eval": row,
    }
    return row, sample


def write_outputs(root: Path, rows: list[dict[str, Any]], samples: list[dict[str, Any]], started: str) -> None:
    out_dir = root / "graph_rag_knowledgement" / "neo4j_load" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "ask_quality_eval_results.csv"
    json_path = out_dir / "ask_quality_eval_samples.json"
    summary_path = out_dir / "ask_quality_eval_summary.txt"

    if rows:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    json_path.write_text(
        json.dumps(
            {
                "created_at": started,
                "llm_used": False,
                "neo4j_write_executed": False,
                "results": rows,
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    total = len(rows)
    pass_count = sum(1 for row in rows if row["final_pass"])
    avg_score = sum(float(row["answer_quality_score"]) for row in rows) / total if total else 0.0
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["category"])].append(row)

    lines = [
        "Ask Quality Evaluation Summary",
        "==============================",
        f"- created_at: {started}",
        f"- total: {total}",
        f"- pass_count: {pass_count}",
        f"- pass_rate: {(pass_count / total * 100) if total else 0:.1f}%",
        f"- avg_answer_quality_score: {avg_score:.2f}",
        "- llm_used: false",
        "- neo4j_write_executed: false",
        "",
        "By category:",
    ]
    for category, category_rows in sorted(by_category.items()):
        category_pass = sum(1 for row in category_rows if row["final_pass"])
        lines.append(f"- {category}: {category_pass}/{len(category_rows)} pass")

    failed = [row for row in rows if not row["final_pass"]]
    lines.extend(["", "Failed questions:"])
    if not failed:
        lines.append("- none")
    else:
        for row in failed:
            lines.append(f"- {row['id']} ({row['category']}): {row['failure_reason']}")

    common_reasons: dict[str, int] = defaultdict(int)
    for row in failed:
        for reason in str(row["failure_reason"]).split("; "):
            if reason:
                common_reasons[reason] += 1
    lines.extend(["", "Common failure reasons:"])
    if not common_reasons:
        lines.append("- none")
    else:
        for reason, count in sorted(common_reasons.items(), key=lambda item: (-item[1], item[0]))[:10]:
            lines.append(f"- {reason}: {count}")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Summary: {summary_path}")
    print(f"Status: {'PASS' if not failed else 'PASS_WITH_EVAL_FAILURES'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Graph-RAG /ask quality")
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--questions", default=None)
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    question_path = Path(args.questions).resolve() if args.questions else Path(__file__).with_name("eval_questions_safety_law.json")
    cases = json.loads(question_path.read_text(encoding="utf-8"))
    client = TestClient(app)
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for case in cases:
        row, sample = evaluate_case(client, case)
        rows.append(row)
        samples.append(sample)

    write_outputs(root, rows, samples, started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
