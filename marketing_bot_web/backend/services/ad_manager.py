"""
통합 광고 관리 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-3] 네이버 검색광고 + GFA API 통합 모니터링

API 문서:
- 검색광고: https://naver.github.io/searchad-apidoc/
- GFA: https://naver-ad-api.github.io/openapi-guide/

필요한 설정 (config/config.json):
{
    "naver_ads": {
        "customer_id": "...",
        "api_key": "...",
        "api_secret": "...",
        "access_license": "..."  // 검색광고 API 라이선스
    }
}
"""

import os
import sys
import json
import time
import hmac
import hashlib
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class NaverAdsClient:
    """네이버 검색광고 API 클라이언트"""

    BASE_URL = "https://api.naver.com"

    def __init__(self, customer_id: str, api_key: str, api_secret: str):
        self.customer_id = customer_id
        self.api_key = api_key
        self.api_secret = api_secret

    def _generate_signature(self, timestamp: str, method: str, path: str) -> str:
        """HMAC-SHA256 서명 생성"""
        sign_str = f"{timestamp}.{method}.{path}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_headers(self, method: str, path: str) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        timestamp = str(int(time.time() * 1000))
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.api_key,
            "X-Customer": self.customer_id,
            "X-Signature": self._generate_signature(timestamp, method, path),
        }

    async def get_campaign_stats(self, date_range: int = 7) -> Dict[str, Any]:
        """
        캠페인 성과 통계 조회

        Returns:
            캠페인별 노출, 클릭, 비용, 전환 데이터
        """
        try:
            import httpx

            path = "/stats"
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=date_range)).strftime("%Y-%m-%d")

            headers = self._get_headers("GET", path)
            params = {
                "datePreset": "CUSTOM",
                "startDate": start_date,
                "endDate": end_date,
                "fields": '["impCnt","clkCnt","salesAmt","convCnt","ctr","cpc","cpa"]',
                "timeRange": '{"since":"' + start_date + '","until":"' + end_date + '"}',
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"광고 API 오류: {response.status_code} - {response.text}")
                    return {"error": f"API 오류: {response.status_code}"}

        except ImportError:
            return {"error": "httpx 패키지 필요"}
        except Exception as e:
            logger.error(f"광고 통계 조회 실패: {e}")
            return {"error": str(e)}

    async def get_keyword_tool(self, keywords: List[str]) -> Dict[str, Any]:
        """
        키워드 도구 - 검색량/경쟁강도 조회

        이미 naver_ad_keyword_collector.py에서 수집 중이므로
        여기서는 온디맨드 조회용
        """
        try:
            import httpx

            path = "/keywordstool"
            headers = self._get_headers("GET", path)
            params = {
                "hintKeywords": ",".join(keywords),
                "showDetail": "1",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json()
                return {"error": f"API 오류: {response.status_code}"}

        except Exception as e:
            return {"error": str(e)}


class AdPerformanceTracker:
    """광고 성과 추적기"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_ad_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        기존 naver_ad_keyword_data 테이블에서 광고 성과 요약

        naver_ad_keyword_collector.py가 이미 수집한 데이터 활용
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # naver_ad_keyword_data에서 광고 경쟁 데이터 조회
            cursor.execute("""
                SELECT
                    keyword,
                    monthly_pc_cnt,
                    monthly_mobile_cnt,
                    competition_level,
                    avg_bid,
                    min_bid,
                    collected_at
                FROM naver_ad_keyword_data
                WHERE collected_at >= datetime('now', ? || ' days')
                ORDER BY monthly_mobile_cnt DESC
                LIMIT 50
            """, (f"-{days}",))

            keywords = [dict(row) for row in cursor.fetchall()]

            # 광고 경쟁 추적 데이터
            cursor.execute("""
                SELECT
                    keyword,
                    ad_count,
                    avg_ad_position,
                    tracked_at
                FROM ad_competition_tracking
                WHERE tracked_at >= datetime('now', ? || ' days')
                ORDER BY tracked_at DESC
                LIMIT 50
            """, (f"-{days}",))

            competition = [dict(row) for row in cursor.fetchall()]

            # 요약 통계
            total_keywords = len(keywords)
            high_competition = sum(1 for k in keywords if k.get('competition_level') == 'HIGH')
            avg_bid = (
                sum(k['avg_bid'] for k in keywords if k.get('avg_bid'))
                / max(sum(1 for k in keywords if k.get('avg_bid')), 1)
            )

            return {
                "keywords": keywords,
                "competition": competition,
                "summary": {
                    "total_tracked": total_keywords,
                    "high_competition": high_competition,
                    "avg_bid": round(avg_bid),
                    "period_days": days,
                },
            }

        except Exception as e:
            logger.error(f"광고 요약 조회 실패: {e}")
            return {"keywords": [], "competition": [], "summary": {}, "error": str(e)}
        finally:
            if conn:
                conn.close()

    def calculate_roas_estimate(self, days: int = 30) -> Dict[str, Any]:
        """
        ROAS 추정 (리드 전환 기반)

        실제 광고비 데이터가 없으므로, 키워드 입찰가 × 예상 클릭수로 추정
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 키워드별 입찰가와 검색량
            cursor.execute("""
                SELECT
                    keyword,
                    avg_bid,
                    monthly_mobile_cnt,
                    monthly_pc_cnt
                FROM naver_ad_keyword_data
                WHERE avg_bid > 0
                ORDER BY monthly_mobile_cnt DESC
                LIMIT 20
            """)

            keywords = [dict(row) for row in cursor.fetchall()]

            # 리드 전환 수 (같은 기간)
            cursor.execute("""
                SELECT COUNT(*) as lead_count
                FROM viral_targets
                WHERE created_at >= datetime('now', ? || ' days')
                  AND status IN ('contacted', 'converted')
            """, (f"-{days}",))
            lead_count = cursor.fetchone()['lead_count']

            # 추정 ROAS
            estimated_monthly_spend = sum(
                k['avg_bid'] * (k['monthly_mobile_cnt'] + k['monthly_pc_cnt']) * 0.03  # CTR 3% 가정
                for k in keywords
            )

            return {
                "estimated_monthly_spend": round(estimated_monthly_spend),
                "lead_count": lead_count,
                "cost_per_lead": round(estimated_monthly_spend / max(lead_count, 1)),
                "top_keywords_by_cost": sorted(
                    keywords,
                    key=lambda k: k['avg_bid'] * (k.get('monthly_mobile_cnt', 0) + k.get('monthly_pc_cnt', 0)),
                    reverse=True
                )[:10],
                "note": "추정치입니다. 실제 광고비 연동 시 정확한 ROAS 계산 가능.",
            }

        except Exception as e:
            return {"error": str(e)}
        finally:
            if conn:
                conn.close()
