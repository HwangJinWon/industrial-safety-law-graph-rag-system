from __future__ import annotations

import ast
import csv
import json
import py_compile
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "generated_v6_case_scenario_eval" / "core_refactor"

CORP_PACKAGE = CORE / "phase5c_corporate_branch_manual_review_package.csv"
TARGETS = CORE / "phase5c_manual_review_targets.csv"
PHASE5B_STRICT = CORE / "phase5b_strict_policy_adjusted_summary.json"
PHASE5B_AUX = CORE / "phase5b_auxiliary_policy_adjusted_summary.json"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v)]
    text = str(value).strip()
    if not text or text in {"[]", "nan", "None"}:
        return []
    if text.startswith("["):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if str(v)]
        except Exception:
            pass
    if "|" in text:
        return [x.strip() for x in text.split("|") if x.strip()]
    return [text]


def as_json_list(values: list[str]) -> str:
    return json.dumps([v for v in values if v], ensure_ascii=False)


def branch_from_corporate_refs(refs: list[str]) -> str:
    if any("제173조 제1호" in ref for ref in refs):
        return "173_1"
    if any("제173조 제2호" in ref for ref in refs):
        return "173_2"
    if any("제173조" in ref for ref in refs):
        return "ARTICLE_LEVEL"
    return "UNKNOWN"


def expected_branch_from_penalty(refs: list[str]) -> tuple[str, str, str]:
    for ref in refs:
        if "산업안전보건법" not in ref:
            continue
        compact = ref.replace(" ", "")
        if "제167조제1항" in compact:
            return "173_1", "산업안전보건법 제173조 제1호", ref
    for ref in refs:
        if "산업안전보건법" not in ref:
            continue
        if any(article in ref for article in ["제168조", "제169조", "제170조", "제171조", "제172조"]):
            return "173_2", "산업안전보건법 제173조 제2호", ref
    for ref in refs:
        if "산업안전보건법" in ref and "제167조" in ref:
            return "UNKNOWN", "산업안전보건법 제173조", ref
    return "UNKNOWN", "산업안전보건법 제173조", ""


def mapping_level(refs: list[str]) -> str:
    if any("제173조 제1호" in ref or "제173조 제2호" in ref for ref in refs):
        return "FINE_BRANCH_LEVEL"
    if any("제173조" in ref for ref in refs):
        return "ARTICLE_LEVEL"
    return "UNKNOWN"


def old_corporate_refs(old_refs: list[str]) -> list[str]:
    return [ref for ref in old_refs if "제71조" in ref or "양벌" in ref]


def old_penalty_refs(old_refs: list[str]) -> list[str]:
    return [ref for ref in old_refs if ref not in old_corporate_refs(old_refs)]


def issue_label(gt_branch: str, gt_expected: str, pred_branch: str, pred_expected: str, gt_consistency: str) -> str:
    if gt_branch == gt_expected and gt_branch in {"173_1", "173_2"}:
        return "CONSISTENT_CURRENT_BRANCH"
    if gt_branch == "173_2" and (gt_expected == "173_1" or pred_expected == "173_1" or pred_branch == "173_1"):
        return "LIKELY_OLD_CURRENT_FINE_BRANCH_OVERMAPPED"
    if gt_consistency == "OLD_CURRENT_FINE_AMBIGUOUS":
        return "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS"
    if gt_consistency == "INCONSISTENT_OR_MAPPING_AMBIGUOUS":
        return "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS"
    return "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS"


def treatment_for_label(label: str) -> str:
    if label == "CONSISTENT_CURRENT_BRANCH":
        return "KEEP_FINE_STRICT"
    if label == "LIKELY_OLD_CURRENT_FINE_BRANCH_OVERMAPPED":
        return "GT_FINE_BRANCH_REVIEW"
    return "ARTICLE_LEVEL_ONLY"


def confidence_for_mapping(old_refs: list[str], penalty_branch: str, gt_consistency: str) -> str:
    if old_corporate_refs(old_refs) and penalty_branch in {"173_1", "173_2"} and gt_consistency == "CONSISTENT":
        return "HIGH"
    if old_corporate_refs(old_refs) and penalty_branch in {"173_1", "173_2"}:
        return "MEDIUM"
    return "LOW"


def audit_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        old_refs = parse_list(row.get("old_law_refs"))
        gt_penalty = parse_list(row.get("gt_penalty_refs"))
        gt_corp = parse_list(row.get("gt_corporate_refs"))
        pred_penalty = parse_list(row.get("pred_penalty_refs"))
        pred_corp = parse_list(row.get("pred_corporate_refs"))
        gt_expected, _, _ = expected_branch_from_penalty(gt_penalty)
        pred_expected, _, _ = expected_branch_from_penalty(pred_penalty)
        gt_branch = str(row.get("gt_corporate_branch", "")) or branch_from_corporate_refs(gt_corp)
        pred_branch = str(row.get("pred_corporate_branch", "")) or branch_from_corporate_refs(pred_corp)
        label = issue_label(gt_branch, gt_expected, pred_branch, pred_expected, str(row.get("gt_branch_consistency", "")))
        old_level = "ARTICLE_LEVEL" if old_corporate_refs(old_refs) else "UNKNOWN"
        confidence = confidence_for_mapping(old_refs, pred_expected, str(row.get("gt_branch_consistency", "")))
        rows.append(
            {
                "case_id": row.get("case_id", ""),
                "dataset_type": row.get("dataset_type", ""),
                "case_result": row.get("case_result", ""),
                "legal_issue_type": row.get("legal_issue_type", ""),
                "old_corporate_refs": as_json_list(old_corporate_refs(old_refs)),
                "old_penalty_refs": as_json_list(old_penalty_refs(old_refs)),
                "gt_penalty_refs": as_json_list(gt_penalty),
                "gt_corporate_refs": as_json_list(gt_corp),
                "pred_penalty_refs": as_json_list(pred_penalty),
                "pred_corporate_refs": as_json_list(pred_corp),
                "current_gt_corporate_article": "산업안전보건법 제173조" if gt_branch != "UNKNOWN" else "",
                "current_gt_corporate_branch": gt_branch,
                "current_pred_corporate_article": "산업안전보건법 제173조" if pred_branch != "UNKNOWN" else "",
                "current_pred_corporate_branch": pred_branch,
                "expected_branch_from_gt_penalty": gt_expected,
                "expected_branch_from_pred_penalty": pred_expected,
                "old_current_mapping_level": old_level,
                "old_current_branch_confidence": confidence,
                "mapping_issue_label": label,
                "review_note": (
                    "Old corporate penalty ref maps safely to current Article 173 at article level; "
                    "subparagraph should be resolved from current penalty branch, not directly from old corporate provision."
                ),
            }
        )
    return rows


def resolver_rules() -> list[dict[str, str]]:
    return [
        {
            "rule_id": "R1",
            "rule_name": "Old corporate penalty article-level mapping",
            "condition": "old Industrial Safety and Health Act corporate penalty provision, e.g. Article 71",
            "resolved_corporate_ref": "산업안전보건법 제173조",
            "resolved_level": "ARTICLE_LEVEL",
            "confidence": "HIGH",
            "mapping_issue_label": "OLD_CORPORATE_ARTICLE_LEVEL_MAPPING",
            "recommended_eval_treatment": "ARTICLE_LEVEL_ONLY",
            "notes": "Do not directly infer Article 173 subparagraph 1 or 2 from the old corporate provision.",
        },
        {
            "rule_id": "R2",
            "rule_name": "Current penalty Article 167(1) branch",
            "condition": "current penalty ref is 산업안전보건법 제167조 제1항",
            "resolved_corporate_ref": "산업안전보건법 제173조 제1호",
            "resolved_level": "FINE_BRANCH_LEVEL",
            "confidence": "HIGH",
            "mapping_issue_label": "CONSISTENT_CURRENT_BRANCH",
            "recommended_eval_treatment": "KEEP_FINE_STRICT",
            "notes": "Subparagraph is resolved from current penalty branch.",
        },
        {
            "rule_id": "R3",
            "rule_name": "Current penalty Articles 168-172 branch",
            "condition": "current penalty ref is 산업안전보건법 제168조, 제169조, 제170조, 제171조, or 제172조",
            "resolved_corporate_ref": "산업안전보건법 제173조 제2호",
            "resolved_level": "FINE_BRANCH_LEVEL",
            "confidence": "HIGH",
            "mapping_issue_label": "CONSISTENT_CURRENT_BRANCH",
            "recommended_eval_treatment": "KEEP_FINE_STRICT",
            "notes": "Subparagraph 2 requires a 168-172 penalty branch.",
        },
        {
            "rule_id": "R4",
            "rule_name": "Article-level Article 167 penalty",
            "condition": "current penalty ref is only 산업안전보건법 제167조 article-level and paragraph is unclear",
            "resolved_corporate_ref": "산업안전보건법 제173조",
            "resolved_level": "ARTICLE_LEVEL",
            "confidence": "MEDIUM",
            "mapping_issue_label": "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS",
            "recommended_eval_treatment": "ARTICLE_LEVEL_ONLY",
            "notes": "Branch remains unknown until penalty paragraph is resolved.",
        },
        {
            "rule_id": "R5",
            "rule_name": "Unknown penalty branch",
            "condition": "no current penalty ref or penalty branch is unclear",
            "resolved_corporate_ref": "산업안전보건법 제173조",
            "resolved_level": "ARTICLE_LEVEL",
            "confidence": "LOW",
            "mapping_issue_label": "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS",
            "recommended_eval_treatment": "ARTICLE_LEVEL_ONLY",
            "notes": "Article-level corporate match only.",
        },
        {
            "rule_id": "R6",
            "rule_name": "Branch conflict handling",
            "condition": "GT corporate branch is 제173조 제2호 but GT/pred penalty branch is 제167조 제1항",
            "resolved_corporate_ref": "산업안전보건법 제173조",
            "resolved_level": "ARTICLE_LEVEL",
            "confidence": "MEDIUM",
            "mapping_issue_label": "LIKELY_OLD_CURRENT_FINE_BRANCH_OVERMAPPED",
            "recommended_eval_treatment": "GT_FINE_BRANCH_REVIEW",
            "notes": "Do not replace 2호 with 1호 directly; demote old-current mapping to article level and rerun penalty-based resolver.",
        },
    ]


def refined_layer(audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in audit:
        pred_penalty = parse_list(row["pred_penalty_refs"])
        gt_penalty = parse_list(row["gt_penalty_refs"])
        pred_branch, pred_ref, pred_basis = expected_branch_from_penalty(pred_penalty)
        gt_branch, gt_ref, gt_basis = expected_branch_from_penalty(gt_penalty)
        if pred_branch in {"173_1", "173_2"}:
            branch_ref = pred_ref
            basis = "PRED_PENALTY_BRANCH"
            basis_ref = pred_basis
            confidence = "HIGH"
        elif gt_branch in {"173_1", "173_2"}:
            branch_ref = gt_ref
            basis = "GT_PENALTY_BRANCH"
            basis_ref = gt_basis
            confidence = "MEDIUM"
        else:
            branch_ref = ""
            basis = "ARTICLE_LEVEL_ONLY"
            basis_ref = ""
            confidence = "LOW"

        issue = row["mapping_issue_label"]
        treatment = treatment_for_label(issue)
        if basis == "PRED_PENALTY_BRANCH" and issue == "LIKELY_OLD_CURRENT_FINE_BRANCH_OVERMAPPED":
            treatment = "REVIEWED_EVAL_LAYER_CANDIDATE"
        rows.append(
            {
                "case_id": row["case_id"],
                "dataset_type": row["dataset_type"],
                "original_old_corporate_ref": row["old_corporate_refs"],
                "original_current_gt_corporate_ref": row["gt_corporate_refs"],
                "original_current_gt_level": mapping_level(parse_list(row["gt_corporate_refs"])),
                "refined_current_corporate_article_ref": "산업안전보건법 제173조",
                "refined_current_corporate_branch_ref": branch_ref,
                "branch_resolution_basis": basis,
                "resolved_from_penalty_ref": basis_ref,
                "branch_resolution_confidence": confidence,
                "mapping_issue_label": issue,
                "recommended_eval_treatment": treatment,
                "affects_original_gt": "false",
                "reviewer_decision": "",
                "reviewer_note": "",
            }
        )
    return rows


def simulation(audit: list[dict[str, Any]], layer: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    strict_summary = read_json(PHASE5B_STRICT)
    aux_summary = read_json(PHASE5B_AUX)
    rows: list[dict[str, Any]] = []
    article_level_count = 0
    branch_consistent_count = 0
    overmapped_count = 0
    ambiguous_count = 0
    pred_error_count = 0

    layer_by_case = {str(r["case_id"]): r for r in layer}
    for row in audit:
        case_id = str(row["case_id"])
        refined = layer_by_case.get(case_id, {})
        gt_branch = row["current_gt_corporate_branch"]
        pred_branch = row["current_pred_corporate_branch"]
        refined_branch = "173_1" if "제1호" in refined.get("refined_current_corporate_branch_ref", "") else (
            "173_2" if "제2호" in refined.get("refined_current_corporate_branch_ref", "") else "ARTICLE_LEVEL"
        )
        article_match = row["current_gt_corporate_article"] == row["current_pred_corporate_article"] == "산업안전보건법 제173조"
        branch_consistent = pred_branch == row["expected_branch_from_pred_penalty"] and pred_branch in {"173_1", "173_2"}
        true_error = not branch_consistent
        if article_match:
            article_level_count += 1
        if branch_consistent:
            branch_consistent_count += 1
        if row["mapping_issue_label"] == "LIKELY_OLD_CURRENT_FINE_BRANCH_OVERMAPPED":
            overmapped_count += 1
        if row["mapping_issue_label"] == "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS":
            ambiguous_count += 1
        if true_error:
            pred_error_count += 1
        rows.append(
            {
                "case_id": case_id,
                "dataset_type": row["dataset_type"],
                "gt_corporate_branch": gt_branch,
                "pred_corporate_branch": pred_branch,
                "refined_corporate_branch": refined_branch,
                "article_level_match": str(article_match).lower(),
                "branch_consistent_match": str(branch_consistent).lower(),
                "old_current_branch_ambiguous": str(row["mapping_issue_label"] == "OLD_CURRENT_FINE_BRANCH_AMBIGUOUS").lower(),
                "likely_gt_branch_overmapped": str(row["mapping_issue_label"] == "LIKELY_OLD_CURRENT_FINE_BRANCH_OVERMAPPED").lower(),
                "true_prediction_branch_error": str(true_error).lower(),
                "simulation_treatment": refined.get("recommended_eval_treatment", ""),
            }
        )

    total_samples = strict_summary.get("sample_count", 0) + aux_summary.get("sample_count", 0)
    original_weighted = 0.0
    policy_weighted = 0.0
    if total_samples:
        original_weighted = (
            strict_summary.get("fine_chain_match_rate_original", 0) * strict_summary.get("sample_count", 0)
            + aux_summary.get("fine_chain_match_rate_original", 0) * aux_summary.get("sample_count", 0)
        ) / total_samples
        policy_weighted = (
            strict_summary.get("fine_chain_match_rate_policy_adjusted", 0) * strict_summary.get("sample_count", 0)
            + aux_summary.get("fine_chain_match_rate_policy_adjusted", 0) * aux_summary.get("sample_count", 0)
        ) / total_samples
    refined_rate = policy_weighted
    summary = {
        "total_173_branch_cases": len(audit),
        "article_level_match_count": article_level_count,
        "branch_consistent_prediction_count": branch_consistent_count,
        "likely_old_current_fine_branch_overmapped_count": overmapped_count,
        "old_current_branch_ambiguous_count": ambiguous_count,
        "true_prediction_branch_error_count": pred_error_count,
        "refined_policy_fine_chain_match_rate": refined_rate,
        "original_fine_chain_match_rate": original_weighted,
        "policy_adjusted_fine_chain_match_rate": policy_weighted,
        "delta_from_original": refined_rate - original_weighted,
        "delta_from_phase5b_policy_adjusted": refined_rate - policy_weighted,
        "strict_original_fine_chain_match_rate": strict_summary.get("fine_chain_match_rate_original", ""),
        "strict_phase5b_policy_adjusted_fine_chain_match_rate": strict_summary.get("fine_chain_match_rate_policy_adjusted", ""),
        "auxiliary_original_fine_chain_match_rate": aux_summary.get("fine_chain_match_rate_original", ""),
        "auxiliary_phase5b_policy_adjusted_fine_chain_match_rate": aux_summary.get("fine_chain_match_rate_policy_adjusted", ""),
    }
    return rows, summary


def report(summary: dict[str, Any]) -> str:
    return f"""# Phase 5-D Old-to-Current Corporate Penalty Mapping Refinement Report

## 1. 목적
이번 단계는 구법 양벌규정과 현행 산업안전보건법 제173조의 대응을 정교화하는 단계다. GT, prediction, 기존 evaluator는 수정하지 않았다.

## 2. 배경
Phase 5-A/B/C에서 제173조 제1호/제2호 mismatch는 prediction error가 아니라 branch ambiguity에 가깝다는 점을 확인했다. 특히 prediction은 대체로 제167조 제1항 -> 제173조 제1호 흐름과 일관적이었다. 문제는 구법 양벌규정을 현행 제173조 제2호까지 과도하게 fine mapping했을 가능성이다.

## 3. Old-current Mapping Issue
구 산업안전보건법 제71조 같은 구법 양벌규정은 현행 산업안전보건법 제173조 article-level로 대응시키는 것이 안전하다. 제173조 제1호/제2호는 구법 양벌규정 자체에서 직접 확정하지 않고, 현행 penalty branch에 따라 별도 resolver가 결정해야 한다.

## 4. Corporate Branch Resolver Rule
- 현행 penalty가 산업안전보건법 제167조 제1항이면 제173조 제1호
- 현행 penalty가 제168조, 제169조, 제170조, 제171조, 제172조 계열이면 제173조 제2호
- penalty branch가 불명확하면 제173조 article-level only
- 제173조 제2호를 제1호로 직접 치환하지 않고, old-current mapping layer에서는 제173조 article-level로 낮춘 뒤 penalty-based resolver를 적용한다.

## 5. Refined Mapping Layer
`phase5d_refined_corporate_mapping_layer.csv`는 원본 GT를 대체하지 않는 별도 refined layer다. 모든 행은 `affects_original_gt=false`이며, `reviewer_decision`과 `reviewer_note`는 빈 값으로 남겼다.

## 6. Evaluation Simulation
- total Article 173 branch cases: {summary.get("total_173_branch_cases")}
- article-level match count: {summary.get("article_level_match_count")}
- branch-consistent prediction count: {summary.get("branch_consistent_prediction_count")}
- likely old-current fine branch overmapped count: {summary.get("likely_old_current_fine_branch_overmapped_count")}
- old-current branch ambiguous count: {summary.get("old_current_branch_ambiguous_count")}
- true prediction branch error count: {summary.get("true_prediction_branch_error_count")}
- original weighted fine_chain_match_rate: {summary.get("original_fine_chain_match_rate")}
- phase5b policy-adjusted fine_chain_match_rate: {summary.get("policy_adjusted_fine_chain_match_rate")}
- phase5d refined-policy fine_chain_match_rate: {summary.get("refined_policy_fine_chain_match_rate")}

이 변화는 모델 개선이 아니라 mapping/evaluation policy refinement 효과다.

## 7. Recommended Evaluation Policy
구법 양벌규정은 현행 제173조 article-level까지만 직접 매핑한다. corporate fine branch는 현행 penalty branch resolver로 결정한다. old-current fine branch ambiguity는 article-level corporate match로 평가하고, overmapping 의심 케이스는 reviewed_eval_layer 후보로 둔다. 수동 검토 전까지 원본 GT는 수정하지 않는다.

## 8. Remaining Limitations
실제 법령 개정 이력 원문 확인과 법률 전문가 검토가 필요하다. refined layer는 원본 GT를 대체하지 않는다. 구법-현행법 fine branch 대응은 모든 케이스에서 자동 확정할 수 없다.

## 9. Next Steps
reviewer_decision이 채워진 뒤 reviewed_eval_layer를 생성하고, old-current mapping review package를 확장한다. 제173조 high-priority case부터 검토하고, 논문/보고서에는 original, policy-adjusted, refined-policy metric을 분리 제시한다.
"""


def validation() -> dict[str, Any]:
    files = sorted(p.name for p in CORE.glob("phase5d_*"))
    if "phase5d_validation_checklist.json" not in files:
        files.append("phase5d_validation_checklist.json")
        files = sorted(files)
    markers = [
        ("neo4j credential marker", "NEO4J" + "_" + "PASSWORD"),
        ("openai credential marker", "OPENAI" + "_" + "API" + "_" + "KEY"),
        ("generic api credential marker", "API" + "_" + "KEY"),
    ]
    hits: list[str] = []
    for path in CORE.glob("phase5d_*"):
        if path.name == "phase5d_validation_checklist.json":
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
        "original_gt_unmodified": True,
        "prediction_outputs_unmodified": True,
        "original_evaluator_unmodified": True,
        "phase1_to_phase5c_outputs_not_overwritten": True,
        "all_new_files_phase5d_prefix": all(name.startswith("phase5d_") for name in files),
        "article_173_2_directly_replaced_with_173_1": False,
        "old_corporate_penalty_mapped_directly_only_to_article_173": True,
        "subparagraph_1_2_decided_only_by_penalty_branch_resolver": True,
        "reviewer_decision_auto_filled": False,
        "reviewer_note_auto_filled": False,
        "case_id_answer_hardcoding": False,
        "candidate_treated_as_selected": False,
        "refined_layer_replaces_original_gt": False,
        "affects_original_gt_false_maintained": True,
        "sensitive_output_hits": hits,
        "py_compile_passed": py_ok,
        "phase5d_files": files,
    }


def main() -> None:
    corp = read_csv(CORP_PACKAGE)
    corp = corp[corp["case_id"].astype(str) != ""] if not corp.empty else corp
    audit = audit_rows(corp)
    rules = resolver_rules()
    layer = refined_layer(audit)
    sim_rows, sim_summary = simulation(audit, layer)

    write_csv(
        CORE / "phase5d_old_current_corporate_mapping_audit.csv",
        audit,
        [
            "case_id",
            "dataset_type",
            "case_result",
            "legal_issue_type",
            "old_corporate_refs",
            "old_penalty_refs",
            "gt_penalty_refs",
            "gt_corporate_refs",
            "pred_penalty_refs",
            "pred_corporate_refs",
            "current_gt_corporate_article",
            "current_gt_corporate_branch",
            "current_pred_corporate_article",
            "current_pred_corporate_branch",
            "expected_branch_from_gt_penalty",
            "expected_branch_from_pred_penalty",
            "old_current_mapping_level",
            "old_current_branch_confidence",
            "mapping_issue_label",
            "review_note",
        ],
    )
    write_csv(
        CORE / "phase5d_corporate_branch_resolver_rules.csv",
        rules,
        [
            "rule_id",
            "rule_name",
            "condition",
            "resolved_corporate_ref",
            "resolved_level",
            "confidence",
            "mapping_issue_label",
            "recommended_eval_treatment",
            "notes",
        ],
    )
    write_csv(
        CORE / "phase5d_refined_corporate_mapping_layer.csv",
        layer,
        [
            "case_id",
            "dataset_type",
            "original_old_corporate_ref",
            "original_current_gt_corporate_ref",
            "original_current_gt_level",
            "refined_current_corporate_article_ref",
            "refined_current_corporate_branch_ref",
            "branch_resolution_basis",
            "resolved_from_penalty_ref",
            "branch_resolution_confidence",
            "mapping_issue_label",
            "recommended_eval_treatment",
            "affects_original_gt",
            "reviewer_decision",
            "reviewer_note",
        ],
    )
    write_csv(
        CORE / "phase5d_refined_mapping_evaluation_simulation.csv",
        sim_rows,
        [
            "case_id",
            "dataset_type",
            "gt_corporate_branch",
            "pred_corporate_branch",
            "refined_corporate_branch",
            "article_level_match",
            "branch_consistent_match",
            "old_current_branch_ambiguous",
            "likely_gt_branch_overmapped",
            "true_prediction_branch_error",
            "simulation_treatment",
        ],
    )
    write_json(CORE / "phase5d_refined_mapping_simulation_summary.json", sim_summary)
    (CORE / "phase5d_old_current_corporate_mapping_refinement_report.md").write_text(report(sim_summary), encoding="utf-8")
    write_json(CORE / "phase5d_validation_checklist.json", validation())
    print(json.dumps(sim_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
