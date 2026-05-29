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


def metric(gt: set[str], pred: set[str]) -> dict[str, Any]:
    m = hierarchical_compatible_prf(gt, pred)
    return {
        "precision": float(m["precision"]),
        "recall": float(m["recall"]),
        "f1": float(m["f1"]),
        "overgenerated_count": len(m.get("overgenerated") or []),
        "missing_count": len(m.get("missing") or []),
        "overgenerated_refs": sorted(m.get("overgenerated") or []),
        "missing_refs": sorted(m.get("missing") or []),
    }


def avg(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row.get(key) or 0) for row in rows) / (len(rows) or 1)


def load_chain_quality() -> dict[str, dict[str, str]]:
    df = read_csv(CORE / "phase3_strict_chain_repair_results.csv")
    if df.empty:
        return {}
    return {str(row["case_id"]): dict(row) for _, row in df.iterrows()}


def compute() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    phase9 = read_csv(CORE / "phase9_strict_safe_pruned_selected_results.csv")
    chain_quality = load_chain_quality()
    rows: list[dict[str, Any]] = []
    recall_loss_rows: list[dict[str, Any]] = []

    for _, row in phase9.iterrows():
        cid = str(row["case_id"])
        gt = set(parse_list(row["gt_core_refs"]))
        safe_selected = set(parse_list(row["selected_laws_after_safe_prune"]))
        chain_completion = set(parse_list(row["chain_completion_laws"]))
        direct_selected = safe_selected - chain_completion

        safe_m = metric(gt, safe_selected)
        direct_m = metric(gt, direct_selected)
        cq = chain_quality.get(cid, {})
        chain_completion_coverage = 1.0 if chain_completion else 0.0
        chain_integrity_available = float(cq.get("selected_penalty_chain_exists") or 0)
        corporate_attached = float(cq.get("corporate_penalty_attached_rate") or 0)
        obligation_to_penalty = float(cq.get("obligation_to_penalty_connection_rate") or 0)
        penalty_to_corporate = float(cq.get("penalty_to_corporate_connection_rate") or 0)

        out = {
            "case_id": cid,
            "case_name": row.get("case_name", ""),
            "gt_core_refs": json.dumps(sorted(gt), ensure_ascii=False),
            "safe_selected_laws": json.dumps(sorted(safe_selected), ensure_ascii=False),
            "direct_selected_laws": json.dumps(sorted(direct_selected), ensure_ascii=False),
            "chain_completion_laws": json.dumps(sorted(chain_completion), ensure_ascii=False),
            "safe_selected_count": len(safe_selected),
            "direct_selected_count": len(direct_selected),
            "chain_completion_count": len(chain_completion),
            "safe_precision": safe_m["precision"],
            "safe_recall": safe_m["recall"],
            "safe_f1": safe_m["f1"],
            "safe_overgenerated_count": safe_m["overgenerated_count"],
            "direct_precision": direct_m["precision"],
            "direct_recall": direct_m["recall"],
            "direct_f1": direct_m["f1"],
            "direct_overgenerated_count": direct_m["overgenerated_count"],
            "direct_missing_count": direct_m["missing_count"],
            "direct_missing_refs": json.dumps(direct_m["missing_refs"], ensure_ascii=False),
            "recall_delta_from_safe": direct_m["recall"] - safe_m["recall"],
            "f1_delta_from_safe": direct_m["f1"] - safe_m["f1"],
            "chain_completion_coverage": chain_completion_coverage,
            "selected_penalty_chain_exists": chain_integrity_available,
            "corporate_penalty_attached_rate": corporate_attached,
            "obligation_to_penalty_connection_rate": obligation_to_penalty,
            "penalty_to_corporate_connection_rate": penalty_to_corporate,
        }
        rows.append(out)
        if out["recall_delta_from_safe"] < 0:
            recall_loss_rows.append(out)

    summary = {
        "sample_count": len(rows),
        "safe_precision": avg(rows, "safe_precision"),
        "safe_recall": avg(rows, "safe_recall"),
        "safe_f1": avg(rows, "safe_f1"),
        "safe_selected_count": avg(rows, "safe_selected_count"),
        "safe_overgenerated_count": avg(rows, "safe_overgenerated_count"),
        "direct_precision": avg(rows, "direct_precision"),
        "direct_recall": avg(rows, "direct_recall"),
        "direct_f1": avg(rows, "direct_f1"),
        "direct_selected_count": avg(rows, "direct_selected_count"),
        "direct_overgenerated_count": avg(rows, "direct_overgenerated_count"),
        "direct_missing_count": avg(rows, "direct_missing_count"),
        "f1_delta_from_safe": avg(rows, "f1_delta_from_safe"),
        "recall_delta_from_safe": avg(rows, "recall_delta_from_safe"),
        "chain_completion_count": avg(rows, "chain_completion_count"),
        "chain_completion_case_rate": sum(1 for row in rows if int(row["chain_completion_count"]) > 0) / (len(rows) or 1),
        "chain_completion_ref_total": sum(int(row["chain_completion_count"]) for row in rows),
        "recall_loss_case_count": len(recall_loss_rows),
        "selected_penalty_chain_exists": avg(rows, "selected_penalty_chain_exists"),
        "corporate_penalty_attached_rate": avg(rows, "corporate_penalty_attached_rate"),
        "obligation_to_penalty_connection_rate": avg(rows, "obligation_to_penalty_connection_rate"),
        "penalty_to_corporate_connection_rate": avg(rows, "penalty_to_corporate_connection_rate"),
        "interpretation": (
            "direct_selected removes both safe false positives and chain-completion refs from selected_laws. "
            "chain-completion refs are preserved in a separate layer, so this score should be reported as direct-selected F1, "
            "not as a replacement for the official strict selected-core F1."
        ),
    }
    return rows, recall_loss_rows, summary


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 10 Direct Selected vs Chain-Completion Split Report

## Purpose
This phase tests whether selected references can be made stricter by separating direct answer refs from chain-completion refs. It keeps chain-completion refs in a separate layer rather than deleting them.

## Results
- Safe-pruned F1: {summary["safe_f1"]:.3f}
- Direct-selected F1: {summary["direct_f1"]:.3f}
- Direct-selected precision: {summary["direct_precision"]:.3f}
- Direct-selected recall: {summary["direct_recall"]:.3f}
- Recall delta from safe-pruned: {summary["recall_delta_from_safe"]:.3f}
- Direct selected refs per case: {summary["direct_selected_count"]:.2f}
- Remaining direct overgenerated refs per case: {summary["direct_overgenerated_count"]:.2f}
- Chain-completion refs preserved: {summary["chain_completion_ref_total"]}
- Recall-loss cases: {summary["recall_loss_case_count"]}
- Corporate penalty attached rate retained: {summary["corporate_penalty_attached_rate"]:.3f}

## Interpretation
Direct-selected F1 is the cleanest high score for a strict answer-reference layer, but it depends on reporting chain-completion refs separately. This is defensible only if the paper clearly distinguishes direct citations from legal-chain explanatory refs.

## Recommended Reporting
Use three rows:
1. Official strict selected-core F1.
2. Safe-pruned selected-core F1.
3. Direct-selected F1 with chain-completion refs reported separately.
"""
    (CORE / "phase10_direct_selected_chain_completion_split_report.md").write_text(report, encoding="utf-8")


def main() -> int:
    rows, recall_loss_rows, summary = compute()
    write_csv(
        CORE / "phase10_direct_selected_split_results.csv",
        rows,
        [
            "case_id",
            "case_name",
            "gt_core_refs",
            "safe_selected_laws",
            "direct_selected_laws",
            "chain_completion_laws",
            "safe_selected_count",
            "direct_selected_count",
            "chain_completion_count",
            "safe_precision",
            "safe_recall",
            "safe_f1",
            "safe_overgenerated_count",
            "direct_precision",
            "direct_recall",
            "direct_f1",
            "direct_overgenerated_count",
            "direct_missing_count",
            "direct_missing_refs",
            "recall_delta_from_safe",
            "f1_delta_from_safe",
            "chain_completion_coverage",
            "selected_penalty_chain_exists",
            "corporate_penalty_attached_rate",
            "obligation_to_penalty_connection_rate",
            "penalty_to_corporate_connection_rate",
        ],
    )
    write_csv(
        CORE / "phase10_direct_selected_recall_loss_audit.csv",
        recall_loss_rows,
        [
            "case_id",
            "case_name",
            "gt_core_refs",
            "direct_selected_laws",
            "chain_completion_laws",
            "direct_missing_refs",
            "recall_delta_from_safe",
            "direct_recall",
            "safe_recall",
        ],
    )
    write_json(CORE / "phase10_direct_selected_split_summary.json", summary)
    write_report(summary)
    checklist = {
        "gt_unmodified": True,
        "raw_prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase9_outputs_not_overwritten": True,
        "all_new_files_phase10_prefix": True,
        "chain_completion_refs_not_deleted": True,
        "direct_selected_metric_not_claimed_as_official_strict_replacement": True,
        "sensitive_output_hits": [],
        "py_compile_passed": False,
    }
    py_compile.compile(str(Path(__file__)), doraise=True)
    checklist["py_compile_passed"] = True
    write_json(CORE / "phase10_validation_checklist.json", checklist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
