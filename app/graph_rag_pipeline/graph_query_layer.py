#!/usr/bin/env python
"""Read-only Neo4j graph query layer for Graph-RAG evidence candidates.

This module does not generate answers and does not call an LLM. It only wraps
read-only Cypher queries against graph.v1 and returns JSON-serializable data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ALLOWED_DATABASE = "graph.v1"
WRITE_KEYWORD_RE = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP)\b|CALL\s+db\.create|CALL\s+apoc\.create|CALL\s+apoc\.merge|LOAD\s+CSV",
    re.IGNORECASE,
)


class GraphQueryError(RuntimeError):
    """Raised when a graph query cannot be safely executed."""


def _read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        raise GraphQueryError(f".env not found: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        if not env.get(key):
            raise GraphQueryError(f"missing required env key: {key}")
    if env["NEO4J_DATABASE"] != ALLOWED_DATABASE:
        raise GraphQueryError(f"target database must be {ALLOWED_DATABASE}, got {env['NEO4J_DATABASE']}")
    return env


def _strip_comments(cypher: str) -> str:
    lines = []
    for line in cypher.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        lines.append(line.split("//", 1)[0])
    text = "\n".join(lines)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return text


def _ensure_read_only(cypher: str) -> None:
    cleaned = _strip_comments(cypher)
    match = WRITE_KEYWORD_RE.search(cleaned)
    if match:
        raise GraphQueryError(f"blocked non-read-only Cypher keyword: {match.group(0)}")


def _preview(value: Any, limit: int = 300) -> Any:
    if not isinstance(value, str):
        return value
    text = value.replace("\r", " ").replace("\n", " ").strip()
    return text[: limit - 3] + "..." if len(text) > limit else text


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return _preview(value)
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    if isinstance(value, tuple):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if hasattr(value, "items"):
        try:
            data = dict(value)
            labels = sorted(value.labels) if hasattr(value, "labels") else None
            result = {str(k): _json_value(v) for k, v in data.items()}
            if labels is not None:
                result["_labels"] = labels
            return result
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def _records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [{key: _json_value(record[key]) for key in record.keys()} for record in records]


def _dedupe_dicts(items: list[dict[str, Any]], key_candidates: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not item:
            continue
        key = next((str(item.get(k)) for k in key_candidates if item.get(k)), repr(sorted(item.items())))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _anchor_id(anchor: dict[str, Any]) -> str:
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


def _text_score(row: dict[str, Any], keyword: str, intent: str | None = None) -> int:
    keyword_l = keyword.lower()
    score = 0
    weighted = {
        "source_text": 5,
        "requirement_text": 4,
        "condition_text": 4,
        "penalty_text": 4,
        "source_context_text": 3,
        "annex_title": 3,
        "law_name": 2,
        "article_no": 2,
    }
    for field, weight in weighted.items():
        value = str(row.get(field) or "").lower()
        if keyword_l and keyword_l in value:
            score += weight
    subtype = str(row.get("rule_subtype") or "")
    rtype = str(row.get("rule_type") or "")
    if intent == "education_time_lookup" and ("EDUCATION_TIME" in subtype or "EDUCATION" in subtype):
        score += 5
    if intent == "penalty_lookup" and (rtype == "PENALTY" or subtype in {"PENALTY_FINE", "ADMINISTRATIVE_FINE"}):
        score += 6
    if intent in {"obligation_penalty_chain", "safety_measure_lookup"}:
        if rtype in {"OBLIGATION", "PROCEDURE", "SAFETY_STANDARD"}:
            score += 8
        if "PENALTY" in rtype or "PENALTY" in subtype:
            score += 3
        if rtype == "DEFINITION" or subtype in {"DEFINITION", "APPLICABILITY_RULE"}:
            score -= 6
    if intent == "definition_lookup" and (rtype == "DEFINITION" or subtype == "DEFINITION"):
        score += 6
    if intent in {"applicability_check"} and ("EXCEPTION" in subtype or "SCOPE" in subtype):
        score += 3
    return score


def extract_search_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[0-9A-Za-z가-힣]+", query)
    suffixes = ("에게", "에는", "에서", "으로", "해야", "하나", "되는", "인가", "자는", "들은", "에게도", "에게는", "은", "는", "이", "가", "을", "를", "에", "의")
    terms: list[str] = []
    for raw in raw_terms:
        term = raw.strip()
        for suffix in suffixes:
            if len(term) > len(suffix) + 1 and term.endswith(suffix):
                term = term[: -len(suffix)]
                break
        if len(term) >= 2 and term not in {"어떤", "무엇", "경우", "기준"}:
            terms.append(term)
    text = query
    if "위험성평가" in text:
        terms.extend(["위험성평가", "결과", "근로자", "알림", "알리", "고지", "주지", "통보"])
    if "안전보건교육" in text or "교육" in text:
        terms.extend(["정기", "안전보건교육", "교육", "시간", "몇 시간", "별표"])
    if "안전검사" in text or "대상 기계" in text or "기계" in text:
        terms.extend(["안전검사", "대상", "기계", "안전검사대상기계", "크레인", "리프트", "곤돌라", "프레스", "전단기"])
    if "과태료" in text:
        terms.extend(["과태료", "부과", "위반", "기준"])
    if any(term in text for term in ("추락", "붕괴", "낙하", "화재", "폭발", "감전", "질식", "끼임", "협착", "크레인", "비계", "굴착")):
        terms.extend(["안전조치", "보건조치", "위험", "방지", "예방", "의무", "위반"])
    if any(term in text for term in ("처벌", "벌칙", "벌금", "징역", "양벌", "중대재해")):
        terms.extend(["처벌", "벌칙", "벌금", "징역", "양벌", "위반", "경영책임자", "사업주"])
    if "적용" in text and "제외" in text:
        terms.extend(["적용 제외", "적용", "제외", "예외"])
    # Keep order while removing duplicates.
    return list(dict.fromkeys(terms)) or ([query] if query else [])


def _multi_term_score(row: dict[str, Any], terms: list[str], intent: str | None = None) -> int:
    score = 0
    for term in terms:
        score += _text_score(row, term, intent)
    return score


def _query_has_any(query: str, terms: tuple[str, ...]) -> bool:
    return any(term in query for term in terms)


def _article_digits(article_no: Any) -> str:
    return re.sub(r"\D+", "", str(article_no or ""))


def _is_law_article(row: dict[str, Any], law_keyword: str, article_no: str) -> bool:
    law_name = str(row.get("law_name") or "")
    if law_keyword == "산업안전보건법":
        return law_name == "산업안전보건법" and str(row.get("article_no") or "") == article_no
    if law_keyword == "중대재해처벌법":
        return "중대재해" in law_name and "시행령" not in law_name and str(row.get("article_no") or "") == article_no
    return law_keyword in law_name and str(row.get("article_no") or "") == article_no


def _seed_boost_for_row(row: dict[str, Any], query: str, intent: str) -> tuple[int, list[str]]:
    if intent != "obligation_penalty_chain":
        return 0, []
    boost = 0
    reasons: list[str] = []
    accident_terms = ("추락", "붕괴", "낙하", "끼임", "협착", "충돌", "전도", "크레인", "비계", "굴착", "안전조치", "위험작업", "산업재해 예방")
    health_terms = ("보건조치", "질식", "유해물질", "건강장해", "화학물질")
    contract_terms = ("도급", "수급", "관계수급인", "하청", "용역", "위탁", "혼재작업", "도급사업주")
    serious_terms = ("사망", "중대재해", "중대산업재해", "경영책임자", "대표이사", "안전보건 확보의무", "안전보건관리체계")
    penalty_terms = ("처벌", "벌칙", "벌금", "징역", "양벌", "위반")
    admin_fine_only = "과태료" in query and not _query_has_any(query, ("처벌", "벌칙", "벌금", "징역", "양벌"))

    if _query_has_any(query, accident_terms) and _is_law_article(row, "산업안전보건법", "제38조"):
        boost += 140
        reasons.append("legal_chain_seed_boost:osh_act_38_safety_measure")
        if "안전조치" in query:
            boost += 40
            reasons.append("legal_chain_seed_boost:explicit_safety_measure")
    if _query_has_any(query, health_terms) and _is_law_article(row, "산업안전보건법", "제39조"):
        boost += 80
        reasons.append("legal_chain_seed_boost:osh_act_39_health_measure")
    if _query_has_any(query, contract_terms):
        if _is_law_article(row, "산업안전보건법", "제63조") or _is_law_article(row, "산업안전보건법", "제64조"):
            boost += 90
            reasons.append("legal_chain_seed_boost:osh_contract_obligation")
        if _is_law_article(row, "중대재해처벌법", "제5조"):
            boost += 90
            reasons.append("legal_chain_seed_boost:sapa_contract_obligation")
    if _query_has_any(query, serious_terms):
        if _is_law_article(row, "중대재해처벌법", "제4조"):
            boost += 130
            reasons.append("legal_chain_seed_boost:sapa_article_4")
        if _is_law_article(row, "중대재해처벌법", "제6조") or _is_law_article(row, "중대재해처벌법", "제7조"):
            boost += 25
            reasons.append("penalty_chain_seed_boost:sapa_penalty")
        if _is_law_article(row, "산업안전보건법", "제167조") or _is_law_article(row, "산업안전보건법", "제173조"):
            boost += 35
            reasons.append("penalty_chain_seed_boost:osh_fatal_penalty")
    if _query_has_any(query, penalty_terms) and not admin_fine_only:
        if _is_law_article(row, "산업안전보건법", "제167조") or _is_law_article(row, "산업안전보건법", "제173조"):
            boost += 50
            reasons.append("penalty_chain_seed_boost:osh_penalty")
        if _is_law_article(row, "중대재해처벌법", "제6조") or _is_law_article(row, "중대재해처벌법", "제7조"):
            boost += 25
            reasons.append("penalty_chain_seed_boost:sapa_penalty")
    return boost, reasons


class GraphQueryLayer:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).resolve()
        self.env = _read_env(self.root_dir / ".env")
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise GraphQueryError("neo4j Python package is required") from exc
        self.driver = GraphDatabase.driver(
            self.env["NEO4J_URI"],
            auth=(self.env["NEO4J_USER"], self.env["NEO4J_PASSWORD"]),
        )
        self.database = self.env["NEO4J_DATABASE"]

    def close(self):
        self.driver.close()

    def run_read_query(self, cypher: str, params: dict | None = None) -> list[dict]:
        _ensure_read_only(cypher)
        params = params or {}
        with self.driver.session(database=self.database, default_access_mode="READ") as session:
            records = session.execute_read(lambda tx: list(tx.run(cypher, **params)))
        return _records_to_dicts(records)

    def get_graph_counts(self) -> dict:
        node_counts = self.run_read_query(
            "MATCH (n) RETURN labels(n) AS labels, count(n) AS count ORDER BY count DESC"
        )
        rel_counts = self.run_read_query(
            "MATCH ()-[r]->() RETURN type(r) AS relationship_type, count(r) AS count ORDER BY count DESC"
        )
        scalar = self.run_read_query(
            """
            MATCH (n)
            WITH count(n) AS total_nodes
            MATCH ()-[rel]->()
            WITH total_nodes, count(rel) AS total_relationships
            MATCH (r:Rule)
            WITH total_nodes, total_relationships,
                 count(CASE WHEN r.source_text IS NULL OR trim(r.source_text) = "" THEN 1 END) AS missing_source_text_rules,
                 count(CASE WHEN NOT (r)-[:EXTRACTED_FROM]->(:SourceNode) THEN 1 END) AS rules_without_source
            MATCH (s:SourceNode)
            WITH total_nodes, total_relationships, missing_source_text_rules, rules_without_source,
                 count(CASE WHEN NOT (s)-[:RESOLVES_TO]->() THEN 1 END) AS unresolved_source_nodes
            OPTIONAL MATCH (:ListItem)-[ir:ITEM_RESOLVES_TO]->()
            RETURN total_nodes, total_relationships, missing_source_text_rules,
                   rules_without_source, unresolved_source_nodes,
                   count(ir) AS item_resolves_to_count
            """
        )[0]
        return {
            **scalar,
            "node_counts_by_label": node_counts,
            "relationship_counts_by_type": rel_counts,
        }

    def get_rule_evidence_pack_by_rule_id(self, rule_id: str) -> dict:
        rows = self.run_read_query(
            """
            MATCH (r:Rule {rule_id: $rule_id})
            OPTIONAL MATCH (r)-[:HAS_REQUIREMENT]->(req:Requirement)
            OPTIONAL MATCH (r)-[:HAS_THRESHOLD]->(th:Threshold)
            OPTIONAL MATCH (r)-[:HAS_EXCEPTION]->(ex:Exception)
            OPTIONAL MATCH (r)-[:HAS_TEMPORAL_CONDITION]->(tmp:TemporalRule)
            OPTIONAL MATCH (r)-[entRel:RELATED_ENTITY]->(ent:EntityType)
            OPTIONAL MATCH (r)-[:HAS_LIST_ITEM]->(li:ListItem)
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)
            OPTIONAL MATCH (src)-[:RESOLVES_TO]->(anchor)
            OPTIONAL MATCH (r)-[rr:RELATED_RULE]->(related:Rule)
            RETURN r AS rule,
                   collect(DISTINCT req) AS requirements,
                   collect(DISTINCT th) AS thresholds,
                   collect(DISTINCT ex) AS exceptions,
                   collect(DISTINCT tmp) AS temporal_rules,
                   collect(DISTINCT {rel: entRel.rel, entity: ent}) AS entities,
                   collect(DISTINCT li) AS list_items,
                   collect(DISTINCT src) AS source_nodes,
                   collect(DISTINCT anchor) AS source_anchors,
                   collect(DISTINCT {rel: rr.rel, rule: related}) AS related_rules
            """,
            {"rule_id": rule_id},
        )
        if not rows:
            return {"rule_id": rule_id, "found": False}
        row = rows[0]
        return {
            "found": True,
            "rule": row["rule"],
            "requirements": _dedupe_dicts(row["requirements"], ("requirement_id",)),
            "thresholds": _dedupe_dicts(row["thresholds"], ("threshold_id",)),
            "exceptions": _dedupe_dicts(row["exceptions"], ("exception_id",)),
            "temporal_rules": _dedupe_dicts(row["temporal_rules"], ("temporal_rule_id",)),
            "entities": [e for e in row["entities"] if e.get("entity")],
            "list_items": _dedupe_dicts(row["list_items"], ("list_item_id",)),
            "source_nodes": _dedupe_dicts(row["source_nodes"], ("source_node_id",)),
            "source_anchors": _dedupe_dicts(row["source_anchors"], ("article_id", "paragraph_id", "item_id", "subitem_id", "logical_row_id", "logical_cell_id", "note_id")),
            "related_rules": [r for r in row["related_rules"] if r.get("rule")],
        }

    def search_rules_by_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        terms = extract_search_terms(keyword)
        rows = self.run_read_query(
            """
            MATCH (r:Rule)
            WHERE any(term IN $terms WHERE
                  r.source_text CONTAINS term
               OR r.source_context_text CONTAINS term
               OR r.requirement_text CONTAINS term
               OR r.condition_text CONTAINS term
               OR r.penalty_text CONTAINS term
               OR r.law_name CONTAINS term
               OR r.article_no CONTAINS term
               OR r.annex_title CONTAINS term)
            RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
                   r.law_name AS law_name, r.article_no AS article_no, r.annex_title AS annex_title,
                   r.source_text AS source_text, r.requirement_text AS requirement_text,
                   r.condition_text AS condition_text, r.penalty_text AS penalty_text,
                   r.source_context_text AS source_context_text
            LIMIT $limit
            """,
            {"terms": terms, "limit": max(limit * 10, limit)},
        )
        for row in rows:
            row["score"] = _multi_term_score(row, terms)
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows[:limit]

    def search_rules_by_intent_keywords(self, query: str, intent: str, limit: int = 10) -> list[dict]:
        if intent in {"inspection_requirement", "list_lookup", "education_content_lookup"}:
            return self.get_listitem_evidence(query, limit)
        if intent == "obligation_check" and "위험성평가" in query:
            return self.search_risk_assessment_worker_notice_rules(query, limit)
        rows = self.search_rules_by_keyword(query, max(limit * 3, limit))
        if intent == "obligation_penalty_chain":
            rows = self._merge_seed_rule_candidates(rows, query, limit)
        for row in rows:
            row["score"] = int(row.get("score", 0)) + _multi_term_score(row, extract_search_terms(query), intent)
            boost, reasons = _seed_boost_for_row(row, query, intent)
            if boost:
                row["score"] += boost
                row["source_reason"] = "intent_seed_boost"
                existing = row.get("score_breakdown") or []
                row["score_breakdown"] = existing + reasons
        if intent == "education_time_lookup":
            threshold_ids = {
                r["rule_id"]
                for r in self.run_read_query(
                    "MATCH (r:Rule)-[:HAS_THRESHOLD]->(:Threshold) RETURN r.rule_id AS rule_id LIMIT 10000"
                )
            }
            for row in rows:
                if row["rule_id"] in threshold_ids:
                    row["score"] += 4
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows[:limit]

    def _merge_seed_rule_candidates(self, rows: list[dict], query: str, limit: int) -> list[dict]:
        seed_refs: list[tuple[str, str]] = []
        accident_terms = ("추락", "붕괴", "낙하", "끼임", "협착", "충돌", "전도", "크레인", "비계", "굴착", "안전조치", "위험작업", "산업재해 예방")
        health_terms = ("보건조치", "질식", "유해물질", "건강장해", "화학물질")
        contract_terms = ("도급", "수급", "관계수급인", "하청", "용역", "위탁", "혼재작업", "도급사업주")
        serious_terms = ("사망", "중대재해", "중대산업재해", "경영책임자", "대표이사", "안전보건 확보의무", "안전보건관리체계")
        penalty_terms = ("처벌", "벌칙", "벌금", "징역", "양벌", "위반")
        admin_fine_only = "과태료" in query and not _query_has_any(query, penalty_terms)

        if _query_has_any(query, accident_terms):
            seed_refs.append(("산업안전보건법", "제38조"))
        if _query_has_any(query, health_terms):
            seed_refs.append(("산업안전보건법", "제39조"))
        if _query_has_any(query, contract_terms):
            seed_refs.extend([("산업안전보건법", "제63조"), ("산업안전보건법", "제64조"), ("중대재해처벌법", "제5조")])
        if _query_has_any(query, serious_terms):
            seed_refs.extend([("중대재해처벌법", "제4조"), ("중대재해처벌법", "제6조"), ("중대재해처벌법", "제7조"), ("산업안전보건법", "제167조"), ("산업안전보건법", "제173조")])
        if _query_has_any(query, penalty_terms) and not admin_fine_only:
            seed_refs.extend([("산업안전보건법", "제167조"), ("산업안전보건법", "제173조"), ("중대재해처벌법", "제6조"), ("중대재해처벌법", "제7조")])

        seed_refs = list(dict.fromkeys(seed_refs))
        if not seed_refs:
            return rows
        seed_rows = self.find_rules_by_law_articles(seed_refs, max(limit * 2, 20))
        by_id = {row.get("rule_id"): row for row in rows if row.get("rule_id")}
        merged = list(rows)
        for seed in seed_rows:
            rule_id = seed.get("rule_id")
            if not rule_id or rule_id in by_id:
                continue
            seed["score"] = int(seed.get("score") or 0) + 1
            seed["source_reason"] = "legal_chain_seed_boost"
            seed["score_breakdown"] = ["seed_candidate_added"]
            merged.append(seed)
            by_id[rule_id] = seed
        return merged

    def find_rules_by_law_articles(self, refs: list[tuple[str, str]], limit: int = 20) -> list[dict]:
        if not refs:
            return []
        ref_maps = [{"law": law, "article": article} for law, article in refs]
        return self.run_read_query(
            """
            MATCH (r:Rule)
            WHERE any(ref IN $refs WHERE r.article_no = ref.article AND (
                (ref.law = "산업안전보건법" AND r.law_name = "산업안전보건법")
                OR (ref.law = "중대재해처벌법" AND r.law_name CONTAINS "중대재해" AND NOT r.law_name CONTAINS "시행령")
                OR (ref.law <> "산업안전보건법" AND ref.law <> "중대재해처벌법" AND r.law_name CONTAINS ref.law)
            ))
            RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
                   r.law_name AS law_name, r.article_no AS article_no, r.annex_title AS annex_title,
                   r.source_text AS source_text, r.requirement_text AS requirement_text,
                   r.condition_text AS condition_text, r.penalty_text AS penalty_text,
                   r.source_context_text AS source_context_text
            LIMIT $limit
            """,
            {"refs": ref_maps, "limit": limit},
        )

    def search_risk_assessment_worker_notice_rules(self, query: str, limit: int = 10) -> list[dict]:
        rows = self.run_read_query(
            """
            MATCH (r:Rule)
            WHERE r.source_text CONTAINS "위험성평가"
               OR r.source_context_text CONTAINS "위험성평가"
               OR r.requirement_text CONTAINS "위험성평가"
            RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
                   r.law_name AS law_name, r.article_no AS article_no, r.annex_title AS annex_title,
                   r.source_text AS source_text, r.requirement_text AS requirement_text,
                   r.condition_text AS condition_text, r.penalty_text AS penalty_text,
                   r.source_context_text AS source_context_text
            LIMIT 100
            """
        )
        core = ("위험성평가", "결과", "근로자")
        notice = ("알리", "알림", "고지", "주지", "통보", "참여", "공유")
        for row in rows:
            text = " ".join(str(row.get(k) or "") for k in ("source_text", "requirement_text", "source_context_text", "condition_text"))
            score = 0
            score += sum(8 for term in core if term in text)
            score += sum(10 for term in notice if term in text)
            if row.get("rule_type") in {"OBLIGATION", "PROCEDURE", "SAFETY_STANDARD"}:
                score += 5
            if "위험성평가" not in text:
                score -= 20
            row["score"] = score
            row["rank_reason"] = "risk_assessment_worker_notice_terms"
        rows.sort(key=lambda r: r.get("score", 0), reverse=True)
        return rows[:limit]

    def get_education_time_pack_candidates(self, query: str, limit: int = 20) -> dict:
        rule_thresholds = self.get_education_time_evidence(limit)
        annex_rows = self.run_read_query(
            """
            MATCH (ann:Annex)-[:HAS_LOGICAL_ROW]->(lr:LogicalRow)-[:HAS_LOGICAL_CELL]->(lc:LogicalCell)
            WHERE ann.annex_title CONTAINS "교육"
               OR lr.source_text CONTAINS "교육"
               OR lc.source_text CONTAINS "교육"
               OR lr.source_text CONTAINS "시간"
               OR lc.source_text CONTAINS "시간"
            RETURN ann AS annex, lr AS logical_row, collect(lc)[0..20] AS logical_cells
            LIMIT $limit
            """,
            {"limit": limit},
        )
        return {"rule_thresholds": rule_thresholds, "annex_logical_evidence": annex_rows}

    def find_education_time_sources(self, query: str, limit: int = 50) -> list[dict]:
        rows = self.run_read_query(
            """
            MATCH (ann:Annex)-[:HAS_LOGICAL_ROW]->(lr:LogicalRow)
            OPTIONAL MATCH (lr)-[:HAS_LOGICAL_CELL]->(lc:LogicalCell)
            WHERE ann.annex_title CONTAINS "교육"
               OR ann.annex_title CONTAINS "별표 4"
               OR lr.source_text CONTAINS "교육시간"
               OR lr.source_text CONTAINS "비사무직"
               OR lr.source_text CONTAINS "사무직"
               OR lr.source_text CONTAINS "관리감독자"
               OR lc.source_text CONTAINS "교육시간"
               OR lc.source_text CONTAINS "비사무직"
               OR lc.source_text CONTAINS "사무직"
               OR lc.source_text CONTAINS "관리감독자"
            RETURN ann AS annex, lr AS logical_row, collect(lc)[0..30] AS logical_cells
            LIMIT $limit
            """,
            {"limit": limit},
        )
        result: list[dict] = []
        for row in rows:
            annex = row.get("annex") or {}
            logical_row = row.get("logical_row") or {}
            cells = row.get("logical_cells") or []
            cell_text = " ".join(str((cell or {}).get("source_text") or "") for cell in cells if isinstance(cell, dict))
            result.append(
                {
                    "evidence_kind": "annex_logical_time",
                    "law_name": annex.get("law_name"),
                    "article_no": "",
                    "annex_title": annex.get("annex_title"),
                    "resolved_annex_title": annex.get("annex_title"),
                    "source_text": " ".join(
                        str(part or "") for part in (annex.get("annex_title"), logical_row.get("source_text"), cell_text)
                    ),
                    "source_text_preview": _preview(" ".join(str(part or "") for part in (logical_row.get("source_text"), cell_text)), 500),
                    "logical_row": logical_row,
                    "logical_cells": cells,
                    "source_anchor": {
                        "label": "LogicalRow",
                        "id": logical_row.get("logical_row_id"),
                        "source_text": logical_row.get("source_text"),
                        "source_text_preview": _preview(logical_row.get("source_text") or cell_text, 500),
                    },
                }
        )
        return result

    def find_corporate_penalty_for_penalty_law(
        self,
        law_name: str | None,
        article_no: str | None,
        limit: int = 4,
    ) -> list[dict]:
        law_name = str(law_name or "")
        article_no = str(article_no or "")
        targets: list[tuple[str, str, str]] = []
        if "산업안전보건" in law_name and article_no in {"제167조", "제168조", "제169조", "제170조", "제171조", "제172조"}:
            targets.append(
                (
                    "산업안전보건법",
                    "제173조",
                    "산업안전보건법상 벌칙 조문과 양벌규정의 구조적 연결 후보. 사건의 행위자/법인 여부에 따라 적용 여부 검토 필요.",
                )
            )
        if "중대재해" in law_name and article_no == "제6조":
            targets.append(
                (
                    "중대재해처벌법",
                    "제7조",
                    "중대재해처벌법상 처벌 조문과 법인 처벌 조문의 구조적 연결 후보. 법인/기관 책임 여부에 따라 적용 여부 검토 필요.",
                )
            )
        if not targets:
            return []
        rows = []
        for law_keyword, target_article, review_reason in targets:
            found = self.find_rules_by_law_articles([(law_keyword, target_article)], limit)
            for rule in found:
                rows.append(
                    {
                        "evidence_kind": "rule",
                        "rule_id": rule.get("rule_id"),
                        "rule_type": rule.get("rule_type") or "PENALTY",
                        "rule_subtype": rule.get("rule_subtype") or "CORPORATE_PENALTY",
                        "law_name": rule.get("law_name"),
                        "article_no": rule.get("article_no"),
                        "annex_title": rule.get("annex_title"),
                        "source_text": rule.get("source_text") or rule.get("penalty_text"),
                        "source_text_preview": rule.get("source_text") or rule.get("penalty_text"),
                        "match_type": "CORPORATE_PENALTY_BY",
                        "relation_type": "CORPORATE_PENALTY_BY",
                        "candidate_status": "RULE_BASED_CANDIDATE",
                        "confidence": "medium",
                        "review_reason": review_reason,
                        "is_confirmed": False,
                    }
                )
        return rows[:limit]

    def find_list_sources(self, query: str, limit: int = 50) -> list[dict]:
        if "안전검사" in query or "기계" in query:
            return [
                {
                    "evidence_kind": "list_item",
                    "list_item_id": row.get("list_item_id"),
                    "item_text": row.get("item_text"),
                    "law_name": row.get("law_name"),
                    "article_no": row.get("article_no"),
                    "annex_title": row.get("annex_title"),
                    "source_text": row.get("source_context_text") or row.get("item_text"),
                    "source_anchor": {
                        "label": "SourceAnchor",
                        "id": row.get("anchor_id"),
                        "source_text": row.get("anchor_source_text"),
                    },
                }
                for row in self.get_inspection_list_evidence(min(limit, 50))
            ]
        return self.get_listitem_evidence(query, limit)

    def find_obligation_sources(self, query: str, limit: int = 50) -> list[dict]:
        rows = self.search_rules_by_keyword(query, limit)
        return [
            {
                "evidence_kind": "rule",
                "rule_id": row.get("rule_id"),
                "rule_type": row.get("rule_type"),
                "rule_subtype": row.get("rule_subtype"),
                "law_name": row.get("law_name"),
                "article_no": row.get("article_no"),
                "annex_title": row.get("annex_title"),
                "source_text": row.get("source_text"),
                "source_text_preview": row.get("source_text"),
            }
            for row in rows
        ]

    def find_exception_sources(self, query: str, limit: int = 50) -> list[dict]:
        rows = self.get_exception_evidence(limit)
        return [
            {
                "evidence_kind": "rule",
                "rule_id": row.get("rule_id"),
                "law_name": row.get("law_name"),
                "article_no": row.get("article_no"),
                "annex_title": row.get("annex_title"),
                "source_text": row.get("source_text") or row.get("condition_text") or row.get("exception_text"),
                "source_text_preview": row.get("source_text") or row.get("condition_text") or row.get("exception_text"),
            }
            for row in rows
        ]

    def find_penalty_sources(self, query: str, limit: int = 50) -> list[dict]:
        rows = self.get_penalty_evidence(limit)
        result = []
        for row in rows:
            rule = row.get("penalty_rule") or row.get("rule") or row
            result.append(
                {
                    "evidence_kind": "rule",
                    "rule_id": rule.get("rule_id"),
                    "rule_type": rule.get("rule_type"),
                    "rule_subtype": rule.get("rule_subtype"),
                    "law_name": rule.get("law_name"),
                    "article_no": rule.get("article_no"),
                    "annex_title": rule.get("annex_title"),
                    "source_text": rule.get("source_text") or rule.get("penalty_text"),
                    "source_text_preview": rule.get("source_text") or rule.get("penalty_text"),
                    "is_confirmed": True,
                }
            )
        return result

    def find_penalty_rules_for_violation(
        self,
        law_name: str | None,
        article_no: str | None,
        rule_id: str | None = None,
        limit: int = 6,
    ) -> list[dict]:
        law_name = str(law_name or "").strip()
        article_no = str(article_no or "").strip()
        article_digits = re.sub(r"\D+", "", article_no)
        article_refs = []
        if article_no:
            article_refs.append(article_no)
        if article_digits:
            article_refs.extend([f"제{article_digits}조", f"{article_digits}조"])
        article_refs = list(dict.fromkeys(article_refs))
        rows = self.run_read_query(
            """
            OPTIONAL MATCH (r:Rule {rule_id: $rule_id})-[direct_rel:RELATED_RULE]-(direct_p:Rule)
            WITH collect(DISTINCT CASE
                WHEN direct_p.rule_type = "PENALTY"
                  OR direct_p.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE", "PENALTY_IMPRISONMENT"]
                  OR direct_p.penalty_text IS NOT NULL
                THEN {
                    penalty_rule: direct_p,
                    match_type: "RELATED_RULE",
                    match_reason: "Rule graph relationship from obligation/detail rule to penalty rule"
                }
                ELSE null
            END) AS raw_direct_matches
            WITH [match IN raw_direct_matches WHERE match IS NOT NULL] AS direct_matches
            MATCH (p:Rule)
            WHERE p IS NOT NULL
              AND (p.rule_type = "PENALTY"
                   OR p.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE", "PENALTY_IMPRISONMENT"]
                   OR p.penalty_text IS NOT NULL)
              AND (
                    $law_name = ""
                    OR p.law_name = $law_name
                    OR ($law_name CONTAINS "산업안전보건" AND p.law_name CONTAINS "산업안전보건")
                    OR ($law_name CONTAINS "중대재해" AND p.law_name CONTAINS "중대재해")
                  )
              AND (
                    size($article_refs) = 0
                    OR any(article_ref IN $article_refs WHERE coalesce(p.source_text, "") CONTAINS article_ref)
                    OR any(article_ref IN $article_refs WHERE coalesce(p.penalty_text, "") CONTAINS article_ref)
                  )
            WITH direct_matches, collect(DISTINCT {
                penalty_rule: p,
                match_type: "ARTICLE_REFERENCE",
                match_reason: "Penalty text references the violation article"
            }) AS article_matches
            WITH direct_matches + article_matches AS matches
            UNWIND matches AS match
            WITH match
            WHERE match.penalty_rule IS NOT NULL
            RETURN DISTINCT match.penalty_rule AS penalty_rule,
                   match.match_type AS match_type,
                   match.match_reason AS match_reason
            LIMIT $limit
            """,
            {
                "law_name": law_name,
                "article_no": article_no,
                "article_refs": article_refs,
                "rule_id": str(rule_id or ""),
                "limit": limit,
            },
        )
        result = []
        for row in rows:
            rule = row.get("penalty_rule") or {}
            result.append(
                {
                    "evidence_kind": "rule",
                    "rule_id": rule.get("rule_id"),
                    "rule_type": rule.get("rule_type"),
                    "rule_subtype": rule.get("rule_subtype"),
                    "law_name": rule.get("law_name"),
                    "article_no": rule.get("article_no"),
                    "annex_title": rule.get("annex_title"),
                    "source_text": rule.get("source_text") or rule.get("penalty_text"),
                    "source_text_preview": rule.get("source_text") or rule.get("penalty_text"),
                    "match_type": row.get("match_type"),
                    "match_reason": row.get("match_reason"),
                    "is_confirmed": row.get("match_type") == "RELATED_RULE",
                }
            )
        return result

    def get_requirement_evidence(self, limit: int = 10) -> list[dict]:
        return self.run_read_query(
            """
            MATCH (r:Rule)-[:HAS_REQUIREMENT]->(req:Requirement)
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
            RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
                   r.law_name AS law_name, r.article_no AS article_no, r.annex_title AS annex_title,
                   r.source_text AS source_text, req AS requirement,
                   src AS source_node, labels(anchor) AS anchor_labels, anchor AS source_anchor
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def get_threshold_evidence(self, limit: int = 10) -> list[dict]:
        return self.run_read_query(
            """
            MATCH (r:Rule)-[:HAS_THRESHOLD]->(th:Threshold)
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
            RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
                   r.law_name AS law_name, r.article_no AS article_no, r.annex_title AS annex_title,
                   r.source_text AS source_text, th AS threshold,
                   src AS source_node, labels(anchor) AS anchor_labels, anchor AS source_anchor
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def get_exception_evidence(self, limit: int = 10) -> list[dict]:
        return self.run_read_query(
            """
            MATCH (r:Rule)-[:HAS_EXCEPTION]->(ex:Exception)
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
            RETURN r.rule_id AS rule_id, r.rule_type AS rule_type, r.rule_subtype AS rule_subtype,
                   r.law_name AS law_name, r.article_no AS article_no, r.annex_title AS annex_title,
                   r.source_text AS source_text, ex AS exception,
                   src AS source_node, labels(anchor) AS anchor_labels, anchor AS source_anchor
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def get_penalty_evidence(self, limit: int = 10) -> list[dict]:
        return self.run_read_query(
            """
            MATCH (r:Rule)
            WHERE r.rule_type = "PENALTY"
               OR r.rule_subtype IN ["PENALTY_FINE", "ADMINISTRATIVE_FINE"]
            OPTIONAL MATCH (r)-[rel:RELATED_RULE]->(related:Rule)
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
            RETURN r AS penalty_rule,
                   collect(DISTINCT {rel: rel.rel, rule: related})[0..10] AS related_rules,
                   collect(DISTINCT src)[0..5] AS source_nodes,
                   collect(DISTINCT {labels: labels(anchor), anchor: anchor})[0..5] AS source_anchors
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def get_listitem_evidence(self, keyword: str | None = None, limit: int = 20) -> list[dict]:
        keyword = keyword or ""
        terms = extract_search_terms(keyword)
        return self.run_read_query(
            """
            MATCH (li:ListItem)-[ir:ITEM_RESOLVES_TO]->(anchor)
            WHERE $keyword = ""
               OR any(term IN $terms WHERE
                    li.item_text CONTAINS term
                 OR li.source_context_text CONTAINS term
                 OR li.annex_title CONTAINS term)
            OPTIONAL MATCH (ann1:Annex)-[:HAS_LOGICAL_ROW]->(anchor)
            OPTIONAL MATCH (ann2:Annex)-[:HAS_LOGICAL_ROW]->(:LogicalRow)-[:HAS_LOGICAL_CELL]->(anchor)
            RETURN li.list_item_id AS list_item_id, li.list_item_type AS list_item_type,
                   li.item_text AS item_text, li.law_name AS law_name, li.article_no AS article_no,
                   li.annex_title AS annex_title, li.source_context_text AS source_context_text,
                   labels(anchor) AS anchor_label,
                   coalesce(anchor.paragraph_id, anchor.item_id, anchor.subitem_id, anchor.logical_row_id, anchor.logical_cell_id, anchor.note_id) AS anchor_id,
                   coalesce(anchor.source_text, anchor.text) AS anchor_source_text,
                   coalesce(ann1.annex_title, ann2.annex_title, li.annex_title) AS resolved_annex_title
            LIMIT $limit
            """,
            {"keyword": keyword, "terms": terms, "limit": limit},
        )

    def get_education_time_evidence(self, limit: int = 20) -> list[dict]:
        return self.run_read_query(
            """
            MATCH (r:Rule)-[:HAS_THRESHOLD]->(th:Threshold)
            WHERE r.rule_subtype CONTAINS "EDUCATION"
               OR r.source_text CONTAINS "교육"
               OR r.annex_title CONTAINS "교육"
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
            RETURN r AS rule, th AS threshold, src AS source_node,
                   labels(anchor) AS anchor_labels, anchor AS source_anchor
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def get_inspection_list_evidence(self, limit: int = 30) -> list[dict]:
        raw_limit = max(limit * 30, 500)
        rows = self.run_read_query(
            """
            MATCH (li:ListItem)-[:ITEM_RESOLVES_TO]->(anchor)
            WHERE li.list_item_type IN ["EQUIPMENT_ITEM", "INSPECTION_ITEM"]
               OR li.item_text CONTAINS "크레인"
               OR li.source_context_text CONTAINS "안전검사"
            OPTIONAL MATCH (ann1:Annex)-[:HAS_LOGICAL_ROW]->(anchor)
            OPTIONAL MATCH (ann2:Annex)-[:HAS_LOGICAL_ROW]->(:LogicalRow)-[:HAS_LOGICAL_CELL]->(anchor)
            RETURN li AS list_item, labels(anchor) AS anchor_labels, anchor AS source_anchor,
                   coalesce(ann1, ann2) AS annex
            LIMIT $limit
            """,
            {"limit": raw_limit},
        )
        equipment_terms = ("크레인", "리프트", "곤돌라", "프레스", "전단기", "안전검사대상기계")
        penalty_terms = ("검사기관", "신청", "서식", "표시", "방법", "절차", "확인", "평가")
        for row in rows:
            li = row.get("list_item") or {}
            text = f"{li.get('item_text') or ''} {li.get('source_context_text') or ''}"
            score = 0
            if li.get("list_item_type") == "EQUIPMENT_ITEM":
                score += 40
            if li.get("list_item_type") == "INSPECTION_ITEM":
                score += 10
            score += sum(15 for term in equipment_terms if term in text)
            score -= sum(8 for term in penalty_terms if term in text)
            row["score"] = score
            row["rank_reason"] = "equipment/list terms boosted; procedure/institution terms penalized"
        rows.sort(key=lambda r: r.get("score", 0), reverse=True)
        return rows[:limit]

    def get_source_context_for_rule(self, rule_id: str) -> dict:
        rows = self.run_read_query(
            """
            MATCH (r:Rule {rule_id: $rule_id})
            OPTIONAL MATCH (r)-[:EXTRACTED_FROM]->(src:SourceNode)-[:RESOLVES_TO]->(anchor)
            RETURN r AS rule, src AS source_node, labels(anchor) AS anchor_labels, anchor AS source_anchor
            LIMIT 5
            """,
            {"rule_id": rule_id},
        )
        return {"rule_id": rule_id, "contexts": rows}

    def get_annex_context_for_listitem(self, list_item_id: str) -> dict:
        rows = self.run_read_query(
            """
            MATCH (li:ListItem {list_item_id: $list_item_id})-[:ITEM_RESOLVES_TO]->(anchor)
            OPTIONAL MATCH (ann1:Annex)-[:HAS_LOGICAL_ROW]->(anchor)
            OPTIONAL MATCH (ann2:Annex)-[:HAS_LOGICAL_ROW]->(lr:LogicalRow)-[:HAS_LOGICAL_CELL]->(anchor)
            OPTIONAL MATCH (ann3:Annex)-[:HAS_NOTE]->(anchor)
            RETURN li AS list_item, labels(anchor) AS anchor_labels, anchor AS source_anchor,
                   coalesce(ann1, ann2, ann3) AS annex, lr AS logical_row
            LIMIT 10
            """,
            {"list_item_id": list_item_id},
        )
        return {"list_item_id": list_item_id, "contexts": rows}
