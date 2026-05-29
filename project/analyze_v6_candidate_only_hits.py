from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from evaluate_v6_case_scenario import (
    CORE_SELECTED_SLOTS,
    _article_key,
    _case_article_compatible,
    _case_conditions,
    _slot_for_ref,
    normalize_fine_grained_law_ref,
    write_csv,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS = ROOT / "generated_v6_case_scenario_eval" / "evaluation_reviewed" / "v6_reviewed_strict_results.csv"
DEFAULT_DATASET = ROOT / "generated_v6_case_scenario_eval" / "review_upgrade" / "v6_reviewed_case_scenario_eval_ready.json"
DEFAULT_OUTPUT = ROOT / "generated_v6_case_scenario_eval" / "evaluation_reviewed" / "candidate_only_hit_analysis.csv"


def _load_json_cell(row: dict[str, str], key: str, default: Any) -> Any:
    value = row.get(key)
    if not value:
        return default
    return json.loads(value)


def _refs_from_items(items: list[dict]) -> set[str]:
    return {
        normalize_fine_grained_law_ref(item.get("ref", ""))
        for item in items
        if normalize_fine_grained_law_ref(item.get("ref", ""))
    }


def _hit_items(gt_refs: set[str], items: list[dict]) -> list[dict]:
    gt_articles = {_article_key(ref) for ref in gt_refs}
    hits = []
    for item in items:
        ref = normalize_fine_grained_law_ref(item.get("ref", ""))
        if not ref:
            continue
        if ref in gt_refs or _article_key(ref) in gt_articles:
            hits.append({**item, "ref": ref})
    return hits


def _promote_safe(item: dict, expected_refs: set[str], case_item: dict, prompt: str) -> bool:
    ref = normalize_fine_grained_law_ref(item.get("ref", ""))
    if not ref:
        return False
    text = f"{item.get('source', '')} {item.get('reason', '')} {item.get('tier', '')}".lower()
    if any(token in text for token in ("weak", "debug", "law_name_only")):
        return False
    if _slot_for_ref(ref) not in CORE_SELECTED_SLOTS:
        return False
    if not _case_article_compatible(ref, case_item, prompt):
        return False
    expected_articles = {_article_key(gt) for gt in expected_refs}
    return ref in expected_refs or _article_key(ref) in expected_articles


def _recommendation(refs: list[str]) -> str:
    articles = {_article_key(ref) for ref in refs}
    labels = {article for _, article in articles}
    if "167" in labels or "173" in labels:
        return "open death penalty/corporate slot to rank exact 167/173 candidate against selected refs"
    if "38" in labels:
        return "prefer safety-obligation article 38 child refs for fall/collapse/caught cases"
    if "39" in labels:
        return "prefer health-obligation article 39 for suffocation/hazardous substance cases"
    if labels & {"63", "64"}:
        return "prefer contractor-obligation articles 63/64 when contractor_relation is true"
    if labels & {"4", "5", "6", "7"}:
        return "prefer serious-accident chain articles 4/5 -> 6 -> 7 when serious_accident_issue is true"
    return "review candidate-to-selected ranking for same article/slot hit"


def build_analysis(results_path: Path, dataset_path: Path) -> list[dict[str, Any]]:
    dataset = {str(item.get("id", "")): item for item in json.loads(dataset_path.read_text(encoding="utf-8"))}
    with results_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    out: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row.get("id", ""))
        case_item = dataset.get(case_id, {})
        prompt = case_item.get("case_scenario_prompt") or case_item.get("rewritten_question") or case_item.get("question") or ""
        gt_refs = {
            normalize_fine_grained_law_ref(ref)
            for ref in _load_json_cell(row, "ground_truth_laws", [])
            if normalize_fine_grained_law_ref(ref)
        }
        selected = _load_json_cell(row, "selected_laws", [])
        supporting = _load_json_cell(row, "supporting_laws", [])
        candidate = _load_json_cell(row, "candidate_laws", [])
        selected_refs = _refs_from_items(selected)
        missing_gt = sorted(gt_refs - selected_refs)
        candidate_hits = _hit_items(set(missing_gt), candidate)
        supporting_hits = _hit_items(set(missing_gt), supporting)
        if row.get("failure_category") != "candidate_only_match" and not candidate_hits:
            continue

        hit_refs = sorted({item["ref"] for item in candidate_hits})
        safe_refs = [item["ref"] for item in candidate_hits if _promote_safe(item, gt_refs, case_item, prompt)]
        out.append(
            {
                "case_id": case_id,
                "case_name": row.get("case_name", ""),
                "missing_gt_refs": json.dumps(missing_gt, ensure_ascii=False),
                "candidate_hit_refs": json.dumps(hit_refs, ensure_ascii=False),
                "supporting_hit_refs": json.dumps(sorted({item["ref"] for item in supporting_hits}), ensure_ascii=False),
                "selected_refs": json.dumps(sorted(selected_refs), ensure_ascii=False),
                "candidate_sources": json.dumps([item.get("source", "") for item in candidate_hits], ensure_ascii=False),
                "candidate_reasons": json.dumps([item.get("reason", "") for item in candidate_hits], ensure_ascii=False),
                "slot": json.dumps(sorted({_slot_for_ref(ref) for ref in hit_refs}), ensure_ascii=False),
                "article": json.dumps(sorted(f"{law} {article}" for law, article in {_article_key(ref) for ref in hit_refs}), ensure_ascii=False),
                "case_conditions": json.dumps(_case_conditions(case_item, prompt), ensure_ascii=False),
                "recommended_selector_fix": _recommendation(hit_refs),
                "promote_safe": bool(safe_refs),
                "review_reason": json.dumps(
                    {
                        "safe_refs": sorted(safe_refs),
                        "failure_category": row.get("failure_category", ""),
                        "candidate_recall": row.get("candidate_recall", ""),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    rows = build_analysis(Path(args.results), Path(args.dataset))
    write_csv(
        Path(args.output),
        rows,
        [
            "case_id",
            "case_name",
            "missing_gt_refs",
            "candidate_hit_refs",
            "supporting_hit_refs",
            "selected_refs",
            "candidate_sources",
            "candidate_reasons",
            "slot",
            "article",
            "case_conditions",
            "recommended_selector_fix",
            "promote_safe",
            "review_reason",
        ],
    )
    print(json.dumps({"output": args.output, "row_count": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
