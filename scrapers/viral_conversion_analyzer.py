#!/usr/bin/env python3
"""
Viral Conversion Analyzer - 바이럴 타겟 전환 패턴 분석기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
viral_targets(16,971건)과 mentions(리드)를 교차 분석하여
어떤 바이럴 타겟이 실제 리드로 전환되는지 패턴을 발견합니다.

- 플랫폼별 전환율
- 카테고리별 전환율
- 시간대/요일별 패턴
- 점수 임계값 분석
- 댓글 상태별 효과
- 콘텐츠 연령별 효과

Usage:
    python scrapers/viral_conversion_analyzer.py
"""

import sys
import os
import time
import json
import logging
import traceback
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


class ViralConversionAnalyzer:
    """바이럴 타겟 전환 패턴 분석기"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()

    def _ensure_table(self):
        """viral_conversion_patterns 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS viral_conversion_patterns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pattern_dimension TEXT NOT NULL,
                        pattern_key TEXT NOT NULL,
                        total_targets INTEGER DEFAULT 0,
                        commented_targets INTEGER DEFAULT 0,
                        leads_generated INTEGER DEFAULT 0,
                        conversion_rate REAL DEFAULT 0,
                        avg_lead_score REAL DEFAULT 0,
                        recommendation TEXT,
                        analysis_date TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(pattern_dimension, pattern_key, analysis_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_viral_conv_dimension_date
                    ON viral_conversion_patterns (pattern_dimension, analysis_date)
                """)
                conn.commit()
            logger.info("viral_conversion_patterns 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 생성 실패: {e}")
            logger.debug(traceback.format_exc())

    def _load_data(self) -> Tuple[List[Dict], List[Dict]]:
        """viral_targets와 mentions 데이터를 로드합니다."""
        targets = []
        leads = []

        try:
            with self.db.get_new_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # viral_targets
                cursor.execute("""
                    SELECT id, platform, category, matched_keyword,
                           comment_status, priority_score, discovered_at,
                           content_type
                    FROM viral_targets
                """)
                for row in cursor.fetchall():
                    targets.append({
                        'id': row['id'],
                        'platform': row['platform'] or 'unknown',
                        'category': row['category'] or 'unknown',
                        'matched_keyword': row['matched_keyword'] or '',
                        'comment_status': row['comment_status'] or 'pending',
                        'score': row['priority_score'] or 0,
                        'discovered_at': row['discovered_at'] or '',
                        'content_type': row['content_type'] or 'unknown'
                    })

                # mentions (leads) with source_target_id
                cursor.execute("""
                    SELECT id, source_target_id, status, score,
                           platform, scraped_at
                    FROM mentions
                    WHERE source_target_id IS NOT NULL
                      AND source_target_id != ''
                """)
                for row in cursor.fetchall():
                    leads.append({
                        'id': row['id'],
                        'source_target_id': row['source_target_id'],
                        'status': row['status'] or 'New',
                        'score': row['score'] or 0,
                        'platform': row['platform'] or '',
                        'scraped_at': row['scraped_at'] or ''
                    })

        except Exception as e:
            logger.error(f"데이터 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        logger.info(f"바이럴 타겟 {len(targets)}건, 리드 {len(leads)}건 로드")
        return targets, leads

    def _build_conversion_map(self, targets: List[Dict], leads: List[Dict]) -> Dict[str, List[Dict]]:
        """타겟 ID -> 생성된 리드 목록 매핑을 구축합니다."""
        conv_map = defaultdict(list)
        for lead in leads:
            conv_map[lead['source_target_id']].append(lead)
        return dict(conv_map)

    def _analyze_platform(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """플랫폼별 전환 패턴을 분석합니다."""
        platform_stats = defaultdict(lambda: {
            'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []
        })

        for t in targets:
            p = t['platform']
            platform_stats[p]['total'] += 1
            if t['comment_status'] in ('posted', 'completed', 'verified'):
                platform_stats[p]['commented'] += 1
            target_leads = conv_map.get(t['id'], [])
            platform_stats[p]['leads'] += len(target_leads)
            for lead in target_leads:
                platform_stats[p]['lead_scores'].append(lead.get('score', 0))

        results = []
        for platform, stats in sorted(platform_stats.items(), key=lambda x: x[1]['leads'], reverse=True):
            conv_rate = (stats['leads'] / max(stats['total'], 1)) * 100
            avg_score = (sum(stats['lead_scores']) / max(len(stats['lead_scores']), 1)) if stats['lead_scores'] else 0

            recommendation = self._get_platform_recommendation(platform, conv_rate, stats['total'], stats['leads'])

            results.append({
                'pattern_dimension': 'platform',
                'pattern_key': platform,
                'total_targets': stats['total'],
                'commented_targets': stats['commented'],
                'leads_generated': stats['leads'],
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': recommendation
            })

        return results

    def _analyze_category(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """카테고리별 전환 패턴을 분석합니다."""
        cat_stats = defaultdict(lambda: {
            'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []
        })

        for t in targets:
            cat = t['category'] or 'uncategorized'
            cat_stats[cat]['total'] += 1
            if t['comment_status'] in ('posted', 'completed', 'verified'):
                cat_stats[cat]['commented'] += 1
            target_leads = conv_map.get(t['id'], [])
            cat_stats[cat]['leads'] += len(target_leads)
            for lead in target_leads:
                cat_stats[cat]['lead_scores'].append(lead.get('score', 0))

        results = []
        for cat, stats in sorted(cat_stats.items(), key=lambda x: x[1]['leads'], reverse=True):
            conv_rate = (stats['leads'] / max(stats['total'], 1)) * 100
            avg_score = (sum(stats['lead_scores']) / max(len(stats['lead_scores']), 1)) if stats['lead_scores'] else 0

            recommendation = ""
            if conv_rate > 5:
                recommendation = f"최고 전환 카테고리. {cat} 관련 콘텐츠 집중 공략 권장."
            elif stats['total'] > 100 and conv_rate < 1:
                recommendation = f"많은 타겟 대비 전환율 낮음. 타겟팅 기준 재검토 필요."
            elif stats['total'] > 0:
                recommendation = f"전환율 {conv_rate:.1f}%. 관찰 유지."

            results.append({
                'pattern_dimension': 'category',
                'pattern_key': cat,
                'total_targets': stats['total'],
                'commented_targets': stats['commented'],
                'leads_generated': stats['leads'],
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': recommendation
            })

        return results

    def _analyze_time_of_day(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """시간대별 전환 패턴을 분석합니다."""
        hour_stats = defaultdict(lambda: {
            'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []
        })

        for t in targets:
            try:
                discovered = t.get('discovered_at', '')
                if not discovered:
                    continue
                dt = datetime.fromisoformat(discovered.replace('Z', '+00:00')) if 'T' in discovered else datetime.strptime(discovered[:19], '%Y-%m-%d %H:%M:%S')
                hour = dt.hour
                # 시간대를 4시간 블록으로 그룹화
                hour_block = f"{(hour // 4) * 4:02d}-{((hour // 4) * 4 + 3):02d}시"
            except (ValueError, TypeError):
                continue

            hour_stats[hour_block]['total'] += 1
            if t['comment_status'] in ('posted', 'completed', 'verified'):
                hour_stats[hour_block]['commented'] += 1
            target_leads = conv_map.get(t['id'], [])
            hour_stats[hour_block]['leads'] += len(target_leads)
            for lead in target_leads:
                hour_stats[hour_block]['lead_scores'].append(lead.get('score', 0))

        results = []
        for hour_block, stats in sorted(hour_stats.items()):
            conv_rate = (stats['leads'] / max(stats['total'], 1)) * 100
            avg_score = (sum(stats['lead_scores']) / max(len(stats['lead_scores']), 1)) if stats['lead_scores'] else 0

            recommendation = ""
            if conv_rate > 3:
                recommendation = f"최고 전환 시간대. 이 시간대 콘텐츠 우선 처리 권장."
            elif stats['total'] > 500:
                recommendation = f"대량 발견 시간대. 전환율 {conv_rate:.1f}%."

            results.append({
                'pattern_dimension': 'hour',
                'pattern_key': hour_block,
                'total_targets': stats['total'],
                'commented_targets': stats['commented'],
                'leads_generated': stats['leads'],
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': recommendation
            })

        return results

    def _analyze_day_of_week(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """요일별 전환 패턴을 분석합니다."""
        day_names = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
        day_stats = defaultdict(lambda: {
            'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []
        })

        for t in targets:
            try:
                discovered = t.get('discovered_at', '')
                if not discovered:
                    continue
                dt = datetime.fromisoformat(discovered.replace('Z', '+00:00')) if 'T' in discovered else datetime.strptime(discovered[:19], '%Y-%m-%d %H:%M:%S')
                day_name = day_names[dt.weekday()]
            except (ValueError, TypeError):
                continue

            day_stats[day_name]['total'] += 1
            if t['comment_status'] in ('posted', 'completed', 'verified'):
                day_stats[day_name]['commented'] += 1
            target_leads = conv_map.get(t['id'], [])
            day_stats[day_name]['leads'] += len(target_leads)
            for lead in target_leads:
                day_stats[day_name]['lead_scores'].append(lead.get('score', 0))

        results = []
        for day_name in day_names:
            stats = day_stats.get(day_name, {'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []})
            conv_rate = (stats['leads'] / max(stats['total'], 1)) * 100
            avg_score = (sum(stats['lead_scores']) / max(len(stats['lead_scores']), 1)) if stats['lead_scores'] else 0

            results.append({
                'pattern_dimension': 'day_of_week',
                'pattern_key': day_name,
                'total_targets': stats['total'],
                'commented_targets': stats['commented'],
                'leads_generated': stats['leads'],
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': ''
            })

        return results

    def _analyze_score_range(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """점수 구간별 전환 패턴을 분석합니다."""
        score_ranges = [
            ('0-20', 0, 20),
            ('21-40', 21, 40),
            ('41-60', 41, 60),
            ('61-80', 61, 80),
            ('81-100', 81, 100),
        ]

        results = []
        for range_name, low, high in score_ranges:
            range_targets = [t for t in targets if low <= (t.get('score', 0) or 0) <= high]
            if not range_targets:
                continue

            total = len(range_targets)
            commented = sum(1 for t in range_targets if t['comment_status'] in ('posted', 'completed', 'verified'))
            leads = 0
            lead_scores = []

            for t in range_targets:
                target_leads = conv_map.get(t['id'], [])
                leads += len(target_leads)
                for lead in target_leads:
                    lead_scores.append(lead.get('score', 0))

            conv_rate = (leads / max(total, 1)) * 100
            avg_score = (sum(lead_scores) / max(len(lead_scores), 1)) if lead_scores else 0

            recommendation = ""
            if conv_rate > 5:
                recommendation = f"최적 점수 구간. {range_name}점 타겟 우선 공략."
            elif total > 100 and conv_rate < 0.5:
                recommendation = f"저효율 구간. 이 점수대 타겟은 스킵 고려."

            results.append({
                'pattern_dimension': 'score_range',
                'pattern_key': range_name,
                'total_targets': total,
                'commented_targets': commented,
                'leads_generated': leads,
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': recommendation
            })

        return results

    def _analyze_comment_status(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """댓글 상태별 전환 패턴을 분석합니다."""
        status_stats = defaultdict(lambda: {
            'total': 0, 'leads': 0, 'lead_scores': []
        })

        for t in targets:
            cs = t['comment_status']
            status_stats[cs]['total'] += 1
            target_leads = conv_map.get(t['id'], [])
            status_stats[cs]['leads'] += len(target_leads)
            for lead in target_leads:
                status_stats[cs]['lead_scores'].append(lead.get('score', 0))

        results = []
        for status, stats in sorted(status_stats.items(), key=lambda x: x[1]['leads'], reverse=True):
            conv_rate = (stats['leads'] / max(stats['total'], 1)) * 100
            avg_score = (sum(stats['lead_scores']) / max(len(stats['lead_scores']), 1)) if stats['lead_scores'] else 0

            recommendation = ""
            if status in ('posted', 'completed', 'verified') and conv_rate > 0:
                recommendation = "댓글 작성이 전환에 효과가 있습니다."
            elif status == 'pending':
                recommendation = f"미처리 타겟 {stats['total']}건. 처리 시 전환율 개선 가능."

            results.append({
                'pattern_dimension': 'comment_status',
                'pattern_key': status,
                'total_targets': stats['total'],
                'commented_targets': stats['total'] if status in ('posted', 'completed', 'verified') else 0,
                'leads_generated': stats['leads'],
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': recommendation
            })

        return results

    def _analyze_content_age(self, targets: List[Dict], conv_map: Dict) -> List[Dict]:
        """콘텐츠 연령별 전환 패턴을 분석합니다."""
        now = datetime.now()
        age_ranges = [
            ('0-1일', 0, 1),
            ('2-3일', 2, 3),
            ('4-7일', 4, 7),
            ('8-14일', 8, 14),
            ('15-30일', 15, 30),
            ('31-90일', 31, 90),
            ('91일+', 91, 9999),
        ]

        age_stats = defaultdict(lambda: {
            'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []
        })

        for t in targets:
            try:
                discovered = t.get('discovered_at', '')
                if not discovered:
                    continue
                dt = datetime.fromisoformat(discovered.replace('Z', '+00:00')) if 'T' in discovered else datetime.strptime(discovered[:19], '%Y-%m-%d %H:%M:%S')
                age_days = (now - dt.replace(tzinfo=None)).days
            except (ValueError, TypeError):
                continue

            for range_name, low, high in age_ranges:
                if low <= age_days <= high:
                    age_stats[range_name]['total'] += 1
                    if t['comment_status'] in ('posted', 'completed', 'verified'):
                        age_stats[range_name]['commented'] += 1
                    target_leads = conv_map.get(t['id'], [])
                    age_stats[range_name]['leads'] += len(target_leads)
                    for lead in target_leads:
                        age_stats[range_name]['lead_scores'].append(lead.get('score', 0))
                    break

        results = []
        for range_name, low, high in age_ranges:
            stats = age_stats.get(range_name, {'total': 0, 'commented': 0, 'leads': 0, 'lead_scores': []})
            if stats['total'] == 0:
                continue

            conv_rate = (stats['leads'] / max(stats['total'], 1)) * 100
            avg_score = (sum(stats['lead_scores']) / max(len(stats['lead_scores']), 1)) if stats['lead_scores'] else 0

            recommendation = ""
            if conv_rate > 3:
                recommendation = f"최적 콘텐츠 연령. {range_name} 된 콘텐츠가 가장 잘 전환됩니다."
            elif stats['total'] > 100 and conv_rate < 0.5:
                recommendation = f"오래된 콘텐츠는 전환율이 낮습니다. 신선한 콘텐츠 우선."

            results.append({
                'pattern_dimension': 'content_age',
                'pattern_key': range_name,
                'total_targets': stats['total'],
                'commented_targets': stats['commented'],
                'leads_generated': stats['leads'],
                'conversion_rate': round(conv_rate, 2),
                'avg_lead_score': round(avg_score, 1),
                'recommendation': recommendation
            })

        return results

    def _get_platform_recommendation(self, platform: str, conv_rate: float, total: int, leads: int) -> str:
        """플랫폼별 맞춤 추천을 생성합니다."""
        if conv_rate > 5:
            return f"최고 전환 플랫폼. {platform} 공략에 리소스 집중 권장."
        elif conv_rate > 2:
            return f"양호한 전환율. 현재 전략 유지."
        elif total > 1000 and conv_rate < 0.5:
            return f"대량 타겟이지만 전환율 매우 낮음. 타겟 선별 기준 강화 필요."
        elif total > 100:
            return f"전환율 {conv_rate:.1f}%. 댓글 품질 개선 검토."
        else:
            return f"데이터 부족 ({total}건). 추가 수집 필요."

    def _save_results(self, all_results: List[Dict]):
        """분석 결과를 DB에 저장합니다."""
        analysis_date = datetime.now().strftime("%Y-%m-%d")

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for result in all_results:
                    cursor.execute("""
                        INSERT INTO viral_conversion_patterns
                        (pattern_dimension, pattern_key, total_targets,
                         commented_targets, leads_generated, conversion_rate,
                         avg_lead_score, recommendation, analysis_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(pattern_dimension, pattern_key, analysis_date) DO UPDATE SET
                            total_targets = excluded.total_targets,
                            commented_targets = excluded.commented_targets,
                            leads_generated = excluded.leads_generated,
                            conversion_rate = excluded.conversion_rate,
                            avg_lead_score = excluded.avg_lead_score,
                            recommendation = excluded.recommendation
                    """, (
                        result['pattern_dimension'],
                        result['pattern_key'],
                        result['total_targets'],
                        result['commented_targets'],
                        result['leads_generated'],
                        result['conversion_rate'],
                        result['avg_lead_score'],
                        result['recommendation'],
                        analysis_date
                    ))

                conn.commit()
                logger.info(f"전환 패턴 {len(all_results)}건 DB 저장 완료")

        except Exception as e:
            logger.error(f"DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

    def _print_dimension(self, title: str, results: List[Dict]):
        """차원별 분석 결과를 출력합니다."""
        if not results:
            return

        print(f"\n  [{title}]")
        print(f"  {'키':20s} {'타겟':>8s} {'댓글':>8s} {'리드':>6s} {'전환율':>8s} {'평균점수':>8s}")
        print(f"  {'-'*62}")

        for r in results:
            print(
                f"  {r['pattern_key']:20s} "
                f"{r['total_targets']:>8,} "
                f"{r['commented_targets']:>8,} "
                f"{r['leads_generated']:>6,} "
                f"{r['conversion_rate']:>7.2f}% "
                f"{r['avg_lead_score']:>8.1f}"
            )
            if r.get('recommendation'):
                print(f"    -> {r['recommendation']}")

    def run(self):
        """전환 패턴 분석을 실행합니다."""
        print(f"\n{'='*60}")
        print(f" Viral Conversion Analyzer")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # 데이터 로드
        targets, leads = self._load_data()

        if not targets:
            print("분석할 바이럴 타겟이 없습니다.")
            return

        # 전환 맵 구축
        conv_map = self._build_conversion_map(targets, leads)

        total_with_leads = sum(1 for t in targets if t['id'] in conv_map)
        total_leads = len(leads)
        overall_conv_rate = (total_with_leads / max(len(targets), 1)) * 100

        print(f"  바이럴 타겟: {len(targets):,}건")
        print(f"  연결된 리드: {total_leads:,}건")
        print(f"  전환된 타겟: {total_with_leads:,}건 ({overall_conv_rate:.2f}%)")

        # 각 차원별 분석
        all_results = []

        print(f"\n{'='*60}")
        print(f" 전환 패턴 분석 결과")
        print(f"{'='*60}")

        # 1. 플랫폼별
        platform_results = self._analyze_platform(targets, conv_map)
        all_results.extend(platform_results)
        self._print_dimension("플랫폼별 전환", platform_results)

        # 2. 카테고리별
        category_results = self._analyze_category(targets, conv_map)
        all_results.extend(category_results)
        self._print_dimension("카테고리별 전환", category_results)

        # 3. 시간대별
        hour_results = self._analyze_time_of_day(targets, conv_map)
        all_results.extend(hour_results)
        self._print_dimension("시간대별 전환", hour_results)

        # 4. 요일별
        day_results = self._analyze_day_of_week(targets, conv_map)
        all_results.extend(day_results)
        self._print_dimension("요일별 전환", day_results)

        # 5. 점수 구간별
        score_results = self._analyze_score_range(targets, conv_map)
        all_results.extend(score_results)
        self._print_dimension("점수 구간별 전환", score_results)

        # 6. 댓글 상태별
        comment_results = self._analyze_comment_status(targets, conv_map)
        all_results.extend(comment_results)
        self._print_dimension("댓글 상태별 전환", comment_results)

        # 7. 콘텐츠 연령별
        age_results = self._analyze_content_age(targets, conv_map)
        all_results.extend(age_results)
        self._print_dimension("콘텐츠 연령별 전환", age_results)

        # DB 저장
        self._save_results(all_results)

        # 최종 요약
        print(f"\n{'='*60}")
        print(f" 분석 완료!")
        print(f" 총 패턴: {len(all_results)}건")
        print(f" 7개 차원: platform, category, hour, day_of_week, score_range, comment_status, content_age")
        print(f"{'='*60}")

        return all_results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        analyzer = ViralConversionAnalyzer()
        analyzer.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
