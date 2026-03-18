"""
Marketing Intelligence Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase B] AI 기반 지능화 시스템
- B-1: 전환 패턴 학습 (ConversionPatternLearner)
- B-2: 댓글 효과 분석 (CommentEffectivenessAnalyzer)
- B-3: 순위 변동 예측 (RankPredictor)
- B-4: 최적 타이밍 추천 (TimingRecommender)
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
# B-1: 전환 패턴 학습
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConversionPatternLearner:
    """
    전환된 리드의 공통 패턴을 학습하여 전환 확률 예측 정확도 향상

    학습 요소:
    - 플랫폼별 전환율
    - 키워드별 전환율
    - 시간대별 전환율
    - 점수 구간별 전환율
    - 응답 시간 영향
    """

    def __init__(self):
        self.patterns = {}
        self._load_patterns()

    def _load_patterns(self):
        """저장된 패턴 로드"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # conversion_patterns 테이블에서 로드
            cursor.execute("""
                SELECT pattern_type, pattern_key, conversion_rate, sample_count, updated_at
                FROM conversion_patterns
                WHERE sample_count >= 5
            """)
            rows = cursor.fetchall()

            for row in rows:
                pattern_type, pattern_key, rate, count, updated = row
                if pattern_type not in self.patterns:
                    self.patterns[pattern_type] = {}
                self.patterns[pattern_type][pattern_key] = {
                    'conversion_rate': rate,
                    'sample_count': count,
                    'updated_at': updated
                }

            conn.close()
            logger.debug(f"[Intelligence] {len(self.patterns)} 패턴 카테고리 로드됨")

        except Exception as e:
            logger.debug(f"[Intelligence] 패턴 로드 스킵 (테이블 없음 또는 오류): {e}")
            self.patterns = {}

    def learn_from_conversions(self) -> Dict[str, Any]:
        """
        전환 데이터에서 패턴 학습

        Returns:
            학습 결과 요약
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        results = {
            'platform_patterns': {},
            'keyword_patterns': {},
            'time_patterns': {},
            'score_patterns': {},
            'total_conversions': 0,
            'total_leads': 0
        }

        try:
            # 1. 플랫폼별 전환율 계산
            cursor.execute("""
                SELECT
                    COALESCE(m.platform, m.source, 'unknown') as platform,
                    COUNT(*) as total_leads,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                GROUP BY platform
                HAVING total_leads >= 3
            """)

            for row in cursor.fetchall():
                platform, total, conversions = row
                rate = conversions / total if total > 0 else 0
                results['platform_patterns'][platform] = {
                    'conversion_rate': round(rate, 4),
                    'total_leads': total,
                    'conversions': conversions
                }
                results['total_leads'] += total
                results['total_conversions'] += conversions

            # 2. 키워드별 전환율 계산
            cursor.execute("""
                SELECT
                    COALESCE(m.matched_keyword, 'unknown') as keyword,
                    COUNT(*) as total_leads,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                AND m.matched_keyword IS NOT NULL AND m.matched_keyword != ''
                GROUP BY keyword
                HAVING total_leads >= 3
            """)

            for row in cursor.fetchall():
                keyword, total, conversions = row
                rate = conversions / total if total > 0 else 0
                results['keyword_patterns'][keyword] = {
                    'conversion_rate': round(rate, 4),
                    'total_leads': total,
                    'conversions': conversions
                }

            # 3. 시간대별 전환율 (요일 + 시간)
            cursor.execute("""
                SELECT
                    strftime('%w', m.created_at) as day_of_week,
                    CAST(strftime('%H', m.created_at) / 4 AS INTEGER) as time_slot,
                    COUNT(*) as total_leads,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                GROUP BY day_of_week, time_slot
                HAVING total_leads >= 3
            """)

            day_names = ['일', '월', '화', '수', '목', '금', '토']
            time_slots = ['새벽(0-4)', '아침(4-8)', '오전(8-12)', '오후(12-16)', '저녁(16-20)', '밤(20-24)']

            for row in cursor.fetchall():
                day_idx, slot_idx, total, conversions = row
                if day_idx is None or slot_idx is None:
                    continue
                day_name = day_names[int(day_idx)]
                slot_name = time_slots[int(slot_idx)] if int(slot_idx) < len(time_slots) else '기타'
                key = f"{day_name}_{slot_name}"
                rate = conversions / total if total > 0 else 0
                results['time_patterns'][key] = {
                    'conversion_rate': round(rate, 4),
                    'total_leads': total,
                    'conversions': conversions
                }

            # 4. 점수 구간별 전환율 (mentions 테이블에 score 컬럼이 있다면)
            cursor.execute("PRAGMA table_info(mentions)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'score' in columns:
                cursor.execute("""
                    SELECT
                        CASE
                            WHEN score >= 80 THEN 'hot'
                            WHEN score >= 60 THEN 'warm'
                            WHEN score >= 40 THEN 'cool'
                            ELSE 'cold'
                        END as score_grade,
                        COUNT(*) as total_leads,
                        SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                    FROM mentions m
                    LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                    WHERE m.created_at >= datetime('now', '-90 days')
                    AND m.score IS NOT NULL
                    GROUP BY score_grade
                """)

                for row in cursor.fetchall():
                    grade, total, conversions = row
                    rate = conversions / total if total > 0 else 0
                    results['score_patterns'][grade] = {
                        'conversion_rate': round(rate, 4),
                        'total_leads': total,
                        'conversions': conversions
                    }

            # 패턴 저장
            self._save_patterns(cursor, results)
            conn.commit()

        except Exception as e:
            logger.error(f"[Intelligence] 전환 패턴 학습 오류: {e}")
            conn.rollback()
        finally:
            conn.close()

        return results

    def _save_patterns(self, cursor, results: Dict[str, Any]):
        """학습된 패턴을 DB에 저장"""
        now = datetime.now().isoformat()

        # conversion_patterns 테이블 생성 (없으면)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversion_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                conversion_rate REAL DEFAULT 0,
                sample_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pattern_type, pattern_key)
            )
        """)

        patterns_to_save = []

        for platform, data in results.get('platform_patterns', {}).items():
            patterns_to_save.append(('platform', platform, data['conversion_rate'], data['total_leads']))

        for keyword, data in results.get('keyword_patterns', {}).items():
            patterns_to_save.append(('keyword', keyword, data['conversion_rate'], data['total_leads']))

        for time_key, data in results.get('time_patterns', {}).items():
            patterns_to_save.append(('time', time_key, data['conversion_rate'], data['total_leads']))

        for grade, data in results.get('score_patterns', {}).items():
            patterns_to_save.append(('score', grade, data['conversion_rate'], data['total_leads']))

        for pattern_type, pattern_key, rate, count in patterns_to_save:
            cursor.execute("""
                INSERT OR REPLACE INTO conversion_patterns
                (pattern_type, pattern_key, conversion_rate, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (pattern_type, pattern_key, rate, count, now))

        logger.info(f"[Intelligence] {len(patterns_to_save)}개 전환 패턴 저장됨")

    def predict_conversion_probability(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        리드의 전환 확률 예측 (학습된 패턴 기반)

        Args:
            lead: 리드 정보 (platform, keyword, score 등)

        Returns:
            예측 결과 및 근거
        """
        base_probability = 0.05  # 기본 전환율 5%
        factors = []

        # 플랫폼 기반 조정
        platform = (lead.get('platform') or lead.get('source') or 'unknown').lower()
        if 'platform' in self.patterns:
            for p_key, p_data in self.patterns.get('platform', {}).items():
                if p_key.lower() in platform:
                    platform_rate = p_data['conversion_rate']
                    if platform_rate > 0:
                        adjustment = (platform_rate - base_probability) * 0.5
                        base_probability += adjustment
                        factors.append({
                            'factor': 'platform',
                            'value': p_key,
                            'impact': round(adjustment, 4)
                        })
                    break

        # 키워드 기반 조정
        keyword = lead.get('matched_keyword') or lead.get('keyword') or ''
        if keyword and 'keyword' in self.patterns:
            keyword_data = self.patterns.get('keyword', {}).get(keyword)
            if keyword_data:
                keyword_rate = keyword_data['conversion_rate']
                adjustment = (keyword_rate - base_probability) * 0.3
                base_probability += adjustment
                factors.append({
                    'factor': 'keyword',
                    'value': keyword,
                    'impact': round(adjustment, 4)
                })

        # 점수 기반 조정
        score = lead.get('score', 0)
        if score and 'score' in self.patterns:
            if score >= 80:
                grade = 'hot'
            elif score >= 60:
                grade = 'warm'
            elif score >= 40:
                grade = 'cool'
            else:
                grade = 'cold'

            score_data = self.patterns.get('score', {}).get(grade)
            if score_data:
                score_rate = score_data['conversion_rate']
                adjustment = (score_rate - base_probability) * 0.4
                base_probability += adjustment
                factors.append({
                    'factor': 'score_grade',
                    'value': grade,
                    'impact': round(adjustment, 4)
                })

        # 확률 범위 제한 (1% ~ 80%)
        final_probability = max(0.01, min(0.80, base_probability))

        return {
            'predicted_probability': round(final_probability, 4),
            'confidence': 'high' if len(factors) >= 2 else 'medium' if len(factors) == 1 else 'low',
            'factors': factors,
            'recommendation': self._get_recommendation(final_probability)
        }

    def _get_recommendation(self, probability: float) -> str:
        """확률 기반 추천 메시지"""
        if probability >= 0.3:
            return "즉시 대응 권장 - 전환 가능성 높음"
        elif probability >= 0.15:
            return "당일 내 대응 권장 - 전환 가능성 중간"
        elif probability >= 0.08:
            return "2-3일 내 대응 - 전환 가능성 낮음"
        else:
            return "주간 리뷰 - 우선순위 낮음"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B-2: 댓글 효과 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CommentEffectivenessAnalyzer:
    """
    바이럴 댓글의 효과를 분석하여 어떤 스타일이 전환에 효과적인지 학습

    분석 요소:
    - 댓글 길이와 전환율 상관관계
    - 키워드 포함 여부와 전환율
    - 톤/스타일과 전환율
    - 템플릿별 성과
    """

    def analyze_comment_effectiveness(self) -> Dict[str, Any]:
        """댓글 효과 분석 실행"""
        conn = get_db_connection()
        cursor = conn.cursor()

        results = {
            'length_analysis': {},
            'template_analysis': {},
            'style_analysis': {},
            'best_practices': [],
            'recommendations': []
        }

        try:
            # 1. 댓글 길이별 분석
            cursor.execute("""
                SELECT
                    CASE
                        WHEN LENGTH(ch.content) < 50 THEN 'short'
                        WHEN LENGTH(ch.content) < 150 THEN 'medium'
                        ELSE 'long'
                    END as length_category,
                    COUNT(*) as total_comments,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as led_to_conversion
                FROM contact_history ch
                JOIN viral_targets vt ON ch.lead_id = vt.id
                LEFT JOIN lead_conversions lc ON vt.id = lc.lead_id
                WHERE ch.contact_type = 'comment' AND ch.created_at >= datetime('now', '-90 days')
                GROUP BY length_category
            """)

            for row in cursor.fetchall():
                length_cat, total, conversions = row
                rate = conversions / total if total > 0 else 0
                results['length_analysis'][length_cat] = {
                    'total': total,
                    'conversions': conversions,
                    'conversion_rate': round(rate, 4)
                }

            # 2. 템플릿별 분석 (contact_history에 template_id가 있다면)
            cursor.execute("PRAGMA table_info(contact_history)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'template_id' in columns:
                cursor.execute("""
                    SELECT
                        ct.name as template_name,
                        ct.situation_type,
                        COUNT(*) as uses,
                        SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                    FROM contact_history ch
                    JOIN comment_templates ct ON ch.template_id = ct.id
                    JOIN viral_targets vt ON ch.lead_id = vt.id
                    LEFT JOIN lead_conversions lc ON vt.id = lc.lead_id
                    WHERE ch.created_at >= datetime('now', '-90 days')
                    GROUP BY ct.id
                    HAVING uses >= 3
                    ORDER BY conversions DESC
                """)

                for row in cursor.fetchall():
                    name, situation, uses, conversions = row
                    rate = conversions / uses if uses > 0 else 0
                    results['template_analysis'][name] = {
                        'situation_type': situation,
                        'uses': uses,
                        'conversions': conversions,
                        'conversion_rate': round(rate, 4)
                    }

            # 3. 스타일 분석 (키워드 기반)
            style_keywords = {
                'question': ['?', '어떠세요', '괜찮으실까요', '해보시겠어요'],
                'recommendation': ['추천', '권해드려요', '좋아요', '만족'],
                'empathy': ['저도', '공감', '이해해요', '그러시죠'],
                'urgency': ['지금', '오늘', '바로', '빨리'],
                'benefit': ['효과', '결과', '혜택', '특별']
            }

            cursor.execute("""
                SELECT ch.content, CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END as converted
                FROM contact_history ch
                JOIN viral_targets vt ON ch.lead_id = vt.id
                LEFT JOIN lead_conversions lc ON vt.id = lc.lead_id
                WHERE ch.contact_type = 'comment' AND ch.created_at >= datetime('now', '-90 days')
            """)

            style_stats = {style: {'total': 0, 'conversions': 0} for style in style_keywords}

            for row in cursor.fetchall():
                content, converted = row
                if not content:
                    continue
                content_lower = content.lower()
                for style, keywords in style_keywords.items():
                    if any(kw in content_lower for kw in keywords):
                        style_stats[style]['total'] += 1
                        style_stats[style]['conversions'] += converted

            for style, stats in style_stats.items():
                if stats['total'] > 0:
                    rate = stats['conversions'] / stats['total']
                    results['style_analysis'][style] = {
                        'total': stats['total'],
                        'conversions': stats['conversions'],
                        'conversion_rate': round(rate, 4)
                    }

            # 4. 베스트 프랙티스 도출
            results['best_practices'] = self._derive_best_practices(results)
            results['recommendations'] = self._generate_recommendations(results)

            # 결과 저장
            self._save_effectiveness_data(cursor, results)
            conn.commit()

        except Exception as e:
            logger.error(f"[Intelligence] 댓글 효과 분석 오류: {e}")
            conn.rollback()
        finally:
            conn.close()

        return results

    def _derive_best_practices(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """분석 결과에서 베스트 프랙티스 도출"""
        practices = []

        # 길이 분석
        length_data = results.get('length_analysis', {})
        if length_data:
            best_length = max(length_data.items(), key=lambda x: x[1].get('conversion_rate', 0))
            if best_length[1].get('conversion_rate', 0) > 0:
                practices.append({
                    'category': 'length',
                    'recommendation': f"'{best_length[0]}' 길이의 댓글이 가장 효과적 (전환율: {best_length[1]['conversion_rate']*100:.1f}%)",
                    'conversion_rate': best_length[1]['conversion_rate']
                })

        # 스타일 분석
        style_data = results.get('style_analysis', {})
        if style_data:
            sorted_styles = sorted(style_data.items(), key=lambda x: x[1].get('conversion_rate', 0), reverse=True)
            for style, data in sorted_styles[:3]:
                if data.get('conversion_rate', 0) > 0.05:  # 5% 이상만
                    practices.append({
                        'category': 'style',
                        'recommendation': f"'{style}' 스타일 댓글 권장 (전환율: {data['conversion_rate']*100:.1f}%)",
                        'conversion_rate': data['conversion_rate']
                    })

        return practices

    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """분석 결과 기반 추천 생성"""
        recommendations = []

        # 길이 추천
        length_data = results.get('length_analysis', {})
        if 'medium' in length_data and length_data['medium'].get('conversion_rate', 0) > 0.05:
            recommendations.append("50-150자 정도의 적당한 길이의 댓글이 효과적입니다.")

        # 스타일 추천
        style_data = results.get('style_analysis', {})
        if style_data:
            top_styles = sorted(style_data.items(), key=lambda x: x[1].get('conversion_rate', 0), reverse=True)[:2]
            style_names = {'question': '질문형', 'recommendation': '추천형', 'empathy': '공감형', 'urgency': '긴급성', 'benefit': '혜택 강조'}
            for style, _ in top_styles:
                if style in style_names:
                    recommendations.append(f"{style_names[style]} 댓글 스타일을 활용해보세요.")

        if not recommendations:
            recommendations.append("더 많은 댓글 데이터가 쌓이면 상세한 추천이 가능합니다.")

        return recommendations

    def _save_effectiveness_data(self, cursor, results: Dict[str, Any]):
        """효과 분석 결과 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comment_effectiveness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_type TEXT NOT NULL,
                category TEXT NOT NULL,
                total_count INTEGER DEFAULT 0,
                conversion_count INTEGER DEFAULT 0,
                conversion_rate REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(analysis_type, category)
            )
        """)

        now = datetime.now().isoformat()

        # 길이 분석 저장
        for category, data in results.get('length_analysis', {}).items():
            cursor.execute("""
                INSERT OR REPLACE INTO comment_effectiveness
                (analysis_type, category, total_count, conversion_count, conversion_rate, updated_at)
                VALUES ('length', ?, ?, ?, ?, ?)
            """, (category, data['total'], data['conversions'], data['conversion_rate'], now))

        # 스타일 분석 저장
        for category, data in results.get('style_analysis', {}).items():
            cursor.execute("""
                INSERT OR REPLACE INTO comment_effectiveness
                (analysis_type, category, total_count, conversion_count, conversion_rate, updated_at)
                VALUES ('style', ?, ?, ?, ?, ?)
            """, (category, data['total'], data['conversions'], data['conversion_rate'], now))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B-3: 순위 변동 예측
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RankPredictor:
    """
    과거 순위 데이터를 기반으로 순위 변동 예측

    예측 요소:
    - 최근 트렌드 (상승/하락/유지)
    - 경쟁사 순위 변동
    - 바이럴 활동량
    - 계절성/요일 패턴
    """

    def predict_rank_changes(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """
        키워드별 순위 변동 예측

        Args:
            days_ahead: 예측 기간 (일)

        Returns:
            키워드별 예측 결과 리스트
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        predictions = []

        try:
            # 추적 중인 키워드 목록 조회
            cursor.execute("""
                SELECT DISTINCT keyword
                FROM rank_history
                WHERE date >= date('now', '-30 days')
                ORDER BY keyword
            """)
            keywords = [row[0] for row in cursor.fetchall()]

            for keyword in keywords:
                prediction = self._predict_keyword_rank(cursor, keyword, days_ahead)
                if prediction:
                    predictions.append(prediction)

            # 예측 결과 저장
            self._save_predictions(cursor, predictions)
            conn.commit()

        except Exception as e:
            logger.error(f"[Intelligence] 순위 예측 오류: {e}")
            conn.rollback()
        finally:
            conn.close()

        return predictions

    def _predict_keyword_rank(self, cursor, keyword: str, days_ahead: int) -> Optional[Dict[str, Any]]:
        """
        개별 키워드 순위 예측 (고도화 버전)

        예측 방법론:
        1. 지수 이동 평균 (EMA) - 최근 데이터에 가중치
        2. 요일별 패턴 분석 - 주중/주말 차이 반영
        3. 모멘텀 계산 - 변화 가속도 반영
        4. 신뢰 구간 제공 - 상한/하한 예측
        """
        # 최근 45일 순위 데이터 조회 (패턴 분석용)
        cursor.execute("""
            SELECT date, rank, status
            FROM rank_history
            WHERE keyword = ? AND date >= date('now', '-45 days')
            ORDER BY date DESC
        """, (keyword,))

        history = cursor.fetchall()

        if len(history) < 3:
            return None

        # 유효한 순위 데이터만 추출 (날짜, 순위, 요일)
        valid_ranks = []
        for row in history:
            if row[2] == 'found' and row[1] is not None:
                try:
                    date_obj = datetime.strptime(row[0][:10], '%Y-%m-%d')
                    valid_ranks.append({
                        'date': row[0],
                        'rank': row[1],
                        'weekday': date_obj.weekday()  # 0=월, 6=일
                    })
                except Exception:
                    valid_ranks.append({
                        'date': row[0],
                        'rank': row[1],
                        'weekday': None
                    })

        if len(valid_ranks) < 3:
            return None

        current_rank = valid_ranks[0]['rank']
        ranks_only = [r['rank'] for r in valid_ranks]

        # ─────────────────────────────────────────────
        # 1. 지수 이동 평균 (EMA) 계산
        # ─────────────────────────────────────────────
        alpha = 0.3  # 스무딩 팩터 (높을수록 최근 데이터 중시)
        ema = ranks_only[0]
        for rank in ranks_only[1:min(14, len(ranks_only))]:
            ema = alpha * rank + (1 - alpha) * ema

        # ─────────────────────────────────────────────
        # 2. 요일별 패턴 분석
        # ─────────────────────────────────────────────
        weekday_ranks = {i: [] for i in range(7)}
        for r in valid_ranks:
            if r['weekday'] is not None:
                weekday_ranks[r['weekday']].append(r['rank'])

        # 요일별 평균 순위 (데이터 충분 시)
        weekday_avg = {}
        overall_avg = sum(ranks_only) / len(ranks_only)
        for day, ranks in weekday_ranks.items():
            if len(ranks) >= 2:
                weekday_avg[day] = sum(ranks) / len(ranks)
            else:
                weekday_avg[day] = overall_avg

        # 예측일의 요일 패턴 반영
        target_weekday = (datetime.now().weekday() + days_ahead) % 7
        weekday_adjustment = weekday_avg.get(target_weekday, overall_avg) - overall_avg

        # ─────────────────────────────────────────────
        # 3. 트렌드 및 모멘텀 계산
        # ─────────────────────────────────────────────
        # 최근 7일 vs 이전 7일 비교
        recent_7 = ranks_only[:7] if len(ranks_only) >= 7 else ranks_only
        older_7 = ranks_only[7:14] if len(ranks_only) >= 14 else []

        recent_avg = sum(recent_7) / len(recent_7)
        older_avg = sum(older_7) / len(older_7) if older_7 else recent_avg

        # 1차 트렌드 (변화량)
        trend_delta = older_avg - recent_avg  # 양수 = 상승

        # 2차 트렌드 (가속도) - 최근 3일 vs 4-6일 전
        if len(ranks_only) >= 6:
            very_recent = sum(ranks_only[:3]) / 3
            slightly_older = sum(ranks_only[3:6]) / 3
            acceleration = (slightly_older - very_recent) - (trend_delta / 2)
        else:
            acceleration = 0

        # 트렌드 분류
        if trend_delta > 2 or (trend_delta > 0 and acceleration > 1):
            trend = 'rising'
            trend_strength = min(abs(trend_delta) / 5 + abs(acceleration) / 3, 1.0)
        elif trend_delta < -2 or (trend_delta < 0 and acceleration < -1):
            trend = 'falling'
            trend_strength = min(abs(trend_delta) / 5 + abs(acceleration) / 3, 1.0)
        else:
            trend = 'stable'
            trend_strength = 0.2

        # ─────────────────────────────────────────────
        # 4. 예측 순위 계산 (EMA + 트렌드 + 요일패턴)
        # ─────────────────────────────────────────────
        # 기본 예측 = EMA 기반
        base_prediction = ema

        # 트렌드 반영 (기간에 비례, 가속도 포함)
        trend_effect = (trend_delta + acceleration * 0.5) * (days_ahead / 7) * 0.6

        # 요일 패턴 반영 (50% 가중치)
        weekday_effect = weekday_adjustment * 0.5

        predicted_rank = base_prediction - trend_effect + weekday_effect
        predicted_rank = max(1, min(100, predicted_rank))  # 1~100 범위

        # ─────────────────────────────────────────────
        # 5. 변동성 및 신뢰 구간
        # ─────────────────────────────────────────────
        if len(recent_7) > 1:
            variance = sum((r - recent_avg) ** 2 for r in recent_7) / len(recent_7)
            volatility = variance ** 0.5
        else:
            volatility = 0

        # 신뢰 구간 (변동성 기반)
        confidence_margin = volatility * (1 + days_ahead / 14)  # 예측 기간에 따라 넓어짐
        predicted_lower = max(1, predicted_rank - confidence_margin)
        predicted_upper = min(100, predicted_rank + confidence_margin)

        # 신뢰도 판정
        if volatility < 2 and len(valid_ranks) >= 21:
            confidence = 'high'
            confidence_pct = 85
        elif volatility < 4 and len(valid_ranks) >= 14:
            confidence = 'medium'
            confidence_pct = 70
        elif volatility < 6 and len(valid_ranks) >= 7:
            confidence = 'medium'
            confidence_pct = 55
        else:
            confidence = 'low'
            confidence_pct = 40

        # ─────────────────────────────────────────────
        # 6. 결과 구성
        # ─────────────────────────────────────────────
        return {
            'keyword': keyword,
            'current_rank': current_rank,
            'predicted_rank': round(predicted_rank),
            'predicted_lower': round(predicted_lower),
            'predicted_upper': round(predicted_upper),
            'trend': trend,
            'trend_strength': round(trend_strength, 2),
            'predicted_change': round(current_rank - predicted_rank),  # 양수 = 상승
            'volatility': round(volatility, 2),
            'confidence': confidence,
            'confidence_pct': confidence_pct,
            'days_ahead': days_ahead,
            'data_points': len(valid_ranks),
            'model_factors': {
                'ema': round(ema, 1),
                'trend_effect': round(trend_effect, 1),
                'weekday_effect': round(weekday_effect, 1),
                'acceleration': round(acceleration, 2)
            },
            'recommendation': self._get_rank_recommendation(trend, current_rank, predicted_rank)
        }

    def _get_rank_recommendation(self, trend: str, current: int, predicted: float) -> str:
        """순위 예측 기반 추천"""
        if trend == 'falling' and predicted > current:
            if current <= 10:
                return "Top 10 이탈 위험 - 바이럴 활동 강화 권장"
            else:
                return "순위 하락 예상 - 콘텐츠 전략 재검토 필요"
        elif trend == 'rising':
            if predicted <= 10:
                return "Top 10 진입 가능성 - 현재 전략 유지"
            else:
                return "상승 추세 유지 중 - 바이럴 활동 지속"
        else:
            return "순위 안정적 - 현재 전략 유지"

    def _save_predictions(self, cursor, predictions: List[Dict[str, Any]]):
        """예측 결과 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rank_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                current_rank INTEGER,
                predicted_rank INTEGER,
                trend TEXT,
                confidence TEXT,
                days_ahead INTEGER DEFAULT 7,
                predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actual_rank INTEGER,
                accuracy_checked INTEGER DEFAULT 0
            )
        """)

        for pred in predictions:
            cursor.execute("""
                INSERT INTO rank_predictions
                (keyword, current_rank, predicted_rank, trend, confidence, days_ahead, predicted_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                pred['keyword'],
                pred['current_rank'],
                pred['predicted_rank'],
                pred['trend'],
                pred['confidence'],
                pred['days_ahead']
            ))

    def check_prediction_accuracy(self) -> Dict[str, Any]:
        """과거 예측의 정확도 검증"""
        conn = get_db_connection()
        cursor = conn.cursor()

        results = {
            'total_predictions': 0,
            'checked_predictions': 0,
            'accurate_predictions': 0,
            'accuracy_rate': 0,
            'by_confidence': {}
        }

        try:
            # 7일 이상 지난 미검증 예측 조회
            cursor.execute("""
                SELECT rp.id, rp.keyword, rp.predicted_rank, rp.days_ahead, rp.predicted_at, rp.confidence
                FROM rank_predictions rp
                WHERE rp.accuracy_checked = 0
                AND date(rp.predicted_at, '+' || rp.days_ahead || ' days') <= date('now')
            """)

            predictions_to_check = cursor.fetchall()

            for pred in predictions_to_check:
                pred_id, keyword, predicted_rank, days_ahead, predicted_at, confidence = pred

                # 예측 대상 날짜의 실제 순위 조회
                target_date = (datetime.fromisoformat(predicted_at) + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

                cursor.execute("""
                    SELECT rank FROM rank_history
                    WHERE keyword = ? AND date = ? AND status = 'found'
                """, (keyword, target_date))

                actual = cursor.fetchone()

                if actual:
                    actual_rank = actual[0]
                    # ±3순위 이내면 정확한 예측으로 간주
                    is_accurate = abs(predicted_rank - actual_rank) <= 3

                    cursor.execute("""
                        UPDATE rank_predictions
                        SET actual_rank = ?, accuracy_checked = 1
                        WHERE id = ?
                    """, (actual_rank, pred_id))

                    results['checked_predictions'] += 1
                    if is_accurate:
                        results['accurate_predictions'] += 1

                    if confidence not in results['by_confidence']:
                        results['by_confidence'][confidence] = {'total': 0, 'accurate': 0}
                    results['by_confidence'][confidence]['total'] += 1
                    if is_accurate:
                        results['by_confidence'][confidence]['accurate'] += 1

            conn.commit()

            # 전체 정확도 계산
            cursor.execute("SELECT COUNT(*) FROM rank_predictions")
            results['total_predictions'] = cursor.fetchone()[0]

            if results['checked_predictions'] > 0:
                results['accuracy_rate'] = round(
                    results['accurate_predictions'] / results['checked_predictions'], 4
                )

            # 신뢰도별 정확도 계산
            for conf, data in results['by_confidence'].items():
                if data['total'] > 0:
                    data['accuracy_rate'] = round(data['accurate'] / data['total'], 4)

        except Exception as e:
            logger.error(f"[Intelligence] 예측 정확도 검증 오류: {e}")
        finally:
            conn.close()

        return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B-4: 최적 타이밍 추천
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TimingRecommender:
    """
    리드 응답 및 바이럴 게시 최적 시간 추천

    분석 요소:
    - 플랫폼별 최적 시간대
    - 요일별 전환율
    - 골든타임 분석 (응답까지 걸린 시간 vs 전환율)
    """

    def analyze_optimal_timing(self) -> Dict[str, Any]:
        """최적 타이밍 분석"""
        conn = get_db_connection()
        cursor = conn.cursor()

        results = {
            'platform_timing': {},
            'day_of_week': {},
            'hour_of_day': {},
            'golden_time_analysis': {},
            'recommendations': []
        }

        try:
            # 1. 플랫폼별 최적 시간대
            cursor.execute("""
                SELECT
                    COALESCE(m.platform, m.source, 'unknown') as platform,
                    CAST(strftime('%H', m.created_at) / 4 AS INTEGER) as time_slot,
                    COUNT(*) as total,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                GROUP BY platform, time_slot
                HAVING total >= 3
            """)

            time_slots = ['새벽(0-4)', '아침(4-8)', '오전(8-12)', '오후(12-16)', '저녁(16-20)', '밤(20-24)']

            for row in cursor.fetchall():
                platform, slot_idx, total, conversions = row
                if platform not in results['platform_timing']:
                    results['platform_timing'][platform] = {}

                slot_name = time_slots[int(slot_idx)] if slot_idx is not None and int(slot_idx) < len(time_slots) else '기타'
                rate = conversions / total if total > 0 else 0

                results['platform_timing'][platform][slot_name] = {
                    'total': total,
                    'conversions': conversions,
                    'conversion_rate': round(rate, 4)
                }

            # 2. 요일별 전환율
            cursor.execute("""
                SELECT
                    strftime('%w', m.created_at) as day_of_week,
                    COUNT(*) as total,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                GROUP BY day_of_week
            """)

            day_names = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일']

            for row in cursor.fetchall():
                day_idx, total, conversions = row
                if day_idx is None:
                    continue
                day_name = day_names[int(day_idx)]
                rate = conversions / total if total > 0 else 0

                results['day_of_week'][day_name] = {
                    'total': total,
                    'conversions': conversions,
                    'conversion_rate': round(rate, 4)
                }

            # 3. 시간대별 전환율
            cursor.execute("""
                SELECT
                    strftime('%H', m.created_at) as hour,
                    COUNT(*) as total,
                    SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                FROM mentions m
                LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                WHERE m.created_at >= datetime('now', '-90 days')
                GROUP BY hour
                HAVING total >= 5
            """)

            for row in cursor.fetchall():
                hour, total, conversions = row
                rate = conversions / total if total > 0 else 0
                results['hour_of_day'][f"{hour}시"] = {
                    'total': total,
                    'conversions': conversions,
                    'conversion_rate': round(rate, 4)
                }

            # 4. 골든타임 분석 (응답 시간 vs 전환율)
            cursor.execute("PRAGMA table_info(mentions)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'response_time_hours' in columns:
                cursor.execute("""
                    SELECT
                        CASE
                            WHEN response_time_hours <= 1 THEN '1시간 이내'
                            WHEN response_time_hours <= 4 THEN '4시간 이내'
                            WHEN response_time_hours <= 12 THEN '12시간 이내'
                            WHEN response_time_hours <= 24 THEN '24시간 이내'
                            ELSE '24시간 초과'
                        END as response_category,
                        COUNT(*) as total,
                        SUM(CASE WHEN lc.id IS NOT NULL THEN 1 ELSE 0 END) as conversions
                    FROM mentions m
                    LEFT JOIN lead_conversions lc ON m.id = lc.lead_id
                    WHERE m.response_time_hours IS NOT NULL
                    AND m.created_at >= datetime('now', '-90 days')
                    GROUP BY response_category
                """)

                for row in cursor.fetchall():
                    category, total, conversions = row
                    rate = conversions / total if total > 0 else 0
                    results['golden_time_analysis'][category] = {
                        'total': total,
                        'conversions': conversions,
                        'conversion_rate': round(rate, 4)
                    }

            # 5. 추천 생성
            results['recommendations'] = self._generate_timing_recommendations(results)

            # 결과 저장
            self._save_timing_analysis(cursor, results)
            conn.commit()

        except Exception as e:
            logger.error(f"[Intelligence] 타이밍 분석 오류: {e}")
            conn.rollback()
        finally:
            conn.close()

        return results

    def _generate_timing_recommendations(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """타이밍 분석 기반 추천 생성"""
        recommendations = []

        # 요일 추천
        day_data = results.get('day_of_week', {})
        if day_data:
            best_days = sorted(day_data.items(), key=lambda x: x[1].get('conversion_rate', 0), reverse=True)[:2]
            for day, data in best_days:
                if data.get('conversion_rate', 0) > 0.05:
                    recommendations.append({
                        'type': 'day',
                        'recommendation': f"{day}에 바이럴 활동 집중 권장",
                        'reason': f"전환율 {data['conversion_rate']*100:.1f}%",
                        'priority': 'high'
                    })

        # 시간대 추천
        hour_data = results.get('hour_of_day', {})
        if hour_data:
            best_hours = sorted(hour_data.items(), key=lambda x: x[1].get('conversion_rate', 0), reverse=True)[:3]
            for hour, data in best_hours:
                if data.get('conversion_rate', 0) > 0.05:
                    recommendations.append({
                        'type': 'hour',
                        'recommendation': f"{hour} 시간대에 게시물 확인 및 댓글 권장",
                        'reason': f"전환율 {data['conversion_rate']*100:.1f}%",
                        'priority': 'medium'
                    })

        # 골든타임 추천
        golden_data = results.get('golden_time_analysis', {})
        if '1시간 이내' in golden_data:
            one_hour_rate = golden_data['1시간 이내'].get('conversion_rate', 0)
            if one_hour_rate > 0.1:
                recommendations.append({
                    'type': 'response_time',
                    'recommendation': "Hot 리드 발견 시 1시간 이내 응답 권장",
                    'reason': f"1시간 이내 응답 시 전환율 {one_hour_rate*100:.1f}%",
                    'priority': 'critical'
                })

        return recommendations

    def _save_timing_analysis(self, cursor, results: Dict[str, Any]):
        """타이밍 분석 결과 저장"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timing_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_type TEXT NOT NULL,
                category TEXT NOT NULL,
                sub_category TEXT,
                total_count INTEGER DEFAULT 0,
                conversion_count INTEGER DEFAULT 0,
                conversion_rate REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(analysis_type, category, sub_category)
            )
        """)

        now = datetime.now().isoformat()

        # 플랫폼별 시간대 저장
        for platform, slots in results.get('platform_timing', {}).items():
            for slot, data in slots.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO timing_analytics
                    (analysis_type, category, sub_category, total_count, conversion_count, conversion_rate, updated_at)
                    VALUES ('platform_timing', ?, ?, ?, ?, ?, ?)
                """, (platform, slot, data['total'], data['conversions'], data['conversion_rate'], now))

        # 요일별 저장
        for day, data in results.get('day_of_week', {}).items():
            cursor.execute("""
                INSERT OR REPLACE INTO timing_analytics
                (analysis_type, category, sub_category, total_count, conversion_count, conversion_rate, updated_at)
                VALUES ('day_of_week', ?, NULL, ?, ?, ?, ?)
            """, (day, data['total'], data['conversions'], data['conversion_rate'], now))

        # 시간대별 저장
        for hour, data in results.get('hour_of_day', {}).items():
            cursor.execute("""
                INSERT OR REPLACE INTO timing_analytics
                (analysis_type, category, sub_category, total_count, conversion_count, conversion_rate, updated_at)
                VALUES ('hour_of_day', ?, NULL, ?, ?, ?, ?)
            """, (hour, data['total'], data['conversions'], data['conversion_rate'], now))

    def get_current_recommendations(self) -> List[Dict[str, Any]]:
        """현재 시점 기준 추천 조회"""
        now = datetime.now()
        current_hour = now.hour
        current_day = now.strftime('%A')

        day_names_kr = {
            'Sunday': '일요일', 'Monday': '월요일', 'Tuesday': '화요일',
            'Wednesday': '수요일', 'Thursday': '목요일', 'Friday': '금요일',
            'Saturday': '토요일'
        }
        current_day_kr = day_names_kr.get(current_day, current_day)

        conn = get_db_connection()
        cursor = conn.cursor()

        recommendations = []

        try:
            # 현재 요일의 전환율 조회
            cursor.execute("""
                SELECT conversion_rate FROM timing_analytics
                WHERE analysis_type = 'day_of_week' AND category = ?
            """, (current_day_kr,))
            row = cursor.fetchone()

            if row and row[0] > 0.05:
                recommendations.append({
                    'type': 'current_day',
                    'message': f"오늘({current_day_kr})은 전환율이 높은 날입니다!",
                    'conversion_rate': row[0]
                })

            # 현재 시간대의 전환율 조회
            cursor.execute("""
                SELECT conversion_rate FROM timing_analytics
                WHERE analysis_type = 'hour_of_day' AND category = ?
            """, (f"{current_hour}시",))
            row = cursor.fetchone()

            if row and row[0] > 0.05:
                recommendations.append({
                    'type': 'current_hour',
                    'message': f"현재 시간대({current_hour}시)는 활동하기 좋은 시간입니다!",
                    'conversion_rate': row[0]
                })

        except Exception as e:
            logger.debug(f"[Intelligence] 현재 추천 조회 오류: {e}")
        finally:
            conn.close()

        return recommendations


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 인텔리전스 서비스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MarketingIntelligence:
    """
    통합 마케팅 인텔리전스 서비스
    모든 AI 기반 분석 기능 통합
    """

    def __init__(self):
        self.conversion_learner = ConversionPatternLearner()
        self.comment_analyzer = CommentEffectivenessAnalyzer()
        self.rank_predictor = RankPredictor()
        self.timing_recommender = TimingRecommender()

    def run_full_analysis(self) -> Dict[str, Any]:
        """전체 인텔리전스 분석 실행"""
        logger.info("[Intelligence] 전체 분석 시작...")

        results = {
            'conversion_patterns': None,
            'comment_effectiveness': None,
            'rank_predictions': None,
            'timing_analysis': None,
            'errors': []
        }

        # 1. 전환 패턴 학습
        try:
            results['conversion_patterns'] = self.conversion_learner.learn_from_conversions()
            logger.info("[Intelligence] 전환 패턴 학습 완료")
        except Exception as e:
            results['errors'].append(f"전환 패턴: {e}")
            logger.error(f"[Intelligence] 전환 패턴 학습 오류: {e}")

        # 2. 댓글 효과 분석
        try:
            results['comment_effectiveness'] = self.comment_analyzer.analyze_comment_effectiveness()
            logger.info("[Intelligence] 댓글 효과 분석 완료")
        except Exception as e:
            results['errors'].append(f"댓글 효과: {e}")
            logger.error(f"[Intelligence] 댓글 효과 분석 오류: {e}")

        # 3. 순위 예측
        try:
            results['rank_predictions'] = self.rank_predictor.predict_rank_changes()
            logger.info("[Intelligence] 순위 예측 완료")
        except Exception as e:
            results['errors'].append(f"순위 예측: {e}")
            logger.error(f"[Intelligence] 순위 예측 오류: {e}")

        # 4. 타이밍 분석
        try:
            results['timing_analysis'] = self.timing_recommender.analyze_optimal_timing()
            logger.info("[Intelligence] 타이밍 분석 완료")
        except Exception as e:
            results['errors'].append(f"타이밍: {e}")
            logger.error(f"[Intelligence] 타이밍 분석 오류: {e}")

        logger.info("[Intelligence] 전체 분석 완료")
        return results

    def get_dashboard_insights(self) -> Dict[str, Any]:
        """대시보드용 주요 인사이트 반환"""
        insights = {
            'conversion_rate_by_platform': {},
            'top_keywords': [],
            'rank_alerts': [],
            'timing_recommendations': [],
            'updated_at': datetime.now().isoformat()
        }

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 플랫폼별 전환율
            cursor.execute("""
                SELECT pattern_key, conversion_rate, sample_count
                FROM conversion_patterns
                WHERE pattern_type = 'platform' AND sample_count >= 5
                ORDER BY conversion_rate DESC
                LIMIT 5
            """)
            for row in cursor.fetchall():
                insights['conversion_rate_by_platform'][row[0]] = {
                    'rate': row[1],
                    'samples': row[2]
                }

            # 고성과 키워드 (전환율 상위)
            cursor.execute("""
                SELECT pattern_key, conversion_rate, sample_count
                FROM conversion_patterns
                WHERE pattern_type = 'keyword' AND sample_count >= 5
                ORDER BY conversion_rate DESC
                LIMIT 5
            """)
            insights['top_keywords'] = [
                {'keyword': row[0], 'conversion_rate': row[1], 'leads': row[2]}
                for row in cursor.fetchall()
            ]

            # 순위 경고 (하락 예측 키워드)
            cursor.execute("""
                SELECT keyword, current_rank, predicted_rank, trend, confidence
                FROM rank_predictions
                WHERE predicted_at >= datetime('now', '-1 day')
                AND trend = 'falling'
                ORDER BY (predicted_rank - current_rank) DESC
                LIMIT 5
            """)
            insights['rank_alerts'] = [
                {
                    'keyword': row[0],
                    'current': row[1],
                    'predicted': row[2],
                    'confidence': row[4]
                }
                for row in cursor.fetchall()
            ]

            # 현재 시점 타이밍 추천
            insights['timing_recommendations'] = self.timing_recommender.get_current_recommendations()

        except Exception as e:
            logger.error(f"[Intelligence] 대시보드 인사이트 조회 오류: {e}")
        finally:
            conn.close()

        return insights


# 싱글톤 인스턴스
_intelligence_instance = None


def get_marketing_intelligence() -> MarketingIntelligence:
    """MarketingIntelligence 싱글톤 인스턴스 반환"""
    global _intelligence_instance
    if _intelligence_instance is None:
        _intelligence_instance = MarketingIntelligence()
    return _intelligence_instance
