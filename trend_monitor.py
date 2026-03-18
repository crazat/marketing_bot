#!/usr/bin/env python3
"""
키워드 트렌드 모니터링 시스템
- 검색량 급증/급감 감지
- 신규 진입 키워드 감지
- 주간 트렌드 리포트 생성
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrendAlert:
    """트렌드 알림"""
    keyword: str
    category: str
    change_type: str  # surge, drop, new_entry, rank_up, rank_down
    old_value: float
    new_value: float
    change_rate: float
    severity: str  # critical, high, medium, low
    detected_at: str


class TrendMonitor:
    """키워드 트렌드 모니터링"""

    def __init__(self, db_path: str = "db/marketing_data.db"):
        self.db_path = db_path

        # 임계값 설정
        self.SURGE_THRESHOLD = 0.5  # 50% 이상 증가
        self.DROP_THRESHOLD = -0.5  # 50% 이상 감소
        self.CRITICAL_THRESHOLD = 1.0  # 100% 이상 변화

    def get_weekly_comparison(self) -> List[Dict]:
        """주간 검색량 비교 (이번 주 vs 지난 주)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 7일 전과 현재 데이터 비교
        query = """
        SELECT
            k1.keyword,
            k1.category,
            k1.search_volume as current_volume,
            k1.grade as current_grade,
            k2.search_volume as previous_volume,
            k2.created_at as previous_date,
            k1.created_at as current_date
        FROM keyword_insights k1
        LEFT JOIN keyword_insights k2
            ON k1.keyword = k2.keyword
            AND k2.created_at BETWEEN date('now', '-14 days') AND date('now', '-7 days')
        WHERE k1.created_at >= date('now', '-7 days')
            AND k1.search_volume > 0
        ORDER BY k1.search_volume DESC
        """

        cursor.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def detect_trends(self, comparison: List[Dict]) -> List[TrendAlert]:
        """트렌드 변화 감지"""
        alerts = []

        for item in comparison:
            keyword = item['keyword']
            category = item.get('category', '기타')
            current = item['current_volume']
            previous = item.get('previous_volume', 0)

            # 신규 진입 (이전 데이터 없음)
            if previous == 0 or previous is None:
                if current >= 100:  # 검색량 100 이상만
                    alerts.append(TrendAlert(
                        keyword=keyword,
                        category=category,
                        change_type="new_entry",
                        old_value=0,
                        new_value=current,
                        change_rate=float('inf'),
                        severity="medium",
                        detected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                continue

            # 변화율 계산
            change_rate = (current - previous) / previous

            # 급증 감지
            if change_rate >= self.SURGE_THRESHOLD:
                severity = "critical" if change_rate >= self.CRITICAL_THRESHOLD else "high"
                alerts.append(TrendAlert(
                    keyword=keyword,
                    category=category,
                    change_type="surge",
                    old_value=previous,
                    new_value=current,
                    change_rate=change_rate,
                    severity=severity,
                    detected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

            # 급감 감지
            elif change_rate <= self.DROP_THRESHOLD:
                severity = "critical" if change_rate <= -self.CRITICAL_THRESHOLD else "high"
                alerts.append(TrendAlert(
                    keyword=keyword,
                    category=category,
                    change_type="drop",
                    old_value=previous,
                    new_value=current,
                    change_rate=change_rate,
                    severity=severity,
                    detected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

        # 중요도 순 정렬
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        alerts.sort(key=lambda x: (severity_order[x.severity], abs(x.change_rate)), reverse=True)

        return alerts

    def get_rank_changes(self) -> List[Dict]:
        """순위 변동 감지 (상위 50개 키워드)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 현재와 7일 전 순위 비교
        query = """
        WITH current_rank AS (
            SELECT
                keyword,
                category,
                search_volume,
                ROW_NUMBER() OVER (ORDER BY search_volume DESC) as rank
            FROM keyword_insights
            WHERE created_at >= date('now', '-1 days')
                AND search_volume > 0
            LIMIT 50
        ),
        previous_rank AS (
            SELECT
                keyword,
                search_volume,
                ROW_NUMBER() OVER (ORDER BY search_volume DESC) as rank
            FROM keyword_insights
            WHERE created_at BETWEEN date('now', '-8 days') AND date('now', '-7 days')
                AND search_volume > 0
            LIMIT 50
        )
        SELECT
            c.keyword,
            c.category,
            c.rank as current_rank,
            p.rank as previous_rank,
            c.search_volume as current_volume,
            p.search_volume as previous_volume
        FROM current_rank c
        LEFT JOIN previous_rank p ON c.keyword = p.keyword
        WHERE p.rank IS NOT NULL
        ORDER BY c.rank
        """

        cursor.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # 순위 변동 계산
        for item in results:
            rank_change = item['previous_rank'] - item['current_rank']  # 양수 = 상승
            item['rank_change'] = rank_change

        return results

    def generate_report(self) -> str:
        """주간 트렌드 리포트 생성"""
        comparison = self.get_weekly_comparison()
        alerts = self.detect_trends(comparison)
        rank_changes = self.get_rank_changes()

        # 리포트 생성
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append(f"📊 주간 트렌드 리포트 - {datetime.now().strftime('%Y-%m-%d')}")
        report_lines.append("=" * 70)

        # 1. 급증 키워드
        surges = [a for a in alerts if a.change_type == "surge"]
        if surges:
            report_lines.append("\n🔥 검색량 급증 키워드")
            report_lines.append("-" * 70)
            for alert in surges[:10]:
                change_pct = alert.change_rate * 100
                report_lines.append(
                    f"   {alert.severity.upper():8} | {alert.keyword:30} "
                    f"| {alert.old_value:>6.0f} → {alert.new_value:>6.0f} (+{change_pct:.1f}%)"
                )

        # 2. 급감 키워드
        drops = [a for a in alerts if a.change_type == "drop"]
        if drops:
            report_lines.append("\n📉 검색량 급감 키워드")
            report_lines.append("-" * 70)
            for alert in drops[:10]:
                change_pct = alert.change_rate * 100
                report_lines.append(
                    f"   {alert.severity.upper():8} | {alert.keyword:30} "
                    f"| {alert.old_value:>6.0f} → {alert.new_value:>6.0f} ({change_pct:.1f}%)"
                )

        # 3. 신규 진입 키워드
        new_entries = [a for a in alerts if a.change_type == "new_entry"]
        if new_entries:
            report_lines.append("\n✨ 신규 진입 키워드")
            report_lines.append("-" * 70)
            for alert in new_entries[:10]:
                report_lines.append(
                    f"   {alert.keyword:30} | 검색량: {alert.new_value:.0f}"
                )

        # 4. 순위 변동
        if rank_changes:
            report_lines.append("\n📊 순위 변동 (상위 50개)")
            report_lines.append("-" * 70)

            # 상승
            rank_ups = [r for r in rank_changes if r['rank_change'] > 0][:5]
            if rank_ups:
                report_lines.append("   📈 순위 상승:")
                for r in rank_ups:
                    report_lines.append(
                        f"      {r['keyword']:30} | {r['previous_rank']}위 → {r['current_rank']}위 (↑{r['rank_change']})"
                    )

            # 하락
            rank_downs = [r for r in rank_changes if r['rank_change'] < 0][:5]
            if rank_downs:
                report_lines.append("   📉 순위 하락:")
                for r in rank_downs:
                    report_lines.append(
                        f"      {r['keyword']:30} | {r['previous_rank']}위 → {r['current_rank']}위 (↓{abs(r['rank_change'])})"
                    )

        # 5. 요약
        report_lines.append("\n" + "=" * 70)
        report_lines.append("📈 요약")
        report_lines.append("=" * 70)
        report_lines.append(f"   급증 키워드: {len(surges)}개")
        report_lines.append(f"   급감 키워드: {len(drops)}개")
        report_lines.append(f"   신규 진입: {len(new_entries)}개")
        report_lines.append(f"   분석 키워드: {len(comparison)}개")

        return "\n".join(report_lines)

    def save_report(self, report: str, filename: str = None):
        """리포트 파일 저장"""
        if filename is None:
            filename = f"reports/trend_report_{datetime.now().strftime('%Y%m%d')}.txt"

        report_path = Path(filename)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"✅ 리포트 저장: {filename}")

        return filename


def main():
    """CLI 실행"""
    print("📊 키워드 트렌드 모니터링 시작")

    monitor = TrendMonitor()

    # 리포트 생성
    report = monitor.generate_report()

    # 출력
    print(report)

    # 파일 저장
    monitor.save_report(report)


if __name__ == "__main__":
    main()
