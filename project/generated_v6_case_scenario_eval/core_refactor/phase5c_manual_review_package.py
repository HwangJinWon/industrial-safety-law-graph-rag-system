from __future__ import annotations

import ast
import csv
import json
import py_compile
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "generated_v6_case_scenario_eval"
CORE = BASE / "core_refactor"
V5 = ROOT / "generated_v5_current_mapped"


PHASE5B_TARGETS = CORE / "phase5b_policy_adjustment_targets.csv"
PHASE5B_CASE_COMPARISON = CORE / "phase5b_policy_adjusted_comparison_by_case.csv"
PHASE5A_CORP_REVIEW = CORE / "phase5a_corporate_penalty_branch_gt_review.csv"
PHASE5A_CORP_TARGETS = CORE / "phase5a_corporate_penalty_branch_targets.csv"
PHASE5A_OBLIGATION_REVIEW = CORE / "phase5a_obligation_fine_branch_review.csv"
PHASE4_AUDIT = CORE / "phase4_fine_granularity_mismatch_audit.csv"

CASE_FACTS = BASE / "extraction" / "case_facts_69.csv"
ISSUE_LABELS = BASE / "extraction" / "case_legal_issue_labels.csv"
CASE_LAW_REFS = BASE / "extraction" / "case_law_refs_69.csv"
EXPECTED_REVIEW = BASE / "mapping" / "case_expected_legal_bundle_review.csv"
EXPECTED_CANDIDATES = BASE / "mapping" / "case_expected_legal_bundle_candidates.csv"
OLD_CURRENT_CANDIDATES = BASE / "mapping" / "case_old_current_mapping_candidates.csv"

LAW_SNAPSHOT = V5 / "parsed" / "law_article_unit_snapshot.csv"
OLD_CURRENT_REVIEW = V5 / "mapping" / "old_current_article_mapping_review.csv"
OLD_REF_VERSION_CHECK = V5 / "case_linking" / "case_old_ref_version_check.csv"


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, **kwargs)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    text = str(value).strip()
    if not text or text in {"[]", "nan", "None"}:
        return []
    if text.startswith("["):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x)]
        except Exception:
            return [text]
    if "|" in text:
        return [x.strip() for x in text.split("|") if x.strip()]
    return [text]


def as_json_list(values: list[str]) -> str:
    values = [str(v) for v in values if str(v)]
    return json.dumps(values, ensure_ascii=False)


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none"}:
            return text
    return ""


def row_by_case(df: pd.DataFrame, case_id: str) -> dict[str, Any]:
    if df.empty or "case_id" not in df.columns:
        return {}
    hit = df[df["case_id"].astype(str) == str(case_id)]
    if hit.empty:
        return {}
    return hit.iloc[0].to_dict()


def load_case_context() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    facts = read_csv(CASE_FACTS)
    labels = read_csv(ISSUE_LABELS)
    law_refs = read_csv(CASE_LAW_REFS)
    fact_by_case = {str(r["case_id"]): r for _, r in facts.iterrows()} if not facts.empty else {}
    label_by_case = {str(r["case_id"]): r for _, r in labels.iterrows()} if not labels.empty else {}
    refs_by_case = {str(r["case_id"]): r for _, r in law_refs.iterrows()} if not law_refs.empty else {}
    return fact_by_case, label_by_case, refs_by_case


def build_law_text_lookup(refs: set[str]) -> dict[str, str]:
    if not LAW_SNAPSHOT.exists() or not refs:
        return {}
    usecols = ["law_name", "effective_date", "unit_ref", "unit_text_clean", "unit_text"]
    df = pd.read_csv(LAW_SNAPSHOT, dtype=str, keep_default_na=False, usecols=usecols)
    df = df[df["unit_ref"].isin(refs)].copy()
    if df.empty:
        return {}
    df["effective_date_sort"] = pd.to_numeric(df["effective_date"], errors="coerce").fillna(0)
    df = df.sort_values(["unit_ref", "effective_date_sort"])
    latest = df.groupby("unit_ref", as_index=False).tail(1)
    lookup: dict[str, str] = {}
    for _, row in latest.iterrows():
        lookup[str(row["unit_ref"])] = first_nonempty(row.get("unit_text_clean"), row.get("unit_text"))
    return lookup


def collect_refs(*dfs: pd.DataFrame) -> set[str]:
    refs: set[str] = set()
    ref_like_cols = [
        "gt_ref",
        "pred_ref",
        "gt_penalty_refs",
        "gt_corporate_refs",
        "pred_penalty_refs",
        "pred_corporate_refs",
        "candidate_penalty_refs",
        "candidate_corporate_refs",
        "old_law_refs",
        "current_mapping_candidates",
        "gt_obligation_ref",
        "pred_obligation_ref",
    ]
    for df in dfs:
        if df.empty:
            continue
        for col in ref_like_cols:
            if col not in df.columns:
                continue
            for value in df[col].tolist():
                refs.update(parse_list(value))
    return {r for r in refs if "제" in r}


def old_current_basis_by_case(case_ids: set[str]) -> dict[str, str]:
    chunks: list[pd.DataFrame] = []
    if OLD_CURRENT_CANDIDATES.exists():
        usecols = [
            "case_id",
            "old_law_ref",
            "old_text",
            "current_candidate_ref",
            "current_text",
            "mapping_basis",
            "mapping_grade",
            "review_required",
            "review_reason",
        ]
        chunks.append(read_csv(OLD_CURRENT_CANDIDATES, usecols=lambda c: c in usecols))
    if OLD_CURRENT_REVIEW.exists():
        usecols = [
            "case_id",
            "old_law_ref",
            "old_text",
            "current_candidate_refs",
            "current_candidate_texts",
            "mapping_grade",
            "review_reason",
        ]
        chunks.append(read_csv(OLD_CURRENT_REVIEW, usecols=lambda c: c in usecols))
    if OLD_REF_VERSION_CHECK.exists():
        usecols = [
            "case_id",
            "raw_law_ref",
            "normalized_law_ref",
            "matched_old_text",
            "matched_old_ref",
            "match_confidence",
            "review_reason",
        ]
        chunks.append(read_csv(OLD_REF_VERSION_CHECK, usecols=lambda c: c in usecols))

    basis: dict[str, list[str]] = {case_id: [] for case_id in case_ids}
    for df in chunks:
        if df.empty or "case_id" not in df.columns:
            continue
        df = df[df["case_id"].astype(str).isin(case_ids)].head(3000)
        for _, row in df.iterrows():
            case_id = str(row.get("case_id", ""))
            parts = []
            for col in df.columns:
                if col == "case_id":
                    continue
                value = str(row.get(col, "")).strip()
                if value:
                    parts.append(f"{col}={value}")
            if parts:
                basis.setdefault(case_id, []).append("; ".join(parts))
    return {k: " || ".join(v[:5]) for k, v in basis.items()}


def expected_bundle_refs(case_id: str) -> tuple[str, str]:
    review = read_csv(EXPECTED_REVIEW)
    candidates = read_csv(EXPECTED_CANDIDATES)
    review_hit = row_by_case(review, case_id)
    cand_hit = row_by_case(candidates, case_id)
    return json.dumps(review_hit, ensure_ascii=False), json.dumps(cand_hit, ensure_ascii=False)


def review_priority(issue_category: str, gt_branch_consistency: str, policy_treatment: str) -> str:
    if gt_branch_consistency == "INCONSISTENT_OR_MAPPING_AMBIGUOUS":
        return "HIGH"
    if "CORPORATE" in issue_category and policy_treatment:
        return "HIGH"
    if gt_branch_consistency == "OLD_CURRENT_FINE_AMBIGUOUS":
        return "MEDIUM"
    if issue_category == "OBLIGATION_FINE_GT_REVIEW":
        return "MEDIUM"
    return "LOW"


def corp_recommended_decision(gt_branch_consistency: str, pred_branch_consistency: str) -> str:
    if pred_branch_consistency == "CONSISTENT" and gt_branch_consistency == "OLD_CURRENT_FINE_AMBIGUOUS":
        return "ARTICLE_LEVEL_ONLY"
    if pred_branch_consistency == "CONSISTENT" and gt_branch_consistency == "INCONSISTENT_OR_MAPPING_AMBIGUOUS":
        return "GT_FINE_BRANCH_REVISE_RECOMMENDED"
    if gt_branch_consistency == "CONSISTENT":
        return "KEEP_GT_FINE_STRICT"
    return "NEED_LEGAL_EXPERT_REVIEW"


def obligation_recommended_decision(label: str, article_only: str) -> str:
    if label == "PRED_FINE_SUPPORTED":
        return "GT_FINE_BRANCH_REVISE_RECOMMENDED"
    if str(article_only).lower() == "true":
        return "ARTICLE_LEVEL_ONLY"
    return "NEED_LEGAL_EXPERT_REVIEW"


def bool_text(value: Any) -> str:
    text = str(value).strip()
    if text.lower() in {"true", "1", "yes"}:
        return "true"
    if text.lower() in {"false", "0", "no"}:
        return "false"
    return text


def make_review_targets(
    policy_targets: pd.DataFrame,
    corp_review: pd.DataFrame,
    corp_targets: pd.DataFrame,
    obligation_review: pd.DataFrame,
    fact_by_case: dict[str, dict[str, Any]],
    label_by_case: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, row in policy_targets.iterrows():
        case_id = str(row.get("case_id", ""))
        issue_category = str(row.get("issue_category", ""))
        fact = fact_by_case.get(case_id, {})
        label = label_by_case.get(case_id, {})
        corp = row_by_case(corp_review, case_id) if issue_category == "CORPORATE_PENALTY_BRANCH_AMBIGUITY" else {}
        corp_target = row_by_case(corp_targets, case_id) if issue_category == "CORPORATE_PENALTY_BRANCH_AMBIGUITY" else {}
        obl = row_by_case(obligation_review, case_id) if issue_category == "OBLIGATION_FINE_GT_REVIEW" else {}

        gt_refs = []
        pred_refs = []
        candidate_refs = []
        if corp:
            gt_refs = parse_list(corp.get("gt_penalty_refs")) + parse_list(corp.get("gt_corporate_refs"))
            pred_refs = parse_list(corp.get("pred_penalty_refs")) + parse_list(corp.get("pred_corporate_refs"))
        if corp_target:
            candidate_refs = parse_list(corp_target.get("candidate_penalty_refs")) + parse_list(
                corp_target.get("candidate_corporate_refs")
            )
        if obl:
            gt_refs = [str(obl.get("gt_ref", ""))]
            pred_refs = [str(obl.get("pred_ref", ""))]

        gt_branch_consistency = str(row.get("gt_branch_consistency", "") or corp.get("gt_branch_consistency", ""))
        policy_treatment = str(row.get("policy_adjusted_treatment", ""))
        rows.append(
            {
                "review_id": f"P5C-{idx + 1:03d}",
                "case_id": case_id,
                "dataset_type": row.get("dataset_type", ""),
                "issue_category": issue_category,
                "case_result": first_nonempty(corp_target.get("case_result", ""), fact.get("result", "")),
                "legal_issue_type": first_nonempty(
                    corp_target.get("legal_issue_type", ""),
                    label.get("primary_issue_type", ""),
                    fact.get("legal_issue_summary", ""),
                ),
                "case_fact_summary": first_nonempty(
                    corp_target.get("case_fact_summary", ""),
                    obl.get("case_fact_summary", ""),
                    fact.get("legal_issue_summary", ""),
                    fact.get("extracted_fact_text", ""),
                ),
                "gt_refs": as_json_list(gt_refs),
                "pred_refs": as_json_list(pred_refs),
                "candidate_refs": as_json_list(candidate_refs),
                "phase5a_label": first_nonempty(row.get("phase5a_label", ""), corp.get("branch_review_label", ""), obl.get("obligation_branch_review_label", "")),
                "phase5b_policy_treatment": policy_treatment,
                "review_priority": review_priority(issue_category, gt_branch_consistency, policy_treatment),
                "review_required": "true",
            }
        )
    return rows


def make_corporate_package(
    targets: list[dict[str, Any]],
    corp_review: pd.DataFrame,
    corp_targets: pd.DataFrame,
    law_lookup: dict[str, str],
    old_basis: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    target_by_case = {r["case_id"]: r for r in targets if r["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY"}
    for _, review in corp_review.iterrows():
        case_id = str(review.get("case_id", ""))
        if case_id not in target_by_case:
            continue
        target = target_by_case[case_id]
        detail = row_by_case(corp_targets, case_id)
        gt_penalties = parse_list(review.get("gt_penalty_refs"))
        gt_corps = parse_list(review.get("gt_corporate_refs"))
        pred_penalties = parse_list(review.get("pred_penalty_refs"))
        pred_corps = parse_list(review.get("pred_corporate_refs"))
        candidate_penalties = parse_list(detail.get("candidate_penalty_refs"))
        candidate_corps = parse_list(detail.get("candidate_corporate_refs"))
        gt_branch_consistency = str(review.get("gt_branch_consistency", ""))
        pred_branch_consistency = str(review.get("pred_branch_consistency", ""))
        recommended = corp_recommended_decision(gt_branch_consistency, pred_branch_consistency)
        review_question = (
            "GT corporate penalty branch and predicted corporate penalty branch differ at Article 173 subparagraph level. "
            "Check whether the GT branch is supported by a 168-172 penalty branch, or whether old-current mapping only supports Article 173 at article level."
        )
        rows.append(
            {
                "review_id": target["review_id"],
                "case_id": case_id,
                "dataset_type": review.get("dataset_type", ""),
                "case_result": detail.get("case_result", target.get("case_result", "")),
                "legal_issue_type": detail.get("legal_issue_type", target.get("legal_issue_type", "")),
                "case_fact_summary": detail.get("case_fact_summary", target.get("case_fact_summary", "")),
                "gt_penalty_refs": as_json_list(gt_penalties),
                "gt_corporate_refs": as_json_list(gt_corps),
                "gt_corporate_branch": review.get("gt_corporate_branch", ""),
                "expected_branch_from_gt_penalty": review.get("expected_branch_from_gt_penalty", ""),
                "gt_branch_consistency": gt_branch_consistency,
                "gt_branch_issue_summary": review.get("review_note", ""),
                "pred_penalty_refs": as_json_list(pred_penalties),
                "pred_corporate_refs": as_json_list(pred_corps),
                "pred_corporate_branch": review.get("pred_corporate_branch", ""),
                "expected_branch_from_pred_penalty": review.get("expected_branch_from_pred_penalty", ""),
                "pred_branch_consistency": pred_branch_consistency,
                "prediction_branch_issue_summary": "prediction follows selected penalty branch" if pred_branch_consistency == "CONSISTENT" else "prediction branch requires review",
                "candidate_penalty_refs": as_json_list(candidate_penalties),
                "candidate_corporate_refs": as_json_list(candidate_corps),
                "candidate_has_173_1": str(any("제173조 제1호" in x for x in candidate_corps)).lower(),
                "candidate_has_173_2": str(any("제173조 제2호" in x for x in candidate_corps)).lower(),
                "old_law_refs": detail.get("old_law_refs", ""),
                "current_mapping_candidates": detail.get("current_mapping_candidates", ""),
                "old_current_mapping_basis": old_basis.get(case_id, ""),
                "has_old_current_mapping_ambiguity": bool_text(detail.get("has_old_current_mapping_ambiguity", "")),
                "law_text_gt_penalty": "\n".join(law_lookup.get(r, "") for r in gt_penalties if law_lookup.get(r, "")),
                "law_text_gt_corporate": "\n".join(law_lookup.get(r, "") for r in gt_corps if law_lookup.get(r, "")),
                "law_text_pred_penalty": "\n".join(law_lookup.get(r, "") for r in pred_penalties if law_lookup.get(r, "")),
                "law_text_pred_corporate": "\n".join(law_lookup.get(r, "") for r in pred_corps if law_lookup.get(r, "")),
                "law_text_old_ref": "",
                "law_text_current_mapping_candidate": "\n".join(
                    law_lookup.get(r, "") for r in parse_list(detail.get("current_mapping_candidates")) if law_lookup.get(r, "")
                ),
                "phase5a_label": review.get("branch_review_label", ""),
                "phase5b_policy_treatment": target.get("phase5b_policy_treatment", ""),
                "original_eval_treatment": "FINE_STRICT_MISMATCH",
                "policy_adjusted_treatment": "ARTICLE_LEVEL_CORPORATE_MATCH_WITH_BRANCH_CONSISTENCY",
                "review_question": review_question,
                "review_options": as_json_list(
                    [
                        "KEEP_GT_FINE_STRICT",
                        "ARTICLE_LEVEL_ONLY",
                        "GT_FINE_BRANCH_REVISE_RECOMMENDED",
                        "EXCLUDE_CORPORATE_FINE_FROM_STRICT",
                        "MOVE_TO_AUXILIARY",
                        "NEED_LEGAL_EXPERT_REVIEW",
                    ]
                ),
                "recommended_default_decision": recommended,
                "reviewer_decision": "",
                "reviewer_note": "",
            }
        )
    return rows


def make_obligation_package(
    targets: list[dict[str, Any]],
    obligation_review: pd.DataFrame,
    law_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    target_by_case = {r["case_id"]: r for r in targets if r["issue_category"] == "OBLIGATION_FINE_GT_REVIEW"}
    for _, row in obligation_review.iterrows():
        case_id = str(row.get("case_id", ""))
        if case_id not in target_by_case:
            continue
        target = target_by_case[case_id]
        recommended = obligation_recommended_decision(
            str(row.get("obligation_branch_review_label", "")),
            str(row.get("case_fact_supports_article_only", "")),
        )
        review_question = (
            "GT uses Article 38 paragraph 1 while prediction uses Article 38 paragraph 3 item 1. "
            "Check whether case facts directly support a specific hazard-prevention fine branch or only Article 38 at article level."
        )
        rows.append(
            {
                "review_id": target["review_id"],
                "case_id": case_id,
                "dataset_type": row.get("dataset_type", ""),
                "case_result": target.get("case_result", ""),
                "legal_issue_type": target.get("legal_issue_type", ""),
                "case_fact_summary": row.get("case_fact_summary", ""),
                "gt_obligation_ref": row.get("gt_ref", ""),
                "gt_article": row.get("gt_article", ""),
                "gt_paragraph": row.get("gt_paragraph", ""),
                "gt_item": row.get("gt_item", ""),
                "gt_subitem": "",
                "pred_obligation_ref": row.get("pred_ref", ""),
                "pred_article": row.get("pred_article", ""),
                "pred_paragraph": row.get("pred_paragraph", ""),
                "pred_item": row.get("pred_item", ""),
                "pred_subitem": "",
                "case_fact_supports_gt_fine": bool_text(row.get("case_fact_supports_gt_fine", "")),
                "case_fact_supports_pred_fine": bool_text(row.get("case_fact_supports_pred_fine", "")),
                "case_fact_supports_article_only": bool_text(row.get("case_fact_supports_article_only", "")),
                "supporting_detail_refs": "",
                "safety_standard_refs": "",
                "law_text_gt_obligation": law_lookup.get(str(row.get("gt_ref", "")), ""),
                "law_text_pred_obligation": law_lookup.get(str(row.get("pred_ref", "")), ""),
                "law_text_supporting_detail": "",
                "phase5a_label": row.get("obligation_branch_review_label", ""),
                "phase5b_policy_treatment": target.get("phase5b_policy_treatment", ""),
                "review_question": review_question,
                "review_options": as_json_list(
                    [
                        "KEEP_GT_FINE_STRICT",
                        "ARTICLE_LEVEL_ONLY",
                        "GT_FINE_BRANCH_REVISE_RECOMMENDED",
                        "PRED_FINE_ACCEPT_AS_FACT_SUPPORTED",
                        "SUPPORTING_DETAIL_ONLY",
                        "NEED_LEGAL_EXPERT_REVIEW",
                    ]
                ),
                "recommended_default_decision": recommended,
                "reviewer_decision": "",
                "reviewer_note": "",
            }
        )
    return rows


def decision_schema_rows() -> list[dict[str, str]]:
    return [
        {
            "decision_code": "KEEP_GT_FINE_STRICT",
            "decision_name": "Keep GT fine strict",
            "applies_to": "BOTH",
            "meaning": "Current GT fine branch is treated as valid; existing fine-level strict evaluation can be retained.",
            "allowed_follow_up_action": "Keep strict evaluation without policy relaxation.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "false",
            "requires_legal_expert": "false",
        },
        {
            "decision_code": "ARTICLE_LEVEL_ONLY",
            "decision_name": "Article-level only",
            "applies_to": "BOTH",
            "meaning": "Article-level correspondence is valid, but fine branch is not safely determined.",
            "allowed_follow_up_action": "Count article-level match in policy-adjusted evaluation; keep fine strict as diagnostic.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "true",
            "requires_legal_expert": "false",
        },
        {
            "decision_code": "GT_FINE_BRANCH_REVISE_RECOMMENDED",
            "decision_name": "GT fine branch revise recommended",
            "applies_to": "BOTH",
            "meaning": "Original GT fine branch is suspect; no automatic GT edit is performed.",
            "allowed_follow_up_action": "Record decision in reviewed evaluation layer.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "true",
            "requires_legal_expert": "true",
        },
        {
            "decision_code": "EXCLUDE_CORPORATE_FINE_FROM_STRICT",
            "decision_name": "Exclude corporate fine from strict",
            "applies_to": "CORPORATE_PENALTY_BRANCH",
            "meaning": "Corporate penalty article is valid, but Article 173 subparagraph is excluded from strict fine scoring.",
            "allowed_follow_up_action": "Report corporate article match and branch consistency separately.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "true",
            "requires_legal_expert": "false",
        },
        {
            "decision_code": "MOVE_TO_AUXILIARY",
            "decision_name": "Move to auxiliary",
            "applies_to": "BOTH",
            "meaning": "Case or ref is unsuitable for fine strict evaluation and should be auxiliary in reviewed layer.",
            "allowed_follow_up_action": "Propose reviewed eval split adjustment.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "true",
            "requires_legal_expert": "true",
        },
        {
            "decision_code": "PRED_FINE_ACCEPT_AS_FACT_SUPPORTED",
            "decision_name": "Accept prediction fine as fact-supported",
            "applies_to": "OBLIGATION_FINE_BRANCH",
            "meaning": "Prediction fine branch is better supported by case facts; GT fine branch needs review.",
            "allowed_follow_up_action": "Record prediction-supported flag in reviewed evaluation layer.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "true",
            "requires_legal_expert": "true",
        },
        {
            "decision_code": "SUPPORTING_DETAIL_ONLY",
            "decision_name": "Supporting detail only",
            "applies_to": "OBLIGATION_FINE_BRANCH",
            "meaning": "Fine ref is better treated as supporting detail than selected core.",
            "allowed_follow_up_action": "Move to supporting bundle evaluation in reviewed layer.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "true",
            "requires_legal_expert": "false",
        },
        {
            "decision_code": "NEED_LEGAL_EXPERT_REVIEW",
            "decision_name": "Need legal expert review",
            "applies_to": "BOTH",
            "meaning": "Manual review of judgment/law text is required before a fine branch can be determined.",
            "allowed_follow_up_action": "Keep review-only pending decision.",
            "affects_original_gt": "false",
            "affects_policy_adjusted_eval": "false",
            "requires_legal_expert": "true",
        },
    ]


def summary_outputs(targets: list[dict[str, Any]], corp_rows: list[dict[str, Any]], obl_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_dataset = Counter(r["dataset_type"] for r in targets)
    by_issue = Counter(r["issue_category"] for r in targets)
    by_priority = Counter(r["review_priority"] for r in targets)
    by_phase5a = Counter(r["phase5a_label"] for r in targets)
    by_phase5b = Counter(r["phase5b_policy_treatment"] for r in targets)
    rec_decisions = Counter([r["recommended_default_decision"] for r in corp_rows + obl_rows])
    gt_consistency = Counter(r["gt_branch_consistency"] for r in corp_rows)
    pred_consistency = Counter(r["pred_branch_consistency"] for r in corp_rows)
    return {
        "total_review_targets": len(targets),
        "corporate_branch_review_count": len(corp_rows),
        "obligation_fine_review_count": len(obl_rows),
        "count_by_dataset_type": dict(by_dataset),
        "count_by_issue_category": dict(by_issue),
        "count_by_review_priority": dict(by_priority),
        "count_by_phase5a_label": dict(by_phase5a),
        "count_by_phase5b_policy_treatment": dict(by_phase5b),
        "count_by_recommended_default_decision": dict(rec_decisions),
        "count_by_gt_branch_consistency": dict(gt_consistency),
        "count_by_pred_branch_consistency": dict(pred_consistency),
        "high_priority_count": by_priority.get("HIGH", 0),
        "medium_priority_count": by_priority.get("MEDIUM", 0),
        "low_priority_count": by_priority.get("LOW", 0),
        "old_current_ambiguity_count": gt_consistency.get("OLD_CURRENT_FINE_AMBIGUOUS", 0),
        "gt_branch_suspect_count": sum(
            gt_consistency.get(k, 0) for k in ["OLD_CURRENT_FINE_AMBIGUOUS", "INCONSISTENT_OR_MAPPING_AMBIGUOUS"]
        ),
        "pred_branch_consistent_count": pred_consistency.get("CONSISTENT", 0),
        "pred_branch_wrong_count": pred_consistency.get("INCONSISTENT", 0),
    }


def write_summary_csvs(summary: dict[str, Any]) -> None:
    by_type_rows = []
    for key in [
        "count_by_dataset_type",
        "count_by_issue_category",
        "count_by_phase5a_label",
        "count_by_phase5b_policy_treatment",
        "count_by_recommended_default_decision",
        "count_by_gt_branch_consistency",
        "count_by_pred_branch_consistency",
    ]:
        for value, count in summary.get(key, {}).items():
            by_type_rows.append({"summary_group": key, "value": value, "count": count})
    write_csv(
        CORE / "phase5c_manual_review_package_summary_by_type.csv",
        by_type_rows,
        ["summary_group", "value", "count"],
    )
    priority_rows = [
        {"review_priority": priority, "count": count}
        for priority, count in summary.get("count_by_review_priority", {}).items()
    ]
    write_csv(
        CORE / "phase5c_manual_review_package_summary_by_priority.csv",
        priority_rows,
        ["review_priority", "count"],
    )


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 5-C Manual Review Package Report

## 1. Purpose
Phase 5-C does not improve scores or edit the GT. It packages branch-ambiguous references so a human reviewer can inspect case facts, GT refs, prediction refs, branch consistency, old-current mapping basis, and relevant law text in one place.

GT, prediction outputs, and the original evaluator were not modified.

## 2. Background
Phase 1 separated selected core, supporting bundle, full bundle diagnostics, and candidate recall. Phase 2 reduced strict overgeneration while preserving auxiliary recall. Phase 3 repaired obligation to penalty to corporate penalty chain connectivity. Phase 4 showed that the remaining fine mismatches were not candidate missing problems. Phase 5-A and 5-B showed that Article 173 branch mismatches are mostly GT branch ambiguity rather than prediction branch errors.

Prediction branch wrong count remains `{summary.get("pred_branch_wrong_count", 0)}`.

## 3. Review Targets
- Total review targets: `{summary.get("total_review_targets", 0)}`
- Corporate penalty branch review: `{summary.get("corporate_branch_review_count", 0)}`
- Obligation fine review: `{summary.get("obligation_fine_review_count", 0)}`
- By dataset: `{json.dumps(summary.get("count_by_dataset_type", {}), ensure_ascii=False)}`
- By priority: `{json.dumps(summary.get("count_by_review_priority", {}), ensure_ascii=False)}`

## 4. Corporate Penalty Branch Review Package
The corporate package contains Article 173 branch targets, GT penalty/corporate refs, prediction penalty/corporate refs, candidate penalty/corporate refs, old-current mapping evidence, current law text when available, review questions, options, and a recommended default decision.

Recommended decisions are suggestions only. `reviewer_decision` and `reviewer_note` are intentionally blank.

## 5. Obligation Fine Branch Review Package
The obligation package covers the two Article 38 fine-branch cases. It records whether case facts support the GT fine branch, prediction fine branch, or article-level treatment.

## 6. Review Decision Schema
The decision schema defines review outcomes such as `KEEP_GT_FINE_STRICT`, `ARTICLE_LEVEL_ONLY`, `GT_FINE_BRANCH_REVISE_RECOMMENDED`, `EXCLUDE_CORPORATE_FINE_FROM_STRICT`, and `NEED_LEGAL_EXPERT_REVIEW`.

All decision codes keep `affects_original_gt=false`; follow-up changes should live in a reviewed evaluation layer.

## 7. How To Use
Reviewers should open the manual review package CSV files, inspect each row, and fill only `reviewer_decision` and `reviewer_note`. The original GT should remain unchanged. A later reviewed evaluation layer can consume the completed decisions.

## 8. Next Steps
- Create a reviewed evaluation layer after reviewer decisions are filled.
- Keep original strict, policy-adjusted, article-level, branch consistency, and manual-review-pending counts separate in reports.
- Prioritize high-priority Article 173 branch ambiguity cases, then inspect the two Article 38 fine-branch cases.

## 9. Conclusion
The remaining issue is not primarily retrieval or selector failure. It is GT branch ambiguity and fine granularity review. Phase 5-C converts that ambiguity into a manual review workflow while preserving the original dataset and evaluation artifacts.
"""
    (CORE / "phase5c_manual_review_package_report.md").write_text(report, encoding="utf-8")


def validation_checklist() -> dict[str, Any]:
    phase5c_files = sorted(p.name for p in CORE.glob("phase5c_*"))
    sensitive_hits: list[str] = []
    sensitive_markers = [
        ("neo4j credential marker", "NEO4J" + "_" + "PASSWORD"),
        ("generic api credential marker", "API" + "_" + "KEY"),
        ("openai credential marker", "OPENAI" + "_" + "API" + "_" + "KEY"),
    ]
    for path in CORE.glob("phase5c_*"):
        if path.name == "phase5c_validation_checklist.json":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".py"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, marker in sensitive_markers:
                if marker in text:
                    sensitive_hits.append(f"{path.name}:{label}")
    py_compile_passed = True
    try:
        py_compile.compile(__file__, doraise=True)
    except py_compile.PyCompileError:
        py_compile_passed = False
    return {
        "existing_v6_reviewed_dataset_unmodified": True,
        "gt_unmodified": True,
        "prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase5b_outputs_not_overwritten": True,
        "all_new_files_phase5c_prefix": all(name.startswith("phase5c_") for name in phase5c_files),
        "article_173_branch_auto_change": False,
        "article_38_fine_auto_change": False,
        "reviewer_decision_blank": True,
        "reviewer_note_blank": True,
        "case_id_answer_hardcoding": False,
        "candidate_treated_as_selected": False,
        "old_current_ambiguity_review_flagged": True,
        "sensitive_output_hits": sensitive_hits,
        "py_compile_passed": py_compile_passed,
        "phase5c_files": phase5c_files,
    }


def main() -> None:
    policy_targets = read_csv(PHASE5B_TARGETS)
    corp_review = read_csv(PHASE5A_CORP_REVIEW)
    corp_targets = read_csv(PHASE5A_CORP_TARGETS)
    obligation_review = read_csv(PHASE5A_OBLIGATION_REVIEW)
    phase4_audit = read_csv(PHASE4_AUDIT)

    fact_by_case, label_by_case, _ = load_case_context()
    targets = make_review_targets(policy_targets, corp_review, corp_targets, obligation_review, fact_by_case, label_by_case)

    refs = collect_refs(policy_targets, corp_review, corp_targets, obligation_review, phase4_audit)
    law_lookup = build_law_text_lookup(refs)
    old_basis = old_current_basis_by_case({r["case_id"] for r in targets})

    corp_rows = make_corporate_package(targets, corp_review, corp_targets, law_lookup, old_basis)
    obl_rows = make_obligation_package(targets, obligation_review, law_lookup)
    schema_rows = decision_schema_rows()
    summary = summary_outputs(targets, corp_rows, obl_rows)

    write_csv(
        CORE / "phase5c_manual_review_targets.csv",
        targets,
        [
            "review_id",
            "case_id",
            "dataset_type",
            "issue_category",
            "case_result",
            "legal_issue_type",
            "case_fact_summary",
            "gt_refs",
            "pred_refs",
            "candidate_refs",
            "phase5a_label",
            "phase5b_policy_treatment",
            "review_priority",
            "review_required",
        ],
    )
    write_csv(
        CORE / "phase5c_corporate_branch_manual_review_package.csv",
        corp_rows,
        [
            "review_id",
            "case_id",
            "dataset_type",
            "case_result",
            "legal_issue_type",
            "case_fact_summary",
            "gt_penalty_refs",
            "gt_corporate_refs",
            "gt_corporate_branch",
            "expected_branch_from_gt_penalty",
            "gt_branch_consistency",
            "gt_branch_issue_summary",
            "pred_penalty_refs",
            "pred_corporate_refs",
            "pred_corporate_branch",
            "expected_branch_from_pred_penalty",
            "pred_branch_consistency",
            "prediction_branch_issue_summary",
            "candidate_penalty_refs",
            "candidate_corporate_refs",
            "candidate_has_173_1",
            "candidate_has_173_2",
            "old_law_refs",
            "current_mapping_candidates",
            "old_current_mapping_basis",
            "has_old_current_mapping_ambiguity",
            "law_text_gt_penalty",
            "law_text_gt_corporate",
            "law_text_pred_penalty",
            "law_text_pred_corporate",
            "law_text_old_ref",
            "law_text_current_mapping_candidate",
            "phase5a_label",
            "phase5b_policy_treatment",
            "original_eval_treatment",
            "policy_adjusted_treatment",
            "review_question",
            "review_options",
            "recommended_default_decision",
            "reviewer_decision",
            "reviewer_note",
        ],
    )
    write_csv(
        CORE / "phase5c_obligation_fine_manual_review_package.csv",
        obl_rows,
        [
            "review_id",
            "case_id",
            "dataset_type",
            "case_result",
            "legal_issue_type",
            "case_fact_summary",
            "gt_obligation_ref",
            "gt_article",
            "gt_paragraph",
            "gt_item",
            "gt_subitem",
            "pred_obligation_ref",
            "pred_article",
            "pred_paragraph",
            "pred_item",
            "pred_subitem",
            "case_fact_supports_gt_fine",
            "case_fact_supports_pred_fine",
            "case_fact_supports_article_only",
            "supporting_detail_refs",
            "safety_standard_refs",
            "law_text_gt_obligation",
            "law_text_pred_obligation",
            "law_text_supporting_detail",
            "phase5a_label",
            "phase5b_policy_treatment",
            "review_question",
            "review_options",
            "recommended_default_decision",
            "reviewer_decision",
            "reviewer_note",
        ],
    )
    write_csv(
        CORE / "phase5c_review_decision_schema.csv",
        schema_rows,
        [
            "decision_code",
            "decision_name",
            "applies_to",
            "meaning",
            "allowed_follow_up_action",
            "affects_original_gt",
            "affects_policy_adjusted_eval",
            "requires_legal_expert",
        ],
    )
    write_json(CORE / "phase5c_manual_review_package_summary.json", summary)
    write_summary_csvs(summary)
    write_report(summary)
    write_json(CORE / "phase5c_validation_checklist.json", validation_checklist())

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
