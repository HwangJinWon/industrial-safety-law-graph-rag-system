from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated_v6_case_scenario_eval"
RAW_CASES = ROOT / "raw_cases"

TARGET_LAWS = [
    "산업안전보건법",
    "구 산업안전보건법",
    "산업안전보건법 시행령",
    "산업안전보건법 시행규칙",
    "산업안전보건기준에 관한 규칙",
    "중대재해 처벌 등에 관한 법률",
    "중대재해처벌법",
    "중대재해처벌법 시행령",
    "형법",
    "건설기술관리법",
    "건설산업기본법",
    "민법",
]

LAW_GROUPS = {
    "산업안전보건법": "osh_act",
    "구 산업안전보건법": "osh_act",
    "산업안전보건법 시행령": "osh_enforcement_decree",
    "산업안전보건법 시행규칙": "osh_enforcement_rule",
    "산업안전보건기준에 관한 규칙": "osh_standards_rule",
    "중대재해처벌법": "serious_accidents_act",
    "중대재해 처벌 등에 관한 법률": "serious_accidents_act",
    "중대재해처벌법 시행령": "serious_accidents_enforcement_decree",
}


def ensure(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: Any) -> None:
    ensure(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def clean_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", str(text or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def case_text(data: dict[str, Any]) -> tuple[str, dict[str, str]]:
    svc = data.get("PrecService") if isinstance(data, dict) else {}
    if not isinstance(svc, dict):
        return "", {}
    parts = []
    for key in ["사건명", "판시사항", "판결요지", "참조조문", "판례내용"]:
        if svc.get(key):
            parts.append(f"{key}: {clean_html(svc.get(key))}")
    return "\n".join(parts), {k: clean_html(v) for k, v in svc.items() if isinstance(v, str)}


def normalize_law_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    if "중대재해" in name and "처벌" in name and "시행령" not in name:
        return "중대재해처벌법"
    if "중대재해" in name and "처벌" in name and "시행령" in name:
        return "중대재해처벌법 시행령"
    if name == "구 산업안전보건법":
        return "산업안전보건법"
    return name


def normalize_ref(law_name: str, article: str, para: str = "", item: str = "", subitem: str = "") -> str:
    bits = [normalize_law_name(law_name), article, para, item, subitem]
    return " ".join([b for b in bits if b]).strip()


def extract_law_refs_from_text(text: str) -> list[dict[str, str]]:
    law_alt = "|".join(map(re.escape, sorted(TARGET_LAWS, key=len, reverse=True)))
    pattern = re.compile(
        rf"(?P<law>{law_alt})\s*(?P<article>제\s*\d+(?:조의\d+)?조?)\s*"
        rf"(?P<para>제\s*\d+항)?\s*(?P<item>제\s*\d+호)?\s*(?P<subitem>[가-하]목)?"
    )
    rows = []
    for m in pattern.finditer(text):
        law = re.sub(r"\s+", " ", m.group("law")).strip()
        article = re.sub(r"\s+", "", m.group("article")).replace("조조", "조")
        para = re.sub(r"\s+", "", m.group("para") or "")
        item = re.sub(r"\s+", "", m.group("item") or "")
        subitem = m.group("subitem") or ""
        article = re.sub(r"제(\d+)", r"제\1", article)
        context = text[max(0, m.start() - 120): m.end() + 120]
        old = "구 " in law or is_old_article_candidate(law, article)
        norm_law = normalize_law_name(law)
        rows.append({
            "raw_law_ref": m.group(0),
            "normalized_law_name": norm_law,
            "article_no": article,
            "paragraph_no": para,
            "item_no": item,
            "subitem_no": subitem,
            "normalized_ref": normalize_ref(norm_law, article, para, item, subitem),
            "law_ref_type": "old_law" if old else "current_direct" if norm_law in LAW_GROUPS else "non_target",
            "is_current_law_candidate": str(not old and norm_law in LAW_GROUPS),
            "is_old_law_candidate": str(old),
            "is_target_law": str(norm_law in LAW_GROUPS),
            "is_non_target_law": str(norm_law not in LAW_GROUPS),
            "extraction_context": context,
            "confidence": "medium",
            "review_reason": "구법 후보로 태깅. 현행법 자동 변환 안 함." if old else "",
        })
    return rows


def is_old_article_candidate(law: str, article: str) -> bool:
    if "산업안전보건법" not in law:
        return False
    old_nums = {"제18조", "제23조", "제24조", "제29조", "제33조", "제66조", "제66조의2", "제67조", "제68조", "제70조", "제71조"}
    return article in old_nums


def extract_dates(text: str, svc: dict[str, str]) -> dict[str, str]:
    judgment = re.sub(r"\D", "", svc.get("선고일자", ""))[:8]
    dates = re.findall(r"(19\d{2}|20\d{2})[.\-년]\s*(\d{1,2})[.\-월]\s*(\d{1,2})", text)
    normalized = []
    for y, m, d in dates:
        try:
            normalized.append(datetime(int(y), int(m), int(d)).strftime("%Y%m%d"))
        except ValueError:
            pass
    selected = normalized[0] if normalized else judgment
    basis = "case_text_first_date" if normalized else "judgment_date" if judgment else ""
    return {
        "accident_date": normalized[0] if normalized else "",
        "violation_date": "",
        "judgment_date": judgment,
        "selected_date_for_law_version": selected,
        "date_basis": basis,
    }


def keyword_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def extract_facts(text: str, svc: dict[str, str]) -> dict[str, Any]:
    dates = extract_dates(text, svc)
    accidents = {
        "추락": ["추락", "떨어"],
        "붕괴": ["붕괴"],
        "끼임/협착": ["끼임", "협착", "압착"],
        "감전": ["감전"],
        "질식": ["질식", "산소결핍"],
        "화재": ["화재"],
        "폭발": ["폭발"],
        "낙하/비래": ["낙하", "비래", "떨어진", "덮쳐"],
        "충돌": ["충돌"],
        "전도": ["전도"],
        "매몰": ["매몰"],
        "중독": ["중독"],
    }
    accident_type = ", ".join([k for k, vals in accidents.items() if keyword_any(text, vals)]) or "unknown"
    result = "사망" if "사망" in text or "치사" in text else "상해" if "상해" in text or "치상" in text else "unknown"
    if "중대산업재해" in text or "중대재해" in text:
        result = result if result != "unknown" else "중대산업재해"
    work_terms = [k for k in ["크레인", "비계", "굴착", "전기", "지하", "선박", "보수", "하역", "건설", "제조", "공사", "중량물"] if k in text]
    place_terms = [k for k in ["선박", "화물창", "지하", "터널", "공사현장", "공장", "작업장", "건설현장", "야외작업장"] if k in text]
    victim_terms = [k for k in ["근로자", "관계수급인", "수급인 근로자", "종사자", "피해자"] if k in text]
    parties = [k for k in ["사업주", "법인", "대표이사", "경영책임자", "현장소장", "안전보건관리책임자", "관리감독자", "도급인", "수급인", "관계수급인"] if k in text]
    risks = [k for k in ["안전난간", "안전대", "개구부", "덮개", "작업계획서", "방호조치", "관리감독", "라이프라인", "보호구", "안전보건관리체계"] if k in text]
    issues = [k for k in ["안전조치", "보건조치", "도급", "처벌", "양벌", "적용범위", "상시 근로자", "중대재해처벌법", "상상적 경합"] if k in text]
    return {
        **dates,
        "accident_type": accident_type,
        "result": result,
        "work_type": ", ".join(work_terms),
        "place": ", ".join(place_terms),
        "victim_type": ", ".join(victim_terms),
        "responsible_parties": json.dumps(parties, ensure_ascii=False),
        "employer_or_business_owner": "사업주" if "사업주" in text else "",
        "site_manager": "현장소장" if "현장소장" in text else "",
        "contractor_relation": str(keyword_any(text, ["도급", "수급", "하청", "관계수급인"])),
        "contractor_type": "도급/수급" if keyword_any(text, ["도급", "수급", "하청", "관계수급인"]) else "",
        "serious_accident_issue": str(keyword_any(text, ["중대재해", "중대산업재해", "경영책임자"])),
        "health_issue": str(keyword_any(text, ["보건", "질식", "산소결핍", "유해", "건강장해", "중독"])),
        "safety_issue": str(keyword_any(text, ["안전조치", "추락", "붕괴", "끼임", "낙하", "감전", "위험"])),
        "scope_issue": str(keyword_any(text, ["적용범위", "상시 근로자", "50명 미만", "사업장", "시행일", "유예"])),
        "unsafe_condition": ", ".join(risks),
        "omitted_action": "필요한 안전보건조치 미이행" if keyword_any(text, ["조치를 하지", "조치하지", "게을리"]) else "",
        "risk_factors": json.dumps(risks, ensure_ascii=False),
        "legal_issue_summary": json.dumps(issues, ensure_ascii=False),
        "extracted_fact_text": text[:1500],
        "fact_confidence": "medium" if accident_type != "unknown" or result != "unknown" else "low",
        "review_required": str(accident_type == "unknown" or not dates["selected_date_for_law_version"]),
        "review_reason": "" if accident_type != "unknown" else "사고유형 추출 불확실",
    }


def build_inventory() -> list[dict[str, Any]]:
    rows = []
    files = sorted(RAW_CASES.glob("*.json"), key=lambda p: p.name)
    for idx, path in enumerate(files, 1):
        try:
            data = read_json(path)
            text, svc = case_text(data)
            refs = extract_law_refs_from_text(text)
            rows.append({
                "case_id": str(idx),
                "source_case_id": path.stem,
                "case_name": svc.get("사건명", path.stem),
                "case_file_path": str(path),
                "available_files": json.dumps([str(path)], ensure_ascii=False),
                "file_type": "json",
                "text_length": len(text),
                "has_case_text": str(bool(text)),
                "has_facts": str(bool(svc.get("판례내용") or svc.get("판결요지") or svc.get("판시사항"))),
                "has_law_refs": str(bool(refs)),
                "has_judgment_date": str(bool(svc.get("선고일자"))),
                "source_dataset": "raw_cases",
                "inventory_status": "OK" if text else "NEEDS_REVIEW",
                "review_reason": "" if text else "본문 추출 실패",
            })
        except Exception as exc:
            rows.append({
                "case_id": str(idx),
                "source_case_id": path.stem,
                "case_name": path.stem,
                "case_file_path": str(path),
                "available_files": json.dumps([str(path)], ensure_ascii=False),
                "file_type": "json",
                "text_length": 0,
                "has_case_text": "False",
                "has_facts": "False",
                "has_law_refs": "False",
                "has_judgment_date": "False",
                "source_dataset": "raw_cases",
                "inventory_status": "PARSE_FAILED",
                "review_reason": str(exc),
            })
    fields = ["case_id", "source_case_id", "case_name", "case_file_path", "available_files", "file_type", "text_length", "has_case_text", "has_facts", "has_law_refs", "has_judgment_date", "source_dataset", "inventory_status", "review_reason"]
    write_csv(OUT / "inventory" / "case_inventory_69.csv", rows, fields)
    write_json(OUT / "inventory" / "case_inventory_summary.json", {
        "total_case_count": 69,
        "found_case_count": len(rows),
        "missing_or_duplicate_case_count": max(0, 69 - len(rows)),
        "file_type_distribution": dict(Counter(r["file_type"] for r in rows)),
        "cases_with_text": sum(r["has_case_text"] == "True" for r in rows),
        "cases_without_text": sum(r["has_case_text"] != "True" for r in rows),
        "cases_needing_manual_path_review": [r for r in rows if r["inventory_status"] != "OK"],
    })
    return rows


def load_case_by_inventory(row: dict[str, str]) -> tuple[str, dict[str, str]]:
    data = read_json(Path(row["case_file_path"]))
    return case_text(data)


def extract_facts_and_refs() -> tuple[list[dict], list[dict]]:
    inventory = read_csv(OUT / "inventory" / "case_inventory_69.csv") or build_inventory()
    fact_rows = []
    ref_rows = []
    for inv in inventory:
        text, svc = load_case_by_inventory(inv)
        facts = extract_facts(text, svc)
        fact_rows.append({"case_id": inv["case_id"], "case_name": inv["case_name"], **facts})
        for ref in extract_law_refs_from_text(text):
            ref_rows.append({
                "case_id": inv["case_id"],
                "case_name": inv["case_name"],
                "source_file": inv["case_file_path"],
                "source_section": "PrecService",
                **ref,
            })
    fact_fields = ["case_id", "case_name", "accident_date", "violation_date", "judgment_date", "selected_date_for_law_version", "date_basis", "accident_type", "result", "work_type", "place", "victim_type", "responsible_parties", "employer_or_business_owner", "site_manager", "contractor_relation", "contractor_type", "serious_accident_issue", "health_issue", "safety_issue", "scope_issue", "unsafe_condition", "omitted_action", "risk_factors", "legal_issue_summary", "extracted_fact_text", "fact_confidence", "review_required", "review_reason"]
    ref_fields = ["case_id", "case_name", "source_file", "source_section", "raw_law_ref", "normalized_law_name", "article_no", "paragraph_no", "item_no", "subitem_no", "normalized_ref", "law_ref_type", "is_current_law_candidate", "is_old_law_candidate", "is_target_law", "is_non_target_law", "extraction_context", "confidence", "review_reason"]
    write_csv(OUT / "extraction" / "case_facts_69.csv", fact_rows, fact_fields)
    write_csv(OUT / "extraction" / "case_law_refs_69.csv", ref_rows, ref_fields)
    write_csv(OUT / "extraction" / "case_extraction_review.csv", [r for r in fact_rows if r["review_required"] == "True"], fact_fields)
    write_json(OUT / "extraction" / "case_extraction_summary.json", {
        "case_count": len(fact_rows),
        "law_ref_count": len(ref_rows),
        "review_required_count": sum(r["review_required"] == "True" for r in fact_rows),
        "accident_type_counts": dict(Counter(r["accident_type"] for r in fact_rows)),
        "result_counts": dict(Counter(r["result"] for r in fact_rows)),
    })
    return fact_rows, ref_rows


def classify_issues() -> list[dict]:
    facts = read_csv(OUT / "extraction" / "case_facts_69.csv")
    rows = []
    for f in facts:
        flags = {
            "issue_safety_obligation": f["safety_issue"],
            "issue_health_obligation": f["health_issue"],
            "issue_contractor_obligation": f["contractor_relation"],
            "issue_serious_accident_obligation": f["serious_accident_issue"],
            "issue_detail_rule": str(bool(f["unsafe_condition"])),
            "issue_penalty": str("처벌" in f["legal_issue_summary"] or f["result"] in {"사망", "상해"}),
            "issue_corporate_penalty": str("양벌" in f["legal_issue_summary"] or "법인" in f["responsible_parties"]),
            "issue_definition_scope": f["scope_issue"],
            "issue_administrative_fine": "False",
            "issue_education": str("교육" in f["extracted_fact_text"]),
            "issue_appointment": str("선임" in f["extracted_fact_text"]),
            "issue_reporting_submission": str(any(k in f["extracted_fact_text"] for k in ["보고", "제출", "신고"])),
            "issue_record_retention": str("보존" in f["extracted_fact_text"] or "기록" in f["extracted_fact_text"]),
        }
        primary = "unknown"
        for key in ["issue_serious_accident_obligation", "issue_contractor_obligation", "issue_safety_obligation", "issue_health_obligation", "issue_definition_scope"]:
            if flags[key] == "True":
                primary = key.replace("issue_", "")
                break
        secondary = [k.replace("issue_", "") for k, v in flags.items() if v == "True" and k.replace("issue_", "") != primary]
        rows.append({"case_id": f["case_id"], "case_name": f["case_name"], **flags, "primary_issue_type": primary, "secondary_issue_types": json.dumps(secondary, ensure_ascii=False), "issue_confidence": "medium", "review_reason": ""})
    fields = ["case_id", "case_name", "issue_safety_obligation", "issue_health_obligation", "issue_contractor_obligation", "issue_serious_accident_obligation", "issue_detail_rule", "issue_penalty", "issue_corporate_penalty", "issue_definition_scope", "issue_administrative_fine", "issue_education", "issue_appointment", "issue_reporting_submission", "issue_record_retention", "primary_issue_type", "secondary_issue_types", "issue_confidence", "review_reason"]
    write_csv(OUT / "extraction" / "case_legal_issue_labels.csv", rows, fields)
    return rows


def date_to_int(date: str) -> int:
    return int(re.sub(r"\D", "", date)[:8] or 0)


def link_versions() -> list[dict]:
    facts = read_csv(OUT / "extraction" / "case_facts_69.csv")
    timeline = read_csv(ROOT / "generated_v5_current_mapped" / "parsed" / "law_version_timeline.csv")
    by_group = defaultdict(list)
    for row in timeline:
        by_group[row["law_group"]].append(row)
    for group in by_group:
        by_group[group].sort(key=lambda r: date_to_int(r["effective_date"]))
    rows = []
    for f in facts:
        d = date_to_int(f["selected_date_for_law_version"])
        for group, versions in by_group.items():
            selected = None
            for idx, ver in enumerate(versions):
                eff = date_to_int(ver["effective_date"])
                nxt = date_to_int(versions[idx + 1]["effective_date"]) if idx + 1 < len(versions) else 99999999
                if eff <= d < nxt:
                    selected = (ver, versions[idx + 1] if idx + 1 < len(versions) else None)
                    break
            if group.startswith("serious_accidents") and d and d < 20220127:
                rows.append({"case_id": f["case_id"], "case_name": f["case_name"], "selected_date_for_law_version": f["selected_date_for_law_version"], "date_basis": f["date_basis"], "law_group": group, "law_name": "", "applicable_mst": "", "applicable_effective_date": "", "next_effective_date": "", "applicable_promulgation_no": "", "link_method": "NOT_APPLICABLE", "link_confidence": "high", "review_reason": "중대재해처벌법 시행 전"})
            elif selected:
                ver, nxt = selected
                rows.append({"case_id": f["case_id"], "case_name": f["case_name"], "selected_date_for_law_version": f["selected_date_for_law_version"], "date_basis": f["date_basis"], "law_group": group, "law_name": ver.get("law_name", ""), "applicable_mst": ver.get("mst", ""), "applicable_effective_date": ver.get("effective_date", ""), "next_effective_date": nxt.get("effective_date", "") if nxt else "", "applicable_promulgation_no": ver.get("promulgation_no", ""), "link_method": "effective_date_range", "link_confidence": "medium" if f["date_basis"] else "low", "review_reason": ""})
            else:
                rows.append({"case_id": f["case_id"], "case_name": f["case_name"], "selected_date_for_law_version": f["selected_date_for_law_version"], "date_basis": f["date_basis"], "law_group": group, "law_name": "", "applicable_mst": "", "applicable_effective_date": "", "next_effective_date": "", "applicable_promulgation_no": "", "link_method": "NO_VERSION_FOUND", "link_confidence": "low", "review_reason": "해당 날짜 version link 실패"})
    fields = ["case_id", "case_name", "selected_date_for_law_version", "date_basis", "law_group", "law_name", "applicable_mst", "applicable_effective_date", "next_effective_date", "applicable_promulgation_no", "link_method", "link_confidence", "review_reason"]
    write_csv(OUT / "mapping" / "case_version_links.csv", rows, fields)
    return rows


def build_mapping_candidates() -> list[dict]:
    refs = read_csv(OUT / "extraction" / "case_law_refs_69.csv")
    v5 = read_csv(ROOT / "generated_v5_current_mapped" / "mapping" / "old_current_article_mapping_candidates.csv")
    focus = read_csv(ROOT / "generated_v5_current_mapped" / "revision_analysis" / "known_transition_focus_review.csv")
    v5_by_old = defaultdict(list)
    for row in v5:
        v5_by_old[row["old_law_ref"]].append(row)
    focus_by_old = defaultdict(list)
    for row in focus:
        focus_by_old[row["old_ref"]].append(row)
    rows = []
    for ref in refs:
        if ref["is_old_law_candidate"] != "True" or ref["is_target_law"] != "True":
            continue
        candidates = v5_by_old.get(ref["normalized_ref"], [])
        if not candidates:
            candidates = [{
                "current_candidate_ref": f.get("current_candidate_ref", ""),
                "current_text": f.get("current_text", ""),
                "mapping_basis": "known_transition_focus",
                "title_similarity": f.get("title_similarity", ""),
                "text_similarity": f.get("text_similarity", ""),
                "role_similarity": f.get("role_similarity", ""),
                "combined_score": f.get("text_similarity", ""),
                "mapping_grade": f.get("preliminary_grade", "B"),
                "current_law_group": "osh_act",
                "current_mst": "",
                "current_effective_date": f.get("current_version", ""),
            } for f in focus_by_old.get(ref["normalized_ref"], [])]
        if not candidates:
            candidates = [{"current_candidate_ref": "", "mapping_grade": "D", "mapping_basis": "no_mapping_found"}]
        for cand in candidates:
            grade = cand.get("mapping_grade") or ("A" if str(cand.get("use_for_eval_candidate", "")).lower() == "true" else "B")
            rows.append({
                "case_id": ref["case_id"],
                "case_name": ref["case_name"],
                "old_law_ref": ref["normalized_ref"],
                "old_law_group": LAW_GROUPS.get(ref["normalized_law_name"], ""),
                "old_mst": "",
                "old_effective_date": "",
                "old_article_no": ref["article_no"],
                "old_paragraph_no": ref["paragraph_no"],
                "old_item_no": ref["item_no"],
                "old_text": "",
                "current_law_group": cand.get("current_law_group", ""),
                "current_mst": cand.get("current_mst", ""),
                "current_effective_date": cand.get("current_effective_date", ""),
                "current_candidate_ref": cand.get("current_candidate_ref", ""),
                "current_article_no": cand.get("current_article_no", ""),
                "current_paragraph_no": cand.get("current_paragraph_no", ""),
                "current_item_no": cand.get("current_item_no", ""),
                "current_text": cand.get("current_text", ""),
                "mapping_basis": cand.get("mapping_basis", "v5_existing_mapping"),
                "old_ref_found_in_version": "",
                "current_ref_exists": str(bool(cand.get("current_candidate_ref"))),
                "old_and_new_pair_found": cand.get("old_and_new_pair_found", ""),
                "title_similarity": cand.get("title_similarity", ""),
                "text_similarity": cand.get("text_similarity", ""),
                "role_similarity": cand.get("role_similarity", ""),
                "issue_similarity": "",
                "structure_similarity": cand.get("structure_similarity", ""),
                "combined_score": cand.get("combined_score", ""),
                "mapping_grade": grade,
                "use_for_eval_candidate": str(grade == "A"),
                "review_required": str(grade != "A"),
                "review_reason": "A만 ready GT 후보. B/C/D는 review-only." if grade != "A" else "A등급 mapping 후보",
            })
    fields = ["case_id", "case_name", "old_law_ref", "old_law_group", "old_mst", "old_effective_date", "old_article_no", "old_paragraph_no", "old_item_no", "old_text", "current_law_group", "current_mst", "current_effective_date", "current_candidate_ref", "current_article_no", "current_paragraph_no", "current_item_no", "current_text", "mapping_basis", "old_ref_found_in_version", "current_ref_exists", "old_and_new_pair_found", "title_similarity", "text_similarity", "role_similarity", "issue_similarity", "structure_similarity", "combined_score", "mapping_grade", "use_for_eval_candidate", "review_required", "review_reason"]
    write_csv(OUT / "mapping" / "case_old_current_mapping_candidates.csv", rows, fields)
    return rows


def classify_ref_slot(ref: str) -> str:
    if "중대재해처벌법 제4조" in ref or "중대재해처벌법 제5조" in ref:
        return "serious_accident_obligation"
    if "산업안전보건법 제39조" in ref:
        return "health_obligation"
    if any(x in ref for x in ["산업안전보건법 제63조", "산업안전보건법 제64조"]):
        return "contractor_obligation"
    if any(x in ref for x in ["산업안전보건법 제38조", "산업안전보건법 제34조"]):
        return "primary_obligation"
    if any(x in ref for x in ["산업안전보건법 제167조", "산업안전보건법 제168조", "중대재해처벌법 제6조"]):
        return "penalty"
    if any(x in ref for x in ["산업안전보건법 제173조", "중대재해처벌법 제7조"]):
        return "corporate_penalty"
    if any(x in ref for x in ["제1조", "제2조", "제3조"]):
        return "definition_or_scope"
    if "규칙" in ref or "시행령" in ref or "시행규칙" in ref:
        return "detail_rule"
    return "procedure_or_management"


def build_expected_bundles() -> list[dict]:
    refs = read_csv(OUT / "extraction" / "case_law_refs_69.csv")
    mappings = read_csv(OUT / "mapping" / "case_old_current_mapping_candidates.csv")
    by_case = defaultdict(lambda: defaultdict(list))
    candidate_by_case = defaultdict(list)
    for ref in refs:
        if ref["law_ref_type"] == "current_direct" and ref["is_target_law"] == "True":
            by_case[ref["case_id"]][classify_ref_slot(ref["normalized_ref"])].append(ref["normalized_ref"])
    for m in mappings:
        cur = m.get("current_candidate_ref", "")
        if not cur:
            continue
        if m.get("mapping_grade") == "A":
            by_case[m["case_id"]][classify_ref_slot(cur)].append(cur)
        elif m.get("mapping_grade") == "B":
            candidate_by_case[m["case_id"]].append(cur)
    facts = {r["case_id"]: r for r in read_csv(OUT / "extraction" / "case_facts_69.csv")}
    rows = []
    for case_id, f in facts.items():
        bundle = {k: sorted(set(by_case[case_id].get(k, []))) for k in ["primary_obligation", "health_obligation", "contractor_obligation", "serious_accident_obligation", "detail_rule", "penalty", "corporate_penalty", "definition_or_scope", "administrative_fine", "procedure_or_management"]}
        ready_refs = sorted({ref for vals in bundle.values() for ref in vals})
        status = "READY_A" if ready_refs else "REVIEW_B" if candidate_by_case[case_id] else "INSUFFICIENT"
        rows.append({
            "case_id": case_id,
            "case_name": f["case_name"],
            "bundle_status": status,
            "expected_legal_bundle_json": json.dumps(bundle, ensure_ascii=False),
            "ground_truth_laws": json.dumps(ready_refs, ensure_ascii=False),
            "expected_law_candidates": json.dumps(sorted(set(candidate_by_case[case_id])), ensure_ascii=False),
            "review_reason": "A/current direct만 GT 포함. B는 candidate/review." if status != "INSUFFICIENT" else "GT로 쓸 현행/A mapping 없음",
        })
    fields = ["case_id", "case_name", "bundle_status", "expected_legal_bundle_json", "ground_truth_laws", "expected_law_candidates", "review_reason"]
    write_csv(OUT / "mapping" / "case_expected_legal_bundle_candidates.csv", rows, fields)
    write_csv(OUT / "mapping" / "case_expected_legal_bundle_review.csv", [r for r in rows if r["bundle_status"] != "READY_A"], fields)
    write_json(OUT / "mapping" / "case_mapping_summary.json", {
        "mapping_grade_counts": dict(Counter(r["mapping_grade"] for r in read_csv(OUT / "mapping" / "case_old_current_mapping_candidates.csv"))),
        "bundle_status_counts": dict(Counter(r["bundle_status"] for r in rows)),
    })
    return rows


def parse_json_list(value: str) -> list:
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def build_prompt(f: dict[str, str]) -> str:
    return f"""다음 산업재해/중대재해 판례 상황에 대해 현행 산업안전보건법 및 중대재해처벌법 기준으로 적용 가능한 법령 조문을 판단하세요.

[판례 상황]
- 사고일 또는 기준일: {f.get('selected_date_for_law_version', '')}
- 사고 유형: {f.get('accident_type', '')}
- 결과: {f.get('result', '')}
- 작업 내용: {f.get('work_type', '')}
- 장소: {f.get('place', '')}
- 피해자 유형: {f.get('victim_type', '')}
- 책임 주체: {', '.join(parse_json_list(f.get('responsible_parties', '[]')))}
- 위반 또는 미조치 내용: {f.get('omitted_action', '')} {f.get('unsafe_condition', '')}
- 도급 관계: {f.get('contractor_relation', '')}
- 보건 쟁점: {f.get('health_issue', '')}
- 중대재해처벌법 쟁점: {f.get('serious_accident_issue', '')}

[요구 출력]
1. 적용 가능한 의무 조문
2. 필요한 세부 안전보건 기준
3. 처벌 조문
4. 양벌규정 또는 법인 처벌
5. 적용범위/정의 조문이 필요한 경우 그 근거
6. 구법 조문이 판례에 등장한 경우 현행법 대응 후보와 불확실성

중요:
- 모르는 조문은 단정하지 말 것
- 후보와 확정 근거를 구분할 것
- evidence에 없는 조문을 만들지 말 것
"""


def build_dataset() -> list[dict]:
    facts = {r["case_id"]: r for r in read_csv(OUT / "extraction" / "case_facts_69.csv")}
    bundles = read_csv(OUT / "mapping" / "case_expected_legal_bundle_candidates.csv")
    candidates = []
    ready = []
    review_rows = []
    preview_rows = []
    for b in bundles:
        f = facts.get(b["case_id"], {})
        bundle = json.loads(b["expected_legal_bundle_json"])
        gt = parse_json_list(b["ground_truth_laws"])
        item = {
            "id": b["case_id"],
            "source_case_id": b["case_id"],
            "case_name": b["case_name"],
            "input_type": "case_scenario",
            "dataset_status": b["bundle_status"],
            "case_facts": {
                k: f.get(k, "") for k in ["accident_date", "selected_date_for_law_version", "accident_type", "result", "work_type", "place", "victim_type", "responsible_parties", "unsafe_condition", "omitted_action", "contractor_relation", "serious_accident_issue", "health_issue", "safety_issue", "scope_issue"]
            },
            "original_law_refs": [],
            "mapped_current_law_refs": gt,
            "ground_truth_laws": gt,
            "expected_legal_bundle": bundle,
            "expected_law_candidates": parse_json_list(b["expected_law_candidates"]),
            "case_scenario_prompt": build_prompt(f),
            "question": build_prompt(f),
            "rewritten_question": build_prompt(f),
            "review_reason": b["review_reason"],
        }
        candidates.append(item)
        if b["bundle_status"] == "READY_A":
            ready.append(item)
        review_rows.append({"case_id": b["case_id"], "case_name": b["case_name"], "dataset_status": b["bundle_status"], "ground_truth_count": len(gt), "candidate_count": len(item["expected_law_candidates"]), "review_reason": b["review_reason"]})
        preview_rows.append({"case_id": b["case_id"], "case_name": b["case_name"], "dataset_status": b["bundle_status"], "case_scenario_prompt": item["case_scenario_prompt"][:2000]})
    write_json(OUT / "dataset" / "case_scenario_eval_candidates.json", candidates)
    write_json(OUT / "dataset" / "case_scenario_eval_ready.json", ready)
    write_csv(OUT / "dataset" / "case_scenario_eval_review.csv", review_rows, ["case_id", "case_name", "dataset_status", "ground_truth_count", "candidate_count", "review_reason"])
    write_csv(OUT / "dataset" / "case_scenario_prompt_preview.csv", preview_rows, ["case_id", "case_name", "dataset_status", "case_scenario_prompt"])
    write_json(OUT / "dataset" / "case_scenario_dataset_summary.json", {"candidate_count": len(candidates), "ready_count": len(ready), "status_counts": dict(Counter(i["dataset_status"] for i in candidates))})
    return ready


def run_all_build_steps() -> None:
    build_inventory()
    extract_facts_and_refs()
    classify_issues()
    link_versions()
    build_mapping_candidates()
    build_expected_bundles()
    build_dataset()


if __name__ == "__main__":
    run_all_build_steps()
