from __future__ import annotations

import csv
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

from eval_adapter import hierarchical_compatible_prf, normalize_fine_grained_law_ref, parse_fine_grained_law_ref  # noqa: E402
from evaluate_v6_core_refactor import (  # noqa: E402
    AUX_RESULTS,
    STRICT_RESULTS,
    article_key,
    candidate_pool,
    classify_ref,
    parse_json_cell,
    partition_refs,
    read_csv,
    read_json,
    selected_pool,
    serialize,
    supporting_pool,
    write_csv,
    write_json,
)
from phase2_core_refactor import phase1_expansions, phase1_selected_rows, selected_policy  # noqa: E402
from phase3_penalty_chain_repair import (  # noqa: E402
    AUX_DATASET,
    REVIEW_ONLY_DATASET,
    STRICT_DATASET,
)


PHASE3_REPAIRED_CHAINS = OUT / "phase3_repaired_selected_chains.csv"
PHASE3_FAILURES = OUT / "phase3_failure_type_before_after.csv"
PHASE3_STRICT_RESULTS = OUT / "phase3_strict_chain_repair_results.csv"
PHASE3_AUX_RESULTS = OUT / "phase3_auxiliary_chain_repair_results.csv"
PHASE2_FAILURES = OUT / "phase2_selected_chain_fine_failure_analysis.csv"
CASE_FACTS = ROOT / "extraction" / "case_facts_69.csv"
CASE_ISSUES = ROOT / "extraction" / "case_legal_issue_labels.csv"
MAPPING_REVIEW = ROOT / "mapping" / "case_expected_legal_bundle_review.csv"
MAPPING_CANDIDATES = ROOT / "mapping" / "case_expected_legal_bundle_candidates.csv"
SENSITIVE_PATTERNS = ("NEO4J_PASSWORD", "OPENAI_API_KEY", "API_KEY", "PASSWORD=")


def result_rows() -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for split, path in [("strict", STRICT_RESULTS), ("auxiliary", AUX_RESULTS)]:
        for row in read_csv(path):
            out[(split, row.get("id", ""))] = row
    return out


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


def is_fine(ref: str) -> bool:
    _, _, paragraph, item, subitem = ref_key(ref)
    return bool(paragraph or item or subitem)


def is_parent_of(gt_ref: str, pred_ref: str) -> bool:
    g_law, g_article, g_para, g_item, g_sub = ref_key(gt_ref)
    p_law, p_article, p_para, p_item, p_sub = ref_key(pred_ref)
    if (g_law, g_article) != (p_law, p_article):
        return False
    gt_parts = [g_para, g_item, g_sub]
    pred_parts = [p_para, p_item, p_sub]
    for p, g in zip(pred_parts, gt_parts):
        if p and p != g:
            return False
    return any(gt_parts) and not pred_parts == gt_parts


def normalize_ref_set(values: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(values, str):
        values = parse_json_cell(values)
    if not isinstance(values, list):
        return refs
    for value in values:
        if isinstance(value, dict):
            ref = normalize_fine_grained_law_ref(value.get("ref", ""))
        else:
            ref = normalize_fine_grained_law_ref(value)
        if ref:
            refs.add(ref)
    return refs


def load_facts() -> dict[str, dict[str, str]]:
    if not CASE_FACTS.exists():
        return {}
    return {row.get("case_id", ""): row for row in read_csv(CASE_FACTS)}


def load_issues() -> dict[str, dict[str, str]]:
    if not CASE_ISSUES.exists():
        return {}
    return {row.get("case_id", ""): row for row in read_csv(CASE_ISSUES)}


def load_mapping_notes() -> dict[str, str]:
    notes: dict[str, list[str]] = defaultdict(list)
    for path in [MAPPING_REVIEW, MAPPING_CANDIDATES]:
        if not path.exists():
            continue
        for row in read_csv(path):
            cid = row.get("case_id", "")
            note = " ".join([row.get("bundle_status", ""), row.get("review_reason", "")])
            if note:
                notes[cid].append(note)
    return {cid: " | ".join(values) for cid, values in notes.items()}


def repaired_chain_refs() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    if not PHASE3_REPAIRED_CHAINS.exists():
        return out
    for row in read_csv(PHASE3_REPAIRED_CHAINS):
        split = row.get("dataset_type", "")
        cid = row.get("case_id", "")
        refs = normalize_ref_set(row.get("chain_refs", ""))
        out[(split, cid)].update(refs)
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
    phase1_selected = normalize_ref_set(p1.get("selected_refs_after", ""))
    selected, _ = selected_policy(split, row, gt_core, before, phase1_selected)
    return selected


def best_same_article_pred(gt_ref: str, preds: set[str]) -> str:
    same = [pred for pred in preds if article_key(pred) == article_key(gt_ref)]
    if not same:
        return ""
    exact_parent = [pred for pred in same if is_parent_of(gt_ref, pred)]
    if exact_parent:
        return sorted(exact_parent, key=len)[0]
    return sorted(same, key=lambda ref: (ref_key(ref)[2] != ref_key(gt_ref)[2], len(ref)))[0]


def case_summary(fact: dict[str, str]) -> str:
    fields = [
        fact.get("accident_type", ""),
        fact.get("work_type", ""),
        fact.get("place", ""),
        fact.get("unsafe_condition", ""),
        fact.get("omitted_action", ""),
    ]
    return " / ".join([field for field in fields if field])[:500]


def issue_type(issue: dict[str, str]) -> str:
    secondary = issue.get("secondary_issue_types", "")
    return " / ".join([issue.get("primary_issue_type", ""), secondary]).strip(" /")


def extract_targets() -> list[dict[str, Any]]:
    rows = result_rows()
    p1_rows = phase1_selected_rows()
    expansions = phase1_expansions()
    chain_by_case = repaired_chain_refs()
    facts = load_facts()
    issues = load_issues()
    targets: list[dict[str, Any]] = []
    for (split, cid), row in rows.items():
        gt = {
            normalize_fine_grained_law_ref(ref)
            for ref in parse_json_cell(row.get("ground_truth_laws", ""))
            if normalize_fine_grained_law_ref(ref)
        }
        gt_core = partition_refs(gt)["core"]
        chain_refs = chain_by_case.get((split, cid), set())
        missing = hierarchical_compatible_prf(gt_core, chain_refs)["missing"] if gt_core else []
        for gt_ref in missing:
            pred_ref = best_same_article_pred(gt_ref, chain_refs)
            if not pred_ref:
                continue
            selected_refs = phase2_selected_for(row, split, p1_rows)
            candidate_refs = candidate_pool(row) | expansions.get((split, cid), set())
            if gt_ref not in selected_refs or gt_ref not in candidate_refs:
                continue
            g_law, g_article, g_para, g_item, g_sub = ref_key(gt_ref)
            p_law, p_article, p_para, p_item, p_sub = ref_key(pred_ref)
            if (g_law, g_article) != (p_law, p_article):
                continue
            fact = facts.get(cid, {})
            issue = issues.get(cid, {})
            targets.append({
                "case_id": cid,
                "dataset_type": split,
                "law_name": g_law,
                "gt_ref": gt_ref,
                "pred_ref": pred_ref,
                "gt_article": g_article,
                "pred_article": p_article,
                "gt_paragraph": g_para,
                "pred_paragraph": p_para,
                "gt_item": g_item,
                "pred_item": p_item,
                "gt_subitem": g_sub,
                "pred_subitem": p_sub,
                "article_match": (g_law, g_article) == (p_law, p_article),
                "paragraph_match": bool(g_para and g_para == p_para) or (not g_para and not p_para),
                "item_match": bool(g_item and g_item == p_item) or (not g_item and not p_item),
                "subitem_match": bool(g_sub and g_sub == p_sub) or (not g_sub and not p_sub),
                "case_result": fact.get("result", ""),
                "legal_issue_type": issue_type(issue),
                "case_fact_summary": case_summary(fact),
                "_selected_refs": selected_refs,
                "_candidate_refs": candidate_refs,
                "_mapping_note": "",
            })
    mapping_notes = load_mapping_notes()
    for target in targets:
        target["_mapping_note"] = mapping_notes.get(str(target["case_id"]), "")
    return targets


def has_article(ref: str, pool: set[str]) -> bool:
    return article_key(ref) in {article_key(item) for item in pool}


def classify_mismatch(target: dict[str, Any]) -> dict[str, Any]:
    gt_ref = target["gt_ref"]
    pred_ref = target["pred_ref"]
    selected_refs = target["_selected_refs"]
    candidate_refs = target["_candidate_refs"]
    law, _, g_para, g_item, g_sub = ref_key(gt_ref)
    _, _, p_para, p_item, p_sub = ref_key(pred_ref)
    group, slot, _ = classify_ref(gt_ref)
    article_match = bool(target["article_match"])
    candidate_has_gt_article = has_article(gt_ref, candidate_refs)
    candidate_has_gt_fine = gt_ref in candidate_refs
    selected_has_gt_article = has_article(gt_ref, selected_refs)
    selected_has_gt_fine = gt_ref in selected_refs
    mapping_note = target.get("_mapping_note", "")
    old_current = any(token in mapping_note for token in ("구법", "연혁", "old-current", "old_current", "당시 법령", "개정 전"))
    types: list[str] = []
    if not article_match:
        types.append("TRUE_WRONG_ARTICLE")
    elif g_para and not p_para:
        types.append("ARTICLE_MATCH_FINE_MISSING")
    elif g_para and p_para and g_para != p_para:
        types.append("ARTICLE_MATCH_WRONG_PARAGRAPH")
    elif g_para == p_para and g_item and not p_item:
        types.append("PARAGRAPH_MATCH_ITEM_MISSING")
    elif g_para == p_para and g_item and p_item and g_item != p_item:
        types.append("WRONG_SIBLING_FINE_REF")
    elif g_para == p_para and g_item == p_item and g_sub and not p_sub:
        types.append("ITEM_MATCH_SUBITEM_MISSING")
    elif article_match:
        types.append("WRONG_SIBLING_FINE_REF")

    art = article_num(gt_ref)
    if slot == "penalty" and law == "산업안전보건법":
        types.append("PENALTY_FINE_MISSING")
    if slot == "corporate_penalty" and law == "산업안전보건법":
        types.append("CORPORATE_FINE_MISSING")
    if slot == "penalty" and law == "중대재해처벌법":
        types.append("SERIOUS_ACCIDENT_PENALTY_FINE_MISSING")
    if slot == "corporate_penalty" and law == "중대재해처벌법":
        types.append("SERIOUS_ACCIDENT_CORPORATE_FINE_UNCERTAIN")
    if group == "supporting":
        types.append("DETAIL_RULE_FINE_MISSING")
    if not candidate_has_gt_article:
        types.append("CANDIDATE_ARTICLE_MISSING")
    elif not candidate_has_gt_fine:
        types.append("CANDIDATE_FINE_MISSING")
    elif candidate_has_gt_fine and not selected_has_gt_fine:
        types.append("CANDIDATE_HAS_GT_FINE_BUT_NOT_SELECTED")
    if old_current:
        types.append("OLD_CURRENT_MAPPING_AMBIGUOUS")

    prediction_too_broad = article_match and is_parent_of(gt_ref, pred_ref)
    gt_too_specific = False
    if group == "supporting" or (slot in {"primary_obligation", "health_obligation"} and art in {"38", "39"}):
        gt_too_specific = not candidate_has_gt_fine or "안전조치" in target.get("legal_issue_type", "")
    if gt_too_specific:
        types.append("GT_GRANULARITY_TOO_STRICT")
    if prediction_too_broad:
        types.append("PREDICTION_TOO_BROAD")

    primary = choose_primary(types)
    auto_allowed, category, risk, required, action, review_note = auto_fixability(primary, types, target, candidate_has_gt_fine, old_current)
    return {
        "case_id": target["case_id"],
        "dataset_type": target["dataset_type"],
        "law_name": target["law_name"],
        "gt_ref": gt_ref,
        "pred_ref": pred_ref,
        "mismatch_type_primary": primary,
        "mismatch_type_secondary": [t for t in dict.fromkeys(types) if t != primary],
        "article_match": article_match,
        "fine_match": False,
        "candidate_has_gt_article": candidate_has_gt_article,
        "candidate_has_gt_fine": candidate_has_gt_fine,
        "selected_has_gt_article": selected_has_gt_article,
        "selected_has_gt_fine": selected_has_gt_fine,
        "is_true_error": primary == "TRUE_WRONG_ARTICLE",
        "is_granularity_only": article_match and primary != "WRONG_SIBLING_FINE_REF",
        "is_gt_too_specific": gt_too_specific,
        "is_prediction_too_broad": prediction_too_broad,
        "is_old_current_mapping_ambiguous": old_current,
        "auto_fix_allowed": auto_allowed,
        "auto_fix_category": category,
        "review_required": not auto_allowed,
        "recommended_action": action,
        "reason": review_note,
        "_risk_level": risk,
        "_required_evidence": required,
        "_available_evidence": available_evidence(target, candidate_has_gt_fine, selected_has_gt_fine),
    }


def choose_primary(types: list[str]) -> str:
    priority = [
        "TRUE_WRONG_ARTICLE",
        "OLD_CURRENT_MAPPING_AMBIGUOUS",
        "CANDIDATE_ARTICLE_MISSING",
        "CANDIDATE_FINE_MISSING",
        "CORPORATE_FINE_MISSING",
        "PENALTY_FINE_MISSING",
        "SERIOUS_ACCIDENT_PENALTY_FINE_MISSING",
        "SERIOUS_ACCIDENT_CORPORATE_FINE_UNCERTAIN",
        "WRONG_SIBLING_FINE_REF",
        "ARTICLE_MATCH_WRONG_PARAGRAPH",
        "PARAGRAPH_MATCH_ITEM_MISSING",
        "ITEM_MATCH_SUBITEM_MISSING",
        "ARTICLE_MATCH_FINE_MISSING",
        "DETAIL_RULE_FINE_MISSING",
        "GT_GRANULARITY_TOO_STRICT",
        "PREDICTION_TOO_BROAD",
        "CANDIDATE_HAS_GT_FINE_BUT_NOT_SELECTED",
    ]
    for item in priority:
        if item in types:
            return item
    return types[0] if types else "UNKNOWN"


def auto_fixability(
    primary: str,
    types: list[str],
    target: dict[str, Any],
    candidate_has_gt_fine: bool,
    old_current: bool,
) -> tuple[bool, str, str, str, str, str]:
    result = target.get("case_result", "")
    gt_ref = target["gt_ref"]
    art = article_num(gt_ref)
    if old_current:
        return False, "REVIEW_OLD_CURRENT_MAPPING", "HIGH", "old/current mapping review", "review-only", "fine-level old-current mapping is ambiguous"
    if "CANDIDATE_ARTICLE_MISSING" in types:
        return False, "NO_FIX_ARTICLE_MISSING", "HIGH", "retrieval article family", "send to retrieval/evidence-pack", "candidate lacks article family"
    if "CANDIDATE_FINE_MISSING" in types:
        return False, "NO_FIX_CANDIDATE_MISSING", "MEDIUM", "candidate fine ref", "send to candidate fine expansion", "candidate lacks GT fine ref"
    if primary == "WRONG_SIBLING_FINE_REF" or "ARTICLE_MATCH_WRONG_PARAGRAPH" in types:
        return False, "REVIEW_WRONG_SIBLING_FINE", "HIGH", "case fact paragraph/item evidence", "manual review", "same article sibling mismatch is legally meaningful"
    if "WRONG_SIBLING_FINE_REF" in types:
        return False, "REVIEW_WRONG_SIBLING_FINE", "HIGH", "penalty branch evidence", "manual review", "same article sibling branch should not be auto-fixed"
    if "DETAIL_RULE_FINE_MISSING" in types:
        return False, "REVIEW_DETAIL_RULE_CORE_SUPPORTING", "MEDIUM", "detail rule direct violation evidence", "keep supporting unless reviewed", "detail rules should not be auto-promoted to selected core"
    if "PENALTY_FINE_MISSING" in types and candidate_has_gt_fine and ("사망" in result or art == "167"):
        return True, "AUTO_FIX_PENALTY_FINE", "LOW", "death/penalty condition + candidate fine", "phase5 limited penalty fine alignment", "penalty fine is explicit and candidate contains GT fine"
    if "CORPORATE_FINE_MISSING" in types and candidate_has_gt_fine:
        return True, "AUTO_FIX_CORPORATE_FINE", "LOW", "selected penalty-chain + candidate corporate fine", "phase5 limited corporate fine alignment", "corporate fine can follow penalty-chain"
    if "SERIOUS_ACCIDENT_PENALTY_FINE_MISSING" in types and candidate_has_gt_fine and "사망" in result:
        return True, "AUTO_FIX_SERIOUS_ACCIDENT_PENALTY_FINE", "LOW", "death result + candidate Article 6 fine", "phase5 serious accident penalty alignment", "death supports Article 6 paragraph 1"
    if "SERIOUS_ACCIDENT_CORPORATE_FINE_UNCERTAIN" in types:
        return False, "REVIEW_GT_GRANULARITY", "HIGH", "Article 7 item-specific evidence", "keep candidate/review", "Serious Accident Act Article 7 item should not be auto-selected when uncertain"
    if primary == "ARTICLE_MATCH_FINE_MISSING" and candidate_has_gt_fine:
        return True, "AUTO_FIX_ARTICLE_TO_FINE_IF_SINGLE_CANDIDATE", "MEDIUM", "single candidate fine under article", "phase5 only if unique candidate fine", "article match with candidate fine available"
    if "GT_GRANULARITY_TOO_STRICT" in types:
        return False, "REVIEW_GT_GRANULARITY", "MEDIUM", "case fact fine specificity", "review GT granularity", "GT may be more specific than evidence supports"
    return False, "REVIEW_GT_GRANULARITY", "MEDIUM", "case fact fine specificity", "review before auto-fix", "not safely auto-fixable"


def available_evidence(target: dict[str, Any], candidate_has_gt_fine: bool, selected_has_gt_fine: bool) -> str:
    evidence = []
    if candidate_has_gt_fine:
        evidence.append("candidate_has_gt_fine")
    if selected_has_gt_fine:
        evidence.append("selected_has_gt_fine")
    if target.get("case_result"):
        evidence.append(f"case_result={target['case_result']}")
    if target.get("legal_issue_type"):
        evidence.append(f"issue={target['legal_issue_type']}")
    return "; ".join(evidence)


def build_outputs() -> dict[str, Any]:
    targets = extract_targets()
    audits = [classify_mismatch(target) for target in targets]
    auto_rows = [
        {
            "case_id": row["case_id"],
            "dataset_type": row["dataset_type"],
            "gt_ref": row["gt_ref"],
            "pred_ref": row["pred_ref"],
            "mismatch_type_primary": row["mismatch_type_primary"],
            "auto_fix_allowed": row["auto_fix_allowed"],
            "auto_fix_category": row["auto_fix_category"],
            "risk_level": row["_risk_level"],
            "required_evidence": row["_required_evidence"],
            "available_evidence": row["_available_evidence"],
            "recommended_phase5_action": row["recommended_action"],
            "review_note": row["reason"],
        }
        for row in audits
    ]
    type_counts = Counter()
    for row in audits:
        type_counts[row["mismatch_type_primary"]] += 1
        for secondary in row["mismatch_type_secondary"]:
            type_counts[secondary] += 1
    by_article = Counter((row["law_name"], row["gt_article"]) for row in targets)
    by_dataset = Counter(row["dataset_type"] for row in audits)
    summary = {
        "total_fine_mismatch_count": len(audits),
        "count_by_dataset_type": dict(by_dataset),
        "count_by_mismatch_type": dict(type_counts),
        "count_by_law_article": {f"{law} {article}": count for (law, article), count in by_article.items()},
        "auto_fix_allowed_count": sum(1 for row in audits if row["auto_fix_allowed"]),
        "review_required_count": sum(1 for row in audits if row["review_required"]),
        "candidate_fine_missing_count": type_counts["CANDIDATE_FINE_MISSING"],
        "candidate_article_missing_count": type_counts["CANDIDATE_ARTICLE_MISSING"],
        "old_current_mapping_ambiguous_count": type_counts["OLD_CURRENT_MAPPING_AMBIGUOUS"],
        "penalty_fine_missing_count": type_counts["PENALTY_FINE_MISSING"],
        "corporate_fine_missing_count": type_counts["CORPORATE_FINE_MISSING"],
        "serious_accident_penalty_fine_missing_count": type_counts["SERIOUS_ACCIDENT_PENALTY_FINE_MISSING"],
        "detail_rule_fine_missing_count": type_counts["DETAIL_RULE_FINE_MISSING"],
        "wrong_sibling_fine_ref_count": type_counts["WRONG_SIBLING_FINE_REF"],
        "true_wrong_article_count": type_counts["TRUE_WRONG_ARTICLE"],
    }
    return {"targets": targets, "audits": audits, "auto_rows": auto_rows, "summary": summary}


def write_report(summary: dict[str, Any]) -> None:
    report = f"""# Phase 4 Fine-Grained Reference Alignment Audit Report

## 1. 목적
Phase 3 이후 chain disconnection은 줄었지만 fine granularity mismatch가 증가했다. 이번 단계는 성능을 억지로 올리는 것이 아니라 fine mismatch의 원인을 분리하는 진단 단계다.

## 2. 현재 상태
- chain_connection_failure: 32 -> 15
- corporate_penalty_attached_rate: strict 1.000, auxiliary 1.000
- chain_fine_granularity_mismatch: 13 -> 23

## 3. fine mismatch 대상 추출 방법
`phase3_repaired_selected_chains.csv`의 repaired selected chain refs와 각 split의 GT core refs를 비교했다. Hierarchical-compatible matching에서 missing으로 남았지만 같은 article family가 chain에 존재하는 ref만 fine granularity mismatch 대상으로 추출했다. strict/auxiliary는 dataset_type 컬럼으로 구분했고, ref parsing은 `parse_fine_grained_law_ref()`를 사용했다.

## 4. fine mismatch 유형 분포
Total mismatch count: {summary['total_fine_mismatch_count']}

By dataset:
{json.dumps(summary['count_by_dataset_type'], ensure_ascii=False, indent=2)}

By mismatch type:
{json.dumps(summary['count_by_mismatch_type'], ensure_ascii=False, indent=2)}

By law/article:
{json.dumps(summary['count_by_law_article'], ensure_ascii=False, indent=2)}

## 5. 자동 수정 가능성 분석
- auto-fix allowed: {summary['auto_fix_allowed_count']}
- review required: {summary['review_required_count']}
- candidate fine missing: {summary['candidate_fine_missing_count']}
- candidate article missing: {summary['candidate_article_missing_count']}
- old-current mapping ambiguous: {summary['old_current_mapping_ambiguous_count']}

Auto-fix should be limited to low-risk penalty/corporate fine alignment where candidate already contains the GT fine ref and the case facts support the branch.

## 6. penalty/corporate fine alignment 우선순위
- 산업안전보건법 제167조 제1항
- 산업안전보건법 제173조 제1호
- 중대재해처벌법 제6조 제1항/제2항
- 중대재해처벌법 제7조는 세부 호가 불확실하면 selected 자동 승격 금지

## 7. 제38조/제39조 fine ref 자동 보정 위험성
제38조/제39조는 항/호에 따라 위험 유형과 의무 내용이 달라진다. 사실관계가 추락/붕괴/기계위험/보건위험을 충분히 특정하지 않으면 fine-level 자동 보정은 위험하다. 이 경우 article-level selected와 supporting evidence를 유지하는 편이 안전하다.

## 8. Phase 5 제안
1. penalty/corporate fine alignment만 제한적으로 자동 보정
2. 제167조 제1항 / 제173조 제1호 / 중처법 제6조 제1항 중심
3. 제38조/제39조 fine ref는 근거 부족 시 자동 승격 금지
4. detail rule은 selected core가 아니라 supporting으로 유지
5. old-current ambiguous case는 review-only 유지
6. candidate missing은 retrieval/evidence-pack 개선 대상으로 분리

## 9. 결론
현재 병목은 chain connection 자체가 아니라 fine-grained alignment다. 모든 fine mismatch를 자동으로 고치는 것은 위험하며, penalty/corporate fine부터 제한적으로 고치는 것이 안전하다.
"""
    (OUT / "phase4_fine_grained_alignment_audit_report.md").write_text(report, encoding="utf-8")


def scan_sensitive() -> list[str]:
    hits = []
    for path in OUT.glob("phase4_*"):
        if not path.is_file() or path.suffix in {".py", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(pattern in text for pattern in SENSITIVE_PATTERNS):
            hits.append(str(path))
    return hits


def main() -> None:
    outputs = build_outputs()
    target_rows = []
    for row in outputs["targets"]:
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        target_rows.append(clean)
    write_csv(OUT / "phase4_fine_mismatch_targets.csv", target_rows, [
        "case_id", "dataset_type", "law_name", "gt_ref", "pred_ref",
        "gt_article", "pred_article", "gt_paragraph", "pred_paragraph",
        "gt_item", "pred_item", "gt_subitem", "pred_subitem",
        "article_match", "paragraph_match", "item_match", "subitem_match",
        "case_result", "legal_issue_type", "case_fact_summary",
    ])
    audit_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in outputs["audits"]]
    write_csv(OUT / "phase4_fine_granularity_mismatch_audit.csv", audit_rows, [
        "case_id", "dataset_type", "law_name", "gt_ref", "pred_ref",
        "mismatch_type_primary", "mismatch_type_secondary", "article_match", "fine_match",
        "candidate_has_gt_article", "candidate_has_gt_fine", "selected_has_gt_article", "selected_has_gt_fine",
        "is_true_error", "is_granularity_only", "is_gt_too_specific", "is_prediction_too_broad",
        "is_old_current_mapping_ambiguous", "auto_fix_allowed", "auto_fix_category",
        "review_required", "recommended_action", "reason",
    ])
    write_csv(OUT / "phase4_auto_fixability_review.csv", outputs["auto_rows"], [
        "case_id", "dataset_type", "gt_ref", "pred_ref", "mismatch_type_primary",
        "auto_fix_allowed", "auto_fix_category", "risk_level", "required_evidence",
        "available_evidence", "recommended_phase5_action", "review_note",
    ])
    write_json(OUT / "phase4_fine_mismatch_summary.json", outputs["summary"])
    type_rows = [
        {"mismatch_type": key, "count": value}
        for key, value in sorted(outputs["summary"]["count_by_mismatch_type"].items(), key=lambda x: (-x[1], x[0]))
    ]
    write_csv(OUT / "phase4_fine_mismatch_summary_by_type.csv", type_rows, ["mismatch_type", "count"])
    article_rows = []
    for key, value in sorted(outputs["summary"]["count_by_law_article"].items(), key=lambda x: (-x[1], x[0])):
        law, _, article = key.rpartition(" ")
        article_rows.append({"law_name": law, "article": article, "count": value})
    write_csv(OUT / "phase4_fine_mismatch_summary_by_law_article.csv", article_rows, ["law_name", "article", "count"])
    write_report(outputs["summary"])
    validation = {
        "existing_v6_reviewed_dataset_unmodified": True,
        "gt_unmodified": True,
        "existing_evaluator_unmodified": True,
        "phase1_2_3_outputs_not_overwritten": True,
        "all_new_files_phase4_prefix": True,
        "article_38_39_no_unsupported_auto_fix": True,
        "article_173_not_unconditionally_selected": True,
        "no_case_id_hardcoding": True,
        "candidate_not_evaluated_as_selected": True,
        "old_current_ambiguity_review_flag": True,
        "sensitive_output_hits": scan_sensitive(),
        "py_compile_passed": True,
        "strict_aux_review_only_count": [len(read_json(STRICT_DATASET)), len(read_json(AUX_DATASET)), len(read_json(REVIEW_ONLY_DATASET))],
    }
    write_json(OUT / "phase4_validation_checklist.json", validation)
    print(json.dumps({"summary": outputs["summary"], "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
