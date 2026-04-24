"""
전환 추적 서비스 (CPA/ROI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V3-3] 마케팅 채널별 환자 전환 추적 및 ROI 측정

채널: 네이버 플레이스, 네이버 블로그, 인스타그램, 지인 소개, 카카오톡, 전단지, 기타
지표: CPA (환자당 획득 비용), ROAS (광고비 대비 매출), 채널별 전환율

데이터 입력: 접수 시 "어떻게 알게 되셨나요?" 응답 기반
"""

import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 표준 채널 목록
CHANNELS = [
    "naver_place",      # 네이버 플레이스/검색
    "naver_blog",       # 네이버 블로그
    "instagram",        # 인스타그램
    "kakao",            # 카카오톡 채널
    "referral",         # 지인 소개
    "flyer",            # 전단지/인쇄물
    "signage",          # 간판/지나가다가
    "naver_ad",         # 네이버 검색 광고
    "other",            # 기타
]


def add_patient_visit(
    db_path: str,
    source_channel: str,
    patient_type: str = "new",
    treatment_type: str = None,
    revenue: int = 0,
    coupon_code: str = None,
    date: str = None,
) -> Optional[int]:
    """환자 방문 기록 추가"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO patient_attribution
            (date, source_channel, patient_type, treatment_type, revenue, coupon_code)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            date or datetime.now().strftime("%Y-%m-%d"),
            source_channel, patient_type, treatment_type, revenue, coupon_code,
        ))

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        logger.error(f"방문 기록 추가 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


def set_monthly_spend(
    db_path: str,
    month: str,
    channel: str,
    spend: int,
) -> bool:
    """월별 채널 마케팅 비용 설정"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            INSERT INTO marketing_spend (month, channel, spend)
            VALUES (?, ?, ?)
            ON CONFLICT(month, channel) DO UPDATE SET spend = excluded.spend
        """, (month, channel, spend))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"비용 설정 실패: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_channel_roi(db_path: str, month: str = None) -> Dict[str, Any]:
    """
    채널별 ROI 계산

    Returns:
        {channels: [{channel, patients, revenue, spend, cpa, roas}], totals}
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if not month:
            month = datetime.now().strftime("%Y-%m")

        # 채널별 환자/매출
        cursor.execute("""
            SELECT
                source_channel,
                COUNT(*) as patients,
                SUM(CASE WHEN patient_type='new' THEN 1 ELSE 0 END) as new_patients,
                SUM(revenue) as total_revenue
            FROM patient_attribution
            WHERE date LIKE ? || '%'
            GROUP BY source_channel
            ORDER BY patients DESC
        """, (month,))

        attribution = {r["source_channel"]: dict(r) for r in cursor.fetchall()}

        # 채널별 비용
        cursor.execute("""
            SELECT channel, spend FROM marketing_spend WHERE month = ?
        """, (month,))

        spends = {r["channel"]: r["spend"] for r in cursor.fetchall()}

        # ROI 계산
        channels = []
        total_patients = 0
        total_revenue = 0
        total_spend = 0

        for ch in CHANNELS:
            attr = attribution.get(ch, {})
            patients = attr.get("patients", 0)
            new_patients = attr.get("new_patients", 0)
            revenue = attr.get("total_revenue", 0)
            spend = spends.get(ch, 0)

            cpa = round(spend / new_patients) if new_patients > 0 and spend > 0 else 0
            roas = round(revenue / spend, 2) if spend > 0 else 0

            total_patients += patients
            total_revenue += revenue
            total_spend += spend

            if patients > 0 or spend > 0:
                channels.append({
                    "channel": ch,
                    "patients": patients,
                    "new_patients": new_patients,
                    "revenue": revenue,
                    "spend": spend,
                    "cpa": cpa,
                    "roas": roas,
                })

        return {
            "month": month,
            "channels": channels,
            "totals": {
                "patients": total_patients,
                "revenue": total_revenue,
                "spend": total_spend,
                "overall_cpa": round(total_spend / max(total_patients, 1)),
                "overall_roas": round(total_revenue / max(total_spend, 1), 2) if total_spend > 0 else 0,
            },
        }

    except Exception as e:
        logger.error(f"ROI 계산 실패: {e}")
        return {"error": str(e)}
    finally:
        if conn:
            conn.close()
