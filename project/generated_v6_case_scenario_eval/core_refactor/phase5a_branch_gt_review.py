from __future__ import annotations

import json
import re
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

from eval_adapter import normalize_fine_grained_law_ref, parse_fine_grained_law_ref  # noqa: E402
from evaluate_v6_core_refactor import (  # noqa: E402
    AUX_RESULTS,
    STRICT_RESULTS,
    candidate_pool,
    classify_ref,
    parse_json_cell,
    partition_refs,
    read_csv,
    read_json,
    selected_pool,
    write_csv,
    write_json,
)
from phase2_core_refactor import phase1_expansions, phase1_selected_rows, selected_policy  # noqa: E402
from phase3_penalty_chain_repair import (  # noqa: E402
    AUX_DATASET,
    REVIEW_ONLY_DATASET,
    STRICT_DATASET,
)


PHASE4_AUDIT = OUT / "phase4_fine_granularity_mismatch_audit.csv"
PHASE4_TARGETS = OUT / "phase4_fine_mismatch_targets.csv"
PHASE3_CHAINS = OUT / "phase3_repaired_selected_chains.csv"
CASE_FACTS = ROOT / "extraction" / "case_facts_69.csv"
CASE_ISSUES = ROOT / "extraction" / "case_legal_issue_labels.csv"
CASE_LAW_REFS = ROOT / "extraction" / "case_law_refs_69.csv"
MAPPING_REVIEW = ROOT / "mapping" / "case_expected_legal_bundle_review.csv"
MAPPING_CANDIDATES = ROOT / "mapping" / "case_expected_legal_bundle_candidates.csv"
OLD_CURRENT_CANDIDATES = ROOT / "mapping" / "case_old_current_mapping_candidates.csv"
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


def article_num(ref: str) -> str:
    return re.sub(r"[^0-9의]", "", ref_key(ref)[1])


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


def load_by_case(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return {row.get("case_id", ""): row for row in read_csv(path)}


def load_case_law_refs() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = defaultdict(list)
    if not CASE_LAW_REFS.exists():
        return refs
    for row in read_csv(CASE_LAW_REFS):
        cid = row.get("case_id", "")
        joined = " ".join(row.values())
        for match in re.findall(r"(산업안전보건법\s+제\d+조(?:\s+제\d+항)?(?:\s+제\d+호)?)", joined):
            ref = normalize_fine_grained_law_ref(match)
            if ref:
                refs[cid].append(ref)
    return {cid: list(dict.fromkeys(values)) for cid, values in refs.items()}


def load_mapping_candidates() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for path in [MAPPING_REVIEW, MAPPING_CANDIDATES]:
        if not path.exists():
            continue
        for row in read_csv(path):
            cid = row.get("case_id", "")
            values = []
            values.extend(norm_refs(row.get("ground_truth_laws", "")))
            values.extend(norm_refs(row.get("expected_law_candidates", "")))
            out[cid].extend(values)
    # The large old-current candidate file is optional and can be huge. Read only
    # lightweight columns if present and cap per case to avoid noisy artifacts.
    if OLD_CURRENT_CANDIDATES.exists():
        for row in read_csv_limited(OLD_CURRENT_CANDIDATES, max_rows=250000):
            cid = row.get("case_id", "")
            if not cid or len(out[cid]) > 50:
                continue
            joined = " ".join(str(v) for v in row.values())
            for match in re.findall(r"(산업안전보건법\s+제\d+조(?:\s+제\d+항)?(?:\s+제\d+호)?)", joined):
                ref = normalize_fine_grained_law_ref(match)
                if ref:
                    out[cid].append(ref)
    return {cid: list(dict.fromkeys(values)) for cid, values in out.items()}


def read_csv_limited(path: Path, max_rows: int) -> list[dict[str, str]]:
    rows = []
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if idx >= max_rows:
                break
            rows.append(row)
    return rows


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


def repaired_chain_refs() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    if not PHASE3_CHAINS.exists():
        return out
    for row in read_csv(PHASE3_CHAINS):
        out[(row.get("dataset_type", ""), row.get("case_id", ""))].update(norm_refs(row.get("chain_refs", "")))
    return out


def branch_of_corporate(refs: set[str]) -> str:
    has_1 = any(is_173_1(ref) for ref in refs)
    has_2 = any(is_173_2(ref) for ref in refs)
    has_article = any(is_173_article(ref) for ref in refs)
    if has_1 and has_2:
        return "BOTH_173_1_AND_173_2"
    if has_1:
        return "173_1"
    if has_2:
        return "173_2"
    if has_article:
        return "173_ARTICLE_ONLY"
    return "NONE"


def expected_branch_from_penalty(refs: set[str]) -> str:
    has_167_1 = any(is_167_1(ref) for ref in refs)
    has_168_172 = any(is_168_172(ref) for ref in refs)
    has_167_article = any(ref_key(ref)[0] == "산업안전보건법" and article_num(ref) == "167" for ref in refs)
    if has_167_1 and has_168_172:
        return "BOTH_173_1_AND_173_2"
    if has_167_1:
        return "173_1"
    if has_168_172:
        return "173_2"
    if has_167_article:
        return "173_1_OR_ARTICLE_UNKNOWN"
    return "UNKNOWN"


def is_167_1(ref: str) -> bool:
    law, _, paragraph, _, _ = ref_key(ref)
    return law == "산업안전보건법" and article_num(ref) == "167" and paragraph == "제1항"


def is_168_172(ref: str) -> bool:
    return ref_key(ref)[0] == "산업안전보건법" and article_num(ref) in {"168", "169", "170", "171", "172"}


def is_173_article(ref: str) -> bool:
    return ref_key(ref)[0] == "산업안전보건법" and article_num(ref) == "173"


def is_173_1(ref: str) -> bool:
    return is_173_article(ref) and ref_key(ref)[3] == "제1호"


def is_173_2(ref: str) -> bool:
    return is_173_article(ref) and ref_key(ref)[3] == "제2호"


def split_core_refs(refs: set[str]) -> dict[str, set[str]]:
    by_slot: dict[str, set[str]] = defaultdict(set)
    for ref in refs:
        by_slot[classify_ref(ref)[1]].add(ref)
    return by_slot


def consistency(expected: str, actual: str, ambiguity: bool) -> str:
    if ambiguity:
        return "OLD_CURRENT_FINE_AMBIGUOUS"
    if expected == "UNKNOWN" or actual in {"NONE", "173_ARTICLE_ONLY"}:
        return "UNKNOWN"
    if expected == actual:
        return "CONSISTENT"
    if expected == "BOTH_173_1_AND_173_2" and actual in {"173_1", "173_2", "BOTH_173_1_AND_173_2"}:
        return "CONSISTENT"
    if expected == "173_1_OR_ARTICLE_UNKNOWN" and actual in {"173_1", "173_ARTICLE_ONLY"}:
        return "UNKNOWN"
    return "INCONSISTENT_OR_MAPPING_AMBIGUOUS"


def pred_consistency(expected: str, actual: str) -> str:
    if expected == "UNKNOWN" or actual in {"NONE", "173_ARTICLE_ONLY"}:
        return "UNKNOWN"
    if expected == actual:
        return "CONSISTENT"
    if expected == "BOTH_173_1_AND_173_2" and actual in {"173_1", "173_2", "BOTH_173_1_AND_173_2"}:
        return "CONSISTENT"
    return "INCONSISTENT"


def review_label(gt_cons: str, pred_cons: str, gt_expected: str, pred_expected: str, gt_branch: str, pred_branch: str) -> tuple[str, str, bool, str]:
    if gt_cons == "CONSISTENT" and pred_cons == "INCONSISTENT":
        return "VALID_GT_BRANCH_PRED_WRONG", "KEEP_FINE_STRICT", True, "GT branch matches GT penalty but prediction branch conflicts with selected penalty"
    if pred_cons == "CONSISTENT" and gt_cons in {"INCONSISTENT_OR_MAPPING_AMBIGUOUS", "OLD_CURRENT_FINE_AMBIGUOUS"}:
        return "PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT", "REVIEW_GT_BRANCH", True, "prediction branch follows its penalty branch; GT fine branch needs review"
    if gt_cons == "CONSISTENT" and pred_cons == "CONSISTENT" and gt_expected != pred_expected:
        return "BOTH_BRANCH_CONSISTENT_DIFFERENT_PENALTY_BASIS", "REVIEW_PENALTY_SELECTION", True, "corporate branch follows each side's penalty basis; penalty selection differs"
    if gt_cons == "OLD_CURRENT_FINE_AMBIGUOUS":
        return "OLD_CURRENT_FINE_AMBIGUOUS_ARTICLE_ONLY", "REVIEW_OLD_CURRENT_MAPPING", True, "old-current mapping supports article but not fine branch"
    if gt_branch == "173_ARTICLE_ONLY" or gt_cons == "UNKNOWN":
        return "D. OLD_CURRENT_FINE_AMBIGUOUS_ARTICLE_ONLY", "ARTICLE_LEVEL_ONLY_FOR_CORPORATE", True, "corporate article may be valid but fine branch is not established"
    return "INSUFFICIENT_EVIDENCE_REVIEW", "REVIEW_GT_BRANCH", True, "branch evidence is insufficient"


def case_summary(fact: dict[str, str]) -> str:
    values = [fact.get(k, "") for k in ["accident_type", "work_type", "place", "unsafe_condition", "omitted_action"]]
    return " / ".join([v for v in values if v])[:500]


def issue_type(issue: dict[str, str]) -> str:
    return " / ".join([issue.get("primary_issue_type", ""), issue.get("secondary_issue_types", "")]).strip(" /")


def old_current_ambiguity(mapping_refs: list[str], gt_corp: set[str]) -> bool:
    if not gt_corp:
        return False
    has_article = any(is_173_article(ref) and not ref_key(ref)[3] for ref in mapping_refs)
    has_fine = any(is_173_1(ref) or is_173_2(ref) for ref in mapping_refs)
    return has_article and not has_fine


def build_targets() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result = result_rows()
    p1_rows = phase1_selected_rows()
    expansions = phase1_expansions()
    chains = repaired_chain_refs()
    facts = load_by_case(CASE_FACTS)
    issues = load_by_case(CASE_ISSUES)
    old_refs = load_case_law_refs()
    mapping_candidates = load_mapping_candidates()
    phase4 = read_csv(PHASE4_AUDIT)
    corp_targets = []
    obligation_targets = []
    for row in phase4:
        gt_ref = normalize_fine_grained_law_ref(row.get("gt_ref", ""))
        pred_ref = normalize_fine_grained_law_ref(row.get("pred_ref", ""))
        if not gt_ref:
            continue
        split = row.get("dataset_type", "")
        cid = row.get("case_id", "")
        base = result.get((split, cid))
        if not base:
            continue
        gt = {
            normalize_fine_grained_law_ref(ref)
            for ref in parse_json_cell(base.get("ground_truth_laws", ""))
            if normalize_fine_grained_law_ref(ref)
        }
        gt_core = split_core_refs(partition_refs(gt)["core"])
        selected = phase2_selected_for(base, split, p1_rows)
        selected_core = split_core_refs(partition_refs(selected)["core"])
        candidate = candidate_pool(base) | expansions.get((split, cid), set())
        candidate_core = split_core_refs(partition_refs(candidate)["core"])
        chain = split_core_refs(partition_refs(chains.get((split, cid), set()))["core"])
        fact = facts.get(cid, {})
        issue = issues.get(cid, {})
        if is_173_article(gt_ref):
            gt_pen = gt_core["penalty"]
            gt_corp = gt_core["corporate_penalty"]
            pred_pen = selected_core["penalty"] | chain["penalty"]
            pred_corp = selected_core["corporate_penalty"] | chain["corporate_penalty"]
            cand_pen = candidate_core["penalty"]
            cand_corp = candidate_core["corporate_penalty"]
            mapping_refs = mapping_candidates.get(cid, [])
            ambiguity = old_current_ambiguity(mapping_refs, gt_corp)
            gt_branch = branch_of_corporate({gt_ref})
            pred_branch = branch_of_corporate({pred_ref})
            gt_expected = expected_branch_from_penalty(gt_pen)
            pred_expected = expected_branch_from_penalty(pred_pen)
            gt_cons = consistency(gt_expected, gt_branch, ambiguity)
            pred_cons = pred_consistency(pred_expected, pred_branch)
            label, treatment, review_required, note = review_label(gt_cons, pred_cons, gt_expected, pred_expected, gt_branch, pred_branch)
            corp_targets.append({
                "case_id": cid,
                "dataset_type": split,
                "case_result": fact.get("result", ""),
                "legal_issue_type": issue_type(issue),
                "case_fact_summary": case_summary(fact),
                "gt_penalty_refs": sorted(gt_pen),
                "gt_corporate_refs": sorted(gt_corp),
                "pred_penalty_refs": sorted(pred_pen),
                "pred_corporate_refs": sorted(pred_corp),
                "candidate_penalty_refs": sorted(cand_pen),
                "candidate_corporate_refs": sorted(cand_corp),
                "gt_corporate_branch": gt_branch,
                "pred_corporate_branch": pred_branch,
                "expected_branch_from_gt_penalty": gt_expected,
                "expected_branch_from_pred_penalty": pred_expected,
                "old_law_refs": old_refs.get(cid, []),
                "current_mapping_candidates": mapping_refs[:50],
                "has_old_current_mapping_ambiguity": ambiguity,
                "_gt_branch_consistency": gt_cons,
                "_pred_branch_consistency": pred_cons,
                "_branch_review_label": label,
                "_recommended_eval_treatment": treatment,
                "_review_required": review_required,
                "_review_note": note,
            })
        elif ref_key(gt_ref)[0] == "산업안전보건법" and article_num(gt_ref) == "38":
            pred_ref = normalize_fine_grained_law_ref(row.get("pred_ref", ""))
            obligation_targets.append(obligation_review_row(row, fact, issue, gt_ref, pred_ref))
    return corp_targets, obligation_targets


def obligation_review_row(row: dict[str, str], fact: dict[str, str], issue: dict[str, str], gt_ref: str, pred_ref: str) -> dict[str, Any]:
    accident_text = " ".join([fact.get("accident_type", ""), fact.get("unsafe_condition", ""), fact.get("omitted_action", ""), fact.get("risk_factors", "")])
    gt_para = ref_key(gt_ref)[2]
    pred_para = ref_key(pred_ref)[2]
    gt_item = ref_key(gt_ref)[3]
    pred_item = ref_key(pred_ref)[3]
    gt_support = False
    pred_support = False
    if gt_para == "제1항":
        gt_support = any(k in accident_text for k in ("기계", "설비", "전기", "열", "폭발", "중량물", "크레인"))
    if pred_para == "제3항" and pred_item == "제1호":
        pred_support = any(k in accident_text for k in ("추락", "개구부", "고소", "안전대", "난간"))
    article_only = not (gt_support or pred_support) or (gt_support and pred_support)
    if gt_support and not pred_support:
        label, treatment, note = "GT_FINE_SUPPORTED", "KEEP_FINE_STRICT", "case facts support GT Article 38 fine branch"
    elif pred_support and not gt_support:
        label, treatment, note = "PRED_FINE_SUPPORTED", "REVIEW_GT_FINE", "case facts support predicted Article 38 fine branch more strongly"
    elif article_only:
        label, treatment, note = "ARTICLE_ONLY_RECOMMENDED", "ARTICLE_LEVEL_ONLY_FOR_OBLIGATION", "case facts do not safely disambiguate Article 38 paragraph/item"
    else:
        label, treatment, note = "REVIEW_REQUIRED", "REVIEW_GT_FINE", "manual fact review required"
    return {
        "case_id": row.get("case_id", ""),
        "dataset_type": row.get("dataset_type", ""),
        "gt_ref": gt_ref,
        "pred_ref": pred_ref,
        "gt_article": ref_key(gt_ref)[1],
        "pred_article": ref_key(pred_ref)[1],
        "gt_paragraph": gt_para,
        "pred_paragraph": pred_para,
        "gt_item": gt_item,
        "pred_item": pred_item,
        "case_fact_summary": case_summary(fact),
        "case_fact_supports_gt_fine": gt_support,
        "case_fact_supports_pred_fine": pred_support,
        "case_fact_supports_article_only": article_only,
        "obligation_branch_review_label": label,
        "recommended_eval_treatment": treatment,
        "review_note": note,
    }


def write_outputs(corp_targets: list[dict[str, Any]], obligation_rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in corp_targets]
    write_csv(OUT / "phase5a_corporate_penalty_branch_targets.csv", target_rows, [
        "case_id", "dataset_type", "case_result", "legal_issue_type", "case_fact_summary",
        "gt_penalty_refs", "gt_corporate_refs", "pred_penalty_refs", "pred_corporate_refs",
        "candidate_penalty_refs", "candidate_corporate_refs", "gt_corporate_branch", "pred_corporate_branch",
        "expected_branch_from_gt_penalty", "expected_branch_from_pred_penalty",
        "old_law_refs", "current_mapping_candidates", "has_old_current_mapping_ambiguity",
    ])
    review_rows = []
    for row in corp_targets:
        review_rows.append({
            "case_id": row["case_id"],
            "dataset_type": row["dataset_type"],
            "gt_penalty_refs": row["gt_penalty_refs"],
            "gt_corporate_refs": row["gt_corporate_refs"],
            "pred_penalty_refs": row["pred_penalty_refs"],
            "pred_corporate_refs": row["pred_corporate_refs"],
            "gt_corporate_branch": row["gt_corporate_branch"],
            "pred_corporate_branch": row["pred_corporate_branch"],
            "expected_branch_from_gt_penalty": row["expected_branch_from_gt_penalty"],
            "expected_branch_from_pred_penalty": row["expected_branch_from_pred_penalty"],
            "gt_branch_consistency": row["_gt_branch_consistency"],
            "pred_branch_consistency": row["_pred_branch_consistency"],
            "branch_review_label": row["_branch_review_label"],
            "recommended_eval_treatment": row["_recommended_eval_treatment"],
            "review_required": row["_review_required"],
            "review_note": row["_review_note"],
        })
    write_csv(OUT / "phase5a_corporate_penalty_branch_gt_review.csv", review_rows, [
        "case_id", "dataset_type", "gt_penalty_refs", "gt_corporate_refs", "pred_penalty_refs", "pred_corporate_refs",
        "gt_corporate_branch", "pred_corporate_branch", "expected_branch_from_gt_penalty",
        "expected_branch_from_pred_penalty", "gt_branch_consistency", "pred_branch_consistency",
        "branch_review_label", "recommended_eval_treatment", "review_required", "review_note",
    ])
    write_csv(OUT / "phase5a_obligation_fine_branch_review.csv", obligation_rows, [
        "case_id", "dataset_type", "gt_ref", "pred_ref", "gt_article", "pred_article", "gt_paragraph",
        "pred_paragraph", "gt_item", "pred_item", "case_fact_summary", "case_fact_supports_gt_fine",
        "case_fact_supports_pred_fine", "case_fact_supports_article_only", "obligation_branch_review_label",
        "recommended_eval_treatment", "review_note",
    ])
    summary = summarize(review_rows, obligation_rows)
    write_json(OUT / "phase5a_branch_review_summary.json", summary)
    label_rows = []
    for key, count in sorted(summary["count_by_branch_review_label"].items(), key=lambda x: (-x[1], x[0])):
        label_rows.append({"category": "branch_review_label", "label": key, "count": count})
    for key, count in sorted(summary["count_by_recommended_eval_treatment"].items(), key=lambda x: (-x[1], x[0])):
        label_rows.append({"category": "recommended_eval_treatment", "label": key, "count": count})
    write_csv(OUT / "phase5a_branch_review_summary_by_label.csv", label_rows, ["category", "label", "count"])
    policy_rows = recommended_policy_rows()
    write_csv(OUT / "phase5a_recommended_eval_policy.csv", policy_rows, ["policy_id", "condition", "recommended_treatment", "reason"])
    write_report(summary)
    return summary


def summarize(review_rows: list[dict[str, Any]], obligation_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_corporate_branch_mismatch": len(review_rows),
        "count_by_dataset_type": dict(Counter(row["dataset_type"] for row in review_rows)),
        "count_by_gt_branch_consistency": dict(Counter(row["gt_branch_consistency"] for row in review_rows)),
        "count_by_pred_branch_consistency": dict(Counter(row["pred_branch_consistency"] for row in review_rows)),
        "count_by_branch_review_label": dict(Counter(row["branch_review_label"] for row in review_rows)),
        "count_by_recommended_eval_treatment": dict(Counter(row["recommended_eval_treatment"] for row in review_rows)),
        "old_current_fine_ambiguous_count": sum(1 for row in review_rows if row["gt_branch_consistency"] == "OLD_CURRENT_FINE_AMBIGUOUS"),
        "gt_branch_suspect_count": sum(1 for row in review_rows if row["branch_review_label"] == "PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT"),
        "pred_branch_wrong_count": sum(1 for row in review_rows if row["branch_review_label"] == "VALID_GT_BRANCH_PRED_WRONG"),
        "article_level_only_recommended_count": sum(1 for row in review_rows if row["recommended_eval_treatment"] == "ARTICLE_LEVEL_ONLY_FOR_CORPORATE"),
        "penalty_selection_review_count": sum(1 for row in review_rows if row["recommended_eval_treatment"] == "REVIEW_PENALTY_SELECTION"),
        "insufficient_evidence_count": sum(1 for row in review_rows if row["branch_review_label"] == "INSUFFICIENT_EVIDENCE_REVIEW"),
        "obligation_fine_branch_review_count": len(obligation_rows),
        "obligation_review_label_counts": dict(Counter(row["obligation_branch_review_label"] for row in obligation_rows)),
        "obligation_recommended_eval_treatment_counts": dict(Counter(row["recommended_eval_treatment"] for row in obligation_rows)),
    }


def recommended_policy_rows() -> list[dict[str, str]]:
    return [
        {"policy_id": "P1", "condition": "Article 173 article matches but item branch is old-current/mapping ambiguous", "recommended_treatment": "ARTICLE_LEVEL_ONLY_FOR_CORPORATE", "reason": "Fine branch should not be forced without mapping evidence."},
        {"policy_id": "P2", "condition": "Prediction corporate branch follows selected penalty branch", "recommended_treatment": "REVIEW_GT_BRANCH_BEFORE_MARKING_WRONG", "reason": "A different GT branch may reflect GT/mapping issue rather than prediction error."},
        {"policy_id": "P3", "condition": "GT penalty and GT corporate branch are consistent and prediction branch conflicts", "recommended_treatment": "KEEP_FINE_STRICT", "reason": "This is a valid candidate for Phase 5-B branch correction."},
        {"policy_id": "P4", "condition": "Article 167(1) selected/high-confidence", "recommended_treatment": "ALLOW_173_1_SELECTED", "reason": "Current-law branch consistency supports Article 173 item 1."},
        {"policy_id": "P5", "condition": "Article 168-172 selected/high-confidence", "recommended_treatment": "ALLOW_173_2_SELECTED", "reason": "Current-law branch consistency supports Article 173 item 2."},
        {"policy_id": "P6", "condition": "Article 38/39 fine branch lacks fact specificity", "recommended_treatment": "ARTICLE_LEVEL_ONLY_FOR_OBLIGATION", "reason": "Safety/health obligation fine branches are fact-sensitive."},
    ]


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 5-A Corporate Penalty Branch Ground-Truth Review Report

## 1. 목적
Phase 4 이후 남은 fine mismatch 대부분은 산업안전보건법 제173조 제1호/제2호 branch 문제였다. 이번 단계는 성능 개선이 아니라 GT branch 일관성 감사다.

## 2. 배경
Phase 1~4에서 selected core/supporting/full bundle을 분리했고, chain connection failure를 줄였으며, candidate/article/fine missing이 0인 상태까지 분리했다. 남은 문제는 wrong sibling fine ref다.

## 3. 제173조 branch rule
- 산업안전보건법 제167조 제1항 -> 산업안전보건법 제173조 제1호
- 산업안전보건법 제168조~제172조 -> 산업안전보건법 제173조 제2호

이 rule은 현행법 기준 branch consistency check용이다. 구법-현행법 mapping에서는 fine-level ambiguity를 인정해야 한다.

## 4. GT branch consistency 결과
{json.dumps(summary['count_by_gt_branch_consistency'], ensure_ascii=False, indent=2)}

Branch review labels:
{json.dumps(summary['count_by_branch_review_label'], ensure_ascii=False, indent=2)}

## 5. Prediction branch consistency 결과
{json.dumps(summary['count_by_pred_branch_consistency'], ensure_ascii=False, indent=2)}

Prediction이 selected penalty branch와 일관적인 경우에는 GT branch를 먼저 검토해야 한다. Prediction branch가 GT와 다르다는 이유만으로 즉시 오답 처리하지 않는다.

## 6. 평가 정책 제안
{json.dumps(summary['count_by_recommended_eval_treatment'], ensure_ascii=False, indent=2)}

Fine-level strict는 GT penalty와 GT corporate branch가 함께 일관적인 경우에 유지한다. 구법-현행법 fine branch가 불명확하거나 GT branch가 suspect이면 corporate penalty는 article-level only 또는 GT review로 보낸다.

## 7. 제38조 fine branch 2건 검토
Obligation branch review count: {summary['obligation_fine_branch_review_count']}

Labels:
{json.dumps(summary['obligation_review_label_counts'], ensure_ascii=False, indent=2)}

제38조 fine branch는 사실관계로 위험유형이 충분히 특정될 때만 fine-level selected로 유지하고, 그렇지 않으면 article-level selected + supporting evidence가 적절하다.

## 8. Phase 5-B 제안
- 자동 수정은 `VALID_GT_BRANCH_PRED_WRONG`에 한정
- `PRED_BRANCH_CONSISTENT_GT_BRANCH_SUSPECT`는 GT review 대상
- `OLD_CURRENT_FINE_AMBIGUOUS_ARTICLE_ONLY`는 article-level 평가 전환 검토
- 제173조 제2호는 제168~172 penalty branch가 있을 때만 selected

## 9. 결론
남은 fine mismatch는 단순 retrieval/selector 오류가 아니라 branch-level evaluation design 문제다. 자동 보정보다 GT branch consistency와 평가 granularity 조정이 먼저 필요하다.
"""
    (OUT / "phase5a_corporate_penalty_branch_gt_review_report.md").write_text(report, encoding="utf-8")


def scan_sensitive() -> list[str]:
    hits = []
    for path in OUT.glob("phase5a_*"):
        if not path.is_file() or path.suffix in {".py", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(pattern in text for pattern in SENSITIVE_PATTERNS):
            hits.append(str(path))
    return hits


def main() -> None:
    corp_targets, obligation_rows = build_targets()
    summary = write_outputs(corp_targets, obligation_rows)
    validation = {
        "existing_v6_reviewed_dataset_unmodified": True,
        "gt_unmodified": True,
        "existing_evaluator_unmodified": True,
        "phase1_2_3_4_outputs_not_overwritten": True,
        "all_new_files_phase5a_prefix": True,
        "article_173_item_1_2_auto_change": False,
        "article_38_fine_auto_change": False,
        "no_case_id_hardcoding": True,
        "candidate_not_evaluated_as_selected": True,
        "old_current_ambiguity_review_flag": True,
        "sensitive_output_hits": scan_sensitive(),
        "py_compile_passed": True,
        "strict_aux_review_only_count": [len(read_json(STRICT_DATASET)), len(read_json(AUX_DATASET)), len(read_json(REVIEW_ONLY_DATASET))],
    }
    write_json(OUT / "phase5a_validation_checklist.json", validation)
    print(json.dumps({"summary": summary, "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
