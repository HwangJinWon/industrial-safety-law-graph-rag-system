"""Evidence-pack readiness checks for answer-generation guardrails.

This module checks whether a structured evidence pack is suitable for a later
answer generator. It does not validate generated prose, generate answers, call
an LLM, or write to Neo4j.
"""

from __future__ import annotations

import re
from typing import Any

from graph_rag_pipeline.citation_formatter import CitationFormatter


class ClaimChecker:
    def __init__(self):
        self.citation_formatter = CitationFormatter()

    def check_pack(self, evidence_pack: dict, citations: list[dict] | None = None) -> dict:
        citations = citations if citations is not None else self.citation_formatter.format_pack_citations(evidence_pack)
        issues: list[dict] = []
        issues.extend(self.check_intent_requirements(evidence_pack))
        issues.extend(self.check_directness(evidence_pack))
        issues.extend(self.check_citations(evidence_pack, citations))
        answer_policy = self.determine_answer_policy(evidence_pack, issues)
        status = self._claim_check_status(evidence_pack, issues, answer_policy)
        result = {
            "query": evidence_pack.get("query"),
            "intent": evidence_pack.get("intent"),
            "pack_status": evidence_pack.get("status"),
            "evidence_readiness": evidence_pack.get("evidence_readiness"),
            "claim_check_status": status,
            "answer_policy": answer_policy,
            "issues": issues,
            "badges": [],
            "summary": self.summarize_check(evidence_pack, issues, citations),
        }
        result["badges"] = self.build_badges(result)
        return result

    def check_intent_requirements(self, evidence_pack: dict) -> list[dict]:
        intent = evidence_pack.get("intent")
        primary = evidence_pack.get("primary_evidence") or []
        supporting = evidence_pack.get("supporting_evidence") or []
        all_items = primary + supporting
        issues: list[dict] = []
        if not primary:
            return [
                self._issue(
                    "NO_PRIMARY_EVIDENCE",
                    "high",
                    "No primary evidence was found.",
                    "Do not answer until more evidence is available.",
                )
            ]
        if intent == "appointment_requirement":
            if not self._has_rule(all_items):
                issues.append(self._issue("RULE_EVIDENCE_MISSING", "high", "Appointment query lacks Rule evidence."))
            if not self._has_requirement_or_source(all_items):
                issues.append(
                    self._issue("REQUIREMENT_MISSING", "medium", "Appointment query lacks requirement/source evidence.")
                )
            if not self._has_entity_or_keyword(all_items, ("관리자", "안전관리자", "보건관리자", "책임자", "선임")):
                issues.append(self._issue("ROLE_CONTEXT_WEAK", "medium", "Role/entity context is weak."))
        elif intent == "education_time_lookup":
            if not self._has_threshold_or_time(all_items):
                issues.append(
                    self._issue("TIME_THRESHOLD_MISSING", "high", "Education time query lacks threshold or time expression.")
                )
            if not self._has_keyword(all_items, ("교육", "안전보건교육", "별표")):
                issues.append(self._issue("EDUCATION_CONTEXT_WEAK", "medium", "Education context is weak."))
        elif intent in {"inspection_requirement", "list_lookup"}:
            if not any(item.get("evidence_kind") == "list_item" or item.get("list_item_id") for item in all_items):
                issues.append(self._issue("LIST_ITEM_MISSING", "high", "List/list query lacks ListItem evidence."))
            if not any(item.get("source_anchor") or item.get("source_anchor_id") for item in all_items):
                issues.append(
                    self._issue("ITEM_SOURCE_ANCHOR_MISSING", "high", "ListItem evidence lacks source-anchor evidence.")
                )
            if not any(item.get("item_text") for item in all_items):
                issues.append(self._issue("ITEM_TEXT_MISSING", "high", "ListItem evidence lacks item_text."))
        elif intent == "obligation_check":
            if not self._has_rule(all_items):
                issues.append(self._issue("RULE_EVIDENCE_MISSING", "high", "Obligation query lacks Rule evidence."))
            if not self._has_requirement_or_source(all_items):
                issues.append(
                    self._issue("OBLIGATION_SOURCE_MISSING", "high", "Obligation query lacks requirement/source evidence.")
                )
            if evidence_pack.get("evidence_readiness") == "INDIRECT_ONLY":
                issues.append(
                    self._issue(
                        "DIRECT_OBLIGATION_SOURCE_MISSING",
                        "high",
                        "Direct obligation source is missing; only indirect evidence is available.",
                        "Use an indirect-only response policy.",
                    )
                )
        elif intent == "penalty_lookup":
            if not self._has_penalty_evidence(all_items):
                issues.append(self._issue("PENALTY_RULE_MISSING", "high", "Penalty query lacks penalty evidence."))
            if not any(item.get("related_rules") for item in all_items):
                issues.append(
                    self._issue(
                        "RELATED_VIOLATION_RULE_MISSING",
                        "medium",
                        "Penalty evidence lacks related violation Rule evidence.",
                        "Answer with caution and cite the penalty source.",
                    )
                )
        elif intent == "applicability_check":
            if not self._has_applicability_context(all_items):
                issues.append(
                    self._issue(
                        "APPLICABILITY_CONTEXT_MISSING",
                        "medium",
                        "Applicability query lacks exception/scope/threshold/temporal/entity evidence.",
                    )
                )
        elif intent == "definition_lookup":
            if not any(item.get("rule_type") == "DEFINITION" or item.get("rule_subtype") == "DEFINITION" for item in all_items):
                issues.append(self._issue("DEFINITION_RULE_MISSING", "medium", "Definition query lacks Definition Rule evidence."))
        return issues

    def check_directness(self, evidence_pack: dict) -> list[dict]:
        issues: list[dict] = []
        readiness = evidence_pack.get("evidence_readiness")
        if readiness == "INDIRECT_ONLY":
            issues.append(
                self._issue(
                    "INDIRECT_ONLY_EVIDENCE",
                    "high",
                    "Evidence readiness is INDIRECT_ONLY.",
                    "Do not produce a direct affirmative or negative legal answer.",
                )
            )
        if readiness in {"LIMITED_EVIDENCE", "NOT_READY"}:
            issues.append(self._issue("LIMITED_EVIDENCE", "high", f"Evidence readiness is {readiness}."))
        for warning in evidence_pack.get("warnings") or []:
            if not isinstance(warning, dict):
                continue
            warning_type = warning.get("warning_type")
            if warning_type == "DIRECT_EVIDENCE_NOT_FOUND":
                issues.append(
                    self._issue(
                        "DIRECT_EVIDENCE_NOT_FOUND",
                        "high",
                        warning.get("message") or "Direct evidence was not found.",
                        "Restrict the answer to indirect evidence status.",
                        warning.get("related_id") or "",
                    )
                )
            elif warning_type in {"NEEDS_REVIEW", "UNKNOWN_RULE_TYPE"}:
                issues.append(
                    self._issue(
                        warning_type,
                        "medium",
                        warning.get("message") or "Evidence has a quality warning.",
                        "Answer with caution if otherwise allowed.",
                        warning.get("related_id") or "",
                    )
                )
        for missing in evidence_pack.get("missing_evidence") or []:
            if isinstance(missing, dict) and missing.get("severity") == "high":
                issues.append(
                    self._issue(
                        missing.get("missing_type") or "HIGH_SEVERITY_MISSING_EVIDENCE",
                        "high",
                        missing.get("message") or "High-severity evidence is missing.",
                        "Restrict or refuse direct answer.",
                    )
                )
        for item in evidence_pack.get("primary_evidence") or []:
            if item.get("needs_review") in {True, "true", "TRUE", "1", 1}:
                issues.append(
                    self._issue("NEEDS_REVIEW", "medium", "Primary evidence is marked needs_review.", related_id=self._item_id(item))
                )
            if item.get("rule_type") == "UNKNOWN" or item.get("rule_subtype") == "UNKNOWN":
                issues.append(
                    self._issue(
                        "UNKNOWN_RULE_TYPE",
                        "medium",
                        "Primary evidence has UNKNOWN rule_type or rule_subtype.",
                        related_id=self._item_id(item),
                    )
                )
        return self._dedupe_issues(issues)

    def check_citations(self, evidence_pack: dict, citations: list[dict] | None = None) -> list[dict]:
        citations = citations if citations is not None else self.citation_formatter.format_pack_citations(evidence_pack)
        if citations:
            return []
        return [
            self._issue(
                "CITATION_MISSING",
                "high",
                "No citation candidates or formatted citations were found.",
                "Do not provide a direct legal answer without citation.",
            )
        ]

    def determine_answer_policy(self, evidence_pack: dict, issues: list[dict]) -> str:
        if not (evidence_pack.get("primary_evidence") or []):
            return "REFUSE_OR_REQUEST_MORE_EVIDENCE"
        issue_types = {issue.get("issue_type") for issue in issues}
        if evidence_pack.get("evidence_readiness") == "INDIRECT_ONLY":
            return "INDIRECT_ONLY_RESPONSE"
        if "DIRECT_EVIDENCE_NOT_FOUND" in issue_types or "DIRECT_OBLIGATION_SOURCE_MISSING" in issue_types:
            return "INDIRECT_ONLY_RESPONSE"
        if any(issue.get("severity") == "high" for issue in issues):
            return "REFUSE_OR_REQUEST_MORE_EVIDENCE"
        if issues or evidence_pack.get("warnings") or evidence_pack.get("missing_evidence"):
            return "ALLOW_WITH_CAUTION"
        return "ALLOW_DIRECT_ANSWER"

    def summarize_check(self, evidence_pack: dict, issues: list[dict], citations: list[dict] | None = None) -> dict:
        citations = citations if citations is not None else self.citation_formatter.format_pack_citations(evidence_pack)
        return {
            "primary_evidence_count": len(evidence_pack.get("primary_evidence") or []),
            "citation_count": len(citations),
            "warning_count": len(evidence_pack.get("warnings") or []),
            "missing_evidence_count": len(evidence_pack.get("missing_evidence") or []),
            "high_severity_issue_count": sum(1 for issue in issues if issue.get("severity") == "high"),
        }

    def build_badges(self, claim_check_result: dict) -> list[dict]:
        policy = claim_check_result.get("answer_policy")
        status = claim_check_result.get("claim_check_status")
        readiness = claim_check_result.get("evidence_readiness")
        if policy == "ALLOW_DIRECT_ANSWER":
            return [{"label": "직접 근거 확인", "severity": "success", "message": "Citation-backed direct answer is allowed."}]
        if policy == "ALLOW_WITH_CAUTION":
            return [{"label": "주의 필요", "severity": "warning", "message": "Answer is allowed with evidence-quality cautions."}]
        if policy == "INDIRECT_ONLY_RESPONSE":
            return [{"label": "간접 근거만 확인", "severity": "warning", "message": "Direct evidence is unavailable; restrict answer wording."}]
        if policy == "REFUSE_OR_REQUEST_MORE_EVIDENCE":
            return [{"label": "답변 보류", "severity": "danger", "message": "Evidence is insufficient for answer generation."}]
        return [{"label": status or readiness or "확인 필요", "severity": "info", "message": "Review claim-check result."}]

    def _claim_check_status(self, evidence_pack: dict, issues: list[dict], answer_policy: str) -> str:
        if answer_policy == "REFUSE_OR_REQUEST_MORE_EVIDENCE":
            return "FAIL"
        if answer_policy == "INDIRECT_ONLY_RESPONSE":
            return "RESTRICTED"
        if any(issue.get("severity") == "high" for issue in issues):
            return "RESTRICTED"
        if issues or evidence_pack.get("warnings") or evidence_pack.get("missing_evidence"):
            return "PASS_WITH_WARNINGS"
        return "PASS"

    def _issue(
        self,
        issue_type: str,
        severity: str,
        message: str,
        recommendation: str = "Review evidence before answer generation.",
        related_id: str = "",
    ) -> dict:
        return {
            "issue_type": issue_type,
            "severity": severity,
            "message": message,
            "related_id": related_id,
            "recommendation": recommendation,
        }

    def _has_rule(self, items: list[dict]) -> bool:
        return any(item.get("evidence_kind") == "rule" or item.get("rule_id") for item in items)

    def _has_requirement_or_source(self, items: list[dict]) -> bool:
        return any(item.get("requirements") or item.get("source_text") or item.get("source_text_preview") for item in items)

    def _has_entity_or_keyword(self, items: list[dict], keywords: tuple[str, ...]) -> bool:
        return any(item.get("entities") or self._has_keyword([item], keywords) for item in items)

    def _has_keyword(self, items: list[dict], keywords: tuple[str, ...]) -> bool:
        return any(any(keyword in self._item_text(item) for keyword in keywords) for item in items)

    def _has_threshold_or_time(self, items: list[dict]) -> bool:
        return any(item.get("thresholds") or item.get("evidence_kind") == "annex_logical_time" or self._contains_time(item) for item in items)

    def _has_penalty_evidence(self, items: list[dict]) -> bool:
        for item in items:
            text = self._item_text(item)
            if item.get("rule_type") == "PENALTY" or "PENALTY" in str(item.get("rule_subtype") or ""):
                return True
            if item.get("penalty_text") or "과태료" in text or "벌칙" in text:
                return True
        return False

    def _has_applicability_context(self, items: list[dict]) -> bool:
        for item in items:
            text = self._item_text(item)
            if item.get("exceptions") or item.get("thresholds") or item.get("temporal_rules") or item.get("entities"):
                return True
            if any(keyword in text for keyword in ("적용 제외", "제외", "예외", "범위", "대상", "미적용")):
                return True
        return False

    def _contains_time(self, item: dict) -> bool:
        text = self._item_text(item)
        return bool(re.search(r"\d+\s*(시간|분|일|개월|년)", text)) or "시간" in text

    def _item_text(self, item: Any) -> str:
        if isinstance(item, dict):
            parts: list[str] = []
            for value in item.values():
                if isinstance(value, (str, int, float, bool)):
                    parts.append(str(value))
                elif isinstance(value, list):
                    parts.append(" ".join(self._item_text(v) for v in value))
                elif isinstance(value, dict):
                    parts.append(self._item_text(value))
            return " ".join(parts)
        if isinstance(item, list):
            return " ".join(self._item_text(v) for v in item)
        return str(item or "")

    def _item_id(self, item: dict) -> str:
        return str(item.get("rule_id") or item.get("list_item_id") or item.get("source_node_id") or "")

    def _dedupe_issues(self, issues: list[dict]) -> list[dict]:
        seen: set[tuple[str, str, str]] = set()
        result: list[dict] = []
        for issue in issues:
            key = (issue.get("issue_type") or "", issue.get("severity") or "", issue.get("related_id") or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(issue)
        return result
