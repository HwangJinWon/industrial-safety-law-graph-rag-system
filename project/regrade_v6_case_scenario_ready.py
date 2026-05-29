from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated_v6_case_scenario_eval"

SLOTS = [
    "primary_obligation",
    "health_obligation",
    "contractor_obligation",
    "serious_accident_obligation",
    "detail_rule",
    "penalty",
    "corporate_penalty",
    "definition_or_scope",
    "administrative_fine",
    "procedure_or_management",
]

OBLIGATION_SLOTS = {
    "primary_obligation",
    "health_obligation",
    "contractor_obligation",
    "serious_accident_obligation",
}

HEALTH_TERMS = ("질식", "중독", "산소결핍", "화학", "유해", "건강장해", "분진", "소음", "진동", "방사선", "감염", "밀폐")
CONTRACTOR_TERMS = ("도급", "수급", "관계수급", "하청", "협력업체", "위탁", "용역", "도급인")
SERIOUS_TERMS = ("중대재해처벌", "중대산업재해", "경영책임자", "대표이사")
SCOPE_TERMS = ("상시 근로자", "상시근로자", "50명", "적용범위", "적용 여부", "유예", "시행일", "부칙")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_json_list(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def parse_json_dict(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def compact_text(*values: Any) -> str:
    return " ".join(str(v or "") for v in values)


def conservative_flags(fact: dict[str, str]) -> dict[str, str]:
    text = compact_text(
        fact.get("case_name"),
        fact.get("accident_type"),
        fact.get("work_type"),
        fact.get("place"),
        fact.get("victim_type"),
        fact.get("responsible_parties"),
        fact.get("unsafe_condition"),
        fact.get("risk_factors"),
        fact.get("legal_issue_summary"),
        fact.get("extracted_fact_text"),
    )
    result = dict(fact)
    result["health_issue_original"] = fact.get("health_issue", "")
    result["contractor_relation_original"] = fact.get("contractor_relation", "")
    result["serious_accident_issue_original"] = fact.get("serious_accident_issue", "")
    result["scope_issue_original"] = fact.get("scope_issue", "")
    result["health_issue"] = str(any(term in text for term in HEALTH_TERMS))
    result["contractor_relation"] = str(any(term in text for term in CONTRACTOR_TERMS))
    result["serious_accident_issue"] = str(any(term in text for term in SERIOUS_TERMS))
    result["scope_issue"] = str(any(term in text for term in SCOPE_TERMS))
    return result


def bundle_has_obligation(bundle: dict[str, list[str]]) -> bool:
    return any(bundle.get(slot) for slot in OBLIGATION_SLOTS)


def infer_obligation_review_candidates(bundle: dict[str, list[str]], fact: dict[str, str]) -> list[str]:
    candidates: list[str] = []
    refs = " ".join(ref for refs in bundle.values() for ref in refs)
    text = compact_text(fact.get("accident_type"), fact.get("legal_issue_summary"), fact.get("extracted_fact_text"), refs)
    if "산업안전보건법" in refs or "안전조치" in text or fact.get("result") == "사망":
        candidates.append("산업안전보건법 제38조")
    if any(term in text for term in HEALTH_TERMS):
        candidates.append("산업안전보건법 제39조")
    if any(term in text for term in CONTRACTOR_TERMS):
        candidates.extend(["산업안전보건법 제63조", "산업안전보건법 제64조"])
    if "중대재해" in text or "중대재해처벌" in text or "중대재해처벌법" in refs:
        candidates.append("중대재해처벌법 제4조")
        if any(term in text for term in CONTRACTOR_TERMS):
            candidates.append("중대재해처벌법 제5조")
    return list(dict.fromkeys(candidates))


def grade_case(audit_issues: list[str], bundle: dict[str, list[str]]) -> tuple[str, str]:
    issue_set = set(audit_issues)
    if "no_core_selected_slot" in issue_set:
        return "A3_REVIEW_ONLY", "core obligation slot is missing; obligation candidates must be reviewed before strict evaluation"
    if "article_level_penalty_gt" in issue_set:
        return "A2_ARTICLE_LEVEL_AUX", "penalty GT is article-level; use article-level auxiliary evaluation and keep fine-level as diagnostic"
    if issue_set == {"ok"} or not issue_set:
        return "A1_STRICT", "GT bundle has core obligation and no audit issue requiring relaxed comparison"
    return "A3_REVIEW_ONLY", "GT bundle has unresolved audit issues"


def main() -> None:
    dataset = read_json(OUT / "dataset" / "case_scenario_eval_ready.json")
    audit_rows = {row["id"]: row for row in read_csv(OUT / "mapping" / "case_gt_bundle_audit.csv")}
    fact_rows = {row["case_id"]: conservative_flags(row) for row in read_csv(OUT / "extraction" / "case_facts_69.csv")}

    a1: list[dict[str, Any]] = []
    a2: list[dict[str, Any]] = []
    a3: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    facts_out = list(fact_rows.values())

    for item in dataset:
        case_id = str(item.get("id", ""))
        audit = audit_rows.get(case_id, {})
        fact = fact_rows.get(case_id, {})
        issues = parse_json_list(audit.get("audit_issues", "[]"))
        bundle = item.get("expected_legal_bundle") or parse_json_dict(audit.get("expected_legal_bundle", "{}"))
        grade, reason = grade_case(issues, bundle)
        updated = dict(item)
        updated["case_facts"] = {
            **(item.get("case_facts") or {}),
            "health_issue": fact.get("health_issue", (item.get("case_facts") or {}).get("health_issue", "")),
            "contractor_relation": fact.get("contractor_relation", (item.get("case_facts") or {}).get("contractor_relation", "")),
            "serious_accident_issue": fact.get("serious_accident_issue", (item.get("case_facts") or {}).get("serious_accident_issue", "")),
            "scope_issue": fact.get("scope_issue", (item.get("case_facts") or {}).get("scope_issue", "")),
        }
        updated["v6_audit_grade"] = grade
        updated["v6_audit_reason"] = reason
        updated["audit_issues"] = issues

        obligation_candidates = infer_obligation_review_candidates(bundle, fact)
        review_rows.append({
            "id": case_id,
            "case_name": item.get("case_name", ""),
            "audit_grade": grade,
            "audit_issues": json.dumps(issues, ensure_ascii=False),
            "populated_slots": audit.get("populated_slots", ""),
            "gt_ref_count": audit.get("gt_ref_count", ""),
            "recommended_obligation_review_candidates": json.dumps(obligation_candidates, ensure_ascii=False),
            "review_reason": reason,
            "health_issue_conservative": fact.get("health_issue", ""),
            "contractor_relation_conservative": fact.get("contractor_relation", ""),
            "serious_accident_issue_conservative": fact.get("serious_accident_issue", ""),
            "scope_issue_conservative": fact.get("scope_issue", ""),
        })
        if grade == "A1_STRICT":
            a1.append(updated)
        elif grade == "A2_ARTICLE_LEVEL_AUX":
            a2.append(updated)
        else:
            a3.append(updated)

    out_dir = OUT / "dataset" / "graded"
    write_json(out_dir / "case_scenario_eval_A1_strict.json", a1)
    write_json(out_dir / "case_scenario_eval_A2_article_aux.json", a2)
    write_json(out_dir / "case_scenario_eval_A1_A2_aux.json", a1 + a2)
    write_json(out_dir / "case_scenario_eval_A3_review_only.json", a3)
    write_csv(OUT / "extraction" / "case_facts_69_conservative.csv", facts_out, list(facts_out[0].keys()) if facts_out else [])
    write_csv(out_dir / "case_scenario_grade_review.csv", review_rows, [
        "id",
        "case_name",
        "audit_grade",
        "audit_issues",
        "populated_slots",
        "gt_ref_count",
        "recommended_obligation_review_candidates",
        "review_reason",
        "health_issue_conservative",
        "contractor_relation_conservative",
        "serious_accident_issue_conservative",
        "scope_issue_conservative",
    ])
    summary = {
        "input_ready_count": len(dataset),
        "grade_counts": dict(Counter(row["audit_grade"] for row in review_rows)),
        "a1_strict_path": str(out_dir / "case_scenario_eval_A1_strict.json"),
        "a1_a2_aux_path": str(out_dir / "case_scenario_eval_A1_A2_aux.json"),
        "a3_review_only_path": str(out_dir / "case_scenario_eval_A3_review_only.json"),
        "policy": {
            "A1_STRICT": "audit ok; strict evaluation target without article-level penalty relaxation",
            "A2_ARTICLE_LEVEL_AUX": "article-level penalty GT; evaluate article level separately from fine level",
            "A3_REVIEW_ONLY": "missing core obligation or unresolved audit issue; not used in strict/aux evaluation",
        },
    }
    write_json(out_dir / "case_scenario_grade_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
