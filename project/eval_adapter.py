"""Compatibility helpers for evaluating the existing Graph-RAG answer shape.

The production /ask response already exposes citations, evidences,
evidence_chips, and optionally evidence_pack.  This module reads those fields
and converts them into the simple "law string list" expected by the project
evaluation scripts, without changing the answer API itself.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib import request as urlrequest


LAW_PATTERN = re.compile(
    r"(산업안전보건기준에\s*관한\s*규칙|산업안전보건법\s*시행규칙|"
    r"중대재해처벌법\s*시행령|중대재해\s*처벌\s*등에\s*관한\s*법률\s*시행령|"
    r"산업안전보건법|중대재해처벌법|중대재해\s*처벌\s*등에\s*관한\s*법률)"
    r"\s*제?\s*(\d+)조(?:\s*제?\s*(\d+)항)?"
)


def normalize_law_name(law: str) -> str:
    if not law:
        return ""
    law = re.sub(r"\s+", " ", str(law)).strip()
    law = law.replace("중대재해 처벌 등에 관한 법률", "중대재해처벌법")
    law = law.replace("중대재해 처벌등에관한법률", "중대재해처벌법")
    law = law.replace("중대재해처벌 등에 관한 법률", "중대재해처벌법")
    law = law.replace("산업안전보건 법", "산업안전보건법")
    law = re.sub(r"\s*제\s*", " 제", law)
    law = re.sub(r"\s*조\s*", "조 ", law)
    law = re.sub(r"\s*항\s*", "항 ", law)
    return re.sub(r"\s+", " ", law).strip()


def normalize_law_list(laws: list[str]) -> list[str]:
    return normalize_law_refs(laws)


LAW_NAME_ALIASES = (
    ("중대재해 처벌 등에 관한 법률 시행령", "중대재해처벌법 시행령"),
    ("중대재해처벌 등에 관한 법률 시행령", "중대재해처벌법 시행령"),
    ("중대재해 처벌 등에 관한 법률", "중대재해처벌법"),
    ("중대재해처벌 등에 관한 법률", "중대재해처벌법"),
    ("중대재해 처벌등에관한법률", "중대재해처벌법"),
    ("산업 안전 보건 기준에 관한 규칙", "산업안전보건기준에 관한 규칙"),
    ("산업안전보건 기준에 관한 규칙", "산업안전보건기준에 관한 규칙"),
    ("산업안전 보건기준에 관한 규칙", "산업안전보건기준에 관한 규칙"),
    ("산업안전 보건법 시행규칙", "산업안전보건법 시행규칙"),
    ("산업안전보건 시행규칙", "산업안전보건법 시행규칙"),
    ("산업안전 보건법", "산업안전보건법"),
)

CANONICAL_LAW_NAMES = (
    "산업안전보건기준에 관한 규칙",
    "산업안전보건법 시행규칙",
    "중대재해처벌법 시행령",
    "산업안전보건법",
    "중대재해처벌법",
)

EVALUATION_POLICY = (
    "Soft match is an auxiliary evaluation based on generalized law hierarchy "
    "patterns. It is not a final legal determination and does not replace exact "
    "match metrics."
)


def normalize_law_ref(text: Any) -> str:
    """Normalize a law reference string while keeping article structure."""

    if not text:
        return ""
    value = str(text)
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[()\[\]{},;:]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    for source, target in LAW_NAME_ALIASES:
        value = value.replace(source, target)
    value = value.replace("제 ", "제")
    value = re.sub(r"제\s*(\d+)\s*조", r"제\1조", value)
    value = re.sub(r"제\s*(\d+)\s*항", r"제\1항", value)
    value = re.sub(r"제\s*(\d+)\s*호", r"제\1호", value)
    value = re.sub(r"(조|항)(제)", r"\1 \2", value)
    parsed = parse_law_ref(value)
    if not parsed:
        return normalize_law_name(value)
    parts = [parsed["law_name"]]
    if parsed.get("article_no"):
        parts.append(f"제{parsed['article_no']}조")
    if parsed.get("paragraph_no"):
        parts.append(f"제{parsed['paragraph_no']}항")
    if parsed.get("item_no"):
        parts.append(f"제{parsed['item_no']}호")
    return " ".join(parts)


def normalize_law_refs(laws: list[str]) -> list[str]:
    normalized: list[str] = []
    for law in laws:
        cleaned = normalize_law_ref(law)
        if cleaned:
            normalized.append(cleaned)
    return list(dict.fromkeys(normalized))


def parse_law_ref(text: Any) -> dict[str, Any] | None:
    """Parse a law reference into law name, article, paragraph, and item."""

    if not text:
        return None
    value = str(text)
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[()\[\]{},;:]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    for source, target in LAW_NAME_ALIASES:
        value = value.replace(source, target)
    value = re.sub(r"\s+", " ", value).strip()

    law_name = ""
    for candidate in CANONICAL_LAW_NAMES:
        if candidate in value:
            law_name = candidate
            break
    if not law_name:
        return None

    article_match = re.search(r"제\s*(\d+(?:의\d+)?)\s*조", value)
    paragraph_match = re.search(r"제\s*(\d+)\s*항", value)
    item_match = re.search(r"제\s*(\d+)\s*호", value)
    return {
        "law_name": law_name,
        "article_no": article_match.group(1) if article_match else "",
        "paragraph_no": paragraph_match.group(1) if paragraph_match else "",
        "item_no": item_match.group(1) if item_match else "",
        "raw": str(text),
        "normalized": "",
    }


def classify_law_role(ref: dict[str, Any] | None) -> str:
    if not ref:
        return "unknown"
    law_name = ref.get("law_name", "")
    article = str(ref.get("article_no", ""))
    if law_name in {"산업안전보건기준에 관한 규칙", "산업안전보건법 시행규칙", "중대재해처벌법 시행령"}:
        return "detail_rule"
    if law_name == "중대재해처벌법":
        if article in {"6", "7"}:
            return "penalty"
        if article == "4":
            return "obligation"
        if article in {"1", "2", "3"}:
            return "definition_or_scope"
        return "serious_accident"
    if law_name == "산업안전보건법":
        if article in {"167", "173"}:
            return "penalty"
        if article in {"38", "39", "63", "64"}:
            return "obligation"
        if article in {"1", "2", "3", "4"}:
            return "definition_or_scope"
        return "obligation"
    return "unknown"


def _is_safety_detail_rule(ref: dict[str, Any]) -> bool:
    return ref.get("law_name") in {"산업안전보건기준에 관한 규칙", "산업안전보건법 시행규칙"}


def _is_serious_accident_decree(ref: dict[str, Any], articles: set[str] | None = None) -> bool:
    if ref.get("law_name") != "중대재해처벌법 시행령":
        return False
    return articles is None or str(ref.get("article_no", "")) in articles


def relation_match(gt_ref: dict[str, Any] | None, pred_ref: dict[str, Any] | None) -> tuple[str, float]:
    """Return the best relation type and score for one GT/predicted pair."""

    if not gt_ref or not pred_ref:
        return "no_match", 0.0

    gt_law = gt_ref.get("law_name", "")
    pred_law = pred_ref.get("law_name", "")
    gt_article = str(gt_ref.get("article_no", ""))
    pred_article = str(pred_ref.get("article_no", ""))
    gt_para = str(gt_ref.get("paragraph_no", ""))
    pred_para = str(pred_ref.get("paragraph_no", ""))

    if gt_law == pred_law and gt_article == pred_article and gt_para == pred_para:
        return "exact", 1.0
    if gt_law == pred_law and gt_article and gt_article == pred_article:
        return "article", 0.8

    if gt_law == "산업안전보건법" and gt_article in {"38", "39"}:
        if pred_law == "산업안전보건기준에 관한 규칙":
            return "parent_child", 0.6
    if gt_law == "산업안전보건법" and gt_article in {"63", "64"}:
        if _is_safety_detail_rule(pred_ref):
            return "parent_child", 0.6
    if gt_law == "중대재해처벌법" and gt_article == "4":
        if _is_serious_accident_decree(pred_ref, {"4", "5", "9"}):
            return "parent_child", 0.6

    if gt_law == "산업안전보건법" and gt_article in {"167", "173"}:
        if pred_law == "산업안전보건법" and pred_article in {"38", "39", "63", "64"}:
            return "penalty_relation", 0.4
        if pred_law == "산업안전보건기준에 관한 규칙":
            return "penalty_relation", 0.4
    if gt_law == "중대재해처벌법" and gt_article in {"6", "7"}:
        if pred_law == "중대재해처벌법" and pred_article == "4":
            return "penalty_relation", 0.4
        if _is_serious_accident_decree(pred_ref, {"4", "5", "9"}):
            return "penalty_relation", 0.4

    if gt_law == pred_law:
        return "law_name_only", 0.2
    return "no_match", 0.0


def evaluate_soft_matches(gt_laws: list[str], pred_laws: list[str]) -> dict[str, Any]:
    """Greedy one-to-one soft evaluation for law hierarchy aware matching."""

    gt_norm = normalize_law_refs(gt_laws)
    pred_norm = normalize_law_refs(pred_laws)
    gt_refs = [parse_law_ref(law) for law in gt_norm]
    pred_refs = [parse_law_ref(law) for law in pred_norm]
    used_pred_indexes: set[int] = set()
    matches: list[dict[str, Any]] = []

    for gt_index, gt_ref in enumerate(gt_refs):
        best: tuple[float, int, str] = (0.0, -1, "no_match")
        for pred_index, pred_ref in enumerate(pred_refs):
            if pred_index in used_pred_indexes:
                continue
            relation_type, score = relation_match(gt_ref, pred_ref)
            if score > best[0]:
                best = (score, pred_index, relation_type)
        if best[0] > 0 and best[1] >= 0:
            used_pred_indexes.add(best[1])
            matches.append(
                {
                    "gt": gt_norm[gt_index],
                    "pred": pred_norm[best[1]],
                    "relation_type": best[2],
                    "score": best[0],
                    "gt_role": classify_law_role(gt_ref),
                    "pred_role": classify_law_role(pred_refs[best[1]]),
                }
            )

    relation_counts = {
        "exact": 0,
        "article": 0,
        "parent_child": 0,
        "penalty_relation": 0,
        "law_name_only": 0,
    }
    for match in matches:
        relation_type = match["relation_type"]
        if relation_type in relation_counts:
            relation_counts[relation_type] += 1

    matched_gt = {match["gt"] for match in matches}
    matched_pred = {match["pred"] for match in matches}
    unmatched_gt = [law for law in gt_norm if law not in matched_gt]
    unmatched_pred = [law for law in pred_norm if law not in matched_pred]
    total_score = sum(float(match["score"]) for match in matches)
    soft_precision = total_score / len(pred_norm) if pred_norm else 0.0
    soft_recall = total_score / len(gt_norm) if gt_norm else 0.0
    soft_f1 = (
        2 * soft_precision * soft_recall / (soft_precision + soft_recall)
        if (soft_precision + soft_recall) > 0
        else 0.0
    )
    weighted_score = total_score / max(len(gt_norm), len(pred_norm), 1)

    return {
        "ground_truth_laws": gt_norm,
        "predicted_laws": pred_norm,
        "soft_precision": soft_precision,
        "soft_recall": soft_recall,
        "soft_f1": soft_f1,
        "weighted_score": weighted_score,
        "exact_matches": [m for m in matches if m["relation_type"] == "exact"],
        "article_matches": [m for m in matches if m["relation_type"] == "article"],
        "parent_child_matches": [m for m in matches if m["relation_type"] == "parent_child"],
        "penalty_relation_matches": [m for m in matches if m["relation_type"] == "penalty_relation"],
        "law_name_only_matches": [m for m in matches if m["relation_type"] == "law_name_only"],
        "unmatched_ground_truth": unmatched_gt,
        "unmatched_predictions": unmatched_pred,
        "match_details": matches,
        "relation_counts": relation_counts,
    }


def extract_laws_from_text(text: Any) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    laws: list[str] = []
    for law_name, article_no, paragraph_no in LAW_PATTERN.findall(text):
        law = f"{law_name} 제{article_no}조"
        if paragraph_no:
            law += f" 제{paragraph_no}항"
        laws.append(law)
    return normalize_law_list(laws)


def _law_from_mapping(item: dict[str, Any]) -> list[str]:
    laws: list[str] = []
    law_name = item.get("law_name") or item.get("law")
    article_no = item.get("article_no") or item.get("article")
    if law_name and article_no:
        laws.append(f"{law_name} {article_no}")

    for field in (
        "citation_text",
        "title",
        "law_title",
        "source_text_preview",
        "preview",
        "source_text",
        "text",
        "article_text",
    ):
        laws.extend(extract_laws_from_text(item.get(field)))
    return laws


def _walk_response(value: Any) -> list[str]:
    laws: list[str] = []
    if isinstance(value, dict):
        laws.extend(_law_from_mapping(value))
        for child in value.values():
            if isinstance(child, (dict, list)):
                laws.extend(_walk_response(child))
    elif isinstance(value, list):
        for child in value:
            laws.extend(_walk_response(child))
    elif isinstance(value, str):
        laws.extend(extract_laws_from_text(value))
    return laws


def extract_laws_from_ask_response(response: dict[str, Any]) -> list[str]:
    """Extract law/article strings from the current /ask response contract."""

    fields = (
        "citations",
        "evidences",
        "evidence_chips",
        "evidence_pack",
        "claim_check",
    )
    laws: list[str] = []
    for field in fields:
        laws.extend(_walk_response(response.get(field)))
    if not laws:
        laws.extend(extract_laws_from_text(response.get("answer")))
    return normalize_law_list(laws)


def build_keyword_question(keywords: list[str]) -> str:
    keyword_text = ", ".join(str(keyword) for keyword in keywords if keyword)
    return f"{keyword_text} 관련 산업안전보건 법령 근거는 무엇인가요?"


def ask_via_api(question: str, api_url: str | None = None) -> dict[str, Any]:
    base_url = (api_url or os.environ.get("PROJECT_EVAL_API_URL") or "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "question": question,
        "mode": "qa",
        "chat_history": [],
        "options": {"include_evidence": True, "include_debug": True},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        f"{base_url}/ask",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=60) as response:  # noqa: S310 - local/dev eval endpoint
        return json.loads(response.read().decode("utf-8"))


def ask_via_local_adapter(question: str, root_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(root_dir or os.environ.get("PROJECT_EVAL_ROOT_DIR") or Path(__file__).resolve().parents[1]).resolve()
    code_dir = root / "05_code"
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))
    from graph_rag_pipeline.ask_adapter import ask_graph_rag

    return ask_graph_rag(
        {
            "question": question,
            "mode": "qa",
            "chat_history": [],
            "options": {"include_evidence": True, "include_debug": True},
        },
        root,
    )


def predict_laws_via_ask(
    question: str,
    predictor: str = "api",
    api_url: str | None = None,
    root_dir: str | Path | None = None,
) -> list[str]:
    if predictor == "local":
        response = ask_via_local_adapter(question, root_dir)
    elif predictor == "api":
        response = ask_via_api(question, api_url)
    else:
        raise ValueError(f"unsupported /ask predictor: {predictor}")
    return extract_laws_from_ask_response(response)


def predict_laws_and_response_via_ask(
    question: str,
    predictor: str = "api",
    api_url: str | None = None,
    root_dir: str | Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    if predictor == "local":
        response = ask_via_local_adapter(question, root_dir)
    elif predictor == "api":
        response = ask_via_api(question, api_url)
    else:
        raise ValueError(f"unsupported /ask predictor: {predictor}")
    return extract_laws_from_ask_response(response), response


FINE_CIRCLED_PARAGRAPHS = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5, "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9, "⑩": 10}


def _fine_law_name(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    if "중대재해" in text and "시행령" not in text:
        return "중대재해처벌법"
    if "산업안전보건법" in text and "시행" not in text and "기준" not in text:
        return "산업안전보건법"
    if "산업안전보건기준" in text:
        return "산업안전보건기준에 관한 규칙"
    if "산업안전보건법시행규칙" in text:
        return "산업안전보건법 시행규칙"
    return str(value or "").strip()


def _fine_article(value: Any) -> str:
    match = re.search(r"(\d+(?:의\d+)?)", str(value or ""))
    return f"제{match.group(1)}조" if match else ""


def _fine_paragraph(value: Any) -> str:
    text = str(value or "").strip()
    if text in FINE_CIRCLED_PARAGRAPHS:
        return f"제{FINE_CIRCLED_PARAGRAPHS[text]}항"
    match = re.search(r"제?\s*(\d+)\s*항", text)
    return f"제{match.group(1)}항" if match else ""


def _fine_item(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"제?\s*(\d+)\s*호", text)
    return f"제{match.group(1)}호" if match else ""


def _fine_subitem(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"([가-하])\s*목", text)
    return f"{match.group(1)}목" if match else ""


def parse_fine_grained_law_ref(text: Any) -> dict[str, Any] | None:
    value = str(text or "").replace("\u00a0", " ")
    value = value.replace("중대재해 처벌 등에 관한 법률", "중대재해처벌법")
    value = value.replace("중대재해처벌 등에 관한 법률", "중대재해처벌법")
    value = value.replace("산업안전 보건법", "산업안전보건법")
    law_name = ""
    for candidate in [
        "산업안전보건기준에 관한 규칙",
        "산업안전보건법 시행규칙",
        "산업안전보건법 시행령",
        "중대재해처벌법 시행령",
        "산업안전보건법",
        "중대재해처벌법",
    ]:
        if re.sub(r"\s+", "", candidate) in re.sub(r"\s+", "", value):
            law_name = candidate
            break
    if not law_name:
        return None
    compact = re.sub(r"\s+", "", value)
    article = re.search(r"제(\d+(?:의\d+)?)조", compact)
    if not article:
        return None
    after = compact[article.end():]
    paragraph = re.search(r"제(\d+)항", after)
    item = re.search(r"제(\d+)호", after)
    subitem = re.search(r"([가-하])목", after)
    parts = [law_name, f"제{article.group(1)}조"]
    paragraph_no = f"제{paragraph.group(1)}항" if paragraph else ""
    item_no = f"제{item.group(1)}호" if item else ""
    subitem_no = f"{subitem.group(1)}목" if subitem else ""
    for part in (paragraph_no, item_no, subitem_no):
        if part:
            parts.append(part)
    level = "article"
    if subitem_no:
        level = "subitem"
    elif item_no:
        level = "item"
    elif paragraph_no:
        level = "paragraph"
    return {
        "law_name": law_name,
        "article_no": f"제{article.group(1)}조",
        "paragraph_no": paragraph_no,
        "item_no": item_no,
        "subitem_no": subitem_no,
        "normalized_ref": " ".join(parts),
        "ref_level": level,
        "raw": str(text or ""),
    }


def normalize_fine_grained_law_ref(text: Any) -> str:
    parsed = parse_fine_grained_law_ref(text)
    return parsed["normalized_ref"] if parsed else normalize_law_ref(text)


def ref_to_tuple(ref: Any) -> tuple[str, str, str, str, str] | None:
    parsed = parse_fine_grained_law_ref(ref)
    if not parsed:
        return None
    return (
        parsed["law_name"],
        parsed["article_no"],
        parsed.get("paragraph_no") or "",
        parsed.get("item_no") or "",
        parsed.get("subitem_no") or "",
    )


def get_ref_level(parsed_ref: dict[str, Any] | None) -> str:
    return (parsed_ref or {}).get("ref_level") or "unknown"


def is_same_article(ref_a: Any, ref_b: Any) -> bool:
    a = ref_to_tuple(ref_a)
    b = ref_to_tuple(ref_b)
    return bool(a and b and a[:2] == b[:2])


def is_same_paragraph(ref_a: Any, ref_b: Any) -> bool:
    a = ref_to_tuple(ref_a)
    b = ref_to_tuple(ref_b)
    return bool(a and b and a[:3] == b[:3] and a[2])


def is_same_item(ref_a: Any, ref_b: Any) -> bool:
    a = ref_to_tuple(ref_a)
    b = ref_to_tuple(ref_b)
    return bool(a and b and a[:4] == b[:4] and a[3])


def fine_grained_match_score(gt_ref: Any, pred_ref: Any) -> tuple[str, float]:
    gt = ref_to_tuple(gt_ref)
    pred = ref_to_tuple(pred_ref)
    if not gt or not pred:
        return "no_match", 0.0
    if gt == pred:
        return "fine_exact", 1.0
    if gt[:4] == pred[:4] and gt[3]:
        return "item", 1.0
    if gt[:3] == pred[:3] and gt[2]:
        return "paragraph", 0.85
    if gt[:2] == pred[:2]:
        return "article", 0.65
    if gt[0] == pred[0]:
        return "law_name_only", 0.2
    return "no_match", 0.0


def _fine_ref_from_mapping(item: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    refs: list[str] = []
    details: list[dict[str, str]] = []
    for key in ("source_ref", "target_ref", "ref", "normalized_ref", "full_ref"):
        direct_ref = item.get(key)
        if isinstance(direct_ref, str) and direct_ref:
            parsed_direct = parse_fine_grained_law_ref(direct_ref)
            if parsed_direct:
                ref = parsed_direct["normalized_ref"]
                refs.append(ref)
                details.append({
                    "ref": ref,
                    "source": key,
                    "node_id": str(item.get("source_node_id") or item.get("target_node_id") or item.get("node_id") or ""),
                    "level": parsed_direct["ref_level"],
                })

    node_id = str(item.get("node_id") or item.get("source_node_id") or item.get("rule_id") or "")
    indexed_ref = _lookup_fine_ref_by_node_id(node_id)
    if indexed_ref:
        parsed_indexed = parse_fine_grained_law_ref(indexed_ref)
        refs.append(indexed_ref)
        details.append({
            "ref": indexed_ref,
            "source": "law_ref_index_node",
            "node_id": node_id,
            "level": (parsed_indexed or {}).get("ref_level", "article"),
        })
        return refs, details

    law = item.get("law_name") or item.get("law")
    article = item.get("article_no") or item.get("article")
    source_text = str(item.get("source_text") or item.get("source_text_preview") or item.get("text") or "")
    paragraph = item.get("paragraph_no") or ""
    item_no = item.get("item_no") or ""
    if not paragraph and source_text:
        stripped = source_text.strip()
        if stripped[:1] in FINE_CIRCLED_PARAGRAPHS:
            paragraph = stripped[:1]
        elif re.match(r"\s*\d+\s*[.ㆍ]", stripped):
            item_no = re.match(r"\s*(\d+)", stripped).group(1)
    if law and article:
        law_name = _fine_law_name(law)
        article_no = _fine_article(article)
        parts = [law_name, article_no]
        paragraph_no = _fine_paragraph(paragraph)
        item_norm = _fine_item(item_no) or (f"제{item_no}호" if str(item_no).isdigit() else "")
        if paragraph_no:
            parts.append(paragraph_no)
        if item_norm:
            parts.append(item_norm)
        ref = " ".join(part for part in parts if part)
        refs.append(ref)
        details.append({
            "ref": ref,
            "source": "mapping_fields",
            "node_id": node_id,
            "level": (parse_fine_grained_law_ref(ref) or {}).get("ref_level", "article"),
        })
    return refs, details


_FINE_REF_INDEX_CACHE: dict[str, str] | None = None
_FINE_EDGE_CACHE: list[dict[str, str]] | None = None


def _load_fine_ref_index_by_node() -> dict[str, str]:
    global _FINE_REF_INDEX_CACHE
    if _FINE_REF_INDEX_CACHE is not None:
        return _FINE_REF_INDEX_CACHE
    path = Path(__file__).resolve().parent / "generated_v4_current_strict" / "fine_grained" / "law_ref_index.csv"
    if not path.exists():
        _FINE_REF_INDEX_CACHE = {}
        return _FINE_REF_INDEX_CACHE
    import csv

    refs: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            node_id = row.get("node_id") or ""
            ref = row.get("normalized_ref") or row.get("full_ref") or ""
            if node_id and ref:
                refs[node_id] = normalize_fine_grained_law_ref(ref)
    _FINE_REF_INDEX_CACHE = refs
    return refs


def _lookup_fine_ref_by_node_id(node_id: str) -> str:
    if not node_id:
        return ""
    return _load_fine_ref_index_by_node().get(node_id, "")


def _load_fine_penalty_edges() -> list[dict[str, str]]:
    global _FINE_EDGE_CACHE
    if _FINE_EDGE_CACHE is not None:
        return _FINE_EDGE_CACHE
    path = Path(__file__).resolve().parent / "generated_v4_current_strict" / "fine_grained" / "fine_grained_penalty_edges.csv"
    if not path.exists():
        _FINE_EDGE_CACHE = []
        return _FINE_EDGE_CACHE
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        _FINE_EDGE_CACHE = list(csv.DictReader(f))
    return _FINE_EDGE_CACHE


def _expand_fine_refs_with_penalty_edges(refs: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    ref_set = set(refs)
    added: list[str] = []
    details: list[dict[str, str]] = []
    for edge in _load_fine_penalty_edges():
        source = edge.get("source_ref") or ""
        target = edge.get("target_ref") or ""
        if not source or not target or source not in ref_set or target in ref_set:
            continue
        if edge.get("status") not in {"TEXT_REFERENCE_CANDIDATE", "RULE_BASED_CANDIDATE"}:
            continue
        parsed_target = parse_fine_grained_law_ref(target)
        if not parsed_target or parsed_target["ref_level"] not in {"paragraph", "item"}:
            continue
        # Keep expansion narrow: at most one fine-grained penalty per source/article target.
        added.append(target)
        details.append({
            "ref": target,
            "source": f"fine_grained_penalty_edge:{edge.get('relation_type')}",
            "node_id": edge.get("target_node_id", ""),
            "level": parsed_target["ref_level"],
        })
    return list(dict.fromkeys(added[:4])), details


_FINE_PROMOTION_ARTICLE_ALLOWLIST = {
    ("산업안전보건법", "제1조"),
    ("산업안전보건법", "제38조"),
    ("산업안전보건법", "제39조"),
    ("산업안전보건법", "제63조"),
    ("산업안전보건법", "제64조"),
    ("산업안전보건법", "제167조"),
    ("산업안전보건법", "제168조"),
    ("산업안전보건법", "제173조"),
    ("중대재해처벌법", "제1조"),
    ("중대재해처벌법", "제2조"),
    ("중대재해처벌법", "제3조"),
    ("중대재해처벌법", "제4조"),
    ("중대재해처벌법", "제5조"),
    ("중대재해처벌법", "제6조"),
    ("중대재해처벌법", "제7조"),
    ("중대재해처벌법", "제9조"),
    ("중대재해처벌법", "제10조"),
}


def _fine_ref_priority(ref: str) -> int:
    parsed = parse_fine_grained_law_ref(ref)
    if not parsed:
        return 0
    article_key = (parsed["law_name"], parsed["article_no"])
    high = {
        ("산업안전보건법", "제167조"),
        ("산업안전보건법", "제168조"),
        ("중대재해처벌법", "제2조"),
        ("중대재해처벌법", "제4조"),
        ("중대재해처벌법", "제6조"),
        ("중대재해처벌법", "제7조"),
    }
    medium = {
        ("산업안전보건법", "제38조"),
        ("산업안전보건법", "제39조"),
        ("산업안전보건법", "제63조"),
        ("산업안전보건법", "제64조"),
        ("산업안전보건법", "제173조"),
    }
    if article_key in high:
        return 100
    if article_key in medium:
        return 50
    return 10


def fine_max_child_promotions() -> int:
    raw = os.environ.get("FINE_MAX_CHILD_PROMOTIONS") or os.environ.get("PROJECT_FINE_MAX_CHILD_PROMOTIONS") or "5"
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


def _cap_fine_refs(refs: list[str], max_children_per_article: int = 2, max_child_refs: int | None = None) -> list[str]:
    if max_child_refs is None:
        max_child_refs = fine_max_child_promotions()
    article_refs: list[str] = []
    child_candidates: list[tuple[int, int, str]] = []
    child_counts: dict[tuple[str, str], int] = {}
    for index, ref in enumerate(refs):
        parsed = parse_fine_grained_law_ref(ref)
        if not parsed:
            continue
        article_key = (parsed["law_name"], parsed["article_no"])
        if article_key not in _FINE_PROMOTION_ARTICLE_ALLOWLIST:
            continue
        if parsed["ref_level"] == "article":
            article_refs.append(parsed["normalized_ref"])
            continue
        child_candidates.append((-_fine_ref_priority(parsed["normalized_ref"]), index, parsed["normalized_ref"]))
    kept_children: list[str] = []
    for _, _, ref in sorted(child_candidates):
        parsed = parse_fine_grained_law_ref(ref)
        if not parsed:
            continue
        article_key = (parsed["law_name"], parsed["article_no"])
        if child_counts.get(article_key, 0) >= max_children_per_article:
            continue
        if len(kept_children) >= max_child_refs:
            continue
        child_counts[article_key] = child_counts.get(article_key, 0) + 1
        kept_children.append(parsed["normalized_ref"])
    return list(dict.fromkeys(article_refs + kept_children))


def _walk_fine_refs(value: Any) -> tuple[list[str], list[dict[str, str]]]:
    refs: list[str] = []
    details: list[dict[str, str]] = []
    if isinstance(value, dict):
        child_refs, child_details = _fine_ref_from_mapping(value)
        refs.extend(child_refs)
        details.extend(child_details)
        for child in value.values():
            if isinstance(child, (dict, list)):
                c_refs, c_details = _walk_fine_refs(child)
                refs.extend(c_refs)
                details.extend(c_details)
    elif isinstance(value, list):
        for child in value:
            c_refs, c_details = _walk_fine_refs(child)
            refs.extend(c_refs)
            details.extend(c_details)
    elif isinstance(value, str):
        parsed = parse_fine_grained_law_ref(value)
        if parsed:
            refs.append(parsed["normalized_ref"])
            details.append({"ref": parsed["normalized_ref"], "source": "string_ref", "node_id": "", "level": parsed["ref_level"]})
    return refs, details


def extract_fine_grained_laws_from_response(response: dict[str, Any] | None, fallback_laws: list[str] | None = None) -> tuple[list[str], dict[str, Any]]:
    response = response or {}
    refs: list[str] = []
    details: list[dict[str, str]] = []
    for field in ("citations", "evidences", "evidence_chips", "evidence_pack", "claim_check"):
        c_refs, c_details = _walk_fine_refs(response.get(field))
        refs.extend(c_refs)
        details.extend(c_details)
    if fallback_laws:
        for law in fallback_laws:
            parsed = parse_fine_grained_law_ref(law)
            if parsed:
                refs.append(parsed["normalized_ref"])
                details.append({"ref": parsed["normalized_ref"], "source": "fallback_predicted_laws", "node_id": "", "level": parsed["ref_level"]})
    deduped = list(dict.fromkeys(normalize_fine_grained_law_ref(ref) for ref in refs if ref))
    deduped = _cap_fine_refs(deduped)
    edge_refs, edge_details = _expand_fine_refs_with_penalty_edges(deduped)
    deduped = _cap_fine_refs(list(dict.fromkeys(deduped + edge_refs)))
    details.extend(edge_details)
    article_refs = []
    level_counts: dict[str, int] = {}
    for ref in deduped:
        parsed = parse_fine_grained_law_ref(ref)
        if not parsed:
            continue
        article_refs.append(f"{parsed['law_name']} {parsed['article_no']}")
        level_counts[parsed["ref_level"]] = level_counts.get(parsed["ref_level"], 0) + 1
    return deduped, {
        "predicted_law_refs_fine": deduped,
        "predicted_law_refs_article": list(dict.fromkeys(article_refs)),
        "predicted_ref_levels": level_counts,
        "fine_grained_extraction_source": details,
    }


def evaluate_fine_grained_matches(gt_laws: list[str], pred_refs: list[str], response: dict[str, Any] | None = None) -> dict[str, Any]:
    gt_refs = list(dict.fromkeys(normalize_fine_grained_law_ref(law) for law in gt_laws if law))
    pred_norm = list(dict.fromkeys(normalize_fine_grained_law_ref(law) for law in pred_refs if law))
    gt_set = set(gt_refs)
    pred_set = set(pred_norm)
    exact_tp = len(gt_set & pred_set)
    exact_precision = exact_tp / len(pred_set) if pred_set else 0.0
    exact_recall = exact_tp / len(gt_set) if gt_set else 0.0
    exact_f1 = 2 * exact_precision * exact_recall / (exact_precision + exact_recall) if exact_precision + exact_recall else 0.0

    used: set[int] = set()
    matches: list[dict[str, Any]] = []
    for gt in gt_refs:
        best = (0.0, -1, "no_match")
        for idx, pred in enumerate(pred_norm):
            if idx in used:
                continue
            rel, score = fine_grained_match_score(gt, pred)
            if score > best[0]:
                best = (score, idx, rel)
        if best[1] >= 0 and best[0] > 0:
            used.add(best[1])
            matches.append({"gt": gt, "pred": pred_norm[best[1]], "relation_type": best[2], "score": best[0]})
    total_score = sum(m["score"] for m in matches)
    soft_precision = total_score / len(pred_norm) if pred_norm else 0.0
    soft_recall = total_score / len(gt_refs) if gt_refs else 0.0
    soft_f1 = 2 * soft_precision * soft_recall / (soft_precision + soft_recall) if soft_precision + soft_recall else 0.0

    def filter_level(refs: list[str], level: str) -> set[str]:
        result = set()
        for ref in refs:
            parsed = parse_fine_grained_law_ref(ref)
            if parsed and parsed["ref_level"] == level:
                result.add(parsed["normalized_ref"])
        return result

    level_metrics = {}
    for level in ("article", "paragraph", "item"):
        g = filter_level(gt_refs, level)
        p = filter_level(pred_norm, level)
        tp = len(g & p)
        pr = tp / len(p) if p else 0.0
        re_ = tp / len(g) if g else 0.0
        level_metrics[level] = {"precision": pr, "recall": re_, "f1": 2 * pr * re_ / (pr + re_) if pr + re_ else 0.0}

    chain_refs: list[str] = []
    chain_edges: list[dict[str, Any]] = []
    chain_debug: dict[str, Any] = {}
    if response:
        pack = response.get("evidence_pack") or {}
        chain_debug = pack.get("debug") or {}
        legal_chains = pack.get("legal_chains") or []
        c_refs, _ = _walk_fine_refs(legal_chains)
        chain_refs = list(dict.fromkeys(c_refs))
        for chain in legal_chains:
            if not isinstance(chain, dict) or chain.get("chain_type") != "fine_grained_penalty_chain":
                continue
            for edge in chain.get("edges") or []:
                if isinstance(edge, dict):
                    chain_edges.append(edge)
    chain_relevant_articles = {
        ("산업안전보건법", "제38조"),
        ("산업안전보건법", "제39조"),
        ("산업안전보건법", "제63조"),
        ("산업안전보건법", "제64조"),
        ("산업안전보건법", "제167조"),
        ("산업안전보건법", "제168조"),
        ("산업안전보건법", "제173조"),
        ("중대재해처벌법", "제4조"),
        ("중대재해처벌법", "제5조"),
        ("중대재해처벌법", "제6조"),
        ("중대재해처벌법", "제7조"),
        ("중대재해처벌법", "제9조"),
        ("중대재해처벌법", "제10조"),
    }

    def is_chain_relevant(ref: str) -> bool:
        parsed = parse_fine_grained_law_ref(ref)
        if not parsed:
            return False
        return (parsed.get("law_name") or "", parsed.get("article_no") or "") in chain_relevant_articles

    chain_gt = [ref for ref in gt_refs if is_chain_relevant(ref)]
    chain_pred = [ref for ref in chain_refs if is_chain_relevant(ref)]
    chain_set = set(chain_pred)
    chain_gt_set = set(chain_gt)

    chain_matches: list[dict[str, Any]] = []
    used_chain_preds: set[int] = set()
    for gt in chain_gt:
        best_idx = -1
        best_rel = "no_match"
        best_score = 0.0
        for idx, pred in enumerate(chain_pred):
            if idx in used_chain_preds:
                continue
            rel, score = fine_grained_match_score(gt, pred)
            if score > best_score:
                best_idx = idx
                best_rel = rel
                best_score = score
        if best_idx >= 0 and best_score >= 0.65:
            used_chain_preds.add(best_idx)
            chain_matches.append({
                "gt": gt,
                "pred": chain_pred[best_idx],
                "relation_type": f"fine_chain_{best_rel}",
                "score": best_score,
            })

    matched_chain_gt = {match["gt"] for match in chain_matches}
    matched_chain_pred = {match["pred"] for match in chain_matches}
    chain_tp = len(chain_matches)
    chain_precision = chain_tp / len(chain_set) if chain_set else 0.0
    chain_recall = chain_tp / len(chain_gt_set) if chain_gt_set else 0.0
    chain_f1 = 2 * chain_precision * chain_recall / (chain_precision + chain_recall) if chain_precision + chain_recall else 0.0

    promoted = [ref for ref in pred_norm if ref not in {f"{(parse_fine_grained_law_ref(ref) or {}).get('law_name')} {(parse_fine_grained_law_ref(ref) or {}).get('article_no')}" for ref in pred_norm}]
    return {
        "ground_truth_refs_fine": gt_refs,
        "predicted_refs_fine": pred_norm,
        "fine_grained_matches": matches,
        "article_level_matches": [m for m in matches if m["relation_type"] == "article" or (parse_fine_grained_law_ref(m["gt"]) or {}).get("ref_level") == "article"],
        "paragraph_level_matches": [m for m in matches if (parse_fine_grained_law_ref(m["gt"]) or {}).get("ref_level") == "paragraph"],
        "item_level_matches": [m for m in matches if (parse_fine_grained_law_ref(m["gt"]) or {}).get("ref_level") == "item"],
        "fine_grained_legal_chain_matches": sorted(matched_chain_gt),
        "fine_grained_legal_chain_refs": sorted(chain_set),
        "fine_grained_legal_chain_edges": chain_edges,
        "fine_grained_chain_match_details": chain_matches,
        "fine_grained_chain_missing": sorted(chain_gt_set - matched_chain_gt),
        "fine_grained_chain_source_level": sorted(
            {
                (parse_fine_grained_law_ref(edge.get("from") or "") or {}).get("ref_level", "unknown")
                for edge in chain_edges
            }
        ),
        "fine_grained_chain_target_level": sorted(
            {
                (parse_fine_grained_law_ref(edge.get("to") or "") or {}).get("ref_level", "unknown")
                for edge in chain_edges
            }
        ),
        "promoted_child_refs": [ref for ref in pred_norm if (parse_fine_grained_law_ref(ref) or {}).get("ref_level") in {"paragraph", "item", "subitem"}],
        "fine_grained_missing_refs": sorted(gt_set - pred_set),
        "fine_grained_overgenerated_refs": sorted(pred_set - gt_set),
        "fine_grained_exact_precision": exact_precision,
        "fine_grained_exact_recall": exact_recall,
        "fine_grained_exact_f1": exact_f1,
        "fine_grained_soft_precision": soft_precision,
        "fine_grained_soft_recall": soft_recall,
        "fine_grained_soft_f1": soft_f1,
        "fine_grained_legal_chain_precision": chain_precision,
        "fine_grained_legal_chain_recall": chain_recall,
        "fine_grained_legal_chain_f1": chain_f1,
        "obligation_seed_found_count": int(chain_debug.get("obligation_seed_found_count") or 0),
        "obligation_seed_to_child_success_count": int(chain_debug.get("obligation_seed_to_child_success_count") or 0),
        "obligation_to_penalty_chain_count": int(chain_debug.get("obligation_to_penalty_chain_count") or 0),
        "full_obligation_penalty_corporate_chain_count": int(chain_debug.get("full_obligation_penalty_corporate_chain_count") or 0),
        "legal_chains_missing_count": int(chain_debug.get("legal_chains_missing_count") or 0),
        "fine_grained_ref_coverage": len(pred_norm) / max(1, len(gt_refs)),
        "article_to_child_promotion_count": len([ref for ref in pred_norm if (parse_fine_grained_law_ref(ref) or {}).get("ref_level") in {"paragraph", "item", "subitem"}]),
        "fine_grained_penalty_edge_match_count": chain_tp,
        "article_level_exact_precision": level_metrics["article"]["precision"],
        "article_level_exact_recall": level_metrics["article"]["recall"],
        "article_level_exact_f1": level_metrics["article"]["f1"],
        "paragraph_level_exact_precision": level_metrics["paragraph"]["precision"],
        "paragraph_level_exact_recall": level_metrics["paragraph"]["recall"],
        "paragraph_level_exact_f1": level_metrics["paragraph"]["f1"],
        "item_level_exact_precision": level_metrics["item"]["precision"],
        "item_level_exact_recall": level_metrics["item"]["recall"],
        "item_level_exact_f1": level_metrics["item"]["f1"],
    }


SELECTED_BUNDLE_SLOTS = {
    "primary_obligation",
    "health_obligation",
    "contractor_obligation",
    "serious_accident_obligation",
    "penalty",
    "corporate_penalty",
}
SUPPORTING_BUNDLE_SLOTS = {
    "definition_or_scope",
    "purpose_support",
    "detail_rule",
    "administrative_fine",
    "procedure_or_management",
    "education_requirement",
    "appointment_requirement",
    "reporting_or_submission",
    "record_retention",
}


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}


def _case_fact_supporting_refs(context: dict[str, Any], question: str) -> list[tuple[str, str]]:
    item = context.get("item") or {}
    facts = item.get("case_facts") or {}
    text = " ".join([question, json.dumps(facts, ensure_ascii=False)])
    refs: list[tuple[str, str]] = []

    def add(ref: str, reason: str) -> None:
        refs.append((ref, reason))

    if _truthy(facts.get("scope_issue")) or any(k in text for k in ("적용범위", "상시근로자", "시행일", "사업장", "50명")):
        add("중대재해처벌법 제1조", "case_facts scope/purpose supporting ref")
        add("중대재해처벌법 제2조", "case_facts definition supporting ref")
        add("중대재해처벌법 제3조", "case_facts scope supporting ref")
        add("산업안전보건법 제1조", "case_facts OSH purpose supporting ref")
        add("산업안전보건법 제2조", "case_facts OSH definition supporting ref")
    if _truthy(facts.get("serious_accident_issue")) or any(k in text for k in ("중대재해", "경영책임자", "안전보건관리체계")):
        add("중대재해처벌법 시행령 제4조", "case_facts serious-accident detail supporting ref")
    if _truthy(facts.get("health_issue")) or any(k in text for k in ("질식", "산소결핍", "유해물질", "화학", "중독")):
        add("산업안전보건법 제39조", "case_facts health obligation supporting ref")
        if any(k in text for k in ("질식", "산소결핍")):
            add("산업안전보건기준에 관한 규칙 제619조", "case_facts suffocation detail supporting ref")
    if _truthy(facts.get("contractor_relation")) or any(k in text for k in ("도급", "수급", "관계수급인", "하청")):
        add("산업안전보건법 제63조", "case_facts contractor obligation supporting ref")
        add("산업안전보건법 제64조", "case_facts contractor management supporting ref")
    return list(dict.fromkeys(refs))


def _add_tier_ref(tiers: dict[str, list[dict[str, Any]]], tier: str, ref: Any, source: str, reason: str) -> None:
    parsed = parse_fine_grained_law_ref(ref)
    if not parsed:
        return
    tiers[tier].append({
        "ref": parsed["normalized_ref"],
        "source": source,
        "tier": tier.replace("_laws", ""),
        "reason": reason,
        "level": parsed["ref_level"],
    })


def _tier_refs_from_part(part: Any, tier: str, source: str, reason: str) -> list[dict[str, Any]]:
    refs, details = _walk_fine_refs(part)
    if tier == "candidate":
        refs = _cap_fine_refs(refs, max_children_per_article=2, max_child_refs=16)
    elif tier == "supporting":
        refs = _cap_fine_refs(refs, max_children_per_article=2, max_child_refs=24)
    out = []
    for ref in refs:
        parsed = parse_fine_grained_law_ref(ref)
        if parsed:
            out.append({
                "ref": parsed["normalized_ref"],
                "source": source,
                "tier": tier,
                "reason": reason,
                "level": parsed["ref_level"],
            })
    return out


def _is_fine_ref_more_specific(a: str, b: str) -> bool:
    pa = parse_fine_grained_law_ref(a) or {}
    pb = parse_fine_grained_law_ref(b) or {}
    if pa.get("law_name") != pb.get("law_name") or pa.get("article_no") != pb.get("article_no"):
        return False
    order = {"article": 0, "paragraph": 1, "item": 2, "subitem": 3}
    return order.get(pa.get("ref_level", "article"), 0) > order.get(pb.get("ref_level", "article"), 0)


def _keep_article_duplicate(ref: str) -> bool:
    parsed = parse_fine_grained_law_ref(ref) or {}
    if parsed.get("ref_level") != "article":
        return False
    law = parsed.get("law_name", "")
    article = parsed.get("article_no", "")
    if "산업안전보건법" in law and article in {"제167조", "제168조", "제173조"}:
        return True
    if "중대재해처벌법" in law and "시행" not in law and article in {"제6조", "제7조"}:
        return True
    return False


def _dedupe_tier_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ref: dict[str, dict[str, Any]] = {}
    for item in items:
        ref = normalize_fine_grained_law_ref(item.get("ref"))
        if not ref:
            continue
        item = dict(item)
        item["ref"] = ref
        by_ref.setdefault(ref, item)
    refs = list(by_ref)
    remove: set[str] = set()
    for ref in refs:
        if _keep_article_duplicate(ref):
            continue
        for other in refs:
            if ref != other and _is_fine_ref_more_specific(other, ref):
                remove.add(ref)
    return [item for ref, item in by_ref.items() if ref not in remove]


def _merge_law_tiers(raw_tiers: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    priority = ["selected_laws", "supporting_laws", "candidate_laws", "debug_laws"]
    assigned: dict[str, str] = {}
    merged = {key: [] for key in priority}
    for tier in priority:
        for item in _dedupe_tier_items(raw_tiers.get(tier, [])):
            ref = item["ref"]
            if ref in assigned:
                continue
            # If a more specific ref is already in a higher tier, skip article-level duplicate.
            if any(_is_fine_ref_more_specific(existing, ref) for existing in assigned):
                continue
            assigned[ref] = tier
            merged[tier].append(item)
    return merged


def _classify_chain(chain: Any, question: str = "") -> tuple[str, dict[str, Any] | None]:
    if not isinstance(chain, dict):
        return "debug_legal_chains", None
    refs, _ = _walk_fine_refs(chain)
    refs = list(dict.fromkeys(normalize_fine_grained_law_ref(ref) for ref in refs if normalize_fine_grained_law_ref(ref)))
    if len(refs) < 2:
        return "debug_legal_chains", {"chain": chain, "refs": refs, "reason": "chain length < 2"}
    chain_type = str(chain.get("chain_type") or "")
    edges = chain.get("edges") or []
    statuses = " ".join(str(edge.get("status", "")) for edge in edges if isinstance(edge, dict))
    relation_types = " ".join(str(edge.get("relation_type", "")) for edge in edges if isinstance(edge, dict))
    source_ref = refs[0]
    target_refs = refs[1:]
    source_role = _selected_role_from_ref(source_ref)
    target_roles = {_selected_role_from_ref(ref) for ref in target_refs}
    has_penalty = bool({"penalty", "corporate_penalty"} & target_roles)
    selected_type = chain_type in {"fine_grained_penalty_chain", "obligation_penalty_chain"} or "PENAL" in relation_types
    if selected_type and source_role in {"primary_obligation", "health_obligation", "contractor_obligation", "serious_accident_obligation"} and has_penalty:
        return "selected_legal_chains", {
            "chain": chain,
            "refs": refs,
            "reason": "obligation source with penalty/corporate target",
            "source_role": source_role,
            "target_roles": sorted(target_roles),
        }
    if "WEAK" in statuses or not has_penalty:
        return "debug_legal_chains", {
            "chain": chain,
            "refs": refs,
            "reason": "weak or non-penalty chain",
            "source_role": source_role,
            "target_roles": sorted(target_roles),
        }
    return "candidate_legal_chains", {
        "chain": chain,
        "refs": refs,
        "reason": "conditional or broad candidate chain",
        "source_role": source_role,
        "target_roles": sorted(target_roles),
    }


def _selected_role_from_ref(ref: Any) -> str:
    parsed = parse_fine_grained_law_ref(ref)
    if not parsed:
        return "unknown"
    law_name = parsed.get("law_name")
    article = str(parsed.get("article_no") or "")
    if law_name == "산업안전보건법":
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
    if law_name == "중대재해처벌법":
        if article in {"제4조", "제5조"}:
            return "serious_accident_obligation"
        if article == "제6조":
            return "penalty"
        if article == "제7조":
            return "corporate_penalty"
        if article in {"제1조", "제2조", "제3조"}:
            return "definition_or_scope"
    if law_name in {"산업안전보건기준에 관한 규칙", "산업안전보건법 시행규칙", "중대재해처벌법 시행령"}:
        return "detail_rule"
    return "unknown"


def classify_predicted_laws_by_evidence_tier(
    api_response: dict[str, Any] | None,
    eval_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Split /ask references into selected/supporting/candidate/debug tiers.

    This is an evaluation-side policy. It does not change the API response and
    does not promote broad candidates into selected answers.
    """

    response = api_response or {}
    context = eval_context or {}
    question = str(context.get("question") or response.get("question") or "")
    pack = response.get("evidence_pack") or {}
    raw_tiers: dict[str, list[dict[str, Any]]] = {
        "selected_laws": [],
        "supporting_laws": [],
        "candidate_laws": [],
        "debug_laws": [],
    }

    # Answer text can include broad candidate explanations. Keep it supporting
    # unless the same ref is also present in primary evidence or a selected chain.
    for item in _tier_refs_from_part(response.get("answer"), "supporting", "answer", "cited in answer but not independently selected"):
        raw_tiers["supporting_laws"].append(item)

    # Backend primary evidence can contain full article children. Treat it as
    # supporting unless a ref is also selected by a chain or a core bundle slot.
    for field in ("primary_evidence", "primary_evidences", "evidences", "legal_bundle_supporting_evidence", "supporting_evidence"):
        raw_tiers["supporting_laws"].extend(_tier_refs_from_part(pack.get(field), "supporting", f"evidence_pack.{field}", "supporting evidence"))
    for field in ("selected_evidence",):
        for item in _tier_refs_from_part(pack.get(field), "selected", f"evidence_pack.{field}", "explicit selected evidence"):
            raw_tiers["selected_laws"].append(item)
    for field in ("legal_bundle_candidate_evidence", "candidate_evidence", "candidate_penalties", "rule_based_candidate_penalties"):
        raw_tiers["candidate_laws"].extend(_tier_refs_from_part(pack.get(field), "candidate", f"evidence_pack.{field}", "candidate evidence"))
    for field in ("debug", "retrieval_candidates", "weak_candidate_penalties"):
        raw_tiers["debug_laws"].extend(_tier_refs_from_part(pack.get(field), "debug", f"evidence_pack.{field}", "debug/weak candidate"))

    for ref, reason in _case_fact_supporting_refs(context, question):
        _add_tier_ref(raw_tiers, "supporting_laws", ref, "case_facts_supporting_policy", reason)

    # Legal bundle slots: core slots can be selected only when status is not weak.
    legal_bundle = pack.get("legal_bundle") or {}
    if isinstance(legal_bundle, dict):
        for slot, value in legal_bundle.items():
            tier = "selected_laws" if slot in SELECTED_BUNDLE_SLOTS else "supporting_laws" if slot in SUPPORTING_BUNDLE_SLOTS else "candidate_laws"
            reason = f"legal_bundle slot:{slot}"
            raw_tiers[tier].extend(_tier_refs_from_part(value, tier.replace("_laws", ""), f"legal_bundle.{slot}", reason))

    selected_chains: list[dict[str, Any]] = []
    candidate_chains: list[dict[str, Any]] = []
    debug_chains: list[dict[str, Any]] = []
    for chain in pack.get("selected_legal_chains") or []:
        tier, classified = _classify_chain(chain, question)
        if classified:
            selected_chains.append(classified)
    for chain in pack.get("legal_chains") or []:
        tier, classified = _classify_chain(chain, question)
        if not classified:
            continue
        if tier == "selected_legal_chains":
            selected_chains.append(classified)
        elif tier == "candidate_legal_chains":
            candidate_chains.append(classified)
            for ref in classified["refs"]:
                _add_tier_ref(raw_tiers, "candidate_laws", ref, "candidate_legal_chain", classified["reason"])
        else:
            debug_chains.append(classified)
            for ref in classified["refs"]:
                _add_tier_ref(raw_tiers, "debug_laws", ref, "debug_legal_chain", classified["reason"])
    for chain in pack.get("candidate_legal_chains") or []:
        tier, classified = _classify_chain(chain, question)
        if classified:
            candidate_chains.append(classified)

    if len(selected_chains) > 3:
        candidate_chains.extend(selected_chains[3:])
        selected_chains = selected_chains[:3]
    for classified in selected_chains:
        for ref in classified["refs"]:
            _add_tier_ref(raw_tiers, "selected_laws", ref, "selected_legal_chain", classified["reason"])

    # Fallback: if response has no explicit selected tier, keep answer/fine refs
    # conservative. Do not put broad fallback predicted_laws into selected.
    if not raw_tiers["selected_laws"]:
        for item in _tier_refs_from_part(response.get("citations"), "supporting", "citations", "citation fallback"):
            raw_tiers["supporting_laws"].append(item)

    merged = _merge_law_tiers(raw_tiers)
    return {
        **merged,
        "selected_legal_chains": selected_chains,
        "candidate_legal_chains": candidate_chains,
        "debug_legal_chains": debug_chains,
        "tier_classification_reason": {
            "policy": "selected=answer/primary evidence/obligation->penalty chain; supporting=detail/definition/purpose; candidate=conditional; debug=weak/internal",
            "question": question,
        },
    }


def _refs_from_tier_items(items: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(normalize_fine_grained_law_ref(item.get("ref")) for item in items if normalize_fine_grained_law_ref(item.get("ref"))))


def _article_key_from_ref(ref: Any) -> tuple[str, str] | None:
    parsed = parse_fine_grained_law_ref(ref)
    if not parsed:
        return None
    return parsed.get("law_name", ""), parsed.get("article_no", "")


def _article_recall_hits(gt_refs: set[str], pool_refs: set[str]) -> tuple[list[str], float]:
    pool_articles = {_article_key_from_ref(ref) for ref in pool_refs if _article_key_from_ref(ref)}
    hits = sorted(ref for ref in gt_refs if _article_key_from_ref(ref) in pool_articles)
    recall = len(hits) / len(gt_refs) if gt_refs else 0.0
    return hits, recall


def _article_compatible_prf(gt_refs: set[str], pred_refs: set[str]) -> dict[str, Any]:
    gt_articles = {_article_key_from_ref(ref) for ref in gt_refs if _article_key_from_ref(ref)}
    pred_articles = {_article_key_from_ref(ref) for ref in pred_refs if _article_key_from_ref(ref)}
    hit_articles = gt_articles & pred_articles
    precision = len(hit_articles) / len(pred_articles) if pred_articles else 0.0
    recall = len(hit_articles) / len(gt_articles) if gt_articles else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hit_articles": sorted(f"{law} {article}" for law, article in hit_articles),
        "missing_articles": sorted(f"{law} {article}" for law, article in (gt_articles - pred_articles)),
        "over_articles": sorted(f"{law} {article}" for law, article in (pred_articles - gt_articles)),
    }


def _ref_depth(ref_tuple: tuple[str, str, str, str, str]) -> int:
    _, article, paragraph, item_no, subitem = ref_tuple
    if subitem:
        return 5
    if item_no:
        return 4
    if paragraph:
        return 3
    if article:
        return 2
    return 1


def _is_hierarchical_compatible(gt_ref: str, pred_ref: str) -> tuple[bool, str]:
    gt = ref_to_tuple(gt_ref)
    pred = ref_to_tuple(pred_ref)
    if not gt or not pred:
        return False, "no_match"
    if gt == pred:
        return True, "fine_exact"
    if gt[:2] != pred[:2]:
        return False, "different_article"
    gt_depth = _ref_depth(gt)
    pred_depth = _ref_depth(pred)
    min_depth = min(gt_depth, pred_depth)
    if gt[:min_depth] == pred[:min_depth]:
        if gt_depth < pred_depth:
            return True, "prediction_child_of_gt"
        if pred_depth < gt_depth:
            return True, "prediction_parent_of_gt"
    return False, "same_article_different_child"


def _hierarchical_compatible_prf(gt_refs: set[str], pred_refs: set[str]) -> dict[str, Any]:
    gt_list = sorted(gt_refs)
    pred_list = sorted(pred_refs)
    used_pred: set[int] = set()
    used_gt: set[str] = set()
    matches: list[dict[str, str]] = []

    # First reserve exact hits. Otherwise a child prediction can be consumed by
    # a parent GT ref and the identical child GT is incorrectly left missing.
    pred_index = {pred: idx for idx, pred in enumerate(pred_list)}
    for gt in gt_list:
        idx = pred_index.get(gt)
        if idx is not None and idx not in used_pred:
            used_pred.add(idx)
            used_gt.add(gt)
            matches.append({"gt": gt, "pred": gt, "relation_type": "fine_exact"})

    for gt in gt_list:
        if gt in used_gt:
            continue
        best_idx = -1
        best_rel = "no_match"
        best_score = -1
        for idx, pred in enumerate(pred_list):
            if idx in used_pred:
                continue
            ok, rel = _is_hierarchical_compatible(gt, pred)
            if not ok:
                continue
            score = 3 if rel == "fine_exact" else 2 if rel == "prediction_child_of_gt" else 1
            if score > best_score:
                best_idx = idx
                best_rel = rel
                best_score = score
        if best_idx >= 0:
            used_pred.add(best_idx)
            matches.append({"gt": gt, "pred": pred_list[best_idx], "relation_type": best_rel})
    matched_gt = {m["gt"] for m in matches}
    matched_pred = {m["pred"] for m in matches}
    precision = len(matched_pred) / len(pred_refs) if pred_refs else 0.0
    recall = len(matched_gt) / len(gt_refs) if gt_refs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matches": matches,
        "missing": sorted(gt_refs - matched_gt),
        "overgenerated": sorted(pred_refs - matched_pred),
    }


def hierarchical_compatible_prf(gt_refs: set[str], pred_refs: set[str]) -> dict[str, Any]:
    return _hierarchical_compatible_prf(gt_refs, pred_refs)


def evaluate_selected_tiers(gt_laws: list[str], tier_output: dict[str, Any]) -> dict[str, Any]:
    selected_refs = _refs_from_tier_items(tier_output.get("selected_laws", []))
    supporting_refs = _refs_from_tier_items(tier_output.get("supporting_laws", []))
    candidate_refs = _refs_from_tier_items(tier_output.get("candidate_laws", []))
    debug_refs = _refs_from_tier_items(tier_output.get("debug_laws", []))
    selected_metrics = evaluate_fine_grained_matches(gt_laws, selected_refs, None)
    selected_pool_metrics = evaluate_fine_grained_matches(gt_laws, list(dict.fromkeys(selected_refs + supporting_refs)), None)
    candidate_pool_metrics = evaluate_fine_grained_matches(gt_laws, list(dict.fromkeys(selected_refs + supporting_refs + candidate_refs)), None)

    selected_chain_refs: list[str] = []
    candidate_chain_refs: list[str] = []
    debug_chain_refs: list[str] = []
    for chain in tier_output.get("selected_legal_chains", []):
        selected_chain_refs.extend(chain.get("refs") or [])
    for chain in tier_output.get("candidate_legal_chains", []):
        candidate_chain_refs.extend(chain.get("refs") or [])
    for chain in tier_output.get("debug_legal_chains", []):
        debug_chain_refs.extend(chain.get("refs") or [])
    selected_chain_metrics = evaluate_fine_grained_matches(gt_laws, list(dict.fromkeys(selected_chain_refs)), None)

    gt_refs = set(normalize_fine_grained_law_ref(law) for law in gt_laws if normalize_fine_grained_law_ref(law))
    selected_set = set(selected_refs)
    selected_missing = sorted(gt_refs - selected_set)
    selected_over = sorted(selected_set - gt_refs)
    candidate_pool = set(selected_refs + supporting_refs + candidate_refs)
    selected_supporting_pool = set(selected_refs + supporting_refs)
    debug_pool = set(debug_refs)
    full_debug_pool = set(selected_refs + supporting_refs + candidate_refs + debug_refs)
    candidate_hits = sorted(gt_refs & candidate_pool)
    candidate_recall = len(candidate_hits) / len(gt_refs) if gt_refs else 0.0
    selected_article_hits, selected_article_recall = _article_recall_hits(gt_refs, selected_set)
    selected_supporting_article_hits, selected_supporting_article_recall = _article_recall_hits(gt_refs, selected_supporting_pool)
    candidate_article_hits, candidate_article_recall = _article_recall_hits(gt_refs, candidate_pool)
    debug_article_hits, debug_article_recall = _article_recall_hits(gt_refs, debug_pool)
    full_debug_article_hits, full_debug_article_recall = _article_recall_hits(gt_refs, full_debug_pool)
    selected_article_compatible = _article_compatible_prf(gt_refs, selected_set)
    candidate_article_compatible = _article_compatible_prf(gt_refs, candidate_pool)
    selected_hierarchical_compatible = _hierarchical_compatible_prf(gt_refs, selected_set)
    candidate_hierarchical_compatible = _hierarchical_compatible_prf(gt_refs, candidate_pool)
    candidate_fine_missing = sorted(gt_refs - candidate_pool)
    candidate_article_missing = sorted(set(gt_refs) - set(candidate_article_hits))
    selected_failure_category = _selected_failure_category(selected_missing, candidate_pool)

    return {
        "selected_laws": tier_output.get("selected_laws", []),
        "supporting_laws": tier_output.get("supporting_laws", []),
        "candidate_laws": tier_output.get("candidate_laws", []),
        "debug_laws": tier_output.get("debug_laws", []),
        "selected_legal_chains": tier_output.get("selected_legal_chains", []),
        "candidate_legal_chains": tier_output.get("candidate_legal_chains", []),
        "debug_legal_chains": tier_output.get("debug_legal_chains", []),
        "selected_matches": selected_metrics.get("fine_grained_matches", []),
        "selected_missing": selected_missing,
        "selected_overgenerated": selected_over,
        "candidate_recall_hits": candidate_hits,
        "candidate_fine_missing": candidate_fine_missing,
        "candidate_article_missing": candidate_article_missing,
        "selected_article_recall_hits": selected_article_hits,
        "selected_supporting_article_recall_hits": selected_supporting_article_hits,
        "candidate_article_recall_hits": candidate_article_hits,
        "debug_article_recall_hits": debug_article_hits,
        "full_debug_article_recall_hits": full_debug_article_hits,
        "selected_article_compatible_hits": selected_article_compatible["hit_articles"],
        "selected_article_compatible_missing": selected_article_compatible["missing_articles"],
        "candidate_article_compatible_hits": candidate_article_compatible["hit_articles"],
        "candidate_article_compatible_missing": candidate_article_compatible["missing_articles"],
        "selected_hierarchical_compatible_matches": selected_hierarchical_compatible["matches"],
        "selected_hierarchical_compatible_missing": selected_hierarchical_compatible["missing"],
        "candidate_hierarchical_compatible_matches": candidate_hierarchical_compatible["matches"],
        "candidate_hierarchical_compatible_missing": candidate_hierarchical_compatible["missing"],
        "tier_classification_reason": tier_output.get("tier_classification_reason", {}),
        "selected_failure_category": selected_failure_category,
        "selected_fine_grained_exact_precision": selected_metrics["fine_grained_exact_precision"],
        "selected_fine_grained_exact_recall": selected_metrics["fine_grained_exact_recall"],
        "selected_fine_grained_exact_f1": selected_metrics["fine_grained_exact_f1"],
        "selected_fine_grained_soft_precision": selected_metrics["fine_grained_soft_precision"],
        "selected_fine_grained_soft_recall": selected_metrics["fine_grained_soft_recall"],
        "selected_fine_grained_soft_f1": selected_metrics["fine_grained_soft_f1"],
        "selected_legal_chain_precision": selected_chain_metrics["fine_grained_exact_precision"],
        "selected_legal_chain_recall": selected_chain_metrics["fine_grained_exact_recall"],
        "selected_legal_chain_f1": selected_chain_metrics["fine_grained_exact_f1"],
        "selected_expected_law_precision": selected_pool_metrics["fine_grained_soft_precision"],
        "selected_expected_law_recall": selected_pool_metrics["fine_grained_soft_recall"],
        "selected_expected_law_f1": selected_pool_metrics["fine_grained_soft_f1"],
        "candidate_recall": candidate_recall,
        "candidate_fine_recall": candidate_recall,
        "candidate_article_recall": candidate_article_recall,
        "selected_article_recall": selected_article_recall,
        "selected_supporting_article_recall": selected_supporting_article_recall,
        "selected_article_compatible_precision": selected_article_compatible["precision"],
        "selected_article_compatible_recall": selected_article_compatible["recall"],
        "selected_article_compatible_f1": selected_article_compatible["f1"],
        "candidate_article_compatible_precision": candidate_article_compatible["precision"],
        "candidate_article_compatible_recall": candidate_article_compatible["recall"],
        "candidate_article_compatible_f1": candidate_article_compatible["f1"],
        "selected_hierarchical_compatible_precision": selected_hierarchical_compatible["precision"],
        "selected_hierarchical_compatible_recall": selected_hierarchical_compatible["recall"],
        "selected_hierarchical_compatible_f1": selected_hierarchical_compatible["f1"],
        "candidate_hierarchical_compatible_precision": candidate_hierarchical_compatible["precision"],
        "candidate_hierarchical_compatible_recall": candidate_hierarchical_compatible["recall"],
        "candidate_hierarchical_compatible_f1": candidate_hierarchical_compatible["f1"],
        "debug_article_recall": debug_article_recall,
        "full_debug_article_recall": full_debug_article_recall,
        "selected_law_count": len(selected_refs),
        "supporting_law_count": len(supporting_refs),
        "candidate_law_count": len(candidate_refs),
        "debug_law_count": len(debug_refs),
        "selected_chain_count": len(tier_output.get("selected_legal_chains", [])),
        "candidate_chain_count": len(tier_output.get("candidate_legal_chains", [])),
        "debug_chain_count": len(tier_output.get("debug_legal_chains", [])),
    }


def _selected_failure_category(missing: list[str], candidate_pool: set[str]) -> str:
    if not missing:
        return ""
    if any(ref in candidate_pool for ref in missing):
        return "candidate_only_match"
    joined = " ".join(missing)
    if any(key in joined for key in ["제38조", "제39조", "제63조", "제64조", "제4조", "제5조"]):
        return "selected_core_obligation_missing"
    if any(key in joined for key in ["제167조", "제168조", "제6조"]):
        return "selected_penalty_missing"
    if any(key in joined for key in ["제173조", "제7조"]):
        return "selected_corporate_penalty_missing"
    if any(key in joined for key in ["제1조", "제2조", "제3조"]):
        return "selected_scope_definition_missing"
    if any((parse_fine_grained_law_ref(ref) or {}).get("ref_level") in {"paragraph", "item", "subitem"} for ref in missing):
        return "selected_fine_ref_mismatch"
    return "unknown"


CORE_OBLIGATION_ARTICLES = {
    ("산업안전보건법", "38"),
    ("산업안전보건법", "39"),
    ("산업안전보건법", "63"),
    ("산업안전보건법", "64"),
    ("중대재해처벌법", "4"),
    ("중대재해처벌법", "5"),
}
CORPORATE_PENALTY_ARTICLES = {
    ("산업안전보건법", "173"),
    ("중대재해처벌법", "7"),
}


def _law_article_key(value: Any) -> tuple[str, str] | None:
    ref = parse_law_ref(value)
    if not ref:
        return None
    law_name = str(ref.get("law_name") or "")
    article_no = str(ref.get("article_no") or "")
    if not law_name or not article_no:
        return None
    if "중대재해" in law_name:
        law_name = "중대재해처벌법"
    elif "산업안전보건법" in law_name and "시행" not in law_name and "기준" not in law_name:
        law_name = "산업안전보건법"
    return (law_name, article_no)


def _refs_from_response_part(value: Any) -> list[str]:
    return normalize_law_refs(_walk_response(value))


def analyze_legal_chain_response(
    response: dict[str, Any] | None,
    gt_laws: list[str],
    pred_laws: list[str],
) -> dict[str, Any]:
    response = response or {}
    gt_norm = normalize_law_refs(gt_laws)
    pred_norm = normalize_law_refs(pred_laws)
    gt_keys = {_law_article_key(ref) for ref in gt_norm}
    gt_keys.discard(None)
    pred_keys = [_law_article_key(ref) for ref in pred_norm]

    core_targets = sorted(key for key in gt_keys if key in CORE_OBLIGATION_ARTICLES)
    core_details = []
    for target in core_targets:
        rank = 0
        for idx, key in enumerate(pred_keys, 1):
            if key == target:
                rank = idx
                break
        core_details.append({"law_name": target[0], "article_no": target[1], "rank": rank})
    core_hit_at_1 = sum(1 for item in core_details if 0 < item["rank"] <= 1)
    core_hit_at_3 = sum(1 for item in core_details if 0 < item["rank"] <= 3)
    core_hit_at_5 = sum(1 for item in core_details if 0 < item["rank"] <= 5)

    pack = response.get("evidence_pack") or {}
    confirmed_refs = _refs_from_response_part(pack.get("confirmed_penalties"))
    rule_based_refs = _refs_from_response_part(pack.get("rule_based_candidate_penalties"))
    candidate_refs = _refs_from_response_part(pack.get("candidate_penalties"))
    chain_refs = _refs_from_response_part(pack.get("legal_chains"))
    confirmed_keys = {_law_article_key(ref) for ref in confirmed_refs}
    rule_based_keys = {_law_article_key(ref) for ref in rule_based_refs}
    candidate_keys = {_law_article_key(ref) for ref in candidate_refs + chain_refs}
    confirmed_keys.discard(None)
    rule_based_keys.discard(None)
    candidate_keys.discard(None)

    corporate_targets = sorted(key for key in gt_keys if key in CORPORATE_PENALTY_ARTICLES)
    corporate_matches = [key for key in corporate_targets if key in candidate_keys]
    rule_based_corporate = [key for key in corporate_targets if key in rule_based_keys]
    confirmed_penalty_matches = [key for key in gt_keys if key in confirmed_keys]
    candidate_penalty_matches = [key for key in gt_keys if key in candidate_keys]

    chain_pred_set = {ref for ref in chain_refs if ref}
    gt_set = set(gt_norm)
    legal_chain_tp = len(chain_pred_set & gt_set)
    legal_chain_precision = legal_chain_tp / len(chain_pred_set) if chain_pred_set else 0.0
    legal_chain_recall = legal_chain_tp / len(gt_set) if gt_set else 0.0
    legal_chain_f1 = (
        2 * legal_chain_precision * legal_chain_recall / (legal_chain_precision + legal_chain_recall)
        if (legal_chain_precision + legal_chain_recall) > 0
        else 0.0
    )

    def _format_key(key: tuple[str, str]) -> str:
        return f"{key[0]} 제{key[1]}조"

    return {
        "core_obligation_hits": [_format_key((item["law_name"], item["article_no"])) for item in core_details if item["rank"]],
        "core_obligation_rank_details": core_details,
        "core_obligation_hit_at_1": core_hit_at_1,
        "core_obligation_hit_at_3": core_hit_at_3,
        "core_obligation_hit_at_5": core_hit_at_5,
        "corporate_penalty_chain_matches": [_format_key(key) for key in corporate_matches],
        "rule_based_corporate_penalty_matches": [_format_key(key) for key in rule_based_corporate],
        "confirmed_penalty_matches": [_format_key(key) for key in confirmed_penalty_matches],
        "candidate_penalty_matches": [_format_key(key) for key in candidate_penalty_matches],
        "legal_chain_precision": legal_chain_precision,
        "legal_chain_recall": legal_chain_recall,
        "legal_chain_f1": legal_chain_f1,
        "legal_chain_details": {
            "chain_refs": chain_refs,
            "confirmed_refs": confirmed_refs,
            "rule_based_refs": rule_based_refs,
            "candidate_refs": candidate_refs,
        },
    }


BUNDLE_SLOT_NAMES = [
    "primary_obligation",
    "secondary_obligation",
    "health_obligation",
    "contractor_obligation",
    "detail_rule",
    "serious_accident_obligation",
    "penalty",
    "corporate_penalty",
    "definition_or_scope",
    "purpose_support",
    "administrative_fine",
    "procedure_or_management",
    "education_requirement",
    "appointment_requirement",
    "reporting_or_submission",
    "record_retention",
]


def _simple_parse_law_ref(value: Any) -> tuple[str, str] | None:
    text = str(value or "")
    compact = re.sub(r"\s+", "", text)
    law_name = ""
    if "산업안전보건기준에관한규칙" in compact:
        law_name = "산업안전보건기준에 관한 규칙"
    elif "산업안전보건법시행규칙" in compact:
        law_name = "산업안전보건법 시행규칙"
    elif "산업안전보건법시행령" in compact:
        law_name = "산업안전보건법 시행령"
    elif "산업안전보건법" in compact:
        law_name = "산업안전보건법"
    elif "중대재해처벌등에관한법률시행령" in compact or "중대재해처벌법시행령" in compact:
        law_name = "중대재해처벌법 시행령"
    elif "중대재해처벌등에관한법률" in compact or "중대재해처벌법" in compact:
        law_name = "중대재해처벌법"
    if not law_name:
        return None
    match = re.search(r"제(\d+(?:조의\d+)?)조", compact)
    if not match:
        return None
    return law_name, f"제{match.group(1)}조"


def _format_bundle_ref(key: tuple[str, str]) -> str:
    return f"{key[0]} {key[1]}"


def _bundle_expected_from_item(item: dict[str, Any]) -> dict[str, list[str]]:
    expected = item.get("expected_legal_bundle") or {}
    if expected:
        return {slot: list(expected.get(slot) or []) for slot in BUNDLE_SLOT_NAMES}
    classified = item.get("classified_ground_truth_laws") or {}
    if classified:
        return {
        "primary_obligation": list(classified.get("primary_obligation") or []),
        "secondary_obligation": list(classified.get("procedure_or_management") or []),
        "health_obligation": [
            law for law in classified.get("primary_obligation") or []
            if _simple_parse_law_ref(law) == ("산업안전보건법", "제39조")
        ],
        "contractor_obligation": [
            law for law in classified.get("primary_obligation") or []
            if _simple_parse_law_ref(law) in {("산업안전보건법", "제63조"), ("산업안전보건법", "제64조")}
        ],
        "detail_rule": list(classified.get("detail_rule") or []),
        "serious_accident_obligation": list(classified.get("serious_accident_obligation") or []),
        "penalty": list(classified.get("penalty") or []),
        "corporate_penalty": list(classified.get("corporate_penalty") or []),
        "definition_or_scope": list(classified.get("definition_or_scope") or []),
        "purpose_support": [],
        "administrative_fine": [],
        "procedure_or_management": list(classified.get("procedure_or_management") or []),
        "education_requirement": [],
        "appointment_requirement": [],
        "reporting_or_submission": [],
        "record_retention": [],
        }
    auto = {slot: [] for slot in BUNDLE_SLOT_NAMES}
    for law in item.get("ground_truth_laws") or []:
        slot = _slot_from_law_ref(law)
        if slot:
            auto[slot].append(law)
    return auto


def _slot_from_law_ref(law_ref: Any) -> str:
    key = _simple_parse_law_ref(law_ref)
    if not key:
        return ""
    law_name, article_no = key
    if law_name == "산업안전보건법":
        if article_no == "제38조":
            return "primary_obligation"
        if article_no == "제39조":
            return "health_obligation"
        if article_no in {"제63조", "제64조"}:
            return "contractor_obligation"
        if article_no in {"제167조", "제168조", "제169조", "제170조", "제171조", "제172조"}:
            return "penalty"
        if article_no == "제173조":
            return "corporate_penalty"
        if article_no in {"제1조", "제2조", "제3조"}:
            return "definition_or_scope"
        return "procedure_or_management"
    if law_name == "중대재해처벌법":
        if article_no in {"제4조", "제5조", "제9조"}:
            return "serious_accident_obligation"
        if article_no == "제6조":
            return "penalty"
        if article_no == "제7조":
            return "corporate_penalty"
        if article_no in {"제1조", "제2조", "제3조"}:
            return "definition_or_scope"
    if law_name in {"산업안전보건법 시행규칙", "산업안전보건기준에 관한 규칙", "중대재해처벌법 시행령"}:
        return "detail_rule"
    return "unknown"


def _refs_from_bundle_slot(slot_value: Any) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    if isinstance(slot_value, list):
        for item in slot_value:
            if isinstance(item, dict):
                key = _simple_parse_law_ref(f"{item.get('law_name') or ''} {item.get('article_no') or ''}")
                if key:
                    refs.add(key)
            else:
                key = _simple_parse_law_ref(item)
                if key:
                    refs.add(key)
    return refs


def analyze_bundle_response(
    response: dict[str, Any] | None,
    item: dict[str, Any],
    pred_laws: list[str],
) -> dict[str, Any]:
    response = response or {}
    pack = response.get("evidence_pack") or {}
    expected = _bundle_expected_from_item(item)
    predicted_refs = {_simple_parse_law_ref(ref) for ref in pred_laws}
    predicted_refs.discard(None)

    legal_bundle = pack.get("legal_bundle") or {}
    supporting_evidence = pack.get("legal_bundle_supporting_evidence") or []
    candidate_evidence = pack.get("candidate_evidence") or pack.get("legal_bundle_candidate_evidence") or []
    bundle_refs_by_slot: dict[str, set[tuple[str, str]]] = {}
    for slot in BUNDLE_SLOT_NAMES:
        bundle_refs_by_slot[slot] = _refs_from_bundle_slot(legal_bundle.get(slot))

    all_bundle_refs: set[tuple[str, str]] = set()
    for slot_refs in bundle_refs_by_slot.values():
        all_bundle_refs |= slot_refs
    all_bundle_refs |= {_simple_parse_law_ref(ref) for ref in _refs_from_response_part(pack.get("legal_bundle_supporting_evidence"))}
    all_bundle_refs |= {_simple_parse_law_ref(ref) for ref in _refs_from_response_part(pack.get("candidate_evidence"))}
    all_bundle_refs.discard(None)

    slot_details: dict[str, Any] = {}
    slot_hit_count = 0
    slot_total_count = 0
    expected_law_hit_count = 0
    expected_law_total_count = 0
    missing_categories: list[str] = []

    category_by_slot = {
        "primary_obligation": "core_obligation_missing",
        "health_obligation": "health_obligation_missing",
        "contractor_obligation": "contractor_obligation_missing",
        "serious_accident_obligation": "serious_accident_obligation_missing",
        "penalty": "penalty_missing",
        "corporate_penalty": "corporate_penalty_missing",
        "definition_or_scope": "definition_scope_missing",
        "purpose_support": "purpose_support_missing",
        "administrative_fine": "administrative_fine_missing",
        "procedure_or_management": "procedure_missing",
        "education_requirement": "procedure_missing",
        "appointment_requirement": "procedure_missing",
        "reporting_or_submission": "procedure_missing",
        "record_retention": "procedure_missing",
    }

    for slot in BUNDLE_SLOT_NAMES:
        expected_refs = {_simple_parse_law_ref(ref) for ref in expected.get(slot) or []}
        expected_refs.discard(None)
        if not expected_refs:
            slot_details[slot] = {"expected": [], "hits": [], "missing": [], "hit": None}
            continue
        slot_total_count += 1
        candidate_refs = predicted_refs | all_bundle_refs | bundle_refs_by_slot.get(slot, set())
        hits = sorted(ref for ref in expected_refs if ref in candidate_refs)
        missing = sorted(expected_refs - set(hits))
        expected_law_hit_count += len(hits)
        expected_law_total_count += len(expected_refs)
        if hits:
            slot_hit_count += 1
        elif slot in category_by_slot:
            missing_categories.append(category_by_slot[slot])
        slot_details[slot] = {
            "expected": [_format_bundle_ref(ref) for ref in sorted(expected_refs)],
            "hits": [_format_bundle_ref(ref) for ref in hits],
            "missing": [_format_bundle_ref(ref) for ref in missing],
            "hit": bool(hits),
        }

    bundle_complete_hit = 1 if slot_total_count and slot_hit_count == slot_total_count else 0
    bundle_slot_recall = slot_hit_count / slot_total_count if slot_total_count else 0.0
    bundle_expected_law_recall = expected_law_hit_count / expected_law_total_count if expected_law_total_count else 0.0
    bundle_predicted_count = len(all_bundle_refs)
    bundle_slot_precision = slot_hit_count / bundle_predicted_count if bundle_predicted_count else 0.0
    bundle_expected_law_precision = expected_law_hit_count / bundle_predicted_count if bundle_predicted_count else 0.0
    bundle_expected_law_f1 = (
        2 * bundle_expected_law_precision * bundle_expected_law_recall / (bundle_expected_law_precision + bundle_expected_law_recall)
        if (bundle_expected_law_precision + bundle_expected_law_recall) > 0
        else 0.0
    )
    weak_candidate_count = sum(1 for item in candidate_evidence if isinstance(item, dict) and item.get("candidate_status") == "WEAK_CANDIDATE")
    rule_based_candidate_count = sum(1 for item in candidate_evidence if isinstance(item, dict) and item.get("candidate_status") in {"RULE_BASED_CANDIDATE", "BUNDLE_COMPLETION_CANDIDATE"})
    confirmed_evidence_count = sum(1 for item in supporting_evidence if isinstance(item, dict) and item.get("candidate_status") == "CONFIRMED")
    candidate_overgeneration_rate = len(candidate_evidence) / max(1, expected_law_total_count)
    return {
        "bundle_slot_hit_count": slot_hit_count,
        "bundle_slot_total_count": slot_total_count,
        "bundle_slot_recall": bundle_slot_recall,
        "bundle_slot_precision": bundle_slot_precision,
        "bundle_expected_law_hit_count": expected_law_hit_count,
        "bundle_expected_law_total_count": expected_law_total_count,
        "bundle_expected_law_recall": bundle_expected_law_recall,
        "bundle_expected_law_precision": bundle_expected_law_precision,
        "bundle_expected_law_f1": bundle_expected_law_f1,
        "bundle_complete_hit": bundle_complete_hit,
        "supporting_evidence_count": len(supporting_evidence),
        "candidate_evidence_count": len(candidate_evidence),
        "weak_candidate_count": weak_candidate_count,
        "rule_based_candidate_count": rule_based_candidate_count,
        "confirmed_evidence_count": confirmed_evidence_count,
        "candidate_overgeneration_rate": candidate_overgeneration_rate,
        "bundle_slot_details": slot_details,
        "bundle_missing_categories": sorted(set(missing_categories)),
    }
