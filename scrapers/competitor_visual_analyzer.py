"""
경쟁사 Place 사진 시각 약점 분석 (Gemini Vision)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ROI: 9곳 × 사진 20장 = 180장/일, Gemini Flash Lite Vision $0.03/일 (월 $0.90)

분석 5축:
  - interior_cleanliness (0-10)
  - staff_visible (의료진 사진 노출 여부)
  - facility_modernity (0-10)
  - patient_review_photos (사진 후기 수)
  - weakness_summary (자유 서술)

저장: competitor_visual_scores 테이블 (db_init에서 생성)

사용:
    python scrapers/competitor_visual_analyzer.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urlparse

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'marketing_bot_web', 'backend'))

from utils import logger as _logger

logger = _logger


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Vision schema
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _schema():
    """Pydantic schema for structured Vision output."""
    from pydantic import BaseModel, Field

    class VisualScore(BaseModel):
        interior_cleanliness: float = Field(ge=0, le=10, description="0-10, 인테리어 청결/세련")
        staff_visible: bool = Field(description="원장/의료진 사진 노출 여부")
        facility_modernity: float = Field(ge=0, le=10, description="0-10, 시설 현대성")
        patient_review_photos: int = Field(ge=0, description="환자 후기 사진 수 (추정)")
        weakness_summary: str = Field(description="50-150자 한국어 약점 요약")
        our_advantage_hint: str = Field(description="50자 이내 우리(규림) 차별화 힌트")

    return VisualScore


PROMPT = """당신은 청주 한의원 마케팅 컨설턴트입니다.
경쟁사 한의원의 네이버 플레이스에 올라온 사진들을 분석하여 5가지 축으로 평가하세요.

[평가 축]
1. interior_cleanliness (0-10): 인테리어 청결/세련도
2. staff_visible (true/false): 원장·의료진 얼굴이 사진에 보이는가
3. facility_modernity (0-10): 시설 현대성·신축감
4. patient_review_photos (정수): 환자가 직접 찍은 후기 사진 수 추정
5. weakness_summary (50-150자): 이 한의원의 사진 마케팅 약점
6. our_advantage_hint (50자): 우리 한의원이 어떤 사진으로 차별화하면 좋을지

JSON으로 응답."""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사진 URL 수집 (place_id → photo URLs)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_place_photos(place_id: str, max_photos: int = 20) -> List[str]:
    """네이버 플레이스 m.place.naver.com/restaurant/{place_id}/photo 에서 사진 URL 추출.

    한의원도 'restaurant' path 활용 (네이버 plate API 패턴).
    캡차 회피 위해 Camoufox 사용.
    """
    try:
        from scrapers.camoufox_engine import CamoufoxFetcher
    except ImportError:
        logger.warning("camoufox unavailable, fallback to empty photo list")
        return []

    photo_urls: List[str] = []
    url = f"https://m.place.naver.com/hospital/{place_id}/photo"

    with CamoufoxFetcher(headless=True) as f:
        html = f.fetch(url, wait_ms=2000)
        if not html or f.is_blocked(html):
            return []
        # 사진 URL 추출 (네이버 CDN 패턴)
        import re
        # phinf.pstatic.net / pup-review.pstatic.net 등
        candidates = re.findall(
            r'https?://[^\s"\']+\.(?:pstatic\.net|naver\.net)[^\s"\']*?\.(?:jpg|jpeg|png|webp)',
            html, re.IGNORECASE,
        )
        # 중복 제거 + 작은 thumbnail 제외 (URL에 'w80'/'w100' 같은 작은 사이즈 제외)
        seen = set()
        for u in candidates:
            base = u.split("?")[0]
            if base in seen:
                continue
            if any(small in u for small in ("w80", "w100", "w120")):
                continue
            seen.add(base)
            photo_urls.append(u)
            if len(photo_urls) >= max_photos:
                break
    return photo_urls


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Analyze
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_competitor_photos(
    competitor_name: str,
    place_id: str,
    max_photos: int = 20,
) -> Optional[Dict[str, Any]]:
    """1개 경쟁사 분석 후 dict 반환 + DB 저장."""
    from services.ai_client import ai_analyze_image

    photos = _fetch_place_photos(place_id, max_photos=max_photos)
    if not photos:
        logger.warning(f"[visual] {competitor_name}: 사진 0건, 스킵")
        return None

    Schema = _schema()
    # 1번 호출에 여러 사진 batch
    result = ai_analyze_image(
        photos[:max_photos],  # multi-image
        PROMPT,
        response_schema=Schema,
        temperature=0.3,
        max_tokens=600,
    )
    if result is None:
        logger.warning(f"[visual] {competitor_name}: vision 실패")
        return None

    out = {
        "competitor_name": competitor_name,
        "place_id": place_id,
        "scanned_date": datetime.now().strftime("%Y-%m-%d"),
        "interior_cleanliness": result.interior_cleanliness,
        "staff_visible": result.staff_visible,
        "facility_modernity": result.facility_modernity,
        "patient_review_photos": result.patient_review_photos,
        "weakness_summary": result.weakness_summary,
        "our_advantage_hint": result.our_advantage_hint,
        "photo_count_analyzed": len(photos),
    }
    _save(out)
    logger.info(
        f"[visual] {competitor_name}: 청결{out['interior_cleanliness']:.1f}/"
        f"현대{out['facility_modernity']:.1f} | {out['weakness_summary'][:50]}"
    )
    return out


def _save(row: Dict[str, Any]) -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    db = os.path.join(os.path.dirname(here), "db", "marketing_data.db")
    conn = None
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO competitor_visual_scores
              (competitor_name, place_id, scanned_date,
               interior_cleanliness, staff_visible, facility_modernity,
               patient_review_photos, weakness_summary, photo_count_analyzed,
               raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["competitor_name"], row["place_id"], row["scanned_date"],
            row["interior_cleanliness"], 1 if row["staff_visible"] else 0,
            row["facility_modernity"], row["patient_review_photos"],
            row["weakness_summary"], row["photo_count_analyzed"],
            json.dumps(row, ensure_ascii=False, default=str),
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"[visual] DB save 실패: {e}")
    finally:
        if conn:
            conn.close()


def run_all() -> Dict[str, Any]:
    """rank_history나 competitor_reviews에 등록된 모든 경쟁사 분석."""
    here = os.path.dirname(os.path.abspath(__file__))
    db = os.path.join(os.path.dirname(here), "db", "marketing_data.db")

    competitors = []
    conn = None
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # competitor_reviews에서 place_id 추출 (가장 신뢰도 높은 source)
        cur.execute("""
            SELECT DISTINCT competitor_name, place_id
            FROM competitor_reviews
            WHERE place_id IS NOT NULL AND place_id != ''
            LIMIT 20
        """)
        competitors = [(r["competitor_name"], r["place_id"]) for r in cur.fetchall()]
    except Exception as e:
        logger.warning(f"competitor list 로드 실패: {e}")
    finally:
        if conn:
            conn.close()

    if not competitors:
        logger.warning("경쟁사 목록 비어있음")
        return {"analyzed": 0, "failed": 0}

    analyzed = 0
    failed = 0
    for name, pid in competitors:
        try:
            r = analyze_competitor_photos(name, str(pid), max_photos=20)
            if r:
                analyzed += 1
            else:
                failed += 1
            time.sleep(2)  # rate limit
        except Exception as e:
            logger.error(f"[visual] {name} 실패: {e}")
            failed += 1
    return {"analyzed": analyzed, "failed": failed, "total": len(competitors)}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")
    summary = run_all()
    print(f"\n경쟁사 시각 분석 완료: {summary['analyzed']}/{summary['total']} (실패 {summary['failed']})")
