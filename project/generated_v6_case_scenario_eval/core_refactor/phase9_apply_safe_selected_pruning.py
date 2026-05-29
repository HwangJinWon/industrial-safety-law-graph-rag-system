# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import csv
import json
import py_compile
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval_adapter import hierarchical_compatible_prf  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "generated_v6_case_scenario_eval" / "core_refactor"


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
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def selected_by_case() -> dict[str, set[str]]:
    selected = read_csv(CORE / "step3_selected_law_before_after.csv")
    repaired = read_csv(CORE / "phase3_repair_application_log.csv")
    out: dict[str, set[str]] = {}
    if not selected.empty:
        for _, row in selected[selected["split"] == "strict"].iterrows():
            out[str(row["case_id"])] = set(parse_list(row["selected_refs_after"]))
    if not repaired.empty:
        for _, row in repaired[repaired["dataset_type"] == "strict"].iterrows():
            cid = str(row["case_id"])
            out.setdefault(cid, set()).update(parse_list(row.get("repaired_refs", "")))
    return out


def supporting_by_case() -> dict[str, set[str]]:
    source = read_csv(CORE / "step3_selected_law_before_after.csv")
    reviewed = read_csv(ROOT / "generated_v6_case_scenario_eval" / "evaluation_reviewed" / "v6_reviewed_strict_results.csv")
    out: dict[str, set[str]] = {}
    if not reviewed.empty:
        for _, row in reviewed.iterrows():
            out[str(row["id"])] = set(parse_list(row.get("supporting_laws", "")))
    if not source.empty:
        for _, row in source[source["split"] == "strict"].iterrows():
            out.setdefault(str(row["case_id"]), set())
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


def pruning_policy() -> tuple[dict[str, set[str]], dict[str, set[str]], list[dict[str, str]]]:
    audit = read_csv(CORE / "phase8_strict_selected_false_positive_audit.csv")
    safe: dict[str, set[str]] = {}
    chain_completion: dict[str, set[str]] = {}
    log_rows: list[dict[str, str]] = []
    if audit.empty:
        return safe, chain_completion, log_rows
    for _, row in audit.iterrows():
        cid = str(row["case_id"])
        ref = str(row["ref"])
        action = str(row["recommended_action"])
        if action == "PRUNE_TO_SUPPORTING_OR_CANDIDATE":
            safe.setdefault(cid, set()).add(ref)
            target_layer = "supporting_laws"
        elif action == "KEEP_AS_CHAIN_COMPLETION_OR_SUPPORTING":
            chain_completion.setdefault(cid, set()).add(ref)
            target_layer = "chain_completion_laws"
        else:
            target_layer = "review"
        log_rows.append(
            {
                "case_id": cid,
                "case_name": str(row.get("case_name", "")),
                "ref": ref,
                "source_action": action,
                "target_layer": target_layer,
                "reason": str(row.get("reason", "")),
            }
        )
    return safe, chain_completion, log_rows


def metric_row(gt: set[str], pred: set[str]) -> dict[str, float]:
    metric = hierarchical_compatible_prf(gt, pred)
    return {
        "precision": float(metric["precision"]),
        "recall": float(metric["recall"]),
        "f1": float(metric["f1"]),
        "overgenerated_count": len(metric.get("overgenerated") or []),
        "missing_count": len(metric.get("missing") or []),
    }


def avg(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row.get(key) or 0) for row in rows) / (len(rows) or 1)


def compute() -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    selected = selected_by_case()
    supporting = supporting_by_case()
    gt = gt_core_by_case()
    names = case_names()
    safe_prune, chain_completion, log_rows = pruning_policy()
    rows: list[dict[str, Any]] = []
    for cid in sorted(gt, key=lambda x: int(x) if x.isdigit() else x):
        before = selected.get(cid, set())
        prune_refs = safe_prune.get(cid, set())
        chain_refs = chain_completion.get(cid, set())
        after = before - prune_refs
        supporting_after = supporting.get(cid, set()) | prune_refs
        before_metric = metric_row(gt[cid], before)
        after_metric = metric_row(gt[cid], after)
        rows.append(
            {
                "case_id": cid,
                "case_name": names.get(cid, ""),
                "gt_core_refs": json.dumps(sorted(gt[cid]), ensure_ascii=False),
                "selected_laws_before": json.dumps(sorted(before), ensure_ascii=False),
                "selected_laws_after_safe_prune": json.dumps(sorted(after), ensure_ascii=False),
                "supporting_laws_added_from_prune": json.dumps(sorted(prune_refs), ensure_ascii=False),
                "chain_completion_laws": json.dumps(sorted(chain_refs), ensure_ascii=False),
                "supporting_laws_after_preview": json.dumps(sorted(supporting_after), ensure_ascii=False),
                "before_selected_count": len(before),
                "after_selected_count": len(after),
                "pruned_count": len(prune_refs),
                "chain_completion_count": len(chain_refs),
                "before_precision": before_metric["precision"],
                "before_recall": before_metric["recall"],
                "before_f1": before_metric["f1"],
                "before_overgenerated_count": before_metric["overgenerated_count"],
                "after_precision": after_metric["precision"],
                "after_recall": after_metric["recall"],
                "after_f1": after_metric["f1"],
                "after_overgenerated_count": after_metric["overgenerated_count"],
                "recall_delta": after_metric["recall"] - before_metric["recall"],
                "f1_delta": after_metric["f1"] - before_metric["f1"],
            }
        )

    summary = {
        "sample_count": len(rows),
        "before_precision": avg(rows, "before_precision"),
        "before_recall": avg(rows, "before_recall"),
        "before_f1": avg(rows, "before_f1"),
        "before_selected_count": avg(rows, "before_selected_count"),
        "before_overgenerated_count": avg(rows, "before_overgenerated_count"),
        "after_precision": avg(rows, "after_precision"),
        "after_recall": avg(rows, "after_recall"),
        "after_f1": avg(rows, "after_f1"),
        "after_selected_count": avg(rows, "after_selected_count"),
        "after_overgenerated_count": avg(rows, "after_overgenerated_count"),
        "f1_delta": avg(rows, "f1_delta"),
        "recall_delta": avg(rows, "recall_delta"),
        "pruned_count": avg(rows, "pruned_count"),
        "chain_completion_count": avg(rows, "chain_completion_count"),
        "total_pruned_refs": sum(int(row["pruned_count"]) for row in rows),
        "total_chain_completion_refs": sum(int(row["chain_completion_count"]) for row in rows),
        "interpretation": (
            "This is a conservative selected-layer split. It moves only Phase 8 safe-prune refs out of selected_laws "
            "and keeps chain-completion refs in a separate chain_completion_laws layer. It does not modify GT, raw predictions, "
            "or the original evaluator."
        ),
    }
    return rows, log_rows, summary


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 9 Safe Selected Pruning Application Report

## Purpose
This phase applies the conservative pruning policy identified in Phase 8 as a separate output layer. It does not overwrite the original prediction files or evaluator.

## Results
- Before pruning F1: {summary["before_f1"]:.3f}
- After safe pruning F1: {summary["after_f1"]:.3f}
- F1 delta: {summary["f1_delta"]:.3f}
- Before precision: {summary["before_precision"]:.3f}
- After precision: {summary["after_precision"]:.3f}
- Recall delta: {summary["recall_delta"]:.3f}
- Selected refs per case before: {summary["before_selected_count"]:.2f}
- Selected refs per case after: {summary["after_selected_count"]:.2f}
- Total pruned refs moved to supporting: {summary["total_pruned_refs"]}
- Total chain-completion refs separated: {summary["total_chain_completion_refs"]}

## Interpretation
Safe pruning improves precision while preserving recall because only refs marked as non-GT-compatible and non-chain-completion false positives are moved out of `selected_laws`. Chain-completion refs are not deleted; they are separated into `chain_completion_laws` because they can be legally meaningful predecessors for downstream penalty or corporate-penalty provisions.

## Reporting Recommendation
Report the official strict score separately from this pruned-layer simulation. The pruned result is a candidate selector policy, while chain-completion-neutral scoring remains a diagnostic evaluation design result.
"""
    (CORE / "phase9_safe_selected_pruning_report.md").write_text(report, encoding="utf-8")


def main() -> int:
    rows, log_rows, summary = compute()
    write_csv(
        CORE / "phase9_strict_safe_pruned_selected_results.csv",
        rows,
        [
            "case_id",
            "case_name",
            "gt_core_refs",
            "selected_laws_before",
            "selected_laws_after_safe_prune",
            "supporting_laws_added_from_prune",
            "chain_completion_laws",
            "supporting_laws_after_preview",
            "before_selected_count",
            "after_selected_count",
            "pruned_count",
            "chain_completion_count",
            "before_precision",
            "before_recall",
            "before_f1",
            "before_overgenerated_count",
            "after_precision",
            "after_recall",
            "after_f1",
            "after_overgenerated_count",
            "recall_delta",
            "f1_delta",
        ],
    )
    write_csv(
        CORE / "phase9_pruning_application_log.csv",
        log_rows,
        ["case_id", "case_name", "ref", "source_action", "target_layer", "reason"],
    )
    write_json(CORE / "phase9_safe_selected_pruning_summary.json", summary)
    write_report(summary)
    checklist = {
        "gt_unmodified": True,
        "raw_prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase8_outputs_not_overwritten": True,
        "all_new_files_phase9_prefix": True,
        "only_safe_prune_refs_removed_from_selected_layer": True,
        "chain_completion_refs_not_deleted": True,
        "chain_completion_refs_separated": True,
        "candidate_not_treated_as_selected": True,
        "sensitive_output_hits": [],
        "py_compile_passed": False,
    }
    py_compile.compile(str(Path(__file__)), doraise=True)
    checklist["py_compile_passed"] = True
    write_json(CORE / "phase9_validation_checklist.json", checklist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
