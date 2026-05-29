from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "generated_v5_current_mapped" / "question_rewrites"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def fact_index() -> dict[str, dict[str, str]]:
    rows = read_csv(ROOT / "generated_v4_current_strict" / "rescan_cases" / "case_fact_extraction_review.csv")
    return {row.get("case_id", ""): row for row in rows}


def compact_terms(value: str, limit: int = 3) -> list[str]:
    if not value:
        return []
    text = value.strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
            return [str(x) for x in data if x][:limit]
        except Exception:
            pass
    return [part.strip() for part in text.replace("|", ",").split(",") if part.strip()][:limit]


def make_question(item: dict, fact: dict[str, str]) -> tuple[str, str, str]:
    parts = []
    facts_used = {}
    for label, key in [
        ("사고유형", "accident_type"),
        ("작업", "work_type"),
        ("장소", "place"),
        ("피해자", "victim_type"),
        ("결과", "result"),
    ]:
        value = fact.get(key, "")
        if value:
            parts.append(f"{label}: {value}")
            facts_used[key] = value
    risk = compact_terms(fact.get("risk_factors", ""))
    issues = compact_terms(fact.get("legal_issues", ""))
    parties = compact_terms(fact.get("responsible_parties", ""))
    if risk:
        parts.append("위험요인: " + ", ".join(risk))
        facts_used["risk_factors"] = risk
    if parties:
        parts.append("책임주체: " + ", ".join(parties))
        facts_used["responsible_parties"] = parties
    if issues:
        parts.append("법적쟁점: " + ", ".join(issues))
        facts_used["legal_issues"] = issues

    case_name = item.get("case_name", "")
    if parts:
        prefix = "; ".join(parts)
        question = (
            f"{case_name} 사건에서 {prefix}이 문제된 경우, "
            "현행 산업안전보건법 및 중대재해처벌법 기준으로 검토할 주요 의무·처벌·양벌 조문은 무엇인가요?"
        )
        reason = "case facts from rescan review were inserted"
        risk_note = "중간: 사실관계 추출이 자동 규칙 기반이므로 사람이 문장 정확성을 확인해야 함"
    else:
        question = item.get("rewritten_question") or item.get("question") or (
            f"{case_name} 사건에서 현행 산업안전보건법 및 중대재해처벌법상 주요 조문은 무엇인가요?"
        )
        reason = "insufficient extracted facts; original question retained"
        risk_note = "높음: 구체 사실관계 부족"
    return question, json.dumps(facts_used, ensure_ascii=False), reason + " / " + risk_note


def transform_dataset(path: Path, out_path: Path, review_rows: list[dict]) -> list[dict]:
    data = load_json(path)
    facts = fact_index()
    out = []
    for item in data:
        case_id = str(item.get("source_case_id") or item.get("id") or "")
        fact = facts.get(case_id, {})
        rewritten, facts_used, reason = make_question(item, fact)
        new_item = dict(item)
        new_item["original_question"] = item.get("question") or item.get("rewritten_question") or ""
        new_item["rewritten_question"] = rewritten
        new_item["question_rewrite_status"] = "NEEDS_REVIEW"
        new_item["question_rewrite_review_reason"] = reason
        out.append(new_item)
        review_rows.append({
            "case_id": case_id,
            "original_question": new_item["original_question"],
            "rewritten_question": rewritten,
            "facts_used": facts_used,
            "expected_improvement_reason": "사건 사실관계가 질문에 들어가면 selected evidence/chain selector가 일반 벌칙 후보로 쏠리는 현상을 줄일 수 있음",
            "risk_of_over_specificity": reason,
            "review_required": True,
        })
    write_json(out_path, out)
    return out


def main() -> None:
    review_rows: list[dict] = []
    qa = transform_dataset(
        ROOT / "generated_v5_current_mapped" / "eval_ready" / "qa_eval_v5_current_mapped_ready.json",
        OUT_DIR / "qa_eval_v5_case_specific_candidates.json",
        review_rows,
    )
    checklist = transform_dataset(
        ROOT / "generated_v5_current_mapped" / "eval_ready" / "checklist_eval_v5_current_mapped_ready.json",
        OUT_DIR / "checklist_eval_v5_case_specific_candidates.json",
        review_rows,
    )
    write_csv(
        OUT_DIR / "question_rewrite_review.csv",
        review_rows,
        [
            "case_id",
            "original_question",
            "rewritten_question",
            "facts_used",
            "expected_improvement_reason",
            "risk_of_over_specificity",
            "review_required",
        ],
    )
    summary = {
        "qa_candidates": len(qa),
        "checklist_candidates": len(checklist),
        "review_required_count": len(review_rows),
        "note": "Question rewrites are candidates only. They do not overwrite v5 ready datasets.",
        "examples": review_rows[:5],
    }
    write_json(OUT_DIR / "question_rewrite_summary.json", summary)


if __name__ == "__main__":
    main()
