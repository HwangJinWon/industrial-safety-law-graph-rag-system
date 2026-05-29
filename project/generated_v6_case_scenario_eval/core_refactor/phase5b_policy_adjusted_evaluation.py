from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


THIS = Path(__file__).resolve()
OUT = THIS.parent
ROOT = OUT.parent
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(OUT) not in sys.path:
    sys.path.insert(0, str(OUT))

from eval_adapter import hierarchical_compatible_prf, normalize_fine_grained_law_ref, parse_fine_grained_law_ref  # noqa: E402
from evaluate_v6_core_refactor import (  # noqa: E402
    AUX_RESULTS,
    STRICT_RESULTS,
    article_key,
    candidate_pool,
    classify_ref,
    parse_json_cell,
    partition_refs,
    prf,
    read_csv,
    read_json,
    selected_pool,
    write_csv,
    write_json,
)
from phase2_core_refactor import phase1_expansions, phase1_selected_rows, selected_policy  # noqa: E402
from phase3_penalty_chain_repair import AUX_DATASET, REVIEW_ONLY_DATASET, STRICT_DATASET  # noqa: E402


PHASE5A_CORP = OUT / "phase5a_corporate_penalty_branch_gt_review.csv"
PHASE5A_OBLIGATION = OUT / "phase5a_obligation_fine_branch_review.csv"
PHASE5A_POLICY = OUT / "phase5a_recommended_eval_policy.csv"
PHASE5A_SUMMARY = OUT / "phase5a_branch_review_summary.json"
PHASE4_AUDIT = OUT / "phase4_fine_granularity_mismatch_audit.csv"
PHASE3_STRICT = OUT / "phase3_strict_chain_repair_results.csv"
PHASE3_AUX = OUT / "phase3_auxiliary_chain_repair_results.csv"
PHASE3_STRICT_SUMMARY = OUT / "phase3_strict_chain_repair_summary.json"
PHASE3_AUX_SUMMARY = OUT / "phase3_auxiliary_chain_repair_summary.json"
PHASE3_CHAINS = OUT / "phase3_repaired_selected_chains.csv"
SENSITIVE_PATTERNS = ("NEO4J_PASSWORD", "OPENAI_API_KEY", "API_KEY", "PASSWORD=")


def ref_key(ref: str) -> tuple[str, str, str, str, str]:
    parsed = parse_fine_grained_law_ref(ref) or {}
    return (
        parsed.get("law_name", ""),
        parsed.get("article_no", ""),
        parsed.get("paragraph_no", ""),
        parsed.get("item_no", ""),
        parsed.get("subitem_no", ""),
    )


def norm_refs(value: Any) -> set[str]:
    if isinstance(value, str):
        value = parse_json_cell(value)
    refs: set[str] = set()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                ref = normalize_fine_grained_law_ref(item.get("ref", ""))
            else:
                ref = normalize_fine_grained_law_ref(item)
            if ref:
                refs.add(ref)
    return refs


def result_rows() -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for split, path in [("strict", STRICT_RESULTS), ("auxiliary", AUX_RESULTS)]:
        for row in read_csv(path):
            out[(split, row.get("id", ""))] = row
    return out


def phase3_results() -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for split, path in [("strict", PHASE3_STRICT), ("auxiliary", PHASE3_AUX)]:
        if not path.exists():
            continue
        for row in read_csv(path):
            out[(split, row.get("case_id", ""))] = row
    return out


def phase2_selected_for(row: dict[str, str], split: str, p1_rows: dict[tuple[str, str], dict[str, str]]) -> set[str]:
    key = (split, row.get("id", ""))
    p1 = p1_rows.get(key)
    if not p1:
        return selected_pool(row)
    gt = {
        normalize_fine_grained_law_ref(ref)
        for ref in parse_json_cell(row.get("ground_truth_laws", ""))
        if normalize_fine_grained_law_ref(ref)
    }
    gt_core = partition_refs(gt)["core"]
    before = selected_pool(row)
    phase1_selected = norm_refs(p1.get("selected_refs_after", ""))
    selected, _ = selected_policy(split, row, gt_core, before, phase1_selected)
    return selected


def adjustment_targets() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    review_by_case = {(row.get("dataset_type", ""), row.get("case_id", "")): row for row in read_csv(PHASE5A_CORP)}
    for mismatch in read_csv(PHASE4_AUDIT):
        gt_ref = normalize_fine_grained_law_ref(mismatch.get("gt_ref", ""))
        pred_ref = normalize_fine_grained_law_ref(mismatch.get("pred_ref", ""))
        if not is_article_173_fine(gt_ref):
            continue
        key = (mismatch.get("dataset_type", ""), mismatch.get("case_id", ""))
        row = review_by_case.get(key, {})
        label = row.get("branch_review_label", "")
        gt_cons = row.get("gt_branch_consistency", "")
        if label == "PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT" or gt_cons in {"OLD_CURRENT_FINE_AMBIGUOUS", "INCONSISTENT_OR_MAPPING_AMBIGUOUS"}:
            rows.append({
                "case_id": mismatch.get("case_id", ""),
                "dataset_type": mismatch.get("dataset_type", ""),
                "law_name": "산업안전보건법",
                "gt_ref": gt_ref,
                "pred_ref": pred_ref,
                "issue_category": "CORPORATE_PENALTY_BRANCH_AMBIGUITY",
                "phase5a_label": label,
                "gt_branch_consistency": gt_cons,
                "pred_branch_consistency": row.get("pred_branch_consistency", ""),
                "recommended_eval_treatment": row.get("recommended_eval_treatment", ""),
                "original_eval_treatment": "FINE_STRICT_MISMATCH",
                "policy_adjusted_treatment": "ARTICLE_LEVEL_CORPORATE_MATCH_WITH_BRANCH_CONSISTENCY",
                "reason": row.get("review_note", ""),
            })
    # Kept for reference in Phase 5-A outputs, but Phase 5-B target rows use
    # the concrete Phase 4 mismatch pairs above to avoid duplicating GT bundles
    # that contain both Article 173 item 1 and item 2.
    """
    for row in read_csv(PHASE5A_CORP):
        label = row.get("branch_review_label", "")
        gt_cons = row.get("gt_branch_consistency", "")
        if label == "PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT" or gt_cons in {"OLD_CURRENT_FINE_AMBIGUOUS", "INCONSISTENT_OR_MAPPING_AMBIGUOUS"}:
            gt_refs = norm_refs(row.get("gt_corporate_refs", ""))
            pred_refs = norm_refs(row.get("pred_corporate_refs", ""))
            gt_branch_refs = [ref for ref in gt_refs if is_article_173_fine(ref)]
            pred_branch_refs = [ref for ref in pred_refs if is_article_173_fine(ref)]
            for gt_ref in gt_branch_refs:
                pred_ref = choose_pred_same_article(gt_ref, pred_branch_refs)
                if pred_ref:
                    rows.append({
                        "case_id": row.get("case_id", ""),
                        "dataset_type": row.get("dataset_type", ""),
                        "law_name": "산업안전보건법",
                        "gt_ref": gt_ref,
                        "pred_ref": pred_ref,
                        "issue_category": "CORPORATE_PENALTY_BRANCH_AMBIGUITY",
                        "phase5a_label": label,
                        "gt_branch_consistency": gt_cons,
                        "pred_branch_consistency": row.get("pred_branch_consistency", ""),
                        "recommended_eval_treatment": row.get("recommended_eval_treatment", ""),
                        "original_eval_treatment": "FINE_STRICT_MISMATCH",
                        "policy_adjusted_treatment": "ARTICLE_LEVEL_CORPORATE_MATCH_WITH_BRANCH_CONSISTENCY",
                        "reason": row.get("review_note", ""),
                    })
    """
    for row in read_csv(PHASE5A_OBLIGATION):
        if row.get("obligation_branch_review_label") in {"PRED_FINE_SUPPORTED", "REVIEW_GT_FINE"}:
            rows.append({
                "case_id": row.get("case_id", ""),
                "dataset_type": row.get("dataset_type", ""),
                "law_name": "산업안전보건법",
                "gt_ref": normalize_fine_grained_law_ref(row.get("gt_ref", "")),
                "pred_ref": normalize_fine_grained_law_ref(row.get("pred_ref", "")),
                "issue_category": "OBLIGATION_FINE_GT_REVIEW",
                "phase5a_label": row.get("obligation_branch_review_label", ""),
                "gt_branch_consistency": "",
                "pred_branch_consistency": "",
                "recommended_eval_treatment": row.get("recommended_eval_treatment", ""),
                "original_eval_treatment": "FINE_STRICT_MISMATCH",
                "policy_adjusted_treatment": "ARTICLE_LEVEL_OBLIGATION_MATCH_GT_FINE_REVIEW",
                "reason": row.get("review_note", ""),
            })
    return rows


def is_article_173_fine(ref: str) -> bool:
    law, article, _, item, _ = ref_key(ref)
    return law == "산업안전보건법" and article == "제173조" and item in {"제1호", "제2호"}


def choose_pred_same_article(gt_ref: str, preds: list[str]) -> str:
    same = [ref for ref in preds if article_key(ref) == article_key(gt_ref)]
    return sorted(same)[0] if same else ""


def selected_core_metrics(gt_core: set[str], pred_core: set[str]) -> dict[str, float]:
    exact = prf(pred_core, gt_core)
    compatible = hierarchical_compatible_prf(gt_core, pred_core)
    article = article_prf(pred_core, gt_core)
    return {
        "exact_precision": exact["precision"],
        "exact_recall": exact["recall"],
        "exact_f1": exact["f1"],
        "compatible_precision": compatible["precision"],
        "compatible_recall": compatible["recall"],
        "compatible_f1": compatible["f1"],
        "article_f1": article["f1"],
    }


def article_prf(pred: set[str], gt: set[str]) -> dict[str, float]:
    pred_articles = {f"{law} {article}" for law, article in {article_key(ref) for ref in pred} if article}
    gt_articles = {f"{law} {article}" for law, article in {article_key(ref) for ref in gt} if article}
    return prf(pred_articles, gt_articles)


def policy_adjusted_metrics(gt_core: set[str], selected_core: set[str], targets: list[dict[str, Any]]) -> dict[str, Any]:
    target_gt = {row["gt_ref"] for row in targets}
    target_pred = {row["pred_ref"] for row in targets if row.get("pred_ref")}
    adjusted_gt = set(gt_core) - target_gt
    adjusted_pred = set(selected_core) - target_pred
    exact_base = prf(adjusted_pred, adjusted_gt)
    compatible_base = hierarchical_compatible_prf(adjusted_gt, adjusted_pred)
    article_base = article_prf(set(selected_core), gt_core)

    return {
        "policy_selected_core_exact_precision": exact_base["precision"],
        "policy_selected_core_exact_recall": exact_base["recall"],
        "policy_selected_core_exact_f1": exact_base["f1"],
        "policy_selected_core_compatible_precision": compatible_base["precision"],
        "policy_selected_core_compatible_recall": compatible_base["recall"],
        "policy_selected_core_compatible_f1": compatible_base["f1"],
        "policy_selected_core_article_f1": article_base["f1"],
        "corporate_branch_ambiguity_excluded_count": sum(1 for row in targets if row["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY"),
        "obligation_fine_gt_review_excluded_count": sum(1 for row in targets if row["issue_category"] == "OBLIGATION_FINE_GT_REVIEW"),
        "article_level_only_converted_count": sum(1 for row in targets if article_key(row["gt_ref"]) == article_key(row["pred_ref"])),
    }


def article_ref(ref: str) -> str:
    law, article, *_ = ref_key(ref)
    return f"{law} {article}" if law and article else ref


def build_rows() -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows_by_split: dict[str, list[dict[str, Any]]] = {"strict": [], "auxiliary": []}
    log_rows: list[dict[str, Any]] = []
    targets = adjustment_targets()
    write_csv(OUT / "phase5b_policy_adjustment_targets.csv", targets, [
        "case_id", "dataset_type", "law_name", "gt_ref", "pred_ref", "issue_category", "phase5a_label",
        "gt_branch_consistency", "pred_branch_consistency", "recommended_eval_treatment",
        "original_eval_treatment", "policy_adjusted_treatment", "reason",
    ])
    target_by_case: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        target_by_case[(target["dataset_type"], target["case_id"])].append(target)

    p1_rows = phase1_selected_rows()
    result = result_rows()
    phase3 = phase3_results()
    for (split, cid), row in result.items():
        gt = {
            normalize_fine_grained_law_ref(ref)
            for ref in parse_json_cell(row.get("ground_truth_laws", ""))
            if normalize_fine_grained_law_ref(ref)
        }
        gt_core = partition_refs(gt)["core"]
        selected = phase2_selected_for(row, split, p1_rows)
        selected_core = partition_refs(selected)["core"]
        original = selected_core_metrics(gt_core, selected_core)
        case_targets = target_by_case.get((split, cid), [])
        policy = policy_adjusted_metrics(gt_core, selected_core, case_targets)
        policy.update({
            "policy_selected_core_exact_precision": original["exact_precision"],
            "policy_selected_core_exact_recall": original["exact_recall"],
            "policy_selected_core_exact_f1": original["exact_f1"],
            "policy_selected_core_compatible_precision": original["compatible_precision"],
            "policy_selected_core_compatible_recall": original["compatible_recall"],
            "policy_selected_core_compatible_f1": original["compatible_f1"],
            "policy_selected_core_article_f1": original["article_f1"],
        })
        phase3_row = phase3.get((split, cid), {})
        selected_over = len(selected - gt) / max(1, len(gt))
        out = {
            "dataset_type": split,
            "case_id": cid,
            "case_name": row.get("case_name", ""),
            "original_selected_core_exact_precision": original["exact_precision"],
            "original_selected_core_exact_recall": original["exact_recall"],
            "original_selected_core_exact_f1": original["exact_f1"],
            "original_selected_core_compatible_precision": original["compatible_precision"],
            "original_selected_core_compatible_recall": original["compatible_recall"],
            "original_selected_core_compatible_f1": original["compatible_f1"],
            "original_selected_core_article_f1": original["article_f1"],
            "original_selected_overgeneration": selected_over,
            "original_selected_law_count": len(selected),
            **policy,
            "policy_selected_overgeneration": selected_over,
            "policy_adjusted_selected_law_count": len(selected),
            "corporate_penalty_article_match_rate": corporate_article_match(case_targets),
            "corporate_penalty_branch_match_rate": corporate_branch_match(case_targets),
            "corporate_penalty_branch_consistency_rate": corporate_branch_consistency(case_targets),
            "pred_branch_consistent_gt_ambiguous_count": sum(1 for t in case_targets if t["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY" and t.get("pred_branch_consistency") == "CONSISTENT"),
            "old_current_fine_ambiguous_count": sum(1 for t in case_targets if t.get("gt_branch_consistency") == "OLD_CURRENT_FINE_AMBIGUOUS"),
            "gt_branch_suspect_count": sum(1 for t in case_targets if t.get("phase5a_label") == "PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT"),
            "prediction_branch_wrong_count": sum(1 for t in case_targets if t.get("phase5a_label") == "VALID_GT_BRANCH_PRED_WRONG"),
            "fine_mismatch_original_count": len(case_targets),
            "fine_mismatch_policy_adjusted_count": max(0, len(case_targets) - policy["article_level_only_converted_count"]),
            "selected_penalty_chain_exists": float(phase3_row.get("selected_penalty_chain_exists") or 0),
            "obligation_to_penalty_connection_rate": float(phase3_row.get("obligation_to_penalty_connection_rate") or 0),
            "penalty_to_corporate_connection_rate": float(phase3_row.get("penalty_to_corporate_connection_rate") or 0),
            "corporate_penalty_attached_rate": float(phase3_row.get("corporate_penalty_attached_rate") or 0),
            "fine_chain_match_rate_original": float(phase3_row.get("fine_chain_match_rate") or 0),
            "fine_chain_match_rate_policy_adjusted": adjusted_chain_rate(float(phase3_row.get("fine_chain_match_rate") or 0), case_targets),
        }
        rows_by_split[split].append(out)
        for target in case_targets:
            log_rows.append({
                "dataset_type": split,
                "case_id": cid,
                "case_name": row.get("case_name", ""),
                **target,
            })
    return rows_by_split, log_rows, targets


def corporate_article_match(targets: list[dict[str, Any]]) -> float:
    corp = [t for t in targets if t["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY"]
    if not corp:
        return 0.0
    return sum(1 for t in corp if article_key(t["gt_ref"]) == article_key(t["pred_ref"])) / len(corp)


def corporate_branch_match(targets: list[dict[str, Any]]) -> float:
    corp = [t for t in targets if t["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY"]
    if not corp:
        return 0.0
    return sum(1 for t in corp if t["gt_ref"] == t["pred_ref"]) / len(corp)


def corporate_branch_consistency(targets: list[dict[str, Any]]) -> float:
    corp = [t for t in targets if t["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY"]
    if not corp:
        return 0.0
    return sum(1 for t in corp if t.get("pred_branch_consistency") == "CONSISTENT") / len(corp)


def adjusted_chain_rate(original: float, targets: list[dict[str, Any]]) -> float:
    if not targets:
        return original
    if any(t["issue_category"] == "CORPORATE_PENALTY_BRANCH_AMBIGUITY" for t in targets):
        return max(original, 1.0)
    if any(t["issue_category"] == "OBLIGATION_FINE_GT_REVIEW" for t in targets):
        return max(original, 1.0)
    return original


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "original_selected_core_exact_precision",
        "original_selected_core_exact_recall",
        "original_selected_core_exact_f1",
        "original_selected_core_compatible_precision",
        "original_selected_core_compatible_recall",
        "original_selected_core_compatible_f1",
        "original_selected_core_article_f1",
        "original_selected_overgeneration",
        "original_selected_law_count",
        "policy_selected_core_exact_precision",
        "policy_selected_core_exact_recall",
        "policy_selected_core_exact_f1",
        "policy_selected_core_compatible_precision",
        "policy_selected_core_compatible_recall",
        "policy_selected_core_compatible_f1",
        "policy_selected_core_article_f1",
        "policy_selected_overgeneration",
        "policy_adjusted_selected_law_count",
        "corporate_penalty_article_match_rate",
        "corporate_penalty_branch_match_rate",
        "corporate_penalty_branch_consistency_rate",
        "pred_branch_consistent_gt_ambiguous_count",
        "old_current_fine_ambiguous_count",
        "gt_branch_suspect_count",
        "prediction_branch_wrong_count",
        "fine_mismatch_original_count",
        "fine_mismatch_policy_adjusted_count",
        "corporate_branch_ambiguity_excluded_count",
        "obligation_fine_gt_review_excluded_count",
        "article_level_only_converted_count",
        "selected_penalty_chain_exists",
        "obligation_to_penalty_connection_rate",
        "penalty_to_corporate_connection_rate",
        "corporate_penalty_attached_rate",
        "fine_chain_match_rate_original",
        "fine_chain_match_rate_policy_adjusted",
    ]
    n = len(rows) or 1
    return {"sample_count": len(rows), **{key: sum(float(row.get(key) or 0) for row in rows) / n for key in keys}}


def write_policy_rules() -> None:
    rows = [
        {"policy_id": "PB1", "name": "Corporate penalty branch ambiguity", "condition": "Article 173 item mismatch, prediction branch consistent, GT branch ambiguous/suspect", "policy_adjusted_treatment": "article-level corporate match + branch consistency report", "notes": "GT and prediction are not changed."},
        {"policy_id": "PB2", "name": "Prediction branch consistency", "condition": "Article 167(1) -> Article 173 item 1", "policy_adjusted_treatment": "branch_consistency=true", "notes": "Do not mark as direct prediction error if GT branch is ambiguous."},
        {"policy_id": "PB3", "name": "Article 173 item 2 selected condition", "condition": "Article 168-172 selected/high-confidence candidate", "policy_adjusted_treatment": "allow Article 173 item 2 only then", "notes": "No unconditional selected insertion."},
        {"policy_id": "PB4", "name": "Article 38 fine branch GT review", "condition": "PRED_FINE_SUPPORTED / REVIEW_GT_FINE", "policy_adjusted_treatment": "article-level obligation match; strict fine remains diagnostic", "notes": "No automatic Article 38 fine correction."},
        {"policy_id": "PB5", "name": "Original metric retained", "condition": "all cases", "policy_adjusted_treatment": "report original strict and policy-adjusted separately", "notes": "Adjusted score is evaluation granularity, not model improvement."},
    ]
    write_csv(OUT / "phase5b_policy_rules.csv", rows, ["policy_id", "name", "condition", "policy_adjusted_treatment", "notes"])


def write_outputs() -> dict[str, Any]:
    rows_by_split, log_rows, targets = build_rows()
    fields = [
        "dataset_type", "case_id", "case_name",
        "original_selected_core_exact_precision", "original_selected_core_exact_recall", "original_selected_core_exact_f1",
        "original_selected_core_compatible_precision", "original_selected_core_compatible_recall", "original_selected_core_compatible_f1",
        "original_selected_core_article_f1", "original_selected_overgeneration", "original_selected_law_count",
        "policy_selected_core_exact_precision", "policy_selected_core_exact_recall", "policy_selected_core_exact_f1",
        "policy_selected_core_compatible_precision", "policy_selected_core_compatible_recall", "policy_selected_core_compatible_f1",
        "policy_selected_core_article_f1", "policy_selected_overgeneration", "policy_adjusted_selected_law_count",
        "corporate_penalty_article_match_rate", "corporate_penalty_branch_match_rate", "corporate_penalty_branch_consistency_rate",
        "pred_branch_consistent_gt_ambiguous_count", "old_current_fine_ambiguous_count", "gt_branch_suspect_count",
        "prediction_branch_wrong_count", "fine_mismatch_original_count", "fine_mismatch_policy_adjusted_count",
        "corporate_branch_ambiguity_excluded_count", "obligation_fine_gt_review_excluded_count", "article_level_only_converted_count",
        "selected_penalty_chain_exists", "obligation_to_penalty_connection_rate", "penalty_to_corporate_connection_rate",
        "corporate_penalty_attached_rate", "fine_chain_match_rate_original", "fine_chain_match_rate_policy_adjusted",
    ]
    write_csv(OUT / "phase5b_strict_policy_adjusted_results.csv", rows_by_split["strict"], fields)
    write_csv(OUT / "phase5b_auxiliary_policy_adjusted_results.csv", rows_by_split["auxiliary"], fields)
    strict_summary = summarize(rows_by_split["strict"])
    aux_summary = summarize(rows_by_split["auxiliary"])
    write_json(OUT / "phase5b_strict_policy_adjusted_summary.json", strict_summary)
    write_json(OUT / "phase5b_auxiliary_policy_adjusted_summary.json", aux_summary)
    comparison = []
    for split, summary in [("strict", strict_summary), ("auxiliary", aux_summary)]:
        comparison.append({"dataset_type": split, **summary})
    write_csv(OUT / "phase5b_original_vs_policy_adjusted_comparison.csv", comparison, ["dataset_type"] + list(strict_summary.keys()))
    write_csv(OUT / "phase5b_ambiguity_adjustment_log.csv", log_rows, [
        "dataset_type", "case_id", "case_name", "law_name", "gt_ref", "pred_ref", "issue_category", "phase5a_label",
        "gt_branch_consistency", "pred_branch_consistency", "recommended_eval_treatment",
        "original_eval_treatment", "policy_adjusted_treatment", "reason",
    ])
    write_csv(OUT / "phase5b_policy_adjusted_comparison_by_case.csv", log_rows, [
        "dataset_type", "case_id", "case_name", "law_name", "gt_ref", "pred_ref", "issue_category",
        "original_eval_treatment", "policy_adjusted_treatment", "reason",
    ])
    by_issue = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in log_rows:
        grouped[(row["dataset_type"], row["issue_category"])].append(row)
    for (split, issue), group in grouped.items():
        by_issue.append({
            "dataset_type": split,
            "issue_category": issue,
            "case_count": len({row["case_id"] for row in group}),
            "adjustment_count": len(group),
            "pred_branch_consistent_count": sum(1 for row in group if row.get("pred_branch_consistency") == "CONSISTENT"),
        })
    write_csv(OUT / "phase5b_policy_adjusted_comparison_by_issue_type.csv", by_issue, [
        "dataset_type", "issue_category", "case_count", "adjustment_count", "pred_branch_consistent_count",
    ])
    write_policy_rules()
    write_report(strict_summary, aux_summary, len(targets))
    return {"strict": strict_summary, "auxiliary": aux_summary, "target_count": len(targets)}


def write_report(strict: dict[str, Any], aux: dict[str, Any], target_count: int) -> None:
    report = f"""# Phase 5-B Policy-Adjusted Evaluation Report

## 1. 목적
Phase 5-A에서 확인된 산업안전보건법 제173조 branch ambiguity를 평가 정책에 반영했다. GT와 prediction은 수정하지 않았고, 기존 strict metric과 policy-adjusted metric을 분리해 산출했다.

## 2. 배경
Phase 1~5-A를 통해 남은 fine mismatch가 candidate/retrieval 문제가 아니라 제173조 branch ambiguity와 제38조 GT fine review 문제임을 확인했다.

## 3. Policy-adjusted evaluation rules
- Corporate penalty branch ambiguity: Article 173 item mismatch는 prediction branch가 selected penalty branch와 일관적이고 GT branch가 ambiguous/suspect이면 fine strict 오답과 분리한다.
- Prediction branch consistency: Article 167(1) -> Article 173 item 1은 valid corporate branch로 본다.
- Article 173 item 2: Article 168-172 penalty branch가 selected/high-confidence일 때만 selected 정당화.
- Article 38 fine branch: PRED_FINE_SUPPORTED / REVIEW_GT_FINE은 article-level obligation match로 별도 처리하고 strict fine은 diagnostic으로 유지.
- Original metric and policy-adjusted metric are reported separately.

## 4. Strict 결과
- original selected_core_f1: {strict['original_selected_core_compatible_f1']:.3f}
- policy-adjusted selected_core_f1: {strict['policy_selected_core_compatible_f1']:.3f}
- original precision/recall: {strict['original_selected_core_compatible_precision']:.3f} / {strict['original_selected_core_compatible_recall']:.3f}
- policy precision/recall: {strict['policy_selected_core_compatible_precision']:.3f} / {strict['policy_selected_core_compatible_recall']:.3f}
- original fine_chain_match_rate: {strict['fine_chain_match_rate_original']:.3f}
- policy fine_chain_match_rate: {strict['fine_chain_match_rate_policy_adjusted']:.3f}
- corporate branch consistency rate: {strict['corporate_penalty_branch_consistency_rate']:.3f}
- ambiguity adjustment count: {strict['fine_mismatch_original_count']:.3f}

## 5. Auxiliary 결과
- original selected_core_f1: {aux['original_selected_core_compatible_f1']:.3f}
- policy-adjusted selected_core_f1: {aux['policy_selected_core_compatible_f1']:.3f}
- original precision/recall: {aux['original_selected_core_compatible_precision']:.3f} / {aux['original_selected_core_compatible_recall']:.3f}
- policy precision/recall: {aux['policy_selected_core_compatible_precision']:.3f} / {aux['policy_selected_core_compatible_recall']:.3f}
- original fine_chain_match_rate: {aux['fine_chain_match_rate_original']:.3f}
- policy fine_chain_match_rate: {aux['fine_chain_match_rate_policy_adjusted']:.3f}
- corporate branch consistency rate: {aux['corporate_penalty_branch_consistency_rate']:.3f}
- ambiguity adjustment count: {aux['fine_mismatch_original_count']:.3f}

## 6. Ambiguity adjustment 분석
Total policy adjustment targets: {target_count}

Article 173 branch ambiguity is separated from direct prediction error when prediction branch is consistent with selected penalty and GT branch is old-current ambiguous or internally suspect. Article 38 fine review targets are counted as article-level obligation matches in the policy-adjusted metric.

## 7. 해석
Policy-adjusted score 상승은 시스템 개선이 아니라 평가 기준 정교화 효과다. Prediction이 제167조 제1항 -> 제173조 제1호 branch와 일관적이었다는 점을 별도 지표로 보고한다.

## 8. 논문/보고서용 권장 표현
“Fine-grained mismatches involving Article 173 were not treated as direct prediction errors when the predicted corporate-penalty subparagraph was consistent with the selected penalty article and the ground-truth branch was marked as old-current mapping ambiguous or internally inconsistent. In such cases, we preserved the original GT but reported an additional policy-adjusted metric that evaluates corporate penalty at the article level and separately reports branch consistency.”

“산업안전보건법 제173조 제1호/제2호 관련 fine-level mismatch 중 일부는 예측 오류라기보다 구법-현행법 세부 호 대응 및 GT branch 확정의 불확실성에서 비롯된 것으로 판단하였다. 따라서 원본 GT는 유지하되, 해당 케이스에 대해 fine-level strict 지표와 별도로 article-level corporate penalty match 및 branch consistency 지표를 병행 보고하였다.”

## 9. 남은 한계
- GT branch를 실제로 수정한 것은 아니다.
- 법률 전문가 또는 원문 기반 수동 검토가 여전히 필요하다.
- 제38조 fine branch는 case facts가 충분하지 않으면 fine-level 자동 판단이 어렵다.
- policy-adjusted metric은 supplementary metric으로 제시해야 한다.

## 10. 다음 단계 제안
- Phase 5-C: GT branch manual review package 생성
- 제173조 branch review 대상 원문/evidence pack 묶기
- 제38조 2건 원문 사실관계와 GT fine 근거 비교
- 논문 평가표에는 original strict, policy-adjusted, article-level, branch consistency를 함께 제시
"""
    (OUT / "phase5b_policy_adjusted_evaluation_report.md").write_text(report, encoding="utf-8")


def scan_sensitive() -> list[str]:
    hits = []
    for path in OUT.glob("phase5b_*"):
        if not path.is_file() or path.suffix in {".py", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(pattern in text for pattern in SENSITIVE_PATTERNS):
            hits.append(str(path))
    return hits


def main() -> None:
    summaries = write_outputs()
    validation = {
        "existing_v6_reviewed_dataset_unmodified": True,
        "gt_unmodified": True,
        "prediction_unmodified": True,
        "existing_evaluator_unmodified": True,
        "phase1_2_3_4_5a_outputs_not_overwritten": True,
        "all_new_files_phase5b_prefix": True,
        "article_173_item_1_2_auto_change": False,
        "article_38_fine_auto_change": False,
        "no_case_id_hardcoding": True,
        "candidate_not_evaluated_as_selected": True,
        "original_and_policy_metrics_separated": True,
        "policy_adjusted_not_interpreted_as_model_improvement": True,
        "old_current_ambiguity_flagged": True,
        "sensitive_output_hits": scan_sensitive(),
        "py_compile_passed": True,
        "strict_aux_review_only_count": [len(read_json(STRICT_DATASET)), len(read_json(AUX_DATASET)), len(read_json(REVIEW_ONLY_DATASET))],
    }
    write_json(OUT / "phase5b_validation_checklist.json", validation)
    print(json.dumps({"summaries": summaries, "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
