"""
Real-time Trend Detector
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3.2] 실시간 트렌드 감지 서비스

급상승 키워드를 실시간으로 감지:
- 최근 N시간/일 동안 수집된 데이터 분석
- 과거 평균 대비 급상승 키워드 탐지
- 트렌드 레벨 분류 (HOT, RISING, STABLE, DECLINING)
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)

# DB 경로
DB_PATH = Path(__file__).parent.parent / 'db' / 'marketing_data.db'


@dataclass
class TrendingKeyword:
    """트렌드 키워드"""
    keyword: str
    current_count: int
    avg_count: float
    growth_rate: float
    trend_level: str  # HOT, RISING, STABLE, DECLINING
    sources: List[str]  # 발견된 소스 (viral, pathfinder, etc.)
    first_seen: Optional[datetime] = None
    peak_time: Optional[datetime] = None


class TrendDetector:
    """
    실시간 트렌드 감지기

    다양한 소스에서 키워드 빈도를 분석하여
    급상승 트렌드를 감지합니다.
    """

    # 트렌드 레벨 임계값
    TREND_THRESHOLDS = {
        'HOT': 5.0,      # 평균 대비 5배 이상
        'RISING': 2.0,   # 평균 대비 2배 이상
        'STABLE': 0.8,   # 평균 대비 80% 이상
        'DECLINING': 0.0  # 그 외
    }

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._keyword_history: Dict[str, List[Tuple[datetime, int]]] = defaultdict(list)

    def _get_db_connection(self) -> sqlite3.Connection:
        """DB 연결"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def detect_rising_keywords(
        self,
        hours: int = 24,
        min_count: int = 3,
        limit: int = 50
    ) -> List[TrendingKeyword]:
        """
        급상승 키워드 감지

        Args:
            hours: 분석 기간 (시간)
            min_count: 최소 등장 횟수
            limit: 최대 반환 개수

        Returns:
            TrendingKeyword 목록 (growth_rate 내림차순)
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            # 분석 기간 계산
            now = datetime.now()
            period_start = now - timedelta(hours=hours)
            historical_start = now - timedelta(days=30)

            # 1. 최근 기간 키워드 수집 (viral_targets)
            recent_keywords = self._get_recent_keywords(
                cursor, period_start, now
            )

            # 2. 과거 30일 평균 계산
            historical_avg = self._get_historical_average(
                cursor, historical_start, period_start
            )

            # 3. 트렌드 분석
            trending = []
            for keyword, count in recent_keywords.items():
                if count < min_count:
                    continue

                avg = historical_avg.get(keyword, 0.1)  # 0 방지
                growth_rate = count / avg

                trend_level = self._classify_trend(growth_rate)

                trending.append(TrendingKeyword(
                    keyword=keyword,
                    current_count=count,
                    avg_count=avg,
                    growth_rate=growth_rate,
                    trend_level=trend_level,
                    sources=['viral_targets']
                ))

            # 4. Pathfinder 키워드도 분석
            pf_trending = self._analyze_pathfinder_trends(cursor, hours)
            for item in pf_trending:
                # 기존 목록에 있으면 병합
                existing = next((t for t in trending if t.keyword == item.keyword), None)
                if existing:
                    existing.sources.append('pathfinder')
                    existing.current_count += item.current_count
                else:
                    trending.append(item)

            conn.close()

            # 정렬 및 제한
            trending.sort(key=lambda x: x.growth_rate, reverse=True)

            hot_count = sum(1 for t in trending if t.trend_level == 'HOT')
            rising_count = sum(1 for t in trending if t.trend_level == 'RISING')

            logger.info(
                f"🔥 트렌드 감지 완료: {len(trending)}개 키워드 "
                f"(HOT: {hot_count}, RISING: {rising_count})"
            )

            return trending[:limit]

        except Exception as e:
            logger.error(f"트렌드 감지 실패: {e}")
            return []

    def _get_recent_keywords(
        self,
        cursor: sqlite3.Cursor,
        start: datetime,
        end: datetime
    ) -> Dict[str, int]:
        """최근 기간 키워드 빈도 수집"""
        keywords = Counter()

        try:
            # viral_targets에서 키워드 추출
            cursor.execute("""
                SELECT title, content_preview, matched_keywords
                FROM viral_targets
                WHERE scraped_at >= ? AND scraped_at <= ?
            """, (start.isoformat(), end.isoformat()))

            for row in cursor.fetchall():
                # 매칭된 키워드
                if row['matched_keywords']:
                    for kw in row['matched_keywords'].split(','):
                        kw = kw.strip()
                        if kw and len(kw) >= 2:
                            keywords[kw] += 1

                # 제목/내용에서 추가 키워드 추출
                text = f"{row['title'] or ''} {row['content_preview'] or ''}"
                extracted = self._extract_keywords(text)
                for kw in extracted:
                    keywords[kw] += 1

        except sqlite3.OperationalError as e:
            logger.warning(f"viral_targets 테이블 조회 실패: {e}")

        return dict(keywords)

    def _get_historical_average(
        self,
        cursor: sqlite3.Cursor,
        start: datetime,
        end: datetime
    ) -> Dict[str, float]:
        """과거 기간 키워드 일평균 계산"""
        keywords = Counter()
        days = (end - start).days or 1

        try:
            cursor.execute("""
                SELECT title, content_preview, matched_keywords
                FROM viral_targets
                WHERE scraped_at >= ? AND scraped_at < ?
            """, (start.isoformat(), end.isoformat()))

            for row in cursor.fetchall():
                if row['matched_keywords']:
                    for kw in row['matched_keywords'].split(','):
                        kw = kw.strip()
                        if kw and len(kw) >= 2:
                            keywords[kw] += 1

        except sqlite3.OperationalError:
            pass

        # 일평균 계산
        return {kw: count / days for kw, count in keywords.items()}

    def _analyze_pathfinder_trends(
        self,
        cursor: sqlite3.Cursor,
        hours: int
    ) -> List[TrendingKeyword]:
        """Pathfinder 키워드 트렌드 분석"""
        trending = []

        try:
            # 최근 스캔된 키워드
            cursor.execute("""
                SELECT keyword, grade, search_volume, created_at
                FROM keyword_insights
                WHERE created_at >= datetime('now', ?)
                ORDER BY created_at DESC
            """, (f'-{hours} hours',))

            recent = Counter()
            for row in cursor.fetchall():
                kw = row['keyword']
                if kw:
                    recent[kw] += 1

            # S/A 등급 키워드 우선
            cursor.execute("""
                SELECT keyword, grade, search_volume
                FROM keyword_insights
                WHERE grade IN ('S', 'A')
                AND created_at >= datetime('now', '-7 days')
            """)

            high_grade = {row['keyword'] for row in cursor.fetchall()}

            for keyword, count in recent.most_common(20):
                growth = 3.0 if keyword in high_grade else 1.5
                trending.append(TrendingKeyword(
                    keyword=keyword,
                    current_count=count,
                    avg_count=count / growth,
                    growth_rate=growth,
                    trend_level='RISING' if keyword in high_grade else 'STABLE',
                    sources=['pathfinder']
                ))

        except sqlite3.OperationalError as e:
            logger.warning(f"keyword_insights 테이블 조회 실패: {e}")

        return trending

    def _extract_keywords(self, text: str) -> List[str]:
        """텍스트에서 키워드 추출"""
        if not text:
            return []

        # 한글 키워드 추출 (2~10자)
        keywords = re.findall(r'[가-힣]{2,10}', text)

        # 불용어 제거
        stopwords = {'그리고', '하지만', '그래서', '그러나', '이것', '저것', '있는', '없는', '하는'}
        return [kw for kw in keywords if kw not in stopwords]

    def _classify_trend(self, growth_rate: float) -> str:
        """성장률에 따른 트렌드 레벨 분류"""
        if growth_rate >= self.TREND_THRESHOLDS['HOT']:
            return 'HOT'
        elif growth_rate >= self.TREND_THRESHOLDS['RISING']:
            return 'RISING'
        elif growth_rate >= self.TREND_THRESHOLDS['STABLE']:
            return 'STABLE'
        else:
            return 'DECLINING'

    def get_trend_summary(self, hours: int = 24) -> Dict[str, Any]:
        """트렌드 요약 정보"""
        trending = self.detect_rising_keywords(hours=hours, limit=100)

        summary = {
            'period_hours': hours,
            'total_trending': len(trending),
            'by_level': {
                'HOT': [],
                'RISING': [],
                'STABLE': [],
                'DECLINING': []
            },
            'top_keywords': []
        }

        for item in trending:
            summary['by_level'][item.trend_level].append(item.keyword)

        # 상위 10개
        summary['top_keywords'] = [
            {
                'keyword': t.keyword,
                'growth_rate': round(t.growth_rate, 2),
                'level': t.trend_level,
                'count': t.current_count
            }
            for t in trending[:10]
        ]

        return summary

    def get_hot_keywords(self, limit: int = 10) -> List[Dict[str, Any]]:
        """HOT 트렌드 키워드만 반환"""
        trending = self.detect_rising_keywords(hours=24, limit=50)

        hot = [t for t in trending if t.trend_level == 'HOT']

        return [
            {
                'keyword': t.keyword,
                'growth_rate': round(t.growth_rate, 2),
                'current_count': t.current_count,
                'sources': t.sources
            }
            for t in hot[:limit]
        ]


# 싱글톤 인스턴스
_detector_instance = None


def get_trend_detector(db_path: str = None) -> TrendDetector:
    """TrendDetector 싱글톤 인스턴스 반환"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = TrendDetector(db_path)
    return _detector_instance
