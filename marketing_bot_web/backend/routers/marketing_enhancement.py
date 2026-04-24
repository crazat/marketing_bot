"""
Marketing Enhancement API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

마케팅 강화 기능 API:
1. 골든타임 분석
2. 리드 품질 스코어링
3. 콘텐츠 성과 분석
4. 캠페인 관리
5. A/B 테스트
6. 경쟁사 바이럴 레이더
7. 스마트 알림
8. 통합 ROI 대시보드
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'

# 상위 디렉토리 추가
import sys
sys.path.insert(0, str(PROJECT_ROOT.parent))
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


def get_db_connection():
    """DB 연결 획득"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ============================================
# 1. 골든타임 분석 API
# ============================================

@router.get("/golden-time/stats")
async def get_golden_time_stats(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    days: int = Query(30, ge=7, le=90)
) -> Dict[str, Any]:
    """
    골든타임 통계 조회
    - 시간대별 반응률 히트맵 데이터
    - 플랫폼/카테고리별 최적 시간
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 기간 설정
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # 시간대별 집계 쿼리
        query = """
            SELECT
                COALESCE(posted_hour, strftime('%H', posted_at)) as hour,
                COALESCE(posted_day_of_week, strftime('%w', posted_at)) as day_of_week,
                COUNT(*) as total_comments,
                SUM(COALESCE(likes, 0)) as total_likes,
                SUM(COALESCE(replies, 0)) as total_replies,
                SUM(COALESCE(clicks, 0)) as total_clicks,
                SUM(CASE WHEN led_to_conversion = 1 THEN 1 ELSE 0 END) as conversions,
                CASE WHEN COUNT(*) > 0
                    THEN CAST(SUM(COALESCE(likes, 0) + COALESCE(replies, 0)) AS REAL) / COUNT(*)
                    ELSE 0
                END as avg_engagement
            FROM posted_comments
            WHERE posted_at >= ?
        """
        params = [start_date]

        if platform:
            query += " AND platform = ?"
            params.append(platform)

        query += " GROUP BY hour, day_of_week ORDER BY hour, day_of_week"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 히트맵 데이터 구성
        heatmap_data = []
        hourly_stats = {}
        daily_stats = {}

        for row in rows:
            hour = int(row['hour']) if row['hour'] else 0
            day = int(row['day_of_week']) if row['day_of_week'] else 0

            heatmap_data.append({
                'hour': hour,
                'day_of_week': day,
                'total_comments': row['total_comments'],
                'total_likes': row['total_likes'],
                'total_replies': row['total_replies'],
                'avg_engagement': round(row['avg_engagement'], 2),
                'conversions': row['conversions']
            })

            # 시간대별 집계
            if hour not in hourly_stats:
                hourly_stats[hour] = {'comments': 0, 'engagement': 0, 'conversions': 0}
            hourly_stats[hour]['comments'] += row['total_comments']
            hourly_stats[hour]['engagement'] += row['total_likes'] + row['total_replies']
            hourly_stats[hour]['conversions'] += row['conversions']

            # 요일별 집계
            if day not in daily_stats:
                daily_stats[day] = {'comments': 0, 'engagement': 0, 'conversions': 0}
            daily_stats[day]['comments'] += row['total_comments']
            daily_stats[day]['engagement'] += row['total_likes'] + row['total_replies']
            daily_stats[day]['conversions'] += row['conversions']

        # 최적 시간 계산
        best_hours = sorted(
            hourly_stats.items(),
            key=lambda x: x[1]['engagement'] / max(x[1]['comments'], 1),
            reverse=True
        )[:3]

        best_days = sorted(
            daily_stats.items(),
            key=lambda x: x[1]['engagement'] / max(x[1]['comments'], 1),
            reverse=True
        )[:3]

        day_names = ['일', '월', '화', '수', '목', '금', '토']

        conn.close()

        return {
            'period_days': days,
            'platform': platform,
            'category': category,
            'heatmap': heatmap_data,
            'hourly_stats': [
                {'hour': h, **s} for h, s in sorted(hourly_stats.items())
            ],
            'daily_stats': [
                {'day': d, 'day_name': day_names[d], **s} for d, s in sorted(daily_stats.items())
            ],
            'recommendations': {
                'best_hours': [{'hour': h, 'engagement_rate': s['engagement'] / max(s['comments'], 1)} for h, s in best_hours],
                'best_days': [{'day': d, 'day_name': day_names[d], 'engagement_rate': s['engagement'] / max(s['comments'], 1)} for d, s in best_days],
            }
        }

    except Exception as e:
        logger.error(f"골든타임 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 2. 리드 품질 스코어링 API
# ============================================

@router.get("/lead-quality/stats")
async def get_lead_quality_stats(
    dimension: str = Query("platform", pattern="^(platform|category|content_type)$"),
    days: int = Query(30, ge=7, le=90)
) -> Dict[str, Any]:
    """
    리드 품질 통계 조회
    - 플랫폼/카테고리별 전환율
    - 리드 품질 점수
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # 차원별 통계 쿼리
        if dimension == "platform":
            group_col = "vt.platform"
        elif dimension == "category":
            group_col = "vt.category"
        else:
            group_col = "vt.content_type"

        # viral_targets 기준 통계
        query = f"""
            SELECT
                {group_col} as dimension_value,
                COUNT(DISTINCT vt.id) as total_targets,
                COUNT(DISTINCT pc.id) as total_comments,
                SUM(COALESCE(pc.likes, 0) + COALESCE(pc.replies, 0)) as total_engagements,
                SUM(CASE WHEN pc.led_to_contact = 1 THEN 1 ELSE 0 END) as total_leads,
                SUM(CASE WHEN pc.led_to_conversion = 1 THEN 1 ELSE 0 END) as total_conversions
            FROM viral_targets vt
            LEFT JOIN posted_comments pc ON vt.id = pc.target_id
            WHERE vt.discovered_at >= ?
            GROUP BY {group_col}
            HAVING total_targets > 0
            ORDER BY total_conversions DESC
        """

        cursor.execute(query, [start_date])
        rows = cursor.fetchall()

        stats = []
        for row in rows:
            dimension_value = row['dimension_value'] or 'unknown'
            total_targets = row['total_targets'] or 0
            total_comments = row['total_comments'] or 0
            total_leads = row['total_leads'] or 0
            total_conversions = row['total_conversions'] or 0

            # 전환율 계산
            comment_rate = (total_comments / total_targets * 100) if total_targets > 0 else 0
            lead_rate = (total_leads / total_comments * 100) if total_comments > 0 else 0
            conversion_rate = (total_conversions / total_leads * 100) if total_leads > 0 else 0

            # 품질 점수 (가중 평균)
            quality_score = (comment_rate * 0.2 + lead_rate * 0.3 + conversion_rate * 0.5)

            stats.append({
                'dimension': dimension,
                'value': dimension_value,
                'total_targets': total_targets,
                'total_comments': total_comments,
                'total_leads': total_leads,
                'total_conversions': total_conversions,
                'comment_rate': round(comment_rate, 1),
                'lead_rate': round(lead_rate, 1),
                'conversion_rate': round(conversion_rate, 1),
                'quality_score': round(quality_score, 1)
            })

        # 정렬 (품질 점수 기준)
        stats.sort(key=lambda x: x['quality_score'], reverse=True)

        conn.close()

        return {
            'period_days': days,
            'dimension': dimension,
            'stats': stats,
            'summary': {
                'total_targets': sum(s['total_targets'] for s in stats),
                'total_comments': sum(s['total_comments'] for s in stats),
                'total_leads': sum(s['total_leads'] for s in stats),
                'total_conversions': sum(s['total_conversions'] for s in stats),
                'best_performing': stats[0] if stats else None
            }
        }

    except Exception as e:
        logger.error(f"리드 품질 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 3. 콘텐츠 성과 분석 API
# ============================================

@router.get("/content-performance/stats")
async def get_content_performance_stats(
    days: int = Query(30, ge=7, le=90)
) -> Dict[str, Any]:
    """
    콘텐츠 유형별 성과 분석
    - 질문형, 고민형, 후기형, 정보형 분류
    - 플랫폼 × 유형 교차 분석
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # 콘텐츠 유형별 통계
        query = """
            SELECT
                COALESCE(vt.content_type, 'unknown') as content_type,
                vt.platform,
                COUNT(DISTINCT vt.id) as total_targets,
                COUNT(DISTINCT pc.id) as total_comments,
                SUM(COALESCE(pc.likes, 0)) as total_likes,
                SUM(COALESCE(pc.replies, 0)) as total_replies,
                SUM(CASE WHEN pc.led_to_contact = 1 THEN 1 ELSE 0 END) as leads,
                SUM(CASE WHEN pc.led_to_conversion = 1 THEN 1 ELSE 0 END) as conversions
            FROM viral_targets vt
            LEFT JOIN posted_comments pc ON vt.id = pc.target_id
            WHERE vt.discovered_at >= ?
            GROUP BY content_type, vt.platform
            ORDER BY conversions DESC
        """

        cursor.execute(query, [start_date])
        rows = cursor.fetchall()

        # 매트릭스 데이터 구성
        matrix = {}
        type_stats = {}
        platform_stats = {}

        for row in rows:
            content_type = row['content_type']
            platform = row['platform'] or 'unknown'
            total_comments = row['total_comments'] or 0
            conversions = row['conversions'] or 0

            conversion_rate = (conversions / total_comments * 100) if total_comments > 0 else 0

            # 매트릭스 데이터
            key = f"{content_type}_{platform}"
            matrix[key] = {
                'content_type': content_type,
                'platform': platform,
                'targets': row['total_targets'],
                'comments': total_comments,
                'conversions': conversions,
                'conversion_rate': round(conversion_rate, 1)
            }

            # 유형별 집계
            if content_type not in type_stats:
                type_stats[content_type] = {'targets': 0, 'comments': 0, 'conversions': 0}
            type_stats[content_type]['targets'] += row['total_targets']
            type_stats[content_type]['comments'] += total_comments
            type_stats[content_type]['conversions'] += conversions

            # 플랫폼별 집계
            if platform not in platform_stats:
                platform_stats[platform] = {'targets': 0, 'comments': 0, 'conversions': 0}
            platform_stats[platform]['targets'] += row['total_targets']
            platform_stats[platform]['comments'] += total_comments
            platform_stats[platform]['conversions'] += conversions

        # 전환율 계산
        for stats in [type_stats, platform_stats]:
            for key in stats:
                comments = stats[key]['comments']
                conversions = stats[key]['conversions']
                stats[key]['conversion_rate'] = round((conversions / comments * 100) if comments > 0 else 0, 1)

        conn.close()

        return {
            'period_days': days,
            'matrix': list(matrix.values()),
            'by_content_type': [
                {'content_type': k, **v}
                for k, v in sorted(type_stats.items(), key=lambda x: x[1]['conversion_rate'], reverse=True)
            ],
            'by_platform': [
                {'platform': k, **v}
                for k, v in sorted(platform_stats.items(), key=lambda x: x[1]['conversion_rate'], reverse=True)
            ]
        }

    except Exception as e:
        logger.error(f"콘텐츠 성과 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 4. 캠페인 관리 API
# ============================================

class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    target_categories: List[str] = []
    target_platforms: List[str] = []
    daily_target: int = 10
    total_target: int = 100
    budget: float = 0
    template_ids: List[int] = []


@router.get("/campaigns")
async def get_campaigns(
    status: Optional[str] = None
) -> Dict[str, Any]:
    """캠페인 목록 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거
        columns = """id, name, description, status, start_date, end_date, target_categories,
                     target_platforms, daily_target, total_target, budget, template_ids, priority, created_at"""
        query = f"SELECT {columns} FROM campaigns"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        campaigns = []

        for row in cursor.fetchall():
            campaign = dict(row)
            campaign['target_categories'] = json.loads(campaign.get('target_categories', '[]'))
            campaign['target_platforms'] = json.loads(campaign.get('target_platforms', '[]'))
            campaign['template_ids'] = json.loads(campaign.get('template_ids', '[]'))

            # KPI 집계
            cursor.execute("""
                SELECT
                    SUM(targets_processed) as processed,
                    SUM(comments_posted) as comments,
                    SUM(leads_generated) as leads,
                    SUM(conversions) as conversions,
                    SUM(revenue) as revenue
                FROM campaign_kpis
                WHERE campaign_id = ?
            """, [campaign['id']])

            kpi_row = cursor.fetchone()
            campaign['kpi_summary'] = {
                'processed': kpi_row['processed'] or 0,
                'comments': kpi_row['comments'] or 0,
                'leads': kpi_row['leads'] or 0,
                'conversions': kpi_row['conversions'] or 0,
                'revenue': kpi_row['revenue'] or 0
            } if kpi_row else {}

            # 진행률 계산
            total_target = campaign.get('total_target', 100)
            processed = campaign['kpi_summary'].get('processed', 0)
            campaign['progress_percent'] = round((processed / total_target * 100) if total_target > 0 else 0, 1)

            campaigns.append(campaign)

        conn.close()

        return {
            'campaigns': campaigns,
            'total': len(campaigns)
        }

    except Exception as e:
        logger.error(f"캠페인 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns")
async def create_campaign(campaign: CampaignCreate) -> Dict[str, Any]:
    """캠페인 생성"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO campaigns (
                name, description, start_date, end_date,
                target_categories, target_platforms,
                daily_target, total_target, budget, template_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            campaign.name,
            campaign.description,
            campaign.start_date,
            campaign.end_date,
            json.dumps(campaign.target_categories),
            json.dumps(campaign.target_platforms),
            campaign.daily_target,
            campaign.total_target,
            campaign.budget,
            json.dumps(campaign.template_ids)
        ])

        campaign_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {'id': campaign_id, 'message': '캠페인이 생성되었습니다.'}

    except Exception as e:
        logger.error(f"캠페인 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/campaigns/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: int,
    status: str = Query(..., pattern="^(draft|active|paused|completed)$")
) -> Dict[str, Any]:
    """캠페인 상태 변경"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE campaigns
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, [status, campaign_id])

        conn.commit()
        conn.close()

        return {'message': f'캠페인 상태가 {status}로 변경되었습니다.'}

    except Exception as e:
        logger.error(f"캠페인 상태 변경 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 5. 통합 ROI 대시보드 API
# ============================================

@router.get("/roi/dashboard")
async def get_roi_dashboard(
    days: int = Query(30, ge=7, le=90)
) -> Dict[str, Any]:
    """
    통합 ROI 대시보드
    - 퍼널 분석
    - 채널별 ROI
    - AI 권장사항
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # 1. 퍼널 데이터
        cursor.execute("""
            SELECT COUNT(*) as count FROM viral_targets
            WHERE discovered_at >= ?
        """, [start_date])
        total_targets = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count FROM posted_comments
            WHERE posted_at >= ?
        """, [start_date])
        total_comments = cursor.fetchone()['count']

        cursor.execute("""
            SELECT
                SUM(COALESCE(likes, 0) + COALESCE(replies, 0)) as engagements,
                SUM(CASE WHEN led_to_contact = 1 THEN 1 ELSE 0 END) as leads,
                SUM(CASE WHEN led_to_conversion = 1 THEN 1 ELSE 0 END) as conversions
            FROM posted_comments
            WHERE posted_at >= ?
        """, [start_date])
        engagement_row = cursor.fetchone()

        total_engagements = engagement_row['engagements'] or 0
        total_leads = engagement_row['leads'] or 0
        total_conversions = engagement_row['conversions'] or 0

        # lead_conversions에서 매출 조회
        cursor.execute("""
            SELECT SUM(revenue) as total_revenue
            FROM lead_conversions
            WHERE converted_at >= ?
        """, [start_date])
        revenue_row = cursor.fetchone()
        total_revenue = revenue_row['total_revenue'] or 0

        # 2. 채널별 ROI
        cursor.execute("""
            SELECT
                pc.platform,
                COUNT(DISTINCT pc.id) as comments,
                SUM(COALESCE(pc.likes, 0) + COALESCE(pc.replies, 0)) as engagements,
                SUM(CASE WHEN pc.led_to_contact = 1 THEN 1 ELSE 0 END) as leads,
                SUM(CASE WHEN pc.led_to_conversion = 1 THEN 1 ELSE 0 END) as conversions
            FROM posted_comments pc
            WHERE pc.posted_at >= ?
            GROUP BY pc.platform
            ORDER BY conversions DESC
        """, [start_date])

        channel_stats = []
        for row in cursor.fetchall():
            platform = row['platform'] or 'unknown'
            comments = row['comments'] or 0
            conversions = row['conversions'] or 0

            # 간단한 ROI 계산 (시간당 비용 가정)
            estimated_cost = comments * 5000  # 댓글당 5000원 비용 가정
            estimated_revenue = conversions * 500000  # 전환당 50만원 수익 가정
            roi_percentage = ((estimated_revenue - estimated_cost) / estimated_cost * 100) if estimated_cost > 0 else 0

            channel_stats.append({
                'platform': platform,
                'comments': comments,
                'engagements': row['engagements'] or 0,
                'leads': row['leads'] or 0,
                'conversions': conversions,
                'estimated_revenue': estimated_revenue,
                'estimated_cost': estimated_cost,
                'roi_percentage': round(roi_percentage, 1)
            })

        # 3. 퍼널 전환율 계산
        funnel = {
            'targets': total_targets,
            'comments': total_comments,
            'engagements': total_engagements,
            'leads': total_leads,
            'conversions': total_conversions,
            'revenue': total_revenue,
            'rates': {
                'target_to_comment': round((total_comments / total_targets * 100) if total_targets > 0 else 0, 1),
                'comment_to_engagement': round((total_engagements / total_comments * 100) if total_comments > 0 else 0, 1),
                'engagement_to_lead': round((total_leads / total_engagements * 100) if total_engagements > 0 else 0, 1),
                'lead_to_conversion': round((total_conversions / total_leads * 100) if total_leads > 0 else 0, 1)
            }
        }

        # 4. AI 권장사항 생성
        recommendations = []

        # 최고 성과 채널 찾기
        if channel_stats:
            best_channel = max(channel_stats, key=lambda x: x['roi_percentage'])
            if best_channel['roi_percentage'] > 0:
                recommendations.append({
                    'type': 'channel_focus',
                    'priority': 'high',
                    'title': f"{best_channel['platform']} 채널 집중 권장",
                    'description': f"ROI {best_channel['roi_percentage']}%로 가장 높은 성과. 리소스 추가 투입 권장.",
                    'expected_impact': '+30% 수익 증가 예상'
                })

        # 전환율 낮은 단계 개선
        if funnel['rates']['lead_to_conversion'] < 30:
            recommendations.append({
                'type': 'conversion_improvement',
                'priority': 'medium',
                'title': '리드→전환 개선 필요',
                'description': f"현재 전환율 {funnel['rates']['lead_to_conversion']}%. 후속 연락 강화 권장.",
                'expected_impact': '+20% 전환율 향상 가능'
            })

        conn.close()

        return {
            'period_days': days,
            'funnel': funnel,
            'by_channel': channel_stats,
            'summary': {
                'total_revenue': total_revenue,
                'estimated_cost': sum(c['estimated_cost'] for c in channel_stats),
                'overall_roi': round(
                    ((total_revenue - sum(c['estimated_cost'] for c in channel_stats)) /
                     max(sum(c['estimated_cost'] for c in channel_stats), 1) * 100), 1
                )
            },
            'recommendations': recommendations
        }

    except Exception as e:
        logger.error(f"ROI 대시보드 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 6. 스마트 알림 API
# ============================================

class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rule_type: str
    condition_json: str
    action_type: str = "notification"
    action_params: str = "{}"
    priority: str = "medium"


@router.get("/alerts/rules")
async def get_alert_rules() -> Dict[str, Any]:
    """알림 규칙 목록 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거
        columns = """id, name, description, rule_type, condition_json, action_type, action_params,
                     priority, is_active, cooldown_minutes, last_triggered_at, trigger_count, created_at"""
        cursor.execute(f"""
            SELECT {columns} FROM alert_rules
            ORDER BY is_active DESC, priority DESC, created_at DESC
        """)

        rules = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return {'rules': rules, 'total': len(rules)}

    except Exception as e:
        logger.error(f"알림 규칙 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/rules")
async def create_alert_rule(rule: AlertRuleCreate) -> Dict[str, Any]:
    """알림 규칙 생성"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alert_rules (
                name, description, rule_type, condition_json,
                action_type, action_params, priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            rule.name, rule.description, rule.rule_type,
            rule.condition_json, rule.action_type, rule.action_params,
            rule.priority
        ])

        rule_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {'id': rule_id, 'message': '알림 규칙이 생성되었습니다.'}

    except Exception as e:
        logger.error(f"알림 규칙 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AlertRuleUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    description: Optional[str] = None
    condition_json: Optional[str] = None
    action_type: Optional[str] = None
    action_params: Optional[str] = None
    priority: Optional[str] = None


@router.patch("/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: int, update: AlertRuleUpdate) -> Dict[str, Any]:
    """알림 규칙 업데이트"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거 - 현재 규칙 조회
        cursor.execute("SELECT id FROM alert_rules WHERE id = ?", [rule_id])
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다")

        # 업데이트할 필드 구성
        updates = []
        values = []

        if update.is_active is not None:
            updates.append("is_active = ?")
            values.append(1 if update.is_active else 0)
        if update.name is not None:
            updates.append("name = ?")
            values.append(update.name)
        if update.description is not None:
            updates.append("description = ?")
            values.append(update.description)
        if update.condition_json is not None:
            updates.append("condition_json = ?")
            values.append(update.condition_json)
        if update.action_type is not None:
            updates.append("action_type = ?")
            values.append(update.action_type)
        if update.action_params is not None:
            updates.append("action_params = ?")
            values.append(update.action_params)
        if update.priority is not None:
            updates.append("priority = ?")
            values.append(update.priority)

        if updates:
            updates.append("updated_at = datetime('now')")
            values.append(rule_id)

            cursor.execute(f"""
                UPDATE alert_rules
                SET {', '.join(updates)}
                WHERE id = ?
            """, values)
            conn.commit()

        # [Phase 7] SELECT * 제거 - 업데이트된 규칙 조회
        columns = """id, name, description, rule_type, condition_json, action_type, action_params,
                     priority, is_active, cooldown_minutes, last_triggered_at, trigger_count, created_at"""
        cursor.execute(f"SELECT {columns} FROM alert_rules WHERE id = ?", [rule_id])
        updated_rule = dict(cursor.fetchone())
        conn.close()

        return {'success': True, 'rule': updated_rule}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"알림 규칙 업데이트 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: int) -> Dict[str, Any]:
    """알림 규칙 삭제"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 규칙 존재 확인
        cursor.execute("SELECT id FROM alert_rules WHERE id = ?", [rule_id])
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다")

        # 삭제
        cursor.execute("DELETE FROM alert_rules WHERE id = ?", [rule_id])
        conn.commit()
        conn.close()

        return {'success': True, 'deleted_id': rule_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"알림 규칙 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/logs")
async def get_alert_logs(
    limit: int = Query(50, ge=10, le=200)
) -> Dict[str, Any]:
    """알림 로그 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT al.*, ar.name as rule_name
            FROM alert_logs al
            LEFT JOIN alert_rules ar ON al.rule_id = ar.id
            ORDER BY al.created_at DESC
            LIMIT ?
        """, [limit])

        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return {'logs': logs, 'total': len(logs)}

    except Exception as e:
        logger.error(f"알림 로그 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 7. 경쟁사 바이럴 레이더 API
# ============================================

@router.get("/competitor-radar/stats")
async def get_competitor_radar_stats(
    days: int = Query(30, ge=7, le=90)
) -> Dict[str, Any]:
    """경쟁사 바이럴 활동 통계"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # 경쟁사별 언급 통계
        cursor.execute("""
            SELECT
                competitor_name,
                COUNT(*) as total_mentions,
                SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
                SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative,
                SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END) as neutral,
                SUM(CASE WHEN weakness_detected = 1 THEN 1 ELSE 0 END) as weaknesses,
                AVG(counter_attack_score) as avg_counter_score
            FROM competitor_viral_mentions
            WHERE discovered_at >= ?
            GROUP BY competitor_name
            ORDER BY total_mentions DESC
        """, [start_date])

        competitor_stats = [dict(row) for row in cursor.fetchall()]

        # [Phase 7] SELECT * 제거 - 역공략 기회
        cursor.execute("""
            SELECT id, source_mention_id, competitor_name, opportunity_type, opportunity_score,
                   our_strength, suggested_response, status, created_at
            FROM counter_attack_opportunities
            WHERE status = 'pending'
            ORDER BY opportunity_score DESC
            LIMIT 10
        """)

        opportunities = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            'period_days': days,
            'competitors': competitor_stats,
            'opportunities': opportunities,
            'summary': {
                'total_competitors': len(competitor_stats),
                'total_mentions': sum(c['total_mentions'] for c in competitor_stats),
                'total_weaknesses': sum(c['weaknesses'] for c in competitor_stats),
                'pending_opportunities': len(opportunities)
            }
        }

    except Exception as e:
        logger.error(f"경쟁사 레이더 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 8. A/B 테스트 API
# ============================================

class ExperimentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    experiment_type: str = "comment_style"
    target_category: Optional[str] = None
    target_platform: Optional[str] = None
    sample_size_target: int = 100
    variants: List[Dict[str, Any]] = []


@router.get("/ab-tests")
async def get_ab_tests() -> Dict[str, Any]:
    """A/B 테스트 목록 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거
        exp_columns = """id, name, description, status, experiment_type, target_category, target_platform,
                         sample_size_target, confidence_level, start_date, end_date, winner_variant_id, created_at"""
        cursor.execute(f"""
            SELECT {exp_columns} FROM ab_experiments
            ORDER BY created_at DESC
        """)

        experiments = []
        for row in cursor.fetchall():
            exp = dict(row)

            # [Phase 7] SELECT * 제거 - 변형 통계 조회
            var_columns = """id, experiment_id, name, description, content_template, weight, is_control,
                             impressions, engagements, conversions, engagement_rate, conversion_rate"""
            cursor.execute(f"""
                SELECT {var_columns} FROM ab_variants
                WHERE experiment_id = ?
                ORDER BY is_control DESC, id
            """, [exp['id']])

            exp['variants'] = [dict(v) for v in cursor.fetchall()]

            # 총 샘플 수 계산
            total_impressions = sum(v.get('impressions', 0) for v in exp['variants'])
            exp['total_impressions'] = total_impressions
            exp['progress_percent'] = round(
                (total_impressions / exp.get('sample_size_target', 100) * 100), 1
            )

            experiments.append(exp)

        conn.close()

        return {'experiments': experiments, 'total': len(experiments)}

    except Exception as e:
        logger.error(f"A/B 테스트 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ab-tests")
async def create_ab_test(experiment: ExperimentCreate) -> Dict[str, Any]:
    """A/B 테스트 생성"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ab_experiments (
                name, description, experiment_type,
                target_category, target_platform, sample_size_target
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, [
            experiment.name, experiment.description, experiment.experiment_type,
            experiment.target_category, experiment.target_platform,
            experiment.sample_size_target
        ])

        experiment_id = cursor.lastrowid

        # 변형 추가
        for i, variant in enumerate(experiment.variants):
            cursor.execute("""
                INSERT INTO ab_variants (
                    experiment_id, name, description, content_template, is_control
                ) VALUES (?, ?, ?, ?, ?)
            """, [
                experiment_id,
                variant.get('name', f'변형 {i + 1}'),
                variant.get('description'),
                variant.get('content_template'),
                1 if i == 0 else 0  # 첫 번째가 대조군
            ])

        conn.commit()
        conn.close()

        return {'id': experiment_id, 'message': 'A/B 테스트가 생성되었습니다.'}

    except Exception as e:
        logger.error(f"A/B 테스트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ab-tests/{experiment_id}/status")
async def update_experiment_status(
    experiment_id: int,
    status: str = Query(..., pattern="^(draft|running|paused|completed)$")
) -> Dict[str, Any]:
    """A/B 테스트 상태 변경"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        update_fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status]

        if status == "running":
            update_fields.append("start_date = CURRENT_TIMESTAMP")
        elif status == "completed":
            update_fields.append("end_date = CURRENT_TIMESTAMP")

        params.append(experiment_id)

        cursor.execute(f"""
            UPDATE ab_experiments
            SET {', '.join(update_fields)}
            WHERE id = ?
        """, params)

        conn.commit()
        conn.close()

        return {'message': f'A/B 테스트 상태가 {status}로 변경되었습니다.'}

    except Exception as e:
        logger.error(f"A/B 테스트 상태 변경 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [고도화 V2-5] 시즌별 캠페인 자동화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/seasonal-campaigns")
async def get_seasonal_campaigns():
    """
    [고도화 V2-5] 현재 활성 시즌 캠페인 + 임박 캠페인

    계절/시기에 맞는 마케팅 캠페인을 자동 제안합니다.
    추천 키워드, 콘텐츠 주제, 타겟 고객층 포함.
    """
    try:
        from services.seasonal_campaign import get_active_campaigns
        return get_active_campaigns()
    except Exception as e:
        logger.error(f"시즌 캠페인 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/seasonal-campaigns/{campaign_id}/calendar")
async def get_campaign_calendar(campaign_id: str, weeks: int = 4):
    """[고도화 V2-5] 특정 캠페인의 주간 콘텐츠 캘린더"""
    try:
        from services.seasonal_campaign import get_campaign_content_calendar
        return get_campaign_content_calendar(campaign_id, weeks=weeks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [고도화 V2-8] 블로그 콘텐츠 생성 파이프라인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BlogGenerateRequest(BaseModel):
    keyword: str
    clinic_name: Optional[str] = "규림한의원"
    doctor_name: Optional[str] = "원장"
    target_audience: Optional[str] = "일반 환자"


@router.post("/blog/generate")
async def generate_blog_post(request: BlogGenerateRequest):
    """
    [고도화 V2-8] 블로그 포스트 자동 생성 파이프라인

    키워드 → 아웃라인 → 초안 → AEO 최적화 → 규정 체크 → Schema Markup

    Body:
        keyword: "환절기 한의원"
        clinic_name: "규림한의원"
        doctor_name: "원장"
    """
    try:
        from services.content_pipeline import ContentPipeline

        db = DatabaseManager()
        pipeline = ContentPipeline(db_path=db.db_path)

        result = await pipeline.full_pipeline(
            keyword=request.keyword,
            clinic_name=request.clinic_name,
            doctor_name=request.doctor_name,
            target_audience=request.target_audience,
        )

        return result

    except Exception as e:
        logger.error(f"블로그 생성 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blog/outline")
async def generate_blog_outline(request: BlogGenerateRequest):
    """[고도화 V2-8] 아웃라인만 생성 (초안 전 단계)"""
    try:
        from services.content_pipeline import ContentPipeline

        db = DatabaseManager()
        pipeline = ContentPipeline(db_path=db.db_path)

        outline = await pipeline.generate_outline(
            keyword=request.keyword,
            target_audience=request.target_audience,
        )
        return outline

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
