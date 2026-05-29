from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluate_v6_case_scenario import _article_key, _case_conditions, _slot_for_ref, normalize_fine_grained_law_ref, write_csv, write_json


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS = ROOT / "generated_v6_case_scenario_eval" / "evaluation_reviewed" / "selector_v3_ablation" / "cap7" / "case_scenario_api_results.csv"
DEFAULT_DATASET = ROOT / "generated_v6_case_scenario_eval" / "review_upgrade" / "v6_reviewed_case_scenario_eval_ready.json"
DEFAULT_OUTPUT = ROOT / "generated_v6_case_scenario_eval" / "evaluation_reviewed" / "candidate_pool_missing_analysis.csv"


def _json_cell(row: dict[str, str], key: str, default: Any) -> Any:
    value = row.get(key)
    if not value:
        return default
    return json.loads(value)


def _refs(items: list[dict]) -> set[str]:
    return {
        normalize_fine_grained_law_ref(item.get("ref", ""))
        for item in items
        if normalize_fine_grained_law_ref(item.get("ref", ""))
    }


def _article_labels(refs: list[str]) -> list[str]:
    labels = []
    for ref in refs:
        law, article = _article_key(ref)
        if law and article:
            labels.append(f"{law} {article}")
    return sorted(set(labels))


def _fix_hint(refs: list[str], conditions: dict[str, bool]) -> str:
    labels = " ".join(refs)
    if any(token in labels for token in ["제167조", "제173조"]):
        return "expand graph penalty/corporate candidates from death-related OSH obligation refs"
    if "제38조" in labels:
        return "expand safety-obligation candidates from accident_type/work_type facts"
    if "제39조" in labels:
        return "expand health-obligation candidates from health/hazard/suffocation facts"
    if "제63조" in labels or "제64조" in labels:
        return "expand contractor obligation candidates when contractor_relation is true"
    if any(token in labels for token in ["중대재해처벌법 제4조", "중대재해처벌법 제5조", "중대재해처벌법 제6조", "중대재해처벌법 제7조"]):
        return "expand Serious Accident Act chain candidates from serious_accident_issue facts"
    if any(token in labels for token in ["제1조", "제2조", "제3조", "시행령"]):
        return "route scope/definition refs to supporting evidence when scope_issue is true"
    return "inspect retrieval/evidence_pack source for missing article family"


def build_analysis(results_path: Path, dataset_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset = {str(item.get("id", "")): item for item in json.loads(dataset_path.read_text(encoding="utf-8"))}
    with results_path.open("r", encoding="utf-8-sig", newline="") as f:
        result_rows = list(csv.DictReader(f))

    rows: list[dict[str, Any]] = []
    slot_counter: Counter[str] = Counter()
    article_counter: Counter[str] = Counter()
    for row in result_rows:
        case_id = str(row.get("id", ""))
        item = dataset.get(case_id, {})
        prompt = item.get("case_scenario_prompt") or item.get("rewritten_question") or item.get("question") or ""
        gt_refs = _json_cell(row, "ground_truth_laws", [])
        candidate_fine_missing = _json_cell(row, "candidate_fine_missing", [])
        candidate_article_missing = _json_cell(row, "candidate_article_missing", [])

        if not candidate_fine_missing and not candidate_article_missing:
            continue

        selected_refs = sorted(_refs(_json_cell(row, "selected_laws", [])))
        supporting_refs = sorted(_refs(_json_cell(row, "supporting_laws", [])))
        candidate_refs = sorted(_refs(_json_cell(row, "candidate_laws", [])))
        missing_slots = sorted({_slot_for_ref(ref) for ref in candidate_article_missing or candidate_fine_missing})
        missing_articles = _article_labels(candidate_article_missing or candidate_fine_missing)
        for slot in missing_slots:
            slot_counter[slot] += 1
        for article in missing_articles:
            article_counter[article] += 1

        conditions = _case_conditions(item, prompt)
        rows.append(
            {
                "case_id": case_id,
                "case_name": row.get("case_name", ""),
                "candidate_fine_recall": row.get("candidate_fine_recall", row.get("candidate_recall", "")),
                "candidate_article_recall": row.get("candidate_article_recall", ""),
                "candidate_fine_missing": json.dumps(candidate_fine_missing, ensure_ascii=False),
                "candidate_article_missing": json.dumps(candidate_article_missing, ensure_ascii=False),
                "missing_slots": json.dumps(missing_slots, ensure_ascii=False),
                "missing_articles": json.dumps(missing_articles, ensure_ascii=False),
                "case_conditions": json.dumps(conditions, ensure_ascii=False),
                "selected_refs": json.dumps(selected_refs, ensure_ascii=False),
                "supporting_refs": json.dumps(supporting_refs, ensure_ascii=False),
                "candidate_refs": json.dumps(candidate_refs, ensure_ascii=False),
                "recommended_retrieval_fix": _fix_hint(candidate_article_missing or candidate_fine_missing, conditions),
                "gt_refs": json.dumps(gt_refs, ensure_ascii=False),
            }
        )

    summary = {
        "row_count": len(rows),
        "missing_slot_counts": dict(slot_counter),
        "missing_article_counts": dict(article_counter.most_common()),
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    rows, summary = build_analysis(Path(args.results), Path(args.dataset))
    output = Path(args.output)
    write_csv(
        output,
        rows,
        [
            "case_id",
            "case_name",
            "candidate_fine_recall",
            "candidate_article_recall",
            "candidate_fine_missing",
            "candidate_article_missing",
            "missing_slots",
            "missing_articles",
            "case_conditions",
            "selected_refs",
            "supporting_refs",
            "candidate_refs",
            "recommended_retrieval_fix",
            "gt_refs",
        ],
    )
    write_json(output.with_suffix(".summary.json"), summary)
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
