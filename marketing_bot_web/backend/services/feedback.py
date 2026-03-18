"""
Marketing Feedback Loop Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase D] 피드백 루프 완성
- D-1: 성과 피드백 루프 (스코어링 개선)
- D-2: 예측 정확도 자동 검증
- D-3: 키워드별 ROI 추적
- D-4: 성과 리포트 자동 생성
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# DB 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'


def get_db_connection():
    """SQLite 연결 생성"""
    return sqlite3.connect(str(DB_PATH))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-1: 성과 피드백 루프
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PerformanceFeedbackLoop:
    """
    성과 피드백 루프 시스템

    전환된 리드의 특성을 분석하여 스코어링 가중치 자동 조정
    """

    def analyze_conversion_characteristics(self) -> Dict[str, Any]:
        """
        전환된 리드의 공통 특성 분석

        Returns:
            특성 분석 결과 및 가중치 조정 제안
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        analysis = {
            'total_conversions': 0,
            'platform_performance': {},
            'keyword_performance': {},
            'score_distribution': {},
            'time_to_conversion': {},
            'recommended_adjustments': []
        }

        try:
            # 1. 플랫폼별 전환율 분석
            cursor.execute("""
                SELECT
                    COALESCE(m.platform, m.source, 'unknown') as platform,
                    COUNT(DISTINCT m.id) as total_leads,
                    COUNT(DISTINCT lc.id) as conversions,
                    AVG(lc.revenue) as avg_revenue
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                GROUP BY platform
                HAVING total_leads >= 5
            """)

            for row in cursor.fetchall():
                platform, total, conversions, avg_rev = row
                conv_rate = conversions / total if total > 0 else 0
                analysis['platform_performance'][platform] = {
                    'total_leads': total,
                    'conversions': conversions,
                    'conversion_rate': round(conv_rate, 4),
                    'avg_revenue': round(avg_rev or 0, 0)
                }
                analysis['total_conversions'] += conversions

            # 2. 점수 구간별 전환율 분석
            cursor.execute("""
                SELECT
                    CASE
                        WHEN m.score >= 80 THEN '80-100 (Hot)'
                        WHEN m.score >= 60 THEN '60-79 (Warm)'
                        WHEN m.score >= 40 THEN '40-59 (Cool)'
                        ELSE '0-39 (Cold)'
                    END as score_range,
                    COUNT(DISTINCT m.id) as total_leads,
                    COUNT(DISTINCT lc.id) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.score IS NOT NULL
                AND m.created_at >= datetime('now', '-90 days')
                GROUP BY score_range
            """)

            for row in cursor.fetchall():
                score_range, total, conversions = row
                conv_rate = conversions / total if total > 0 else 0
                analysis['score_distribution'][score_range] = {
                    'total_leads': total,
                    'conversions': conversions,
                    'conversion_rate': round(conv_rate, 4)
                }

            # 3. 전환까지 걸린 시간 분석
            cursor.execute("""
                SELECT
                    lc.days_to_conversion,
                    COUNT(*) as count
                FROM lead_conversions lc
                WHERE lc.days_to_conversion IS NOT NULL
                GROUP BY lc.days_to_conversion
                ORDER BY lc.days_to_conversion
            """)

            time_buckets = {'same_day': 0, '1-3_days': 0, '4-7_days': 0, '8-14_days': 0, '15+_days': 0}
            for row in cursor.fetchall():
                days, count = row
                if days == 0:
                    time_buckets['same_day'] += count
                elif days <= 3:
                    time_buckets['1-3_days'] += count
                elif days <= 7:
                    time_buckets['4-7_days'] += count
                elif days <= 14:
                    time_buckets['8-14_days'] += count
                else:
                    time_buckets['15+_days'] += count

            analysis['time_to_conversion'] = time_buckets

            # 4. 가중치 조정 제안 생성
            analysis['recommended_adjustments'] = self._generate_weight_adjustments(analysis)

            # 5. 분석 결과 저장
            self._save_feedback_analysis(cursor, analysis)
            conn.commit()

        except Exception as e:
            logger.error(f"[피드백] 전환 특성 분석 오류: {e}")
        finally:
            conn.close()

        return analysis

    def _generate_weight_adjustments(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """가중치 조정 제안 생성"""
        adjustments = []

        # 플랫폼 가중치 조정
        platform_perf = analysis.get('platform_performance', {})
        if platform_perf:
            avg_conv_rate = sum(p['conversion_rate'] for p in platform_perf.values()) / len(platform_perf)

            for platform, data in platform_perf.items():
                if data['conversion_rate'] > avg_conv_rate * 1.5:
                    adjustments.append({
                        'type': 'platform_weight',
                        'target': platform,
                        'current_performance': data['conversion_rate'],
                        'recommendation': 'increase',
                        'reason': f"평균 대비 {data['conversion_rate']/avg_conv_rate:.1f}배 높은 전환율"
                    })
                elif data['conversion_rate'] < avg_conv_rate * 0.5 and data['total_leads'] >= 10:
                    adjustments.append({
                        'type': 'platform_weight',
                        'target': platform,
                        'current_performance': data['conversion_rate'],
                        'recommendation': 'decrease',
                        'reason': f"평균 대비 {data['conversion_rate']/avg_conv_rate:.1f}배 낮은 전환율"
                    })

        # 점수 임계값 조정
        score_dist = analysis.get('score_distribution', {})
        for score_range, data in score_dist.items():
            if 'Hot' in score_range and data['conversion_rate'] < 0.1:
                adjustments.append({
                    'type': 'threshold',
                    'target': 'hot_threshold',
                    'recommendation': 'increase',
                    'reason': f"Hot 리드 전환율이 {data['conversion_rate']*100:.1f}%로 낮음"
                })
            if 'Warm' in score_range and data['conversion_rate'] > 0.15:
                adjustments.append({
                    'type': 'threshold',
                    'target': 'warm_threshold',
                    'recommendation': 'decrease',
                    'reason': f"Warm 리드 전환율이 {data['conversion_rate']*100:.1f}%로 높음"
                })

        return adjustments

    def _save_feedback_analysis(self, cursor, analysis: Dict[str, Any]):
        """피드백 분석 결과 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_type TEXT NOT NULL,
                analysis_date TEXT DEFAULT (DATE('now')),
                content TEXT NOT NULL,
                adjustments_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            INSERT INTO feedback_analysis (analysis_type, content, adjustments_count)
            VALUES ('conversion_characteristics', ?, ?)
        """, (
            json.dumps(analysis, ensure_ascii=False),
            len(analysis.get('recommended_adjustments', []))
        ))

    def apply_feedback_adjustments(self, adjustments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        피드백 기반 조정 적용

        Note: 실제 가중치 변경은 설정 파일 수정이 필요하므로
        여기서는 추천 사항을 기록하고 알림 생성
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        result = {
            'applied': 0,
            'notifications_created': 0
        }

        try:
            for adj in adjustments:
                # 알림 생성
                cursor.execute("""
                    INSERT INTO notifications (type, title, message, priority, is_read, created_at)
                    VALUES ('system', ?, ?, 'medium', 0, datetime('now'))
                """, (
                    f"스코어링 조정 권장: {adj['target']}",
                    f"{adj['recommendation']} 권장 - {adj['reason']}"
                ))
                result['notifications_created'] += 1

            conn.commit()
            result['applied'] = len(adjustments)

        except Exception as e:
            logger.error(f"[피드백] 조정 적용 오류: {e}")
            conn.rollback()
        finally:
            conn.close()

        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-2: 예측 정확도 자동 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PredictionAccuracyValidator:
    """
    예측 정확도 자동 검증 시스템

    순위 예측 및 전환 예측의 정확도를 검증하고 개선
    """

    def validate_rank_predictions(self) -> Dict[str, Any]:
        """
        순위 예측 정확도 검증

        Returns:
            정확도 분석 결과
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        result = {
            'total_predictions': 0,
            'verified_predictions': 0,
            'accurate_predictions': 0,
            'overall_accuracy': 0,
            'accuracy_by_confidence': {},
            'accuracy_by_trend': {},
            'recommendations': []
        }

        try:
            # 검증 대상 예측 조회 (예측 후 days_ahead 일이 지난 것)
            cursor.execute("""
                SELECT
                    rp.id, rp.keyword, rp.predicted_rank, rp.current_rank,
                    rp.trend, rp.confidence, rp.days_ahead, rp.predicted_at
                FROM rank_predictions rp
                WHERE rp.accuracy_checked = 0
                AND date(rp.predicted_at, '+' || rp.days_ahead || ' days') <= date('now')
            """)

            predictions = cursor.fetchall()
            result['total_predictions'] = len(predictions)

            by_confidence = defaultdict(lambda: {'total': 0, 'accurate': 0})
            by_trend = defaultdict(lambda: {'total': 0, 'accurate': 0})

            for pred in predictions:
                pred_id, keyword, predicted, current, trend, confidence, days_ahead, predicted_at = pred

                # 예측 대상 날짜의 실제 순위 조회
                target_date = (datetime.fromisoformat(predicted_at) + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

                cursor.execute("""
                    SELECT rank FROM rank_history
                    WHERE keyword = ? AND date = ? AND status = 'found'
                """, (keyword, target_date))

                actual_row = cursor.fetchone()
                if actual_row:
                    actual_rank = actual_row[0]

                    # ±3순위 이내면 정확한 예측
                    is_accurate = abs(predicted - actual_rank) <= 3

                    # 예측 결과 업데이트
                    cursor.execute("""
                        UPDATE rank_predictions
                        SET actual_rank = ?, accuracy_checked = 1
                        WHERE id = ?
                    """, (actual_rank, pred_id))

                    result['verified_predictions'] += 1
                    if is_accurate:
                        result['accurate_predictions'] += 1

                    by_confidence[confidence]['total'] += 1
                    by_trend[trend]['total'] += 1
                    if is_accurate:
                        by_confidence[confidence]['accurate'] += 1
                        by_trend[trend]['accurate'] += 1

            # 정확도 계산
            if result['verified_predictions'] > 0:
                result['overall_accuracy'] = round(
                    result['accurate_predictions'] / result['verified_predictions'], 4
                )

            # 신뢰도별 정확도
            for conf, data in by_confidence.items():
                if data['total'] > 0:
                    result['accuracy_by_confidence'][conf] = {
                        'total': data['total'],
                        'accurate': data['accurate'],
                        'accuracy': round(data['accurate'] / data['total'], 4)
                    }

            # 트렌드별 정확도
            for trend, data in by_trend.items():
                if data['total'] > 0:
                    result['accuracy_by_trend'][trend] = {
                        'total': data['total'],
                        'accurate': data['accurate'],
                        'accuracy': round(data['accurate'] / data['total'], 4)
                    }

            # 개선 추천
            result['recommendations'] = self._generate_accuracy_recommendations(result)

            # 결과 저장
            self._save_accuracy_report(cursor, result)
            conn.commit()

        except Exception as e:
            logger.error(f"[피드백] 예측 정확도 검증 오류: {e}")
        finally:
            conn.close()

        return result

    def _generate_accuracy_recommendations(self, result: Dict[str, Any]) -> List[str]:
        """정확도 개선 추천 생성"""
        recommendations = []

        if result['overall_accuracy'] < 0.5:
            recommendations.append("전체 예측 정확도가 50% 미만입니다. 모델 재검토가 필요합니다.")

        # 신뢰도별 분석
        for conf, data in result.get('accuracy_by_confidence', {}).items():
            if conf == 'high' and data['accuracy'] < 0.7:
                recommendations.append(f"'high' 신뢰도 예측의 정확도가 {data['accuracy']*100:.0f}%로 낮습니다.")
            if conf == 'low' and data['accuracy'] > 0.6:
                recommendations.append(f"'low' 신뢰도 예측도 {data['accuracy']*100:.0f}% 정확도로 신뢰할 수 있습니다.")

        # 트렌드별 분석
        for trend, data in result.get('accuracy_by_trend', {}).items():
            if data['accuracy'] < 0.4:
                recommendations.append(f"'{trend}' 트렌드 예측 정확도({data['accuracy']*100:.0f}%)가 낮습니다.")

        return recommendations

    def _save_accuracy_report(self, cursor, result: Dict[str, Any]):
        """정확도 리포트 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                report_date TEXT DEFAULT (DATE('now')),
                overall_accuracy REAL,
                verified_count INTEGER,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            INSERT INTO accuracy_reports (report_type, overall_accuracy, verified_count, content)
            VALUES ('rank_prediction', ?, ?, ?)
        """, (
            result['overall_accuracy'],
            result['verified_predictions'],
            json.dumps(result, ensure_ascii=False)
        ))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-3: 키워드별 ROI 추적
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class KeywordROITracker:
    """
    키워드별 ROI 추적 시스템

    키워드별 리드, 전환, 수익을 추적하여 ROI 분석
    """

    def calculate_keyword_roi(self, period_days: int = 30) -> Dict[str, Any]:
        """
        키워드별 ROI 계산

        Args:
            period_days: 분석 기간 (일)

        Returns:
            키워드별 ROI 분석 결과
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        result = {
            'period_days': period_days,
            'keywords': [],
            'top_performers': [],
            'underperformers': [],
            'summary': {}
        }

        try:
            # 키워드별 성과 집계
            cursor.execute("""
                SELECT
                    COALESCE(m.matched_keyword, '(키워드 없음)') as keyword,
                    COUNT(DISTINCT m.id) as total_leads,
                    COUNT(DISTINCT lc.id) as conversions,
                    COALESCE(SUM(lc.revenue), 0) as total_revenue,
                    AVG(m.score) as avg_score
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY keyword
                HAVING total_leads >= 3
                ORDER BY total_revenue DESC
            """, (period_days,))

            all_keywords = []
            total_leads = 0
            total_conversions = 0
            total_revenue = 0

            for row in cursor.fetchall():
                keyword, leads, conversions, revenue, avg_score = row

                conv_rate = conversions / leads if leads > 0 else 0
                value_per_lead = revenue / leads if leads > 0 else 0

                # ROI 점수 계산 (전환율 * 평균 수익)
                roi_score = conv_rate * (revenue / max(conversions, 1)) if conversions > 0 else 0

                keyword_data = {
                    'keyword': keyword,
                    'leads': leads,
                    'conversions': conversions,
                    'revenue': round(revenue, 0),
                    'conversion_rate': round(conv_rate, 4),
                    'value_per_lead': round(value_per_lead, 0),
                    'avg_score': round(avg_score or 0, 1),
                    'roi_score': round(roi_score, 2)
                }

                all_keywords.append(keyword_data)
                total_leads += leads
                total_conversions += conversions
                total_revenue += revenue

            # 정렬
            result['keywords'] = sorted(all_keywords, key=lambda x: x['roi_score'], reverse=True)

            # 상위/하위 성과자
            result['top_performers'] = result['keywords'][:5]
            result['underperformers'] = [k for k in result['keywords'] if k['conversion_rate'] == 0 and k['leads'] >= 5][:5]

            # 요약
            result['summary'] = {
                'total_keywords': len(all_keywords),
                'total_leads': total_leads,
                'total_conversions': total_conversions,
                'total_revenue': round(total_revenue, 0),
                'overall_conversion_rate': round(total_conversions / total_leads, 4) if total_leads > 0 else 0,
                'avg_value_per_lead': round(total_revenue / total_leads, 0) if total_leads > 0 else 0
            }

            # ROI 통계 저장
            self._save_roi_stats(cursor, result, period_days)
            conn.commit()

        except Exception as e:
            logger.error(f"[피드백] ROI 계산 오류: {e}")
        finally:
            conn.close()

        return result

    def _save_roi_stats(self, cursor, result: Dict[str, Any], period_days: int):
        """ROI 통계 저장"""
        period_end = datetime.now().strftime('%Y-%m-%d')
        period_start = (datetime.now() - timedelta(days=period_days)).strftime('%Y-%m-%d')

        for kw in result.get('keywords', []):
            cursor.execute("""
                INSERT OR REPLACE INTO keyword_roi_stats
                (keyword, period_start, period_end, total_leads, total_conversions,
                 total_revenue, conversion_rate, roi_score, calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                kw['keyword'],
                period_start,
                period_end,
                kw['leads'],
                kw['conversions'],
                kw['revenue'],
                kw['conversion_rate'],
                kw['roi_score']
            ))

    def get_roi_trends(self, keyword: str = None) -> Dict[str, Any]:
        """
        ROI 트렌드 조회

        Args:
            keyword: 특정 키워드 (None이면 전체)
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        result = {
            'keyword': keyword or 'all',
            'trends': []
        }

        try:
            if keyword:
                cursor.execute("""
                    SELECT period_start, period_end, total_leads, total_conversions,
                           total_revenue, conversion_rate, roi_score
                    FROM keyword_roi_stats
                    WHERE keyword = ?
                    ORDER BY period_end DESC
                    LIMIT 12
                """, (keyword,))
            else:
                cursor.execute("""
                    SELECT period_end,
                           SUM(total_leads) as leads,
                           SUM(total_conversions) as conversions,
                           SUM(total_revenue) as revenue
                    FROM keyword_roi_stats
                    GROUP BY period_end
                    ORDER BY period_end DESC
                    LIMIT 12
                """)

            for row in cursor.fetchall():
                if keyword:
                    result['trends'].append({
                        'period': f"{row[0]} ~ {row[1]}",
                        'leads': row[2],
                        'conversions': row[3],
                        'revenue': row[4],
                        'conversion_rate': row[5],
                        'roi_score': row[6]
                    })
                else:
                    result['trends'].append({
                        'period': row[0],
                        'leads': row[1],
                        'conversions': row[2],
                        'revenue': row[3]
                    })

        except Exception as e:
            logger.error(f"[피드백] ROI 트렌드 조회 오류: {e}")
        finally:
            conn.close()

        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D-4: 성과 리포트 자동 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PerformanceReportGenerator:
    """
    성과 리포트 자동 생성

    주간/월간 성과 리포트 생성
    """

    def generate_weekly_report(self) -> Dict[str, Any]:
        """주간 성과 리포트 생성"""
        return self._generate_report('weekly', 7)

    def generate_monthly_report(self) -> Dict[str, Any]:
        """월간 성과 리포트 생성"""
        return self._generate_report('monthly', 30)

    def _generate_report(self, period_type: str, days: int) -> Dict[str, Any]:
        """
        성과 리포트 생성

        Args:
            period_type: 리포트 유형 (weekly/monthly)
            days: 분석 기간
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        report = {
            'type': period_type,
            'period_days': days,
            'generated_at': datetime.now().isoformat(),
            'kpi_summary': {},
            'rank_performance': {},
            'lead_performance': {},
            'viral_performance': {},
            'trends': {},
            'recommendations': [],
            'highlights': []
        }

        try:
            # 1. KPI 요약
            report['kpi_summary'] = self._get_kpi_summary(cursor, days)

            # 2. 순위 성과
            report['rank_performance'] = self._get_rank_performance(cursor, days)

            # 3. 리드 성과
            report['lead_performance'] = self._get_lead_performance(cursor, days)

            # 4. 바이럴 성과
            report['viral_performance'] = self._get_viral_performance(cursor, days)

            # 5. 트렌드 (이전 기간 대비)
            report['trends'] = self._calculate_trends(cursor, days)

            # 6. 추천 및 하이라이트
            report['recommendations'] = self._generate_report_recommendations(report)
            report['highlights'] = self._generate_report_highlights(report)

            # 리포트 저장
            self._save_report(cursor, report)
            conn.commit()

        except Exception as e:
            logger.error(f"[피드백] 리포트 생성 오류: {e}")
        finally:
            conn.close()

        return report

    def _get_kpi_summary(self, cursor, days: int) -> Dict[str, Any]:
        """KPI 요약"""
        kpi = {
            'total_keywords_tracked': 0,
            'top_10_keywords': 0,
            'new_leads': 0,
            'conversions': 0,
            'total_revenue': 0,
            'viral_completed': 0
        }

        # 추적 키워드 수
        cursor.execute("SELECT COUNT(DISTINCT keyword) FROM rank_history WHERE date >= date('now', '-' || ? || ' days')", (days,))
        kpi['total_keywords_tracked'] = cursor.fetchone()[0] or 0

        # Top 10 키워드 수
        cursor.execute("""
            SELECT COUNT(DISTINCT keyword) FROM rank_history
            WHERE date = date('now', '-1 day') AND rank <= 10 AND status = 'found'
        """)
        kpi['top_10_keywords'] = cursor.fetchone()[0] or 0

        # 신규 리드
        cursor.execute("SELECT COUNT(*) FROM mentions WHERE created_at >= datetime('now', '-' || ? || ' days')", (days,))
        kpi['new_leads'] = cursor.fetchone()[0] or 0

        # 전환
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(revenue), 0)
            FROM lead_conversions
            WHERE converted_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        row = cursor.fetchone()
        kpi['conversions'] = row[0] or 0
        kpi['total_revenue'] = round(row[1] or 0, 0)

        # 바이럴 완료
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status IN ('completed', 'posted')
            AND updated_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        kpi['viral_completed'] = cursor.fetchone()[0] or 0

        return kpi

    def _get_rank_performance(self, cursor, days: int) -> Dict[str, Any]:
        """순위 성과"""
        perf = {
            'improved': 0,
            'declined': 0,
            'stable': 0,
            'new_top_10': [],
            'lost_top_10': []
        }

        # 순위 변동 (기간 시작 vs 종료)
        cursor.execute("""
            SELECT
                start_rank.keyword,
                start_rank.rank as start_rank,
                end_rank.rank as end_rank
            FROM (
                SELECT keyword, rank FROM rank_history
                WHERE date = date('now', '-' || ? || ' days') AND status = 'found'
            ) start_rank
            JOIN (
                SELECT keyword, rank FROM rank_history
                WHERE date = date('now', '-1 day') AND status = 'found'
            ) end_rank ON start_rank.keyword = end_rank.keyword
        """, (days,))

        for row in cursor.fetchall():
            keyword, start, end = row
            if end < start:
                perf['improved'] += 1
                if end <= 10 and start > 10:
                    perf['new_top_10'].append({'keyword': keyword, 'rank': end})
            elif end > start:
                perf['declined'] += 1
                if start <= 10 and end > 10:
                    perf['lost_top_10'].append({'keyword': keyword, 'rank': end})
            else:
                perf['stable'] += 1

        return perf

    def _get_lead_performance(self, cursor, days: int) -> Dict[str, Any]:
        """리드 성과"""
        perf = {
            'total': 0,
            'by_platform': {},
            'by_grade': {},
            'conversion_rate': 0
        }

        cursor.execute("""
            SELECT
                COALESCE(platform, source, 'unknown') as platform,
                COUNT(*) as count
            FROM mentions
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY platform
            ORDER BY count DESC
        """, (days,))

        for row in cursor.fetchall():
            perf['by_platform'][row[0]] = row[1]
            perf['total'] += row[1]

        cursor.execute("""
            SELECT grade, COUNT(*) FROM mentions
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            AND grade IS NOT NULL
            GROUP BY grade
        """, (days,))

        for row in cursor.fetchall():
            perf['by_grade'][row[0] or 'unknown'] = row[1]

        # 전환율
        cursor.execute("""
            SELECT COUNT(DISTINCT lc.lead_id)
            FROM lead_conversions lc
            JOIN mentions m ON lc.lead_id = m.id
            WHERE m.created_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        conversions = cursor.fetchone()[0] or 0

        if perf['total'] > 0:
            perf['conversion_rate'] = round(conversions / perf['total'], 4)

        return perf

    def _get_viral_performance(self, cursor, days: int) -> Dict[str, Any]:
        """바이럴 성과"""
        perf = {
            'total_targets': 0,
            'completed': 0,
            'pending': 0,
            'completion_rate': 0
        }

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN comment_status IN ('completed', 'posted') THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN comment_status IS NULL OR comment_status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM viral_targets
            WHERE created_at >= datetime('now', '-' || ? || ' days')
        """, (days,))

        row = cursor.fetchone()
        if row:
            perf['total_targets'] = row[0] or 0
            perf['completed'] = row[1] or 0
            perf['pending'] = row[2] or 0
            if perf['total_targets'] > 0:
                perf['completion_rate'] = round(perf['completed'] / perf['total_targets'], 4)

        return perf

    def _calculate_trends(self, cursor, days: int) -> Dict[str, Any]:
        """이전 기간 대비 트렌드 계산"""
        trends = {}

        # 현재 기간 리드 수
        cursor.execute("SELECT COUNT(*) FROM mentions WHERE created_at >= datetime('now', '-' || ? || ' days')", (days,))
        current_leads = cursor.fetchone()[0] or 0

        # 이전 기간 리드 수
        cursor.execute("""
            SELECT COUNT(*) FROM mentions
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            AND created_at < datetime('now', '-' || ? || ' days')
        """, (days * 2, days))
        prev_leads = cursor.fetchone()[0] or 1  # 0으로 나누기 방지

        trends['leads'] = {
            'current': current_leads,
            'previous': prev_leads,
            'change_percent': round((current_leads - prev_leads) / prev_leads * 100, 1)
        }

        # 전환 트렌드
        cursor.execute("""
            SELECT COUNT(*) FROM lead_conversions
            WHERE converted_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        current_conv = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM lead_conversions
            WHERE converted_at >= datetime('now', '-' || ? || ' days')
            AND converted_at < datetime('now', '-' || ? || ' days')
        """, (days * 2, days))
        prev_conv = cursor.fetchone()[0] or 1

        trends['conversions'] = {
            'current': current_conv,
            'previous': prev_conv,
            'change_percent': round((current_conv - prev_conv) / prev_conv * 100, 1)
        }

        return trends

    def _generate_report_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """리포트 기반 추천 생성"""
        recommendations = []

        # 순위 기반 추천
        rank_perf = report.get('rank_performance', {})
        if rank_perf.get('declined', 0) > rank_perf.get('improved', 0):
            recommendations.append("순위 하락 키워드가 많습니다. 바이럴 활동을 강화하세요.")

        if rank_perf.get('lost_top_10'):
            keywords = ', '.join([k['keyword'] for k in rank_perf['lost_top_10'][:3]])
            recommendations.append(f"Top 10 이탈 키워드 주의: {keywords}")

        # 리드 기반 추천
        lead_perf = report.get('lead_performance', {})
        if lead_perf.get('conversion_rate', 0) < 0.05:
            recommendations.append("전환율이 5% 미만입니다. Hot 리드 응답 시간을 단축하세요.")

        # 바이럴 기반 추천
        viral_perf = report.get('viral_performance', {})
        if viral_perf.get('completion_rate', 0) < 0.3:
            recommendations.append("바이럴 완료율이 낮습니다. 대기 중인 타겟을 처리하세요.")

        # 트렌드 기반 추천
        trends = report.get('trends', {})
        if trends.get('leads', {}).get('change_percent', 0) < -20:
            recommendations.append("리드 유입이 20% 이상 감소했습니다. 마케팅 채널을 점검하세요.")

        return recommendations

    def _generate_report_highlights(self, report: Dict[str, Any]) -> List[str]:
        """리포트 하이라이트 생성"""
        highlights = []

        kpi = report.get('kpi_summary', {})
        rank_perf = report.get('rank_performance', {})
        trends = report.get('trends', {})

        if kpi.get('top_10_keywords', 0) > 0:
            highlights.append(f"{kpi['top_10_keywords']}개 키워드 Top 10 유지 중")

        if rank_perf.get('new_top_10'):
            highlights.append(f"{len(rank_perf['new_top_10'])}개 키워드 새로 Top 10 진입")

        if kpi.get('conversions', 0) > 0:
            highlights.append(f"{kpi['conversions']}건 전환 발생 (수익: {kpi['total_revenue']:,.0f}원)")

        if trends.get('leads', {}).get('change_percent', 0) > 10:
            highlights.append(f"리드 유입 {trends['leads']['change_percent']:.0f}% 증가")

        return highlights

    def _save_report(self, cursor, report: Dict[str, Any]):
        """리포트 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                period_days INTEGER,
                content TEXT NOT NULL,
                highlights TEXT,
                recommendations TEXT
            )
        """)

        cursor.execute("""
            INSERT INTO performance_reports
            (report_type, period_days, content, highlights, recommendations)
            VALUES (?, ?, ?, ?, ?)
        """, (
            report['type'],
            report['period_days'],
            json.dumps(report, ensure_ascii=False),
            json.dumps(report.get('highlights', []), ensure_ascii=False),
            json.dumps(report.get('recommendations', []), ensure_ascii=False)
        ))

    def get_latest_report(self, report_type: str = 'weekly') -> Optional[Dict[str, Any]]:
        """최신 리포트 조회"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT content FROM performance_reports
                WHERE report_type = ?
                ORDER BY generated_at DESC
                LIMIT 1
            """, (report_type,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"[피드백] 리포트 조회 오류: {e}")
            return None
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 피드백 서비스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MarketingFeedbackSystem:
    """통합 마케팅 피드백 시스템"""

    def __init__(self):
        self.feedback_loop = PerformanceFeedbackLoop()
        self.accuracy_validator = PredictionAccuracyValidator()
        self.roi_tracker = KeywordROITracker()
        self.report_generator = PerformanceReportGenerator()

    def run_full_feedback_cycle(self) -> Dict[str, Any]:
        """전체 피드백 사이클 실행"""
        logger.info("[피드백] 전체 피드백 사이클 시작...")

        results = {
            'conversion_analysis': None,
            'prediction_accuracy': None,
            'roi_analysis': None,
            'weekly_report': None,
            'errors': []
        }

        # 1. 전환 특성 분석
        try:
            results['conversion_analysis'] = self.feedback_loop.analyze_conversion_characteristics()
            logger.info("[피드백] 전환 특성 분석 완료")
        except Exception as e:
            results['errors'].append(f"전환 분석: {e}")

        # 2. 예측 정확도 검증
        try:
            results['prediction_accuracy'] = self.accuracy_validator.validate_rank_predictions()
            logger.info("[피드백] 예측 정확도 검증 완료")
        except Exception as e:
            results['errors'].append(f"정확도 검증: {e}")

        # 3. ROI 분석
        try:
            results['roi_analysis'] = self.roi_tracker.calculate_keyword_roi(30)
            logger.info("[피드백] ROI 분석 완료")
        except Exception as e:
            results['errors'].append(f"ROI 분석: {e}")

        # 4. 주간 리포트 생성
        try:
            results['weekly_report'] = self.report_generator.generate_weekly_report()
            logger.info("[피드백] 주간 리포트 생성 완료")
        except Exception as e:
            results['errors'].append(f"리포트: {e}")

        logger.info("[피드백] 전체 피드백 사이클 완료")
        return results


# 싱글톤 인스턴스
_feedback_instance = None


def get_feedback_system() -> MarketingFeedbackSystem:
    """MarketingFeedbackSystem 싱글톤 인스턴스 반환"""
    global _feedback_instance
    if _feedback_instance is None:
        _feedback_instance = MarketingFeedbackSystem()
    return _feedback_instance
