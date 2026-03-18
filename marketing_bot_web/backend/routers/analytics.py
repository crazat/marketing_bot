"""
[Phase G/H/I/J/K/L] 마케팅 분석 API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- G-1: 전환 어트리뷰션 체인
- H-3: 리드 응답 골든타임
- I-1: 경쟁사 움직임 감지
- J-2: AI 주간 브리핑
- K-1: 키워드 라이프사이클
- L-1: 채널별 ROI 대시보드
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import sqlite3
import json
import logging

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

def get_db_path():
    """DatabaseManager에서 db_path 가져오기"""
    return DatabaseManager().db_path
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [G-1] 전환 어트리뷰션 체인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/attribution-chain")
async def get_attribution_chain(days: int = 30) -> Dict[str, Any]:
    """
    전환 어트리뷰션 체인 분석
    키워드 → 바이럴 → 리드 → 전환의 전체 경로 추적
    """
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()

        # [Phase 2 최적화] N+1 서브쿼리 → LEFT JOIN으로 변경
        cursor.execute("""
            SELECT
                lc.keyword,
                COUNT(DISTINCT lc.id) as conversions,
                SUM(lc.revenue) as total_revenue,
                AVG(lc.days_to_conversion) as avg_days_to_conversion,
                AVG(lc.response_time_hours) as avg_response_time,
                COUNT(DISTINCT vt.id) as viral_count,
                COUNT(DISTINCT m.id) as lead_count
            FROM lead_conversions lc
            LEFT JOIN viral_targets vt ON vt.matched_keyword = lc.keyword
            LEFT JOIN mentions m ON m.keyword = lc.keyword
            WHERE lc.conversion_date >= date('now', ?)
            AND lc.keyword IS NOT NULL AND lc.keyword != ''
            GROUP BY lc.keyword
            ORDER BY total_revenue DESC
            LIMIT 20
        """, (f'-{days} days',))

        keyword_attribution = []
        for row in cursor.fetchall():
            keyword = row[0]
            conversion_count = row[1]
            total_revenue = row[2] or 0
            viral_count = row[5] or 0
            lead_count = row[6] or 0

            keyword_attribution.append({
                'keyword': keyword,
                'viral_count': viral_count,
                'lead_count': lead_count,
                'conversion_count': conversion_count,
                'total_revenue': total_revenue,
                'avg_days_to_conversion': round(row[3] or 0, 1),
                'avg_response_time_hours': round(row[4] or 0, 1),
                'conversion_rate': round((conversion_count / lead_count * 100) if lead_count > 0 else 0, 1),
                'revenue_per_viral': round(total_revenue / viral_count, 0) if viral_count > 0 else 0,
                'revenue_per_lead': round(total_revenue / lead_count, 0) if lead_count > 0 else 0,
            })

        # 전체 퍼널 통계
        cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE grade IN ('S', 'A')")
        total_keywords = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM viral_targets WHERE comment_status = 'completed'")
        total_virals = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM mentions WHERE status != 'rejected'")
        total_leads = cursor.fetchone()[0]

        # [Phase 2 보안] f-string → 파라미터 바인딩으로 변경
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(revenue), 0)
            FROM lead_conversions
            WHERE conversion_date >= date('now', ?)
        """, (f'-{days} days',))
        conv_row = cursor.fetchone()
        total_conversions = conv_row[0]
        total_revenue = conv_row[1]

        return {
            'period_days': days,
            'funnel_overview': {
                'total_keywords': total_keywords,
                'total_virals': total_virals,
                'total_leads': total_leads,
                'total_conversions': total_conversions,
                'total_revenue': total_revenue,
                'viral_to_lead_rate': round((total_leads / total_virals * 100) if total_virals > 0 else 0, 1),
                'lead_to_conversion_rate': round((total_conversions / total_leads * 100) if total_leads > 0 else 0, 1),
            },
            'by_keyword': keyword_attribution,
        }

    except Exception as e:
        logger.error(f"attribution-chain 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [H-3] 리드 응답 골든타임
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/response-golden-time")
async def get_response_golden_time(days: int = 90) -> Dict[str, Any]:
    """
    응답 시간별 전환율 분석 (골든타임 도출)
    """
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()

        # 응답 시간 구간별 전환율 분석
        time_brackets = [
            ('1시간 이내', 0, 1),
            ('1-6시간', 1, 6),
            ('6-24시간', 6, 24),
            ('24-48시간', 24, 48),
            ('48시간 이후', 48, 9999),
        ]

        bracket_stats = []
        for label, min_hours, max_hours in time_brackets:
            # 해당 시간대 리드 수 (응답한 리드)
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
                FROM mentions
                WHERE response_time_hours IS NOT NULL
                AND response_time_hours > ? AND response_time_hours <= ?
                AND scraped_at >= date('now', ?)
            """, (min_hours, max_hours, f'-{days} days'))

            row = cursor.fetchone()
            total = row[0] or 0
            converted = row[1] or 0

            bracket_stats.append({
                'bracket': label,
                'min_hours': min_hours,
                'max_hours': max_hours if max_hours < 9999 else None,
                'total_leads': total,
                'converted': converted,
                'conversion_rate': round((converted / total * 100) if total > 0 else 0, 1),
            })

        # Hot 리드 골든타임 분석 (score >= 80 = hot)
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted,
                AVG(response_time_hours) as avg_response_time
            FROM mentions
            WHERE score >= 80
            AND response_time_hours IS NOT NULL
            AND response_time_hours <= 1
            AND scraped_at >= date('now', ?)
        """, (f'-{days} days',))
        hot_1h = cursor.fetchone()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM mentions
            WHERE score >= 80
            AND (response_time_hours IS NULL OR response_time_hours > 48)
            AND scraped_at >= date('now', ?)
        """, (f'-{days} days',))
        hot_48h_plus = cursor.fetchone()

        # 현재 미응답 Hot 리드 (New/pending 또는 미설정 상태)
        cursor.execute("""
            SELECT COUNT(*) FROM mentions
            WHERE score >= 80
            AND (status IN ('New', 'pending') OR status IS NULL)
            AND first_response_at IS NULL
        """)
        pending_hot = cursor.fetchone()[0]

        # 48시간 초과 미응답 Hot 리드
        cursor.execute("""
            SELECT COUNT(*) FROM mentions
            WHERE score >= 80
            AND (status IN ('New', 'pending') OR status IS NULL)
            AND first_response_at IS NULL
            AND scraped_at <= datetime('now', '-48 hours')
        """)
        urgent_hot = cursor.fetchone()[0]

        # 인사이트 생성
        insights = []
        if bracket_stats[0]['conversion_rate'] > 0 and bracket_stats[4]['conversion_rate'] > 0:
            ratio = bracket_stats[0]['conversion_rate'] / bracket_stats[4]['conversion_rate']
            if ratio > 1:
                insights.append(f"1시간 이내 응답 시 전환율이 48시간 이후 대비 {ratio:.1f}배 높습니다")

        if urgent_hot > 0:
            insights.append(f"⚠️ {urgent_hot}건의 Hot 리드가 48시간 초과 미응답 상태입니다")

        if pending_hot > 0:
            insights.append(f"현재 응답 대기 중인 Hot 리드: {pending_hot}건")

        return {
            'period_days': days,
            'by_response_time': bracket_stats,
            'hot_lead_analysis': {
                'within_1hour': {
                    'total': hot_1h[0] or 0,
                    'converted': hot_1h[1] or 0,
                    'conversion_rate': round(((hot_1h[1] or 0) / (hot_1h[0] or 1)) * 100, 1),
                },
                'after_48hours': {
                    'total': hot_48h_plus[0] or 0,
                    'converted': hot_48h_plus[1] or 0,
                    'conversion_rate': round(((hot_48h_plus[1] or 0) / (hot_48h_plus[0] or 1)) * 100, 1),
                },
            },
            'alerts': {
                'pending_hot_leads': pending_hot,
                'urgent_hot_leads': urgent_hot,
            },
            'insights': insights,
        }

    except Exception as e:
        logger.error(f"response-golden-time 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


class RecordResponseRequest(BaseModel):
    lead_id: int
    response_content: Optional[str] = None


@router.post("/record-response")
async def record_lead_response(data: RecordResponseRequest) -> Dict[str, Any]:
    """
    리드 첫 응답 시간 기록 (골든타임 분석용)
    """
    conn = None
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        # mentions 테이블에서 리드 찾기
        cursor.execute("""
            SELECT scraped_at, first_response_at FROM mentions WHERE id = ?
        """, (data.lead_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="리드를 찾을 수 없습니다")

        scraped_at = row[0]
        existing_response = row[1]

        if existing_response:
            return {
                "success": True,
                "message": "이미 응답 시간이 기록되어 있습니다",
                "first_response_at": existing_response
            }

        # 응답 시간 계산
        if scraped_at:
            try:
                scraped_dt = datetime.fromisoformat(scraped_at.replace('Z', '+00:00'))
                now_dt = datetime.now()
                response_time_hours = (now_dt - scraped_dt).total_seconds() / 3600
            except (ValueError, TypeError):
                response_time_hours = None  # 날짜 파싱 실패
        else:
            response_time_hours = None

        # 업데이트
        cursor.execute("""
            UPDATE mentions
            SET first_response_at = ?,
                response_time_hours = ?,
                status = CASE WHEN status = 'pending' THEN 'contacted' ELSE status END
            WHERE id = ?
        """, (now, response_time_hours, data.lead_id))

        conn.commit()

        return {
            "success": True,
            "message": "응답 시간이 기록되었습니다",
            "first_response_at": now,
            "response_time_hours": round(response_time_hours, 2) if response_time_hours else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"record-response 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [I-1] 경쟁사 움직임 감지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/competitor-movements")
async def get_competitor_movements(days: int = 7) -> Dict[str, Any]:
    """
    경쟁사 순위 변동, 활동량 변화, 신규 키워드 진입 감지
    """
    conn = None
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        movements = []
        alerts = []

        # 경쟁사 순위 급상승 감지
        cursor.execute("""
            SELECT
                cr1.competitor_name,
                cr1.keyword,
                cr1.rank as current_rank,
                cr2.rank as previous_rank,
                (cr2.rank - cr1.rank) as rank_change
            FROM competitor_rankings cr1
            LEFT JOIN competitor_rankings cr2
                ON cr1.competitor_name = cr2.competitor_name
                AND cr1.keyword = cr2.keyword
                AND cr2.scanned_date = date(cr1.scanned_date, '-7 days')
            WHERE cr1.scanned_date >= date('now', '-1 day')
            AND cr2.rank IS NOT NULL
            AND (cr2.rank - cr1.rank) >= 3
            ORDER BY rank_change DESC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            movement = {
                'type': 'rank_surge',
                'competitor': row[0],
                'keyword': row[1],
                'current_rank': row[2],
                'previous_rank': row[3],
                'change': row[4],
                'severity': 'high' if row[4] >= 5 else 'medium',
            }
            movements.append(movement)

            if row[4] >= 5:
                alerts.append({
                    'type': 'competitor_surge',
                    'message': f"🔴 {row[0]}이(가) '{row[1]}' 키워드에서 {row[3]}위→{row[2]}위로 급상승",
                    'severity': 'high',
                })

        # 신규 키워드 진입 감지
        cursor.execute("""
            SELECT
                competitor_name,
                keyword,
                rank
            FROM competitor_rankings
            WHERE scanned_date >= date('now', '-7 days')
            AND competitor_name || keyword NOT IN (
                SELECT competitor_name || keyword
                FROM competitor_rankings
                WHERE scanned_date < date('now', '-7 days')
            )
            ORDER BY rank ASC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            movements.append({
                'type': 'new_entry',
                'competitor': row[0],
                'keyword': row[1],
                'rank': row[2],
                'severity': 'medium' if row[2] <= 10 else 'low',
            })

            if row[2] <= 10:
                alerts.append({
                    'type': 'new_entry',
                    'message': f"🟡 {row[0]}이(가) '{row[1]}' 키워드에 {row[2]}위로 신규 진입",
                    'severity': 'medium',
                })

        # 경쟁사 활동량 변화 (리뷰 수 기반)
        cursor.execute("""
            SELECT
                competitor_name,
                COUNT(*) as recent_reviews,
                (SELECT COUNT(*) FROM competitor_reviews cr2
                 WHERE cr2.competitor_name = cr.competitor_name
                 AND cr2.scraped_at < date('now', '-7 days')
                 AND cr2.scraped_at >= date('now', '-14 days')) as previous_reviews
            FROM competitor_reviews cr
            WHERE scraped_at >= date('now', '-7 days')
            GROUP BY competitor_name
            HAVING recent_reviews > previous_reviews * 1.5
            ORDER BY recent_reviews DESC
            LIMIT 5
        """)

        for row in cursor.fetchall():
            recent = row[1]
            previous = row[2] or 1
            increase_pct = round((recent - previous) / previous * 100, 0)

            movements.append({
                'type': 'activity_surge',
                'competitor': row[0],
                'recent_reviews': recent,
                'previous_reviews': previous,
                'increase_percent': increase_pct,
                'severity': 'medium',
            })

        # 활동 감소 감지 (기회 포착)
        cursor.execute("""
            SELECT
                competitor_name,
                MAX(scraped_at) as last_activity
            FROM competitor_reviews
            GROUP BY competitor_name
            HAVING last_activity < date('now', '-14 days')
            LIMIT 5
        """)

        opportunities = []
        for row in cursor.fetchall():
            opportunities.append({
                'competitor': row[0],
                'last_activity': row[1],
                'message': f"🟢 {row[0]}의 활동이 2주 이상 감소됨 - 점유율 확대 기회",
            })

        return {
            'period_days': days,
            'movements': movements,
            'alerts': alerts,
            'opportunities': opportunities,
            'summary': {
                'total_movements': len(movements),
                'high_severity': len([m for m in movements if m.get('severity') == 'high']),
                'medium_severity': len([m for m in movements if m.get('severity') == 'medium']),
                'opportunities_count': len(opportunities),
            }
        }

    except Exception as e:
        logger.error(f"competitor-movements 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [J-2] AI 주간 브리핑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/weekly-briefing")
async def get_weekly_briefing() -> Dict[str, Any]:
    """
    크로스 모듈 데이터 기반 AI 주간 브리핑
    """
    conn = None
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # [Phase 2 보안] f-string → 직접 SQL로 변경

        # 이번주 리드 통계 (score >= 80 = hot, score >= 60 = warm)
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) as hot,
                SUM(CASE WHEN score >= 60 AND score < 80 THEN 1 ELSE 0 END) as warm,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM mentions
            WHERE scraped_at >= date('now', '-7 days')
        """)
        this_week_leads = cursor.fetchone()

        # 지난주 리드 통계
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM mentions
            WHERE scraped_at >= date('now', '-14 days') AND scraped_at < date('now', '-7 days')
        """)
        last_week_leads = cursor.fetchone()

        # 이번주 전환 및 매출
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(revenue), 0)
            FROM lead_conversions
            WHERE conversion_date >= date('now', '-7 days')
        """)
        this_week_conv = cursor.fetchone()

        # 지난주 전환 및 매출
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(revenue), 0)
            FROM lead_conversions
            WHERE conversion_date >= date('now', '-14 days') AND conversion_date < date('now', '-7 days')
        """)
        last_week_conv = cursor.fetchone()

        # 키워드 성과 (이번주 전환 기준)
        cursor.execute("""
            SELECT keyword, COUNT(*) as conv, SUM(revenue) as rev
            FROM lead_conversions
            WHERE conversion_date >= date('now', '-7 days')
            AND keyword IS NOT NULL AND keyword != ''
            GROUP BY keyword
            ORDER BY rev DESC
            LIMIT 5
        """)
        top_keywords = [{'keyword': r[0], 'conversions': r[1], 'revenue': r[2]} for r in cursor.fetchall()]

        # 순위 변동 키워드 (checked_at 사용)
        cursor.execute("""
            SELECT
                rh1.keyword,
                rh1.rank as current_rank,
                rh2.rank as previous_rank,
                (rh2.rank - rh1.rank) as change
            FROM rank_history rh1
            LEFT JOIN rank_history rh2
                ON rh1.keyword = rh2.keyword
                AND rh2.checked_at = (
                    SELECT MAX(checked_at) FROM rank_history
                    WHERE keyword = rh1.keyword
                    AND checked_at < rh1.checked_at
                )
            WHERE rh1.checked_at = (
                SELECT MAX(checked_at) FROM rank_history WHERE keyword = rh1.keyword
            )
            AND rh2.rank IS NOT NULL
            ORDER BY change DESC
            LIMIT 5
        """)
        rank_changes = []
        for row in cursor.fetchall():
            rank_changes.append({
                'keyword': row[0],
                'current_rank': row[1],
                'previous_rank': row[2],
                'change': row[3],
                'direction': 'up' if row[3] > 0 else 'down' if row[3] < 0 else 'stable'
            })

        # 미응답 Hot 리드 (score >= 80 = hot)
        cursor.execute("""
            SELECT COUNT(*) FROM mentions
            WHERE score >= 80
            AND (status IN ('New', 'pending') OR status IS NULL)
            AND first_response_at IS NULL
        """)
        pending_hot = cursor.fetchone()[0]

        # 경쟁사 알림
        cursor.execute("""
            SELECT COUNT(*) FROM competitor_rankings
            WHERE scanned_date >= date('now', '-7 days')
            AND rank <= 3
        """)
        competitor_top3 = cursor.fetchone()[0]

        # 변화율 계산
        lead_change = ((this_week_leads[0] - last_week_leads[0]) / last_week_leads[0] * 100) if last_week_leads[0] > 0 else 0
        conv_change = ((this_week_conv[0] - last_week_conv[0]) / last_week_conv[0] * 100) if last_week_conv[0] > 0 else 0
        conversion_rate = (this_week_conv[0] / this_week_leads[0] * 100) if this_week_leads[0] > 0 else 0

        # 인사이트 생성
        insights = []
        if lead_change > 20:
            insights.append(f"📈 신규 리드가 전주 대비 {lead_change:.0f}% 증가했습니다")
        elif lead_change < -20:
            insights.append(f"📉 신규 리드가 전주 대비 {abs(lead_change):.0f}% 감소했습니다")

        if top_keywords:
            insights.append(f"🎯 '{top_keywords[0]['keyword']}' 키워드의 전환 성과가 가장 좋습니다")

        if pending_hot > 0:
            insights.append(f"⚠️ {pending_hot}건의 Hot 리드가 응답 대기 중입니다")

        # 권장 액션
        actions = []
        if pending_hot > 0:
            actions.append({
                'priority': 'high',
                'action': f'Hot 리드 {pending_hot}건 응답',
                'link': '/leads?grade=hot&status=pending'
            })

        rank_down = [r for r in rank_changes if r['change'] < -3]
        if rank_down:
            actions.append({
                'priority': 'high',
                'action': f"'{rank_down[0]['keyword']}' 순위 방어 콘텐츠 필요",
                'link': f"/battle?keyword={rank_down[0]['keyword']}"
            })

        rank_up = [r for r in rank_changes if r['change'] > 0]
        if rank_up:
            actions.append({
                'priority': 'medium',
                'action': f"'{rank_up[0]['keyword']}' 모멘텀 유지 바이럴 추가",
                'link': f"/viral?keyword={rank_up[0]['keyword']}"
            })

        return {
            'generated_at': datetime.now().isoformat(),
            'period': {
                'start': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'end': datetime.now().strftime('%Y-%m-%d'),
            },
            'key_metrics': {
                'new_leads': {
                    'value': this_week_leads[0],
                    'change_percent': round(lead_change, 1),
                    'hot_count': this_week_leads[1],
                    'warm_count': this_week_leads[2],
                },
                'conversions': {
                    'value': this_week_conv[0],
                    'change_percent': round(conv_change, 1),
                    'conversion_rate': round(conversion_rate, 1),
                },
                'revenue': {
                    'value': this_week_conv[1],
                    'change_percent': round(((this_week_conv[1] - last_week_conv[1]) / last_week_conv[1] * 100) if last_week_conv[1] > 0 else 0, 1),
                },
            },
            'top_performing_keywords': top_keywords,
            'rank_changes': rank_changes,
            'alerts': {
                'pending_hot_leads': pending_hot,
                'competitor_in_top3': competitor_top3,
            },
            'insights': insights,
            'recommended_actions': actions,
        }

    except Exception as e:
        logger.error(f"weekly-briefing 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [K-1] 키워드 라이프사이클
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/keyword-lifecycle")
async def get_keyword_lifecycle(
    status: Optional[str] = None,
    # [UX 개선] offset/limit 방식으로 통일 (page/page_size도 하위 호환성 유지)
    limit: int = Query(default=50, ge=1, le=200, description="조회할 항목 수"),
    offset: int = Query(default=0, ge=0, description="건너뛸 항목 수"),
    # 하위 호환성을 위해 page 파라미터도 지원 (deprecated)
    page: Optional[int] = Query(default=None, ge=1, description="페이지 번호 (deprecated, offset 사용 권장)"),
    page_size: Optional[int] = Query(default=None, ge=1, le=200, description="페이지 크기 (deprecated, limit 사용 권장)"),
) -> Dict[str, Any]:
    """
    키워드 라이프사이클 현황 조회
    상태: discovered → tracking → active → maintaining → archived

    페이지네이션:
    - 권장: offset (기본 0), limit (기본 50, 최대 200)
    - deprecated: page, page_size (하위 호환성 유지)
    """
    # [UX 개선] page 파라미터가 전달된 경우 offset으로 변환 (하위 호환성)
    if page is not None:
        actual_page_size = page_size if page_size else limit
        offset = (page - 1) * actual_page_size
        limit = actual_page_size
    elif page_size is not None:
        limit = page_size

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_lifecycle'")
        if not cursor.fetchone():
            conn.close()
            return {
                'keywords': [],
                'by_status': {},
                'summary': {'total': 0, 'by_status': {}},
                'recent_transitions': [],
                'total': 0,
                'offset': offset,
                'limit': limit,
                'total_pages': 0,
            }

        # 상태별 필터 (파라미터 바인딩으로 SQL 인젝션 방지)
        valid_statuses = ['discovered', 'tracking', 'active', 'maintaining', 'archived']

        if status and status in valid_statuses:
            cursor.execute("""
                SELECT
                    keyword, status, grade,
                    total_leads, total_conversions, total_revenue,
                    current_rank, best_rank, weeks_in_top10,
                    discovered_at, tracking_started_at, active_started_at,
                    last_viral_at, last_lead_at, last_conversion_at,
                    updated_at
                FROM keyword_lifecycle
                WHERE status = ?
                ORDER BY
                    CASE status
                        WHEN 'active' THEN 1
                        WHEN 'tracking' THEN 2
                        WHEN 'maintaining' THEN 3
                        WHEN 'discovered' THEN 4
                        ELSE 5
                    END,
                    total_revenue DESC
                LIMIT ? OFFSET ?
            """, (status, limit, offset))
        else:
            cursor.execute("""
                SELECT
                    keyword, status, grade,
                    total_leads, total_conversions, total_revenue,
                    current_rank, best_rank, weeks_in_top10,
                    discovered_at, tracking_started_at, active_started_at,
                    last_viral_at, last_lead_at, last_conversion_at,
                    updated_at
                FROM keyword_lifecycle
                ORDER BY
                    CASE status
                        WHEN 'active' THEN 1
                        WHEN 'tracking' THEN 2
                        WHEN 'maintaining' THEN 3
                        WHEN 'discovered' THEN 4
                        ELSE 5
                    END,
                    total_revenue DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

        keywords = []
        for row in cursor.fetchall():
            keywords.append({
                'keyword': row[0],
                'status': row[1],
                'grade': row[2],
                'total_leads': row[3],
                'total_conversions': row[4],
                'total_revenue': row[5],
                'current_rank': row[6],
                'best_rank': row[7],
                'weeks_in_top10': row[8],
                'discovered_at': row[9],
                'tracking_started_at': row[10],
                'active_started_at': row[11],
                'last_viral_at': row[12],
                'last_lead_at': row[13],
                'last_conversion_at': row[14],
                'updated_at': row[15],
            })

        # 상태별 집계 + 전체 개수 조회
        cursor.execute("""
            SELECT status, COUNT(*) FROM keyword_lifecycle GROUP BY status
        """)
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        # 현재 필터에 맞는 전체 개수
        if status and status in valid_statuses:
            total_count = by_status.get(status, 0)
        else:
            total_count = sum(by_status.values())

        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0

        # 최근 상태 전환 이력 (keyword_lifecycle_history 테이블이 없으면 빈 배열)
        recent_transitions = []
        try:
            cursor.execute("""
                SELECT keyword, from_status, to_status, changed_at, reason
                FROM keyword_lifecycle_history
                ORDER BY changed_at DESC
                LIMIT 10
            """)
            for row in cursor.fetchall():
                recent_transitions.append({
                    'keyword': row[0],
                    'from_status': row[1],
                    'to_status': row[2],
                    'changed_at': row[3],
                    'reason': row[4],
                })
        except sqlite3.OperationalError:
            pass  # 테이블이 없으면 무시

        conn.close()

        return {
            'keywords': keywords,
            'by_status': by_status,
            'summary': {
                'total': total_count,
                'by_status': by_status,
            },
            'recent_transitions': recent_transitions,
            'total': total_count,
            # [UX 개선] offset/limit 기반 응답 (하위 호환성을 위해 page도 포함)
            'offset': offset,
            'limit': limit,
            'page': (offset // limit) + 1 if limit > 0 else 1,  # 하위 호환성
            'page_size': limit,  # 하위 호환성
            'total_pages': total_pages,
        }

    except Exception as e:
        logger.error(f"keyword-lifecycle 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class KeywordStatusUpdate(BaseModel):
    keyword: str
    new_status: str
    reason: Optional[str] = None


@router.post("/keyword-lifecycle/update-status")
async def update_keyword_lifecycle_status(data: KeywordStatusUpdate) -> Dict[str, Any]:
    """
    키워드 라이프사이클 상태 수동 변경
    """
    valid_statuses = ['discovered', 'tracking', 'active', 'maintaining', 'archived']
    if data.new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태: {data.new_status}")

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 현재 상태 조회
        cursor.execute("SELECT status FROM keyword_lifecycle WHERE keyword = ?", (data.keyword,))
        row = cursor.fetchone()

        if not row:
            # 새 키워드 등록
            cursor.execute("""
                INSERT INTO keyword_lifecycle (keyword, status)
                VALUES (?, ?)
            """, (data.keyword, data.new_status))
            from_status = None
        else:
            from_status = row[0]
            # 상태별 타임스탬프 컬럼 매핑 (화이트리스트)
            timestamp_columns = {
                'discovered': 'discovered_at',
                'tracking': 'tracking_started_at',
                'active': 'active_started_at',
                'maintaining': 'maintaining_started_at',
                'archived': 'archived_at',
            }
            timestamp_col = timestamp_columns.get(data.new_status, 'updated_at')

            # 동적 컬럼명은 화이트리스트로 검증됨
            cursor.execute(f"""
                UPDATE keyword_lifecycle
                SET status = ?,
                    {timestamp_col} = datetime('now'),
                    updated_at = datetime('now')
                WHERE keyword = ?
            """, (data.new_status, data.keyword))

        # 히스토리 기록
        cursor.execute("""
            INSERT INTO keyword_lifecycle_history (keyword, from_status, to_status, reason)
            VALUES (?, ?, ?, ?)
        """, (data.keyword, from_status, data.new_status, data.reason))

        conn.commit()
        conn.close()

        return {
            'success': True,
            'keyword': data.keyword,
            'from_status': from_status,
            'to_status': data.new_status,
        }

    except Exception as e:
        logger.error(f"update-keyword-status 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keyword-lifecycle/auto-transition")
async def run_keyword_auto_transition() -> Dict[str, Any]:
    """
    키워드 상태 자동 전환 실행
    규칙 기반으로 상태를 자동으로 업데이트
    """
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        transitions = []

        # 1. discovered → tracking: A급 이상 키워드가 순위 추적에 등록되면
        cursor.execute("""
            SELECT ki.keyword, ki.grade
            FROM keyword_insights ki
            LEFT JOIN keyword_lifecycle kl ON ki.keyword = kl.keyword
            WHERE ki.grade IN ('S', 'A')
            AND (kl.status IS NULL OR kl.status = 'discovered')
            AND ki.keyword IN (SELECT keyword FROM rank_history)
        """)
        for row in cursor.fetchall():
            keyword, grade = row
            cursor.execute("""
                INSERT OR REPLACE INTO keyword_lifecycle
                (keyword, status, grade, tracking_started_at, updated_at)
                VALUES (?, 'tracking', ?, datetime('now'), datetime('now'))
            """, (keyword, grade))
            transitions.append({'keyword': keyword, 'to': 'tracking', 'reason': 'A급 이상 + 순위 추적 등록'})

        # 2. tracking → active: 순위 10위 이내 + 2주 유지
        cursor.execute("""
            SELECT kl.keyword
            FROM keyword_lifecycle kl
            WHERE kl.status = 'tracking'
            AND kl.keyword IN (
                SELECT keyword FROM rank_history
                WHERE rank <= 10
                AND scanned_at >= date('now', '-14 days')
                GROUP BY keyword
                HAVING COUNT(DISTINCT date(scanned_at)) >= 7
            )
        """)
        for row in cursor.fetchall():
            keyword = row[0]
            cursor.execute("""
                UPDATE keyword_lifecycle
                SET status = 'active', active_started_at = datetime('now'), updated_at = datetime('now')
                WHERE keyword = ?
            """, (keyword,))
            transitions.append({'keyword': keyword, 'to': 'active', 'reason': '10위 이내 2주 유지'})

        # 3. active → maintaining: 순위 3위 이내 + 4주 유지
        cursor.execute("""
            SELECT kl.keyword
            FROM keyword_lifecycle kl
            WHERE kl.status = 'active'
            AND kl.keyword IN (
                SELECT keyword FROM rank_history
                WHERE rank <= 3
                AND scanned_at >= date('now', '-28 days')
                GROUP BY keyword
                HAVING COUNT(DISTINCT date(scanned_at)) >= 14
            )
        """)
        for row in cursor.fetchall():
            keyword = row[0]
            cursor.execute("""
                UPDATE keyword_lifecycle
                SET status = 'maintaining', maintaining_started_at = datetime('now'), updated_at = datetime('now')
                WHERE keyword = ?
            """, (keyword,))
            transitions.append({'keyword': keyword, 'to': 'maintaining', 'reason': '3위 이내 4주 유지'})

        # 4. maintaining → archived: 전환율 5% 미만 3개월 지속
        cursor.execute("""
            SELECT kl.keyword, kl.total_leads, kl.total_conversions
            FROM keyword_lifecycle kl
            WHERE kl.status = 'maintaining'
            AND kl.maintaining_started_at <= date('now', '-90 days')
            AND (kl.total_conversions * 1.0 / NULLIF(kl.total_leads, 0)) < 0.05
        """)
        for row in cursor.fetchall():
            keyword = row[0]
            cursor.execute("""
                UPDATE keyword_lifecycle
                SET status = 'archived', archived_at = datetime('now'), updated_at = datetime('now')
                WHERE keyword = ?
            """, (keyword,))
            transitions.append({'keyword': keyword, 'to': 'archived', 'reason': '전환율 5% 미만 3개월'})

        # 히스토리 기록
        for t in transitions:
            cursor.execute("""
                INSERT INTO keyword_lifecycle_history (keyword, from_status, to_status, reason)
                SELECT status, ?, ? FROM keyword_lifecycle WHERE keyword = ?
            """, (t['to'], t['reason'], t['keyword']))

        conn.commit()
        conn.close()

        return {
            'success': True,
            'transitions': transitions,
            'total_transitions': len(transitions),
        }

    except Exception as e:
        logger.error(f"auto-transition 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [L-1] 채널별 ROI 대시보드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/channel-roi")
async def get_channel_roi(days: int = 30) -> Dict[str, Any]:
    """
    채널별 ROI 분석
    플랫폼별/키워드별 투입 대비 수익 분석
    """
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # [Phase 2 보안/최적화] f-string → 파라미터 바인딩, 서브쿼리 → LEFT JOIN
        days_param = f'-{days} days'
        cursor.execute("""
            SELECT
                m.source as platform,
                COUNT(DISTINCT m.id) as total_leads,
                SUM(CASE WHEN m.status = 'converted' THEN 1 ELSE 0 END) as converted,
                COALESCE(SUM(lc.revenue), 0) as revenue,
                COUNT(DISTINCT vt.id) as viral_count
            FROM mentions m
            LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
            LEFT JOIN viral_targets vt ON vt.platform = m.source AND vt.discovered_at >= date('now', ?)
            WHERE m.scraped_at >= date('now', ?)
            GROUP BY m.source
            ORDER BY revenue DESC
        """, (days_param, days_param))

        by_platform = []
        for row in cursor.fetchall():
            platform = row[0] or 'unknown'
            leads = row[1]
            converted = row[2]
            revenue = row[3]
            viral_count = row[4] or 0

            by_platform.append({
                'platform': platform,
                'viral_count': viral_count,
                'lead_count': leads,
                'converted': converted,
                'revenue': revenue,
                'conversion_rate': round((converted / leads * 100) if leads > 0 else 0, 1),
                'revenue_per_viral': round(revenue / viral_count, 0) if viral_count > 0 else 0,
                'revenue_per_lead': round(revenue / leads, 0) if leads > 0 else 0,
            })

        # [Phase 2 보안/최적화] N+1 서브쿼리 → LEFT JOIN으로 변경
        cursor.execute("""
            SELECT
                lc.keyword,
                COUNT(DISTINCT lc.id) as conversions,
                SUM(lc.revenue) as revenue,
                AVG(lc.days_to_conversion) as avg_days,
                COUNT(DISTINCT m.id) as lead_count,
                COUNT(DISTINCT vt.id) as viral_count
            FROM lead_conversions lc
            LEFT JOIN mentions m ON m.keyword = lc.keyword
            LEFT JOIN viral_targets vt ON vt.matched_keyword = lc.keyword
            WHERE lc.conversion_date >= date('now', ?)
            AND lc.keyword IS NOT NULL AND lc.keyword != ''
            GROUP BY lc.keyword
            ORDER BY revenue DESC
            LIMIT 15
        """, (days_param,))

        by_keyword = []
        for row in cursor.fetchall():
            keyword = row[0]
            conversions = row[1]
            revenue = row[2]
            leads = row[4] or 0
            virals = row[5] or 0

            by_keyword.append({
                'keyword': keyword,
                'viral_count': virals,
                'lead_count': leads,
                'conversions': conversions,
                'revenue': revenue,
                'conversion_rate': round((conversions / leads * 100) if leads > 0 else 0, 1),
                'avg_days_to_conversion': round(row[3] or 0, 1),
                'revenue_per_viral': round(revenue / virals, 0) if virals > 0 else 0,
            })

        # [Phase 2 보안] 전체 요약 - 파라미터 바인딩 사용
        cursor.execute("""
            SELECT
                COUNT(DISTINCT id) as total_conversions,
                COALESCE(SUM(revenue), 0) as total_revenue
            FROM lead_conversions
            WHERE conversion_date >= date('now', ?)
        """, (days_param,))
        overall = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE discovered_at >= date('now', ?)
        """, (days_param,))
        total_virals = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM mentions
            WHERE scraped_at >= date('now', ?)
        """, (days_param,))
        total_leads = cursor.fetchone()[0]

        conn.close()

        # 인사이트 생성
        insights = []
        if by_platform:
            best_platform = max(by_platform, key=lambda x: x['conversion_rate'])
            if best_platform['conversion_rate'] > 0:
                insights.append(f"🏆 {best_platform['platform']} 플랫폼의 전환율이 가장 높습니다 ({best_platform['conversion_rate']}%)")

        if by_keyword:
            best_keyword = max(by_keyword, key=lambda x: x['revenue'])
            insights.append(f"💰 '{best_keyword['keyword']}' 키워드가 가장 높은 매출을 기록했습니다")

            low_performers = [k for k in by_keyword if k['conversion_rate'] < 5 and k['lead_count'] > 5]
            if low_performers:
                insights.append(f"⚠️ {len(low_performers)}개 키워드의 전환율이 5% 미만입니다 - 전략 재검토 필요")

        return {
            'period_days': days,
            'overview': {
                'total_virals': total_virals,
                'total_leads': total_leads,
                'total_conversions': overall[0],
                'total_revenue': overall[1],
                'overall_conversion_rate': round((overall[0] / total_leads * 100) if total_leads > 0 else 0, 1),
                'revenue_per_conversion': round(overall[1] / overall[0], 0) if overall[0] > 0 else 0,
            },
            'by_platform': by_platform,
            'by_keyword': by_keyword,
            'insights': insights,
        }

    except Exception as e:
        logger.error(f"channel-roi 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [M-1] 마케팅 건강 점수 (Marketing Health Score)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/marketing-health-score")
async def get_marketing_health_score(days: int = 30) -> Dict[str, Any]:
    """
    마케팅 건강 점수 - 활동 기반 종합 점수

    구성:
    - 순위 점수 (30%): 키워드별 순위 성과
    - 바이럴 활동 점수 (25%): 바이럴 콘텐츠 활동량
    - 리드 생성 점수 (25%): 리드 발굴 성과
    - 경쟁 우위 점수 (20%): 경쟁사 대비 위치
    """
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        scores = {}
        details = {}

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. 순위 점수 (30%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 최근 순위 데이터 (checked_at 기반)
        cursor.execute("""
            SELECT keyword, rank, checked_at
            FROM rank_history
            WHERE checked_at >= date('now', ?)
            AND rank IS NOT NULL AND rank > 0
        """, (f'-{days} days',))
        rank_data = cursor.fetchall()

        if rank_data:
            # 순위 점수 계산 (1위=100점, 10위=50점, 20위 이상=0점)
            rank_scores = []
            for keyword, rank, _ in rank_data:
                if rank <= 3:
                    rank_scores.append(100)
                elif rank <= 5:
                    rank_scores.append(80)
                elif rank <= 10:
                    rank_scores.append(60)
                elif rank <= 20:
                    rank_scores.append(30)
                else:
                    rank_scores.append(10)

            avg_rank_score = sum(rank_scores) / len(rank_scores)

            # Top 10 내 키워드 비율 보너스
            top10_count = len([r for _, r, _ in rank_data if r <= 10])
            total_keywords = len(set([k for k, _, _ in rank_data]))
            top10_ratio = top10_count / total_keywords if total_keywords > 0 else 0

            scores['ranking'] = min(100, avg_rank_score + (top10_ratio * 20))
            details['ranking'] = {
                'avg_rank_score': round(avg_rank_score, 1),
                'top10_keywords': top10_count,
                'total_keywords': total_keywords,
                'top10_ratio': round(top10_ratio * 100, 1),
            }
        else:
            scores['ranking'] = 0
            details['ranking'] = {'message': '순위 데이터 없음'}

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. 바이럴 활동 점수 (25%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 이번 기간 바이럴
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE discovered_at >= date('now', ?)
        """, (f'-{days} days',))
        current_virals = cursor.fetchone()[0]

        # 이전 기간 바이럴 (비교용)
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE discovered_at >= date('now', ?)
            AND discovered_at < date('now', ?)
        """, (f'-{days * 2} days', f'-{days} days'))
        prev_virals = cursor.fetchone()[0]

        # 완료된 바이럴 비율
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE discovered_at >= date('now', ?)
            AND comment_status = 'completed'
        """, (f'-{days} days',))
        completed_virals = cursor.fetchone()[0]

        # 점수 계산: 활동량 + 완료율 + 성장률
        if current_virals > 0:
            completion_rate = completed_virals / current_virals
            # 기준: 주당 10건 = 만점 (days/7 * 10)
            expected_virals = (days / 7) * 10
            activity_score = min(100, (current_virals / expected_virals) * 100)

            # 성장률 보너스 (최대 20점)
            growth_bonus = 0
            if prev_virals > 0:
                growth_rate = (current_virals - prev_virals) / prev_virals
                growth_bonus = min(20, max(-10, growth_rate * 20))

            scores['viral'] = min(100, activity_score * 0.6 + completion_rate * 100 * 0.3 + growth_bonus)
            details['viral'] = {
                'current_period': current_virals,
                'previous_period': prev_virals,
                'completed': completed_virals,
                'completion_rate': round(completion_rate * 100, 1),
                'growth_rate': round(((current_virals - prev_virals) / prev_virals * 100) if prev_virals > 0 else 0, 1),
            }
        else:
            scores['viral'] = 0
            details['viral'] = {'message': '바이럴 활동 없음'}

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. 리드 생성 점수 (25%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 이번 기간 리드
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) as hot,
                SUM(CASE WHEN score >= 60 AND score < 80 THEN 1 ELSE 0 END) as warm,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM mentions
            WHERE scraped_at >= date('now', ?)
        """, (f'-{days} days',))
        lead_row = cursor.fetchone()

        total_leads = lead_row[0] or 0
        hot_leads = lead_row[1] or 0
        warm_leads = lead_row[2] or 0
        converted_leads = lead_row[3] or 0

        # 이전 기간 리드
        cursor.execute("""
            SELECT COUNT(*) FROM mentions
            WHERE scraped_at >= date('now', ?)
            AND scraped_at < date('now', ?)
        """, (f'-{days * 2} days', f'-{days} days'))
        prev_leads = cursor.fetchone()[0]

        if total_leads > 0:
            # 점수: 리드 수량 + 품질(Hot/Warm 비율) + 전환율
            # 기준: 주당 5건 = 만점
            expected_leads = (days / 7) * 5
            quantity_score = min(100, (total_leads / expected_leads) * 100)

            quality_ratio = (hot_leads * 2 + warm_leads) / total_leads  # Hot은 2배 가중치
            quality_score = min(100, quality_ratio * 50)

            conversion_rate = converted_leads / total_leads
            conversion_score = conversion_rate * 100 * 2  # 전환율 1% = 2점

            scores['leads'] = min(100, quantity_score * 0.4 + quality_score * 0.3 + conversion_score * 0.3)
            details['leads'] = {
                'total': total_leads,
                'hot': hot_leads,
                'warm': warm_leads,
                'converted': converted_leads,
                'conversion_rate': round(conversion_rate * 100, 2),
                'previous_period': prev_leads,
            }
        else:
            scores['leads'] = 0
            details['leads'] = {'message': '리드 데이터 없음'}

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4. 경쟁 우위 점수 (20%)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 경쟁사 대비 순위 비교
        cursor.execute("""
            SELECT
                cr.keyword,
                rh.rank as our_rank,
                MIN(cr.rank) as best_competitor_rank
            FROM competitor_rankings cr
            LEFT JOIN rank_history rh ON cr.keyword = rh.keyword
            WHERE cr.scanned_date >= date('now', '-7 days')
            AND rh.checked_at = (SELECT MAX(checked_at) FROM rank_history WHERE keyword = cr.keyword)
            GROUP BY cr.keyword
        """)
        competition_data = cursor.fetchall()

        if competition_data:
            wins = 0
            ties = 0
            losses = 0

            for keyword, our_rank, competitor_rank in competition_data:
                if our_rank and competitor_rank:
                    if our_rank < competitor_rank:
                        wins += 1
                    elif our_rank == competitor_rank:
                        ties += 1
                    else:
                        losses += 1

            total_comparisons = wins + ties + losses
            if total_comparisons > 0:
                win_rate = wins / total_comparisons
                scores['competition'] = win_rate * 100
                details['competition'] = {
                    'wins': wins,
                    'ties': ties,
                    'losses': losses,
                    'win_rate': round(win_rate * 100, 1),
                }
            else:
                scores['competition'] = 50  # 비교 불가 시 중립
                details['competition'] = {'message': '비교 데이터 부족'}
        else:
            scores['competition'] = 50
            details['competition'] = {'message': '경쟁 데이터 없음'}

        conn.close()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 종합 점수 계산
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        weights = {
            'ranking': 0.30,
            'viral': 0.25,
            'leads': 0.25,
            'competition': 0.20,
        }

        total_score = sum(scores[k] * weights[k] for k in weights)

        # 등급 결정
        if total_score >= 80:
            grade = 'A'
            grade_label = '매우 건강'
            grade_color = 'green'
        elif total_score >= 60:
            grade = 'B'
            grade_label = '양호'
            grade_color = 'blue'
        elif total_score >= 40:
            grade = 'C'
            grade_label = '개선 필요'
            grade_color = 'yellow'
        else:
            grade = 'D'
            grade_label = '주의 필요'
            grade_color = 'red'

        # 개선 제안 생성
        recommendations = []
        if scores['ranking'] < 50:
            recommendations.append({
                'area': 'ranking',
                'priority': 'high' if scores['ranking'] < 30 else 'medium',
                'message': '순위 향상을 위한 콘텐츠 강화가 필요합니다',
            })
        if scores['viral'] < 50:
            recommendations.append({
                'area': 'viral',
                'priority': 'high' if scores['viral'] < 30 else 'medium',
                'message': '바이럴 활동량을 늘려주세요',
            })
        if scores['leads'] < 50:
            recommendations.append({
                'area': 'leads',
                'priority': 'medium',
                'message': '리드 발굴 및 응답율 개선이 필요합니다',
            })
        if scores['competition'] < 50:
            recommendations.append({
                'area': 'competition',
                'priority': 'medium',
                'message': '경쟁사 대비 순위 방어 전략이 필요합니다',
            })

        return {
            'period_days': days,
            'calculated_at': datetime.now().isoformat(),
            'total_score': round(total_score, 1),
            'grade': grade,
            'grade_label': grade_label,
            'grade_color': grade_color,
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'weights': weights,
            'details': details,
            'recommendations': recommendations,
        }

    except Exception as e:
        logger.error(f"marketing-health-score 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [M-2] Before/After 비교 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/before-after-comparison")
async def get_before_after_comparison(
    before_start: Optional[str] = None,
    before_end: Optional[str] = None,
    after_start: Optional[str] = None,
    after_end: Optional[str] = None
) -> Dict[str, Any]:
    """
    Before/After 비교 분석

    두 기간의 마케팅 지표를 비교하여 변화량 분석
    기본값: 이번달 vs 지난달
    """
    try:
        # 기본 기간 설정 (이번달 vs 지난달)
        today = datetime.now()
        if not after_end:
            after_end = today.strftime('%Y-%m-%d')
        if not after_start:
            after_start = (today.replace(day=1)).strftime('%Y-%m-%d')
        if not before_end:
            before_end = (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
        if not before_start:
            before_start = (today.replace(day=1) - timedelta(days=30)).strftime('%Y-%m-%d')

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        def get_period_metrics(start_date: str, end_date: str) -> Dict[str, Any]:
            """특정 기간의 지표 조회"""
            metrics = {}

            # 리드 수
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
                FROM mentions
                WHERE scraped_at >= ? AND scraped_at <= ?
            """, (start_date, end_date))
            row = cursor.fetchone()
            metrics['leads'] = {
                'total': row[0] or 0,
                'hot': row[1] or 0,
                'converted': row[2] or 0,
            }

            # 바이럴 수
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN comment_status = 'completed' THEN 1 ELSE 0 END) as completed
                FROM viral_targets
                WHERE discovered_at >= ? AND discovered_at <= ?
            """, (start_date, end_date))
            row = cursor.fetchone()
            metrics['virals'] = {
                'total': row[0] or 0,
                'completed': row[1] or 0,
            }

            # 평균 순위 (상위 10개 키워드)
            cursor.execute("""
                SELECT AVG(rank) FROM (
                    SELECT keyword, MIN(rank) as rank
                    FROM rank_history
                    WHERE checked_at >= ? AND checked_at <= ?
                    AND rank > 0
                    GROUP BY keyword
                    ORDER BY rank ASC
                    LIMIT 10
                )
            """, (start_date, end_date))
            avg_rank = cursor.fetchone()[0]
            metrics['avg_rank'] = round(avg_rank, 1) if avg_rank else None

            # Top 10 키워드 수
            cursor.execute("""
                SELECT COUNT(DISTINCT keyword) FROM rank_history
                WHERE checked_at >= ? AND checked_at <= ?
                AND rank <= 10
            """, (start_date, end_date))
            metrics['top10_keywords'] = cursor.fetchone()[0] or 0

            # 전환 및 매출
            cursor.execute("""
                SELECT COUNT(*), COALESCE(SUM(revenue), 0)
                FROM lead_conversions
                WHERE conversion_date >= ? AND conversion_date <= ?
            """, (start_date, end_date))
            row = cursor.fetchone()
            metrics['conversions'] = row[0] or 0
            metrics['revenue'] = row[1] or 0

            return metrics

        before_metrics = get_period_metrics(before_start, before_end)
        after_metrics = get_period_metrics(after_start, after_end)

        conn.close()

        def calc_change(before_val, after_val):
            """변화량 계산"""
            if before_val == 0:
                return {'value': after_val - before_val, 'percent': None, 'direction': 'up' if after_val > 0 else 'stable'}

            change_pct = ((after_val - before_val) / before_val) * 100
            return {
                'value': after_val - before_val,
                'percent': round(change_pct, 1),
                'direction': 'up' if change_pct > 0 else 'down' if change_pct < 0 else 'stable'
            }

        # 변화량 계산
        changes = {
            'leads_total': calc_change(before_metrics['leads']['total'], after_metrics['leads']['total']),
            'leads_hot': calc_change(before_metrics['leads']['hot'], after_metrics['leads']['hot']),
            'leads_converted': calc_change(before_metrics['leads']['converted'], after_metrics['leads']['converted']),
            'virals_total': calc_change(before_metrics['virals']['total'], after_metrics['virals']['total']),
            'virals_completed': calc_change(before_metrics['virals']['completed'], after_metrics['virals']['completed']),
            'top10_keywords': calc_change(before_metrics['top10_keywords'], after_metrics['top10_keywords']),
            'conversions': calc_change(before_metrics['conversions'], after_metrics['conversions']),
            'revenue': calc_change(before_metrics['revenue'], after_metrics['revenue']),
        }

        # 순위는 낮을수록 좋음 (역방향)
        if before_metrics['avg_rank'] and after_metrics['avg_rank']:
            rank_change = before_metrics['avg_rank'] - after_metrics['avg_rank']  # 역방향
            changes['avg_rank'] = {
                'value': round(rank_change, 1),
                'percent': round((rank_change / before_metrics['avg_rank']) * 100, 1) if before_metrics['avg_rank'] else None,
                'direction': 'up' if rank_change > 0 else 'down' if rank_change < 0 else 'stable'
            }
        else:
            changes['avg_rank'] = {'value': 0, 'percent': None, 'direction': 'stable'}

        # 종합 평가
        positive_changes = sum(1 for k, v in changes.items() if v['direction'] == 'up')
        negative_changes = sum(1 for k, v in changes.items() if v['direction'] == 'down')

        if positive_changes > negative_changes * 2:
            overall = 'significant_improvement'
            overall_label = '큰 폭 개선'
        elif positive_changes > negative_changes:
            overall = 'improvement'
            overall_label = '개선'
        elif positive_changes == negative_changes:
            overall = 'stable'
            overall_label = '유지'
        elif negative_changes > positive_changes * 2:
            overall = 'significant_decline'
            overall_label = '큰 폭 하락'
        else:
            overall = 'decline'
            overall_label = '하락'

        # 주요 인사이트 생성
        insights = []
        if changes['leads_total']['direction'] == 'up' and changes['leads_total'].get('percent', 0):
            insights.append(f"리드 수가 {changes['leads_total']['percent']}% 증가했습니다")
        if changes['revenue']['direction'] == 'up' and changes['revenue']['value'] > 0:
            insights.append(f"매출이 {changes['revenue']['value']:,}원 증가했습니다")
        if changes['avg_rank']['direction'] == 'up' and changes['avg_rank']['value'] > 0:
            insights.append(f"평균 순위가 {changes['avg_rank']['value']}계단 상승했습니다")
        if changes['virals_total']['direction'] == 'down':
            insights.append("바이럴 활동량이 감소했습니다 - 활동 강화 권장")

        return {
            'periods': {
                'before': {'start': before_start, 'end': before_end},
                'after': {'start': after_start, 'end': after_end},
            },
            'before': before_metrics,
            'after': after_metrics,
            'changes': changes,
            'overall': overall,
            'overall_label': overall_label,
            'positive_changes': positive_changes,
            'negative_changes': negative_changes,
            'insights': insights,
        }

    except Exception as e:
        logger.error(f"before-after-comparison 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [M-3] 유입 경로 기록
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ReferralSourceRequest(BaseModel):
    conversion_id: Optional[int] = None
    lead_id: Optional[int] = None
    source: str  # how_did_you_find_us 응답
    source_detail: Optional[str] = None  # 상세 정보 (예: 특정 검색어)


@router.post("/record-referral-source")
async def record_referral_source(data: ReferralSourceRequest) -> Dict[str, Any]:
    """
    유입 경로 기록

    "어떻게 오셨어요?" 질문 응답을 기록
    """
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # referral_sources 테이블 확인/생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referral_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversion_id INTEGER,
                lead_id INTEGER,
                source TEXT NOT NULL,
                source_detail TEXT,
                recorded_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (conversion_id) REFERENCES lead_conversions(id),
                FOREIGN KEY (lead_id) REFERENCES mentions(id)
            )
        """)

        # 기록 저장
        cursor.execute("""
            INSERT INTO referral_sources (conversion_id, lead_id, source, source_detail)
            VALUES (?, ?, ?, ?)
        """, (data.conversion_id, data.lead_id, data.source, data.source_detail))

        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            'success': True,
            'id': new_id,
            'message': '유입 경로가 기록되었습니다',
        }

    except Exception as e:
        logger.error(f"record-referral-source 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/referral-sources")
async def get_referral_sources(days: int = 90) -> Dict[str, Any]:
    """
    유입 경로 통계
    """
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referral_sources'")
        if not cursor.fetchone():
            conn.close()
            return {
                'by_source': [],
                'total': 0,
                'message': '유입 경로 데이터가 없습니다. 환자 방문 시 "어떻게 오셨어요?" 응답을 기록해주세요.',
            }

        # 유입 경로별 집계
        cursor.execute("""
            SELECT
                source,
                COUNT(*) as count,
                GROUP_CONCAT(DISTINCT source_detail) as details
            FROM referral_sources
            WHERE recorded_at >= date('now', ?)
            GROUP BY source
            ORDER BY count DESC
        """, (f'-{days} days',))

        by_source = []
        total = 0
        for row in cursor.fetchall():
            count = row[1]
            total += count
            by_source.append({
                'source': row[0],
                'count': count,
                'details': row[2].split(',') if row[2] else [],
            })

        # 비율 계산
        for item in by_source:
            item['percentage'] = round((item['count'] / total * 100) if total > 0 else 0, 1)

        conn.close()

        # 인사이트 생성
        insights = []
        if by_source:
            top_source = by_source[0]
            insights.append(f"가장 많은 유입 경로: {top_source['source']} ({top_source['percentage']}%)")

            # 온라인 vs 오프라인 분석
            online_sources = ['네이버 검색', '인스타그램', '블로그', '지인 SNS', '온라인 광고']
            offline_sources = ['지인 소개', '간판', '전단지', '근처 거주']

            online_count = sum(s['count'] for s in by_source if s['source'] in online_sources)
            offline_count = sum(s['count'] for s in by_source if s['source'] in offline_sources)

            if online_count + offline_count > 0:
                online_ratio = online_count / (online_count + offline_count) * 100
                insights.append(f"온라인 유입 비율: {round(online_ratio, 1)}%")

        return {
            'period_days': days,
            'by_source': by_source,
            'total': total,
            'insights': insights,
            'suggested_sources': [
                '네이버 검색',
                '인스타그램',
                '블로그',
                '지인 소개',
                '지인 SNS',
                '간판',
                '근처 거주',
                '온라인 광고',
                '전단지',
                '기타',
            ],
        }

    except Exception as e:
        logger.error(f"referral-sources 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
