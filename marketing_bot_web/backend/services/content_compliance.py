"""
의료광고 규정 준수 체크 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 C-5] 블로그/SNS 콘텐츠의 의료광고 규정 위반 사전 점검

규정 근거:
- 의료법 제56조 (의료광고의 금지 등)
- 의료광고 심의 기준 (보건복지부 고시)
- 대한한의사협회 SNS/블로그 의료광고 심의 가이드북 (2025.09)

핵심 규칙:
1. 치료 전후 사진: 심의 없이 게시 금지
2. "완치", "100% 효과" 등 단정적 표현 금지
3. 타 의료기관 비방 금지
4. 인플루언서 협찬/광고비 지급 방식 홍보 금지
5. 환자 후기: 동의 + 심의 필수
6. 과도한 할인/이벤트 유인 금지
"""

import sqlite3
import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 규정 위반 키워드/패턴 사전
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VIOLATION_PATTERNS = {
    "단정적 표현": {
        "severity": "high",
        "patterns": [
            r"100%\s*(효과|치료|완치|개선)",
            r"완치\s*(가능|됩니다|보장)",
            r"확실(한|히)\s*(효과|치료|치유)",
            r"반드시\s*(낫|치료|효과)",
            r"무조건\s*(효과|낫|좋아)",
            r"보장\s*(합니다|드립니다)",
        ],
        "message": "치료 효과를 단정적으로 표현하는 것은 의료법 위반입니다.",
        "recommendation": "'개선될 수 있습니다', '도움이 될 수 있습니다' 등 가능성 표현으로 수정하세요.",
    },
    "비교 광고": {
        "severity": "high",
        "patterns": [
            r"(최고|최상|1등|넘버원|No\.?\s*1)\s*(한의원|병원|의원|클리닉)",
            r"(타|다른|경쟁)\s*(한의원|병원).*보다\s*(낫|좋|우수|뛰어)",
            r"유일(한|하게)\s*(치료|효과|기술)",
        ],
        "message": "타 의료기관과의 비교 또는 최상급 표현은 금지됩니다.",
        "recommendation": "객관적 사실이나 자사 장점만 기술하세요.",
    },
    "환자 후기 규정": {
        "severity": "medium",
        "patterns": [
            r"(환자|고객)\s*(후기|리뷰|감사|추천|소감)",
            r"치료\s*(전|후)\s*(사진|비교|변화)",
            r"(before|after|비포|애프터)",
        ],
        "message": "환자 후기 및 치료 전후 사진은 사전심의가 필요합니다.",
        "recommendation": "한의사협회 심의위원회(ad.akom.org) 사전심의 후 게시하세요.",
    },
    "과도한 유인": {
        "severity": "medium",
        "patterns": [
            r"무료\s*(진료|상담|치료|시술)",
            r"\d+%\s*(할인|세일|이벤트)",
            r"(선착순|한정|특별)\s*(할인|가격|이벤트)",
            r"(경품|사은품|선물)\s*(증정|제공)",
        ],
        "message": "과도한 할인이나 경품 제공으로 환자를 유인하는 것은 제한됩니다.",
        "recommendation": "할인/이벤트 표현을 절제하거나, 심의를 받으세요.",
    },
    "비급여 가격 표시": {
        "severity": "low",
        "patterns": [
            r"\d+[,.]?\d*\s*(만\s*)?원",
        ],
        "message": "비급여 진료 가격 표시는 허용되지만, 정확한 정보여야 합니다.",
        "recommendation": "표시된 가격이 실제 적용 가격과 일치하는지 확인하세요.",
    },
}


def check_content_compliance(content: str, content_type: str = "blog") -> Dict[str, Any]:
    """
    콘텐츠의 의료광고 규정 준수 여부를 키워드 기반으로 사전 체크합니다.

    Args:
        content: 검사할 콘텐츠 텍스트
        content_type: 콘텐츠 유형 (blog, instagram, youtube, tiktok)

    Returns:
        {
            "result": "pass" | "warning" | "violation",
            "issues": [...],
            "severity": "info" | "low" | "medium" | "high",
            "score": 0-100 (높을수록 안전),
        }
    """
    issues = []
    max_severity = "info"
    severity_order = {"info": 0, "low": 1, "medium": 2, "high": 3}

    for category, rule in VIOLATION_PATTERNS.items():
        for pattern in rule["patterns"]:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                issue = {
                    "category": category,
                    "severity": rule["severity"],
                    "matched": matches[0] if isinstance(matches[0], str) else " ".join(matches[0]),
                    "message": rule["message"],
                    "recommendation": rule["recommendation"],
                }
                issues.append(issue)

                if severity_order.get(rule["severity"], 0) > severity_order.get(max_severity, 0):
                    max_severity = rule["severity"]
                break  # 카테고리당 1개만 보고

    # 결과 판정
    if not issues:
        result = "pass"
        score = 100
    elif max_severity == "high":
        result = "violation"
        score = max(0, 100 - len(issues) * 25)
    else:
        result = "warning"
        score = max(0, 100 - len(issues) * 15)

    return {
        "result": result,
        "issues": issues,
        "severity": max_severity,
        "score": score,
        "checked_items": len(VIOLATION_PATTERNS),
    }


async def check_with_ai(
    content: str,
    content_type: str = "blog",
) -> Dict[str, Any]:
    """
    Gemini AI를 사용하여 의료광고 규정 위반 여부를 정밀 분석합니다.

    키워드 기반 사전 체크 후, AI가 맥락을 고려한 정밀 분석을 수행합니다.
    """
    # 1단계: 키워드 기반 사전 체크
    keyword_result = check_content_compliance(content, content_type)

    # 2단계: AI 정밀 분석
    try:
        from services.ai_client import ai_generate_json

        prompt = f"""당신은 한국 의료광고법 전문가입니다.
아래 {content_type} 콘텐츠가 의료광고 규정을 준수하는지 분석해주세요.

[콘텐츠]
{content[:2000]}

[분석 기준]
1. 의료법 제56조 (의료광고의 금지 등)
2. 치료 효과 단정적 표현 여부
3. 타 의료기관 비교/비방 여부
4. 환자 후기/치료전후 사진 심의 필요 여부
5. 과도한 유인(할인/경품) 여부
6. 허위/과대 광고 여부

[응답 형식 - 반드시 JSON으로]
{{
    "overall_assessment": "safe|caution|violation",
    "issues": [
        {{"category": "분류", "detail": "구체적 문제", "recommendation": "수정 제안"}}
    ],
    "summary": "1~2줄 요약"
}}
"""

        ai_result = ai_generate_json(prompt, temperature=0.3, max_tokens=500)
        if ai_result:
            keyword_result["ai_analysis"] = ai_result
        else:
            keyword_result["ai_analysis"] = "AI 분석 실패 - 키워드 기반 분석만 수행"

    except Exception as e:
        logger.error(f"AI 규정 체크 실패: {e}")
        keyword_result["ai_analysis"] = f"AI 분석 실패: {str(e)}"

    return keyword_result


def save_compliance_check(
    db_path: str,
    content_type: str,
    content_title: str,
    content_url: Optional[str],
    content_text: str,
    result: Dict[str, Any],
) -> Optional[int]:
    """규정 체크 결과를 DB에 저장"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO content_compliance_checks
            (content_type, content_title, content_url, content_text,
             ai_check_result, compliance_issues, severity, recommendations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            content_type,
            content_title,
            content_url,
            content_text[:5000],
            result.get("result", "pending"),
            json.dumps(result.get("issues", []), ensure_ascii=False),
            result.get("severity", "info"),
            json.dumps(result.get("ai_analysis", ""), ensure_ascii=False)
                if isinstance(result.get("ai_analysis"), (dict, list))
                else str(result.get("ai_analysis", "")),
        ))

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        logger.error(f"규정 체크 저장 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()
