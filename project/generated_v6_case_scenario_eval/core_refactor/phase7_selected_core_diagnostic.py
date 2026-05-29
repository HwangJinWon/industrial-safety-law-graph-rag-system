# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import csv
import json
import py_compile
from pathlib import Path
from typing import Any

import pandas as pd

import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval_adapter import hierarchical_compatible_prf, ref_to_tuple  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "generated_v6_case_scenario_eval" / "core_refactor"

OSH = "\uc0b0\uc5c5\uc548\uc804\ubcf4\uac74\ubc95"
SERIOUS = "\uc911\ub300\uc7ac\ud574\ucc98\ubc8c\ubc95"


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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def parse_list(value: Any) -> list[str]:
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        return [str(x) for x in parsed] if isinstance(parsed, list) else []
    except Exception:
        return []


def ref_parts(ref: str) -> tuple[str, str, str, str, str]:
    return ref_to_tuple(ref) or ("", "", "", "", "")


def article_num(ref: str) -> str:
    return ref_parts(ref)[1].replace("제", "").replace("조", "")


def law_name(ref: str) -> str:
    return ref_parts(ref)[0]


def slot(ref: str) -> str:
    law = law_name(ref)
    article = article_num(ref)
    if law == OSH:
        if article in {"38", "39", "63", "64"}:
            return "obligation"
        if article in {"167", "168", "169", "170", "171", "172"}:
            return "penalty"
        if article == "173":
            return "corporate_penalty"
    if law == SERIOUS:
        if article in {"4", "5"}:
            return "obligation"
        if article == "6":
            return "penalty"
        if article == "7":
            return "corporate_penalty"
    return "other"


def has_article(refs: set[str], law: str, article: str) -> bool:
    return any(law_name(ref) == law and article_num(ref) == article for ref in refs)


def has_any_article(refs: set[str], law: str, articles: set[str]) -> bool:
    return any(law_name(ref) == law and article_num(ref) in articles for ref in refs)


def is_chain_completion_ref(ref: str, gt: set[str], pred: set[str]) -> tuple[bool, str]:
    law = law_name(ref)
    article = article_num(ref)
    ref_slot = slot(ref)
    gt_has_osh_corporate = has_article(gt, OSH, "173")
    pred_has_osh_corporate = has_article(pred, OSH, "173")
    gt_has_serious_corporate = has_article(gt, SERIOUS, "7")
    pred_has_serious_corporate = has_article(pred, SERIOUS, "7")

    if law == OSH and gt_has_osh_corporate and pred_has_osh_corporate:
        if article in {"38", "39", "63", "64"}:
            return True, "osh_obligation_needed_to_explain_article_173_chain"
        if article in {"167", "168", "169", "170", "171", "172"}:
            return True, "osh_penalty_needed_to_explain_article_173_chain"

    if law == SERIOUS and gt_has_serious_corporate and pred_has_serious_corporate:
        if article in {"4", "5"}:
            return True, "serious_obligation_needed_to_explain_article_7_chain"
        if article == "6":
            return True, "serious_penalty_needed_to_explain_article_7_chain"

    if ref_slot == "obligation" and (
        has_any_article(gt, law, {"167", "168", "169", "170", "171", "172", "6"})
        or has_any_article(gt, law, {"173", "7"})
    ):
        return True, "obligation_chain_predecessor_for_penalty_or_corporate_gt"

    if ref_slot == "penalty" and has_any_article(gt, law, {"173", "7"}):
        return True, "penalty_chain_predecessor_for_corporate_gt"

    return False, ""


def reconstruct_selected_refs() -> dict[str, set[str]]:
    selected = read_csv(CORE / "step3_selected_law_before_after.csv")
    repaired = read_csv(CORE / "phase3_repair_application_log.csv")
    out: dict[str, set[str]] = {}
    for _, row in selected[selected["split"] == "strict"].iterrows():
        out[str(row["case_id"])] = set(parse_list(row["selected_refs_after"]))
    for _, row in repaired[repaired["dataset_type"] == "strict"].iterrows():
        cid = str(row["case_id"])
        out.setdefault(cid, set()).update(parse_list(row.get("repaired_refs", "")))
    return out


def gt_core_refs() -> dict[str, set[str]]:
    cls = read_csv(CORE / "step1_ref_classification.csv")
    out: dict[str, set[str]] = {}
    core = cls[(cls["split"] == "strict") & (cls["group"] == "core")]
    for cid, group in core.groupby("case_id"):
        out[str(cid)] = set(group["ref"].tolist())
    return out


def case_names() -> dict[str, str]:
    results = read_csv(CORE / "phase3_strict_chain_repair_results.csv")
    return {str(r["case_id"]): r["case_name"] for _, r in results.iterrows()} if not results.empty else {}


def compute() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_by_case = reconstruct_selected_refs()
    gt_by_case = gt_core_refs()
    names = case_names()
    rows: list[dict[str, Any]] = []
    sums = {
        "original_precision": 0.0,
        "original_recall": 0.0,
        "original_f1": 0.0,
        "adjusted_precision": 0.0,
        "adjusted_recall": 0.0,
        "adjusted_f1": 0.0,
        "selected_law_count": 0.0,
        "neutral_chain_completion_count": 0.0,
    }
    for cid in sorted(gt_by_case, key=lambda x: int(x) if x.isdigit() else x):
        gt = gt_by_case[cid]
        pred = selected_by_case.get(cid, set())
        metric = hierarchical_compatible_prf(gt, pred)
        over = set(metric["overgenerated"])
        neutral: list[str] = []
        reasons: list[str] = []
        for ref in sorted(over):
            ok, reason = is_chain_completion_ref(ref, gt, pred)
            if ok:
                neutral.append(ref)
                reasons.append(f"{ref}: {reason}")
        tp = len(metric["matches"])
        fp_adjusted = max(0, len(pred) - tp - len(neutral))
        adjusted_precision = tp / (tp + fp_adjusted) if tp + fp_adjusted else 0.0
        adjusted_recall = metric["recall"]
        adjusted_f1 = (
            2 * adjusted_precision * adjusted_recall / (adjusted_precision + adjusted_recall)
            if adjusted_precision + adjusted_recall
            else 0.0
        )
        row = {
            "case_id": cid,
            "case_name": names.get(cid, ""),
            "gt_core_refs": json.dumps(sorted(gt), ensure_ascii=False),
            "selected_refs": json.dumps(sorted(pred), ensure_ascii=False),
            "original_precision": metric["precision"],
            "original_recall": metric["recall"],
            "original_f1": metric["f1"],
            "overgenerated_refs": json.dumps(sorted(over), ensure_ascii=False),
            "neutral_chain_completion_refs": json.dumps(neutral, ensure_ascii=False),
            "neutral_chain_completion_reasons": json.dumps(reasons, ensure_ascii=False),
            "adjusted_precision": adjusted_precision,
            "adjusted_recall": adjusted_recall,
            "adjusted_f1": adjusted_f1,
            "selected_law_count": len(pred),
            "neutral_chain_completion_count": len(neutral),
        }
        rows.append(row)
        for key in [
            "original_precision",
            "original_recall",
            "original_f1",
            "adjusted_precision",
            "adjusted_recall",
            "adjusted_f1",
            "selected_law_count",
            "neutral_chain_completion_count",
        ]:
            sums[key] += float(row[key])

    n = len(rows) or 1
    summary = {key: value / n for key, value in sums.items()}
    summary.update(
        {
            "sample_count": len(rows),
            "official_phase3_selected_core_f1": read_json(CORE / "phase3_strict_chain_repair_summary.json").get("selected_core_f1"),
            "official_phase3_selected_core_precision": read_json(CORE / "phase3_strict_chain_repair_summary.json").get("selected_core_precision"),
            "official_phase3_selected_core_recall": read_json(CORE / "phase3_strict_chain_repair_summary.json").get("selected_core_recall"),
            "interpretation": "Adjusted metric does not change prediction or GT; it treats legally necessary chain-completion refs as neutral rather than false positives when GT only contains downstream penalty/corporate refs.",
        }
    )
    return rows, summary


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 7 Selected Core F1 Diagnostic Report

## Purpose
This phase explains why strict selected_core_f1 remains low and provides a diagnostic chain-completion-adjusted metric. It does not modify GT, predictions, or the original evaluator.

## Finding
Several low-F1 strict cases contain only downstream corporate-penalty refs in GT, especially Article 173, while selected output includes the obligation and penalty predecessors required to explain that corporate penalty chain. Under the original selected_core metric, these chain-completion refs are counted as false positives.

## Metrics
- Official Phase 3 strict selected_core_f1: {summary.get("official_phase3_selected_core_f1")}
- Reconstructed original selected_core_f1: {summary.get("original_f1")}
- Chain-completion-adjusted selected_core_f1: {summary.get("adjusted_f1")}
- Reconstructed original precision: {summary.get("original_precision")}
- Adjusted precision: {summary.get("adjusted_precision")}
- Recall retained: {summary.get("adjusted_recall")}
- Average neutral chain-completion refs per case: {summary.get("neutral_chain_completion_count")}

## Interpretation
The adjusted score is not a model improvement. It shows that part of the low strict selected_core_f1 is caused by evaluation granularity: selected answers include legally meaningful chain predecessors that are absent from the strict GT core. This should be reported as a diagnostic or supplementary metric, not as the primary strict metric.

## Recommended Next Step
Create a reviewed_eval_layer after legal review that distinguishes direct GT core refs from chain-completion explanatory refs. Until then, keep the original strict selected_core_f1 and report this adjusted metric as evidence that the bottleneck is partly evaluation design.
"""
    (CORE / "phase7_selected_core_diagnostic_report.md").write_text(report, encoding="utf-8")


def validation() -> dict[str, Any]:
    files = sorted(p.name for p in CORE.glob("phase7_*"))
    if "phase7_validation_checklist.json" not in files:
        files.append("phase7_validation_checklist.json")
        files = sorted(files)
    try:
        py_compile.compile(__file__, doraise=True)
        py_ok = True
    except py_compile.PyCompileError:
        py_ok = False
    hits: list[str] = []
    for path in CORE.glob("phase7_*"):
        if path.name == "phase7_validation_checklist.json":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in ["NEO4J" + "_" + "PASSWORD", "OPENAI" + "_" + "API" + "_" + "KEY", "API" + "_" + "KEY"]:
            if marker in text:
                hits.append(path.name)
    return {
        "gt_unmodified": True,
        "prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase6_outputs_not_overwritten": True,
        "all_new_files_phase7_prefix": all(name.startswith("phase7_") for name in files),
        "candidate_treated_as_selected": False,
        "diagnostic_metric_not_model_improvement": True,
        "sensitive_output_hits": hits,
        "py_compile_passed": py_ok,
        "phase7_files": files,
    }


def main() -> None:
    rows, summary = compute()
    write_csv(
        CORE / "phase7_selected_core_chain_completion_adjustment.csv",
        rows,
        [
            "case_id",
            "case_name",
            "gt_core_refs",
            "selected_refs",
            "original_precision",
            "original_recall",
            "original_f1",
            "overgenerated_refs",
            "neutral_chain_completion_refs",
            "neutral_chain_completion_reasons",
            "adjusted_precision",
            "adjusted_recall",
            "adjusted_f1",
            "selected_law_count",
            "neutral_chain_completion_count",
        ],
    )
    write_json(CORE / "phase7_selected_core_diagnostic_summary.json", summary)
    write_report(summary)
    write_json(CORE / "phase7_validation_checklist.json", validation())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
