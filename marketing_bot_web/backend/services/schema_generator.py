"""
Schema.org JSON-LD Generator (MedicalBusiness + FAQPage)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Google Rich Results 가이드 기준:
- MedicalBusiness: name(필수), address, telephone, url, openingHours, medicalSpecialty
- FAQPage: mainEntity[].name + acceptedAnswer.text (필수)

본 모듈은 generate만 담당. 사이트 게시는 운영자 수동.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────
# MedicalBusiness
# ──────────────────────────────────────────────────────────────────────


def generate_medical_business_schema(profile: Dict[str, Any]) -> Dict[str, Any]:
    """business_profile.json::business 구조 → schema.org JSON-LD.

    Profile shape (CLAUDE.md 정의):
      {
        "business": {"name": "...", "industry": "한의원", "region": "청주",
                      "address": "청주시 흥덕구", "phone": "", "website": "", ...},
        "categories": {"main": [...]},
        ...
      }
    """
    business = profile.get("business", profile)  # top-level dict 허용

    name = business.get("name") or "한의원"
    region = business.get("region") or ""
    address_locality = business.get("address") or region
    phone = business.get("phone") or None
    website = business.get("website") or None
    industry = business.get("industry") or "한의원"

    # MedicalSpecialty 매핑 (한의원 → TraditionalChineseMedicine 가장 근접)
    specialty = "TraditionalChineseMedicine" if "한의" in industry else "GeneralPractice"

    main_categories = profile.get("categories", {}).get("main", [])

    schema: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "MedicalBusiness",
        "name": name,
        "medicalSpecialty": specialty,
    }
    if region or address_locality:
        addr: Dict[str, Any] = {"@type": "PostalAddress", "addressCountry": "KR"}
        if address_locality:
            addr["streetAddress"] = address_locality
        if region:
            addr["addressLocality"] = region
        schema["address"] = addr
    if phone:
        schema["telephone"] = phone
    if website:
        schema["url"] = website

    if main_categories:
        schema["availableService"] = [
            {"@type": "MedicalProcedure", "name": cat} for cat in main_categories
        ]

    # 한의원 표준 진료시간 — 비어 있으면 default 패턴
    schema["openingHoursSpecification"] = [
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "opens": "09:30",
            "closes": "19:00",
        },
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Saturday"],
            "opens": "09:30",
            "closes": "13:00",
        },
    ]

    return schema


# ──────────────────────────────────────────────────────────────────────
# FAQPage
# ──────────────────────────────────────────────────────────────────────


def generate_faq_page_schema(qa_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """qa_repository row 리스트 → FAQPage JSON-LD.

    qa_list item shape:
      {"question_pattern": "...", "standard_answer": "...", "variations": "[...]"}
    """
    main_entities: List[Dict[str, Any]] = []
    for qa in qa_list:
        q_raw = qa.get("question_pattern") or qa.get("question") or ""
        a_raw = qa.get("standard_answer") or qa.get("answer") or ""
        if not q_raw or not a_raw:
            continue

        # 정규식 메타문자 제거 (Google FAQPage는 자연어 권장)
        q_clean = (
            q_raw.replace("(", "")
            .replace(")", "")
            .replace("|", " 또는 ")
            .replace("?", "")
            .replace("\\", "")
            .strip()
        )
        # 길이 가드 (FAQPage 자연스러운 길이)
        if len(q_clean) > 200:
            q_clean = q_clean[:200].rstrip() + "…"

        main_entities.append(
            {
                "@type": "Question",
                "name": q_clean,
                "acceptedAnswer": {"@type": "Answer", "text": a_raw[:1500]},
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": main_entities,
    }


# ──────────────────────────────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────────────────────────────

# Google Rich Results 필수 필드 (2026 기준)
_REQUIRED: Dict[str, List[str]] = {
    "MedicalBusiness": ["name"],
    "FAQPage": ["mainEntity"],
    "Question": ["name", "acceptedAnswer"],
    "Answer": ["text"],
}

_RECOMMENDED: Dict[str, List[str]] = {
    "MedicalBusiness": ["address", "telephone", "url", "medicalSpecialty"],
}


def validate_schema(schema: Dict[str, Any]) -> List[str]:
    """필수 필드 누락 체크. 문제 메시지 리스트 반환 (빈 리스트 = 통과)."""
    issues: List[str] = []
    if not isinstance(schema, dict):
        return ["루트 객체가 dict 아님"]

    if schema.get("@context") != "https://schema.org":
        issues.append("@context 누락 또는 잘못됨 (https://schema.org 권장)")

    type_ = schema.get("@type")
    if not type_:
        issues.append("@type 누락")
        return issues

    # 필수
    for field in _REQUIRED.get(type_, []):
        if field not in schema or not schema[field]:
            issues.append(f"{type_}: 필수 필드 '{field}' 누락")

    # FAQPage 내부 검증
    if type_ == "FAQPage":
        entities = schema.get("mainEntity") or []
        if not isinstance(entities, list) or not entities:
            issues.append("FAQPage: mainEntity 비어있음")
        else:
            for i, q in enumerate(entities):
                if q.get("@type") != "Question":
                    issues.append(f"FAQPage.mainEntity[{i}]: @type='Question' 아님")
                for f in _REQUIRED["Question"]:
                    if f not in q or not q[f]:
                        issues.append(f"FAQPage.mainEntity[{i}]: '{f}' 누락")
                ans = q.get("acceptedAnswer", {})
                if isinstance(ans, dict):
                    for f in _REQUIRED["Answer"]:
                        if f not in ans or not ans[f]:
                            issues.append(
                                f"FAQPage.mainEntity[{i}].acceptedAnswer: '{f}' 누락"
                            )

    # 권장 필드 (warn 형식)
    for field in _RECOMMENDED.get(type_, []):
        if field not in schema or not schema[field]:
            issues.append(f"[권장] {type_}: '{field}' 추가 권장")

    return issues


def to_jsonld_string(schema: Dict[str, Any]) -> str:
    """파일 저장용. ensure_ascii=False, indent=2."""
    return json.dumps(schema, ensure_ascii=False, indent=2)


__all__ = [
    "generate_medical_business_schema",
    "generate_faq_page_schema",
    "validate_schema",
    "to_jsonld_string",
]
