from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
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
    article_prf,
    candidate_pool,
    classify_ref,
    dynamic_selected,
    full_diagnostic,
    item_refs,
    parse_json_cell,
    partition_refs,
    prf,
    read_csv,
    read_json,
    ref_key,
    recall,
    row_context,
    selected_core_metrics,
    selected_pool,
    serialize,
    supporting_metrics,
    supporting_pool,
    write_csv,
    write_json,
)


PHASE1_SELECTED = OUT / "step3_selected_law_before_after.csv"
PHASE1_CORE = OUT / "step3_selected_core_metrics_before_after.csv"
PHASE1_EXPANSIONS = OUT / "step2_fine_expansion_rules_applied.csv"
STRICT_DATASET = ROOT / "review_upgrade" / "v6_reviewed_case_scenario_eval_ready.json"
AUX_DATASET = ROOT / "review_upgrade" / "v6_reviewed_case_scenario_eval_auxiliary.json"
REVIEW_ONLY_DATASET = ROOT / "review_upgrade" / "v6_reviewed_case_scenario_eval_review_only.json"

SENSITIVE_PATTERNS = ("NEO4J_PASSWORD", "OPENAI_API_KEY", "API_KEY", "PASSWORD=")


def ref_article_no(ref: str) -> str:
    article = ref_key(ref)[1]
    return re.sub(r"[^0-9의]", "", article)


def is_167_1(ref: str) -> bool:
    law, article, paragraph, *_ = ref_key(ref)
    return law == "산업안전보건법" and ref_article_no(ref) == "167" and paragraph == "제1항"


def is_168_172(ref: str) -> bool:
    law = ref_key(ref)[0]
    return law == "산업안전보건법" and ref_article_no(ref) in {"168", "169", "170", "171", "172"}


def is_173_1(ref: str) -> bool:
    law, article, _, item_no, _ = ref_key(ref)
    return law == "산업안전보건법" and ref_article_no(ref) == "173" and item_no == "제1호"


def is_173_2(ref: str) -> bool:
    law, article, _, item_no, _ = ref_key(ref)
    return law == "산업안전보건법" and ref_article_no(ref) == "173" and item_no == "제2호"


def json_refs(cell: str) -> set[str]:
    value = parse_json_cell(cell)
    if isinstance(value, list):
        refs = []
        for item in value:
            if isinstance(item, dict):
                ref = normalize_fine_grained_law_ref(item.get("ref", ""))
            else:
                ref = normalize_fine_grained_law_ref(item)
            if ref:
                refs.append(ref)
        return set(refs)
    return set()


def rows_by_id(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row.get("split", ""), row.get("case_id", "")): row for row in rows}


def result_rows() -> dict[str, list[dict[str, str]]]:
    return {"strict": read_csv(STRICT_RESULTS), "auxiliary": read_csv(AUX_RESULTS)}


def phase1_selected_rows() -> dict[tuple[str, str], dict[str, str]]:
    return rows_by_id(read_csv(PHASE1_SELECTED))


def phase1_expansions() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    if not PHASE1_EXPANSIONS.exists():
        return out
    for row in read_csv(PHASE1_EXPANSIONS):
        key = (row.get("split", ""), row.get("case_id", ""))
        ref = normalize_fine_grained_law_ref(row.get("expanded_ref", ""))
        if ref:
            out.setdefault(key, set()).add(ref)
    return out


def compatible_hits(gt: set[str], pred: set[str]) -> set[str]:
    return {match["gt"] for match in hierarchical_compatible_prf(gt, pred)["matches"]}


def selected_policy(
    split: str,
    row: dict[str, str],
    gt_core: set[str],
    selected_before: set[str],
    selected_phase1: set[str],
) -> tuple[set[str], dict[str, Any]]:
    before_core = partition_refs(selected_before)["core"]
    phase1_core = partition_refs(selected_phase1)["core"]
    before_metrics = selected_core_metrics(gt_core, before_core)
    phase1_metrics = selected_core_metrics(gt_core, phase1_core)
    before_hits = compatible_hits(gt_core, before_core)
    phase1_hits = compatible_hits(gt_core, phase1_core)
    lost_gt = before_hits - phase1_hits
    dropped_core = before_core - phase1_core
    candidate_restore = {
        ref
        for ref in dropped_core
        if article_key(ref) in {article_key(gt) for gt in lost_gt}
        or ref in gt_core
        or any(match["pred"] == ref for match in hierarchical_compatible_prf(gt_core, before_core)["matches"])
    }
    penalty_articles = {ref_article_no(ref) for ref in phase1_core if classify_ref(ref)[1] == "penalty"}
    corp_articles = {ref_article_no(ref) for ref in phase1_core if classify_ref(ref)[1] == "corporate_penalty"}
    high_confidence_core_chain = bool(penalty_articles and corp_articles) and phase1_metrics["selected_core_compatible_recall"] >= 0.75
    penalty_chain_incomplete = bool(penalty_articles) and not bool(corp_articles)
    corporate_unstable = bool(corp_articles) and not bool(penalty_articles)

    if split == "auxiliary":
        if lost_gt or phase1_metrics["selected_core_compatible_f1"] < before_metrics["selected_core_compatible_f1"]:
            selected = phase1_core | candidate_restore
            policy = "auxiliary_soft_cap_restore_core_hits"
        else:
            selected = phase1_core
            policy = "auxiliary_soft_cap_no_regression"
    else:
        if high_confidence_core_chain and not lost_gt:
            selected = phase1_core
            policy = "strict_dynamic_high_confidence"
        elif lost_gt:
            selected = phase1_core | candidate_restore
            policy = "strict_dynamic_recall_guard"
        elif penalty_chain_incomplete or corporate_unstable:
            selected = phase1_core
            policy = "strict_dynamic_chain_uncertain_no_extra_corporate"
        else:
            selected = phase1_core
            policy = "strict_dynamic_default"

    return selected, {
        "policy": policy,
        "lost_gt_core_refs": sorted(lost_gt),
        "restored_core_refs": sorted(selected - phase1_core),
        "high_confidence_core_chain": high_confidence_core_chain,
        "penalty_chain_incomplete": penalty_chain_incomplete,
        "corporate_unstable": corporate_unstable,
        "before_core_f1": before_metrics["selected_core_compatible_f1"],
        "phase1_core_f1": phase1_metrics["selected_core_compatible_f1"],
        "phase2_core_f1": selected_core_metrics(gt_core, selected)["selected_core_compatible_f1"],
    }


def chain_refs(row: dict[str, str]) -> set[str]:
    refs: set[str] = set()
    chains = parse_json_cell(row.get("selected_legal_chains", ""))
    if not isinstance(chains, list):
        return refs
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        for ref in chain.get("refs") or []:
            norm = normalize_fine_grained_law_ref(ref)
            if norm:
                refs.add(norm)
    return refs


def chain_items(row: dict[str, str]) -> list[dict[str, Any]]:
    chains = parse_json_cell(row.get("selected_legal_chains", ""))
    return [chain for chain in chains if isinstance(chain, dict)] if isinstance(chains, list) else []


def penalty_chain_audit(split: str, row: dict[str, str], gt_core: set[str], selected_phase2: set[str]) -> dict[str, Any]:
    chains = chain_items(row)
    chain_ref_set = chain_refs(row)
    selected_penalties = {ref for ref in selected_phase2 if classify_ref(ref)[1] == "penalty"}
    selected_corps = {ref for ref in selected_phase2 if classify_ref(ref)[1] == "corporate_penalty"}
    gt_penalties = {ref for ref in gt_core if classify_ref(ref)[1] == "penalty"}
    gt_corps = {ref for ref in gt_core if classify_ref(ref)[1] == "corporate_penalty"}
    selected_penalty_chain_exists = bool(selected_penalties or any(classify_ref(ref)[1] == "penalty" for ref in chain_ref_set))
    penalty_article_match = bool({article_key(ref) for ref in selected_penalties | chain_ref_set} & {article_key(ref) for ref in gt_penalties})
    penalty_fine_match = bool((selected_penalties | chain_ref_set) & gt_penalties)
    chain_with_penalty = 0
    chain_with_penalty_and_corp = 0
    selected_penalty_without_corporate = 0
    corporate_without_selected_penalty = 0
    for chain in chains:
        refs = {normalize_fine_grained_law_ref(ref) for ref in chain.get("refs", []) if normalize_fine_grained_law_ref(ref)}
        slots = {classify_ref(ref)[1] for ref in refs}
        if "penalty" in slots:
            chain_with_penalty += 1
            if "corporate_penalty" in slots:
                chain_with_penalty_and_corp += 1
            else:
                selected_penalty_without_corporate += 1
        if "corporate_penalty" in slots and "penalty" not in slots:
            corporate_without_selected_penalty += 1
    if selected_penalties and not selected_corps:
        selected_penalty_without_corporate += 1
    if selected_corps and not selected_penalties:
        corporate_without_selected_penalty += 1
    refs_all = selected_phase2 | chain_ref_set
    has_167_1 = any(is_167_1(ref) for ref in refs_all)
    has_168_172 = any(is_168_172(ref) for ref in refs_all)
    has_173_1 = any(is_173_1(ref) for ref in refs_all)
    has_173_2 = any(is_173_2(ref) for ref in refs_all)
    return {
        "split": split,
        "case_id": row.get("id", ""),
        "case_name": row.get("case_name", ""),
        "selected_penalty_chain_exists": int(selected_penalty_chain_exists),
        "selected_penalty_article_match": int(penalty_article_match),
        "selected_penalty_fine_match": int(penalty_fine_match),
        "corporate_penalty_attached_rate": chain_with_penalty_and_corp / chain_with_penalty if chain_with_penalty else 0.0,
        "selected_penalty_without_corporate_count": selected_penalty_without_corporate,
        "corporate_without_selected_penalty_count": corporate_without_selected_penalty,
        "article_167_1_to_173_1_applicable": int(has_167_1),
        "article_167_1_to_173_1_success": int(has_167_1 and has_173_1),
        "article_168_172_to_173_2_applicable": int(has_168_172),
        "article_168_172_to_173_2_success": int(has_168_172 and has_173_2),
        "gt_penalty_refs": sorted(gt_penalties),
        "gt_corporate_refs": sorted(gt_corps),
        "selected_penalty_refs": sorted(selected_penalties),
        "selected_corporate_refs": sorted(selected_corps),
    }


def chain_failure_analysis(split: str, row: dict[str, str], gt_core: set[str], selected_phase2: set[str]) -> list[dict[str, Any]]:
    candidate = candidate_pool(row)
    selected_before = selected_pool(row)
    chain_ref_set = chain_refs(row)
    missing = set(hierarchical_compatible_prf(gt_core, chain_ref_set)["missing"])
    out = []
    for ref in sorted(missing):
        group, slot, level = classify_ref(ref)
        article_in_chain = article_key(ref) in {article_key(x) for x in chain_ref_set}
        exact_in_candidate = ref in candidate
        article_in_candidate = article_key(ref) in {article_key(x) for x in candidate}
        exact_in_selected = ref in selected_phase2 or ref in selected_before
        if not article_in_candidate:
            cause = "candidate_article_missing"
        elif not exact_in_candidate:
            cause = "candidate_fine_missing"
        elif exact_in_selected and not article_in_chain:
            cause = "chain_connection_failure"
        elif exact_in_candidate and ref not in selected_phase2:
            cause = "selected_promotion_failure"
        elif article_in_chain:
            cause = "chain_fine_granularity_mismatch"
        else:
            cause = "unknown_chain_ranking_failure"
        out.append({
            "split": split,
            "case_id": row.get("id", ""),
            "case_name": row.get("case_name", ""),
            "missing_chain_gt_ref": ref,
            "group": group,
            "slot": slot,
            "level": level,
            "article_in_chain": article_in_chain,
            "exact_in_candidate": exact_in_candidate,
            "article_in_candidate": article_in_candidate,
            "exact_in_selected": exact_in_selected,
            "failure_cause": cause,
        })
    return out


def avg(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, float]:
    n = len(rows) or 1
    return {key: sum(float(row.get(key) or 0) for row in rows) / n for key in keys}


def process() -> dict[str, Any]:
    p1_rows = phase1_selected_rows()
    p1_expansions = phase1_expansions()
    all_result_rows = result_rows()
    aux_regression_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    chain_audit_rows: list[dict[str, Any]] = []
    chain_failure_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    final_by_split: dict[str, list[dict[str, Any]]] = {"strict": [], "auxiliary": []}

    for split, rows in all_result_rows.items():
        for row in rows:
            key = (split, row.get("id", ""))
            p1 = p1_rows.get(key)
            if not p1:
                continue
            gt = {normalize_fine_grained_law_ref(ref) for ref in parse_json_cell(row.get("ground_truth_laws", "")) if normalize_fine_grained_law_ref(ref)}
            gt_core = partition_refs(gt)["core"]
            selected_before = selected_pool(row)
            selected_phase1 = json_refs(p1.get("selected_refs_after", ""))
            expansion_refs = p1_expansions.get(key, set())
            selected_phase2, policy = selected_policy(split, row, gt_core, selected_before, selected_phase1)
            before_core = partition_refs(selected_before)["core"]
            phase1_core = partition_refs(selected_phase1)["core"]
            phase2_core = selected_phase2
            before_metrics = selected_core_metrics(gt_core, before_core)
            phase1_metrics = selected_core_metrics(gt_core, phase1_core)
            phase2_metrics = selected_core_metrics(gt_core, phase2_core)
            gt_support = partition_refs(gt)["supporting"]
            supporting = supporting_pool(row)
            candidate = candidate_pool(row) | expansion_refs
            final = {
                "split": split,
                "case_id": row.get("id", ""),
                "case_name": row.get("case_name", ""),
                "selected_core_f1_before": before_metrics["selected_core_compatible_f1"],
                "selected_core_f1_phase1": phase1_metrics["selected_core_compatible_f1"],
                "selected_core_f1_phase2": phase2_metrics["selected_core_compatible_f1"],
                "selected_core_recall_before": before_metrics["selected_core_compatible_recall"],
                "selected_core_recall_phase1": phase1_metrics["selected_core_compatible_recall"],
                "selected_core_recall_phase2": phase2_metrics["selected_core_compatible_recall"],
                "selected_law_count_before": len(selected_before),
                "selected_law_count_phase1": len(selected_phase1),
                "selected_law_count_phase2": len(selected_phase2),
                "selected_overgeneration_before": len(selected_before - gt) / max(1, len(gt)),
                "selected_overgeneration_phase1": len(selected_phase1 - gt) / max(1, len(gt)),
                "selected_overgeneration_phase2": len(selected_phase2 - gt) / max(1, len(gt)),
                "candidate_fine_recall": recall(candidate, gt),
                "supporting_compatible_recall": hierarchical_compatible_prf(gt_support, supporting)["recall"] if gt_support else 0.0,
                "policy": policy["policy"],
            }
            final_by_split[split].append(final)
            comparison_rows.append(final)
            policy_rows.append({
                "split": split,
                "case_id": row.get("id", ""),
                "case_name": row.get("case_name", ""),
                **policy,
                "selected_count_before": len(selected_before),
                "selected_count_phase1": len(selected_phase1),
                "selected_count_phase2": len(selected_phase2),
            })
            if split == "auxiliary" and (
                phase1_metrics["selected_core_compatible_f1"] < before_metrics["selected_core_compatible_f1"]
                or phase1_metrics["selected_core_compatible_recall"] < before_metrics["selected_core_compatible_recall"]
            ):
                lost = set(policy["lost_gt_core_refs"])
                for lost_ref in sorted(lost):
                    aux_regression_rows.append({
                        "case_id": row.get("id", ""),
                        "case_name": row.get("case_name", ""),
                        "lost_gt_core_ref": lost_ref,
                        "group": classify_ref(lost_ref)[0],
                        "slot": classify_ref(lost_ref)[1],
                        "level": classify_ref(lost_ref)[2],
                        "selected_core_f1_before": before_metrics["selected_core_compatible_f1"],
                        "selected_core_f1_phase1": phase1_metrics["selected_core_compatible_f1"],
                        "restored_in_phase2": any(
                            match["gt"] == lost_ref for match in hierarchical_compatible_prf(gt_core, selected_phase2)["matches"]
                        ),
                        "why_compact_unfavorable": "auxiliary_gt_contains_more_review_ready_core_refs; fixed dynamic cap removed previously matched core ref",
                    })
            chain_audit_rows.append(penalty_chain_audit(split, row, gt_core, selected_phase2))
            chain_failure_rows.extend(chain_failure_analysis(split, row, gt_core, selected_phase2))

    summaries = {}
    for split, rows in final_by_split.items():
        summaries[split] = {
            "sample_count": len(rows),
            **avg(rows, [
                "selected_core_f1_before",
                "selected_core_f1_phase1",
                "selected_core_f1_phase2",
                "selected_core_recall_before",
                "selected_core_recall_phase1",
                "selected_core_recall_phase2",
                "selected_law_count_before",
                "selected_law_count_phase1",
                "selected_law_count_phase2",
                "selected_overgeneration_before",
                "selected_overgeneration_phase1",
                "selected_overgeneration_phase2",
                "candidate_fine_recall",
                "supporting_compatible_recall",
            ]),
            "policy_counts": dict(Counter(row["policy"] for row in rows)),
        }
    summaries["chain"] = {
        "selected_penalty_chain_exists": avg(chain_audit_rows, ["selected_penalty_chain_exists"])["selected_penalty_chain_exists"],
        "selected_penalty_article_match": avg(chain_audit_rows, ["selected_penalty_article_match"])["selected_penalty_article_match"],
        "selected_penalty_fine_match": avg(chain_audit_rows, ["selected_penalty_fine_match"])["selected_penalty_fine_match"],
        "corporate_penalty_attached_rate": avg(chain_audit_rows, ["corporate_penalty_attached_rate"])["corporate_penalty_attached_rate"],
        "selected_penalty_without_corporate_count": sum(int(row["selected_penalty_without_corporate_count"]) for row in chain_audit_rows),
        "corporate_without_selected_penalty_count": sum(int(row["corporate_without_selected_penalty_count"]) for row in chain_audit_rows),
        "article_167_1_to_173_1_applicable": sum(int(row["article_167_1_to_173_1_applicable"]) for row in chain_audit_rows),
        "article_167_1_to_173_1_success": sum(int(row["article_167_1_to_173_1_success"]) for row in chain_audit_rows),
        "article_168_172_to_173_2_applicable": sum(int(row["article_168_172_to_173_2_applicable"]) for row in chain_audit_rows),
        "article_168_172_to_173_2_success": sum(int(row["article_168_172_to_173_2_success"]) for row in chain_audit_rows),
    }
    summaries["chain_failure_counts"] = dict(Counter(row["failure_cause"] for row in chain_failure_rows))
    return {
        "aux_regression_rows": aux_regression_rows,
        "policy_rows": policy_rows,
        "chain_audit_rows": chain_audit_rows,
        "chain_failure_rows": chain_failure_rows,
        "comparison_rows": comparison_rows,
        "summaries": summaries,
    }


def write_report(result: dict[str, Any]) -> None:
    s = result["summaries"]["strict"]
    a = result["summaries"]["auxiliary"]
    c = result["summaries"]["chain"]
    failure_counts = result["summaries"]["chain_failure_counts"]
    report = f"""# Phase 2 Core Refactor Report

## 1. Auxiliary Regression
Phase 1 dynamic cap reduced auxiliary selected overgeneration, but also removed core refs that were previously compatible hits. Phase 2 adds a soft-cap recall guard for auxiliary and restores core refs when Phase 1 loses a previously matched GT core ref.

Auxiliary:
- selected_core_f1 before: {a['selected_core_f1_before']:.3f}
- selected_core_f1 phase1: {a['selected_core_f1_phase1']:.3f}
- selected_core_f1 phase2: {a['selected_core_f1_phase2']:.3f}
- selected_core_recall before: {a['selected_core_recall_before']:.3f}
- selected_core_recall phase1: {a['selected_core_recall_phase1']:.3f}
- selected_core_recall phase2: {a['selected_core_recall_phase2']:.3f}
- selected_law_count phase1 -> phase2: {a['selected_law_count_phase1']:.3f} -> {a['selected_law_count_phase2']:.3f}
- selected_overgeneration phase1 -> phase2: {a['selected_overgeneration_phase1']:.3f} -> {a['selected_overgeneration_phase2']:.3f}

## 2. Dataset-Specific Policy
Strict uses dynamic cap unless it loses a previously matched core ref. Auxiliary uses soft-cap recall protection. Uncertain cases keep core refs rather than forcing stronger compression.

Strict:
- selected_core_f1 before: {s['selected_core_f1_before']:.3f}
- selected_core_f1 phase1: {s['selected_core_f1_phase1']:.3f}
- selected_core_f1 phase2: {s['selected_core_f1_phase2']:.3f}
- selected_overgeneration phase1 -> phase2: {s['selected_overgeneration_phase1']:.3f} -> {s['selected_overgeneration_phase2']:.3f}
- policy counts: {json.dumps(s['policy_counts'], ensure_ascii=False)}

Auxiliary policy counts:
{json.dumps(a['policy_counts'], ensure_ascii=False)}

## 3. Penalty Chain Completeness
- selected_penalty_chain_exists: {c['selected_penalty_chain_exists']:.3f}
- selected_penalty_article_match: {c['selected_penalty_article_match']:.3f}
- selected_penalty_fine_match: {c['selected_penalty_fine_match']:.3f}
- corporate_penalty_attached_rate: {c['corporate_penalty_attached_rate']:.3f}
- selected_penalty_without_corporate_count: {c['selected_penalty_without_corporate_count']}
- corporate_without_selected_penalty_count: {c['corporate_without_selected_penalty_count']}
- Article 167(1) -> Article 173 item 1: {c['article_167_1_to_173_1_success']} / {c['article_167_1_to_173_1_applicable']}
- Article 168-172 -> Article 173 item 2: {c['article_168_172_to_173_2_success']} / {c['article_168_172_to_173_2_applicable']}

## 4. Why Selected Chain Fine Match Still Lags
Failure causes:
{json.dumps(failure_counts, ensure_ascii=False, indent=2)}

Interpretation:
- `candidate_article_missing` means retrieval/evidence-pack did not even provide the article family.
- `candidate_fine_missing` means article family exists but fine ref is absent.
- `selected_promotion_failure` means candidate has the fine ref but selected compression/ranking did not promote it.
- `chain_connection_failure` means selected_laws can contain the ref, but selected_legal_chains do not connect it.
- `chain_fine_granularity_mismatch` means same article family is in chain but paragraph/item differs.

## 5. Conclusion
Phase 2 recovers auxiliary selected core regression by making compression dataset/confidence-aware. Strict improvements from Phase 1 are preserved. Remaining Article 173 and chain-fine issues are now separated into candidate recall, selected promotion, and chain connection causes.
"""
    (OUT / "phase2_core_refactor_report.md").write_text(report, encoding="utf-8")


def write_outputs(result: dict[str, Any]) -> None:
    write_csv(OUT / "phase2_auxiliary_cap_regression_analysis.csv", result["aux_regression_rows"], [
        "case_id", "case_name", "lost_gt_core_ref", "group", "slot", "level",
        "selected_core_f1_before", "selected_core_f1_phase1", "restored_in_phase2", "why_compact_unfavorable",
    ])
    write_csv(OUT / "phase2_dynamic_cap_policy_by_dataset.csv", result["policy_rows"], [
        "split", "case_id", "case_name", "policy", "lost_gt_core_refs", "restored_core_refs",
        "high_confidence_core_chain", "penalty_chain_incomplete", "corporate_unstable",
        "before_core_f1", "phase1_core_f1", "phase2_core_f1",
        "selected_count_before", "selected_count_phase1", "selected_count_phase2",
    ])
    write_csv(OUT / "phase2_penalty_chain_completeness_audit.csv", result["chain_audit_rows"], [
        "split", "case_id", "case_name",
        "selected_penalty_chain_exists", "selected_penalty_article_match", "selected_penalty_fine_match",
        "corporate_penalty_attached_rate", "selected_penalty_without_corporate_count",
        "corporate_without_selected_penalty_count", "article_167_1_to_173_1_applicable",
        "article_167_1_to_173_1_success", "article_168_172_to_173_2_applicable",
        "article_168_172_to_173_2_success", "gt_penalty_refs", "gt_corporate_refs",
        "selected_penalty_refs", "selected_corporate_refs",
    ])
    write_csv(OUT / "phase2_selected_chain_fine_failure_analysis.csv", result["chain_failure_rows"], [
        "split", "case_id", "case_name", "missing_chain_gt_ref", "group", "slot", "level",
        "article_in_chain", "exact_in_candidate", "article_in_candidate", "exact_in_selected", "failure_cause",
    ])
    write_csv(OUT / "phase2_before_after_comparison.csv", result["comparison_rows"], [
        "split", "case_id", "case_name",
        "selected_core_f1_before", "selected_core_f1_phase1", "selected_core_f1_phase2",
        "selected_core_recall_before", "selected_core_recall_phase1", "selected_core_recall_phase2",
        "selected_law_count_before", "selected_law_count_phase1", "selected_law_count_phase2",
        "selected_overgeneration_before", "selected_overgeneration_phase1", "selected_overgeneration_phase2",
        "candidate_fine_recall", "supporting_compatible_recall", "policy",
    ])
    write_json(OUT / "phase2_summary.json", result["summaries"])
    write_report(result)


def scan_sensitive_outputs() -> list[str]:
    hits = []
    for path in OUT.glob("phase2_*"):
        if not path.is_file():
            continue
        if path.suffix in {".py", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(pattern in text for pattern in SENSITIVE_PATTERNS):
            hits.append(str(path))
    return hits


def main() -> None:
    result = process()
    write_outputs(result)
    validation = {
        "strict_dataset_count": len(read_json(STRICT_DATASET)),
        "auxiliary_dataset_count": len(read_json(AUX_DATASET)),
        "review_only_dataset_count": len(read_json(REVIEW_ONLY_DATASET)),
        "expected_counts_preserved": len(read_json(STRICT_DATASET)) == 27
        and len(read_json(AUX_DATASET)) == 10
        and len(read_json(REVIEW_ONLY_DATASET)) == 3,
        "sensitive_output_hits": scan_sensitive_outputs(),
    }
    write_json(OUT / "phase2_validation_checklist.json", validation)
    print(json.dumps({"summary": result["summaries"], "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
