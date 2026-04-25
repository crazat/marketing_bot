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
    "환자 치료경험담 (인플루언서)": {
        "severity": "high",
        "patterns": [
            # 1인칭 + 치료/한약/침/추나 조합 — 의료법 27조 3항 환자유인·알선
            r"(저|제|내|나)(는|가|도)?\s*(받|먹|맞|치료|침|한약|추나|진료|상담)",
            r"(저|제|내|나)(는|가|도)?\s*\S{0,15}(낫|좋아|효과|개선|치료됐|치료됨|회복)",
            r"직접\s*(받|먹|맞|체험|경험|치료)",
            r"(추천|알려|권장)\s*드(려|립)",
        ],
        "message": "비의료인의 치료경험담 게재는 환자유인·알선 (의료법 27조 3항, 3년 이하 징역/3천만원 벌금) 위험.",
        "recommendation": "1인칭 화법·직접체험 표현을 제거하고, 일반 정보 전달 형태로 수정하세요.",
    },
    "AI 의료진 추천 합성": {
        "severity": "high",
        "patterns": [
            r"(의사|한의사|약사|전문의)\s*(가|께서|이)\s*(추천|권장|말씀)",
            r"(원장|박사)\s*님?\s*(추천|권장)",
            r"전문(가|의)\s*(추천|보증|인증)",
        ],
        "message": "AI 합성 또는 비실명 의료진 추천 표현은 2025년부터 명시적 금지.",
        "recommendation": "실명 의료진의 사전 동의·심의받은 인용만 사용하세요.",
    },
    "광고/협찬 표기 누락": {
        "severity": "medium",
        # 이 카테고리는 missing-pattern 검출이라 별도 함수에서 처리 (아래 _check_disclosure)
        "patterns": [],
        "message": "체험단/협찬/광고 콘텐츠는 #광고 #협찬 명시 의무.",
        "recommendation": "콘텐츠 말미에 #광고 또는 #협찬 표기를 자동 첨부합니다.",
    },
    "비급여 할인·이벤트 광고": {
        "severity": "high",
        # 보건복지부 2025-2026 적발 26.7% — 의료법상 환자유인 행위로 강력 단속
        "patterns": [
            r"(특가|이벤트|할인가|반값)\s*(진료|시술|한약|치료|패키지)",
            r"\d+\s*%\s*(할인|세일|특가|혜택|DC|디시)",
            r"(첫\s*방문|첫\s*진료|신규\s*환자)\s*(무료|공짜|할인|혜택)",
            r"(무료\s*체험|무료\s*상담|무료\s*검진|0원\s*진료)",
            r"(런칭|오픈|개원)\s*(기념|특가|이벤트)",
            r"(선착순|한정\s*수량|이번\s*주만|당일\s*예약)",
            r"(원래|정가)\s*\S{0,10}원\s*\S{0,20}(특가|할인|이벤트|만원)",
        ],
        "message": "비급여 진료의 할인·이벤트·무료 유인은 의료법상 환자유인 행위(2025-2026 적발 26.7%).",
        "recommendation": "할인·이벤트 표현을 모두 제거하거나, 한의사협회 사전심의를 받으세요.",
    },
    "AI 가상인물 표시 누락": {
        "severity": "high",
        # 공정위 2026-04-08 행정예고: 매출 2% 과징금, 형사 2년/1.5억
        # 이 패턴은 AI 생성을 시사하는 어휘만 검출 — 표기 의무는 별도 함수에서 처리
        "patterns": [
            r"(가상\s*(?:인물|모델|의사|한의사)|AI\s*(?:생성|모델|아바타))",
            r"(딥페이크|deepfake|디지털\s*휴먼)",
        ],
        "message": "AI 가상인물·생성 콘텐츠는 명시적 표기 의무 (공정위 2026-04-08, 매출 2% 과징금 + 형사 2년).",
        "recommendation": "콘텐츠 제목 또는 첫 부분에 'AI 생성' 또는 '가상인물' 표기를 첨부하세요.",
    },
    "AI 의료진 추천 영상 (전면 금지)": {
        "severity": "high",
        # 식약처/약사법·식품법 개정 2026-04-23 통과 — AI 의료진 추천 광고 전면 금지
        "patterns": [
            r"(AI|인공지능|합성)\s*\S{0,10}(의사|한의사|약사|전문의|원장)",
            r"(AI|인공지능|합성)\s*\S{0,10}(추천|권장|보증|승인|효과\s*입증)",
            r"(가상|합성|딥페이크)\s*(의사|한의사|약사|전문의|원장|의료진)",
        ],
        "message": "AI 생성/합성 의료진 추천 광고는 2026-04-23 개정법으로 전면 금지 (식약처 단속).",
        "recommendation": "실명 의료진의 사전 동의·심의받은 인용만 사용. AI 합성 의료진은 절대 금지.",
    },
    "협찬 미표기 1인칭 후기 (강화)": {
        "severity": "high",
        # 적발 31.7% — 1인칭 표현 + 의료 트리거가 있는데 광고 표기가 없는 경우
        # 패턴 자체는 환자 치료경험담 카테고리가 잡지만, 강화 메시지로 표시
        "patterns": [
            r"(직접\s*받|직접\s*먹|직접\s*맞|체험해\s*봤|먹어\s*봤|받아\s*봤)",
            r"(협찬|광고|제공받|체험단|스폰서)\s*\S{0,5}(아닙니다|아니|없)",
        ],
        "message": "협찬·광고비 받은 환자후기를 자발적으로 위장 (적발 31.7%) — 형사 처벌.",
        "recommendation": "협찬 사실을 명확히 표기하거나, 비협찬 후기는 검증 가능한 출처를 명시하세요.",
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 인라인 스크린 — ai_generate_korean에서 자동 호출되는 경량 게이트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 광고/협찬 표기 (카카오/네이버/인스타 표기 의무)
_DISCLOSURE_TOKENS = ("#광고", "#협찬", "#체험단", "[광고]", "[협찬]", "[체험단]")

# 의료 콘텐츠 판정 트리거 — 한의원 진료 행위가 언급되면 의료광고 카테고리로 본다
_MEDICAL_TRIGGERS = (
    "한약", "한의원", "추나", "침", "뜸", "약침", "교정", "보약",
    "한방", "다이어트", "여드름", "비대칭", "교통사고", "디스크",
    "탈모", "비염", "불면", "통증", "보양", "보혈", "치료",
)


def _is_medical_context(text: str) -> bool:
    return any(t in text for t in _MEDICAL_TRIGGERS)


def _has_disclosure(text: str) -> bool:
    return any(tok in text for tok in _DISCLOSURE_TOKENS)


def screen_korean_comment(
    text: str,
    *,
    require_disclosure: bool = True,
    auto_append_disclosure: bool = True,
) -> Dict[str, Any]:
    """
    한국어 마케팅 댓글/콘텐츠 인라인 스크린.

    AI 생성 직후 ai_client.py에서 자동 호출. AI 호출 없음(비용 0). 정규식만.

    Args:
        text: 검사할 한국어 콘텐츠
        require_disclosure: 의료 콘텐츠일 때 #광고/#협찬 표기 강제
        auto_append_disclosure: 표기 누락 시 자동 #광고 첨부

    Returns:
        {
            "passed": bool,            # high severity 위반 없으면 True
            "violations": [...],       # 카테고리·매치 텍스트 목록
            "max_severity": "info|low|medium|high",
            "final_text": str,         # 자동 표기 첨부된 최종 텍스트
            "auto_modified": bool,     # final_text가 원문과 다른지
        }
    """
    base = check_content_compliance(text, content_type="comment")
    violations = base.get("issues", [])
    max_sev = base.get("severity", "info")

    final_text = text
    auto_modified = False

    # 의료 콘텐츠인데 표기 누락 → 자동 첨부
    if _is_medical_context(text) and require_disclosure and not _has_disclosure(text):
        if auto_append_disclosure:
            final_text = (text.rstrip() + "\n\n#광고 #규림한의원").strip()
            auto_modified = True
        violations.append({
            "category": "광고/협찬 표기 누락",
            "severity": "medium",
            "matched": "(의료 콘텐츠 + 표기 부재)",
            "message": "#광고 또는 #협찬 표기 의무.",
            "recommendation": "자동으로 #광고 표기 첨부됨." if auto_append_disclosure else "수동으로 표기 추가하세요.",
        })
        if max_sev in ("info", "low"):
            max_sev = "medium"

    passed = max_sev != "high"

    return {
        "passed": passed,
        "violations": violations,
        "max_severity": max_sev,
        "final_text": final_text,
        "auto_modified": auto_modified or final_text != text,
    }


# 표준 AI 고지 푸터 — 한국 AI 기본법 (2026/1 시행)
_AI_DISCLOSURE_FOOTER = "\n\n※ 본 콘텐츠는 AI 보조로 작성되었습니다."


def append_ai_disclosure(text: str) -> str:
    """이미 고지 문구가 있으면 그대로, 없으면 자동 첨부.

    한국 AI 기본법 (2026/1) — 생성형 AI 사용 사실 고지 의무.
    의료 콘텐츠는 더 엄격하게 적용.
    """
    if not text:
        return text
    indicators = ("AI 보조로 작성", "AI 생성", "AI로 작성", "AI 도움", "인공지능 도움")
    if any(ind in text for ind in indicators):
        return text
    return text.rstrip() + _AI_DISCLOSURE_FOOTER


def log_korean_screen(
    db_path: str,
    *,
    call_site: str,
    prompt_sample: str,
    generated_text: str,
    screen_result: Dict[str, Any],
    retry_count: int = 0,
) -> Optional[int]:
    """
    한국어 댓글 스크린 결과를 ai_korean_screen_log 테이블에 기록.

    db_init.py에서 테이블 생성. 누락 시 자동 생성.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_korean_screen_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                call_site TEXT,
                prompt_sample TEXT,
                generated_text TEXT,
                final_text TEXT,
                passed INTEGER,
                max_severity TEXT,
                violations_json TEXT,
                auto_modified INTEGER,
                retry_count INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            INSERT INTO ai_korean_screen_log
              (call_site, prompt_sample, generated_text, final_text,
               passed, max_severity, violations_json, auto_modified, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            call_site or "",
            (prompt_sample or "")[:500],
            (generated_text or "")[:2000],
            (screen_result.get("final_text") or "")[:2000],
            1 if screen_result.get("passed") else 0,
            screen_result.get("max_severity", "info"),
            json.dumps(screen_result.get("violations", []), ensure_ascii=False),
            1 if screen_result.get("auto_modified") else 0,
            retry_count,
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.warning(f"[compliance] 스크린 로그 저장 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


def _resolve_default_db_path() -> Optional[str]:
    """프로젝트 루트의 db/marketing_data.db 절대경로."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        # services/ → backend/ → marketing_bot_web/ → project root
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        path = os.path.join(root, "db", "marketing_data.db")
        return path if os.path.exists(path) else None
    except Exception:
        return None


# os import는 모듈 상단에서 누락 가능 — 안전 import
import os  # noqa: E402  (의도된 늦은 import)
