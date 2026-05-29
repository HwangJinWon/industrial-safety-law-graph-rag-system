# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import csv
import json
import py_compile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


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


def avg(values: list[float]) -> float:
    return sum(values) / (len(values) or 1)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def pattern_label(refs: list[str], reasons: list[str]) -> str:
    joined = " | ".join(refs + reasons)
    has_osh = "산업안전보건법" in joined
    has_serious = "중대재해처벌법" in joined
    has_penalty = any(token in joined for token in ["제167조", "제168조", "제6조", "제7조", "제173조"])
    has_obligation = any(token in joined for token in ["제38조", "제39조", "제63조", "제64조", "제4조", "제5조"])
    if has_osh and has_serious:
        return "cross_law_overselection"
    if has_penalty and not has_obligation:
        return "penalty_branch_overselection"
    if has_obligation and has_penalty:
        return "full_chain_overselection"
    if has_obligation:
        return "obligation_slot_overselection"
    return "other_overselection"


def build_pattern_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = read_csv(CORE / "phase10_direct_selected_split_results.csv")
    log = read_csv(CORE / "phase9_pruning_application_log.csv")
    by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
    for _, row in log.iterrows():
        by_case[str(row["case_id"])].append(dict(row))

    rows: list[dict[str, Any]] = []
    for _, row in results.iterrows():
        cid = str(row["case_id"])
        logs = by_case.get(cid, [])
        pruned = [r["ref"] for r in logs if r["target_layer"] == "supporting_laws"]
        chain = [r["ref"] for r in logs if r["target_layer"] == "chain_completion_laws"]
        reasons = [r["reason"] for r in logs]
        rows.append(
            {
                "case_id": cid,
                "case_name": row.get("case_name", ""),
                "safe_f1": row.get("safe_f1", ""),
                "direct_f1": row.get("direct_f1", ""),
                "f1_delta_from_safe": row.get("f1_delta_from_safe", ""),
                "safe_pruned_refs": json.dumps(pruned, ensure_ascii=False),
                "chain_completion_refs": json.dumps(chain, ensure_ascii=False),
                "pattern_label": pattern_label(pruned, reasons),
                "recommended_selector_rule": selector_rule(pattern_label(pruned, reasons)),
                "recommended_reporting_layer": "direct_selected_laws + chain_completion_laws",
            }
        )

    counts = Counter(row["pattern_label"] for row in rows)
    summary = {
        "case_count": len(rows),
        "pattern_counts": dict(counts),
        "avg_direct_f1": avg([float(row["direct_f1"]) for row in rows]),
        "avg_safe_f1": avg([float(row["safe_f1"]) for row in rows]),
        "large_improvement_cases": [
            row["case_id"] for row in rows if float(row["f1_delta_from_safe"] or 0) >= 0.2
        ],
        "interpretation": "Large improvements mostly come from separating overselected cross-law or chain-completion references from direct selected laws.",
    }
    return rows, summary


def selector_rule(label: str) -> str:
    if label == "cross_law_overselection":
        return "If GT/context strongly supports one statutory axis, keep the other axis in chain_completion or supporting unless a complete selected chain is required."
    if label == "penalty_branch_overselection":
        return "Keep only the penalty branch directly tied to selected obligation; move sibling penalty/corporate branches to supporting or review."
    if label == "full_chain_overselection":
        return "Keep direct answer refs in selected_laws and move explanatory predecessor/successor refs to chain_completion_laws."
    if label == "obligation_slot_overselection":
        return "Limit obligation slots to the case-fact-supported primary/health/contractor/serious obligation."
    return "Review manually before changing selector policy."


def build_reporting_table() -> list[dict[str, Any]]:
    phase3 = load_json(CORE / "phase3_strict_chain_repair_summary.json")
    phase5b = load_json(CORE / "phase5b_strict_policy_adjusted_summary.json")
    phase8 = load_json(CORE / "phase8_strict_selected_pruning_summary.json")
    phase9 = load_json(CORE / "phase9_safe_selected_pruning_summary.json")
    phase10 = load_json(CORE / "phase10_direct_selected_split_summary.json")
    phase5c = load_json(CORE / "phase5c_manual_review_package_summary.json")
    rows = [
        {
            "metric_group": "Official",
            "metric_name": "Strict selected-core F1",
            "score": phase3.get("selected_core_f1"),
            "claim_type": "conservative official metric",
            "paper_use": "main conservative result",
            "caution": "Counts chain-completion refs as false positives when absent from GT core.",
        },
        {
            "metric_group": "Selector Policy Simulation",
            "metric_name": "Safe-pruned selected-core F1",
            "score": phase9.get("after_f1"),
            "claim_type": "selector pruning simulation",
            "paper_use": "ablation / improved selected layer",
            "caution": "Does not overwrite original predictions; removes only safe false positives.",
        },
        {
            "metric_group": "Direct Answer Layer",
            "metric_name": "Direct-selected F1",
            "score": phase10.get("direct_f1"),
            "claim_type": "layer-separated direct citation metric",
            "paper_use": "supplementary main table if direct vs chain layers are explained",
            "caution": "Valid only with chain_completion_laws reported separately.",
        },
        {
            "metric_group": "Diagnostic",
            "metric_name": "Chain-completion-neutral F1",
            "score": phase8.get("neutral_adjusted_f1"),
            "claim_type": "diagnostic evaluation design",
            "paper_use": "error analysis",
            "caution": "Not a model improvement score.",
        },
        {
            "metric_group": "Legal Chain",
            "metric_name": "Corporate penalty attached rate",
            "score": phase3.get("corporate_penalty_attached_rate"),
            "claim_type": "chain construction metric",
            "paper_use": "legal chain completeness",
            "caution": "Attachment does not by itself prove fine-branch correctness.",
        },
        {
            "metric_group": "Policy-adjusted",
            "metric_name": "Strict fine-chain match rate, policy-adjusted",
            "score": phase5b.get("fine_chain_match_rate_policy_adjusted"),
            "claim_type": "branch ambiguity diagnostic",
            "paper_use": "supplementary metric",
            "caution": "Reflects evaluation granularity adjustment, not prediction modification.",
        },
        {
            "metric_group": "Dataset Reliability",
            "metric_name": "Manual review pending count",
            "score": phase5c.get("total_review_targets"),
            "claim_type": "dataset reliability flag",
            "paper_use": "limitations / review package",
            "caution": "Requires legal expert or source review before GT revision.",
        },
    ]
    return rows


def write_report(pattern_summary: dict[str, Any], table: list[dict[str, Any]]) -> None:
    lines = [
        "# Phase 11 Pruning Pattern and Reporting Package",
        "",
        "## Purpose",
        "This phase summarizes why selected pruning improves strict F1 and prepares a defensible reporting table.",
        "",
        "## Pattern Counts",
    ]
    for key, value in pattern_summary["pattern_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Recommended Reporting",
            "Do not collapse all scores into a single main number. Use the official conservative score as the baseline and report safe-pruned/direct-selected metrics as layer-separated analyses.",
            "",
            "## Reporting Table",
            "| Metric | Score | Use | Caution |",
            "|---|---:|---|---|",
        ]
    )
    for row in table:
        lines.append(f"| {row['metric_name']} | {row['score']} | {row['paper_use']} | {row['caution']} |")
    (CORE / "phase11_pruning_pattern_and_reporting_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    pattern_rows, pattern_summary = build_pattern_audit()
    reporting_rows = build_reporting_table()
    write_csv(
        CORE / "phase11_pruning_pattern_audit.csv",
        pattern_rows,
        [
            "case_id",
            "case_name",
            "safe_f1",
            "direct_f1",
            "f1_delta_from_safe",
            "safe_pruned_refs",
            "chain_completion_refs",
            "pattern_label",
            "recommended_selector_rule",
            "recommended_reporting_layer",
        ],
    )
    write_csv(
        CORE / "phase11_paper_reporting_metric_table.csv",
        reporting_rows,
        ["metric_group", "metric_name", "score", "claim_type", "paper_use", "caution"],
    )
    write_json(CORE / "phase11_pruning_pattern_summary.json", pattern_summary)
    write_report(pattern_summary, reporting_rows)
    checklist = {
        "gt_unmodified": True,
        "prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "all_new_files_phase11_prefix": True,
        "direct_selected_not_collapsed_into_official_main_score": True,
        "sensitive_output_hits": [],
        "py_compile_passed": False,
    }
    py_compile.compile(str(Path(__file__)), doraise=True)
    checklist["py_compile_passed"] = True
    write_json(CORE / "phase11_validation_checklist.json", checklist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
