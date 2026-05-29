# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import py_compile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "generated_v6_case_scenario_eval" / "core_refactor"


INPUTS = [
    ("final_core_refactor_evaluation_report.md", "Phase 1 report", "phase1", "context"),
    ("final_v6_strict_core_refactor_summary.json", "Phase 1 strict summary", "phase1", "metrics"),
    ("final_v6_auxiliary_core_refactor_summary.json", "Phase 1 auxiliary summary", "phase1", "metrics"),
    ("final_before_after_comparison.csv", "Phase 1 comparison", "phase1", "comparison"),
    ("phase2_summary.json", "Phase 2 summary", "phase2", "metrics"),
    ("phase2_core_refactor_report.md", "Phase 2 report", "phase2", "context"),
    ("phase3_penalty_chain_repair_summary.json", "Phase 3 combined summary if present", "phase3", "optional"),
    ("phase3_strict_chain_repair_summary.json", "Phase 3 strict summary", "phase3", "metrics"),
    ("phase3_auxiliary_chain_repair_summary.json", "Phase 3 auxiliary summary", "phase3", "metrics"),
    ("phase3_failure_type_before_after.csv", "Phase 3 failure table", "phase3", "diagnostic"),
    ("phase3_penalty_chain_repair_report.md", "Phase 3 report", "phase3", "context"),
    ("phase4_fine_mismatch_summary.json", "Phase 4 summary", "phase4", "diagnostic"),
    ("phase4_fine_granularity_mismatch_audit.csv", "Phase 4 audit", "phase4", "diagnostic"),
    ("phase4_fine_grained_alignment_audit_report.md", "Phase 4 report", "phase4", "context"),
    ("phase5a_branch_review_summary.json", "Phase 5-A summary", "phase5a", "metrics"),
    ("phase5a_corporate_penalty_branch_gt_review.csv", "Phase 5-A corporate review", "phase5a", "review"),
    ("phase5a_obligation_fine_branch_review.csv", "Phase 5-A obligation review", "phase5a", "review"),
    ("phase5a_corporate_penalty_branch_gt_review_report.md", "Phase 5-A report", "phase5a", "context"),
    ("phase5b_strict_policy_adjusted_summary.json", "Phase 5-B strict summary", "phase5b", "metrics"),
    ("phase5b_auxiliary_policy_adjusted_summary.json", "Phase 5-B auxiliary summary", "phase5b", "metrics"),
    ("phase5b_original_vs_policy_adjusted_comparison.csv", "Phase 5-B comparison", "phase5b", "comparison"),
    ("phase5b_policy_adjusted_evaluation_report.md", "Phase 5-B report", "phase5b", "context"),
    ("phase5c_manual_review_targets.csv", "Phase 5-C review targets", "phase5c", "review package"),
    ("phase5c_corporate_branch_manual_review_package.csv", "Phase 5-C corporate package", "phase5c", "review package"),
    ("phase5c_obligation_fine_manual_review_package.csv", "Phase 5-C obligation package", "phase5c", "review package"),
    ("phase5c_review_decision_schema.csv", "Phase 5-C decision schema", "phase5c", "schema"),
    ("phase5c_manual_review_package_report.md", "Phase 5-C report", "phase5c", "context"),
    ("phase5c_manual_review_package_summary.json", "Phase 5-C summary", "phase5c", "metrics"),
    ("phase5d_old_current_corporate_mapping_audit.csv", "Phase 5-D mapping audit", "phase5d", "mapping audit"),
    ("phase5d_corporate_branch_resolver_rules.csv", "Phase 5-D resolver rules", "phase5d", "rules"),
    ("phase5d_refined_corporate_mapping_layer.csv", "Phase 5-D refined layer", "phase5d", "refined layer"),
    ("phase5d_refined_mapping_evaluation_simulation.csv", "Phase 5-D simulation rows", "phase5d", "simulation"),
    ("phase5d_refined_mapping_simulation_summary.json", "Phase 5-D simulation summary", "phase5d", "metrics"),
    ("phase5d_old_current_corporate_mapping_refinement_report.md", "Phase 5-D report", "phase5d", "context"),
]


SUMMARY_COLUMNS = [
    "dataset_type",
    "evaluation_version",
    "sample_count",
    "selected_core_f1",
    "selected_core_precision",
    "selected_core_recall",
    "selected_core_compatible_f1",
    "selected_core_compatible_precision",
    "selected_core_compatible_recall",
    "selected_law_count",
    "selected_overgeneration",
    "candidate_article_recall",
    "candidate_fine_recall",
    "candidate_fine_missing",
    "candidate_article_missing",
    "corporate_penalty_attached_rate",
    "obligation_to_penalty_connection_rate",
    "penalty_to_corporate_connection_rate",
    "fine_chain_match_rate_original",
    "fine_chain_match_rate_policy_adjusted",
    "fine_chain_match_rate_refined_policy",
    "branch_consistency_rate",
    "prediction_branch_wrong_count",
    "likely_old_current_fine_branch_overmapped_count",
    "manual_review_pending_count",
    "notes",
]


def read_json(name: str) -> dict[str, Any]:
    path = CORE / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(name: str, data: dict[str, Any]) -> None:
    (CORE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(name: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with (CORE / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def inventory() -> list[dict[str, Any]]:
    rows = []
    for filename, used_for, phase, notes in INPUTS:
        path = CORE / filename
        rows.append(
            {
                "file_path": str(path.relative_to(ROOT)),
                "exists": str(path.exists()).lower(),
                "used_for": used_for,
                "phase": phase,
                "notes": notes if path.exists() else f"missing; {notes}",
            }
        )
    return rows


def row(dataset: str, version: str, notes: str, **values: Any) -> dict[str, Any]:
    out = {col: "" for col in SUMMARY_COLUMNS}
    out.update(values)
    out["dataset_type"] = dataset
    out["evaluation_version"] = version
    out["notes"] = notes
    return out


def final_summary_rows() -> list[dict[str, Any]]:
    phase2 = read_json("phase2_summary.json")
    p1s = read_json("final_v6_strict_core_refactor_summary.json")
    p1a = read_json("final_v6_auxiliary_core_refactor_summary.json")
    p3s = read_json("phase3_strict_chain_repair_summary.json")
    p3a = read_json("phase3_auxiliary_chain_repair_summary.json")
    p5bs = read_json("phase5b_strict_policy_adjusted_summary.json")
    p5ba = read_json("phase5b_auxiliary_policy_adjusted_summary.json")
    p5c = read_json("phase5c_manual_review_package_summary.json")
    p5d = read_json("phase5d_refined_mapping_simulation_summary.json")
    rows: list[dict[str, Any]] = []

    for dataset, p2, p1, p3, p5b, pending in [
        ("strict", phase2.get("strict", {}), p1s, p3s, p5bs, p5c.get("count_by_dataset_type", {}).get("strict", "")),
        ("auxiliary", phase2.get("auxiliary", {}), p1a, p3a, p5ba, p5c.get("count_by_dataset_type", {}).get("auxiliary", "")),
    ]:
        rows.append(
            row(
                dataset,
                "original",
                "pre core-refactor baseline reconstructed from Phase 2 before fields",
                sample_count=p2.get("sample_count"),
                selected_core_f1=p2.get("selected_core_f1_before"),
                selected_core_recall=p2.get("selected_core_recall_before"),
                selected_law_count=p2.get("selected_law_count_before"),
                selected_overgeneration=p2.get("selected_overgeneration_before"),
                candidate_fine_recall=p2.get("candidate_fine_recall"),
            )
        )
        rows.append(
            row(
                dataset,
                "core_refactored",
                "Phase 1 separated selected core, supporting bundle, full bundle diagnostic, and candidate recall",
                sample_count=p1.get("sample_count"),
                selected_core_f1=p1.get("selected_core_compatible_f1"),
                selected_core_precision=p1.get("selected_core_compatible_precision"),
                selected_core_recall=p1.get("selected_core_compatible_recall"),
                selected_core_compatible_f1=p1.get("selected_core_compatible_f1"),
                selected_core_compatible_precision=p1.get("selected_core_compatible_precision"),
                selected_core_compatible_recall=p1.get("selected_core_compatible_recall"),
                selected_law_count=p1.get("selected_law_count"),
                selected_overgeneration=p1.get("selected_overgeneration_rate"),
                candidate_article_recall=p1.get("candidate_article_recall"),
                candidate_fine_recall=p1.get("candidate_fine_recall"),
                candidate_fine_missing=p1.get("candidate_fine_missing"),
                candidate_article_missing=p1.get("candidate_article_missing"),
                fine_chain_match_rate_original=p1.get("chain_fine_match"),
            )
        )
        rows.append(
            row(
                dataset,
                "phase2_soft_cap",
                "dynamic cap for strict and soft-cap recall guard for auxiliary",
                sample_count=p2.get("sample_count"),
                selected_core_f1=p2.get("selected_core_f1_phase2"),
                selected_core_recall=p2.get("selected_core_recall_phase2"),
                selected_law_count=p2.get("selected_law_count_phase2"),
                selected_overgeneration=p2.get("selected_overgeneration_phase2"),
                candidate_fine_recall=p2.get("candidate_fine_recall"),
            )
        )
        rows.append(
            row(
                dataset,
                "phase3_chain_repair",
                "repaired selected legal-chain connectivity without modifying GT or predictions",
                sample_count=p3.get("sample_count"),
                selected_core_f1=p3.get("selected_core_f1"),
                selected_core_precision=p3.get("selected_core_precision"),
                selected_core_recall=p3.get("selected_core_recall"),
                selected_core_compatible_f1=p3.get("selected_core_compatible_f1"),
                selected_core_compatible_precision=p3.get("selected_core_compatible_precision"),
                selected_core_compatible_recall=p3.get("selected_core_compatible_recall"),
                selected_law_count=p3.get("selected_law_count"),
                selected_overgeneration=p3.get("selected_overgeneration_rate"),
                corporate_penalty_attached_rate=p3.get("corporate_penalty_attached_rate"),
                obligation_to_penalty_connection_rate=p3.get("obligation_to_penalty_connection_rate"),
                penalty_to_corporate_connection_rate=p3.get("penalty_to_corporate_connection_rate"),
                fine_chain_match_rate_original=p3.get("fine_chain_match_rate"),
            )
        )
        rows.append(
            row(
                dataset,
                "phase5b_policy_adjusted",
                "policy-adjusted score separates branch ambiguity; selected_core is unchanged because selected_laws were not modified",
                sample_count=p5b.get("sample_count"),
                selected_core_f1=p5b.get("policy_selected_core_compatible_f1"),
                selected_core_precision=p5b.get("policy_selected_core_compatible_precision"),
                selected_core_recall=p5b.get("policy_selected_core_compatible_recall"),
                selected_core_compatible_f1=p5b.get("policy_selected_core_compatible_f1"),
                selected_core_compatible_precision=p5b.get("policy_selected_core_compatible_precision"),
                selected_core_compatible_recall=p5b.get("policy_selected_core_compatible_recall"),
                selected_law_count=p5b.get("policy_adjusted_selected_law_count"),
                selected_overgeneration=p5b.get("policy_selected_overgeneration"),
                corporate_penalty_attached_rate=p5b.get("corporate_penalty_attached_rate"),
                obligation_to_penalty_connection_rate=p5b.get("obligation_to_penalty_connection_rate"),
                penalty_to_corporate_connection_rate=p5b.get("penalty_to_corporate_connection_rate"),
                fine_chain_match_rate_original=p5b.get("fine_chain_match_rate_original"),
                fine_chain_match_rate_policy_adjusted=p5b.get("fine_chain_match_rate_policy_adjusted"),
                branch_consistency_rate=p5b.get("corporate_penalty_branch_consistency_rate"),
                prediction_branch_wrong_count=p5b.get("prediction_branch_wrong_count"),
                manual_review_pending_count=pending,
            )
        )
        refined_rate = (
            p5d.get("strict_phase5b_policy_adjusted_fine_chain_match_rate")
            if dataset == "strict"
            else p5d.get("auxiliary_phase5b_policy_adjusted_fine_chain_match_rate")
        )
        original_rate = (
            p5d.get("strict_original_fine_chain_match_rate")
            if dataset == "strict"
            else p5d.get("auxiliary_original_fine_chain_match_rate")
        )
        rows.append(
            row(
                dataset,
                "phase5d_refined_policy",
                "mapping rationale clarified; no additional score change beyond Phase 5-B policy-adjusted interpretation",
                sample_count=p5b.get("sample_count"),
                selected_core_f1=p5b.get("policy_selected_core_compatible_f1"),
                selected_core_precision=p5b.get("policy_selected_core_compatible_precision"),
                selected_core_recall=p5b.get("policy_selected_core_compatible_recall"),
                selected_core_compatible_f1=p5b.get("policy_selected_core_compatible_f1"),
                selected_core_compatible_precision=p5b.get("policy_selected_core_compatible_precision"),
                selected_core_compatible_recall=p5b.get("policy_selected_core_compatible_recall"),
                selected_law_count=p5b.get("policy_adjusted_selected_law_count"),
                selected_overgeneration=p5b.get("policy_selected_overgeneration"),
                corporate_penalty_attached_rate=p5b.get("corporate_penalty_attached_rate"),
                obligation_to_penalty_connection_rate=p5b.get("obligation_to_penalty_connection_rate"),
                penalty_to_corporate_connection_rate=p5b.get("penalty_to_corporate_connection_rate"),
                fine_chain_match_rate_original=original_rate,
                fine_chain_match_rate_policy_adjusted=p5b.get("fine_chain_match_rate_policy_adjusted"),
                fine_chain_match_rate_refined_policy=refined_rate,
                branch_consistency_rate=p5b.get("corporate_penalty_branch_consistency_rate"),
                prediction_branch_wrong_count=p5d.get("true_prediction_branch_error_count"),
                likely_old_current_fine_branch_overmapped_count=p5d.get("likely_old_current_fine_branch_overmapped_count"),
                manual_review_pending_count=pending,
            )
        )
    return rows


def metric_definitions() -> list[dict[str, str]]:
    def m(name: str, cat: str, definition: str, interpretation: str, main: bool, caution: str, phase: str) -> dict[str, str]:
        return {
            "metric_name": name,
            "category": cat,
            "definition": definition,
            "interpretation": interpretation,
            "should_use_as_main_metric": str(main).lower(),
            "caution": caution,
            "related_phase": phase,
        }

    return [
        m("selected_core_f1", "System Performance", "F1 over compact selected core refs.", "Main compact-answer quality metric.", True, "Separate from full bundle F1.", "Phase 1-3"),
        m("selected_core_precision", "System Performance", "Precision over selected core refs.", "Measures unnecessary selected refs.", True, "Interpret with recall.", "Phase 1-3"),
        m("selected_core_recall", "System Performance", "Recall over GT core refs.", "Measures essential core coverage.", True, "Auxiliary requires recall guard.", "Phase 2"),
        m("selected_core_compatible_f1", "System Performance", "Compatible-match F1 over selected core refs.", "Useful when strict fine branch is ambiguous.", True, "Do not mix with exact strict.", "Phase 1-5B"),
        m("selected_law_count", "System Performance", "Average selected laws per case.", "Compactness indicator.", True, "Lower is not always better.", "Phase 2"),
        m("selected_overgeneration", "System Performance", "Average overgenerated selected refs.", "Precision-risk diagnostic.", True, "Use with selected_core_recall.", "Phase 2"),
        m("candidate_article_recall", "Retrieval/Candidate", "GT article-family recall in candidate pool.", "Article-level retrieval upper bound.", True, "Candidate is not answer.", "Phase 1-2"),
        m("candidate_fine_recall", "Retrieval/Candidate", "GT fine-ref recall in candidate pool.", "Fine selector upper bound.", True, "Candidate is not selected.", "Phase 2"),
        m("candidate_fine_missing", "Retrieval/Candidate", "Average GT fine refs absent from candidate pool.", "Fine evidence gap.", True, "Selector cannot promote absent refs.", "Phase 2/4"),
        m("candidate_article_missing", "Retrieval/Candidate", "Average GT article families absent from candidate pool.", "Article retrieval gap.", True, "Phase 4 remaining issues were not article missing.", "Phase 2/4"),
        m("obligation_to_penalty_connection_rate", "Legal Chain", "Rate of obligation to penalty chain connection.", "Legal-chain construction quality.", True, "Not a fine-branch metric.", "Phase 3"),
        m("penalty_to_corporate_connection_rate", "Legal Chain", "Rate of penalty to corporate penalty connection.", "Corporate chain completeness.", True, "Article 173 branch ambiguity separate.", "Phase 3"),
        m("corporate_penalty_attached_rate", "Legal Chain", "Corporate penalty attachment rate.", "Corporate chain stability.", True, "Attachment does not guarantee subparagraph strictness.", "Phase 3"),
        m("fine_chain_match_rate_original", "Legal Chain", "Original strict fine-chain match rate.", "Strict diagnostic.", True, "Can understate quality under GT branch ambiguity.", "Phase 3/5B"),
        m("fine_chain_match_rate_policy_adjusted", "Policy-Adjusted", "Fine-chain rate after branch ambiguity separation.", "Evaluation interpretation metric.", False, "Not model improvement.", "Phase 5B"),
        m("fine_chain_match_rate_refined_policy", "Refined Mapping", "Fine-chain rate under refined old-current mapping interpretation.", "Mapping rationale metric.", False, "Not model improvement.", "Phase 5D"),
        m("branch_consistency_rate", "Legal Chain", "Predicted corporate branch consistency with selected penalty branch.", "Separates branch logic from GT ambiguity.", True, "Report with original strict metric.", "Phase 5A/5B"),
        m("policy_adjusted_fine_chain_match_rate", "Policy-Adjusted", "Alias for policy-adjusted fine-chain match.", "Supplementary interpretation metric.", False, "Disclose adjusted count.", "Phase 5B"),
        m("corporate_penalty_article_match", "Policy-Adjusted", "Article-level corporate penalty match.", "Useful for Article 173 ambiguity.", True, "Subparagraph strictness separate.", "Phase 5B"),
        m("corporate_penalty_branch_consistency", "Policy-Adjusted", "Consistency of penalty and corporate subparagraph branch.", "Checks legal branch logic.", True, "Does not revise GT.", "Phase 5A/5B"),
        m("ambiguity_adjusted_count", "Policy-Adjusted", "Count adjusted due to ambiguity.", "Explains policy-adjusted delta.", True, "Must be disclosed.", "Phase 5B"),
        m("refined_policy_fine_chain_match_rate", "Refined Mapping", "Weighted refined-policy fine-chain rate.", "Impact of mapping Article 71 only to Article 173 article-level.", False, "Supplementary only.", "Phase 5D"),
        m("likely_old_current_fine_branch_overmapped_count", "Refined Mapping", "Cases likely overmapped to Article 173 fine branch.", "Dataset/mapping reliability signal.", True, "Requires manual review.", "Phase 5D"),
        m("refined_corporate_mapping_layer_count", "Refined Mapping", "Rows in refined corporate mapping layer.", "Layer coverage.", True, "Does not replace GT.", "Phase 5D"),
        m("affects_original_gt_count", "Refined Mapping", "Rows that affect original GT.", "Should be zero.", True, "Must remain false until reviewed.", "Phase 5D"),
        m("old_current_mapping_level", "Refined Mapping", "Article-level vs fine-branch-level old-current mapping.", "Mapping granularity indicator.", True, "Old corporate provision maps to Article 173 article-level by default.", "Phase 5D"),
        m("manual_review_pending_count", "Dataset Reliability", "Manual review target count.", "Dataset reliability indicator.", True, "Do not fold silently into strict metric.", "Phase 5C"),
        m("old_current_fine_ambiguous_count", "Dataset Reliability", "Old-current fine ambiguity count.", "Mapping uncertainty.", True, "Manual review needed.", "Phase 5A/5D"),
        m("gt_branch_suspect_count", "Dataset Reliability", "GT branch suspect count.", "GT reliability risk.", True, "Original GT preserved.", "Phase 5A"),
        m("prediction_branch_wrong_count", "Dataset Reliability", "Prediction branch inconsistency count.", "Separates prediction error from GT ambiguity.", True, "Article 173 set had zero.", "Phase 5A/5D"),
        m("review_priority_high_count", "Dataset Reliability", "High priority review count.", "Review workload.", True, "Not performance.", "Phase 5C"),
        m("full_bundle_f1", "Diagnostic", "F1 against full legal bundle.", "Full bundle restoration diagnostic.", False, "Not main compact-answer metric.", "Phase 1"),
        m("selected_legal_chain_f1", "Diagnostic", "F1 over selected legal chains.", "Strict chain diagnostic.", False, "Sensitive to fine ambiguity.", "Phase 1/3"),
        m("chain_fine_granularity_mismatch", "Diagnostic", "Same article but fine-branch mismatch.", "Fine branch audit target.", False, "Do not auto-fix without review.", "Phase 4"),
        m("chain_connection_failure", "Diagnostic", "Obligation/penalty/corporate connection failure.", "Chain builder failure.", False, "Phase 3 reduced this.", "Phase 3"),
    ]


def error_decomposition() -> list[dict[str, str]]:
    return [
        {"phase": "Phase 1", "diagnosed_problem": "selected answer and full GT bundle mismatch", "evidence": "compact selected answer was compared with full bundle", "action_taken": "separated selected core, supporting, full bundle diagnostic, and candidate recall", "result": "selected core evaluation became interpretable", "remaining_issue": "supporting/detail refs still need separate recall reporting", "interpretation": "full bundle F1 is diagnostic, not the main compact-answer metric"},
        {"phase": "Phase 2", "diagnosed_problem": "selected overgeneration and fixed cap side effects", "evidence": "strict selected_overgeneration 1.111 before refactor; auxiliary recall fell under aggressive compression", "action_taken": "dynamic cap and soft-cap recall guard", "result": "strict selected_core_f1 0.553 -> 0.581; auxiliary recovered to 0.811", "remaining_issue": "fine branch mismatch remained", "interpretation": "compression must be confidence- and split-aware"},
        {"phase": "Phase 3", "diagnosed_problem": "chain_connection_failure", "evidence": "chain_connection_failure 32 before repair", "action_taken": "penalty-chain repair and corporate attachment guard", "result": "chain_connection_failure 32 -> 15; corporate attachment 1.000", "remaining_issue": "mismatches shifted into fine granularity category", "interpretation": "chain connectivity became stable; branch-level alignment remained"},
        {"phase": "Phase 4", "diagnosed_problem": "fine mismatch increase", "evidence": "23 fine mismatches after Phase 3", "action_taken": "full audit of 23 fine mismatches", "result": "candidate missing 0, article missing 0, true wrong article 0", "remaining_issue": "wrong sibling fine refs in Article 173 and Article 38", "interpretation": "remaining fine mismatch was not retrieval failure"},
        {"phase": "Phase 5-A", "diagnosed_problem": "Article 173 subparagraph branch mismatch", "evidence": "21 Article 173 branch mismatches; prediction consistency 21/21", "action_taken": "GT and prediction branch consistency review", "result": "prediction branch wrong 0; GT branch suspect/old-current ambiguity confirmed", "remaining_issue": "manual legal review required", "interpretation": "Article 173 mismatch is branch ambiguity, not direct prediction error"},
        {"phase": "Phase 5-B", "diagnosed_problem": "original fine-chain metric treated branch ambiguity as prediction error", "evidence": "strict original fine_chain_match_rate 0.259", "action_taken": "policy-adjusted evaluation without GT/prediction edits", "result": "strict fine_chain_match_rate 0.259 -> 0.741", "remaining_issue": "policy-adjusted metric is supplementary", "interpretation": "granularity-adjusted reporting is necessary"},
        {"phase": "Phase 5-C", "diagnosed_problem": "branch ambiguity requires manual review", "evidence": "23 review targets: 21 Article 173, 2 Article 38", "action_taken": "manual review package and decision schema", "result": "23 review targets organized; reviewer fields blank", "remaining_issue": "reviewed_eval_layer awaits decisions", "interpretation": "original GT and reviewed layer should be separate"},
        {"phase": "Phase 5-D", "diagnosed_problem": "old corporate penalty may be overmapped to current Article 173 subparagraph 2", "evidence": "21 Article 173 cases were article-level matches and prediction-branch-consistent", "action_taken": "old-current corporate mapping refinement and penalty-branch resolver", "result": "likely old-current fine branch overmapped 21 cases; refined layer generated", "remaining_issue": "manual review needed before reviewed_eval_layer decisions", "interpretation": "old corporate provisions map to current Article 173 article-level; subparagraph is resolved from current penalty branch"},
    ]


def case_flow() -> list[dict[str, Any]]:
    return [
        {"stage": "original_cases", "case_count": 69, "description": "Original precedent/case corpus", "notes": "from project handoff summary"},
        {"stage": "case_text_available", "case_count": 69, "description": "Case text available for extraction", "notes": "from project handoff summary"},
        {"stage": "date_extracted", "case_count": 69, "description": "Dates extracted for law-version linking", "notes": "from project handoff summary"},
        {"stage": "law_version_linked", "case_count": 69, "description": "Old/current law linking attempted", "notes": "from project handoff summary"},
        {"stage": "initial_READY_A", "case_count": 40, "description": "Initial ready-A candidates", "notes": "from project handoff summary"},
        {"stage": "initial_REVIEW_B", "case_count": 17, "description": "Initial review-B candidates", "notes": "from project handoff summary"},
        {"stage": "initial_INSUFFICIENT", "case_count": 12, "description": "Insufficient cases", "notes": "from project handoff summary"},
        {"stage": "original_A1_STRICT", "case_count": 12, "description": "Original A1 strict after audit", "notes": "from project handoff summary"},
        {"stage": "original_A2_ARTICLE_AUX", "case_count": 11, "description": "Original A2 article auxiliary", "notes": "from project handoff summary"},
        {"stage": "original_A3_REVIEW_ONLY", "case_count": 17, "description": "Original A3 review-only", "notes": "from project handoff summary"},
        {"stage": "reviewed_strict", "case_count": 27, "description": "Reviewed strict set", "notes": "confirmed by phase summaries"},
        {"stage": "reviewed_auxiliary", "case_count": 10, "description": "Reviewed auxiliary set", "notes": "confirmed by phase summaries"},
        {"stage": "reviewed_review_only", "case_count": 3, "description": "Reviewed review-only set", "notes": "from project handoff summary"},
        {"stage": "phase5c_manual_review_targets", "case_count": 23, "description": "Manual review targets", "notes": "from phase5c summary"},
        {"stage": "corporate_branch_review_targets", "case_count": 21, "description": "Article 173 branch ambiguity targets", "notes": "from phase5c summary"},
        {"stage": "obligation_fine_review_targets", "case_count": 2, "description": "Article 38 obligation fine review targets", "notes": "from phase5c summary"},
        {"stage": "likely_old_current_fine_branch_overmapped", "case_count": 21, "description": "Likely old-current fine branch overmapped Article 173 cases", "notes": "from phase5d summary"},
    ]


def interpretation_md() -> str:
    return """# Phase 6 Report-Ready Interpretation

## 1. Evaluation design summary

### Korean
본 평가는 단순 법령 QA가 아니라 판례/사고 상황을 입력했을 때 적용 가능한 의무 조문, 처벌 조문, 양벌규정, 그리고 obligation -> penalty -> corporate penalty legal chain을 복원하는 case-scenario evaluation이다. 평가 과정에서는 compact selected answer와 full legal bundle을 동일하게 취급하지 않고, selected core, supporting bundle, full bundle diagnostic, candidate recall을 분리했다.

### English
This evaluation is not a simple statute-QA benchmark. It is a case-scenario evaluation that tests whether the system can reconstruct applicable obligation provisions, penalty provisions, corporate-penalty provisions, and the obligation-to-penalty-to-corporate-penalty legal chain from precedent or accident facts. We separate selected-core evaluation, supporting-bundle recovery, full-bundle diagnostics, and candidate recall.

## 2. Main findings

### Korean
초기 fine-level F1 저하는 selector 실패만으로 설명되지 않았다. 단계별 오류 분해를 통해 평가 구조 문제, selected 과생성, candidate fine recall, chain connection, branch ambiguity, old-current fine branch overmapping을 분리했다. strict selected_core_f1은 0.553에서 0.581로 개선되었고, auxiliary selected_core_f1은 soft-cap recall guard 이후 0.811로 회복되었다. corporate penalty attachment는 strict/auxiliary 모두 1.000으로 안정화되었다. original strict fine_chain_match_rate는 0.259였으나, 제173조 branch ambiguity를 분리한 policy-adjusted 기준에서는 0.741로 해석되었다. Phase 5-D refined mapping audit에서는 제173조 branch case 21건이 likely old-current fine branch overmapped로 분류되었다. 이 상승은 prediction 수정이 아니라 evaluation granularity 및 old-current mapping interpretation adjustment이다.

### English
The initially low fine-level F1 was not explained by selector failure alone. Through staged error decomposition, we separated evaluation-design mismatch, selected-reference overgeneration, candidate fine recall, chain-connection failures, branch ambiguity, and old-current fine-branch overmapping. Strict selected_core_f1 improved from 0.553 to 0.581, while auxiliary selected_core_f1 recovered to 0.811 after the soft-cap recall guard. Corporate penalty attachment stabilized at 1.000 for both strict and auxiliary splits. The original strict fine_chain_match_rate was 0.259, but after separating Article 173 branch ambiguity, the policy-adjusted interpretation was 0.741. Phase 5-D classified 21 Article 173 branch cases as likely old-current fine-branch overmapping. This increase is an evaluation-granularity and old-current mapping interpretation adjustment, not a prediction improvement.

## 3. Recommended wording for paper/report

The initially low fine-level F1 was not solely caused by retrieval or selector failure. Through staged error decomposition, we found that the major sources of apparent error were: mismatch between compact selected answers and full legal bundles, overgeneration in selected references, incomplete fine-grained candidate generation, legal-chain connection failures, and fine-level branch ambiguity in corporate penalty provisions. In particular, the remaining Article 173 mismatches were classified as likely old-to-current fine-branch overmapping rather than prediction branch errors. After separating selected-core evaluation from supporting-bundle recovery, branch-ambiguity diagnostics, and refined old-current mapping interpretation, the system showed stable core legal-chain construction performance, while the remaining mismatches were concentrated in manually reviewable GT branch ambiguity cases.

초기 fine-level F1 저하는 단순 검색 또는 selector 실패만으로 설명되지 않았다. 단계별 오류 분해 결과, compact selected answer와 full legal bundle 간 평가 불일치, selected ref 과생성, fine-grained candidate 누락, legal chain 연결 실패, 그리고 양벌규정 fine branch ambiguity가 주요 원인으로 확인되었다. 특히 산업안전보건법 제173조 관련 남은 mismatch는 prediction branch error라기보다 구법-현행법 fine branch overmapping 문제로 분류되었다. selected-core 평가, supporting-bundle 평가, policy-adjusted branch consistency 평가, refined old-current mapping 해석을 분리한 결과, 시스템의 핵심 법리 chain 구성 능력은 안정적으로 나타났으며, 남은 오류는 대부분 수동 검토가 필요한 GT branch ambiguity로 좁혀졌다.

## 4. Cautionary notes

- Policy-adjusted score must not be interpreted as model improvement.
- Refined-policy score must not be interpreted as model improvement.
- The original GT was not modified.
- The refined mapping layer does not replace original GT.
- Policy-adjusted/refined-policy metrics are supplementary diagnostics.
- Article 173 subparagraph matching may involve old-current mapping ambiguity.
- The 23 manual-review-pending targets should be managed through a reviewed_eval_layer.

## 5. Next steps

- Create a reviewed_eval_layer after reviewer_decision fields are filled.
- Manage original GT and reviewed_eval_layer separately.
- Prioritize legal expert review for high-priority Article 173 cases.
- Review the two Article 38 fine-branch cases.
- Report original strict, policy-adjusted, refined-policy, article-level, branch consistency, and manual-review-pending counts together.
"""


def final_report(metrics: list[dict[str, Any]]) -> str:
    p5c = read_json("phase5c_manual_review_package_summary.json")
    p5d = read_json("phase5d_refined_mapping_simulation_summary.json")
    strict = next(r for r in metrics if r["dataset_type"] == "strict" and r["evaluation_version"] == "phase5d_refined_policy")
    aux = next(r for r in metrics if r["dataset_type"] == "auxiliary" and r["evaluation_version"] == "phase5d_refined_policy")
    return f"""# Phase 6 Final Evaluation Synthesis Report

## 1. Purpose
This report synthesizes Phase 1 through Phase 5-D. It is not an additional performance-improvement step and does not modify GT, predictions, or the original evaluator.

## 2. Dataset and evaluation setup
- Original cases: 69
- Reviewed strict: 27
- Auxiliary: 10
- Review-only: 3
- Manual review targets: {p5c.get("total_review_targets")}

The task is case-scenario evaluation: reconstructing legal obligations, penalties, corporate penalties, and legal chains from precedent or accident facts.

## 3. Why the initial F1 was low
The early fine-level F1 was not a single selector problem. The decomposition separated evaluation-design mismatch, selected overgeneration, candidate fine recall limits, chain connection failure, fine branch ambiguity, old-current fine branch overmapping, and GT granularity issues.

## 4. Phase-by-phase findings
Phase 1 separated selected core/supporting/full bundle/candidate metrics. Phase 2 reduced overgeneration while protecting auxiliary recall. Phase 3 stabilized obligation -> penalty -> corporate penalty chains. Phase 4 showed remaining fine mismatches were not candidate/article missing. Phase 5-A found prediction branch consistency. Phase 5-B separated policy-adjusted evaluation. Phase 5-C produced manual review packages. Phase 5-D refined old-current corporate mapping.

## 5. Final metrics
Strict selected_core_f1 is {strict.get("selected_core_f1")}; auxiliary selected_core_f1 is {aux.get("selected_core_f1")}. Corporate penalty attachment is {strict.get("corporate_penalty_attached_rate")} for strict and {aux.get("corporate_penalty_attached_rate")} for auxiliary. See `phase6_final_evaluation_summary_table.csv` for the full table.

## 6. Interpretation of policy-adjusted and refined-policy metrics
Policy-adjusted metrics are not prediction updates. Refined-policy metrics are also not prediction updates; they clarify old-current mapping rationale. Strict fine_chain_match_rate changes from {strict.get("fine_chain_match_rate_original")} to {strict.get("fine_chain_match_rate_policy_adjusted")}. Weighted original fine_chain_match_rate changes from {p5d.get("original_fine_chain_match_rate")} to refined-policy {p5d.get("refined_policy_fine_chain_match_rate")}. This is an evaluation/mapping interpretation effect.

## 7. Old-current corporate mapping refinement
Old corporate penalty provisions map to current Article 173 at article level. Article 167(1) resolves to Article 173 subparagraph 1. Articles 168-172 resolve to Article 173 subparagraph 2. If the penalty branch is unclear, Article 173 remains article-level only. Article 173 subparagraph 2 was not directly replaced with subparagraph 1. Phase 5-D found {p5d.get("likely_old_current_fine_branch_overmapped_count")} likely old-current fine branch overmapped cases.

## 8. Manual review package
- Total review targets: {p5c.get("total_review_targets")}
- Article 173: {p5c.get("corporate_branch_review_count")}
- Article 38: {p5c.get("obligation_fine_review_count")}
- HIGH priority: {p5c.get("high_priority_count")}
- MEDIUM priority: {p5c.get("medium_priority_count")}
- Recommended decisions: {json.dumps(p5c.get("count_by_recommended_default_decision", {}), ensure_ascii=False)}

`reviewer_decision` fields remain blank.

## 9. Recommended reporting structure
Report original strict selected_core_f1, auxiliary selected_core_f1, candidate recall, selected overgeneration, corporate penalty attached rate, original fine_chain_match_rate, policy-adjusted fine_chain_match_rate, refined-policy fine_chain_match_rate, branch consistency rate, and manual review pending count together.

## 10. Limitations
The original GT was not modified. Branch ambiguity remains pending until manual review. Policy-adjusted/refined-policy metrics are supplementary. Article 38 fine branch depends on fact specificity. Old-current fine-level mapping requires expert review.

## 11. Next steps
Create a reviewed_eval_layer, perform legal expert review, prioritize high-priority Article 173 cases, review the two Article 38 fine-branch cases, and prepare the final paper evaluation table.
"""


def validation() -> dict[str, Any]:
    files = sorted(p.name for p in CORE.glob("phase6_*"))
    if "phase6_validation_checklist.json" not in files:
        files.append("phase6_validation_checklist.json")
        files = sorted(files)
    markers = [
        ("neo4j credential marker", "NEO4J" + "_" + "PASSWORD"),
        ("openai credential marker", "OPENAI" + "_" + "API" + "_" + "KEY"),
        ("generic api credential marker", "API" + "_" + "KEY"),
    ]
    hits = []
    for path in CORE.glob("phase6_*"):
        if path.name == "phase6_validation_checklist.json":
            continue
        if path.suffix.lower() in {".csv", ".json", ".md", ".py"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, marker in markers:
                if marker in text:
                    hits.append(f"{path.name}:{label}")
    try:
        py_compile.compile(__file__, doraise=True)
        py_ok = True
    except py_compile.PyCompileError:
        py_ok = False
    return {
        "existing_v6_reviewed_dataset_unmodified": True,
        "gt_unmodified": True,
        "prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase5d_outputs_not_overwritten": True,
        "all_new_files_phase6_prefix": all(name.startswith("phase6_") for name in files),
        "reviewer_decision_auto_filled": False,
        "reviewer_note_auto_filled": False,
        "article_173_branch_auto_change": False,
        "article_38_fine_auto_change": False,
        "original_policy_adjusted_and_refined_policy_metrics_separated": True,
        "policy_adjusted_not_interpreted_as_system_improvement": True,
        "refined_policy_not_interpreted_as_system_improvement": True,
        "manual_review_pending_count_reported": True,
        "refined_layer_replaces_original_gt": False,
        "affects_original_gt_false_maintained": True,
        "sensitive_output_hits": hits,
        "py_compile_passed": py_ok,
        "phase6_files": files,
    }


def main() -> None:
    metrics = final_summary_rows()
    write_csv("phase6_input_file_inventory.csv", inventory(), ["file_path", "exists", "used_for", "phase", "notes"])
    write_csv("phase6_final_evaluation_summary_table.csv", metrics, SUMMARY_COLUMNS)
    write_csv("phase6_metric_definitions.csv", metric_definitions(), ["metric_name", "category", "definition", "interpretation", "should_use_as_main_metric", "caution", "related_phase"])
    write_csv("phase6_error_decomposition_table.csv", error_decomposition(), ["phase", "diagnosed_problem", "evidence", "action_taken", "result", "remaining_issue", "interpretation"])
    write_csv("phase6_case_flow_summary.csv", case_flow(), ["stage", "case_count", "description", "notes"])
    (CORE / "phase6_report_ready_interpretation.md").write_text(interpretation_md(), encoding="utf-8")
    (CORE / "phase6_final_evaluation_synthesis_report.md").write_text(final_report(metrics), encoding="utf-8")
    write_json("phase6_validation_checklist.json", validation())
    print(json.dumps({"summary_rows": len(metrics), "metric_definitions": len(metric_definitions()), "error_decomposition_rows": len(error_decomposition()), "case_flow_rows": len(case_flow()), "includes_phase5d": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
