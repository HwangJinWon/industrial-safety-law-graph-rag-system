# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import csv
import json
import py_compile
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval_adapter import hierarchical_compatible_prf, ref_to_tuple  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "generated_v6_case_scenario_eval" / "core_refactor"

OSH = "산업안전보건법"
SERIOUS = "중대재해처벌법"


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("") if path.exists() else pd.DataFrame()


def write_csv(path: Path, rows: list[dict[str, Any]], cols: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in cols})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_list(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except Exception:
        try:
            parsed = json.loads(text)
        except Exception:
            return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def ref_parts(ref: str) -> tuple[str, str, str, str, str]:
    return ref_to_tuple(ref) or ("", "", "", "", "")


def article_num(ref: str) -> str:
    article = ref_parts(ref)[1]
    return re.sub(r"[^0-9의]", "", article)


def law_name(ref: str) -> str:
    return ref_parts(ref)[0]


def article_key(ref: str) -> tuple[str, str]:
    law, article, *_ = ref_parts(ref)
    return law, article


def slot(ref: str) -> str:
    law = law_name(ref)
    article = article_num(ref)
    if law == OSH:
        if article in {"38", "39"}:
            return "osh_primary_or_health_obligation"
        if article in {"63", "64"}:
            return "osh_contractor_obligation"
        if article in {"167", "168", "169", "170", "171", "172"}:
            return "osh_penalty"
        if article == "173":
            return "osh_corporate_penalty"
    if law == SERIOUS:
        if article in {"4", "5"}:
            return "serious_obligation"
        if article == "6":
            return "serious_penalty"
        if article == "7":
            return "serious_corporate_penalty"
    return "other"


def is_core_ref(ref: str) -> bool:
    return slot(ref) != "other"


def has_article(refs: set[str], law: str, article: str) -> bool:
    return any(law_name(ref) == law and article_num(ref) == article for ref in refs)


def has_any_article(refs: set[str], law: str, articles: set[str]) -> bool:
    return any(law_name(ref) == law and article_num(ref) in articles for ref in refs)


def is_chain_completion_ref(ref: str, gt: set[str], pred: set[str]) -> tuple[bool, str]:
    law = law_name(ref)
    article = article_num(ref)
    ref_slot = slot(ref)

    if law == OSH and has_article(gt, OSH, "173") and has_article(pred, OSH, "173"):
        if article in {"38", "39", "63", "64"}:
            return True, "osh_obligation_predecessor_for_article_173"
        if article in {"167", "168", "169", "170", "171", "172"}:
            return True, "osh_penalty_predecessor_for_article_173"

    if law == SERIOUS and has_article(gt, SERIOUS, "7") and has_article(pred, SERIOUS, "7"):
        if article in {"4", "5"}:
            return True, "serious_obligation_predecessor_for_article_7"
        if article == "6":
            return True, "serious_penalty_predecessor_for_article_7"

    if ref_slot in {"osh_primary_or_health_obligation", "osh_contractor_obligation", "serious_obligation"}:
        if has_any_article(gt, law, {"167", "168", "169", "170", "171", "172", "6", "173", "7"}):
            return True, "obligation_predecessor_for_downstream_penalty_gt"

    if ref_slot in {"osh_penalty", "serious_penalty"}:
        if has_any_article(gt, law, {"173", "7"}):
            return True, "penalty_predecessor_for_corporate_gt"

    return False, ""


def selected_by_case() -> dict[str, set[str]]:
    selected = read_csv(CORE / "step3_selected_law_before_after.csv")
    repaired = read_csv(CORE / "phase3_repair_application_log.csv")
    out: dict[str, set[str]] = {}
    if not selected.empty:
        for _, row in selected[selected["split"] == "strict"].iterrows():
            out[str(row["case_id"])] = {ref for ref in parse_list(row["selected_refs_after"]) if is_core_ref(ref)}
    if not repaired.empty:
        for _, row in repaired[repaired["dataset_type"] == "strict"].iterrows():
            cid = str(row["case_id"])
            out.setdefault(cid, set()).update(ref for ref in parse_list(row.get("repaired_refs", "")) if is_core_ref(ref))
    return out


def gt_core_by_case() -> dict[str, set[str]]:
    cls = read_csv(CORE / "step1_ref_classification.csv")
    out: dict[str, set[str]] = {}
    if cls.empty:
        return out
    core = cls[(cls["split"] == "strict") & (cls["group"] == "core")]
    for cid, group in core.groupby("case_id"):
        out[str(cid)] = set(group["ref"].tolist())
    return out


def case_names() -> dict[str, str]:
    results = read_csv(CORE / "phase3_strict_chain_repair_results.csv")
    if results.empty:
        return {}
    return {str(row["case_id"]): row["case_name"] for _, row in results.iterrows()}


def f1_from_precision_recall(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def matched_pred_refs(metric: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for match in metric.get("matches") or []:
        if isinstance(match, dict):
            pred = str(match.get("pred") or "")
            if pred:
                refs.add(pred)
        elif isinstance(match, str):
            refs.add(match)
    return refs


def avg(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row.get(key) or 0) for row in rows) / (len(rows) or 1)


def compute() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected = selected_by_case()
    gt_by_case = gt_core_by_case()
    names = case_names()
    case_rows: list[dict[str, Any]] = []
    fp_rows: list[dict[str, Any]] = []

    for cid in sorted(gt_by_case, key=lambda x: int(x) if x.isdigit() else x):
        gt = gt_by_case[cid]
        pred = selected.get(cid, set())
        metric = hierarchical_compatible_prf(gt, pred)
        overgenerated = set(metric.get("overgenerated") or [])
        matches = matched_pred_refs(metric)
        article_gt = {article_key(ref) for ref in gt}

        neutral: set[str] = set()
        prune_safe: set[str] = set()
        prune_risky: set[str] = set()
        for ref in sorted(overgenerated):
            neutral_ok, neutral_reason = is_chain_completion_ref(ref, gt, pred)
            article_match = article_key(ref) in article_gt
            if neutral_ok:
                neutral.add(ref)
                action = "KEEP_AS_CHAIN_COMPLETION_OR_SUPPORTING"
                safe = False
                reason = neutral_reason
            elif article_match:
                prune_risky.add(ref)
                action = "REVIEW_FINE_BRANCH_OR_SLOT_BEFORE_PRUNE"
                safe = False
                reason = "article_family_matches_gt_but_fine_or_slot_mismatch"
            else:
                prune_safe.add(ref)
                action = "PRUNE_TO_SUPPORTING_OR_CANDIDATE"
                safe = True
                reason = "not_gt_compatible_and_not_chain_completion"

            fp_rows.append(
                {
                    "case_id": cid,
                    "case_name": names.get(cid, ""),
                    "ref": ref,
                    "slot": slot(ref),
                    "article_match_gt": article_match,
                    "chain_completion_neutral": neutral_ok,
                    "recommended_action": action,
                    "prune_safe": safe,
                    "reason": reason,
                }
            )

        oracle_pred = pred - overgenerated
        oracle_metric = hierarchical_compatible_prf(gt, oracle_pred)

        safe_pruned_pred = pred - prune_safe
        safe_metric = hierarchical_compatible_prf(gt, safe_pruned_pred)

        neutral_adjusted_fp = max(0, len(pred) - len(matches) - len(neutral))
        neutral_precision = len(matches) / (len(matches) + neutral_adjusted_fp) if len(matches) + neutral_adjusted_fp else 0.0
        neutral_recall = metric["recall"]
        neutral_f1 = f1_from_precision_recall(neutral_precision, neutral_recall)

        case_rows.append(
            {
                "case_id": cid,
                "case_name": names.get(cid, ""),
                "gt_core_count": len(gt),
                "selected_core_count": len(pred),
                "current_precision": metric["precision"],
                "current_recall": metric["recall"],
                "current_f1": metric["f1"],
                "overgenerated_count": len(overgenerated),
                "safe_prune_count": len(prune_safe),
                "neutral_chain_completion_count": len(neutral),
                "risky_article_family_fp_count": len(prune_risky),
                "safe_pruned_selected_count": len(safe_pruned_pred),
                "safe_pruned_precision": safe_metric["precision"],
                "safe_pruned_recall": safe_metric["recall"],
                "safe_pruned_f1": safe_metric["f1"],
                "oracle_pruned_selected_count": len(oracle_pred),
                "oracle_precision": oracle_metric["precision"],
                "oracle_recall": oracle_metric["recall"],
                "oracle_f1": oracle_metric["f1"],
                "neutral_adjusted_precision": neutral_precision,
                "neutral_adjusted_recall": neutral_recall,
                "neutral_adjusted_f1": neutral_f1,
                "safe_prune_refs": json.dumps(sorted(prune_safe), ensure_ascii=False),
                "neutral_chain_completion_refs": json.dumps(sorted(neutral), ensure_ascii=False),
                "risky_article_family_fp_refs": json.dumps(sorted(prune_risky), ensure_ascii=False),
            }
        )

    summary = {
        "sample_count": len(case_rows),
        "current_precision": avg(case_rows, "current_precision"),
        "current_recall": avg(case_rows, "current_recall"),
        "current_f1": avg(case_rows, "current_f1"),
        "safe_pruned_precision": avg(case_rows, "safe_pruned_precision"),
        "safe_pruned_recall": avg(case_rows, "safe_pruned_recall"),
        "safe_pruned_f1": avg(case_rows, "safe_pruned_f1"),
        "oracle_precision": avg(case_rows, "oracle_precision"),
        "oracle_recall": avg(case_rows, "oracle_recall"),
        "oracle_f1": avg(case_rows, "oracle_f1"),
        "neutral_adjusted_precision": avg(case_rows, "neutral_adjusted_precision"),
        "neutral_adjusted_recall": avg(case_rows, "neutral_adjusted_recall"),
        "neutral_adjusted_f1": avg(case_rows, "neutral_adjusted_f1"),
        "selected_core_count": avg(case_rows, "selected_core_count"),
        "safe_pruned_selected_count": avg(case_rows, "safe_pruned_selected_count"),
        "oracle_pruned_selected_count": avg(case_rows, "oracle_pruned_selected_count"),
        "overgenerated_count": avg(case_rows, "overgenerated_count"),
        "safe_prune_count": avg(case_rows, "safe_prune_count"),
        "neutral_chain_completion_count": avg(case_rows, "neutral_chain_completion_count"),
        "risky_article_family_fp_count": avg(case_rows, "risky_article_family_fp_count"),
        "interpretation": (
            "safe_pruned is a conservative simulation that removes only non-GT, non-chain-completion false positives. "
            "oracle_pruned is an upper bound that removes all current overgenerated refs and should not be reported as model performance."
        ),
    }
    return case_rows, fp_rows, summary


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 8 Strict Selected Pruning Audit

## Purpose
This phase separates strict selected-core false positives into safe pruning candidates, risky article-family mismatches, and chain-completion refs that should be treated as explanatory or supporting evidence. It does not modify GT, predictions, or the evaluator.

## Summary
- Current reconstructed strict selected-core F1: {summary["current_f1"]:.3f}
- Conservative safe-pruned F1 simulation: {summary["safe_pruned_f1"]:.3f}
- Chain-completion-neutral adjusted F1: {summary["neutral_adjusted_f1"]:.3f}
- Oracle-pruned upper-bound F1: {summary["oracle_f1"]:.3f}
- Current selected core refs per case: {summary["selected_core_count"]:.2f}
- Safe-pruned selected core refs per case: {summary["safe_pruned_selected_count"]:.2f}
- Average safe prune refs per case: {summary["safe_prune_count"]:.2f}
- Average neutral chain-completion refs per case: {summary["neutral_chain_completion_count"]:.2f}

## Interpretation
The strict score is low for two different reasons. Some selected refs are genuine false positives that can be moved to supporting or candidate evidence. A larger portion are chain-completion refs: obligation or penalty predecessors needed to explain downstream penalty or corporate-penalty GT refs. These should not be silently deleted. They should either remain in selected legal chains or move to an explicit chain-completion/supporting layer.

## Recommended Implementation Rule
Use slot-based selected pruning only for refs marked `PRUNE_TO_SUPPORTING_OR_CANDIDATE`. Keep chain-completion refs out of false-positive scoring through a reviewed evaluation layer rather than forcing the selector to drop legally meaningful predecessors.
"""
    (CORE / "phase8_strict_selected_pruning_audit_report.md").write_text(report, encoding="utf-8")


def main() -> int:
    case_rows, fp_rows, summary = compute()
    write_csv(
        CORE / "phase8_strict_selected_pruning_by_case.csv",
        case_rows,
        [
            "case_id",
            "case_name",
            "gt_core_count",
            "selected_core_count",
            "current_precision",
            "current_recall",
            "current_f1",
            "overgenerated_count",
            "safe_prune_count",
            "neutral_chain_completion_count",
            "risky_article_family_fp_count",
            "safe_pruned_selected_count",
            "safe_pruned_precision",
            "safe_pruned_recall",
            "safe_pruned_f1",
            "oracle_pruned_selected_count",
            "oracle_precision",
            "oracle_recall",
            "oracle_f1",
            "neutral_adjusted_precision",
            "neutral_adjusted_recall",
            "neutral_adjusted_f1",
            "safe_prune_refs",
            "neutral_chain_completion_refs",
            "risky_article_family_fp_refs",
        ],
    )
    write_csv(
        CORE / "phase8_strict_selected_false_positive_audit.csv",
        fp_rows,
        [
            "case_id",
            "case_name",
            "ref",
            "slot",
            "article_match_gt",
            "chain_completion_neutral",
            "recommended_action",
            "prune_safe",
            "reason",
        ],
    )
    write_json(CORE / "phase8_strict_selected_pruning_summary.json", summary)
    write_report(summary)
    checklist = {
        "gt_unmodified": True,
        "prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase7_outputs_not_overwritten": True,
        "all_new_files_phase8_prefix": True,
        "oracle_pruned_not_reported_as_model_performance": True,
        "safe_pruning_is_simulation_only": True,
        "sensitive_output_hits": [],
        "py_compile_passed": False,
    }
    py_compile.compile(str(Path(__file__)), doraise=True)
    checklist["py_compile_passed"] = True
    write_json(CORE / "phase8_validation_checklist.json", checklist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
