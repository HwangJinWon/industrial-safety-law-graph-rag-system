"""Domain extractor registry."""

from __future__ import annotations

from typing import Any

from graph_rag_pipeline.extractors.education_time_extractor import EducationTimeExtractor
from graph_rag_pipeline.extractors.exception_extractor import ExceptionExtractor
from graph_rag_pipeline.extractors.list_lookup_extractor import ListLookupExtractor
from graph_rag_pipeline.extractors.obligation_extractor import ObligationExtractor
from graph_rag_pipeline.extractors.penalty_extractor import PenaltyExtractor


def run_domain_extractor(
    intent: str,
    question: str,
    graph_query_layer: Any = None,
    evidence_candidates: list[dict] | None = None,
    context: dict | None = None,
) -> dict[str, Any]:
    context = context or {}
    extractor_cls = {
        "education_time": EducationTimeExtractor,
        "list_lookup": ListLookupExtractor,
        "obligation": ObligationExtractor,
        "safety_measure": ObligationExtractor,
        "exception": ExceptionExtractor,
        "applicability": ExceptionExtractor,
        "penalty": PenaltyExtractor,
    }.get(intent)
    if not extractor_cls:
        return {
            "handled": False,
            "intent": intent,
            "answer_level": "NOT_FOUND",
            "question_interpretation": "",
            "direct_answer": "",
            "extracted_items": [],
            "sources": [],
            "warnings": [],
            "next_checks": [],
            "confidence": "LOW",
            "failure_reason": "no_registered_extractor",
            "block_random_fallback": False,
        }
    try:
        return extractor_cls(question, graph_query_layer, evidence_candidates or [], context).run()
    except Exception as exc:  # noqa: BLE001
        return {
            "handled": False,
            "intent": intent,
            "answer_level": "NOT_FOUND",
            "question_interpretation": "",
            "direct_answer": "",
            "extracted_items": [],
            "sources": [],
            "warnings": [],
            "next_checks": [],
            "confidence": "LOW",
            "failure_reason": f"{exc.__class__.__name__}: {exc}",
            "block_random_fallback": False,
        }

