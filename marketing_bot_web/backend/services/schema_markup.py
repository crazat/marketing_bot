"""
Schema Markup (JSON-LD) 자동 생성
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-7] 의료기관 구조화 데이터 자동 생성

지원 스키마:
- MedicalClinic: 한의원 기본 정보
- FAQPage: FAQ 콘텐츠
- MedicalProcedure: 시술/치료 정보
- Article: 블로그 포스트
- IndividualPhysician: 원장님 프로필

Google AI Overview + 네이버 AI 브리핑 노출에 핵심적 역할
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime


def generate_medical_clinic_schema(
    name: str,
    address: Dict[str, str],
    phone: str,
    url: str = None,
    specialties: List[str] = None,
    opening_hours: List[Dict[str, Any]] = None,
    image: str = None,
    rating: float = None,
    review_count: int = None,
    services: List[str] = None,
) -> Dict[str, Any]:
    """
    MedicalClinic 스키마 생성

    Args:
        name: 한의원 이름
        address: {"street": "...", "city": "...", "region": "...", "postal": "...", "country": "KR"}
        phone: 전화번호
    """
    schema = {
        "@context": "https://schema.org",
        "@type": "MedicalClinic",
        "name": name,
        "telephone": phone,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": address.get("street", ""),
            "addressLocality": address.get("city", ""),
            "addressRegion": address.get("region", ""),
            "postalCode": address.get("postal", ""),
            "addressCountry": address.get("country", "KR"),
        },
        "isAcceptingNewPatients": True,
    }

    if url:
        schema["url"] = url
    if image:
        schema["image"] = image
    if specialties:
        schema["medicalSpecialty"] = specialties
    if services:
        schema["availableService"] = [
            {"@type": "MedicalProcedure", "name": s} for s in services
        ]
    if opening_hours:
        schema["openingHoursSpecification"] = [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": h.get("days", []),
                "opens": h.get("opens", "09:00"),
                "closes": h.get("closes", "18:00"),
            }
            for h in opening_hours
        ]
    if rating and review_count:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(rating),
            "reviewCount": str(review_count),
        }

    return schema


def generate_faq_schema(faqs: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    FAQPage 스키마 생성

    Args:
        faqs: [{"question": "...", "answer": "..."}, ...]
    """
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq["answer"],
                },
            }
            for faq in faqs
        ],
    }


def generate_article_schema(
    title: str,
    author_name: str,
    date_published: str,
    description: str,
    url: str = None,
    image: str = None,
    author_credentials: str = None,
    medical_reviewer: str = None,
) -> Dict[str, Any]:
    """
    Article 스키마 생성 (블로그 포스트용)

    E-E-A-T 신호 극대화를 위해 author 정보와 medical review 포함
    """
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": date_published,
        "dateModified": datetime.now().strftime("%Y-%m-%d"),
        "author": {
            "@type": "Person",
            "name": author_name,
        },
    }

    if url:
        schema["url"] = url
    if image:
        schema["image"] = image
    if author_credentials:
        schema["author"]["jobTitle"] = author_credentials
    if medical_reviewer:
        schema["reviewedBy"] = {
            "@type": "Person",
            "name": medical_reviewer,
            "jobTitle": "한의사",
        }

    return schema


def generate_medical_procedure_schema(
    name: str,
    description: str,
    body_location: str = None,
    procedure_type: str = "TherapeuticProcedure",
    how_performed: str = None,
) -> Dict[str, Any]:
    """MedicalProcedure 스키마 (시술/치료 정보)"""
    schema = {
        "@context": "https://schema.org",
        "@type": procedure_type,
        "name": name,
        "description": description,
    }

    if body_location:
        schema["bodyLocation"] = body_location
    if how_performed:
        schema["howPerformed"] = how_performed

    return schema


def generate_physician_schema(
    name: str,
    specialty: str,
    clinic_name: str,
    qualifications: List[str] = None,
    image: str = None,
) -> Dict[str, Any]:
    """IndividualPhysician 스키마 (원장님 프로필)"""
    schema = {
        "@context": "https://schema.org",
        "@type": "Physician",
        "name": name,
        "medicalSpecialty": specialty,
        "worksFor": {
            "@type": "MedicalClinic",
            "name": clinic_name,
        },
    }

    if qualifications:
        schema["hasCredential"] = [
            {"@type": "EducationalOccupationalCredential", "credentialCategory": q}
            for q in qualifications
        ]
    if image:
        schema["image"] = image

    return schema


def schema_to_html(schema: Dict[str, Any]) -> str:
    """스키마를 HTML script 태그로 변환 (블로그 삽입용)"""
    json_ld = json.dumps(schema, ensure_ascii=False, indent=2)
    return f'<script type="application/ld+json">\n{json_ld}\n</script>'


def generate_blog_post_schemas(
    title: str,
    author_name: str,
    date_published: str,
    description: str,
    faqs: List[Dict[str, str]] = None,
    url: str = None,
    image: str = None,
) -> str:
    """
    블로그 포스트에 필요한 모든 스키마를 한번에 생성

    Article + FAQPage(있는 경우) 스키마를 HTML script 태그로 반환
    """
    schemas = []

    # Article 스키마
    article = generate_article_schema(
        title=title,
        author_name=author_name,
        date_published=date_published,
        description=description,
        url=url,
        image=image,
    )
    schemas.append(schema_to_html(article))

    # FAQ 스키마 (있는 경우)
    if faqs:
        faq_schema = generate_faq_schema(faqs)
        schemas.append(schema_to_html(faq_schema))

    return "\n\n".join(schemas)
