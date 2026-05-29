"""Post-generation checks for optional LLM-polished answers."""

from __future__ import annotations

import re
from typing import Any


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b:?"
)
ARTICLE_RE = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?")

INTERNAL_MARKERS = (
    "warning:",
    "THRESHOLD_MISSING",
    "Use an indirect-only",
    "candidate has no threshold",
    "source_node_id",
    "source_anchor_id",
    "rule_id",
    "list_item_id",
)

INDIRECT_DIRECT_MARKERS = (
    "반드시 알려야 합니다",
    "고지해야 합니다",
    "알려야 합니다.",
    "의무입니다",
)

CONFIRMED_PENALTY_MARKERS = (
    "처벌됩니다",
    "과태료가 부과됩니다",
    "벌금이 부과됩니다",
    "징역에 처합니다",
)


def validate_polished_answer(answer: str, payload: dict[str, Any]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    text = str(answer or "").strip()
    if not text:
        return False, ["empty_answer"]

    if UUID_RE.search(text):
        notes.append("uuid_leak")

    lowered = text.lower()
    for marker in INTERNAL_MARKERS:
        if marker.lower() in lowered:
            notes.append(f"internal_marker:{marker}")

    if payload.get("answer_policy") == "INDIRECT_ONLY_RESPONSE":
        for marker in INDIRECT_DIRECT_MARKERS:
            if marker in text:
                notes.append(f"indirect_only_direct_marker:{marker}")

    penalties = payload.get("penalties") or []
    candidate_penalties = payload.get("candidate_penalties") or []
    if candidate_penalties and not penalties:
        for marker in CONFIRMED_PENALTY_MARKERS:
            if marker in text:
                notes.append(f"candidate_penalty_confirmed_marker:{marker}")

    citation_blob = " ".join(_citation_text(citation) for citation in payload.get("citations") or [])
    allowed_articles = set(ARTICLE_RE.findall(citation_blob))
    for article in set(ARTICLE_RE.findall(text)):
        if allowed_articles and article not in allowed_articles:
            notes.append(f"article_not_in_citations:{article}")

    hard_fail_prefixes = (
        "empty_answer",
        "uuid_leak",
        "internal_marker:",
        "indirect_only_direct_marker:",
        "candidate_penalty_confirmed_marker:",
    )
    ok = not any(any(note.startswith(prefix) for prefix in hard_fail_prefixes) for note in notes)
    return ok, notes


def _citation_text(citation: Any) -> str:
    if not isinstance(citation, dict):
        return str(citation or "")
    parts = [
        citation.get("citation_text"),
        citation.get("law_name"),
        citation.get("article_no"),
        citation.get("annex_title"),
        citation.get("title"),
    ]
    return " ".join(str(part) for part in parts if part)

