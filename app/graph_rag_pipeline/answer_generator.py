"""Deterministic answer generation from checked Graph-RAG evidence packs.

Legal judgment stays with the graph evidence, citations, claim checker, and
domain extractors. This module only turns those structured signals into a
user-facing Korean answer. Optional LLM polishing is disabled by default and
may only edit the deterministic draft after safety checks.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b:?\s*"
)
FORBIDDEN_EDUCATION_FALLBACK_TERMS = (
    "중대재해 처벌 등에 관한 법률",
    "건강진단",
    "유해물질",
    "보호구",
    "금지유해물질",
    "교육교재",
    "인력ㆍ시설 및 장비",
    "인력·시설 및 장비",
)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class AnswerGenerator:
    def __init__(self, root_dir: str | Path, use_llm: bool = False, use_llm_polish: bool | None = None):
        self.root_dir = Path(root_dir).resolve()
        self.use_llm = use_llm
        self.use_llm_polish = use_llm_polish

    def generate(self, evidence_pack: dict, citations: list[dict], claim_check: dict) -> dict:
        generated = self.generate_template_answer(evidence_pack, citations, claim_check)
        generated["deterministic_answer"] = generated["answer"]

        polish_enabled = self.polish_enabled()
        generated["llm_polish_mode"] = polish_enabled
        generated["llm_used"] = False
        generated["llm_fallback_reason"] = "disabled"
        if not polish_enabled:
            return generated

        try:
            from graph_rag_pipeline.llm.answer_polisher import polish_answer
        except Exception as exc:  # noqa: BLE001
            generated["llm_fallback_reason"] = f"polisher_import_failed:{exc.__class__.__name__}"
            return generated

        payload = {
            "question": evidence_pack.get("query") or "",
            "original_question": evidence_pack.get("original_query") or evidence_pack.get("query") or "",
            "rewritten_question": evidence_pack.get("rewritten_query") or evidence_pack.get("query") or "",
            "question_interpretation": evidence_pack.get("question_interpretation") or "",
            "intent": evidence_pack.get("intent") or "",
            "answer_policy": claim_check.get("answer_policy") or generated.get("answer_policy"),
            "evidence_readiness": evidence_pack.get("evidence_readiness"),
            "deterministic_answer": generated["answer"],
            "citations": citations,
            "evidence_chips": evidence_pack.get("evidence_chips") or [],
            "warnings": evidence_pack.get("warnings") or [],
            "missing_evidence": evidence_pack.get("missing_evidence") or [],
            "penalties": evidence_pack.get("penalties") or [],
            "candidate_penalties": evidence_pack.get("candidate_penalties") or [],
            "domain_result": evidence_pack.get("domain_result") or {},
        }
        polished = polish_answer(payload)
        generated["llm_used"] = bool(polished.get("llm_used"))
        generated["llm_fallback_reason"] = polished.get("llm_fallback_reason") or ""
        generated["llm_post_check_notes"] = polished.get("post_check_notes") or []
        if polished.get("llm_used") and polished.get("answer"):
            generated["answer"] = polished["answer"]
        return generated

    def polish_enabled(self) -> bool:
        if self.use_llm_polish is not None:
            return bool(self.use_llm_polish)
        return env_bool("USE_LLM_POLISH", False)

    def generate_template_answer(self, evidence_pack: dict, citations: list[dict], claim_check: dict) -> dict:
        policy = claim_check.get("answer_policy") or "REFUSE_OR_REQUEST_MORE_EVIDENCE"
        warnings = evidence_pack.get("warnings") or []
        missing = evidence_pack.get("missing_evidence") or []
        interpretation = self.strip_internal_ids(evidence_pack.get("question_interpretation") or "")
        domain_result = evidence_pack.get("domain_result") or {}
        if domain_result.get("handled"):
            return self.generate_domain_answer(evidence_pack, citations, claim_check, domain_result, interpretation)

        sections: list[str] = []
        if interpretation:
            sections.extend(["[질문 해석]", interpretation, ""])
        sections.extend(
            [
                "[결론]",
                self.build_conclusion(evidence_pack, citations, claim_check),
                "",
                "[근거]",
                *self.build_evidence_summary(citations, evidence_pack),
            ]
        )
        legal_chain_lines = self.build_legal_chain_lines(evidence_pack)
        if legal_chain_lines:
            sections.extend(["", "[의무-처벌 연결]", *legal_chain_lines])
        legal_bundle_lines = self.build_legal_bundle_lines(evidence_pack)
        if legal_bundle_lines:
            sections.extend(["", "[법령 묶음 근거]", *legal_bundle_lines])
        caution_lines = self.build_caution_lines(policy, warnings, missing)
        if caution_lines:
            sections.extend(["", "[주의]", *caution_lines])
        next_checks = self.build_next_checks(evidence_pack, claim_check)
        if next_checks:
            sections.extend(["", "[다음 확인]", *next_checks])

        enforced = self.enforce_policy("\n".join(sections).strip(), evidence_pack, claim_check)
        return self._result(enforced, policy, evidence_pack, claim_check, warnings, missing)

    def generate_domain_answer(
        self,
        evidence_pack: dict,
        citations: list[dict],
        claim_check: dict,
        domain_result: dict,
        interpretation: str,
    ) -> dict:
        policy = claim_check.get("answer_policy") or "REFUSE_OR_REQUEST_MORE_EVIDENCE"
        if domain_result.get("intent") == "education_time":
            enforced = self.enforce_policy(
                self.generate_education_time_answer(domain_result, interpretation),
                evidence_pack,
                claim_check,
            )
            result = self._result(
                enforced,
                policy,
                evidence_pack,
                claim_check,
                evidence_pack.get("warnings") or [],
                evidence_pack.get("missing_evidence") or [],
            )
            result.update(
                {
                    "domain_answer": True,
                    "domain_answer_level": domain_result.get("answer_level"),
                    "domain_confidence": domain_result.get("confidence"),
                }
            )
            return result

        sections: list[str] = []
        domain_interpretation = self.strip_internal_ids(domain_result.get("question_interpretation") or interpretation)
        if domain_interpretation:
            sections.extend(["[질문 해석]", domain_interpretation, ""])
        sections.extend(
            [
                "[결론]",
                self.strip_internal_ids(domain_result.get("direct_answer"))
                or "질문 유형에 맞는 직접 답변을 구성하지 못했습니다.",
                "",
                "[근거]",
                *self.build_domain_source_lines(domain_result.get("sources") or []),
            ]
        )
        legal_chain_lines = self.build_legal_chain_lines(evidence_pack)
        if legal_chain_lines:
            sections.extend(["", "[의무-처벌 연결]", *legal_chain_lines])
        legal_bundle_lines = self.build_legal_bundle_lines(evidence_pack)
        if legal_bundle_lines:
            sections.extend(["", "[법령 묶음 근거]", *legal_bundle_lines])
        warning_lines = [f"- {self.strip_internal_ids(item)}" for item in domain_result.get("warnings") or [] if item]
        if warning_lines:
            sections.extend(["", "[주의]", *warning_lines])
        next_lines = [f"- {self.strip_internal_ids(item)}" for item in domain_result.get("next_checks") or [] if item]
        if next_lines:
            sections.extend(["", "[다음 확인]", *next_lines])
        enforced = self.enforce_policy("\n".join(sections).strip(), evidence_pack, claim_check)
        result = self._result(
            enforced,
            policy,
            evidence_pack,
            claim_check,
            evidence_pack.get("warnings") or [],
            evidence_pack.get("missing_evidence") or [],
        )
        result.update(
            {
                "domain_answer": True,
                "domain_answer_level": domain_result.get("answer_level"),
                "domain_confidence": domain_result.get("confidence"),
            }
        )
        return result

    def generate_education_time_answer(self, domain_result: dict, interpretation: str) -> str:
        sections: list[str] = []
        domain_interpretation = self.strip_internal_ids(domain_result.get("question_interpretation") or interpretation)
        if domain_interpretation:
            sections.extend(["[질문 해석]", domain_interpretation, ""])

        items = [item for item in domain_result.get("extracted_items") or [] if isinstance(item, dict)]
        sections.extend(
            [
                "[결론]",
                self.strip_internal_ids(domain_result.get("direct_answer"))
                or (
                    "이 질문은 정기 안전보건교육 시간에 관한 질문으로 해석됩니다. 관련 근거는 시행규칙 "
                    "제26조와 별표 4이나, 현재 시스템이 별표에서 시간 값을 안정적으로 추출하지 못했습니다. "
                    "임의의 다른 법령 근거로 답하지 않겠습니다."
                ),
            ]
        )
        if items:
            for item in items:
                target = self.strip_internal_ids(item.get("target")) or "교육대상"
                value = self.strip_internal_ids(item.get("time_value")) or "현재 자동 추출 실패"
                sections.append(f"- {target}: {value}")

        sections.extend(
            [
                "",
                "[근거]",
                "- 산업안전보건법 시행규칙 제26조: 교육시간은 별표 4에 따른다고 규정",
                "- 산업안전보건법 시행규칙 별표 4: 안전보건교육 교육과정별 교육시간",
                "",
                "[주의]",
                "- 시간 값이 자동 추출되지 않은 항목은 별표 4의 해당 행을 직접 확인해야 합니다. 다만, 질문과 무관한 다른 법령 근거로 답하지 않습니다.",
            ]
        )
        for warning in domain_result.get("warnings") or []:
            text = self.strip_internal_ids(warning)
            if text and text not in "\n".join(sections):
                sections.append(f"- {text}")

        sections.extend(
            [
                "",
                "[다음 확인]",
                "- 실제 대상이 사무직/비사무직/관리감독자 중 어디에 해당하는지 확인",
                "- 정기교육 외에 채용 시 교육 또는 특별교육인지 확인",
                "- 교육 면제 또는 단축 조건이 있는지 확인",
            ]
        )
        return self.remove_forbidden_education_terms("\n".join(sections).strip())

    def build_domain_source_lines(self, sources: list[dict]) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for source in sources[:5]:
            if not isinstance(source, dict):
                continue
            label = " ".join(
                str(part)
                for part in (source.get("law_name"), source.get("article_no"), source.get("title"))
                if part
            )
            label = self.strip_internal_ids(label) or "연결 근거"
            preview = self._short(source.get("source_text") or "", 180)
            line = f"- {label}" + (f": {preview}" if preview else "")
            if line not in seen:
                seen.add(line)
                lines.append(line)
        return lines or ["- 질문 유형에 맞는 근거 출처를 충분히 구조화하지 못했습니다."]

    def build_legal_chain_lines(self, evidence_pack: dict) -> list[str]:
        candidates: list[tuple[int, str]] = []
        seen: set[str] = set()
        for chain in evidence_pack.get("legal_chains") or []:
            if not isinstance(chain, dict):
                continue
            source = chain.get("source") or {}
            source_label = " ".join(
                str(part)
                for part in (source.get("law_name"), source.get("article_no"))
                if part
            )
            source_label = self.strip_internal_ids(source_label)
            if chain.get("target_ref"):
                fine_source = self.strip_internal_ids(str(chain.get("source_ref") or source.get("source_ref") or source_label))
                fine_target = self.strip_internal_ids(str(chain.get("target_ref") or ""))
                status = chain.get("status") or "TEXT_REFERENCE_CANDIDATE"
                if fine_source and fine_target and status != "WEAK_CANDIDATE":
                    priority = {
                        "CONFIRMED": -10,
                        "RULE_BASED_CANDIDATE": -9,
                        "TEXT_REFERENCE_CANDIDATE": -9,
                    }.get(status, -8)
                    line = f"- {fine_source} -> {fine_target} (세부 조문 연결 후보)"
                    if line not in seen:
                        seen.add(line)
                        candidates.append((priority, line))
                continue
            for penalty in chain.get("penalties") or []:
                if not isinstance(penalty, dict):
                    continue
                penalty_label = " ".join(
                    str(part)
                    for part in (penalty.get("law_name"), penalty.get("article_no"))
                    if part
                )
                penalty_label = self.strip_internal_ids(penalty_label)
                if not source_label or not penalty_label:
                    continue
                status = penalty.get("candidate_status") or ("CONFIRMED" if penalty.get("is_confirmed") else "TEXT_REFERENCE_CANDIDATE")
                if status == "WEAK_CANDIDATE":
                    continue
                priority = {
                    "CONFIRMED": 0,
                    "RULE_BASED_CANDIDATE": 1,
                    "TEXT_REFERENCE_CANDIDATE": 2,
                    "WEAK_CANDIDATE": 3,
                }.get(status, 2)
                basis = {
                    "CONFIRMED": "직접 연결",
                    "RULE_BASED_CANDIDATE": "구조적 검토 후보",
                    "TEXT_REFERENCE_CANDIDATE": "조문 참조 후보",
                    "WEAK_CANDIDATE": "약한 후보",
                }.get(status, "조문 참조 후보")
                preview = self._short(penalty.get("source_text_preview") or penalty.get("source_text") or "", 140)
                line = f"- {source_label} 위반 근거 -> {penalty_label} ({basis})"
                if preview:
                    line += f": {preview}"
                review_reason = penalty.get("review_reason") or ""
                if review_reason and status == "RULE_BASED_CANDIDATE":
                    line += f" 검토 필요: {self._short(review_reason, 90)}"
                if line in seen:
                    continue
                seen.add(line)
                candidates.append((priority, line))
        candidates.sort(key=lambda item: item[0])
        return [line for _, line in candidates[:6]]

    def build_legal_bundle_lines(self, evidence_pack: dict) -> list[str]:
        bundle = evidence_pack.get("legal_bundle") or {}
        if not isinstance(bundle, dict):
            return []
        slot_labels = [
            ("primary_obligation", "핵심 의무"),
            ("health_obligation", "보건조치"),
            ("contractor_obligation", "도급 관련 의무"),
            ("serious_accident_obligation", "중대재해 의무"),
            ("penalty", "처벌"),
            ("corporate_penalty", "양벌·법인 처벌"),
            ("definition_or_scope", "정의·적용범위"),
            ("purpose_support", "목적 보조"),
        ]
        lines: list[str] = []
        seen: set[str] = set()
        for slot, label in slot_labels:
            items = bundle.get(slot) or []
            if not isinstance(items, list):
                continue
            refs: list[str] = []
            has_candidate = False
            for item in items:
                if not isinstance(item, dict):
                    continue
                law = self.strip_internal_ids(str(item.get("law_name") or ""))
                article = self.strip_internal_ids(str(item.get("article_no") or ""))
                if not law or not article:
                    continue
                paragraph = self.strip_internal_ids(str(item.get("paragraph_no") or ""))
                item_no = self.strip_internal_ids(str(item.get("item_no") or ""))
                subitem_no = self.strip_internal_ids(str(item.get("subitem_no") or ""))
                status = str(item.get("status") or item.get("candidate_status") or "")
                if "CANDIDATE" in status or status in {"SUPPORTING_DEFINITION"}:
                    has_candidate = True
                ref = " ".join(part for part in (law, article, paragraph, item_no, subitem_no) if part)
                if ref not in refs:
                    refs.append(ref)
            if not refs:
                continue
            suffix = " 함께 검토됩니다."
            if has_candidate or slot in {"penalty", "corporate_penalty", "purpose_support", "definition_or_scope"}:
                suffix = " 사실관계와 적용요건에 따라 검토될 수 있는 근거입니다."
            line = f"- {label}: {', '.join(refs[:5])}.{suffix}"
            if line not in seen:
                seen.add(line)
                lines.append(line)
        return lines[:8]

    def build_conclusion(self, evidence_pack: dict, citations: list[dict], claim_check: dict) -> str:
        policy = claim_check.get("answer_policy") or "REFUSE_OR_REQUEST_MORE_EVIDENCE"
        intent = evidence_pack.get("intent") or ""
        query = evidence_pack.get("query") or ""
        if policy == "INDIRECT_ONLY_RESPONSE":
            return (
                "현재 KB에서는 이 질문에 직접 답할 수 있는 법령 근거가 확인되지 않습니다. "
                "아래 내용은 관련성이 있는 간접 근거를 바탕으로 한 제한적 설명입니다."
            )
        if policy == "REFUSE_OR_REQUEST_MORE_EVIDENCE":
            return "현재 근거만으로는 답변을 단정하기 어렵습니다. 추가 조건이나 직접 근거가 필요합니다."
        if intent == "education_time_lookup" or ("교육" in query and "시간" in query):
            return (
                "정기 안전보건교육 시간은 교육대상과 교육구분에 따라 달라지며, 시행규칙 제26조 및 "
                "별표 4에서 대상별로 확인해야 합니다."
            )
        if policy == "ALLOW_WITH_CAUTION":
            return "근거는 확인되지만 적용 조건, 예외 또는 수치 기준을 함께 확인해야 합니다."
        return "확인된 근거를 기준으로 답변할 수 있습니다."

    def build_evidence_summary(self, citations: list[dict], evidence_pack: dict) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for citation in citations[:5]:
            label = citation.get("citation_text") or " ".join(
                str(part)
                for part in (citation.get("law_name"), citation.get("article_no"), citation.get("annex_title"))
                if part
            )
            label = self.strip_internal_ids(label) or "근거 위치 미확인"
            if label in seen:
                continue
            seen.add(label)
            preview = self._short(citation.get("source_text_preview") or citation.get("preview") or "", 160)
            lines.append(f"- {label}" + (f": {preview}" if preview else ""))
        if lines:
            return lines
        return ["- 현재 표시 가능한 근거 요약이 부족합니다. 연결된 상세 근거에서 원문을 확인하세요."]

    def build_caution_lines(self, policy: str, warnings: list[Any], missing: list[Any]) -> list[str]:
        lines: list[str] = []
        if policy == "INDIRECT_ONLY_RESPONSE":
            lines.append("- 직접 근거가 확인되지 않았으므로 의무 여부를 단정하지 않습니다.")
        elif policy == "ALLOW_WITH_CAUTION":
            lines.append("- 근거는 확인되지만 적용 조건, 예외, 수치 기준을 함께 확인해야 합니다.")
        for warning in warnings[:4]:
            text = self.format_user_warning(warning)
            if text and f"- {text}" not in lines:
                lines.append(f"- {text}")
        for item in missing[:3]:
            text = self._missing_text(item)
            if text and f"- {text}" not in lines:
                lines.append(f"- {text}")
        return lines

    def build_next_checks(self, evidence_pack: dict, claim_check: dict) -> list[str]:
        intent = evidence_pack.get("intent") or ""
        policy = claim_check.get("answer_policy") or ""
        if intent == "education_time_lookup":
            return [
                "- 사무직/비사무직/관리감독자 여부를 먼저 구분하세요.",
                "- 정기교육, 채용 시 교육, 특별교육 중 어떤 교육인지 확인하세요.",
                "- 정확한 시간은 별표 4 원문에서 교육대상과 교육구분을 함께 확인하세요.",
            ]
        if policy == "INDIRECT_ONLY_RESPONSE":
            return ["- 직접 의무 조항이 있는지 별도 확인하기 전에는 단정 답변으로 사용하지 마세요."]
        if policy == "ALLOW_WITH_CAUTION":
            return ["- 적용 조건, 예외, 대상 범위를 확인한 뒤 답변을 사용하세요."]
        return ["- 연결된 근거 원문과 현장 조건이 일치하는지 확인하세요."]

    def format_user_warning(self, warning: Any) -> str:
        if isinstance(warning, dict):
            warning_type = str(warning.get("warning_type") or "")
            message = str(warning.get("message") or "")
        else:
            warning_type = ""
            message = str(warning or "")
        source = f"{warning_type} {message}"
        if "THRESHOLD_MISSING" in source or "Education time evidence candidate has no threshold" in source:
            return "교육시간 값이 구조화된 형태로 분리되지 않았습니다. 정확한 시간은 별표 4의 대상별 행에서 확인해야 합니다."
        if "Many evidence candidates were found" in source or "top-k ambiguity" in source:
            return "관련 근거 후보가 여러 개 확인되어, 가장 직접적인 별표/조문을 우선 확인해야 합니다."
        if "DIRECT_PENALTY_NOT_FOUND" in source:
            return "현재 연결된 근거에서는 직접 처벌 조항이 확인되지 않았습니다."
        if "CANDIDATE_PENALTY_REQUIRES_REVIEW" in source:
            return "관련 가능성이 있는 벌칙·과태료 조항 후보가 있으나, 확정 처벌 결론은 아닙니다."
        return "일부 근거는 적용 조건 또는 예외 확인이 필요합니다."

    def enforce_policy(self, draft_answer: str, evidence_pack: dict, claim_check: dict) -> dict:
        policy = claim_check.get("answer_policy")
        notes: list[str] = []
        answer = self.strip_internal_ids(draft_answer)
        if policy == "INDIRECT_ONLY_RESPONSE":
            required = "현재 KB에서는 이 질문에 직접 답할 수 있는 법령 근거가 확인되지 않습니다."
            if required not in answer:
                answer = f"[결론]\n{required} 아래 내용은 간접 근거 기반의 제한적 설명입니다.\n\n{answer}"
                notes.append("Inserted indirect-only guardrail sentence.")
            conclusion = answer.split("[근거]", 1)[0]
            direct_markers = ("반드시 알려야 합니다", "고지해야 합니다", "알려야 합니다.", "의무입니다")
            if any(marker in conclusion for marker in direct_markers):
                notes.append("Direct obligation marker detected in indirect-only conclusion.")
        return {"answer": answer.strip(), "policy_enforced": True, "policy_notes": notes}

    def generate_llm_answer(self, evidence_pack: dict, citations: list[dict], claim_check: dict) -> dict:
        result = self.generate_template_answer(evidence_pack, citations, claim_check)
        result.update(
            {
                "template_answer": False,
                "llm_used": False,
                "llm_polish_mode": False,
                "llm_fallback_reason": "legacy_generate_llm_answer_disabled",
                "prompt_preview": self.build_prompt(evidence_pack, citations, claim_check)[:1000],
            }
        )
        return result

    def build_prompt(self, evidence_pack: dict, citations: list[dict], claim_check: dict) -> str:
        return "\n".join(
            [
                "You are a legal Graph-RAG answer editor.",
                "Use only the provided Evidence Pack and citations.",
                "Do not invent law names, article numbers, education hours, penalties, or obligations.",
                f"answer_policy: {claim_check.get('answer_policy')}",
                f"query: {evidence_pack.get('query')}",
                f"intent: {evidence_pack.get('intent')}",
                f"citations: {citations[:5]}",
            ]
        )

    def _result(
        self,
        enforced: dict,
        policy: str,
        evidence_pack: dict,
        claim_check: dict,
        warnings: list[Any],
        missing: list[Any],
    ) -> dict:
        return {
            "answer": enforced["answer"],
            "answer_policy": policy,
            "claim_check_status": claim_check.get("claim_check_status"),
            "evidence_readiness": evidence_pack.get("evidence_readiness"),
            "citations_used": [],
            "warnings": warnings,
            "missing_evidence": missing,
            "llm_used": False,
            "template_answer": True,
            "policy_enforced": enforced["policy_enforced"],
            "policy_notes": enforced["policy_notes"],
        }

    def remove_forbidden_education_terms(self, text: str) -> str:
        clean = str(text or "")
        for term in FORBIDDEN_EDUCATION_FALLBACK_TERMS:
            clean = clean.replace(term, "")
        return clean

    def strip_internal_ids(self, text: Any) -> str:
        clean = UUID_RE.sub("", str(text or ""))
        clean = re.sub(r"warning:\s*[A-Z_]+\s*-\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(
            r"\b(?:source_node_id|source_anchor_id|rule_id|list_item_id)\s*[:=]\s*\S+",
            "",
            clean,
            flags=re.IGNORECASE,
        )
        clean = re.sub(
            r"\b(?:THRESHOLD_MISSING|DIRECT_PENALTY_NOT_FOUND|CANDIDATE_PENALTY_REQUIRES_REVIEW)\b",
            "",
            clean,
        )
        clean = clean.replace("Education time evidence candidate has no threshold.", "")
        clean = clean.replace("Many evidence candidates were found; top-k ambiguity is possible.", "")
        clean = clean.replace("\r", "\n")
        return re.sub(r"[ \t]+", " ", clean).strip()

    def _missing_text(self, item: Any) -> str:
        if isinstance(item, str):
            return self.strip_internal_ids(item)
        if isinstance(item, dict):
            label = item.get("label") or item.get("description") or item.get("reason") or item.get("evidence_type")
            if label:
                return self.strip_internal_ids(label)
        return "추가 근거 항목 확인이 필요합니다."

    def _short(self, text: Any, max_length: int) -> str:
        clean = self.strip_internal_ids(text)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) <= max_length:
            return clean
        return clean[: max_length - 3].rstrip() + "..."
