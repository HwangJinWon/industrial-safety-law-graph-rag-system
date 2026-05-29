from __future__ import annotations

import csv
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "generated_v6_case_scenario_eval"
OUT = BASE / "review_upgrade"

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

HEALTH_TERMS = ("질식", "중독", "산소결핍", "화학", "유해", "건강장해", "분진", "소음", "진동", "방사선", "감염", "밀폐")
CONTRACTOR_TERMS = ("도급", "수급", "관계수급", "하청", "협력업체", "위탁", "용역", "도급인")
SERIOUS_TERMS = ("중대재해처벌", "중대산업재해", "경영책임자", "대표이사")


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


def parse_json(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return default


def ref_article(ref: str) -> str:
    match = re.search(r"제(\d+(?:의\d+)?)조", ref or "")
    return match.group(1) if match else ""


def is_article_level(ref: str) -> bool:
    return bool(ref_article(ref)) and not re.search(r"제\d+항|제\d+호|[가-하]목", ref or "")


def slot_for_ref(ref: str) -> str:
    article = ref_article(ref)
    if "산업안전보건법" in ref and all(token not in ref for token in ("시행", "규칙", "기준")):
        if article == "38":
            return "primary_obligation"
        if article == "39":
            return "health_obligation"
        if article in {"63", "64"}:
            return "contractor_obligation"
        if article in {"167", "168"}:
            return "penalty"
        if article == "173":
            return "corporate_penalty"
        if article in {"1", "2", "3"}:
            return "definition_or_scope"
    if "중대재해" in ref and "시행" not in ref:
        if article in {"4", "5"}:
            return "serious_accident_obligation"
        if article == "6":
            return "penalty"
        if article == "7":
            return "corporate_penalty"
        if article in {"1", "2", "3"}:
            return "definition_or_scope"
    if "시행" in ref or "규칙" in ref or "기준" in ref:
        return "detail_rule"
    return "procedure_or_management"


def facts_text(fact: dict[str, str], refs: list[str] | None = None) -> str:
    return " ".join(
        str(fact.get(key, ""))
        for key in [
            "case_name",
            "accident_type",
            "result",
            "work_type",
            "place",
            "victim_type",
            "responsible_parties",
            "unsafe_condition",
            "legal_issue_summary",
            "extracted_fact_text",
        ]
    ) + " " + " ".join(refs or [])


def bundle_refs(bundle: dict[str, list[str]]) -> list[str]:
    return [ref for slot in SLOTS for ref in bundle.get(slot, [])]


def add_ref(bundle: dict[str, list[str]], slot: str, ref: str) -> None:
    bundle.setdefault(slot, [])
    if ref and ref not in bundle[slot]:
        bundle[slot].append(ref)


def fine_candidates_for_article(ref: str, fact: dict[str, str]) -> tuple[list[str], str, str]:
    result = fact.get("result", "")
    text = facts_text(fact, [ref])
    if "산업안전보건법" in ref and ref_article(ref) == "167" and result == "사망":
        return ["산업안전보건법 제167조 제1항"], "law_structure_result_type", "high"
    if "산업안전보건법" in ref and ref_article(ref) == "168":
        if result and result != "사망":
            return ["산업안전보건법 제168조 제1호"], "law_structure_non_death_violation", "medium"
        return ["산업안전보건법 제168조 제1호"], "law_structure_penalty_candidate", "medium"
    if "산업안전보건법" in ref and ref_article(ref) == "173":
        if "법인" in text or "회사" in text:
            return ["산업안전보건법 제173조 제1호", "산업안전보건법 제173조 제2호"], "corporate_context_and_law_structure", "medium"
        return [], "corporate_fine_ref_needs_actor_review", "low"
    if "중대재해" in ref and ref_article(ref) == "6":
        if result == "사망" or "중대산업재해" in text:
            return ["중대재해처벌법 제6조 제1항"], "law_structure_result_type", "high"
        return ["중대재해처벌법 제6조 제2항"], "law_structure_non_death_result", "medium"
    if "중대재해" in ref and ref_article(ref) == "7":
        if result == "사망" or "중대산업재해" in text:
            return ["중대재해처벌법 제7조 제1호"], "law_structure_result_type", "high"
        return ["중대재해처벌법 제7조 제2호"], "law_structure_non_death_result", "medium"
    return [], "no_fine_candidate_rule", "low"


def proposed_obligations(bundle: dict[str, list[str]], fact: dict[str, str], case_refs: list[str]) -> tuple[list[str], str, str]:
    text = facts_text(fact, bundle_refs(bundle) + case_refs)
    refs = bundle_refs(bundle) + case_refs
    proposals: list[str] = []
    basis: list[str] = []
    result = fact.get("result", "")
    if any("산업안전보건법 제38조" in ref or "구 산업안전보건법 제23조" in ref for ref in refs):
        proposals.append("산업안전보건법 제38조")
        basis.append("direct_or_old_safety_obligation_ref")
    elif result == "사망" and any(term in text for term in ("추락", "낙하", "끼임", "협착", "붕괴", "감전", "폭발", "안전조치")):
        proposals.append("산업안전보건법 제38조")
        basis.append("clear_safety_accident_facts")
    if any(term in text for term in HEALTH_TERMS) or any("산업안전보건법 제39조" in ref for ref in refs):
        proposals.append("산업안전보건법 제39조")
        basis.append("health_risk_or_ref")
    if any(term in text for term in CONTRACTOR_TERMS) or any("구 산업안전보건법 제29조" in ref for ref in refs):
        proposals.append("산업안전보건법 제63조")
        basis.append("contractor_relation_or_old_contractor_ref")
    if any(term in text for term in SERIOUS_TERMS) or any("중대재해처벌법 제4조" in ref for ref in refs):
        proposals.append("중대재해처벌법 제4조")
        basis.append("serious_accident_issue_or_ref")
    if any(term in text for term in CONTRACTOR_TERMS) and any("중대재해" in ref for ref in refs):
        proposals.append("중대재해처벌법 제5조")
        basis.append("serious_accident_contractor_context")
    proposals = list(dict.fromkeys(proposals))
    confidence = "high" if any(key in basis for key in ("direct_or_old_safety_obligation_ref", "serious_accident_issue_or_ref")) else "medium" if proposals else "low"
    return proposals, ";".join(basis), confidence


def main() -> None:
    ready = read_json(BASE / "dataset" / "case_scenario_eval_ready.json")
    grade_rows = {row["id"]: row for row in read_csv(BASE / "dataset" / "graded" / "case_scenario_grade_review.csv")}
    facts = {row["case_id"]: row for row in read_csv(BASE / "extraction" / "case_facts_69_conservative.csv")}
    law_refs_rows = read_csv(BASE / "extraction" / "case_law_refs_69.csv")
    law_refs_by_case: dict[str, list[str]] = {}
    for row in law_refs_rows:
        law_refs_by_case.setdefault(row["case_id"], []).append(row.get("normalized_ref") or row.get("raw_law_ref") or "")

    reviewed_ready: list[dict[str, Any]] = []
    auxiliary: list[dict[str, Any]] = []
    review_only: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    a2_review: list[dict[str, Any]] = []
    a3_review: list[dict[str, Any]] = []

    for item in ready:
        case_id = str(item.get("id", ""))
        grade_row = grade_rows.get(case_id, {})
        original_grade = grade_row.get("audit_grade", item.get("v6_audit_grade", ""))
        fact = facts.get(case_id, {})
        case_refs = law_refs_by_case.get(case_id, [])
        updated = deepcopy(item)
        bundle = deepcopy(updated.get("expected_legal_bundle") or {})
        new_grade = original_grade
        action = "KEEP_A1" if original_grade == "A1_STRICT" else "KEEP_A2" if original_grade == "A2_ARTICLE_LEVEL_AUX" else "KEEP_A3"
        reason = grade_row.get("review_reason", "")
        review_required = original_grade == "A3_REVIEW_ONLY"

        if original_grade == "A2_ARTICLE_LEVEL_AUX":
            article_refs = [ref for ref in bundle_refs(bundle) if is_article_level(ref) and slot_for_ref(ref) in {"penalty", "corporate_penalty"}]
            promoted_refs: list[str] = []
            bases: list[str] = []
            confidences: list[str] = []
            for ref in article_refs:
                candidates, basis, confidence = fine_candidates_for_article(ref, fact)
                promoted_refs.extend(candidates)
                bases.append(f"{ref}:{basis}")
                confidences.append(confidence)
                a2_review.append({
                    "case_id": case_id,
                    "case_name": item.get("case_name", ""),
                    "original_article_level_ref": ref,
                    "candidate_fine_refs": json.dumps(candidates, ensure_ascii=False),
                    "candidate_fine_texts": "",
                    "result_type": fact.get("result", ""),
                    "law_role": slot_for_ref(ref),
                    "upgrade_basis": basis,
                    "confidence": confidence,
                    "recommended_action": "PROMOTE_TO_A1_WITH_FINE_REF" if candidates and confidence in {"high", "medium"} else "KEEP_A2_ARTICLE_AUX",
                    "review_reason": "Fine ref candidate derived from result type and statutory penalty structure; reviewer should confirm actor/result details.",
                })
            if promoted_refs and all(conf in {"high", "medium"} for conf in confidences):
                for ref in promoted_refs:
                    add_ref(bundle, slot_for_ref(ref), ref)
                new_grade = "A1_STRICT"
                action = "A2_TO_A1"
                reason = "article-level penalty/corporate GT supplemented with fine refs using result type and statutory structure"
                review_required = False
            else:
                new_grade = "A2_ARTICLE_AUX"
                action = "KEEP_A2"
                review_required = bool(article_refs)
        elif original_grade == "A3_REVIEW_ONLY":
            props, basis, confidence = proposed_obligations(bundle, fact, case_refs)
            penalty_or_corp = bool(bundle.get("penalty") or bundle.get("corporate_penalty"))
            for ref in props:
                add_ref(bundle, slot_for_ref(ref), ref)
            proposed_penalty: list[str] = []
            proposed_corp: list[str] = []
            if fact.get("result") == "사망":
                if any(ref.startswith("산업안전보건법 제38조") or ref.startswith("산업안전보건법 제39조") or ref.startswith("산업안전보건법 제63조") for ref in props):
                    proposed_penalty.append("산업안전보건법 제167조 제1항")
                    proposed_corp.extend(["산업안전보건법 제173조 제1호", "산업안전보건법 제173조 제2호"])
                if any(ref.startswith("중대재해처벌법 제4조") or ref.startswith("중대재해처벌법 제5조") for ref in props):
                    proposed_penalty.append("중대재해처벌법 제6조 제1항")
                    proposed_corp.append("중대재해처벌법 제7조 제1호")
            for ref in proposed_penalty:
                add_ref(bundle, "penalty", ref)
            for ref in proposed_corp:
                add_ref(bundle, "corporate_penalty", ref)
            can_promote_a1 = bool(props) and confidence == "high" and (penalty_or_corp or proposed_penalty or proposed_corp) and fact.get("result") not in {"", "unknown"}
            can_promote_a2 = bool(props) and confidence in {"high", "medium"} and fact.get("result") not in {"", "unknown"}
            if can_promote_a1:
                new_grade = "A1_STRICT"
                action = "A3_TO_A1"
                reason = "missing core obligation supplemented from direct/old ref or strong case facts plus penalty/corporate structure"
                review_required = False
            elif can_promote_a2:
                new_grade = "A2_ARTICLE_AUX"
                action = "A3_TO_A2"
                reason = "core obligation candidates are plausible but require article-level auxiliary treatment or reviewer confirmation"
                review_required = True
            else:
                new_grade = "A3_REVIEW_ONLY"
                action = "KEEP_A3"
                reason = "insufficient evidence for automatic obligation slot promotion"
                review_required = True
            a3_review.append({
                "case_id": case_id,
                "case_name": item.get("case_name", ""),
                "case_facts_summary": facts_text(fact)[:1200],
                "accident_type": fact.get("accident_type", ""),
                "result": fact.get("result", ""),
                "contractor_relation": fact.get("contractor_relation", ""),
                "health_issue": fact.get("health_issue", ""),
                "serious_accident_issue": fact.get("serious_accident_issue", ""),
                "original_law_refs": json.dumps(case_refs, ensure_ascii=False),
                "existing_expected_bundle": json.dumps(item.get("expected_legal_bundle", {}), ensure_ascii=False),
                "missing_core_slots": json.dumps(["primary_obligation", "health_obligation", "contractor_obligation", "serious_accident_obligation"], ensure_ascii=False),
                "proposed_core_obligation_refs": json.dumps(props, ensure_ascii=False),
                "proposed_penalty_refs": json.dumps(proposed_penalty, ensure_ascii=False),
                "proposed_corporate_penalty_refs": json.dumps(proposed_corp, ensure_ascii=False),
                "mapping_basis": basis,
                "evidence_context": facts_text(fact, case_refs)[:1200],
                "confidence": confidence,
                "recommended_action": "PROMOTE_TO_A1_STRICT" if can_promote_a1 else "PROMOTE_TO_A2_AUX" if can_promote_a2 else "KEEP_A3_REVIEW_ONLY",
                "review_reason": reason,
            })

        updated["expected_legal_bundle"] = bundle
        updated["reviewed_grade"] = new_grade
        updated["reviewed_upgrade_action"] = action
        updated["reviewed_upgrade_reason"] = reason
        updated["reviewed_bundle_source_reason"] = "v6_reviewed_upgrade" if action not in {"KEEP_A1", "KEEP_A2", "KEEP_A3"} else "original_v6_bundle"

        if new_grade == "A1_STRICT":
            reviewed_ready.append(updated)
        elif new_grade == "A2_ARTICLE_AUX":
            auxiliary.append(updated)
        else:
            review_only.append(updated)

        decisions.append({
            "case_id": case_id,
            "case_name": item.get("case_name", ""),
            "original_grade": original_grade,
            "new_grade": new_grade,
            "upgrade_action": action,
            "reason": reason,
            "facts_confidence": fact.get("fact_confidence", ""),
            "mapping_confidence": "auto_high_or_medium" if action in {"A2_TO_A1", "A3_TO_A1"} else "review",
            "gt_bundle_confidence": "strict" if new_grade == "A1_STRICT" else "auxiliary" if new_grade == "A2_ARTICLE_AUX" else "review_only",
            "old_refs": json.dumps([ref for ref in case_refs if "구 " in ref], ensure_ascii=False),
            "current_refs": json.dumps([ref for ref in case_refs if "구 " not in ref], ensure_ascii=False),
            "expected_legal_bundle_json": json.dumps(bundle, ensure_ascii=False),
            "review_required": str(review_required),
            "reviewer_notes": reason,
        })

    write_csv(OUT / "a2_fine_ref_upgrade_review.csv", a2_review, [
        "case_id", "case_name", "original_article_level_ref", "candidate_fine_refs", "candidate_fine_texts",
        "result_type", "law_role", "upgrade_basis", "confidence", "recommended_action", "review_reason",
    ])
    write_csv(OUT / "a3_core_obligation_upgrade_review.csv", a3_review, [
        "case_id", "case_name", "case_facts_summary", "accident_type", "result", "contractor_relation",
        "health_issue", "serious_accident_issue", "original_law_refs", "existing_expected_bundle",
        "missing_core_slots", "proposed_core_obligation_refs", "proposed_penalty_refs",
        "proposed_corporate_penalty_refs", "mapping_basis", "evidence_context", "confidence",
        "recommended_action", "review_reason",
    ])
    write_csv(OUT / "v6_case_upgrade_decisions.csv", decisions, [
        "case_id", "case_name", "original_grade", "new_grade", "upgrade_action", "reason",
        "facts_confidence", "mapping_confidence", "gt_bundle_confidence", "old_refs", "current_refs",
        "expected_legal_bundle_json", "review_required", "reviewer_notes",
    ])
    write_json(OUT / "v6_reviewed_case_scenario_eval_ready.json", reviewed_ready)
    write_json(OUT / "v6_reviewed_case_scenario_eval_auxiliary.json", auxiliary)
    write_json(OUT / "v6_reviewed_case_scenario_eval_review_only.json", review_only)

    actions = Counter(row["upgrade_action"] for row in decisions)
    summary = {
        "original_grade_counts": dict(Counter(row["original_grade"] for row in decisions)),
        "new_grade_counts": dict(Counter(row["new_grade"] for row in decisions)),
        "upgrade_action_counts": dict(actions),
        "promoted_A2_to_A1_count": actions.get("A2_TO_A1", 0),
        "promoted_A3_to_A1_count": actions.get("A3_TO_A1", 0),
        "promoted_A3_to_A2_count": actions.get("A3_TO_A2", 0),
        "ready_sample_count": len(reviewed_ready),
        "auxiliary_sample_count": len(auxiliary),
        "review_only_sample_count": len(review_only),
        "note": "Only cases with explicit article-level penalty upgrade basis or strong case-fact/core-obligation basis were promoted automatically.",
    }
    write_json(OUT / "v6_reviewed_upgrade_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
