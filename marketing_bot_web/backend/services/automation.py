"""
Marketing Automation Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase C] 자동화 확장 시스템
- C-1: 리드 자동 분류 및 우선순위
- C-2: 바이럴 타겟 자동 추천
- C-3: 경쟁사 대응 자동화
- C-4: 일일 브리핑 자동 생성
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# DB 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'


def get_db_connection():
    """SQLite 연결 생성"""
    return sqlite3.connect(str(DB_PATH))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-1: 리드 자동 분류 및 우선순위
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LeadAutoClassifier:
    """
    리드 자동 분류 및 우선순위 시스템

    기능:
    - Hot 리드 자동 감지
    - Intelligence 기반 전환 확률 예측
    - 자동 우선순위 할당
    - 알림 생성
    """

    def __init__(self):
        self.hot_threshold = 75  # Hot 리드 점수 임계값
        self.warm_threshold = 55  # Warm 리드 점수 임계값

    def classify_new_leads(self) -> Dict[str, Any]:
        """
        신규 리드 자동 분류

        [안정성 개선] 트랜잭션 + 처리 중 상태로 중복 실행 방지
        - auto_classified: 0=미분류, -1=처리중, 1=완료

        Returns:
            분류 결과 요약
        """
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        results = {
            'total_processed': 0,
            'hot_leads': [],
            'warm_leads': [],
            'notifications_created': 0
        }

        lead_ids_to_process = []

        try:
            # [안정성 개선] 즉시 쓰기 잠금으로 트랜잭션 시작
            cursor.execute("BEGIN IMMEDIATE")

            # 미분류 리드 조회 (최근 24시간) - 처리 중(-1) 제외
            cursor.execute("""
                SELECT id, title, content, platform, matched_keyword, created_at, score
                FROM mentions
                WHERE created_at >= datetime('now', '-1 day')
                AND (auto_classified IS NULL OR auto_classified = 0)
                LIMIT 100
            """)
            leads = cursor.fetchall()

            if not leads:
                conn.commit()
                return results

            # [안정성 개선] 처리할 리드 ID 추출 및 처리 중(-1) 상태로 마킹
            lead_ids_to_process = [lead[0] for lead in leads]
            if lead_ids_to_process:
                placeholders = ','.join('?' * len(lead_ids_to_process))
                cursor.execute(f"""
                    UPDATE mentions
                    SET auto_classified = -1
                    WHERE id IN ({placeholders})
                """, lead_ids_to_process)

            # 트랜잭션 커밋 (처리 중 상태 저장)
            conn.commit()

            # Intelligence 서비스 로드 (트랜잭션 외부에서)
            from services.intelligence import ConversionPatternLearner
            from services.lead_scorer import get_lead_scorer, get_trust_scorer

            pattern_learner = ConversionPatternLearner()
            lead_scorer = get_lead_scorer()
            trust_scorer = get_trust_scorer()

            # [안정성 개선] 개별 리드 처리 - 하나가 실패해도 나머지는 계속 처리
            for lead in leads:
                lead_id = lead[0]
                title = lead[1]
                content = lead[2]
                platform = lead[3]
                keyword = lead[4]
                created_at = lead[5]
                existing_score = lead[6]

                try:
                    # 리드 데이터 구성
                    lead_data = {
                        'id': lead_id,
                        'title': title,
                        'content': content,
                        'platform': platform,
                        'matched_keyword': keyword,
                        'created_at': created_at,
                        'score': existing_score
                    }

                    # 점수가 없으면 새로 계산
                    if not existing_score:
                        score_result = lead_scorer.calculate_score(lead_data)
                        trust_result = trust_scorer.calculate_trust_score(lead_data)
                        total_score = score_result['score']

                        # 점수 업데이트
                        cursor.execute("""
                            UPDATE mentions
                            SET score = ?, grade = ?, trust_score = ?, auto_classified = 1
                            WHERE id = ?
                        """, (total_score, score_result['grade'], trust_result['trust_score'], lead_id))
                    else:
                        total_score = existing_score
                        cursor.execute("UPDATE mentions SET auto_classified = 1 WHERE id = ?", (lead_id,))

                    conn.commit()  # 개별 리드마다 커밋

                    # 전환 확률 예측
                    prediction = pattern_learner.predict_conversion_probability(lead_data)

                    # Hot 리드 처리
                    if total_score >= self.hot_threshold:
                        results['hot_leads'].append({
                            'id': lead_id,
                            'title': title[:50] if title else '',
                            'score': total_score,
                            'conversion_prob': prediction['predicted_probability'],
                            'platform': platform
                        })

                        # Hot 리드 알림 생성
                        self._create_hot_lead_notification(cursor, lead_id, title or '', total_score, platform)
                        conn.commit()
                        results['notifications_created'] += 1

                    elif total_score >= self.warm_threshold:
                        results['warm_leads'].append({
                            'id': lead_id,
                            'title': title[:50] if title else '',
                            'score': total_score,
                            'platform': platform
                        })

                    results['total_processed'] += 1

                except Exception as lead_error:
                    # 개별 리드 처리 실패 시 로깅하고 계속 진행
                    logger.warning(f"[자동화] 리드 {lead_id} 분류 실패 (계속 진행): {lead_error}")
                    # 실패한 리드는 미분류(0) 상태로 되돌림
                    try:
                        cursor.execute("UPDATE mentions SET auto_classified = 0 WHERE id = ?", (lead_id,))
                        conn.commit()
                    except Exception:
                        pass

            logger.info(f"[자동화] {results['total_processed']}개 리드 분류 완료, Hot: {len(results['hot_leads'])}")

        except Exception as e:
            logger.error(f"[자동화] 리드 분류 오류: {e}")
            # 처리 중 상태로 남은 리드들 복구
            if lead_ids_to_process:
                try:
                    placeholders = ','.join('?' * len(lead_ids_to_process))
                    cursor.execute(f"""
                        UPDATE mentions
                        SET auto_classified = 0
                        WHERE id IN ({placeholders}) AND auto_classified = -1
                    """, lead_ids_to_process)
                    conn.commit()
                except Exception:
                    pass
        finally:
            conn.close()

        return results

    def _create_hot_lead_notification(self, cursor, lead_id: int, title: str, score: int, platform: str):
        """Hot 리드 발견 알림 생성"""
        cursor.execute("""
            INSERT INTO notifications (type, title, message, priority, reference_keyword, link, is_read, created_at)
            VALUES ('lead', ?, ?, 'critical', ?, ?, 0, datetime('now'))
        """, (
            f"Hot 리드 발견! (점수: {score})",
            f"[{platform}] {title[:40]}...",
            platform,
            f"/leads?id={lead_id}"
        ))

    def get_priority_queue(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        우선순위 리드 큐 조회

        Returns:
            우선순위순 리드 목록
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    id, title, content, platform, matched_keyword,
                    score, grade, trust_score, created_at
                FROM mentions
                WHERE status IN ('New', 'pending')
                AND score IS NOT NULL
                ORDER BY score DESC, created_at DESC
                LIMIT ?
            """, (limit,))

            leads = []
            for row in cursor.fetchall():
                leads.append({
                    'id': row[0],
                    'title': row[1],
                    'content': row[2][:100] if row[2] else '',
                    'platform': row[3],
                    'keyword': row[4],
                    'score': row[5],
                    'grade': row[6],
                    'trust_score': row[7],
                    'created_at': row[8]
                })

            return leads

        except Exception as e:
            logger.error(f"[자동화] 우선순위 큐 조회 오류: {e}")
            return []
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-2: 바이럴 타겟 자동 추천
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ViralTargetRecommender:
    """
    바이럴 타겟 자동 추천 시스템

    기능:
    - 전환율 높은 플랫폼/시간대 기반 추천
    - 경쟁 키워드 기반 타겟 발굴
    - 우선순위 큐 생성
    """

    def get_recommended_targets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        추천 바이럴 타겟 목록 조회

        Returns:
            추천 타겟 목록 (우선순위순)
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        recommendations = []

        try:
            # 1. 미처리 바이럴 타겟 중 고점수 게시물
            cursor.execute("""
                SELECT
                    vt.id, vt.title, vt.url, vt.platform, vt.matched_keyword,
                    vt.created_at, vt.comment_status
                FROM viral_targets vt
                WHERE vt.comment_status IS NULL OR vt.comment_status = 'pending'
                ORDER BY vt.created_at DESC
                LIMIT ?
            """, (limit * 2,))

            targets = cursor.fetchall()

            # 2. Intelligence 기반 우선순위 계산
            from services.intelligence import ConversionPatternLearner, TimingRecommender
            pattern_learner = ConversionPatternLearner()
            timing_recommender = TimingRecommender()

            current_recommendations = timing_recommender.get_current_recommendations()
            is_good_timing = len(current_recommendations) > 0

            for target in targets:
                target_id, title, url, platform, keyword, created_at, status = target

                # 전환 확률 예측
                prediction = pattern_learner.predict_conversion_probability({
                    'platform': platform,
                    'matched_keyword': keyword
                })

                # 우선순위 점수 계산
                priority_score = prediction['predicted_probability'] * 100

                # 좋은 타이밍이면 보너스
                if is_good_timing:
                    priority_score += 10

                # 최근 게시물 보너스
                if created_at:
                    try:
                        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        hours_old = (datetime.now() - created.replace(tzinfo=None)).total_seconds() / 3600
                        if hours_old < 24:
                            priority_score += 15
                        elif hours_old < 48:
                            priority_score += 10
                    except Exception:
                        pass

                recommendations.append({
                    'id': target_id,
                    'title': title,
                    'url': url,
                    'platform': platform,
                    'keyword': keyword,
                    'priority_score': round(priority_score, 2),
                    'conversion_probability': prediction['predicted_probability'],
                    'recommendation': prediction['recommendation'],
                    'is_good_timing': is_good_timing
                })

            # 우선순위순 정렬
            recommendations.sort(key=lambda x: x['priority_score'], reverse=True)

        except Exception as e:
            logger.error(f"[자동화] 바이럴 타겟 추천 오류: {e}")
        finally:
            conn.close()

        return recommendations[:limit]

    def get_keyword_opportunities(self) -> List[Dict[str, Any]]:
        """
        키워드 기반 바이럴 기회 분석

        Returns:
            키워드별 바이럴 기회 목록
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        opportunities = []

        try:
            # 순위 하락 중인 키워드 - 바이럴 강화 필요
            cursor.execute("""
                SELECT keyword, predicted_rank, current_rank, trend
                FROM rank_predictions
                WHERE predicted_at >= datetime('now', '-1 day')
                AND trend = 'falling'
                ORDER BY (predicted_rank - current_rank) DESC
                LIMIT 5
            """)

            for row in cursor.fetchall():
                keyword, predicted, current, trend = row
                opportunities.append({
                    'keyword': keyword,
                    'type': 'rank_defense',
                    'current_rank': current,
                    'predicted_rank': predicted,
                    'priority': 'high',
                    'action': f"'{keyword}' 키워드 바이럴 활동 강화 권장 - 순위 하락 예상"
                })

            # 상승 중인 키워드 - 모멘텀 유지
            cursor.execute("""
                SELECT keyword, predicted_rank, current_rank, trend
                FROM rank_predictions
                WHERE predicted_at >= datetime('now', '-1 day')
                AND trend = 'rising'
                AND current_rank > 10
                ORDER BY (current_rank - predicted_rank) DESC
                LIMIT 3
            """)

            for row in cursor.fetchall():
                keyword, predicted, current, trend = row
                opportunities.append({
                    'keyword': keyword,
                    'type': 'momentum',
                    'current_rank': current,
                    'predicted_rank': predicted,
                    'priority': 'medium',
                    'action': f"'{keyword}' 키워드 상승 중 - 바이럴로 Top 10 진입 가속"
                })

        except Exception as e:
            logger.error(f"[자동화] 키워드 기회 분석 오류: {e}")
        finally:
            conn.close()

        return opportunities


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-3: 경쟁사 대응 자동화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CompetitorResponseAutomation:
    """
    경쟁사 대응 자동화 시스템

    기능:
    - 경쟁사 순위 급상승 감지
    - 자동 대응 전략 생성
    - 알림 및 액션 트리거
    """

    def analyze_competitor_threats(self) -> List[Dict[str, Any]]:
        """
        경쟁사 위협 분석

        Returns:
            경쟁사 위협 목록 및 대응 전략
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        threats = []

        try:
            # 경쟁사 순위 급상승 감지 (최근 7일 vs 이전 7일)
            cursor.execute("""
                SELECT
                    cr.competitor_name,
                    cr.keyword,
                    cr.rank as current_rank,
                    prev.avg_rank as prev_avg_rank
                FROM competitor_rankings cr
                JOIN (
                    SELECT competitor_name, keyword, AVG(rank) as avg_rank
                    FROM competitor_rankings
                    WHERE scanned_at >= datetime('now', '-14 days')
                    AND scanned_at < datetime('now', '-7 days')
                    GROUP BY competitor_name, keyword
                ) prev ON cr.competitor_name = prev.competitor_name AND cr.keyword = prev.keyword
                WHERE cr.scanned_at >= datetime('now', '-1 day')
                AND cr.rank < prev.avg_rank - 5
                ORDER BY (prev.avg_rank - cr.rank) DESC
                LIMIT 10
            """)

            for row in cursor.fetchall():
                competitor, keyword, current, prev_avg = row
                rank_change = int(prev_avg - current)

                threat_level = 'critical' if rank_change >= 10 else 'high' if rank_change >= 5 else 'medium'

                response_strategies = self._generate_response_strategies(keyword, competitor, current, rank_change)

                threats.append({
                    'competitor': competitor,
                    'keyword': keyword,
                    'current_rank': current,
                    'previous_rank': int(prev_avg),
                    'rank_change': rank_change,
                    'threat_level': threat_level,
                    'response_strategies': response_strategies
                })

        except Exception as e:
            logger.error(f"[자동화] 경쟁사 위협 분석 오류: {e}")
        finally:
            conn.close()

        return threats

    def _generate_response_strategies(self, keyword: str, competitor: str, current_rank: int, rank_change: int) -> List[Dict[str, str]]:
        """경쟁사 대응 전략 생성"""
        strategies = []

        # 바이럴 강화 전략
        strategies.append({
            'type': 'viral',
            'action': f"'{keyword}' 키워드 바이럴 활동 2배 강화",
            'priority': 'immediate'
        })

        # 콘텐츠 전략
        if current_rank <= 5:
            strategies.append({
                'type': 'content',
                'action': f"'{keyword}' 관련 블로그/영상 콘텐츠 제작",
                'priority': 'high'
            })

        # 리뷰 요청 전략
        if rank_change >= 7:
            strategies.append({
                'type': 'review',
                'action': "기존 고객 리뷰 요청 캠페인 실행",
                'priority': 'medium'
            })

        return strategies

    def create_competitor_alert(self, competitor: str, keyword: str, rank_change: int) -> int:
        """경쟁사 급상승 알림 생성"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO notifications (type, title, message, priority, reference_keyword, link, is_read, created_at)
                VALUES ('competitor', ?, ?, 'critical', ?, ?, 0, datetime('now'))
            """, (
                f"경쟁사 급상승: {competitor}",
                f"'{keyword}' 키워드에서 {rank_change}순위 상승!",
                keyword,
                f"/battle?keyword={keyword}"
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"[자동화] 경쟁사 알림 생성 오류: {e}")
            return 0
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C-4: 일일 브리핑 자동 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DailyBriefingGenerator:
    """
    일일 마케팅 브리핑 자동 생성

    구성:
    - 순위 변동 요약
    - 리드 현황 요약
    - 경쟁사 동향
    - AI 추천 액션
    """

    def generate_briefing(self) -> Dict[str, Any]:
        """
        일일 브리핑 생성

        Returns:
            브리핑 데이터
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        briefing = {
            'generated_at': datetime.now().isoformat(),
            'period': 'daily',
            'rank_summary': {},
            'lead_summary': {},
            'competitor_summary': {},
            'viral_summary': {},
            'recommended_actions': [],
            'highlights': []
        }

        try:
            # 1. 순위 변동 요약
            briefing['rank_summary'] = self._get_rank_summary(cursor)

            # 2. 리드 현황 요약
            briefing['lead_summary'] = self._get_lead_summary(cursor)

            # 3. 경쟁사 동향
            briefing['competitor_summary'] = self._get_competitor_summary(cursor)

            # 4. 바이럴 현황
            briefing['viral_summary'] = self._get_viral_summary(cursor)

            # 5. 추천 액션 생성
            briefing['recommended_actions'] = self._generate_recommended_actions(briefing)

            # 6. 하이라이트 생성
            briefing['highlights'] = self._generate_highlights(briefing)

            # 브리핑 저장
            self._save_briefing(cursor, briefing)
            conn.commit()

        except Exception as e:
            logger.error(f"[자동화] 브리핑 생성 오류: {e}")
        finally:
            conn.close()

        return briefing

    def _get_rank_summary(self, cursor) -> Dict[str, Any]:
        """순위 변동 요약"""
        summary = {
            'total_keywords': 0,
            'improved': 0,
            'declined': 0,
            'stable': 0,
            'top_10_count': 0,
            'notable_changes': []
        }

        try:
            # 오늘 vs 어제 순위 비교
            cursor.execute("""
                SELECT
                    today.keyword,
                    today.rank as today_rank,
                    yesterday.rank as yesterday_rank
                FROM (
                    SELECT keyword, rank FROM rank_history
                    WHERE date = date('now') AND status = 'found'
                ) today
                LEFT JOIN (
                    SELECT keyword, rank FROM rank_history
                    WHERE date = date('now', '-1 day') AND status = 'found'
                ) yesterday ON today.keyword = yesterday.keyword
            """)

            for row in cursor.fetchall():
                keyword, today, yesterday = row
                summary['total_keywords'] += 1

                if today <= 10:
                    summary['top_10_count'] += 1

                if yesterday:
                    change = yesterday - today
                    if change > 0:
                        summary['improved'] += 1
                        if change >= 3:
                            summary['notable_changes'].append({
                                'keyword': keyword,
                                'type': 'improved',
                                'from': yesterday,
                                'to': today,
                                'change': change
                            })
                    elif change < 0:
                        summary['declined'] += 1
                        if abs(change) >= 3:
                            summary['notable_changes'].append({
                                'keyword': keyword,
                                'type': 'declined',
                                'from': yesterday,
                                'to': today,
                                'change': change
                            })
                    else:
                        summary['stable'] += 1

        except Exception as e:
            logger.debug(f"순위 요약 조회 오류: {e}")

        return summary

    def _get_lead_summary(self, cursor) -> Dict[str, Any]:
        """리드 현황 요약"""
        summary = {
            'new_today': 0,
            'hot_leads': 0,
            'pending': 0,
            'converted_today': 0,
            'top_platforms': []
        }

        try:
            # 오늘 신규 리드
            cursor.execute("""
                SELECT COUNT(*) FROM mentions
                WHERE created_at >= date('now')
            """)
            summary['new_today'] = cursor.fetchone()[0] or 0

            # Hot 리드 (점수 75점 이상)
            cursor.execute("""
                SELECT COUNT(*) FROM mentions
                WHERE score >= 75 AND status IN ('New', 'pending')
            """)
            summary['hot_leads'] = cursor.fetchone()[0] or 0

            # 대기 중
            cursor.execute("""
                SELECT COUNT(*) FROM mentions
                WHERE status IN ('New', 'pending')
            """)
            summary['pending'] = cursor.fetchone()[0] or 0

            # 오늘 전환
            cursor.execute("""
                SELECT COUNT(*) FROM lead_conversions
                WHERE converted_at >= date('now')
            """)
            summary['converted_today'] = cursor.fetchone()[0] or 0

            # 플랫폼별 리드 수
            cursor.execute("""
                SELECT COALESCE(platform, source, 'unknown') as platform, COUNT(*) as count
                FROM mentions
                WHERE created_at >= date('now', '-7 days')
                GROUP BY platform
                ORDER BY count DESC
                LIMIT 3
            """)
            summary['top_platforms'] = [{'platform': r[0], 'count': r[1]} for r in cursor.fetchall()]

        except Exception as e:
            logger.debug(f"리드 요약 조회 오류: {e}")

        return summary

    def _get_competitor_summary(self, cursor) -> Dict[str, Any]:
        """경쟁사 동향 요약"""
        summary = {
            'threats_detected': 0,
            'competitors_improved': [],
            'competitors_declined': []
        }

        try:
            cursor.execute("""
                SELECT competitor_name, COUNT(*) as improved_count
                FROM competitor_rankings cr
                WHERE scanned_at >= date('now', '-1 day')
                AND rank < (
                    SELECT AVG(rank) FROM competitor_rankings cr2
                    WHERE cr2.competitor_name = cr.competitor_name
                    AND cr2.keyword = cr.keyword
                    AND cr2.scanned_at >= date('now', '-7 days')
                    AND cr2.scanned_at < date('now', '-1 day')
                )
                GROUP BY competitor_name
                ORDER BY improved_count DESC
                LIMIT 3
            """)
            summary['competitors_improved'] = [{'name': r[0], 'count': r[1]} for r in cursor.fetchall()]
            summary['threats_detected'] = len(summary['competitors_improved'])

        except Exception as e:
            logger.debug(f"경쟁사 요약 조회 오류: {e}")

        return summary

    def _get_viral_summary(self, cursor) -> Dict[str, Any]:
        """바이럴 현황 요약"""
        summary = {
            'total_targets': 0,
            'completed_today': 0,
            'pending': 0,
            'completion_rate': 0
        }

        try:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN comment_status = 'completed' OR comment_status = 'posted' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN comment_status IS NULL OR comment_status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM viral_targets
            """)
            row = cursor.fetchone()
            if row:
                summary['total_targets'] = row[0] or 0
                summary['completed_today'] = row[1] or 0
                summary['pending'] = row[2] or 0
                if summary['total_targets'] > 0:
                    summary['completion_rate'] = round(summary['completed_today'] / summary['total_targets'] * 100, 1)

        except Exception as e:
            logger.debug(f"바이럴 요약 조회 오류: {e}")

        return summary

    def _generate_recommended_actions(self, briefing: Dict[str, Any]) -> List[Dict[str, Any]]:
        """추천 액션 생성"""
        actions = []

        # 순위 하락 대응
        rank_summary = briefing.get('rank_summary', {})
        if rank_summary.get('declined', 0) > 2:
            actions.append({
                'type': 'rank_defense',
                'priority': 'high',
                'action': f"{rank_summary['declined']}개 키워드 순위 하락 - 바이럴 활동 강화 필요",
                'target': '하락 키워드'
            })

        # Hot 리드 처리
        lead_summary = briefing.get('lead_summary', {})
        if lead_summary.get('hot_leads', 0) > 0:
            actions.append({
                'type': 'lead_response',
                'priority': 'critical',
                'action': f"{lead_summary['hot_leads']}개 Hot 리드 즉시 대응 필요",
                'target': 'Hot 리드'
            })

        # 경쟁사 대응
        competitor_summary = briefing.get('competitor_summary', {})
        if competitor_summary.get('threats_detected', 0) > 0:
            actions.append({
                'type': 'competitor_response',
                'priority': 'high',
                'action': f"{competitor_summary['threats_detected']}개 경쟁사 순위 상승 감지 - 대응 전략 실행",
                'target': '경쟁사'
            })

        # 바이럴 활동
        viral_summary = briefing.get('viral_summary', {})
        if viral_summary.get('pending', 0) > 50:
            actions.append({
                'type': 'viral',
                'priority': 'medium',
                'action': f"{viral_summary['pending']}개 바이럴 타겟 대기 중 - 댓글 작성 진행",
                'target': '바이럴 타겟'
            })

        return actions

    def _generate_highlights(self, briefing: Dict[str, Any]) -> List[str]:
        """하이라이트 생성"""
        highlights = []

        rank_summary = briefing.get('rank_summary', {})
        lead_summary = briefing.get('lead_summary', {})

        # 긍정적 하이라이트
        if rank_summary.get('improved', 0) > 0:
            highlights.append(f"{rank_summary['improved']}개 키워드 순위 상승")

        if rank_summary.get('top_10_count', 0) > 0:
            highlights.append(f"{rank_summary['top_10_count']}개 키워드 Top 10 유지 중")

        if lead_summary.get('converted_today', 0) > 0:
            highlights.append(f"오늘 {lead_summary['converted_today']}건 전환 발생")

        if lead_summary.get('new_today', 0) > 0:
            highlights.append(f"오늘 {lead_summary['new_today']}개 신규 리드 발견")

        return highlights

    def _save_briefing(self, cursor, briefing: Dict[str, Any]):
        """브리핑 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                period TEXT DEFAULT 'daily',
                content TEXT NOT NULL,
                highlights TEXT,
                actions_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            INSERT INTO daily_briefings (generated_at, period, content, highlights, actions_count)
            VALUES (?, ?, ?, ?, ?)
        """, (
            briefing['generated_at'],
            briefing['period'],
            json.dumps(briefing, ensure_ascii=False),
            json.dumps(briefing.get('highlights', []), ensure_ascii=False),
            len(briefing.get('recommended_actions', []))
        ))

    def get_latest_briefing(self) -> Optional[Dict[str, Any]]:
        """최신 브리핑 조회"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT content FROM daily_briefings
                ORDER BY generated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"[자동화] 브리핑 조회 오류: {e}")
            return None
        finally:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 자동화 서비스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MarketingAutomation:
    """통합 마케팅 자동화 서비스"""

    def __init__(self):
        self.lead_classifier = LeadAutoClassifier()
        self.viral_recommender = ViralTargetRecommender()
        self.competitor_response = CompetitorResponseAutomation()
        self.briefing_generator = DailyBriefingGenerator()

    def run_daily_automation(self) -> Dict[str, Any]:
        """일일 자동화 작업 실행"""
        logger.info("[자동화] 일일 자동화 작업 시작...")

        results = {
            'lead_classification': None,
            'competitor_analysis': None,
            'briefing': None,
            'errors': []
        }

        # 1. 리드 자동 분류
        try:
            results['lead_classification'] = self.lead_classifier.classify_new_leads()
            logger.info("[자동화] 리드 분류 완료")
        except Exception as e:
            results['errors'].append(f"리드 분류: {e}")

        # 2. 경쟁사 위협 분석
        try:
            results['competitor_analysis'] = self.competitor_response.analyze_competitor_threats()
            logger.info("[자동화] 경쟁사 분석 완료")
        except Exception as e:
            results['errors'].append(f"경쟁사 분석: {e}")

        # 3. 일일 브리핑 생성
        try:
            results['briefing'] = self.briefing_generator.generate_briefing()
            logger.info("[자동화] 일일 브리핑 생성 완료")
        except Exception as e:
            results['errors'].append(f"브리핑: {e}")

        logger.info("[자동화] 일일 자동화 작업 완료")
        return results


# 싱글톤 인스턴스
_automation_instance = None


def get_marketing_automation() -> MarketingAutomation:
    """MarketingAutomation 싱글톤 인스턴스 반환"""
    global _automation_instance
    if _automation_instance is None:
        _automation_instance = MarketingAutomation()
    return _automation_instance
