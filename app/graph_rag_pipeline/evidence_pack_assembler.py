#!/usr/bin/env python
"""Evidence pack assembler built on the read-only graph query layer.

This module creates structured evidence packs only. It does not generate
natural-language answers and does not call an LLM.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from graph_rag_pipeline.graph_query_layer import GraphQueryLayer


RULE_CENTERED_INTENTS = {
    "obligation_check",
    "obligation_penalty_chain",
    "safety_measure_lookup",
    "education_time_lookup",
    "appointment_requirement",
    "document_requirement",
    "penalty_lookup",
    "applicability_check",
    "definition_lookup",
}
LISTITEM_CENTERED_INTENTS = {"inspection_requirement", "list_lookup", "education_content_lookup"}
MIXED_INTENTS = {"education_time_lookup", "inspection_requirement", "safety_measure_lookup"}


def preview_text(value: Any, limit: int = 500) -> Any:
    if isinstance(value, str):
        text = value.replace("\r", " ").replace("\n", " ").strip()
        return text[: limit - 3] + "..." if len(text) > limit else text
    if isinstance(value, list):
        return [preview_text(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: preview_text(v, limit) for k, v in value.items()}
    return value


def first_label(labels: Any) -> str:
    if isinstance(labels, list) and labels:
        return str(labels[0])
    if isinstance(labels, str):
        return labels
    return ""


def anchor_id(anchor: dict[str, Any] | None) -> str:
    if not anchor:
        return ""
    for key in (
        "article_id",
        "paragraph_id",
        "item_id",
        "subitem_id",
        "logical_row_id",
        "logical_cell_id",
        "note_id",
        "annex_id",
        "addendum_id",
        "heading_id",
        "law_version_id",
    ):
        if anchor.get(key):
            return str(anchor[key])
    return ""


class EvidencePackAssembler:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).resolve()
        self.query_layer = GraphQueryLayer(self.root_dir)
        self.bundle_policy_edges = self._load_bundle_policy_edges()
        self.fine_grained_penalty_edges = self._load_fine_grained_penalty_edges()

    def close(self):
        self.query_layer.close()

    def _load_bundle_policy_edges(self) -> list[dict[str, str]]:
        candidates = [
            self.root_dir / "project" / "generated" / "legal_bundle_policy" / "legal_bundle_edges.csv",
            self.root_dir / "generated" / "legal_bundle_policy" / "legal_bundle_edges.csv",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    return list(csv.DictReader(f))
            except Exception:
                return []
        return []

    def _load_fine_grained_penalty_edges(self) -> list[dict[str, str]]:
        candidates = [
            self.root_dir / "project" / "generated_v4_current_strict" / "fine_grained" / "fine_grained_penalty_edges.csv",
            self.root_dir / "generated_v4_current_strict" / "fine_grained" / "fine_grained_penalty_edges.csv",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    return list(csv.DictReader(f))
            except Exception:
                return []
        return []

    def assemble(self, query: str, intent: str, limit: int = 5) -> dict:
        try:
            if intent in MIXED_INTENTS:
                return self.assemble_mixed_pack(query, intent, limit)
            if intent in LISTITEM_CENTERED_INTENTS:
                return self.assemble_listitem_pack(query, intent, max(limit, 10))
            return self.assemble_rule_pack(query, intent, limit)
        except Exception as exc:  # noqa: BLE001
            return {
                "query": query,
                "intent": intent,
                "pack_type": "error",
                "status": "ERROR",
                "evidence_readiness": "NOT_READY",
                "primary_evidence": [],
                "supporting_evidence": [],
                "citation_candidates": [],
                "warnings": [
                    {
                        "warning_type": "ASSEMBLY_ERROR",
                        "severity": "high",
                        "message": f"{type(exc).__name__}: {exc}",
                        "related_id": "",
                    }
                ],
                "missing_evidence": [],
                "debug": {
                    "candidate_count": 0,
                    "source": "neo4j_graph.v1",
                    "query_layer": "GraphQueryLayer",
                    "llm_used": False,
                },
            }

    def assemble_rule_pack(self, query: str, intent: str, limit: int = 5) -> dict:
        search_limit = max(limit * 4, 20) if intent in {"education_time_lookup", "obligation_penalty_chain"} else limit
        candidates = self.query_layer.search_rules_by_intent_keywords(query, intent, search_limit)
        if not candidates and intent == "education_time_lookup":
            candidates = [
                {"rule_id": (row.get("rule") or {}).get("rule_id"), "score": 1}
                for row in self.query_layer.get_education_time_evidence(limit)
                if (row.get("rule") or {}).get("rule_id")
            ]
        if not candidates and intent == "penalty_lookup":
            candidates = [
                {"rule_id": (row.get("penalty_rule") or {}).get("rule_id"), "score": 1}
                for row in self.query_layer.get_penalty_evidence(limit)
                if (row.get("penalty_rule") or {}).get("rule_id")
            ]
        if not candidates and intent == "applicability_check":
            candidates = [
                {"rule_id": row.get("rule_id"), "score": 1}
                for row in self.query_layer.get_exception_evidence(limit)
                if row.get("rule_id")
            ]
        if not candidates and intent in {"appointment_requirement", "document_requirement", "obligation_check", "obligation_penalty_chain"}:
            candidates = [
                {"rule_id": row.get("rule_id"), "score": 1}
                for row in self.query_layer.get_requirement_evidence(limit)
                if row.get("rule_id")
            ]
        rule_candidates = [c for c in candidates if c.get("rule_id")]
        evidence_items = []
        for candidate in rule_candidates[:search_limit]:
            pack = self.query_layer.get_rule_evidence_pack_by_rule_id(candidate["rule_id"])
            if not pack.get("found"):
                continue
            evidence_items.append(self._rule_evidence_item(pack, candidate))
        if intent == "education_time_lookup":
            evidence_items.sort(key=lambda item: self._education_time_alignment_score(item, query), reverse=True)
            evidence_items = evidence_items[:limit]
        if intent == "obligation_check" and "위험성평가" in query:
            evidence_items.sort(key=lambda item: self._risk_assessment_alignment_score(item), reverse=True)
        return self._finalize_pack(query, intent, "rule_centered", evidence_items, [])

    def assemble_listitem_pack(self, query: str, intent: str, limit: int = 10) -> dict:
        rows = []
        if intent in {"inspection_requirement", "list_lookup"}:
            rows = self.query_layer.get_inspection_list_evidence(max(limit * 3, limit))
            rows = [self._normalize_inspection_listitem_row(row) for row in rows]
        if not rows:
            rows = self.query_layer.get_listitem_evidence(query, limit)
        evidence_items = [self._listitem_evidence_item(row) for row in rows]
        if intent in {"inspection_requirement", "list_lookup"}:
            evidence_items.sort(key=lambda item: item.get("listitem_score", 0), reverse=True)
            evidence_items = evidence_items[:limit]
        return self._finalize_pack(query, intent, "listitem_centered", evidence_items, [])

    def assemble_mixed_pack(self, query: str, intent: str, limit: int = 5) -> dict:
        rule_pack = self.assemble_rule_pack(query, intent, limit)
        list_pack = self.assemble_listitem_pack(query, intent, max(limit, 10))
        if intent == "inspection_requirement":
            primary = list_pack["primary_evidence"]
            supporting = rule_pack["primary_evidence"]
        elif intent == "education_time_lookup":
            education_supporting = self._education_time_supporting_evidence(query, max(limit * 2, 8))
            combined = rule_pack["primary_evidence"] + education_supporting
            combined.sort(key=lambda item: self._education_time_alignment_score(item, query), reverse=True)
            primary = combined[:limit]
            primary_keys = {self._evidence_identity(item) for item in primary}
            supporting = [
                item for item in combined[limit:] + list_pack["primary_evidence"][:3]
                if self._evidence_identity(item) not in primary_keys
            ]
        else:
            primary = rule_pack["primary_evidence"]
            supporting = list_pack["primary_evidence"][:5]
        return self._finalize_pack(query, intent, "mixed", primary, supporting)

    def format_citation_candidates(self, evidence_items: list[dict]) -> list[dict]:
        citations: list[dict] = []
        seen: set[tuple[str, str, str, str]] = set()
        for item in evidence_items:
            law_name = item.get("law_name") or ""
            article_no = item.get("article_no") or ""
            annex_title = item.get("annex_title") or item.get("resolved_annex_title") or ""
            source_anchor = item.get("source_anchor") or {}
            anchor_label = source_anchor.get("label") or first_label(item.get("anchor_label")) or ""
            source_anchor_id = source_anchor.get("id") or ""
            source_preview = (
                item.get("source_text_preview")
                or source_anchor.get("source_text_preview")
                or preview_text(item.get("source_text") or item.get("item_text") or "")
            )
            if law_name and article_no and annex_title:
                citation_text = f"{law_name} {article_no} / {annex_title}"
            elif law_name and article_no:
                citation_text = f"{law_name} {article_no}"
            elif law_name and annex_title:
                citation_text = f"{law_name} {annex_title}"
            elif anchor_label or source_anchor_id:
                citation_text = f"{anchor_label}:{source_anchor_id}"
            else:
                citation_text = ""
            key = (law_name, article_no, annex_title, source_anchor_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "law_name": law_name,
                    "article_no": article_no,
                    "paragraph_no": item.get("paragraph_no") or "",
                    "item_no": item.get("item_no") or "",
                    "annex_title": annex_title,
                    "source_anchor_label": anchor_label,
                    "source_anchor_id": source_anchor_id,
                    "source_text_preview": source_preview,
                    "citation_text": citation_text,
                }
            )
        return citations

    def build_warnings(self, evidence_items: list[dict], intent: str, query: str = "") -> list[dict]:
        warnings: list[dict] = []
        for item in evidence_items:
            related_id = item.get("rule_id") or item.get("list_item_id") or ""
            if item.get("needs_review") in {True, "true", "TRUE"}:
                warnings.append(
                    {
                        "warning_type": "NEEDS_REVIEW",
                        "severity": "medium",
                        "message": "Evidence item is marked needs_review.",
                        "related_id": related_id,
                    }
                )
            if item.get("rule_type") == "UNKNOWN" or item.get("rule_subtype") == "UNKNOWN":
                warnings.append(
                    {
                        "warning_type": "UNKNOWN_RULE_TYPE",
                        "severity": "medium",
                        "message": "Rule type or subtype is UNKNOWN.",
                        "related_id": related_id,
                    }
                )
            if not item.get("source_anchor") and item.get("evidence_kind") == "list_item":
                warnings.append(
                    {
                        "warning_type": "SOURCE_ANCHOR_MISSING",
                        "severity": "high",
                        "message": "ListItem evidence does not include a source anchor.",
                        "related_id": related_id,
                    }
                )
            if (
                intent == "education_time_lookup"
                and item.get("evidence_kind") == "rule"
                and item.get("rule_type") != "THRESHOLD"
                and not item.get("thresholds")
            ):
                warnings.append(
                    {
                        "warning_type": "THRESHOLD_MISSING",
                        "severity": "medium",
                        "message": "Education time evidence candidate has no threshold.",
                        "related_id": related_id,
                    }
                )
            if intent == "obligation_check" and item.get("evidence_kind") == "rule":
                text = " ".join(str(item.get(k) or "") for k in ("source_text", "source_text_preview"))
                if "위험성평가" in text and self._risk_assessment_alignment_score(item) < 2:
                    warnings.append(
                        {
                            "warning_type": "WEAK_RISK_ASSESSMENT_ALIGNMENT",
                            "severity": "medium",
                            "message": "Risk-assessment query candidate lacks result/worker/notice terms.",
                            "related_id": related_id,
                        }
                    )
            if intent == "penalty_lookup" and item.get("evidence_kind") == "rule" and not item.get("related_rules"):
                warnings.append(
                    {
                        "warning_type": "RELATED_RULE_MISSING",
                        "severity": "medium",
                        "message": "Penalty evidence has no related obligation/prohibition rule.",
                        "related_id": related_id,
                    }
                )
            if intent == "applicability_check" and item.get("evidence_kind") == "rule":
                if not (item.get("exceptions") or item.get("thresholds") or item.get("temporal_rules") or item.get("entities")):
                    warnings.append(
                        {
                            "warning_type": "APPLICABILITY_CONTEXT_WEAK",
                            "severity": "medium",
                            "message": "Applicability candidate lacks exception/threshold/temporal/entity evidence.",
                            "related_id": related_id,
                        }
                    )
        if len(evidence_items) > 8:
            warnings.append(
                {
                    "warning_type": "TOP_K_AMBIGUITY",
                    "severity": "low",
                    "message": "Many evidence candidates were found; top-k ambiguity is possible.",
                    "related_id": "",
                }
            )
        if intent in {"inspection_requirement", "list_lookup", "education_content_lookup"}:
            warnings.append(
                {
                    "warning_type": "LISTITEM_PATH_USED",
                    "severity": "low",
                    "message": "Using ITEM_RESOLVES_TO because direct HAS_LIST_ITEM coverage is limited.",
                    "related_id": "",
                }
            )
        if self._is_risk_assessment_notice_query(query, intent) and not self._has_direct_risk_assessment_notice_evidence(
            evidence_items
        ):
            warnings.append(
                {
                    "warning_type": "DIRECT_EVIDENCE_NOT_FOUND",
                    "severity": "high",
                    "message": (
                        "현재 KB에서는 해당 의무를 직접 뒷받침하는 조문 근거가 확인되지 않았으며, "
                        "간접 근거만 확인됩니다."
                    ),
                    "related_id": "",
                    "reference": {
                        "audit_report": (
                            "graph_rag_knowledgement/neo4j_load/evidence_traversal/"
                            "risk_assessment_notice_source_coverage_audit.txt"
                        ),
                        "audit_matches": (
                            "graph_rag_knowledgement/neo4j_load/evidence_traversal/"
                            "risk_assessment_notice_source_coverage_matches.csv"
                        ),
                        "source_coverage_judgment": "ONLY_INDIRECT_EVIDENCE_FOUND",
                    },
                }
            )
        return warnings

    def build_missing_evidence(self, evidence_items: list[dict], intent: str, query: str = "") -> list[dict]:
        missing: list[dict] = []
        if not evidence_items:
            return [
                {
                    "missing_type": "NO_PRIMARY_EVIDENCE",
                    "message": "No primary evidence candidates were found.",
                    "severity": "high",
                }
            ]
        if intent == "education_time_lookup" and not any(
            item.get("thresholds") or item.get("rule_type") == "THRESHOLD" or item.get("evidence_kind") == "annex_logical_time"
            for item in evidence_items
        ):
            missing.append(
                {
                    "missing_type": "THRESHOLD",
                    "message": "No threshold evidence found for education time query.",
                    "severity": "high",
                }
            )
        if intent == "document_requirement" and not any(item.get("requirements") for item in evidence_items):
            missing.append(
                {
                    "missing_type": "REQUIREMENT",
                    "message": "No requirement evidence found for document requirement query.",
                    "severity": "medium",
                }
            )
        if intent == "penalty_lookup":
            if not any(item.get("rule_type") == "PENALTY" or "PENALTY" in str(item.get("rule_subtype")) for item in evidence_items):
                missing.append(
                    {
                        "missing_type": "PENALTY_RULE",
                        "message": "No penalty rule evidence found.",
                        "severity": "high",
                    }
                )
            if not any(item.get("related_rules") for item in evidence_items):
                missing.append(
                    {
                        "missing_type": "RELATED_VIOLATION_RULE",
                        "message": "No related obligation/prohibition rule found for penalty evidence.",
                        "severity": "medium",
                    }
                )
        if intent in {"inspection_requirement", "list_lookup", "education_content_lookup"}:
            if not any(item.get("evidence_kind") == "list_item" for item in evidence_items):
                missing.append(
                    {
                        "missing_type": "LIST_ITEM",
                        "message": "No ListItem evidence found.",
                        "severity": "high",
                    }
                )
            if not any(item.get("source_anchor") for item in evidence_items):
                missing.append(
                    {
                        "missing_type": "ITEM_RESOLVES_TO_SOURCE_ANCHOR",
                        "message": "No ITEM_RESOLVES_TO source anchor found.",
                        "severity": "high",
                    }
                )
        if intent == "applicability_check" and not any(
            item.get("exceptions") or item.get("thresholds") or item.get("temporal_rules") or item.get("entities")
            for item in evidence_items
        ):
            missing.append(
                {
                    "missing_type": "APPLICABILITY_CONDITION",
                    "message": "No exception/threshold/temporal/entity evidence found.",
                    "severity": "medium",
                }
            )
        if self._is_risk_assessment_notice_query(query, intent) and not self._has_direct_risk_assessment_notice_evidence(
            evidence_items
        ):
            missing.append(
                {
                    "missing_type": "DIRECT_OBLIGATION_SOURCE",
                    "message": (
                        "Direct source wording for risk-assessment result notice/disclosure to workers was not found."
                    ),
                    "severity": "high",
                    "reference": {
                        "audit_report": (
                            "graph_rag_knowledgement/neo4j_load/evidence_traversal/"
                            "risk_assessment_notice_source_coverage_audit.txt"
                        ),
                        "audit_matches": (
                            "graph_rag_knowledgement/neo4j_load/evidence_traversal/"
                            "risk_assessment_notice_source_coverage_matches.csv"
                        ),
                    },
                }
            )
        return missing

    def _is_risk_assessment_notice_query(self, query: str, intent: str) -> bool:
        if intent != "obligation_check":
            return False
        text = query or ""
        has_core = all(term in text for term in ("위험성평가", "결과", "근로자"))
        has_notice = any(term in text for term in ("알려", "알림", "알리", "고지", "주지", "통보"))
        return has_core and has_notice

    def _has_direct_risk_assessment_notice_evidence(self, evidence_items: list[dict]) -> bool:
        for item in evidence_items:
            parts = [
                item.get("source_text"),
                item.get("source_text_preview"),
                item.get("source_context_text"),
                item.get("source_context_text_preview"),
            ]
            for requirement in item.get("requirements") or []:
                parts.extend(requirement.values() if isinstance(requirement, dict) else [requirement])
            source_anchor = item.get("source_anchor") or {}
            if isinstance(source_anchor, dict):
                parts.extend(source_anchor.values())
            for anchor in item.get("source_anchors") or []:
                if isinstance(anchor, dict):
                    parts.extend(anchor.values())
            text = " ".join(str(part or "") for part in parts)
            if (
                "위험성평가" in text
                and "결과" in text
                and "근로자" in text
                and any(term in text for term in ("알리", "알림", "알려", "고지", "주지", "통보"))
            ):
                return True
        return False

    def _has_indirect_risk_assessment_evidence(self, evidence_items: list[dict]) -> bool:
        for item in evidence_items:
            text = " ".join(
                str(item.get(k) or "")
                for k in (
                    "source_text",
                    "source_text_preview",
                    "source_context_text",
                    "source_context_text_preview",
                    "law_name",
                    "article_no",
                    "annex_title",
                )
            )
            if "위험성평가" in text:
                return True
        return False

    def _evidence_readiness(
        self,
        query: str,
        intent: str,
        primary_evidence: list[dict],
        all_evidence: list[dict],
        warnings: list[dict],
        missing: list[dict],
    ) -> str:
        if not primary_evidence:
            return "NOT_READY"
        if self._is_risk_assessment_notice_query(query, intent):
            if self._has_direct_risk_assessment_notice_evidence(all_evidence):
                return "READY_WITH_WARNINGS" if warnings or missing else "READY"
            if self._has_indirect_risk_assessment_evidence(all_evidence):
                return "INDIRECT_ONLY"
            return "LIMITED_EVIDENCE"
        if any(item.get("severity") == "high" for item in warnings + missing):
            return "LIMITED_EVIDENCE"
        if warnings or missing:
            return "READY_WITH_WARNINGS"
        return "READY"

    def _risk_assessment_alignment_score(self, item: dict) -> int:
        text = " ".join(str(item.get(k) or "") for k in ("source_text", "source_text_preview"))
        groups = (
            ("위험성평가",),
            ("결과",),
            ("근로자",),
            ("알리", "알림", "고지", "주지", "통보", "참여", "공유"),
        )
        return sum(1 for group in groups if any(term in text for term in group))

    def _evidence_identity(self, item: dict) -> str:
        source_anchor = item.get("source_anchor") or {}
        return "|".join(
            str(part or "")
            for part in (
                item.get("rule_id"),
                item.get("list_item_id"),
                source_anchor.get("id") if isinstance(source_anchor, dict) else "",
                item.get("annex_title") or item.get("resolved_annex_title"),
                item.get("source_text_preview") or item.get("item_text"),
            )
        )

    def _education_time_alignment_score(self, item: dict, query: str) -> int:
        source_anchor = item.get("source_anchor") or {}
        parts = [
            item.get("law_name"),
            item.get("article_no"),
            item.get("annex_title"),
            item.get("resolved_annex_title"),
            item.get("source_text"),
            item.get("source_text_preview"),
            item.get("source_context_text"),
            item.get("source_context_text_preview"),
            item.get("item_text"),
            source_anchor.get("source_text") if isinstance(source_anchor, dict) else "",
            source_anchor.get("source_text_preview") if isinstance(source_anchor, dict) else "",
        ]
        if item.get("logical_row"):
            parts.append((item.get("logical_row") or {}).get("source_text"))
        for cell in item.get("logical_cells") or []:
            if isinstance(cell, dict):
                parts.append(cell.get("source_text"))
        text = " ".join(str(part or "") for part in parts)
        compact = text.replace(" ", "")
        query_compact = str(query or "").replace(" ", "")
        score = int(item.get("score") or item.get("listitem_score") or 0)

        boosts = (
            ("안전보건교육교육과정별교육시간", 30),
            ("별표4", 28),
            ("교육시간", 24),
            ("제26조", 18),
            ("교육대상", 16),
            ("교육구분", 16),
            ("정기교육", 12),
            ("안전보건교육", 10),
            ("시간", 8),
        )
        for term, weight in boosts:
            if term in compact:
                score += weight

        for target in ("비사무직", "사무직", "관리감독자", "특별교육", "채용시", "채용"):
            if target in query_compact and target in compact:
                score += 18

        weak_training_provider_terms = ("교육교재", "인력", "시설", "장비", "교육기관")
        has_time_basis = any(term in compact for term in ("교육시간", "별표4", "제26조", "교육대상", "교육구분"))
        if any(term in compact for term in weak_training_provider_terms) and not has_time_basis:
            score -= 35
        return score

    def _education_time_supporting_evidence(self, query: str, limit: int) -> list[dict]:
        candidates = self.query_layer.get_education_time_pack_candidates(query, limit)
        supporting = []
        for row in candidates.get("annex_logical_evidence", [])[:limit]:
            annex = row.get("annex") or {}
            logical_row = row.get("logical_row") or {}
            cells = row.get("logical_cells") or []
            joined = " ".join(str(cell.get("source_text") or "") for cell in cells)
            full_text = " ".join(
                str(part or "")
                for part in (
                    annex.get("annex_title"),
                    logical_row.get("source_text"),
                    joined,
                )
            )
            score = 0
            if "교육" in full_text:
                score += 5
            if "시간" in full_text:
                score += 5
            if "별표 4" in full_text or "별표4" in full_text:
                score += 15
            if "교육시간" in full_text:
                score += 15
            if "교육대상" in full_text or "교육구분" in full_text:
                score += 10
            for target in ("비사무직", "사무직", "관리감독자", "특별교육", "채용"):
                if target in query and target in full_text:
                    score += 12
            if any(ch.isdigit() for ch in joined):
                score += 3
            supporting.append(
                {
                    "evidence_kind": "annex_logical_time",
                    "law_name": annex.get("law_name"),
                    "article_no": "",
                    "annex_title": annex.get("annex_title"),
                    "resolved_annex_title": annex.get("annex_title"),
                    "source_anchor": {
                        "label": "LogicalRow",
                        "id": logical_row.get("logical_row_id"),
                        "source_text": logical_row.get("source_text"),
                        "source_text_preview": preview_text(logical_row.get("source_text") or joined),
                    },
                    "logical_row": logical_row,
                    "logical_cells": cells,
                    "score": score,
                }
            )
        supporting.sort(key=lambda item: item.get("score", 0), reverse=True)
        return supporting[:limit]

    def _finalize_pack(
        self,
        query: str,
        intent: str,
        pack_type: str,
        primary_evidence: list[dict],
        supporting_evidence: list[dict],
    ) -> dict:
        legal_chains, legal_chain_evidence = self.build_legal_chains(primary_evidence + supporting_evidence, intent)
        legal_bundle, bundle_supporting_evidence, bundle_candidate_evidence, bundle_edges = self.build_legal_bundle(
            query,
            intent,
            primary_evidence,
            supporting_evidence,
            legal_chain_evidence,
        )
        fine_chains, fine_chain_evidence = self.build_fine_grained_legal_chains(
            primary_evidence + supporting_evidence + bundle_supporting_evidence + bundle_candidate_evidence,
            legal_chain_evidence,
            intent,
            query,
        )
        if fine_chains:
            existing_chain_keys = {
                tuple(chain.get("chain_refs") or [chain.get("source_ref"), chain.get("target_ref")])
                for chain in legal_chains
                if isinstance(chain, dict)
            }
            for chain in fine_chains:
                key = tuple(chain.get("chain_refs") or [chain.get("source_ref"), chain.get("target_ref")])
                if key not in existing_chain_keys:
                    legal_chains.append(chain)
                    existing_chain_keys.add(key)
        if fine_chain_evidence:
            seen_chain_evidence = {self._evidence_identity(item) for item in legal_chain_evidence}
            for item in fine_chain_evidence:
                identity = self._evidence_identity(item)
                if identity not in seen_chain_evidence:
                    legal_chain_evidence.append(item)
                    seen_chain_evidence.add(identity)
        if bundle_supporting_evidence or bundle_candidate_evidence:
            existing = {self._evidence_identity(item) for item in primary_evidence + supporting_evidence}
            for item in bundle_supporting_evidence + bundle_candidate_evidence:
                identity = self._evidence_identity(item)
                if identity not in existing:
                    supporting_evidence.append(item)
                    existing.add(identity)
        if legal_chain_evidence:
            existing = {self._evidence_identity(item) for item in primary_evidence + supporting_evidence}
            for item in legal_chain_evidence:
                identity = self._evidence_identity(item)
                if identity not in existing:
                    supporting_evidence.append(item)
                    existing.add(identity)
        confirmed_penalties = [item for item in legal_chain_evidence if item.get("candidate_status") == "CONFIRMED"]
        rule_based_candidate_penalties = [
            item for item in legal_chain_evidence if item.get("candidate_status") == "RULE_BASED_CANDIDATE"
        ]
        text_reference_candidate_penalties = [
            item for item in legal_chain_evidence if item.get("candidate_status") == "TEXT_REFERENCE_CANDIDATE"
        ]
        weak_candidate_penalties = [item for item in legal_chain_evidence if item.get("candidate_status") == "WEAK_CANDIDATE"]
        all_evidence = primary_evidence + supporting_evidence
        fine_chain_metrics = self._fine_chain_debug_metrics(legal_chains)
        citations = self.format_citation_candidates(all_evidence)
        warnings = self.build_warnings(all_evidence, intent, query)
        missing = self.build_missing_evidence(all_evidence, intent, query)
        evidence_readiness = self._evidence_readiness(query, intent, primary_evidence, all_evidence, warnings, missing)
        if not primary_evidence:
            status = "NO_EVIDENCE"
        elif warnings or missing or not citations:
            if not citations:
                warnings.append(
                    {
                        "warning_type": "CITATION_CANDIDATE_MISSING",
                        "severity": "medium",
                        "message": "No citation candidates could be generated.",
                        "related_id": "",
                    }
                )
            status = "OK_WITH_WARNINGS"
        else:
            status = "OK"
        return {
            "query": query,
            "intent": intent,
            "pack_type": pack_type,
            "status": status,
            "evidence_readiness": evidence_readiness,
            "primary_evidence": preview_text(primary_evidence),
            "supporting_evidence": preview_text(supporting_evidence),
            "legal_bundle": preview_text(legal_bundle),
            "legal_bundle_supporting_evidence": preview_text(bundle_supporting_evidence),
            "candidate_evidence": preview_text(bundle_candidate_evidence),
            "legal_bundle_edges": preview_text(bundle_edges),
            "legal_chains": preview_text(legal_chains),
            "linked_penalty_evidences": preview_text(legal_chain_evidence),
            "confirmed_penalties": preview_text(confirmed_penalties),
            "rule_based_candidate_penalties": preview_text(rule_based_candidate_penalties),
            "text_reference_candidate_penalties": preview_text(text_reference_candidate_penalties),
            "weak_candidate_penalties": preview_text(weak_candidate_penalties),
            "candidate_penalties": preview_text(rule_based_candidate_penalties + text_reference_candidate_penalties + weak_candidate_penalties),
            "citation_candidates": preview_text(citations),
            "warnings": warnings,
            "missing_evidence": missing,
            "debug": {
                "candidate_count": len(primary_evidence),
                "supporting_count": len(supporting_evidence),
                "legal_bundle_supporting_count": len(bundle_supporting_evidence),
                "candidate_evidence_count": len(bundle_candidate_evidence),
                "legal_bundle_edge_count": len(bundle_edges),
                "legal_chain_count": len(legal_chains),
                "linked_penalty_count": len(legal_chain_evidence),
                **fine_chain_metrics,
                "rule_based_candidate_penalty_count": len(rule_based_candidate_penalties),
                "text_reference_candidate_penalty_count": len(text_reference_candidate_penalties),
                "weak_candidate_penalty_count": len(weak_candidate_penalties),
                "source": "neo4j_graph.v1",
                "query_layer": "GraphQueryLayer",
                "llm_used": False,
            },
        }

    def _rule_evidence_item(self, pack: dict, candidate: dict) -> dict:
        rule = pack.get("rule") or {}
        source_anchors = pack.get("source_anchors") or []
        anchor = source_anchors[0] if source_anchors else {}
        return {
            "evidence_kind": "rule",
            "rule_id": rule.get("rule_id") or candidate.get("rule_id"),
            "rule_type": rule.get("rule_type") or candidate.get("rule_type"),
            "rule_subtype": rule.get("rule_subtype") or candidate.get("rule_subtype"),
            "law_name": rule.get("law_name") or candidate.get("law_name"),
            "article_no": rule.get("article_no") or candidate.get("article_no"),
            "annex_title": rule.get("annex_title") or candidate.get("annex_title"),
            "source_text": rule.get("source_text") or candidate.get("source_text"),
            "source_text_preview": preview_text(rule.get("source_text") or candidate.get("source_text") or ""),
            "requirements": pack.get("requirements", []),
            "thresholds": pack.get("thresholds", []),
            "exceptions": pack.get("exceptions", []),
            "temporal_rules": pack.get("temporal_rules", []),
            "entities": pack.get("entities", []),
            "list_items": pack.get("list_items", []),
            "source_nodes": pack.get("source_nodes", []),
            "source_anchors": source_anchors,
            "source_anchor": {
                "label": first_label(anchor.get("_labels")),
                "id": anchor_id(anchor),
                "source_text_preview": preview_text(anchor.get("source_text") or anchor.get("text") or ""),
            }
            if anchor
            else {},
            "related_rules": pack.get("related_rules", []),
            "confidence": rule.get("confidence"),
            "needs_review": rule.get("needs_review", False),
            "score": candidate.get("score"),
            "source_reason": candidate.get("source_reason") or "",
            "score_breakdown": candidate.get("score_breakdown") or [],
        }

    def build_legal_chains(self, evidence_items: list[dict], intent: str) -> tuple[list[dict], list[dict]]:
        if intent not in {"obligation_penalty_chain", "obligation_check", "safety_measure_lookup", "penalty_lookup"}:
            return [], []
        chains: list[dict] = []
        penalty_items: list[dict] = []
        seen_penalties: set[str] = set()
        for item in evidence_items:
            if self._is_penalty_evidence(item):
                continue
            source_law = item.get("law_name") or ""
            source_article = item.get("article_no") or ""
            source_rule_id = item.get("rule_id") or ""
            related_penalties = self._penalty_items_from_related_rules(item)
            if not related_penalties:
                related_penalties = self.query_layer.find_penalty_rules_for_violation(
                    source_law,
                    source_article,
                    source_rule_id,
                    5,
                )
                for penalty in related_penalties:
                    penalty["match_type"] = penalty.get("match_type") or "ARTICLE_REFERENCE"
                    penalty["confidence"] = "medium"
                    penalty["is_confirmed"] = bool(penalty.get("is_confirmed"))
            if not related_penalties:
                continue
            chain_penalties = []
            for penalty in related_penalties[:3]:
                penalty_item = self._normalize_penalty_chain_item(penalty, item)
                identity = self._evidence_identity(penalty_item)
                chain_penalties.append(penalty_item)
                if identity not in seen_penalties:
                    penalty_items.append(penalty_item)
                    seen_penalties.add(identity)
                corporate_penalties = self.query_layer.find_corporate_penalty_for_penalty_law(
                    penalty_item.get("law_name"),
                    penalty_item.get("article_no"),
                    2,
                )
                for corporate in corporate_penalties:
                    corporate_item = self._normalize_penalty_chain_item(corporate, penalty_item)
                    corporate_item["chain_role"] = "corporate_penalty"
                    corporate_item["relation_type"] = "CORPORATE_PENALTY_BY"
                    corporate_item["candidate_status"] = "RULE_BASED_CANDIDATE"
                    corporate_item["confidence"] = corporate.get("confidence") or "medium"
                    corporate_item["review_reason"] = corporate.get("review_reason") or ""
                    corporate_item["needs_review"] = True
                    corporate_item["is_confirmed"] = False
                    chain_penalties.append(corporate_item)
                    corporate_identity = self._evidence_identity(corporate_item)
                    if corporate_identity not in seen_penalties:
                        penalty_items.append(corporate_item)
                        seen_penalties.add(corporate_identity)
            chains.append(
                {
                    "source": {
                        "law_name": source_law,
                        "article_no": source_article,
                        "rule_id": source_rule_id,
                        "rule_type": item.get("rule_type") or "",
                        "rule_subtype": item.get("rule_subtype") or "",
                        "source_text_preview": item.get("source_text_preview") or "",
                    },
                    "penalties": chain_penalties,
                    "edges": self._legal_chain_edges(item, chain_penalties),
                    "chain_type": "DOCUMENT_RULE_TO_PENALTY",
                    "chain_basis": "RELATED_RULE_OR_PENALTY_TEXT_REFERENCE",
                }
            )
        return chains, penalty_items

    def build_legal_bundle(
        self,
        query: str,
        intent: str,
        primary_evidence: list[dict],
        supporting_evidence: list[dict],
        legal_chain_evidence: list[dict],
    ) -> tuple[dict, list[dict], list[dict], list[dict]]:
        if intent not in {"obligation_penalty_chain", "obligation_check", "safety_measure_lookup", "penalty_lookup"}:
            return {}, [], [], []

        evidence_items = primary_evidence + supporting_evidence + legal_chain_evidence
        bundle = {
            "primary_obligation": [],
            "secondary_obligation": [],
            "health_obligation": [],
            "contractor_obligation": [],
            "detail_rule": [],
            "serious_accident_obligation": [],
            "penalty": [],
            "corporate_penalty": [],
            "definition_or_scope": [],
            "purpose_support": [],
            "administrative_fine": [],
            "procedure_or_management": [],
            "education_requirement": [],
            "appointment_requirement": [],
            "reporting_or_submission": [],
            "record_retention": [],
            "completion_policy": "Role-based legal bundle assembled from primary evidence, legal chains, and narrow completion rules. Candidate entries are conditional review aids, not confirmed legal conclusions.",
        }
        supporting: list[dict] = []
        candidates: list[dict] = []
        seen_refs: set[tuple[str, str]] = set()

        for item in evidence_items:
            ref = self._bundle_ref(item)
            if not ref:
                continue
            seen_refs.add(ref)
            slot = self._bundle_slot_for_ref(ref)
            if not slot:
                continue
            self._bundle_add(bundle, slot, item, "retrieved_or_chain", "CONFIRMED" if item.get("is_confirmed") else item.get("candidate_status") or "RETRIEVED")

        query_text = query or ""
        has_death = self._query_has_any(query_text, ("사망", "치사", "중대산업재해", "중대재해"))
        has_contract = self._query_has_any(query_text, ("도급", "수급", "관계수급인", "하청", "용역", "위탁", "원청", "도급사업주", "도급인", "혼재작업", "같은 장소"))
        has_health = self._query_has_any(query_text, ("보건", "건강장해", "유해물질", "화학물질", "질식", "밀폐공간", "분진", "소음", "진동", "고온", "저온", "방사선", "가스", "산소결핍", "중독", "감염", "유해인자"))
        has_serious = self._query_has_any(query_text, ("중대재해", "중대산업재해", "경영책임자", "대표이사", "안전보건 확보의무", "안전보건관리체계"))
        has_scope = self._query_has_any(query_text, ("상시근로자", "적용범위", "적용 범위", "50명", "오십명", "사업장", "사업 또는 사업장"))

        has_osh_obligation = any(ref in seen_refs for ref in {("산업안전보건법", "제38조"), ("산업안전보건법", "제39조")})
        has_sapa_chain = any(ref in seen_refs for ref in {("중대재해처벌법", "제4조"), ("중대재해처벌법", "제5조"), ("중대재해처벌법", "제6조"), ("중대재해처벌법", "제7조")})

        requested_refs, matched_policy_edges = self._requested_refs_from_bundle_policy(
            query_text=query_text,
            intent=intent,
            seen_refs=seen_refs,
            has_death=has_death,
            has_contract=has_contract,
            has_health=has_health,
            has_serious=has_serious,
            has_scope=has_scope,
            has_sapa_chain=has_sapa_chain,
            has_osh_obligation=has_osh_obligation,
        )
        direct_refs = self._direct_bundle_completion_refs(
            query_text=query_text,
            seen_refs=seen_refs,
            has_death=has_death,
            has_contract=has_contract,
            has_health=has_health,
            has_serious=has_serious,
            has_scope=has_scope,
            has_sapa_chain=has_sapa_chain,
            has_osh_obligation=has_osh_obligation,
        )
        requested_refs.extend(direct_refs)

        requested_refs = list(dict.fromkeys(requested_refs))
        fetched = self._fetch_bundle_completion_items(requested_refs)
        for item in fetched:
            ref = self._bundle_ref(item)
            if not ref:
                continue
            slot = item.get("bundle_slot") or self._bundle_slot_for_ref(ref)
            status = item.get("candidate_status") or "BUNDLE_COMPLETION_CANDIDATE"
            self._bundle_add(bundle, slot, item, item.get("source_reason") or "bundle_completion", status)
            if status in {"SUPPORTING_DEFINITION", "TEXT_REFERENCE_CANDIDATE", "CONFIRMED"}:
                supporting.append(item)
            else:
                candidates.append(item)

        return bundle, supporting, candidates, matched_policy_edges

    def _query_has_any(self, query: str, terms: tuple[str, ...]) -> bool:
        return any(term in query for term in terms)

    def _direct_bundle_completion_refs(
        self,
        query_text: str,
        seen_refs: set[tuple[str, str]],
        has_death: bool,
        has_contract: bool,
        has_health: bool,
        has_serious: bool,
        has_scope: bool,
        has_sapa_chain: bool,
        has_osh_obligation: bool,
    ) -> list[tuple[str, str, str, str, str]]:
        requested: list[tuple[str, str, str, str, str]] = []
        osh = "산업안전보건법"
        sapa = "중대재해처벌법"

        def add(law: str, article: str, slot: str, reason: str, review: str) -> None:
            ref = (law, article)
            if ref in seen_refs:
                return
            requested.append((law, article, slot, reason, review))

        if has_health:
            add(
                osh,
                "제39조",
                "health_obligation",
                "bundle_policy_health_obligation_support",
                "보건·건강장해·질식·유해인자 등 보건 위험 키워드가 있는 경우에만 보건조치의무를 보조 근거로 검토합니다.",
            )

        if has_contract:
            for article in ("제63조", "제64조"):
                add(
                    osh,
                    article,
                    "contractor_obligation",
                    "bundle_policy_contractor_obligation_support",
                    "도급·수급·관계수급인·용역·위탁 등 도급 구조가 드러나는 경우에만 조건부로 검토합니다.",
                )
            add(
                sapa,
                "제5조",
                "serious_accident_obligation",
                "bundle_policy_contractor_obligation_support",
                "도급·용역·위탁 관계에서 중대재해처벌법상 안전보건 확보의무가 문제될 수 있어 조건부로 검토합니다.",
            )

        osh_duty_seen = has_osh_obligation or any(
            ref in seen_refs
            for ref in {
                (osh, "제38조"),
                (osh, "제39조"),
                (osh, "제63조"),
                (osh, "제64조"),
            }
        )
        penalty_context = has_death or has_serious or self._query_has_any(
            query_text,
            ("처벌", "벌칙", "벌금", "징역", "위반", "기소", "유죄", "법정형"),
        )
        if osh_duty_seen and penalty_context:
            add(
                osh,
                "제167조",
                "penalty",
                "bundle_policy_rule_based_candidate",
                "산업안전보건법상 안전·보건·도급 의무 위반과 사망 또는 처벌 쟁점이 함께 있는 경우 처벌 조문 후보로 검토합니다.",
            )
            add(
                osh,
                "제168조",
                "penalty",
                "bundle_policy_secondary_penalty_support",
                "제168조는 세부 벌칙 후보입니다. 제167조와 달리 위반 유형에 따라 적용 여부가 달라져 후보로만 표시합니다.",
            )
            add(
                osh,
                "제173조",
                "corporate_penalty",
                "bundle_policy_rule_based_candidate",
                "법인·대표자·종업원 관계가 인정되는 경우 양벌규정으로 함께 검토될 수 있는 후보입니다.",
            )

        sapa_context = has_sapa_chain or has_serious or self._query_has_any(
            query_text,
            ("중대재해", "중대산업재해", "경영책임자", "대표이사", "종사자"),
        )
        if sapa_context:
            add(
                sapa,
                "제2조",
                "definition_or_scope",
                "bundle_policy_definition_support",
                "중대재해·중대산업재해·종사자·경영책임자 개념이 문제되는 경우 정의 조문을 보조 근거로 검토합니다.",
            )
            if has_death or self._query_has_any(query_text, ("예방", "생명", "신체", "안전권", "목적", "취지", "보호법익")):
                add(
                    sapa,
                    "제1조",
                    "purpose_support",
                    "bundle_policy_purpose_support",
                    "중대재해 예방, 생명·신체 보호 또는 입법 목적이 답변 맥락에 필요한 경우에만 보조 근거로 검토합니다.",
                )
            if has_scope:
                add(
                    sapa,
                    "제3조",
                    "definition_or_scope",
                    "bundle_policy_scope_support",
                    "적용범위·상시근로자·사업 또는 사업장 쟁점이 있을 때 보조 근거로 검토합니다.",
                )
            if penalty_context:
                add(
                    sapa,
                    "제6조",
                    "penalty",
                    "bundle_policy_rule_based_candidate",
                    "중대산업재해와 경영책임자 의무 위반이 함께 문제되는 경우 처벌 조문 후보로 검토합니다.",
                )
                add(
                    sapa,
                    "제7조",
                    "corporate_penalty",
                    "bundle_policy_rule_based_candidate",
                    "법인·기관 책임 여부에 따라 함께 검토될 수 있는 법인 처벌 후보입니다.",
                )

        if osh_duty_seen and self._query_has_any(query_text, ("산업재해 예방", "근로자 보호", "목적", "취지", "생명", "신체")):
            add(
                osh,
                "제1조",
                "purpose_support",
                "bundle_policy_purpose_support",
                "산업재해 예방·근로자 보호 또는 목적 조문이 필요한 경우 보조 근거로 검토합니다.",
            )

        return requested

    def _requested_refs_from_bundle_policy(
        self,
        query_text: str,
        intent: str,
        seen_refs: set[tuple[str, str]],
        has_death: bool,
        has_contract: bool,
        has_health: bool,
        has_serious: bool,
        has_scope: bool,
        has_sapa_chain: bool,
        has_osh_obligation: bool,
    ) -> tuple[list[tuple[str, str, str, str, str]], list[dict]]:
        allowed_slots = self._allowed_bundle_slots(intent, query_text)
        requested: list[tuple[str, str, str, str, str]] = []
        matched_edges: list[dict] = []
        if not self.bundle_policy_edges:
            return [], []

        for edge in self.bundle_policy_edges:
            source_ref = (
                self._normalize_policy_law_name(edge.get("source_law_name") or ""),
                self._normalize_article_no(edge.get("source_article_no") or ""),
            )
            target_law = self._normalize_policy_law_name(edge.get("target_law_name") or "")
            target_article = self._normalize_article_no(edge.get("target_article_no") or "")
            target_role = edge.get("target_role") or self._bundle_slot_for_ref((target_law, target_article))
            slot = self._slot_for_policy_role(target_role, edge.get("relation_type") or "")
            if slot not in allowed_slots:
                continue
            if source_ref not in seen_refs and not self._policy_edge_can_apply_without_source(edge, has_sapa_chain, has_osh_obligation):
                continue
            if not self._trigger_matches(
                edge.get("trigger_condition") or "",
                query_text,
                has_death,
                has_contract,
                has_health,
                has_serious,
                has_scope,
                has_sapa_chain,
            ):
                continue
            source_reason = self._source_reason_for_policy(edge)
            review_reason = edge.get("review_reason") or edge.get("policy_reason") or ""
            requested.append((target_law, target_article, slot, source_reason, review_reason))
            matched_edges.append(edge)
        return list(dict.fromkeys(requested)), matched_edges

    def _normalize_policy_law_name(self, law_name: str) -> str:
        if "중대재해" in law_name:
            return "중대재해처벌법"
        if "산업안전보건법" in law_name and "시행" not in law_name and "기준" not in law_name:
            return "산업안전보건법"
        return law_name

    def _slot_for_policy_role(self, role: str, relation_type: str) -> str:
        if role == "purpose" or relation_type == "PURPOSE_SUPPORT":
            return "purpose_support"
        if role in {"definition_or_scope"} or relation_type in {"LAW_DEFINITION_SUPPORT", "LAW_SCOPE_SUPPORT"}:
            return "definition_or_scope"
        if role in {
            "primary_obligation",
            "health_obligation",
            "contractor_obligation",
            "serious_accident_obligation",
            "detail_rule",
            "penalty",
            "corporate_penalty",
            "administrative_fine",
            "procedure_or_management",
            "education_requirement",
            "appointment_requirement",
            "reporting_or_submission",
            "record_retention",
        }:
            return role
        return self._bundle_slot_for_ref(("", ""))

    def _allowed_bundle_slots(self, intent: str, query_text: str) -> set[str]:
        slots = {"primary_obligation", "detail_rule"}
        if intent in {"obligation_penalty_chain", "penalty_lookup"}:
            slots |= {"penalty", "corporate_penalty"}
        if intent in {"obligation_penalty_chain", "obligation_check", "safety_measure_lookup"}:
            slots |= {"health_obligation", "contractor_obligation", "serious_accident_obligation"}
        if self._query_has_any(query_text, ("중대재해", "중대산업재해", "경영책임자", "대표이사", "사망")):
            slots |= {"serious_accident_obligation", "penalty", "corporate_penalty", "definition_or_scope"}
        if self._query_has_any(query_text, ("도급", "수급", "관계수급인", "하청", "위탁", "용역", "원청")):
            slots |= {"contractor_obligation"}
        if self._query_has_any(query_text, ("보건", "건강장해", "유해", "질식", "화학물질", "산소결핍", "중독", "밀폐공간")):
            slots |= {"health_obligation"}
        if self._query_has_any(query_text, ("목적", "취지", "보호법익")):
            slots |= {"purpose_support"}
        if self._query_has_any(query_text, ("정의", "종사자", "중대산업재해", "경영책임자")):
            slots |= {"definition_or_scope"}
        if self._query_has_any(query_text, ("적용", "적용범위", "상시근로자", "50명", "50명 미만", "사업장")):
            slots |= {"definition_or_scope"}
        if self._query_has_any(query_text, ("과태료",)):
            slots |= {"administrative_fine"}
        if self._query_has_any(query_text, ("교육",)):
            slots |= {"education_requirement"}
        if self._query_has_any(query_text, ("선임", "지정", "자격")):
            slots |= {"appointment_requirement"}
        if self._query_has_any(query_text, ("보고", "제출", "신고", "통보")):
            slots |= {"reporting_or_submission"}
        if self._query_has_any(query_text, ("보존", "기록")):
            slots |= {"record_retention"}
        return slots

    def _policy_edge_can_apply_without_source(self, edge: dict, has_sapa_chain: bool, has_osh_obligation: bool) -> bool:
        source_law = self._normalize_policy_law_name(edge.get("source_law_name") or "")
        relation = edge.get("relation_type") or ""
        return (
            (has_sapa_chain and source_law == "중대재해처벌법" and relation in {"LAW_DEFINITION_SUPPORT", "LAW_SCOPE_SUPPORT", "PURPOSE_SUPPORT"})
            or (has_osh_obligation and source_law == "산업안전보건법" and relation in {"PURPOSE_SUPPORT"})
        )

    def _trigger_matches(
        self,
        trigger: str,
        query_text: str,
        has_death: bool,
        has_contract: bool,
        has_health: bool,
        has_serious: bool,
        has_scope: bool,
        has_sapa_chain: bool,
    ) -> bool:
        if not trigger:
            return True
        if "death_or_serious_accident" in trigger and (has_death or has_serious):
            return True
        if "penalty_intent" in trigger and self._query_has_any(query_text, ("처벌", "벌칙", "벌금", "징역", "양벌", "위반")):
            return True
        if "broad_penalty_bundle" in trigger and (has_death or has_serious):
            return True
        if "contractor_context" in trigger and has_contract:
            return True
        if "corporate_or_employer_context" in trigger and self._query_has_any(query_text, ("법인", "회사", "대표자", "대표이사", "사업주", "경영책임자", "양벌")):
            return True
        if "definition_keyword" in trigger and self._query_has_any(query_text, ("정의", "종사자", "중대산업재해", "경영책임자", "중대재해")):
            return True
        if "serious_accident_bundle" in trigger and has_sapa_chain:
            return True
        if "scope_keyword" in trigger and has_scope:
            return True
        if "applicability_intent" in trigger and self._query_has_any(query_text, ("적용", "적용범위", "상시근로자", "사업장")):
            return True
        if "purpose_keyword" in trigger and self._query_has_any(query_text, ("목적", "취지", "보호법익")):
            return True
        return False

    def _source_reason_for_policy(self, edge: dict) -> str:
        status = edge.get("status") or ""
        relation = edge.get("relation_type") or ""
        if status == "CONFIRMED":
            return "bundle_policy_confirmed"
        if status == "TEXT_REFERENCE_CANDIDATE":
            return "bundle_policy_text_reference"
        if relation == "LAW_SCOPE_SUPPORT":
            return "bundle_policy_scope_support"
        if relation == "PURPOSE_SUPPORT":
            return "bundle_policy_purpose_support"
        if relation == "LAW_DEFINITION_SUPPORT":
            return "bundle_policy_definition_support"
        if relation == "SECONDARY_PENALTY_SUPPORT":
            return "bundle_policy_secondary_penalty_support"
        if status == "RULE_BASED_CANDIDATE":
            return "bundle_policy_rule_based_candidate"
        return "bundle_policy_candidate"

    def _bundle_ref(self, item: dict) -> tuple[str, str] | None:
        law_name = str(item.get("law_name") or "")
        article_no = str(item.get("article_no") or "")
        if not law_name or not article_no:
            return None
        if "중대재해" in law_name:
            law_name = "중대재해처벌법"
        elif "산업안전보건법" in law_name and "시행" not in law_name and "기준" not in law_name:
            law_name = "산업안전보건법"
        article_no = self._normalize_article_no(article_no)
        return law_name, article_no

    def _normalize_article_no(self, article_no: str) -> str:
        text = str(article_no or "").strip()
        if not text:
            return ""
        if text.startswith("제") and text.endswith("조"):
            return text
        digits = "".join(ch for ch in text if ch.isdigit())
        return f"제{digits}조" if digits else text

    def _bundle_slot_for_ref(self, ref: tuple[str, str]) -> str:
        law_name, article_no = ref
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
            return "secondary_obligation"
        if law_name == "중대재해처벌법":
            if article_no in {"제4조", "제5조", "제9조"}:
                return "serious_accident_obligation"
            if article_no == "제6조":
                return "penalty"
            if article_no == "제7조":
                return "corporate_penalty"
            if article_no in {"제1조", "제2조", "제3조"}:
                return "definition_or_scope"
        return ""

    def _bundle_add(self, bundle: dict, slot: str, item: dict, basis: str, status: str) -> None:
        if not slot or slot not in bundle:
            return
        entry = {
            "law_name": item.get("law_name") or "",
            "article_no": item.get("article_no") or "",
            "paragraph_no": item.get("paragraph_no") or "",
            "item_no": item.get("item_no") or "",
            "rule_id": item.get("rule_id") or "",
            "status": status,
            "basis": basis,
            "source_reason": item.get("source_reason") or "",
            "review_reason": item.get("review_reason") or "",
            "source_text_preview": item.get("source_text_preview") or preview_text(item.get("source_text") or ""),
        }
        key = (entry["law_name"], entry["article_no"], entry["rule_id"], entry["status"])
        existing = {
            (row.get("law_name"), row.get("article_no"), row.get("rule_id"), row.get("status"))
            for row in bundle.get(slot, [])
            if isinstance(row, dict)
        }
        if key not in existing:
            bundle[slot].append(entry)

    def _fetch_bundle_completion_items(self, refs: list[tuple[str, str, str, str, str]]) -> list[dict]:
        if not refs:
            return []
        query_refs = [(law, article) for law, article, *_ in refs]
        rows = self.query_layer.find_rules_by_law_articles(query_refs, max(len(query_refs) * 3, 12))
        metadata = {(law, article): (slot, reason, review) for law, article, slot, reason, review in refs}
        result = []
        seen = set()
        parent_seen = set()
        fine_counts_by_ref = {}
        for row in rows:
            ref = self._bundle_ref(row)
            if not ref or ref not in metadata:
                continue
            slot, reason, review = metadata[ref]
            if ref not in parent_seen:
                parent_item = self._rule_evidence_item({"rule": row, "source_anchors": []}, row)
                parent_item["paragraph_no"] = ""
                parent_item["item_no"] = ""
                parent_item["subitem_no"] = ""
                parent_item["rule_id"] = ""
                parent_item["chain_role"] = slot
                parent_item["bundle_slot"] = slot
                parent_item["source_reason"] = f"{reason}_parent_article"
                parent_item["candidate_status"] = "TEXT_REFERENCE_CANDIDATE"
                parent_item["confidence"] = "medium"
                parent_item["needs_review"] = True
                parent_item["review_reason"] = review
                result.append(parent_item)
                parent_seen.add(ref)
            fine_identity = (
                ref[0],
                ref[1],
                str(row.get("paragraph_no") or ""),
                str(row.get("item_no") or ""),
                str(row.get("subitem_no") or ""),
                str(row.get("rule_id") or ""),
            )
            if fine_identity in seen:
                continue
            if fine_counts_by_ref.get(ref, 0) >= 3:
                continue
            fine_counts_by_ref[ref] = fine_counts_by_ref.get(ref, 0) + 1
            seen.add(fine_identity)
            item = self._rule_evidence_item({"rule": row, "source_anchors": []}, row)
            item["chain_role"] = slot
            item["bundle_slot"] = slot
            item["source_reason"] = reason
            if reason == "bundle_policy_confirmed":
                item["candidate_status"] = "CONFIRMED"
            elif reason == "bundle_policy_text_reference":
                item["candidate_status"] = "TEXT_REFERENCE_CANDIDATE"
            elif reason in {
                "bundle_policy_definition_support",
                "bundle_policy_scope_support",
                "bundle_policy_purpose_support",
                "bundle_policy_health_obligation_support",
                "bundle_policy_contractor_obligation_support",
            }:
                item["candidate_status"] = "SUPPORTING_DEFINITION"
            else:
                item["candidate_status"] = "BUNDLE_COMPLETION_CANDIDATE"
            item["confidence"] = "medium"
            item["needs_review"] = True
            item["review_reason"] = review
            result.append(item)
        return result

    def _legal_chain_edges(self, source_item: dict, penalties: list[dict]) -> list[dict]:
        edges = []
        current_source = {
            "law_name": source_item.get("law_name") or "",
            "article_no": source_item.get("article_no") or "",
        }
        for penalty in penalties:
            relation_type = penalty.get("relation_type") or penalty.get("match_type") or "VIOLATION_PENALIZED_BY"
            edge_source = current_source
            if relation_type == "CORPORATE_PENALTY_BY" and penalty.get("chain_source_rule_id"):
                edge_source = {
                    "law_name": penalty.get("chain_source_law_name") or "",
                    "article_no": penalty.get("chain_source_article_no") or "",
                }
            edges.append(
                {
                    "relation_type": relation_type,
                    "source": edge_source,
                    "target": {
                        "law_name": penalty.get("law_name") or "",
                        "article_no": penalty.get("article_no") or "",
                    },
                    "confidence": penalty.get("confidence") or "medium",
                    "status": penalty.get("candidate_status") or ("CONFIRMED" if penalty.get("is_confirmed") else "TEXT_REFERENCE_CANDIDATE"),
                    "review_reason": penalty.get("review_reason") or penalty.get("match_reason") or "",
                }
            )
            if relation_type != "CORPORATE_PENALTY_BY":
                current_source = {
                    "law_name": penalty.get("law_name") or "",
                    "article_no": penalty.get("article_no") or "",
                }
        return edges

    def build_fine_grained_legal_chains(
        self,
        evidence_items: list[dict],
        existing_penalty_items: list[dict],
        intent: str,
        query: str = "",
    ) -> tuple[list[dict], list[dict]]:
        if intent not in {"obligation_penalty_chain", "obligation_check", "safety_measure_lookup", "penalty_lookup"}:
            return [], []
        if not self.fine_grained_penalty_edges:
            return [], []

        source_refs = self._fine_source_refs_from_evidence(evidence_items)
        source_refs |= self._fine_obligation_seed_refs_from_query(query)
        if not source_refs:
            return [], []

        existing_targets = {self._fine_ref_from_evidence(item) for item in existing_penalty_items}
        existing_targets.discard("")
        chains: list[dict] = []
        penalty_items: list[dict] = []
        seen_targets: set[str] = set()
        per_source_counts: dict[str, int] = {}

        available_refs = set(source_refs)
        for _ in range(2):
            added_in_pass = False
            for edge in self.fine_grained_penalty_edges:
                source_ref = edge.get("source_ref") or ""
                target_ref = edge.get("target_ref") or ""
                source_article = self._article_key_from_ref(source_ref)
                target_article = self._article_key_from_ref(target_ref)
                if source_ref == target_ref:
                    continue
                if not self._fine_chain_article_allowed(source_article, target_article):
                    continue
                if not source_ref or not target_ref or (source_ref not in available_refs and source_article not in available_refs):
                    continue
                if edge.get("status") not in {"TEXT_REFERENCE_CANDIDATE", "RULE_BASED_CANDIDATE"}:
                    continue
                chain_key = f"{source_ref}->{target_ref}"
                if chain_key in seen_targets:
                    continue
                if per_source_counts.get(source_article, 0) >= 3:
                    continue
                per_source_counts[source_article] = per_source_counts.get(source_article, 0) + 1
                seen_targets.add(chain_key)
                available_refs.add(target_ref)
                available_refs.add(self._article_key_from_ref(target_ref))
                added_in_pass = True

                target_item = self._fine_edge_target_item(edge)
                if target_ref not in existing_targets:
                    penalty_items.append(target_item)

                chains.append(self._fine_chain_object(edge))
            if not added_in_pass:
                break

        return chains[:12], penalty_items[:8]

    def _fine_obligation_seed_refs_from_query(self, query: str) -> set[str]:
        text = query or ""
        refs: set[str] = set()
        if self._query_has_any(text, ("추락", "붕괴", "낙하", "끼임", "협착", "충돌", "전도", "굴착", "크레인", "비계", "안전조치", "위험")):
            refs.add("산업안전보건법 제38조 제1항")
            refs.add("산업안전보건법 제38조")
        if self._query_has_any(text, ("보건", "건강장해", "질식", "산소결핍", "밀폐공간", "유해물질", "화학물질", "중독")):
            refs.add("산업안전보건법 제39조 제1항")
            refs.add("산업안전보건법 제39조")
        if self._query_has_any(text, ("도급", "수급", "관계수급인", "하청", "원청", "용역", "위탁", "도급사업주")):
            refs.add("산업안전보건법 제63조")
            refs.add("산업안전보건법 제64조")
            refs.add("중대재해처벌법 제5조")
        if self._query_has_any(text, ("사망", "중대재해", "중대산업재해", "경영책임자", "대표이사", "안전보건 확보의무")):
            refs.add("중대재해처벌법 제4조")
            refs.add("중대재해처벌법 제5조")
        return refs

    def _fine_chain_article_allowed(self, source_article: str, target_article: str) -> bool:
        obligation_sources = {
            "산업안전보건법 제38조",
            "산업안전보건법 제39조",
            "산업안전보건법 제63조",
            "산업안전보건법 제64조",
            "중대재해처벌법 제4조",
            "중대재해처벌법 제5조",
        }
        penalty_sources = {
            "산업안전보건법 제167조",
            "산업안전보건법 제168조",
            "중대재해처벌법 제6조",
        }
        penalty_targets = {
            "산업안전보건법 제167조",
            "산업안전보건법 제168조",
            "중대재해처벌법 제6조",
        }
        corporate_targets = {
            "산업안전보건법 제173조",
            "중대재해처벌법 제7조",
        }
        return (
            (source_article in obligation_sources and target_article in penalty_targets)
            or (source_article in penalty_sources and target_article in corporate_targets)
        )

    def _fine_chain_debug_metrics(self, legal_chains: list[dict]) -> dict[str, int]:
        fine = [chain for chain in legal_chains if isinstance(chain, dict) and chain.get("chain_type") == "fine_grained_penalty_chain"]
        obligation_articles = {
            "산업안전보건법 제38조",
            "산업안전보건법 제39조",
            "산업안전보건법 제63조",
            "산업안전보건법 제64조",
            "중대재해처벌법 제4조",
            "중대재해처벌법 제5조",
        }
        penalty_articles = {
            "산업안전보건법 제167조",
            "산업안전보건법 제168조",
            "중대재해처벌법 제6조",
        }
        corporate_articles = {
            "산업안전보건법 제173조",
            "중대재해처벌법 제7조",
        }
        seed_edges = 0
        full_edges = 0
        sources = set()
        penalty_targets = set()
        for chain in fine:
            source_article = self._article_key_from_ref(chain.get("source_ref") or "")
            target_article = self._article_key_from_ref(chain.get("target_ref") or "")
            for ref in chain.get("chain_refs") or []:
                if self._article_key_from_ref(ref) in obligation_articles:
                    sources.add(self._article_key_from_ref(ref))
            if source_article in obligation_articles:
                sources.add(source_article)
            if source_article in obligation_articles and target_article in penalty_articles:
                seed_edges += 1
                penalty_targets.add(target_article)
            if source_article in penalty_articles and target_article in corporate_articles:
                full_edges += 1
        return {
            "obligation_seed_found_count": len(sources),
            "obligation_seed_to_child_success_count": seed_edges,
            "obligation_to_penalty_chain_count": seed_edges,
            "full_obligation_penalty_corporate_chain_count": min(seed_edges, full_edges),
            "legal_chains_missing_count": 0 if legal_chains else 1,
            "fine_grained_chain_count": len(fine),
        }

    def _fine_chain_object(self, edge: dict) -> dict:
        source_ref = edge.get("source_ref") or ""
        target_ref = edge.get("target_ref") or ""
        source_law, source_article, _, _ = self._split_ref(source_ref)
        return {
            "chain_type": "fine_grained_penalty_chain",
            "chain_refs": [source_ref, target_ref],
            "source": {
                "law_name": source_law,
                "article_no": source_article,
                "rule_id": edge.get("source_node_id") or "",
                "source_ref": source_ref,
            },
            "source_ref": source_ref,
            "source_node_id": edge.get("source_node_id") or "",
            "source_level": self._ref_level_from_ref(source_ref),
            "relation_type": edge.get("relation_type") or "TEXT_REFERENCE_PENALTY_BY",
            "target_ref": target_ref,
            "target_node_id": edge.get("target_node_id") or "",
            "target_level": self._ref_level_from_ref(target_ref),
            "status": edge.get("status") or "TEXT_REFERENCE_CANDIDATE",
            "confidence": edge.get("confidence") or "medium",
            "chain_source": "fine_grained_penalty_edges",
            "nodes": [
                {"ref": source_ref, "node_id": edge.get("source_node_id") or "", "level": self._ref_level_from_ref(source_ref)},
                {"ref": target_ref, "node_id": edge.get("target_node_id") or "", "level": self._ref_level_from_ref(target_ref)},
            ],
            "edges": [
                {
                    "from": source_ref,
                    "to": target_ref,
                    "relation_type": edge.get("relation_type") or "TEXT_REFERENCE_PENALTY_BY",
                    "status": edge.get("status") or "TEXT_REFERENCE_CANDIDATE",
                    "confidence": edge.get("confidence") or "medium",
                    "review_reason": edge.get("review_reason") or "",
                }
            ],
        }

    def _fine_edge_target_item(self, edge: dict) -> dict:
        law_name, article_no, paragraph_no, item_no = self._split_ref(edge.get("target_ref") or "")
        return {
            "evidence_kind": "rule",
            "chain_role": "fine_grained_penalty",
            "rule_id": edge.get("target_node_id") or "",
            "law_name": law_name,
            "article_no": article_no,
            "paragraph_no": paragraph_no,
            "item_no": item_no,
            "source_text": edge.get("penalty_text") or "",
            "source_text_preview": preview_text(edge.get("penalty_text") or ""),
            "source_ref": edge.get("source_ref") or "",
            "target_ref": edge.get("target_ref") or "",
            "source_node_id": edge.get("source_node_id") or "",
            "target_node_id": edge.get("target_node_id") or "",
            "relation_type": edge.get("relation_type") or "",
            "match_type": edge.get("relation_type") or "",
            "candidate_status": edge.get("status") or "TEXT_REFERENCE_CANDIDATE",
            "confidence": edge.get("confidence") or "medium",
            "is_confirmed": edge.get("status") == "CONFIRMED",
            "needs_review": edge.get("status") != "CONFIRMED",
            "review_reason": edge.get("review_reason") or "",
            "source_reason": "fine_grained_penalty_edge",
        }

    def _fine_source_refs_from_evidence(self, evidence_items: list[dict]) -> set[str]:
        refs: set[str] = set()
        for item in evidence_items:
            ref = self._fine_ref_from_evidence(item)
            if ref:
                refs.add(ref)
            article_ref = self._article_ref_from_evidence(item)
            if article_ref:
                refs.add(article_ref)
        return refs

    def _fine_ref_from_evidence(self, item: dict) -> str:
        for key in ("target_ref", "source_ref", "normalized_ref", "full_ref"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        law = item.get("law_name") or ""
        article = item.get("article_no") or ""
        if not law or not article:
            return ""
        parts = [str(law), str(article)]
        paragraph = item.get("paragraph_no") or self._paragraph_from_text(item.get("source_text") or item.get("source_text_preview") or "")
        item_no = item.get("item_no") or self._item_from_text(item.get("source_text") or item.get("source_text_preview") or "")
        if paragraph:
            parts.append(str(paragraph))
        if item_no:
            parts.append(str(item_no))
        return " ".join(parts)

    def _article_ref_from_evidence(self, item: dict) -> str:
        law = item.get("law_name") or ""
        article = item.get("article_no") or ""
        return f"{law} {article}".strip() if law and article else ""

    def _article_key_from_ref(self, ref: str) -> str:
        parts = ref.split()
        if len(parts) >= 2:
            return " ".join(parts[:2])
        return ref

    def _ref_level_from_ref(self, ref: str) -> str:
        if "목" in ref:
            return "subitem"
        if "호" in ref:
            return "item"
        if "항" in ref:
            return "paragraph"
        if "조" in ref:
            return "article"
        return "unknown"

    def _split_ref(self, ref: str) -> tuple[str, str, str, str]:
        parts = ref.split()
        law_name = ""
        article_no = ""
        paragraph_no = ""
        item_no = ""
        for idx, part in enumerate(parts):
            if part.startswith("제") and "조" in part:
                law_name = " ".join(parts[:idx])
                article_no = part
            elif part.startswith("제") and "항" in part and not paragraph_no:
                paragraph_no = part
            elif part.startswith("제") and "호" in part and not item_no:
                item_no = part
        return law_name, article_no, paragraph_no, item_no

    def _paragraph_from_text(self, text: str) -> str:
        if not text:
            return ""
        circled = {
            "①": "제1항",
            "②": "제2항",
            "③": "제3항",
            "④": "제4항",
            "⑤": "제5항",
            "⑥": "제6항",
            "⑦": "제7항",
            "⑧": "제8항",
            "⑨": "제9항",
            "⑩": "제10항",
        }
        stripped = str(text).strip()
        return circled.get(stripped[:1], "")

    def _item_from_text(self, text: str) -> str:
        if not text:
            return ""
        stripped = str(text).strip()
        if len(stripped) >= 2 and stripped[0].isdigit() and stripped[1] == ".":
            return f"제{stripped[0]}호"
        return ""

    def _is_penalty_evidence(self, item: dict) -> bool:
        rule_type = str(item.get("rule_type") or "")
        rule_subtype = str(item.get("rule_subtype") or "")
        text = " ".join(str(item.get(key) or "") for key in ("source_text", "source_text_preview"))
        return (
            rule_type == "PENALTY"
            or "PENALTY" in rule_subtype
            or "벌칙" in text
            or "벌금" in text
            or "징역" in text
            or "과태료" in text
        )

    def _penalty_items_from_related_rules(self, item: dict) -> list[dict]:
        penalties = []
        for related in item.get("related_rules") or []:
            if not isinstance(related, dict):
                continue
            rule = related.get("rule") or {}
            if not isinstance(rule, dict):
                continue
            candidate = {
                "evidence_kind": "rule",
                "rule_id": rule.get("rule_id"),
                "rule_type": rule.get("rule_type"),
                "rule_subtype": rule.get("rule_subtype"),
                "law_name": rule.get("law_name"),
                "article_no": rule.get("article_no"),
                "annex_title": rule.get("annex_title"),
                "source_text": rule.get("source_text") or rule.get("penalty_text"),
                "source_text_preview": rule.get("source_text") or rule.get("penalty_text"),
                "match_type": "RELATED_RULE",
                "match_reason": f"RELATED_RULE:{related.get('rel') or ''}",
                "is_confirmed": True,
            }
            if self._is_penalty_evidence(candidate):
                penalties.append(candidate)
        return penalties

    def _normalize_penalty_chain_item(self, penalty: dict, source_item: dict) -> dict:
        return {
            "evidence_kind": "rule",
            "chain_role": "penalty",
            "chain_source_rule_id": source_item.get("rule_id") or "",
            "rule_id": penalty.get("rule_id"),
            "rule_type": penalty.get("rule_type"),
            "rule_subtype": penalty.get("rule_subtype"),
            "law_name": penalty.get("law_name"),
            "article_no": penalty.get("article_no"),
            "annex_title": penalty.get("annex_title"),
            "source_text": penalty.get("source_text") or penalty.get("source_text_preview") or "",
            "source_text_preview": preview_text(penalty.get("source_text_preview") or penalty.get("source_text") or ""),
            "source_anchor": {},
            "requirements": [],
            "thresholds": [],
            "exceptions": [],
            "temporal_rules": [],
            "entities": [],
            "list_items": [],
            "source_nodes": [],
            "source_anchors": [],
            "related_rules": [],
            "match_type": penalty.get("match_type") or "",
            "relation_type": penalty.get("relation_type") or penalty.get("match_type") or "",
            "match_reason": penalty.get("match_reason") or "",
            "candidate_status": penalty.get("candidate_status")
            or ("CONFIRMED" if penalty.get("is_confirmed") else "TEXT_REFERENCE_CANDIDATE"),
            "confidence": penalty.get("confidence") or ("high" if penalty.get("is_confirmed") else "medium"),
            "is_confirmed": bool(penalty.get("is_confirmed")),
            "needs_review": not bool(penalty.get("is_confirmed")),
            "review_reason": penalty.get("review_reason") or "",
            "chain_source_law_name": source_item.get("law_name") or "",
            "chain_source_article_no": source_item.get("article_no") or "",
        }

    def _listitem_evidence_item(self, row: dict) -> dict:
        label = first_label(row.get("anchor_label"))
        return {
            "evidence_kind": "list_item",
            "list_item_id": row.get("list_item_id"),
            "list_item_type": row.get("list_item_type"),
            "item_text": row.get("item_text"),
            "law_name": row.get("law_name"),
            "article_no": row.get("article_no"),
            "annex_title": row.get("annex_title"),
            "source_context_text": row.get("source_context_text"),
            "source_context_text_preview": preview_text(row.get("source_context_text") or ""),
            "source_anchor": {
                "label": label,
                "id": row.get("anchor_id"),
                "source_text": row.get("anchor_source_text"),
                "source_text_preview": preview_text(row.get("anchor_source_text") or ""),
            },
            "resolved_annex_title": row.get("resolved_annex_title"),
            "citation": {
                "law_name": row.get("law_name"),
                "article_no": row.get("article_no"),
                "annex_title": row.get("resolved_annex_title") or row.get("annex_title"),
                "source_anchor_label": label,
                "source_anchor_id": row.get("anchor_id"),
            },
            "listitem_score": row.get("score", 0),
            "rank_reason": row.get("rank_reason", ""),
        }

    def _normalize_inspection_listitem_row(self, row: dict) -> dict:
        li = row.get("list_item") or {}
        anchor = row.get("source_anchor") or {}
        annex = row.get("annex") or {}
        label = first_label(row.get("anchor_labels"))
        return {
            "list_item_id": li.get("list_item_id"),
            "list_item_type": li.get("list_item_type"),
            "item_text": li.get("item_text"),
            "law_name": li.get("law_name"),
            "article_no": li.get("article_no"),
            "annex_title": li.get("annex_title"),
            "source_context_text": li.get("source_context_text"),
            "anchor_label": [label] if label else [],
            "anchor_id": anchor_id(anchor),
            "anchor_source_text": anchor.get("source_text") or anchor.get("text"),
            "resolved_annex_title": annex.get("annex_title") or li.get("annex_title"),
            "score": row.get("score", 0),
            "rank_reason": row.get("rank_reason", ""),
        }
