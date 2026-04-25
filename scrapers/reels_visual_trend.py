"""
Instagram Reels Visual Hook 트렌드 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

청주 한의원 카테고리 인기 Reels의 첫 프레임(hook)을 Vision으로 분석.
색감/구도/텍스트 위치/객체(침/뜸/원장) 패턴을 일별 클러스터링.

ROI: 카테고리 상위 reels 30개 × 썸네일 1장/주 = $0.005/주 (월 $0.02)

저장: visual_trend_signals 테이블
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'marketing_bot_web', 'backend'))

from utils import logger as _logger

logger = _logger


def _db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "db", "marketing_data.db")


def _schema():
    """Pydantic schema for Vision output."""
    from pydantic import BaseModel, Field

    class HookAnalysis(BaseModel):
        dominant_colors: List[str] = Field(description="HEX 또는 색상명, 최대 3개")
        composition: str = Field(description="centered|asymmetric|split|grid|portrait")
        text_position: str = Field(description="top|center|bottom|none")
        text_overlay_summary: str = Field(description="텍스트 내용 요약 (50자 이내)")
        objects: List[str] = Field(description="등장 객체 (의료진/침/뜸/약/한의원 인테리어/환자/기타)")
        emotion_tone: str = Field(description="trustworthy|trendy|dramatic|playful|professional|warm")
        visual_hook_score: float = Field(ge=0, le=10, description="0-10, 첫 3초 시선 끌림")

    return HookAnalysis


PROMPT = """당신은 인스타그램 Reels 시각 마케팅 분석가입니다.
청주 한의원 카테고리 Reels 썸네일(첫 프레임)을 분석하세요.

[분석 항목]
1. dominant_colors: 주요 색상 3개 (HEX 또는 한글 색상명)
2. composition: centered | asymmetric | split | grid | portrait
3. text_position: 텍스트 오버레이 위치 (top/center/bottom/none)
4. text_overlay_summary: 텍스트 내용 요약 (50자 이내)
5. objects: 등장 객체 list (의료진/침/뜸/약/인테리어/환자/기타)
6. emotion_tone: trustworthy/trendy/dramatic/playful/professional/warm 중 하나
7. visual_hook_score: 0-10, 첫 3초 시선 끌림 강도

JSON으로 응답."""


def analyze_reel_thumbnail(thumbnail_url: str) -> Optional[Dict[str, Any]]:
    """1개 썸네일 분석."""
    from services.ai_client import ai_analyze_image
    Schema = _schema()
    result = ai_analyze_image(
        thumbnail_url,
        PROMPT,
        response_schema=Schema,
        temperature=0.3,
        max_tokens=600,
    )
    if result is None:
        return None
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


def aggregate_trends(reel_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """N개 분석 → 시각 트렌드 패턴 추출."""
    from collections import Counter
    if not reel_analyses:
        return {"n": 0}

    n = len(reel_analyses)
    color_counter = Counter()
    composition_counter = Counter()
    tone_counter = Counter()
    object_counter = Counter()
    text_pos_counter = Counter()

    for r in reel_analyses:
        for c in r.get("dominant_colors", []) or []:
            color_counter[c] += 1
        composition_counter[r.get("composition", "?")] += 1
        tone_counter[r.get("emotion_tone", "?")] += 1
        text_pos_counter[r.get("text_position", "?")] += 1
        for o in r.get("objects", []) or []:
            object_counter[o] += 1

    avg_hook_score = sum(r.get("visual_hook_score", 0) for r in reel_analyses) / n

    # Top 패턴
    top_color = color_counter.most_common(3)
    top_composition = composition_counter.most_common(2)
    top_tone = tone_counter.most_common(2)
    top_objects = object_counter.most_common(5)

    # 트렌드 강도 (top1 비율)
    strength = max([c for _, c in composition_counter.most_common(1)] or [0]) / n

    summary = (
        f"우세 톤: {top_tone[0][0] if top_tone else '?'} ({top_tone[0][1] if top_tone else 0}/{n}). "
        f"주요 객체: {', '.join(o for o, _ in top_objects[:3])}. "
        f"평균 hook 점수: {avg_hook_score:.1f}/10."
    )

    return {
        "n": n,
        "top_colors": top_color,
        "top_composition": top_composition,
        "top_tone": top_tone,
        "top_objects": top_objects,
        "top_text_position": text_pos_counter.most_common(2),
        "avg_hook_score": round(avg_hook_score, 2),
        "trend_strength": round(strength, 3),
        "summary": summary,
    }


def _save_aggregate(category: str, agg: Dict[str, Any]) -> None:
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO visual_trend_signals
              (scanned_date, platform, category, visual_pattern,
               trend_strength, sample_count, summary, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d"),
            "instagram",
            category,
            json.dumps(agg.get("top_composition", []) + agg.get("top_tone", []),
                       ensure_ascii=False),
            agg.get("trend_strength", 0.0),
            agg.get("n", 0),
            agg.get("summary", ""),
            json.dumps(agg, ensure_ascii=False, default=str),
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"[reels] DB save 실패: {e}")
    finally:
        if conn:
            conn.close()


def run(thumbnail_urls: List[str], category: str = "한의원") -> Dict[str, Any]:
    """N개 thumbnail URL 분석 + aggregate + DB 저장."""
    if not thumbnail_urls:
        return {"n": 0, "warning": "no thumbnails"}

    analyses = []
    for i, url in enumerate(thumbnail_urls, 1):
        try:
            a = analyze_reel_thumbnail(url)
            if a:
                analyses.append(a)
                logger.info(f"[reels] {i}/{len(thumbnail_urls)}: {a.get('emotion_tone')} hook={a.get('visual_hook_score')}")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"[reels] {i} 실패: {e}")

    agg = aggregate_trends(analyses)
    _save_aggregate(category, agg)
    return agg


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")
    # 데모 — 실제 사용 시 scraper_instagram.py에서 thumbnail URL 추출 후 호출
    demo_urls = []  # 실제 운영 시 채워짐
    if not demo_urls:
        print("Demo URL 비어있음. scraper_instagram.py 통합 후 사용.")
        sys.exit(0)
    result = run(demo_urls, category="한의원")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
