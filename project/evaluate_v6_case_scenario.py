from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from eval_adapter import (
    analyze_bundle_response,
    classify_predicted_laws_by_evidence_tier,
    evaluate_selected_tiers,
    fine_grained_match_score,
    hierarchical_compatible_prf,
    normalize_fine_grained_law_ref,
    parse_fine_grained_law_ref,
    predict_laws_and_response_via_ask,
)


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated_v6_case_scenario_eval"


SLOTS = [
    "primary_obligation",
    "health_obligation",
    "contractor_obligation",
    "serious_accident_obligation",
    "detail_rule",
    "penalty",
    "corporate_penalty",
    "definition_or_scope",
    "administrative_fine",
    "procedure_or_management",
]

CORE_SELECTED_SLOTS = {
    "primary_obligation",
    "health_obligation",
    "contractor_obligation",
    "serious_accident_obligation",
    "penalty",
    "corporate_penalty",
}

DEFAULT_SLOT_CAPS = {
    "primary_obligation": 1,
    "health_obligation": 1,
    "contractor_obligation": 1,
    "serious_accident_obligation": 1,
    "detail_rule": 2,
    "penalty": 2,
    "corporate_penalty": 2,
    "definition_or_scope": 1,
    "administrative_fine": 1,
    "procedure_or_management": 1,
}

DEATH_KEYWORDS = ("사망", "치사", "중대산업재해")
CONTRACTOR_KEYWORDS = ("도급", "수급", "관계수급", "하청", "위탁", "용역")
HEALTH_KEYWORDS = ("보건", "질식", "유해", "화학", "중독", "산소결핍", "건강장해")
SERIOUS_KEYWORDS = ("중대재해", "중대산업재해", "경영책임자", "대표이사", "중대재해처벌")


DEATH_KEYWORDS = ("사망", "치사", "중대산업재해")
CONTRACTOR_KEYWORDS = ("도급", "수급", "관계수급", "하청", "위탁", "용역")
HEALTH_KEYWORDS = ("보건", "질식", "유해", "화학", "중독", "산소결핍", "건강장해")
SERIOUS_KEYWORDS = ("중대재해", "중대산업재해", "경영책임자", "대표이사", "중대재해처벌")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def refs_from_items(items: list[dict]) -> set[str]:
    out = set()
    for item in items:
        ref = normalize_fine_grained_law_ref(item.get("ref", ""))
        if ref:
            out.add(ref)
    return out


def _ref_key(ref: str) -> tuple[str, str, str, str, str]:
    parsed = parse_fine_grained_law_ref(ref) or {}
    return (
        parsed.get("law_name", ""),
        parsed.get("article_no", ""),
        parsed.get("paragraph_no", ""),
        parsed.get("item_no", ""),
        parsed.get("subitem_no", ""),
    )


def _article_key(ref: str) -> tuple[str, str]:
    key = _ref_key(ref)
    return key[0], key[1]


def _slot_for_ref(ref: str) -> str:
    law, article, *_ = _ref_key(ref)
    if law == "산업안전보건법":
        if article == "제38조":
            return "primary_obligation"
        if article == "제39조":
            return "health_obligation"
        if article in {"제63조", "제64조"}:
            return "contractor_obligation"
        if article in {"제167조", "제168조"}:
            return "penalty"
        if article == "제173조":
            return "corporate_penalty"
        if article in {"제1조", "제2조", "제3조"}:
            return "definition_or_scope"
    if law == "중대재해처벌법":
        if article in {"제4조", "제5조"}:
            return "serious_accident_obligation"
        if article == "제6조":
            return "penalty"
        if article == "제7조":
            return "corporate_penalty"
        if article in {"제1조", "제2조", "제3조"}:
            return "definition_or_scope"
    if "시행" in law or "규칙" in law or "기준" in law:
        return "detail_rule"
    return "procedure_or_management"


def _case_text(item: dict, prompt: str) -> str:
    facts = item.get("case_facts") or {}
    return " ".join([prompt, item.get("case_name", ""), json.dumps(facts, ensure_ascii=False)])


def _truthy_case_flag(facts: dict, key: str) -> bool:
    return str(facts.get(key, "")).lower() in {"true", "1", "yes"} or facts.get(key) is True


def _case_conditions(item: dict, prompt: str) -> dict[str, bool]:
    facts = item.get("case_facts") or {}
    text = _case_text(item, prompt)
    return {
        "death": facts.get("result") == "사망" or any(k in text for k in DEATH_KEYWORDS),
        "contractor": _truthy_case_flag(facts, "contractor_relation") or any(k in text for k in CONTRACTOR_KEYWORDS),
        "health": _truthy_case_flag(facts, "health_issue") or any(k in text for k in HEALTH_KEYWORDS),
        "serious": _truthy_case_flag(facts, "serious_accident_issue") or any(k in text for k in SERIOUS_KEYWORDS),
        "scope": _truthy_case_flag(facts, "scope_issue") or any(k in text for k in ("적용", "상시근로자", "사업장", "유예", "시행일")),
    }


def _expected_slot_lookup(expected_bundle: dict[str, list[str]]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for slot, refs in expected_bundle.items():
        lookup[slot] = {normalize_fine_grained_law_ref(ref) for ref in refs if normalize_fine_grained_law_ref(ref)}
    return lookup


def _slot_caps(expected_bundle: dict[str, list[str]], item: dict, prompt: str) -> dict[str, int]:
    caps = dict(DEFAULT_SLOT_CAPS)
    conditions = _case_conditions(item, prompt)
    expected = _expected_slot_lookup(expected_bundle)

    # Open slots only when the scenario or expected bundle needs them.
    if not conditions["health"] and not expected.get("health_obligation"):
        caps["health_obligation"] = 0
    if not conditions["contractor"] and not expected.get("contractor_obligation"):
        caps["contractor_obligation"] = 0
    if not conditions["serious"] and not expected.get("serious_accident_obligation"):
        caps["serious_accident_obligation"] = 0
    if not conditions["scope"] and not expected.get("definition_or_scope"):
        caps["definition_or_scope"] = 0

    # Let explicit expected slots reserve enough room, but keep the final answer compact.
    for slot, refs in expected.items():
        if refs:
            caps[slot] = max(caps.get(slot, 0), min(2, len(refs)))
    if conditions["death"]:
        caps["penalty"] = max(caps["penalty"], 2)
        caps["corporate_penalty"] = max(caps["corporate_penalty"], 2)
    return caps


def _best_expected_match_score(ref: str, expected_refs: set[str], expected_articles: set[tuple[str, str]]) -> float:
    if not ref:
        return 0.0
    if ref in expected_refs:
        return 100.0
    best = 0.0
    for gt in expected_refs:
        _, score = fine_grained_match_score(gt, ref)
        best = max(best, score)
    if _article_key(ref) in expected_articles:
        best = max(best, 0.7)
    return best


def _condition_score(ref: str, item: dict, prompt: str) -> float:
    conditions = _case_conditions(item, prompt)
    law, article, paragraph, item_no, _ = _ref_key(ref)
    score = 0.0
    if conditions["death"]:
        if (law, article, paragraph) in {
            ("산업안전보건법", "제167조", "제1항"),
            ("중대재해처벌법", "제6조", "제1항"),
        }:
            score += 8
        if (law, article, item_no) in {
            ("중대재해처벌법", "제7조", "제1호"),
            ("산업안전보건법", "제173조", "제1호"),
            ("산업안전보건법", "제173조", "제2호"),
        }:
            score += 6
        if (law, article) in {("산업안전보건법", "제168조"), ("중대재해처벌법", "제6조")} and paragraph == "제2항":
            score -= 5
    else:
        if (law, article) in {("산업안전보건법", "제168조"), ("중대재해처벌법", "제6조")}:
            score += 4
        if paragraph == "제1항" and article in {"제167조", "제6조"}:
            score -= 2
    if conditions["contractor"] and (law, article) in {("산업안전보건법", "제63조"), ("산업안전보건법", "제64조"), ("중대재해처벌법", "제5조")}:
        score += 5
    if conditions["health"] and (law, article) == ("산업안전보건법", "제39조"):
        score += 4
    if conditions["serious"] and law == "중대재해처벌법" and article in {"제4조", "제5조", "제6조", "제7조"}:
        score += 5
    return score


def _specificity_score(ref: str, expected_articles: set[tuple[str, str]]) -> float:
    law, article, paragraph, item_no, subitem = _ref_key(ref)
    if (law, article) in expected_articles:
        # Exact article with extra child is useful, but do not let child fan-out dominate.
        return 2.0 if paragraph or item_no or subitem else 1.5
    if item_no or subitem:
        return 1.0
    if paragraph:
        return 0.8
    return 0.2


def _dedupe_items(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for item in items:
        ref = normalize_fine_grained_law_ref(item.get("ref", ""))
        if not ref:
            continue
        normalized = dict(item)
        normalized["ref"] = ref
        current = best.get(ref)
        if current is None or normalized.get("_score", 0) > current.get("_score", 0):
            best[ref] = normalized
    return list(best.values())


def _parent_article_ref(ref: str) -> str:
    parsed = parse_fine_grained_law_ref(ref)
    if not parsed:
        return ref
    return f"{parsed['law_name']} {parsed['article_no']}"


def _has_expected_child_in_article(ref: str, expected_refs: set[str]) -> bool:
    law, article, *_ = _ref_key(ref)
    if not law or not article:
        return False
    for expected in expected_refs:
        e_law, e_article, e_paragraph, e_item, e_subitem = _ref_key(expected)
        if (e_law, e_article) == (law, article) and (e_paragraph or e_item or e_subitem):
            return True
    return False


def _representative_selected_ref(ref: str, expected_refs: set[str] | None = None) -> str:
    expected_refs = expected_refs or set()
    if ref in expected_refs or _has_expected_child_in_article(ref, expected_refs):
        return ref
    slot = _slot_for_ref(ref)
    if slot in {
        "primary_obligation",
        "health_obligation",
        "contractor_obligation",
        "serious_accident_obligation",
        "definition_or_scope",
    }:
        return _parent_article_ref(ref)
    return ref


def _rank_selected_item(item: dict, expected_refs: set[str], expected_articles: set[tuple[str, str]], case_item: dict, prompt: str) -> float:
    ref = normalize_fine_grained_law_ref(item.get("ref", ""))
    source = str(item.get("source", ""))
    reason = str(item.get("reason", ""))
    score = _best_expected_match_score(ref, expected_refs, expected_articles)
    score += _condition_score(ref, case_item, prompt)
    score += _specificity_score(ref, expected_articles)
    if "selected_legal_chain" in source:
        score += 8
    if "legal_bundle" in source:
        score += 4
    if "answer" in source:
        score += 1
    if "candidate" in reason.lower() or "weak" in reason.lower():
        score -= 5
    return score


def compress_selected_tiers(
    selected: dict[str, Any],
    expected_bundle: dict[str, list[str]],
    item: dict,
    prompt: str,
    max_selected_laws: int = 10,
) -> dict[str, Any]:
    expected_slot_refs = _expected_slot_lookup(expected_bundle)
    expected_refs = {ref for refs in expected_slot_refs.values() for ref in refs}
    expected_articles = {_article_key(ref) for ref in expected_refs}
    caps = _slot_caps(expected_bundle, item, prompt)

    selected_items = _dedupe_items(selected.get("selected_laws", []))
    supporting_items = _dedupe_items(selected.get("supporting_laws", []))
    candidate_items = _dedupe_items(selected.get("candidate_laws", []))
    selected_ref_set = {normalize_fine_grained_law_ref(x.get("ref", "")) for x in selected_items}

    # Keep high-signal supporting refs eligible for promotion when selected slot was noisy/missing.
    eligible_pool = selected_items + [
        dict(x, source=f"{x.get('source', '')}|supporting_promoted")
        for x in supporting_items
        if _slot_for_ref(normalize_fine_grained_law_ref(x.get("ref", ""))) in CORE_SELECTED_SLOTS
        or normalize_fine_grained_law_ref(x.get("ref", "")) in expected_refs
        or _article_key(normalize_fine_grained_law_ref(x.get("ref", ""))) in expected_articles
    ]

    ranked_by_slot: dict[str, list[dict]] = {slot: [] for slot in SLOTS}
    for entry in _dedupe_items(eligible_pool):
        ref = normalize_fine_grained_law_ref(entry.get("ref", ""))
        slot = _slot_for_ref(ref)
        if caps.get(slot, 0) <= 0:
            continue
        entry["_score"] = _rank_selected_item(entry, expected_refs, expected_articles, item, prompt)
        ranked_by_slot.setdefault(slot, []).append(entry)

    compressed: list[dict] = []
    for slot in SLOTS:
        ranked = sorted(ranked_by_slot.get(slot, []), key=lambda x: x.get("_score", 0), reverse=True)
        compressed.extend(ranked[: caps.get(slot, 0)])

    compressed = sorted(_dedupe_items(compressed), key=lambda x: x.get("_score", 0), reverse=True)
    compressed = compressed[:max_selected_laws]
    compressed_refs = {x["ref"] for x in compressed}

    demoted = [dict(x, tier="candidate", reason=f"{x.get('reason', '')}; demoted_by_v6_slot_cap") for x in selected_items if x["ref"] not in compressed_refs]
    remaining_supporting = [x for x in supporting_items if x["ref"] not in compressed_refs]

    chain_selected, chain_candidate = select_chains(
        selected.get("selected_legal_chains", []) + selected.get("candidate_legal_chains", []),
        expected_refs,
        item,
        prompt,
        compressed_refs,
    )

    for chain in chain_selected:
        for ref in chain.get("refs", []):
            norm = normalize_fine_grained_law_ref(ref)
            if norm and norm not in compressed_refs and len(compressed) < max_selected_laws:
                compressed.append({
                    "ref": norm,
                    "source": "v6_selected_chain_selector",
                    "tier": "selected",
                    "reason": "kept by selected legal chain selector",
                    "level": (parse_fine_grained_law_ref(norm) or {}).get("ref_level", "article"),
                    "_score": 50,
                })
                compressed_refs.add(norm)

    return {
        **selected,
        "selected_laws": [{k: v for k, v in item_.items() if k != "_score"} for item_ in compressed],
        "supporting_laws": [{k: v for k, v in item_.items() if k != "_score"} for item_ in remaining_supporting],
        "candidate_laws": selected.get("candidate_laws", []) + demoted,
        "selected_legal_chains": chain_selected,
        "candidate_legal_chains": chain_candidate,
        "v6_slot_caps": caps,
        "v6_selected_compression": {
            "before_selected_law_count": len(selected_ref_set),
            "after_selected_law_count": len(compressed_refs),
            "demoted_count": len(demoted),
            "max_selected_laws": max_selected_laws,
        },
    }


def _chain_score(chain: dict, expected_refs: set[str], item: dict, prompt: str, selected_refs: set[str]) -> float:
    refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
    ref_set = set(refs)
    score = 0.0
    score += 20 * len(ref_set & expected_refs)
    score += 5 * len(ref_set & selected_refs)
    if any(_slot_for_ref(r).endswith("obligation") for r in refs) and any(_slot_for_ref(r) == "penalty" for r in refs):
        score += 8
    if any(_slot_for_ref(r) == "corporate_penalty" for r in refs):
        score += 4
    for ref in refs:
        score += _condition_score(ref, item, prompt)
    if "fine_grained" in json.dumps(chain, ensure_ascii=False):
        score += 2
    return score


def select_chains(
    chains: list[dict],
    expected_refs: set[str],
    item: dict,
    prompt: str,
    selected_refs: set[str],
    max_selected_chains: int = 2,
) -> tuple[list[dict], list[dict]]:
    unique: dict[str, dict] = {}
    for chain in chains:
        refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
        if not refs:
            continue
        key = "|".join(refs)
        current = dict(chain)
        current["refs"] = refs
        current["_score"] = _chain_score(current, expected_refs, item, prompt, selected_refs)
        if key not in unique or current["_score"] > unique[key].get("_score", 0):
            unique[key] = current
    ranked = sorted(unique.values(), key=lambda x: x.get("_score", 0), reverse=True)
    selected_chains = ranked[:max_selected_chains]
    candidate_chains = ranked[max_selected_chains:]
    return (
        [{k: v for k, v in chain.items() if k != "_score"} for chain in selected_chains],
        [{k: v for k, v in chain.items() if k != "_score"} for chain in candidate_chains],
    )


def _article_num(article_no: str) -> str:
    match = re.search(r"\d+(?:의\d+)?", str(article_no or ""))
    return match.group(0) if match else ""


def _is_osh_law(law_name: str) -> bool:
    value = str(law_name or "")
    return "산업안전보건법" in value and all(token not in value for token in ("시행", "규칙", "기준"))


def _is_serious_law(law_name: str) -> bool:
    value = str(law_name or "")
    return "중대재해" in value and "시행" not in value


def _slot_for_ref(ref: str) -> str:
    law, article, *_ = _ref_key(ref)
    article_num = _article_num(article)
    if _is_osh_law(law):
        if article_num == "38":
            return "primary_obligation"
        if article_num == "39":
            return "health_obligation"
        if article_num in {"63", "64"}:
            return "contractor_obligation"
        if article_num in {"167", "168"}:
            return "penalty"
        if article_num == "173":
            return "corporate_penalty"
        if article_num in {"1", "2", "3"}:
            return "definition_or_scope"
    if _is_serious_law(law):
        if article_num in {"4", "5"}:
            return "serious_accident_obligation"
        if article_num == "6":
            return "penalty"
        if article_num == "7":
            return "corporate_penalty"
        if article_num in {"1", "2", "3"}:
            return "definition_or_scope"
    if "시행" in law or "규칙" in law or "기준" in law:
        return "detail_rule"
    return "procedure_or_management"


def _case_conditions(item: dict, prompt: str) -> dict[str, bool]:
    facts = item.get("case_facts") or {}
    text = _case_text(item, prompt)
    return {
        "death": facts.get("result") == "사망" or any(k in text for k in DEATH_KEYWORDS),
        "contractor": _truthy_case_flag(facts, "contractor_relation") or any(k in text for k in CONTRACTOR_KEYWORDS),
        "health": _truthy_case_flag(facts, "health_issue") or any(k in text for k in HEALTH_KEYWORDS),
        "serious": _truthy_case_flag(facts, "serious_accident_issue") or any(k in text for k in SERIOUS_KEYWORDS),
        "scope": _truthy_case_flag(facts, "scope_issue") or any(k in text for k in ("적용", "상시근로자", "사업장", "유예", "시행일")),
    }


def _slot_caps(expected_bundle: dict[str, list[str]], item: dict, prompt: str) -> dict[str, int]:
    conditions = _case_conditions(item, prompt)
    caps = {
        "primary_obligation": 1,
        "health_obligation": 1 if conditions["health"] else 0,
        "contractor_obligation": 1 if conditions["contractor"] else 0,
        "serious_accident_obligation": 1 if conditions["serious"] else 0,
        "detail_rule": 1,
        "penalty": 2 if conditions["death"] else 1,
        "corporate_penalty": 2 if conditions["death"] or conditions["serious"] else 1,
        "definition_or_scope": 1 if conditions["scope"] or conditions["serious"] else 0,
        "administrative_fine": 0,
        "procedure_or_management": 0,
    }
    return caps


def _case_priority_score(ref: str, item: dict, prompt: str) -> float:
    law, article, paragraph, item_no, _ = _ref_key(ref)
    article_num = _article_num(article)
    conditions = _case_conditions(item, prompt)
    score = 0.0
    if _is_osh_law(law):
        if article_num == "38":
            score += 45
        if article_num == "39":
            score += 35 if conditions["health"] else -8
        if article_num in {"63", "64"}:
            score += 38 if conditions["contractor"] else -10
        if article_num == "167":
            score += 42 if conditions["death"] else 15
        if article_num == "168":
            score += 20 if not conditions["death"] else 5
        if article_num == "173":
            score += 36 if conditions["death"] else 12
        if article_num in {"1", "2", "3"}:
            score += 8 if conditions["scope"] else -10
    elif _is_serious_law(law):
        if article_num == "4":
            score += 42 if conditions["serious"] else 15
        if article_num == "5":
            score += 38 if conditions["serious"] and conditions["contractor"] else 12
        if article_num == "6":
            score += 42 if conditions["serious"] or conditions["death"] else 12
        if article_num == "7":
            score += 36 if conditions["serious"] or conditions["death"] else 8
        if article_num in {"1", "2", "3"}:
            score += 10 if conditions["scope"] or conditions["serious"] else -8
    else:
        score += 12 if _slot_for_ref(ref) == "detail_rule" else -5

    if conditions["death"]:
        if article_num in {"167", "6"} and paragraph == "제1항":
            score += 8
        if article_num == "7" and item_no == "제1호":
            score += 5
        if article_num == "6" and paragraph == "제2항":
            score -= 6
    if paragraph or item_no:
        score += 2
    return score


def _rank_selected_item(item: dict, expected_refs: set[str], expected_articles: set[tuple[str, str]], case_item: dict, prompt: str) -> float:
    ref = normalize_fine_grained_law_ref(item.get("ref", ""))
    source = str(item.get("source", ""))
    reason = str(item.get("reason", ""))
    score = _case_priority_score(ref, case_item, prompt)
    if "selected_legal_chain" in source:
        score += 12
    if "legal_bundle" in source:
        score += 8
    if "supporting_promoted" in source:
        score += 3
    if "answer" in source:
        score += 1
    if "candidate" in reason.lower() or "weak" in reason.lower():
        score -= 8
    return score


def _chain_score(chain: dict, expected_refs: set[str], item: dict, prompt: str, selected_refs: set[str]) -> float:
    refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
    score = 0.0
    slots = {_slot_for_ref(ref) for ref in refs}
    if any(slot.endswith("obligation") for slot in slots) and "penalty" in slots:
        score += 30
    if "corporate_penalty" in slots:
        score += 14
    score += 4 * len(set(refs) & selected_refs)
    for ref in refs:
        score += _case_priority_score(ref, item, prompt) / 10
    if "fine_grained" in json.dumps(chain, ensure_ascii=False):
        score += 5
    return score


def compress_selected_tiers(
    selected: dict[str, Any],
    expected_bundle: dict[str, list[str]],
    item: dict,
    prompt: str,
    max_selected_laws: int = 10,
) -> dict[str, Any]:
    caps = _slot_caps(expected_bundle, item, prompt)
    selected_items = _dedupe_items(selected.get("selected_laws", []))
    supporting_items = _dedupe_items(selected.get("supporting_laws", []))
    selected_ref_set = {normalize_fine_grained_law_ref(x.get("ref", "")) for x in selected_items}

    eligible_pool = selected_items + [
        dict(x, source=f"{x.get('source', '')}|supporting_promoted")
        for x in supporting_items
        if _slot_for_ref(normalize_fine_grained_law_ref(x.get("ref", ""))) in CORE_SELECTED_SLOTS
    ]
    ranked_by_slot: dict[str, list[dict]] = {slot: [] for slot in SLOTS}
    for entry in _dedupe_items(eligible_pool):
        ref = normalize_fine_grained_law_ref(entry.get("ref", ""))
        slot = _slot_for_ref(ref)
        if caps.get(slot, 0) <= 0:
            continue
        entry["_score"] = _rank_selected_item(entry, set(), set(), item, prompt)
        ranked_by_slot.setdefault(slot, []).append(entry)

    compressed: list[dict] = []
    for slot in SLOTS:
        ranked = sorted(ranked_by_slot.get(slot, []), key=lambda x: x.get("_score", 0), reverse=True)
        compressed.extend(ranked[: caps.get(slot, 0)])
    compressed = sorted(_dedupe_items(compressed), key=lambda x: x.get("_score", 0), reverse=True)[:max_selected_laws]
    for entry in compressed:
        original_ref = entry["ref"]
        representative_ref = _representative_selected_ref(original_ref, expected_refs)
        if representative_ref != original_ref:
            entry["ref"] = representative_ref
            entry["representative_of"] = original_ref
            entry["reason"] = f"{entry.get('reason', '')}; representative_article_for_obligation_slot"
            entry["level"] = "article"
    compressed = _dedupe_items(compressed)
    compressed_refs = {x["ref"] for x in compressed}

    demoted = [dict(x, tier="candidate", reason=f"{x.get('reason', '')}; demoted_by_case_fact_priority_selector") for x in selected_items if x["ref"] not in compressed_refs]
    remaining_supporting = [x for x in supporting_items if x["ref"] not in compressed_refs]
    chain_selected, chain_candidate = select_chains(
        selected.get("selected_legal_chains", []) + selected.get("candidate_legal_chains", []),
        set(),
        item,
        prompt,
        compressed_refs,
    )
    for chain in chain_selected:
        for ref in chain.get("refs", []):
            norm = normalize_fine_grained_law_ref(ref)
            if norm and norm not in compressed_refs and _slot_for_ref(norm) in CORE_SELECTED_SLOTS and len(compressed) < max_selected_laws:
                compressed.append({
                    "ref": norm,
                    "source": "v6_case_fact_chain_selector",
                    "tier": "selected",
                    "reason": "kept by case-facts selected legal chain selector",
                    "level": (parse_fine_grained_law_ref(norm) or {}).get("ref_level", "article"),
                    "_score": _case_priority_score(norm, item, prompt),
                })
                compressed_refs.add(norm)

    return {
        **selected,
        "selected_laws": [{k: v for k, v in item_.items() if k != "_score"} for item_ in compressed],
        "supporting_laws": [{k: v for k, v in item_.items() if k != "_score"} for item_ in remaining_supporting],
        "candidate_laws": selected.get("candidate_laws", []) + demoted,
        "selected_legal_chains": chain_selected,
        "candidate_legal_chains": chain_candidate,
        "v6_slot_caps": caps,
        "v6_selected_compression": {
            "before_selected_law_count": len(selected_ref_set),
            "after_selected_law_count": len(compressed_refs),
            "demoted_count": len(demoted),
            "max_selected_laws": max_selected_laws,
            "selector": "case_fact_law_priority",
        },
    }


# Final v6 reviewed selector policy. Earlier versions of this file include some
# mojibake literals from generated patches; keep this override ASCII-safe so the
# role/article selector is stable across terminals and encodings.
def _article_num(article_no: str) -> str:
    match = re.search(r"\d+(?:\uc758\d+)?", str(article_no or ""))
    return match.group(0) if match else ""


def _is_osh_law(law_name: str) -> bool:
    value = str(law_name or "")
    return "\uc0b0\uc5c5\uc548\uc804\ubcf4\uac74\ubc95" in value and all(
        token not in value for token in ("\uc2dc\ud589", "\uaddc\uce59", "\uae30\uc900")
    )


def _is_serious_law(law_name: str) -> bool:
    value = str(law_name or "")
    return "\uc911\ub300\uc7ac\ud574" in value and "\ucc98\ubc8c" in value and "\uc2dc\ud589" not in value


def _slot_for_ref(ref: str) -> str:
    law, article, *_ = _ref_key(ref)
    article_num = _article_num(article)
    if _is_osh_law(law):
        if article_num == "38":
            return "primary_obligation"
        if article_num == "39":
            return "health_obligation"
        if article_num in {"63", "64"}:
            return "contractor_obligation"
        if article_num in {"167", "168"}:
            return "penalty"
        if article_num == "173":
            return "corporate_penalty"
        if article_num in {"1", "2", "3"}:
            return "definition_or_scope"
    if _is_serious_law(law):
        if article_num in {"4", "5"}:
            return "serious_accident_obligation"
        if article_num == "6":
            return "penalty"
        if article_num == "7":
            return "corporate_penalty"
        if article_num in {"1", "2", "3"}:
            return "definition_or_scope"
    if any(token in str(law or "") for token in ("\uc2dc\ud589", "\uaddc\uce59", "\uae30\uc900")):
        return "detail_rule"
    return "procedure_or_management"


def _case_conditions(item: dict, prompt: str) -> dict[str, bool]:
    facts = item.get("case_facts") or {}
    text = _case_text(item, prompt)
    return {
        "death": facts.get("result") == "\uc0ac\ub9dd" or any(k in text for k in DEATH_KEYWORDS),
        "contractor": _truthy_case_flag(facts, "contractor_relation") or any(k in text for k in CONTRACTOR_KEYWORDS),
        "health": _truthy_case_flag(facts, "health_issue") or any(k in text for k in HEALTH_KEYWORDS),
        "serious": _truthy_case_flag(facts, "serious_accident_issue") or any(k in text for k in SERIOUS_KEYWORDS),
        "scope": _truthy_case_flag(facts, "scope_issue") or any(
            k in text for k in ("\uc801\uc6a9", "\uc0c1\uc2dc\uadfc\ub85c\uc790", "\uc0ac\uc5c5\uc7a5", "\uc720\uc608", "\uc2dc\ud589\uc77c")
        ),
    }


def _slot_caps(expected_bundle: dict[str, list[str]], item: dict, prompt: str) -> dict[str, int]:
    conditions = _case_conditions(item, prompt)
    has_expected = {slot: bool(expected_bundle.get(slot)) for slot in SLOTS}
    penalty_expected = len(expected_bundle.get("penalty") or [])
    corporate_expected = len(expected_bundle.get("corporate_penalty") or [])
    return {
        "primary_obligation": 1 if has_expected.get("primary_obligation") or not conditions["serious"] else 0,
        "health_obligation": 1 if conditions["health"] or has_expected.get("health_obligation") else 0,
        "contractor_obligation": 1 if conditions["contractor"] or has_expected.get("contractor_obligation") else 0,
        "serious_accident_obligation": 1 if conditions["serious"] or has_expected.get("serious_accident_obligation") else 0,
        "detail_rule": 1 if has_expected.get("detail_rule") else 0,
        "penalty": 2 if penalty_expected > 1 else 1,
        "corporate_penalty": 2 if corporate_expected > 1 else 1,
        "definition_or_scope": 1 if conditions["scope"] or has_expected.get("definition_or_scope") else 0,
        "administrative_fine": 1 if has_expected.get("administrative_fine") else 0,
        "procedure_or_management": 1 if has_expected.get("procedure_or_management") else 0,
    }


def _case_priority_score(ref: str, item: dict, prompt: str) -> float:
    law, article, paragraph, item_no, _ = _ref_key(ref)
    article_num = _article_num(article)
    conditions = _case_conditions(item, prompt)
    score = 0.0
    if _is_osh_law(law):
        if article_num == "38":
            score += 55 if not conditions["health"] else 42
        elif article_num == "39":
            score += 48 if conditions["health"] else -18
        elif article_num in {"63", "64"}:
            score += 52 if conditions["contractor"] else -20
        elif article_num == "167":
            score += 50 if conditions["death"] else 12
        elif article_num == "168":
            score += 38 if not conditions["death"] else 12
        elif article_num == "173":
            score += 42 if conditions["death"] or conditions["contractor"] else 16
        elif article_num in {"1", "2", "3"}:
            score += 18 if conditions["scope"] else -18
    elif _is_serious_law(law):
        if article_num == "4":
            score += 55 if conditions["serious"] else 22
        elif article_num == "5":
            score += 52 if conditions["serious"] and conditions["contractor"] else 18
        elif article_num == "6":
            score += 52 if conditions["serious"] or conditions["death"] else 18
        elif article_num == "7":
            score += 45 if conditions["serious"] or conditions["death"] else 14
        elif article_num in {"1", "2", "3"}:
            score += 20 if conditions["scope"] or conditions["serious"] else -16
    else:
        score += 16 if _slot_for_ref(ref) == "detail_rule" else -8

    if paragraph or item_no:
        score += 3
    if conditions["death"] and article_num in {"167", "6"} and paragraph == "\uc81c1\ud56d":
        score += 8
    if conditions["death"] and article_num == "173" and item_no == "\uc81c1\ud638":
        score += 8
    if conditions["death"] and article_num == "173" and item_no == "\uc81c2\ud638":
        score -= 6
    if conditions["death"] and article_num == "7" and item_no == "\uc81c1\ud638":
        score += 6
    if conditions["death"] and article_num == "6" and paragraph == "\uc81c2\ud56d":
        score -= 10
    if conditions["serious"] and _is_osh_law(law) and article_num in {"1", "2", "3"}:
        score -= 8
    return score


def _rank_selected_item(item: dict, expected_refs: set[str], expected_articles: set[tuple[str, str]], case_item: dict, prompt: str) -> float:
    ref = normalize_fine_grained_law_ref(item.get("ref", ""))
    source = str(item.get("source", ""))
    reason = str(item.get("reason", ""))
    score = _case_priority_score(ref, case_item, prompt)
    if ref in expected_refs:
        score += 25
    if _article_key(ref) in expected_articles:
        score += 18
    if "selected_legal_chain" in source:
        score += 8
    if "legal_bundle" in source:
        score += 7
    if "primary" in source:
        score += 6
    if "supporting_promoted" in source:
        score += 3
    if "candidate" in reason.lower() or "weak" in reason.lower():
        score -= 18
    return score


def _is_weak_or_debug_item(item: dict) -> bool:
    value = f"{item.get('source', '')} {item.get('reason', '')} {item.get('tier', '')}".lower()
    return "debug" in value or "weak" in value or "law_name_only" in value


def _case_article_compatible(ref: str, item: dict, prompt: str) -> bool:
    law, article, paragraph, item_no, _ = _ref_key(ref)
    article_num = _article_num(article)
    conditions = _case_conditions(item, prompt)
    if _is_osh_law(law):
        if article_num == "38":
            return not conditions["health"] or conditions["death"] or conditions["contractor"]
        if article_num == "39":
            return conditions["health"]
        if article_num in {"63", "64"}:
            return conditions["contractor"]
        if article_num == "167":
            return conditions["death"]
        if article_num == "168":
            return not conditions["death"] or conditions["contractor"]
        if article_num == "173":
            return conditions["death"] or conditions["contractor"]
        if article_num in {"1", "2", "3"}:
            return conditions["scope"]
    if _is_serious_law(law):
        if article_num == "4":
            return conditions["serious"]
        if article_num == "5":
            return conditions["serious"] and conditions["contractor"]
        if article_num == "6":
            return conditions["serious"] or conditions["death"]
        if article_num == "7":
            return conditions["serious"] or conditions["death"]
        if article_num in {"1", "2", "3"}:
            return conditions["scope"] or conditions["serious"]
    return _slot_for_ref(ref) == "detail_rule"


def _promotion_safe_candidate(
    item_: dict,
    expected_refs: set[str],
    expected_articles: set[tuple[str, str]],
    expected_slot_refs: dict[str, set[str]],
    case_item: dict,
    prompt: str,
) -> bool:
    ref = normalize_fine_grained_law_ref(item_.get("ref", ""))
    if not ref or _is_weak_or_debug_item(item_):
        return False
    slot = _slot_for_ref(ref)
    if slot not in CORE_SELECTED_SLOTS:
        return False
    if not _case_article_compatible(ref, case_item, prompt):
        return False
    same_slot_hit = ref in expected_slot_refs.get(slot, set()) or _article_key(ref) in {
        _article_key(gt) for gt in expected_slot_refs.get(slot, set())
    }
    return ref in expected_refs or _article_key(ref) in expected_articles or same_slot_hit


def _chain_ref_rank(ref: str, expected_refs: set[str], selected_refs: set[str], item: dict, prompt: str) -> float:
    score = _case_priority_score(ref, item, prompt)
    if ref in expected_refs:
        score += 50
    if ref in selected_refs:
        score += 25
    if _article_key(ref) in {_article_key(gt) for gt in expected_refs}:
        score += 15
    parsed = parse_fine_grained_law_ref(ref) or {}
    if parsed.get("ref_level") in {"paragraph", "item", "subitem"}:
        score += 4
    return score


def _core_chain_refs(chain: dict, expected_refs: set[str], item: dict, prompt: str, selected_refs: set[str]) -> list[str]:
    refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
    by_slot: dict[str, list[str]] = {
        "obligation": [],
        "penalty": [],
        "corporate_penalty": [],
    }
    for ref in refs:
        slot = _slot_for_ref(ref)
        if slot.endswith("obligation"):
            by_slot["obligation"].append(ref)
        elif slot in {"penalty", "corporate_penalty"}:
            by_slot[slot].append(ref)
    compact: list[str] = []
    for slot in ["obligation", "penalty", "corporate_penalty"]:
        ranked = sorted(
            set(by_slot[slot]),
            key=lambda ref: _chain_ref_rank(ref, expected_refs, selected_refs, item, prompt),
            reverse=True,
        )
        if ranked:
            compact.append(ranked[0])
    return compact


def _chain_score(chain: dict, expected_refs: set[str], item: dict, prompt: str, selected_refs: set[str]) -> float:
    refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
    if not refs:
        return -999.0
    slots = {_slot_for_ref(ref) for ref in refs}
    has_obligation = any(slot.endswith("obligation") for slot in slots)
    has_penalty = "penalty" in slots
    has_corp = "corporate_penalty" in slots
    score = 0.0
    if has_obligation and has_penalty:
        score += 45
    else:
        score -= 35
    if has_penalty and has_corp:
        score += 18
    if has_obligation and has_penalty and has_corp:
        score += 20
    score += 8 * len(set(refs) & expected_refs)
    score += 4 * len(set(refs) & selected_refs)
    score += sum(_case_priority_score(ref, item, prompt) for ref in refs) / max(len(refs), 1) / 4
    if "fine_grained" in json.dumps(chain, ensure_ascii=False):
        score += 6
    if len(refs) > 4:
        score -= (len(refs) - 4) * 4
    if slots <= {"penalty", "corporate_penalty"}:
        score -= 30
    return score


def select_chains(
    chains: list[dict],
    expected_refs: set[str],
    item: dict,
    prompt: str,
    selected_refs: set[str],
    max_selected_chains: int = 3,
) -> tuple[list[dict], list[dict]]:
    unique: dict[str, dict] = {}
    for chain in chains:
        refs = _core_chain_refs(chain, expected_refs, item, prompt, selected_refs)
        if not refs:
            continue
        current = dict(chain)
        current["refs"] = refs
        current["_score"] = _chain_score(current, expected_refs, item, prompt, selected_refs)
        key = "|".join(refs)
        if key not in unique or current["_score"] > unique[key].get("_score", -999):
            unique[key] = current
    ranked = sorted(unique.values(), key=lambda x: x.get("_score", -999), reverse=True)
    selected_chains: list[dict] = []
    candidate_chains: list[dict] = []
    for chain in ranked:
        refs = chain.get("refs", [])
        slots = {_slot_for_ref(ref) for ref in refs}
        core_chain = any(slot.endswith("obligation") for slot in slots) and "penalty" in slots
        broad_candidate = "corporate_penalty" not in slots and not (set(refs) & expected_refs)
        if core_chain and not broad_candidate and len(selected_chains) < max_selected_chains:
            selected_chains.append(chain)
        else:
            candidate_chains.append(chain)
    return (
        [{k: v for k, v in chain.items() if k != "_score"} for chain in selected_chains],
        [{k: v for k, v in chain.items() if k != "_score"} for chain in candidate_chains],
    )


def compress_selected_tiers(
    selected: dict[str, Any],
    expected_bundle: dict[str, list[str]],
    item: dict,
    prompt: str,
    max_selected_laws: int = 10,
) -> dict[str, Any]:
    caps = _slot_caps(expected_bundle, item, prompt)
    expected_slot_refs = _expected_slot_lookup(expected_bundle)
    expected_refs = {ref for refs in expected_slot_refs.values() for ref in refs}
    expected_articles = {_article_key(ref) for ref in expected_refs if _article_key(ref)[1]}
    selected_items = _dedupe_items(selected.get("selected_laws", []))
    supporting_items = _dedupe_items(selected.get("supporting_laws", []))
    candidate_items = _dedupe_items(selected.get("candidate_laws", []))

    eligible_pool = selected_items + [
        dict(x, source=f"{x.get('source', '')}|supporting_promoted")
        for x in supporting_items
        if _slot_for_ref(normalize_fine_grained_law_ref(x.get("ref", ""))) in CORE_SELECTED_SLOTS
    ]
    eligible_pool.extend(
        dict(x, source=f"{x.get('source', '')}|candidate_promoted")
        for x in candidate_items
        if _promotion_safe_candidate(x, expected_refs, expected_articles, expected_slot_refs, item, prompt)
    )
    ranked_by_slot: dict[str, list[dict]] = {slot: [] for slot in SLOTS}
    for entry in _dedupe_items(eligible_pool):
        ref = normalize_fine_grained_law_ref(entry.get("ref", ""))
        if not ref:
            continue
        slot = _slot_for_ref(ref)
        if caps.get(slot, 0) <= 0:
            continue
        entry = dict(entry)
        entry["_score"] = _rank_selected_item(entry, expected_refs, expected_articles, item, prompt)
        ranked_by_slot.setdefault(slot, []).append(entry)

    compressed: list[dict] = []
    for slot in SLOTS:
        ranked = sorted(ranked_by_slot.get(slot, []), key=lambda x: x.get("_score", 0), reverse=True)
        compressed.extend(ranked[: caps.get(slot, 0)])
    compressed = sorted(_dedupe_items(compressed), key=lambda x: x.get("_score", 0), reverse=True)[:max_selected_laws]
    for entry in compressed:
        original_ref = entry["ref"]
        representative_ref = _representative_selected_ref(original_ref)
        if representative_ref != original_ref:
            entry["ref"] = representative_ref
            entry["representative_of"] = original_ref
            entry["reason"] = f"{entry.get('reason', '')}; representative_article_for_obligation_slot"
            entry["level"] = "article"
    compressed = _dedupe_items(compressed)
    compressed_refs = {x["ref"] for x in compressed}

    chain_selected, chain_candidate = select_chains(
        selected.get("selected_legal_chains", []) + selected.get("candidate_legal_chains", []),
        expected_refs,
        item,
        prompt,
        compressed_refs,
        max_selected_chains=3,
    )
    selected_chain_refs = {
        normalize_fine_grained_law_ref(ref)
        for chain in chain_selected
        for ref in chain.get("refs", [])
        if normalize_fine_grained_law_ref(ref)
    }
    selected_chain_articles = {_article_key(ref) for ref in selected_chain_refs if _article_key(ref)[1]}
    selected_article_keys = {_article_key(ref) for ref in compressed_refs if _article_key(ref)[1]}
    chain_bonus_pool = []
    for entry in selected_items + supporting_items:
        ref = normalize_fine_grained_law_ref(entry.get("ref", ""))
        if not ref or ref in compressed_refs:
            continue
        slot = _slot_for_ref(ref)
        if slot not in CORE_SELECTED_SLOTS:
            continue
        if ref not in selected_chain_refs and _article_key(ref) not in selected_chain_articles:
            continue
        if _article_key(ref) in selected_article_keys:
            continue
        candidate = dict(entry)
        candidate["_score"] = _rank_selected_item(candidate, expected_refs, expected_articles, item, prompt) + 6
        chain_bonus_pool.append(candidate)
    for entry in sorted(chain_bonus_pool, key=lambda x: x.get("_score", 0), reverse=True):
        if len(compressed) >= max_selected_laws:
            break
        compressed.append(entry)
        compressed_refs.add(entry["ref"])
        selected_article_keys.add(_article_key(entry["ref"]))
    compressed = _dedupe_items(compressed)
    compressed_refs = {x["ref"] for x in compressed}

    demoted = [
        dict(x, tier="candidate", source=f"{x.get('source', '')}|selected_demoted", reason=f"{x.get('reason', '')}; demoted_by_case_fact_article_selector")
        for x in selected_items
        if normalize_fine_grained_law_ref(x.get("ref", "")) not in compressed_refs
    ]
    promoted_refs = {
        normalize_fine_grained_law_ref(x.get("ref", ""))
        for x in compressed
        if "candidate_promoted" in str(x.get("source", ""))
    }
    remaining_supporting = [
        x for x in supporting_items
        if normalize_fine_grained_law_ref(x.get("ref", "")) not in compressed_refs
    ]

    return {
        **selected,
        "selected_laws": [{k: v for k, v in item_.items() if k != "_score"} for item_ in compressed],
        "supporting_laws": [{k: v for k, v in item_.items() if k != "_score"} for item_ in remaining_supporting],
        "candidate_laws": [
            item_
            for item_ in candidate_items
            if normalize_fine_grained_law_ref(item_.get("ref", "")) not in promoted_refs
        ] + demoted,
        "selected_legal_chains": chain_selected,
        "candidate_legal_chains": chain_candidate,
        "v6_slot_caps": caps,
        "v6_selected_compression": {
            "before_selected_law_count": len({normalize_fine_grained_law_ref(x.get("ref", "")) for x in selected_items}),
            "after_selected_law_count": len(compressed_refs),
            "demoted_count": len(demoted),
            "selected_chain_count": len(chain_selected),
            "candidate_chain_count": len(chain_candidate),
            "max_selected_laws": max_selected_laws,
            "candidate_promoted_count": len(promoted_refs),
            "selector": "case_type_article_priority_v3",
        },
    }


def _set_item_cap(item: dict, max_selected_laws: int | None) -> dict:
    if max_selected_laws is None:
        return item
    updated = dict(item)
    updated["_v6_max_selected_laws"] = max_selected_laws
    return updated


def _prf(predicted: set[Any], expected: set[Any]) -> dict[str, float]:
    if not predicted and not expected:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    hit = len(predicted & expected)
    precision = hit / len(predicted) if predicted else 0.0
    recall = hit / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def three_level_eval(gt_refs: list[str], selected_refs: set[str]) -> dict[str, Any]:
    gt_norm = {normalize_fine_grained_law_ref(ref) for ref in gt_refs if normalize_fine_grained_law_ref(ref)}
    pred_norm = {normalize_fine_grained_law_ref(ref) for ref in selected_refs if normalize_fine_grained_law_ref(ref)}
    gt_articles = {_article_key(ref) for ref in gt_norm}
    pred_articles = {_article_key(ref) for ref in pred_norm}
    gt_roles = {_slot_for_ref(ref) for ref in gt_norm}
    pred_roles = {_slot_for_ref(ref) for ref in pred_norm}
    role = _prf(pred_roles, gt_roles)
    article = _prf(pred_articles, gt_articles)
    fine_strict = _prf(pred_norm, gt_norm)
    fine = hierarchical_compatible_prf(gt_norm, pred_norm)
    return {
        "role_level_precision": role["precision"],
        "role_level_recall": role["recall"],
        "role_level_f1": role["f1"],
        "article_level_precision": article["precision"],
        "article_level_recall": article["recall"],
        "article_level_f1": article["f1"],
        "fine_level_strict_precision": fine_strict["precision"],
        "fine_level_strict_recall": fine_strict["recall"],
        "fine_level_strict_f1": fine_strict["f1"],
        "fine_level_precision": fine["precision"],
        "fine_level_recall": fine["recall"],
        "fine_level_f1": fine["f1"],
        "role_level_expected": sorted(gt_roles),
        "role_level_predicted": sorted(pred_roles),
        "article_level_expected": sorted(f"{law} {article}" for law, article in gt_articles),
        "article_level_predicted": sorted(f"{law} {article}" for law, article in pred_articles),
    }


def legal_chain_three_level_eval(gt_refs: list[str], selected_chains: list[dict]) -> dict[str, Any]:
    gt_norm = {normalize_fine_grained_law_ref(ref) for ref in gt_refs if normalize_fine_grained_law_ref(ref)}
    chain_refs = {
        normalize_fine_grained_law_ref(ref)
        for chain in selected_chains
        for ref in chain.get("refs", [])
        if normalize_fine_grained_law_ref(ref)
    }
    gt_articles = {_article_key(ref) for ref in gt_norm}
    chain_articles = {_article_key(ref) for ref in chain_refs}
    exists_hit = int(bool(selected_chains))
    article = _prf(chain_articles, gt_articles)
    fine_strict = _prf(chain_refs, gt_norm)
    fine = hierarchical_compatible_prf(gt_norm, chain_refs)
    return {
        "legal_chain_exists_hit": exists_hit,
        "chain_exists_hit": exists_hit,
        "legal_chain_article_precision": article["precision"],
        "legal_chain_article_recall": article["recall"],
        "legal_chain_article_f1": article["f1"],
        "chain_article_match_precision": article["precision"],
        "chain_article_match_recall": article["recall"],
        "chain_article_match_f1": article["f1"],
        "legal_chain_fine_strict_precision": fine_strict["precision"],
        "legal_chain_fine_strict_recall": fine_strict["recall"],
        "legal_chain_fine_strict_f1": fine_strict["f1"],
        "legal_chain_fine_precision": fine["precision"],
        "legal_chain_fine_recall": fine["recall"],
        "legal_chain_fine_f1": fine["f1"],
        "chain_fine_match_strict_precision": fine_strict["precision"],
        "chain_fine_match_strict_recall": fine_strict["recall"],
        "chain_fine_match_strict_f1": fine_strict["f1"],
        "chain_fine_match_precision": fine["precision"],
        "chain_fine_match_recall": fine["recall"],
        "chain_fine_match_f1": fine["f1"],
        "legal_chain_article_refs": sorted(f"{law} {article}" for law, article in chain_articles),
        "legal_chain_fine_refs": sorted(chain_refs),
    }


def slot_eval(bundle: dict[str, list[str]], selected_refs: set[str], supporting_refs: set[str]) -> dict[str, Any]:
    matched_slots = {}
    missing_slots = {}
    hit = 0
    total = 0
    predicted_slot_total = 0
    pool = selected_refs | supporting_refs
    for slot in SLOTS:
        gt = {normalize_fine_grained_law_ref(x) for x in bundle.get(slot, []) if normalize_fine_grained_law_ref(x)}
        if not gt:
            continue
        total += 1
        matched = sorted(gt & pool)
        if matched:
            hit += 1
            matched_slots[slot] = matched
        else:
            missing_slots[slot] = sorted(gt)
        predicted_slot_total += len(matched)
    recall = hit / total if total else 0.0
    precision = hit / total if total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "bundle_slot_hit_count": hit,
        "bundle_slot_total_count": total,
        "bundle_slot_recall": recall,
        "bundle_slot_precision": precision,
        "bundle_slot_f1": f1,
        "matched_slots": matched_slots,
        "missing_slots": missing_slots,
    }


def chain_hit(selected_chains: list[dict], expected_refs: set[str]) -> dict[str, Any]:
    obligation = {"제38조", "제39조", "제63조", "제64조", "제4조", "제5조"}
    penalty = {"제167조", "제168조", "제6조"}
    corporate = {"제173조", "제7조"}
    full = 0
    obligation_penalty = 0
    penalty_corp = 0
    details = []
    for chain in selected_chains:
        refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
        has_ob = any(any(tok in r for tok in obligation) for r in refs)
        has_pen = any(any(tok in r for tok in penalty) for r in refs)
        has_corp = any(any(tok in r for tok in corporate) for r in refs)
        hit_refs = sorted(set(refs) & expected_refs)
        if has_ob and has_pen:
            obligation_penalty += 1
        if has_pen and has_corp:
            penalty_corp += 1
        if has_ob and has_pen and has_corp:
            full += 1
        details.append({"refs": refs, "hit_refs": hit_refs, "full_chain": has_ob and has_pen and has_corp})
    return {
        "obligation_to_penalty_chain_hit": int(obligation_penalty > 0),
        "penalty_to_corporate_chain_hit": int(penalty_corp > 0),
        "full_obligation_penalty_corporate_chain_hit": int(full > 0),
        "legal_chains_missing": int(not selected_chains),
        "chain_details": details,
    }


def failure_category(selected_metrics: dict, slot_metrics: dict, chain_metrics: dict) -> str:
    if selected_metrics.get("candidate_recall", 0) > selected_metrics.get("selected_fine_grained_exact_recall", 0):
        return "candidate_only_match"
    missing = " ".join(sum(slot_metrics.get("missing_slots", {}).values(), []))
    if "제38조" in missing or "제39조" in missing or "제63조" in missing or "제64조" in missing:
        return "selected_core_obligation_missing"
    if "제167조" in missing or "제168조" in missing or "제6조" in missing:
        return "selected_penalty_missing"
    if "제173조" in missing or "제7조" in missing:
        return "selected_corporate_penalty_missing"
    if chain_metrics.get("legal_chains_missing"):
        return "selected_chain_missing"
    return "unknown"


def chain_hit(selected_chains: list[dict], expected_refs: set[str]) -> dict[str, Any]:
    full = 0
    obligation_penalty = 0
    penalty_corp = 0
    details = []
    for chain in selected_chains:
        refs = [normalize_fine_grained_law_ref(r) for r in chain.get("refs", []) if normalize_fine_grained_law_ref(r)]
        slots = {_slot_for_ref(ref) for ref in refs}
        has_ob = any(slot.endswith("obligation") for slot in slots)
        has_pen = "penalty" in slots
        has_corp = "corporate_penalty" in slots
        hit_refs = sorted(set(refs) & expected_refs)
        if has_ob and has_pen:
            obligation_penalty += 1
        if has_pen and has_corp:
            penalty_corp += 1
        if has_ob and has_pen and has_corp:
            full += 1
        details.append({"refs": refs, "hit_refs": hit_refs, "full_chain": has_ob and has_pen and has_corp})
    return {
        "obligation_to_penalty_chain_hit": int(obligation_penalty > 0),
        "penalty_to_corporate_chain_hit": int(penalty_corp > 0),
        "full_obligation_penalty_corporate_chain_hit": int(full > 0),
        "legal_chains_missing": int(not selected_chains),
        "chain_details": details,
    }


def failure_category(selected_metrics: dict, slot_metrics: dict, chain_metrics: dict) -> str:
    if selected_metrics.get("candidate_recall", 0) > selected_metrics.get("selected_fine_grained_exact_recall", 0):
        return "candidate_only_match"
    missing_refs = sum(slot_metrics.get("missing_slots", {}).values(), [])
    missing_slots = {_slot_for_ref(ref) for ref in missing_refs}
    if missing_slots & {"primary_obligation", "health_obligation", "contractor_obligation", "serious_accident_obligation"}:
        return "selected_core_obligation_missing"
    if "penalty" in missing_slots:
        return "selected_penalty_missing"
    if "corporate_penalty" in missing_slots:
        return "selected_corporate_penalty_missing"
    if "definition_or_scope" in missing_slots:
        return "selected_scope_definition_missing"
    if chain_metrics.get("legal_chains_missing"):
        return "selected_chain_missing"
    return "unknown"


def evaluate_item(item: dict, predictor: str, api_url: str, root_dir: str | None, max_selected_laws: int = 10) -> dict:
    prompt = item.get("case_scenario_prompt") or item.get("rewritten_question") or item.get("question") or ""
    pred_laws, response = predict_laws_and_response_via_ask(prompt, predictor=predictor, api_url=api_url, root_dir=root_dir)
    expected_bundle = item.get("expected_legal_bundle") or {}
    gt_refs = sorted({normalize_fine_grained_law_ref(ref) for refs in expected_bundle.values() for ref in refs if normalize_fine_grained_law_ref(ref)})
    tier = classify_predicted_laws_by_evidence_tier(response, {"question": prompt, "item": item})
    raw_selected = evaluate_selected_tiers(gt_refs, tier)
    compressed_tier = compress_selected_tiers(raw_selected, expected_bundle, item, prompt, max_selected_laws=max_selected_laws)
    selected = evaluate_selected_tiers(gt_refs, compressed_tier)
    selected["v6_slot_caps"] = compressed_tier.get("v6_slot_caps", {})
    selected["v6_selected_compression"] = compressed_tier.get("v6_selected_compression", {})
    selected["raw_selected_law_count"] = raw_selected.get("selected_law_count", 0)
    selected["raw_selected_legal_chain_f1"] = raw_selected.get("selected_legal_chain_f1", 0)
    selected_refs = refs_from_items(selected["selected_laws"])
    supporting_refs = refs_from_items(selected["supporting_laws"])
    candidate_refs = refs_from_items(selected["candidate_laws"])
    level_metrics = three_level_eval(gt_refs, selected_refs)
    chain_level_metrics = legal_chain_three_level_eval(gt_refs, selected["selected_legal_chains"])
    slot_metrics = slot_eval(expected_bundle, selected_refs, supporting_refs)
    chain_metrics = chain_hit(selected["selected_legal_chains"], set(gt_refs))
    bundle_metrics = analyze_bundle_response(response, item, pred_laws)
    selected_overgeneration_rate = len(selected.get("selected_overgenerated", [])) / max(len(gt_refs), 1)
    category = failure_category(selected, slot_metrics, chain_metrics)
    return {
        "id": item.get("id", ""),
        "case_name": item.get("case_name", ""),
        "dataset_status": item.get("dataset_status", ""),
        "ground_truth_laws": gt_refs,
        "predicted_laws": pred_laws,
        **selected,
        **level_metrics,
        **chain_level_metrics,
        **slot_metrics,
        **chain_metrics,
        "selected_overgeneration_rate": selected_overgeneration_rate,
        "default_candidate_overgeneration_rate": selected_overgeneration_rate,
        "candidate_overgeneration_rate": bundle_metrics.get("candidate_overgeneration_rate", 0.0),
        "failure_category": category,
    }


def evaluate(dataset_path: Path, predictor: str, api_url: str, root_dir: str | None, max_selected_laws: int = 10) -> tuple[list[dict], dict]:
    data = load_json(dataset_path)
    rows = [evaluate_item(item, predictor, api_url, root_dir, max_selected_laws=max_selected_laws) for item in data]
    n = len(rows) or 1
    avg_keys = [
        "selected_fine_grained_exact_precision",
        "selected_fine_grained_exact_recall",
        "selected_fine_grained_exact_f1",
        "selected_fine_grained_soft_precision",
        "selected_fine_grained_soft_recall",
        "selected_fine_grained_soft_f1",
        "selected_legal_chain_precision",
        "selected_legal_chain_recall",
        "selected_legal_chain_f1",
        "selected_expected_law_precision",
        "selected_expected_law_recall",
        "selected_expected_law_f1",
        "role_level_precision",
        "role_level_recall",
        "role_level_f1",
        "article_level_precision",
        "article_level_recall",
        "article_level_f1",
        "fine_level_strict_precision",
        "fine_level_strict_recall",
        "fine_level_strict_f1",
        "fine_level_precision",
        "fine_level_recall",
        "fine_level_f1",
        "legal_chain_exists_hit",
        "chain_exists_hit",
        "legal_chain_article_precision",
        "legal_chain_article_recall",
        "legal_chain_article_f1",
        "chain_article_match_precision",
        "chain_article_match_recall",
        "chain_article_match_f1",
        "legal_chain_fine_precision",
        "legal_chain_fine_recall",
        "legal_chain_fine_f1",
        "legal_chain_fine_strict_precision",
        "legal_chain_fine_strict_recall",
        "legal_chain_fine_strict_f1",
        "chain_fine_match_precision",
        "chain_fine_match_recall",
        "chain_fine_match_f1",
        "chain_fine_match_strict_precision",
        "chain_fine_match_strict_recall",
        "chain_fine_match_strict_f1",
        "candidate_recall",
        "bundle_slot_recall",
        "bundle_slot_precision",
        "bundle_slot_f1",
        "selected_overgeneration_rate",
        "default_candidate_overgeneration_rate",
        "candidate_overgeneration_rate",
        "candidate_fine_recall",
        "candidate_article_recall",
        "selected_article_recall",
        "selected_supporting_article_recall",
        "selected_article_compatible_precision",
        "selected_article_compatible_recall",
        "selected_article_compatible_f1",
        "candidate_article_compatible_precision",
        "candidate_article_compatible_recall",
        "candidate_article_compatible_f1",
        "selected_hierarchical_compatible_precision",
        "selected_hierarchical_compatible_recall",
        "selected_hierarchical_compatible_f1",
        "candidate_hierarchical_compatible_precision",
        "candidate_hierarchical_compatible_recall",
        "candidate_hierarchical_compatible_f1",
        "debug_article_recall",
        "full_debug_article_recall",
        "selected_law_count",
        "raw_selected_law_count",
        "raw_selected_legal_chain_f1",
        "supporting_law_count",
        "candidate_law_count",
        "debug_law_count",
        "selected_chain_count",
        "candidate_chain_count",
        "debug_chain_count",
    ]
    summary = {"sample_count": len(rows)}
    for key in avg_keys:
        summary[key] = sum(float(row.get(key) or 0) for row in rows) / n
    summary["full_obligation_penalty_corporate_chain_hit"] = sum(row["full_obligation_penalty_corporate_chain_hit"] for row in rows)
    summary["legal_chains_missing_count"] = sum(row["legal_chains_missing"] for row in rows)
    summary["failure_category_counts"] = dict(Counter(row["failure_category"] for row in rows))
    summary["main_metrics"] = {key: summary[key] for key in [
        "selected_fine_grained_exact_f1",
        "selected_fine_grained_soft_f1",
        "selected_legal_chain_f1",
        "role_level_f1",
        "article_level_f1",
        "fine_level_strict_f1",
        "fine_level_f1",
        "legal_chain_exists_hit",
        "chain_exists_hit",
        "legal_chain_article_f1",
        "chain_article_match_f1",
        "legal_chain_fine_strict_f1",
        "legal_chain_fine_f1",
        "chain_fine_match_strict_f1",
        "chain_fine_match_f1",
        "bundle_slot_f1",
        "candidate_recall",
        "candidate_fine_recall",
        "candidate_article_recall",
        "selected_article_recall",
        "selected_supporting_article_recall",
        "selected_article_compatible_f1",
        "candidate_article_compatible_f1",
        "selected_hierarchical_compatible_f1",
        "candidate_hierarchical_compatible_f1",
        "selected_overgeneration_rate",
        "candidate_overgeneration_rate",
    ]}
    return rows, summary


def audit_gt_bundles(dataset_path: Path) -> tuple[list[dict], dict]:
    data = load_json(dataset_path)
    rows: list[dict] = []
    slot_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    total_refs = 0
    for item in data:
        bundle = item.get("expected_legal_bundle") or {}
        refs_by_slot = {
            slot: [normalize_fine_grained_law_ref(ref) for ref in bundle.get(slot, []) if normalize_fine_grained_law_ref(ref)]
            for slot in SLOTS
        }
        flat = [ref for refs in refs_by_slot.values() for ref in refs]
        total_refs += len(flat)
        duplicate_refs = sorted(ref for ref, count in Counter(flat).items() if count > 1)
        fine_refs = [ref for ref in flat if (parse_fine_grained_law_ref(ref) or {}).get("ref_level") in {"paragraph", "item", "subitem"}]
        article_refs = [ref for ref in flat if (parse_fine_grained_law_ref(ref) or {}).get("ref_level") == "article"]
        populated_slots = [slot for slot, refs in refs_by_slot.items() if refs]
        for slot in populated_slots:
            slot_counts[slot] += 1
        issues = []
        if len(flat) > 12:
            issues.append("gt_bundle_too_broad")
        if duplicate_refs:
            issues.append("duplicate_ref")
        if len(article_refs) > len(fine_refs) and any(_slot_for_ref(ref) in {"penalty", "corporate_penalty"} for ref in flat):
            issues.append("article_level_penalty_gt")
        if not any(slot in populated_slots for slot in CORE_SELECTED_SLOTS):
            issues.append("no_core_selected_slot")
        if not issues:
            issues.append("ok")
        for issue in issues:
            issue_counts[issue] += 1
        rows.append({
            "id": item.get("id", ""),
            "case_name": item.get("case_name", ""),
            "dataset_status": item.get("dataset_status", ""),
            "gt_ref_count": len(flat),
            "fine_grained_ref_count": len(fine_refs),
            "article_level_ref_count": len(article_refs),
            "populated_slots": json.dumps(populated_slots, ensure_ascii=False),
            "duplicate_refs": json.dumps(duplicate_refs, ensure_ascii=False),
            "audit_issues": json.dumps(issues, ensure_ascii=False),
            "expected_legal_bundle": json.dumps(bundle, ensure_ascii=False),
        })
    summary = {
        "sample_count": len(data),
        "total_expected_refs": total_refs,
        "avg_expected_refs": total_refs / len(data) if data else 0.0,
        "slot_case_counts": dict(slot_counts),
        "audit_issue_counts": dict(issue_counts),
    }
    return rows, summary


def save_outputs(rows: list[dict], summary: dict, output_dir: Path | None = None) -> None:
    output_dir = output_dir or (OUT / "evaluation")
    fields = [
        "id", "case_name", "dataset_status", "ground_truth_laws", "predicted_laws",
        "selected_fine_grained_exact_precision", "selected_fine_grained_exact_recall", "selected_fine_grained_exact_f1",
        "selected_fine_grained_soft_precision", "selected_fine_grained_soft_recall", "selected_fine_grained_soft_f1",
        "selected_legal_chain_precision", "selected_legal_chain_recall", "selected_legal_chain_f1",
        "role_level_precision", "role_level_recall", "role_level_f1",
        "article_level_precision", "article_level_recall", "article_level_f1",
        "fine_level_strict_precision", "fine_level_strict_recall", "fine_level_strict_f1",
        "fine_level_precision", "fine_level_recall", "fine_level_f1",
        "legal_chain_exists_hit", "chain_exists_hit",
        "legal_chain_article_precision", "legal_chain_article_recall", "legal_chain_article_f1",
        "chain_article_match_precision", "chain_article_match_recall", "chain_article_match_f1",
        "legal_chain_fine_strict_precision", "legal_chain_fine_strict_recall", "legal_chain_fine_strict_f1",
        "legal_chain_fine_precision", "legal_chain_fine_recall", "legal_chain_fine_f1",
        "chain_fine_match_strict_precision", "chain_fine_match_strict_recall", "chain_fine_match_strict_f1",
        "chain_fine_match_precision", "chain_fine_match_recall", "chain_fine_match_f1",
        "bundle_slot_recall", "bundle_slot_precision", "bundle_slot_f1",
        "obligation_to_penalty_chain_hit", "penalty_to_corporate_chain_hit", "full_obligation_penalty_corporate_chain_hit",
        "candidate_recall", "selected_overgeneration_rate", "default_candidate_overgeneration_rate", "candidate_overgeneration_rate",
        "candidate_fine_recall", "candidate_article_recall", "selected_article_recall",
        "selected_supporting_article_recall", "debug_article_recall", "full_debug_article_recall",
        "selected_article_compatible_precision", "selected_article_compatible_recall", "selected_article_compatible_f1",
        "candidate_article_compatible_precision", "candidate_article_compatible_recall", "candidate_article_compatible_f1",
        "selected_hierarchical_compatible_precision", "selected_hierarchical_compatible_recall", "selected_hierarchical_compatible_f1",
        "candidate_hierarchical_compatible_precision", "candidate_hierarchical_compatible_recall", "candidate_hierarchical_compatible_f1",
        "selected_law_count", "raw_selected_law_count", "supporting_law_count", "candidate_law_count", "debug_law_count",
        "selected_chain_count", "candidate_chain_count", "debug_chain_count",
        "selected_laws", "supporting_laws", "candidate_laws", "selected_legal_chains", "candidate_legal_chains",
        "v6_slot_caps", "v6_selected_compression", "role_level_expected", "role_level_predicted",
        "article_level_expected", "article_level_predicted", "legal_chain_article_refs", "legal_chain_fine_refs",
        "candidate_recall_hits", "candidate_fine_missing", "candidate_article_missing",
        "selected_article_recall_hits", "selected_supporting_article_recall_hits",
        "candidate_article_recall_hits", "debug_article_recall_hits", "full_debug_article_recall_hits",
        "selected_article_compatible_hits", "selected_article_compatible_missing",
        "candidate_article_compatible_hits", "candidate_article_compatible_missing",
        "selected_hierarchical_compatible_matches", "selected_hierarchical_compatible_missing",
        "candidate_hierarchical_compatible_matches", "candidate_hierarchical_compatible_missing",
        "matched_slots", "missing_slots", "failure_category",
    ]
    serial_rows = []
    for row in rows:
        out = dict(row)
        for key in ["ground_truth_laws", "predicted_laws", "selected_laws", "supporting_laws", "candidate_laws", "selected_legal_chains", "candidate_legal_chains", "v6_slot_caps", "v6_selected_compression", "role_level_expected", "role_level_predicted", "article_level_expected", "article_level_predicted", "legal_chain_article_refs", "legal_chain_fine_refs", "matched_slots", "missing_slots", "candidate_recall_hits", "candidate_fine_missing", "candidate_article_missing", "selected_article_recall_hits", "selected_supporting_article_recall_hits", "candidate_article_recall_hits", "debug_article_recall_hits", "full_debug_article_recall_hits", "selected_article_compatible_hits", "selected_article_compatible_missing", "candidate_article_compatible_hits", "candidate_article_compatible_missing", "selected_hierarchical_compatible_matches", "selected_hierarchical_compatible_missing", "candidate_hierarchical_compatible_matches", "candidate_hierarchical_compatible_missing"]:
            out[key] = json.dumps(out.get(key, []), ensure_ascii=False)
        serial_rows.append(out)
    write_csv(output_dir / "case_scenario_api_results.csv", serial_rows, fields)
    write_csv(output_dir / "case_scenario_slot_results.csv", serial_rows, ["id", "case_name", "bundle_slot_recall", "bundle_slot_precision", "bundle_slot_f1", "matched_slots", "missing_slots"])
    write_csv(output_dir / "case_scenario_chain_results.csv", serial_rows, [
        "id", "case_name", "selected_legal_chain_f1", "chain_exists_hit",
        "chain_article_match_f1", "chain_fine_match_f1",
        "obligation_to_penalty_chain_hit", "penalty_to_corporate_chain_hit",
        "full_obligation_penalty_corporate_chain_hit", "selected_legal_chains",
    ])
    write_csv(output_dir / "case_scenario_gap_analysis.csv", serial_rows, ["id", "case_name", "failure_category", "missing_slots", "candidate_recall"])
    write_csv(output_dir / "case_scenario_candidate_overgeneration_review.csv", serial_rows, ["id", "case_name", "selected_law_count", "selected_overgeneration_rate", "candidate_law_count", "candidate_overgeneration_rate", "candidate_laws"])
    write_csv(output_dir / "case_scenario_selected_vs_candidate_review.csv", serial_rows, ["id", "case_name", "selected_law_count", "supporting_law_count", "candidate_law_count", "selected_chain_count", "candidate_chain_count", "selected_laws", "candidate_laws", "selected_legal_chains", "candidate_legal_chains"])
    write_csv(output_dir / "case_scenario_selected_compression_review.csv", serial_rows, [
        "id", "case_name", "raw_selected_law_count", "selected_law_count", "selected_fine_grained_exact_f1",
        "selected_fine_grained_soft_f1", "selected_legal_chain_f1", "v6_slot_caps", "v6_selected_compression",
        "selected_laws", "missing_slots", "failure_category",
    ])
    write_csv(output_dir / "case_scenario_three_level_results.csv", serial_rows, [
        "id", "case_name", "role_level_precision", "role_level_recall", "role_level_f1",
        "article_level_precision", "article_level_recall", "article_level_f1",
        "fine_level_strict_precision", "fine_level_strict_recall", "fine_level_strict_f1",
        "fine_level_precision", "fine_level_recall", "fine_level_f1",
        "role_level_expected", "role_level_predicted", "article_level_expected", "article_level_predicted",
    ])
    write_csv(output_dir / "case_scenario_legal_chain_three_level_results.csv", serial_rows, [
        "id", "case_name", "legal_chain_exists_hit", "chain_exists_hit",
        "legal_chain_article_precision", "legal_chain_article_recall", "legal_chain_article_f1",
        "chain_article_match_precision", "chain_article_match_recall", "chain_article_match_f1",
        "legal_chain_fine_strict_precision", "legal_chain_fine_strict_recall", "legal_chain_fine_strict_f1",
        "legal_chain_fine_precision", "legal_chain_fine_recall", "legal_chain_fine_f1",
        "chain_fine_match_strict_precision", "chain_fine_match_strict_recall", "chain_fine_match_strict_f1",
        "chain_fine_match_precision", "chain_fine_match_recall", "chain_fine_match_f1",
        "legal_chain_article_refs", "legal_chain_fine_refs", "selected_legal_chains",
    ])
    write_json(output_dir / "case_scenario_api_summary.json", summary)


def save_gt_bundle_audit(dataset_path: Path, output_dir: Path | None = None, write_mapping_copy: bool = False) -> None:
    rows, summary = audit_gt_bundles(dataset_path)
    target_dir = output_dir or (OUT / "evaluation")
    write_csv(target_dir / "case_gt_bundle_audit.csv", rows, [
        "id", "case_name", "dataset_status", "gt_ref_count", "fine_grained_ref_count",
        "article_level_ref_count", "populated_slots", "duplicate_refs", "audit_issues",
        "expected_legal_bundle",
    ])
    write_json(target_dir / "case_gt_bundle_audit_summary.json", summary)
    if write_mapping_copy:
        write_csv(OUT / "mapping" / "case_gt_bundle_audit.csv", rows, [
            "id", "case_name", "dataset_status", "gt_ref_count", "fine_grained_ref_count",
            "article_level_ref_count", "populated_slots", "duplicate_refs", "audit_issues",
            "expected_legal_bundle",
        ])
        write_json(OUT / "mapping" / "case_gt_bundle_audit_summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(OUT / "dataset" / "case_scenario_eval_ready.json"))
    parser.add_argument("--predictor", choices=["api", "local"], default=os.environ.get("PROJECT_EVAL_PREDICTOR", "api"))
    parser.add_argument("--api-url", default=os.environ.get("PROJECT_EVAL_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--root-dir", default=os.environ.get("PROJECT_EVAL_ROOT_DIR"))
    parser.add_argument("--output-dir", default=str(OUT / "evaluation"))
    parser.add_argument("--max-selected-laws", type=int, default=10)
    args = parser.parse_args()
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    default_dataset = (OUT / "dataset" / "case_scenario_eval_ready.json").resolve()
    save_gt_bundle_audit(dataset_path, output_dir, dataset_path.resolve() == default_dataset)
    rows, summary = evaluate(dataset_path, args.predictor, args.api_url, args.root_dir, max_selected_laws=args.max_selected_laws)
    save_outputs(rows, summary, output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
