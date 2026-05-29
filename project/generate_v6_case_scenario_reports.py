from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated_v6_case_scenario_eval"
REPORTS = OUT / "reports"


def load_json(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    inv = load_json(OUT / "inventory" / "case_inventory_summary.json")
    extraction = load_json(OUT / "extraction" / "case_extraction_summary.json")
    mapping = load_json(OUT / "mapping" / "case_mapping_summary.json")
    dataset = load_json(OUT / "dataset" / "case_scenario_dataset_summary.json")
    eval_summary = load_json(OUT / "evaluation" / "case_scenario_api_summary.json")
    gaps = read_csv(OUT / "evaluation" / "case_scenario_gap_analysis.csv")
    reviews = read_csv(OUT / "dataset" / "case_scenario_eval_review.csv")

    write(REPORTS / "v6_dataset_construction_report.md", f"""# V6 Case Scenario Dataset Construction

## Inventory
- expected total: {inv.get('total_case_count', 69)}
- found: {inv.get('found_case_count', 0)}
- cases with text: {inv.get('cases_with_text', 0)}
- cases without text: {inv.get('cases_without_text', 0)}

## Extraction
- case facts rows: {extraction.get('case_count', 0)}
- law ref rows: {extraction.get('law_ref_count', 0)}
- review required: {extraction.get('review_required_count', 0)}
- accident type counts: `{json.dumps(extraction.get('accident_type_counts', {}), ensure_ascii=False)}`

## Mapping and Bundle
- mapping grade counts: `{json.dumps(mapping.get('mapping_grade_counts', {}), ensure_ascii=False)}`
- bundle status counts: `{json.dumps(mapping.get('bundle_status_counts', {}), ensure_ascii=False)}`
- dataset candidates: {dataset.get('candidate_count', 0)}
- READY_A: {dataset.get('ready_count', 0)}

## Manual Review
READY_A uses only direct current refs and A-grade mappings. REVIEW_B remains excluded from ready evaluation.
""")

    write(REPORTS / "v6_case_scenario_evaluation_report.md", f"""# V6 Case Scenario Evaluation

## Evaluation Setup
Input is a structured case_scenario prompt derived from each case's facts. GT is expected_legal_bundle; B-grade mappings are excluded.

## Main Metrics
- sample_count: {eval_summary.get('sample_count', 0)}
- selected_fine_grained_exact_f1: {eval_summary.get('selected_fine_grained_exact_f1', 0):.3f}
- selected_fine_grained_soft_f1: {eval_summary.get('selected_fine_grained_soft_f1', 0):.3f}
- selected_legal_chain_f1: {eval_summary.get('selected_legal_chain_f1', 0):.3f}
- bundle_slot_f1: {eval_summary.get('bundle_slot_f1', 0):.3f}
- full_obligation_penalty_corporate_chain_hit: {eval_summary.get('full_obligation_penalty_corporate_chain_hit', 0)}
- candidate_recall: {eval_summary.get('candidate_recall', 0):.3f}
- candidate_overgeneration_rate: {eval_summary.get('candidate_overgeneration_rate', 0):.3f}

## Interpretation
This is not question rewriting. It measures whether the system can reconstruct a legal bundle from case facts.
""")

    failure_counts = {}
    for row in gaps:
        failure_counts[row.get("failure_category", "unknown")] = failure_counts.get(row.get("failure_category", "unknown"), 0) + 1
    failed_examples = "\n".join(
        f"- {row.get('id')}: {row.get('case_name')} / {row.get('failure_category')}"
        for row in gaps[:15]
    )
    write(REPORTS / "v6_failure_analysis_report.md", f"""# V6 Failure Analysis

## Failure Type Counts
`{json.dumps(failure_counts, ensure_ascii=False)}`

## Example Cases
{failed_examples}

## Common Causes
- case facts are still automatically extracted and may be incomplete.
- B-grade old-current mappings are excluded, so some expected bundles are intentionally sparse.
- selected selector remains conservative; some correct refs may stay in supporting/candidate.
""")

    review_list = "\n".join(
        f"- {r.get('case_id')}: {r.get('case_name')} / {r.get('dataset_status')} / {r.get('review_reason')}"
        for r in reviews if r.get("dataset_status") != "READY_A"
    )
    write(REPORTS / "v6_next_improvement_plan.md", f"""# V6 Next Improvement Plan

## P0
- Manually review REVIEW_B cases and promote only verified mappings.
- Improve selected selector using case issue labels.
- Validate case_facts for high-value cases with many old-law refs.

## P1
- Add detail-rule matching for 산업안전보건기준에 관한 규칙.
- Separate selected/supporting/candidate bundle slots inside backend evidence_pack.
- Add answer-cited selected refs only when backed by selected chain or selected slot.

## Cases Needing Review
{review_list[:5000]}
""")


if __name__ == "__main__":
    main()
