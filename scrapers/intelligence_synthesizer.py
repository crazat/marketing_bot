#!/usr/bin/env python3
"""
Intelligence Synthesizer - Comprehensive Marketing Intelligence Reports
========================================================================

Cross-analyzes ALL collected data to generate detailed, actionable
marketing intelligence reports:

1. Rank Intelligence Report (순위 인텔리전스)
2. Competitor Threat Report (경쟁사 위협 분석)
3. Keyword Opportunity Report (키워드 기회 분석)
4. Community & Lead Intelligence (커뮤니티 & 리드 인텔리전스)
5. Anomaly & Alert Report
6. Weekly Summary (주간 종합 요약)

Sends detailed Telegram notification after report generation.

Usage:
    python scrapers/intelligence_synthesizer.py
"""

import sys
import os
import time
import json
import logging
import traceback
import sqlite3
import math
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


def _norm_device(device_type):
    """device_type 정규화: api_local → mobile"""
    dt = device_type or 'mobile'
    return 'mobile' if dt == 'api_local' else dt


class IntelligenceSynthesizer:
    """Cross-analyzes ALL collected data to generate comprehensive intelligence reports."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_report_table()
        self.report_date = datetime.now().strftime("%Y-%m-%d")
        self.report_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.alerts: List[str] = []
        self.report_sections: Dict[str, str] = {}

        # Load business profile
        self.business_name = "규림한의원"
        self.business_short = "규림"
        try:
            bp_path = os.path.join(project_root, 'config', 'business_profile.json')
            if os.path.exists(bp_path):
                with open(bp_path, 'r', encoding='utf-8') as f:
                    bp = json.load(f)
                    self.business_name = bp.get('business', {}).get('name', '규림한의원')
                    self.business_short = bp.get('business', {}).get('short_name', '규림')
        except Exception:
            pass

        # Load tracked keywords
        self.place_keywords = []
        self.blog_keywords = []
        try:
            kw_path = os.path.join(project_root, 'config', 'keywords.json')
            if os.path.exists(kw_path):
                with open(kw_path, 'r', encoding='utf-8') as f:
                    kw_data = json.load(f)
                    self.place_keywords = kw_data.get('naver_place', [])
                    self.blog_keywords = kw_data.get('blog_seo', [])
        except Exception:
            pass

    def _ensure_report_table(self):
        """Create intelligence_reports table if it doesn't exist."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS intelligence_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        report_type TEXT NOT NULL,
                        report_date TEXT NOT NULL,
                        summary TEXT,
                        details TEXT,
                        alerts TEXT DEFAULT '[]',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(report_type, report_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_intelligence_reports_type_date
                    ON intelligence_reports (report_type, report_date)
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"intelligence_reports table creation failed: {e}")
            raise
        logger.info("intelligence_reports table ready")

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        """Check if a table exists in the database."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def _safe_query(self, conn: sqlite3.Connection, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query safely, returning empty list on error."""
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.debug(f"Query failed (may be expected): {e}")
            return []

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string in various formats."""
        if not date_str:
            return None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except (ValueError, AttributeError):
                continue
        return None

    def _rank_arrow(self, change: int) -> str:
        """Return an arrow indicator for rank change. Negative = improved."""
        if change < 0:
            return f"(+{abs(change)})"  # rank improved (number went down)
        elif change > 0:
            return f"(-{change})"  # rank dropped (number went up)
        return "(=)"

    def _trend_arrow(self, change: float) -> str:
        """Return trend arrow based on change direction."""
        if change > 2:
            return "^^"
        elif change > 0:
            return "^"
        elif change < -2:
            return "vv"
        elif change < 0:
            return "v"
        return "="

    # ====================================================================
    # REPORT 1: RANK INTELLIGENCE (순위 인텔리전스)
    # ====================================================================

    def generate_rank_intelligence(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Generate comprehensive rank intelligence report."""
        print("\n  [1/6] Rank Intelligence Report...")
        result = {"keywords": [], "summary_stats": {}, "text": "", "summary": ""}

        if not self._table_exists(conn, 'rank_history'):
            result["summary"] = "rank_history table not found. Skipped."
            print("    -> Skipped (missing rank_history)")
            return result

        # --- Gather all rank data ---
        all_ranks = self._safe_query(conn, """
            SELECT keyword, device_type, rank, status, checked_at,
                   COALESCE(target_name, '') as place_name
            FROM rank_history
            ORDER BY keyword, device_type, checked_at
        """)

        if not all_ranks:
            result["summary"] = "No rank data available."
            print("    -> No rank data")
            return result

        # Group by keyword + device_type (api_local → mobile로 통합)
        kw_device_data = defaultdict(list)
        for row in all_ranks:
            dt = row.get('device_type', 'mobile') or 'mobile'
            if dt == 'api_local':
                dt = 'mobile'
            key = (row['keyword'], dt)
            kw_device_data[key].append(row)

        # --- Get search volume data ---
        volume_map = {}
        competition_map = {}
        if self._table_exists(conn, 'naver_ad_keyword_data'):
            ad_data = self._safe_query(conn, """
                SELECT keyword, monthly_search_pc, monthly_search_mobile,
                       total_search_volume, competition_level
                FROM naver_ad_keyword_data
                WHERE is_related = 0 OR is_related IS NULL
            """)
            for row in ad_data:
                volume_map[row['keyword']] = {
                    'pc': row.get('monthly_search_pc', 0) or 0,
                    'mobile': row.get('monthly_search_mobile', 0) or 0,
                    'total': row.get('total_search_volume', 0) or 0,
                }
                competition_map[row['keyword']] = row.get('competition_level', '?') or '?'

        # --- Get keyword trend data ---
        trend_map = {}
        if self._table_exists(conn, 'keyword_trend_daily'):
            trend_data = self._safe_query(conn, """
                SELECT keyword, trend_date, ratio
                FROM keyword_trend_daily
                ORDER BY keyword, trend_date
            """)
            kw_trends = defaultdict(list)
            for row in trend_data:
                kw_trends[row['keyword']].append({
                    'date': row['trend_date'],
                    'ratio': row.get('ratio', 0) or 0,
                })
            for kw, points in kw_trends.items():
                if len(points) >= 2:
                    first_half = points[:len(points)//2]
                    second_half = points[len(points)//2:]
                    avg_first = sum(p['ratio'] for p in first_half) / len(first_half) if first_half else 0
                    avg_second = sum(p['ratio'] for p in second_half) / len(second_half) if second_half else 0
                    diff = avg_second - avg_first
                    if diff > 5:
                        trend_map[kw] = "RISING"
                    elif diff < -5:
                        trend_map[kw] = "FALLING"
                    else:
                        trend_map[kw] = "STABLE"
                    trend_map[f"{kw}_latest"] = points[-1]['ratio']
                    trend_map[f"{kw}_diff"] = round(diff, 1)
                elif len(points) == 1:
                    trend_map[kw] = "INSUFFICIENT"
                    trend_map[f"{kw}_latest"] = points[0]['ratio']

        # --- Get blog rank data ---
        blog_rank_map = {}
        if self._table_exists(conn, 'blog_rank_history'):
            blog_ranks = self._safe_query(conn, """
                SELECT keyword, rank_position, found, result_title, tracked_at
                FROM blog_rank_history
                ORDER BY keyword, tracked_at DESC
            """)
            for row in blog_ranks:
                if row['keyword'] not in blog_rank_map:
                    blog_rank_map[row['keyword']] = {
                        'rank': row.get('rank_position', 0),
                        'found': row.get('found', 0),
                        'title': row.get('result_title', ''),
                        'date': row.get('tracked_at', ''),
                    }

        # --- Get geo-grid data ---
        geo_map = {}
        if self._table_exists(conn, 'geo_grid_rankings'):
            geo_data = self._safe_query(conn, """
                SELECT keyword, grid_label, rank, status, arp
                FROM geo_grid_rankings
                ORDER BY keyword, grid_label
            """)
            kw_geo = defaultdict(list)
            for row in geo_data:
                kw_geo[row['keyword']].append(row)
            for kw, grids in kw_geo.items():
                found_count = sum(1 for g in grids if g.get('status') == 'found' or (g.get('rank') and g['rank'] > 0))
                total = len(grids)
                avg_rank = 0
                ranked = [g['rank'] for g in grids if g.get('rank') and g['rank'] > 0]
                if ranked:
                    avg_rank = sum(ranked) / len(ranked)
                geo_map[kw] = {
                    'coverage': f"{found_count}/{total}",
                    'found': found_count,
                    'total': total,
                    'avg_rank': round(avg_rank, 1),
                    'arp': round(sum(g.get('arp', 0) or 0 for g in grids) / max(1, len(grids)), 1),
                }

        # --- Build per-keyword analysis ---
        unique_keywords = sorted(set(row['keyword'] for row in all_ranks))
        keyword_reports = []
        all_current_ranks = []  # for summary stats
        improving_count = 0
        declining_count = 0
        volatile_keywords = []

        lines = []
        lines.append("=" * 70)
        lines.append("  RANK INTELLIGENCE REPORT (순위 인텔리전스)")
        lines.append(f"  {self.business_name} - {self.report_date}")
        lines.append("=" * 70)

        for kw in unique_keywords:
            kw_report = {"keyword": kw}
            kw_lines = []
            kw_lines.append(f"\n  --- {kw} ---")

            # Current rank for mobile & desktop
            for device in ['mobile', 'desktop']:
                key = (kw, device)
                records = kw_device_data.get(key, [])
                if not records:
                    kw_report[f'{device}_rank'] = 'N/A'
                    kw_report[f'{device}_status'] = 'no_data'
                    continue

                # Latest record
                latest = records[-1]
                current_rank = latest.get('rank', 0) or 0
                current_status = latest.get('status', 'unknown')

                kw_report[f'{device}_rank'] = current_rank if current_status == 'found' else current_status
                kw_report[f'{device}_status'] = current_status

                # Best ever rank
                found_records = [r for r in records if r.get('status') == 'found' and r.get('rank', 0)]
                best_rank = min((r['rank'] for r in found_records), default=0)
                kw_report[f'{device}_best'] = best_rank

                # Rank trajectory across scan dates
                scan_dates = []
                for r in records:
                    if r.get('status') == 'found' and r.get('rank', 0):
                        scan_dates.append((r['checked_at'], r['rank']))

                # Rank change (first vs last among found)
                rank_change = 0
                if len(scan_dates) >= 2:
                    rank_change = scan_dates[-1][1] - scan_dates[0][1]
                    kw_report[f'{device}_change'] = rank_change

                # Volatility (max - min rank)
                if found_records:
                    ranks_list = [r['rank'] for r in found_records]
                    volatility = max(ranks_list) - min(ranks_list)
                    kw_report[f'{device}_volatility'] = volatility
                    if device == 'mobile':
                        volatile_keywords.append((kw, volatility))

                # Days since last scan
                last_checked = self._parse_date(latest.get('checked_at', ''))
                days_since = (datetime.now() - last_checked).days if last_checked else -1
                kw_report[f'{device}_days_since_scan'] = days_since

                # Competitors above us
                competitors_above = set()
                for r in records:
                    pn = r.get('place_name', '')
                    if pn and self.business_short not in pn and self.business_name not in pn:
                        competitors_above.add(pn)
                kw_report[f'{device}_competitors_above'] = list(competitors_above)[:5]

                if current_status == 'found':
                    rank_str = f"{current_rank}위"
                    if best_rank and best_rank != current_rank:
                        rank_str += f" (최고: {best_rank}위)"
                    if rank_change != 0:
                        arrow = "^" if rank_change < 0 else "v"
                        rank_str += f" [{arrow}{abs(rank_change)}]"
                    kw_lines.append(f"    {device.upper():>8}: {rank_str}")
                    if device == 'mobile' and current_rank > 0:
                        all_current_ranks.append(current_rank)
                        if rank_change < 0:
                            improving_count += 1
                        elif rank_change > 0:
                            declining_count += 1
                else:
                    kw_lines.append(f"    {device.upper():>8}: {current_status}")

                if days_since >= 0:
                    freshness = "FRESH" if days_since <= 1 else ("OK" if days_since <= 3 else "STALE")
                    kw_lines.append(f"    {'':>8}  Last scan: {days_since}d ago [{freshness}]")

            # Desktop vs mobile difference
            m_rank = kw_report.get('mobile_rank', 'N/A')
            d_rank = kw_report.get('desktop_rank', 'N/A')
            if isinstance(m_rank, int) and isinstance(d_rank, int) and m_rank > 0 and d_rank > 0:
                diff = abs(m_rank - d_rank)
                if diff > 0:
                    kw_lines.append(f"    DIFF    : Mobile-Desktop gap = {diff} positions")
                    kw_report['mobile_desktop_diff'] = diff

            # Search volume
            vol_data = volume_map.get(kw)
            if vol_data:
                kw_lines.append(f"    VOLUME  : {vol_data['total']:,} (PC: {vol_data['pc']:,} / Mobile: {vol_data['mobile']:,})")
                kw_report['search_volume'] = vol_data['total']
                comp = competition_map.get(kw, '?')
                kw_lines.append(f"    COMP    : {comp}")
                kw_report['competition'] = comp

            # Trend
            trend_dir = trend_map.get(kw)
            if trend_dir:
                latest_ratio = trend_map.get(f"{kw}_latest", 0)
                diff_val = trend_map.get(f"{kw}_diff", 0)
                kw_lines.append(f"    TREND   : {trend_dir} (ratio: {latest_ratio}, delta: {diff_val:+.1f})")
                kw_report['trend'] = trend_dir

            # Blog VIEW rank
            blog = blog_rank_map.get(kw)
            if blog:
                if blog['found']:
                    kw_lines.append(f"    BLOG    : VIEW tab #{blog['rank']} - {blog['title'][:40]}")
                else:
                    kw_lines.append(f"    BLOG    : Not found in VIEW tab")
                kw_report['blog_rank'] = blog['rank'] if blog['found'] else 'not_found'

            # Geo-grid coverage
            geo = geo_map.get(kw)
            if geo:
                kw_lines.append(f"    GEO     : Coverage {geo['coverage']} | Avg rank {geo['avg_rank']} | ARP {geo['arp']}")
                kw_report['geo_coverage'] = geo['coverage']
                kw_report['geo_avg_rank'] = geo['avg_rank']

            # Competitors above us (mobile, deduplicated)
            comps = kw_report.get('mobile_competitors_above', [])
            if comps:
                kw_lines.append(f"    ABOVE US: {', '.join(comps[:5])}")

            keyword_reports.append(kw_report)
            lines.extend(kw_lines)

        # --- Summary Statistics ---
        top5 = sum(1 for r in all_current_ranks if r <= 5)
        top10 = sum(1 for r in all_current_ranks if r <= 10)
        top20 = sum(1 for r in all_current_ranks if r <= 20)
        outside20 = sum(1 for r in all_current_ranks if r > 20)
        avg_rank = round(sum(all_current_ranks) / len(all_current_ranks), 1) if all_current_ranks else 0

        volatile_keywords.sort(key=lambda x: x[1], reverse=True)
        most_volatile = volatile_keywords[:5]

        summary_stats = {
            "total_keywords": len(unique_keywords),
            "ranked_keywords": len(all_current_ranks),
            "top5": top5,
            "top10": top10,
            "top20": top20,
            "outside20": outside20,
            "avg_rank": avg_rank,
            "improving": improving_count,
            "declining": declining_count,
            "most_volatile": [(kw, v) for kw, v in most_volatile],
        }

        lines.append(f"\n  {'='*50}")
        lines.append(f"  SUMMARY STATISTICS")
        lines.append(f"  {'='*50}")
        lines.append(f"  Total keywords tracked: {len(unique_keywords)}")
        lines.append(f"  Keywords with ranking : {len(all_current_ranks)}")
        lines.append(f"  Top 5  : {top5}")
        lines.append(f"  Top 10 : {top10}")
        lines.append(f"  Top 20 : {top20}")
        lines.append(f"  Outside: {outside20}")
        lines.append(f"  Average rank: {avg_rank}")
        lines.append(f"  Improving: {improving_count} | Declining: {declining_count}")
        if most_volatile:
            lines.append(f"  Most volatile: {', '.join(f'{kw}({v})' for kw, v in most_volatile)}")

        text = "\n".join(lines)
        result["keywords"] = keyword_reports
        result["summary_stats"] = summary_stats
        result["text"] = text
        result["summary"] = (
            f"Tracked {len(unique_keywords)} keywords. "
            f"Ranked: {len(all_current_ranks)} (Top5: {top5}, Top10: {top10}). "
            f"Avg rank: {avg_rank}. Improving: {improving_count}, Declining: {declining_count}."
        )

        # Alerts for rank drops
        for kr in keyword_reports:
            mobile_change = kr.get('mobile_change', 0)
            if mobile_change > 5:
                self.alerts.append(
                    f"RANK DROP: '{kr['keyword']}' dropped {mobile_change} positions "
                    f"(now {kr.get('mobile_rank', '?')})"
                )

        print(text)
        print(f"\n    -> {len(unique_keywords)} keywords analyzed, {len(all_current_ranks)} ranked")
        return result

    # ====================================================================
    # REPORT 2: COMPETITOR THREAT (경쟁사 위협 분석)
    # ====================================================================

    def generate_competitor_threat(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Generate detailed competitor threat analysis."""
        print("\n  [2/6] Competitor Threat Report...")
        result = {"competitors": [], "text": "", "summary": ""}

        competitors_data = defaultdict(lambda: {
            "total_reviews": 0,
            "avg_rating": 0.0,
            "reviews_list": [],
            "review_velocity": 0.0,
            "response_rate": 0.0,
            "suspicious_score": 0,
            "blog_posts": [],
            "blog_keywords": set(),
            "blog_frequency": 0.0,
            "keywords_above_us": [],
            "photo_review_ratio": 0.0,
        })

        all_competitors = set()

        # Source 1: review_intelligence (aggregated review data)
        if self._table_exists(conn, 'review_intelligence'):
            ri_data = self._safe_query(conn, """
                SELECT competitor_name, total_reviews, avg_rating,
                       photo_review_count, photo_review_ratio,
                       response_count, response_rate,
                       suspicious_score, collected_at
                FROM review_intelligence
                ORDER BY competitor_name, collected_at DESC
            """)
            seen = set()
            for row in ri_data:
                cn = row['competitor_name']
                all_competitors.add(cn)
                if cn not in seen:
                    seen.add(cn)
                    competitors_data[cn]['total_reviews'] = row.get('total_reviews', 0) or 0
                    competitors_data[cn]['avg_rating'] = row.get('avg_rating', 0) or 0
                    competitors_data[cn]['response_rate'] = row.get('response_rate', 0) or 0
                    competitors_data[cn]['suspicious_score'] = row.get('suspicious_score', 0) or 0
                    competitors_data[cn]['photo_review_ratio'] = row.get('photo_review_ratio', 0) or 0

        # Source 2: competitor_reviews (individual reviews for velocity calc)
        if self._table_exists(conn, 'competitor_reviews'):
            cr_data = self._safe_query(conn, """
                SELECT competitor_name, rating, review_date, scraped_at
                FROM competitor_reviews
                ORDER BY competitor_name, review_date
            """)
            cr_by_comp = defaultdict(list)
            for row in cr_data:
                cn = row['competitor_name']
                all_competitors.add(cn)
                cr_by_comp[cn].append(row)

            for cn, reviews in cr_by_comp.items():
                if not competitors_data[cn]['total_reviews']:
                    competitors_data[cn]['total_reviews'] = len(reviews)
                if not competitors_data[cn]['avg_rating'] and reviews:
                    ratings = [r.get('rating', 0) or 0 for r in reviews if r.get('rating')]
                    if ratings:
                        competitors_data[cn]['avg_rating'] = round(sum(ratings) / len(ratings), 2)

                # Calculate review velocity (reviews per week)
                dates = []
                for r in reviews:
                    rd = r.get('review_date') or r.get('scraped_at', '')
                    parsed = self._parse_date(rd)
                    if parsed:
                        dates.append(parsed)
                if len(dates) >= 2:
                    dates.sort()
                    span_days = max((dates[-1] - dates[0]).days, 1)
                    velocity_per_week = len(dates) / (span_days / 7.0)
                    competitors_data[cn]['review_velocity'] = round(velocity_per_week, 1)

                competitors_data[cn]['reviews_list'] = reviews

        # Source 3: competitor_blog_activity
        if self._table_exists(conn, 'competitor_blog_activity'):
            blog_data = self._safe_query(conn, """
                SELECT competitor_name, blog_title, post_date, matched_keywords, detected_at
                FROM competitor_blog_activity
                ORDER BY competitor_name, post_date DESC
            """)
            blog_by_comp = defaultdict(list)
            for row in blog_data:
                cn = row['competitor_name']
                all_competitors.add(cn)
                blog_by_comp[cn].append(row)
                # Track keywords
                mk = row.get('matched_keywords', '')
                if mk:
                    for k in mk.split(','):
                        k = k.strip()
                        if k:
                            competitors_data[cn]['blog_keywords'].add(k)

            for cn, posts in blog_by_comp.items():
                competitors_data[cn]['blog_posts'] = posts
                # Blog frequency (posts per month)
                dates = []
                for p in posts:
                    parsed = self._parse_date(p.get('post_date', '') or p.get('detected_at', ''))
                    if parsed:
                        dates.append(parsed)
                if len(dates) >= 2:
                    dates.sort()
                    span_days = max((dates[-1] - dates[0]).days, 1)
                    freq = len(dates) / (span_days / 30.0)
                    competitors_data[cn]['blog_frequency'] = round(freq, 1)
                elif dates:
                    competitors_data[cn]['blog_frequency'] = len(dates)

        # Source 4: rank_history (find keywords where competitors outrank us)
        if self._table_exists(conn, 'rank_history'):
            # Get our latest rank per keyword
            our_ranks = self._safe_query(conn, """
                SELECT keyword, device_type, rank
                FROM rank_history
                WHERE status = 'found'
                AND id IN (
                    SELECT MAX(id) FROM rank_history
                    WHERE status = 'found'
                    GROUP BY keyword, device_type
                )
            """)
            our_rank_map = {}
            for r in our_ranks:
                key = (r['keyword'], _norm_device(r.get('device_type')))
                our_rank_map[key] = r['rank']

            # Get place_name occurrences (competitors appearing in results)
            place_names = self._safe_query(conn, """
                SELECT keyword, device_type, COALESCE(target_name, '') as place_name, rank
                FROM rank_history
                WHERE target_name IS NOT NULL AND target_name != ''
                AND status = 'found'
                AND id IN (
                    SELECT MAX(id) FROM rank_history
                    WHERE target_name IS NOT NULL AND target_name != ''
                    GROUP BY keyword, device_type, target_name
                )
            """)
            for pn in place_names:
                comp_name = pn.get('place_name', '')
                if not comp_name or self.business_short in comp_name or self.business_name in comp_name:
                    continue
                # Check if this competitor ranks above us for this keyword
                key = (pn['keyword'], pn.get('device_type', 'mobile') or 'mobile')
                our_rank = our_rank_map.get(key, 999)
                comp_rank = pn.get('rank', 0) or 0
                if comp_rank > 0 and comp_rank < our_rank:
                    competitors_data[comp_name]['keywords_above_us'].append({
                        'keyword': pn['keyword'],
                        'their_rank': comp_rank,
                        'our_rank': our_rank,
                    })
                    all_competitors.add(comp_name)

        if not all_competitors:
            result["summary"] = "No competitor data available."
            print("    -> No competitor data")
            return result

        # --- Calculate threat scores and build report ---
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("  COMPETITOR THREAT REPORT (경쟁사 위협 분석)")
        lines.append(f"  {self.business_name} - {self.report_date}")
        lines.append("=" * 70)

        competitor_reports = []
        for cn in sorted(all_competitors):
            data = competitors_data[cn]

            # --- Threat Score Calculation ---
            # Review Strength (30 points)
            review_strength = 0
            tr = data['total_reviews']
            if tr >= 500:
                review_strength += 10
            elif tr >= 200:
                review_strength += 7
            elif tr >= 50:
                review_strength += 4
            elif tr > 0:
                review_strength += 2

            ar = data['avg_rating']
            if ar >= 4.5:
                review_strength += 8
            elif ar >= 4.0:
                review_strength += 5
            elif ar >= 3.5:
                review_strength += 3

            rv = data['review_velocity']
            if rv >= 10:
                review_strength += 7
            elif rv >= 5:
                review_strength += 5
            elif rv >= 2:
                review_strength += 3
            elif rv > 0:
                review_strength += 1

            rr = data['response_rate']
            if rr >= 80:
                review_strength += 5
            elif rr >= 50:
                review_strength += 3
            elif rr > 0:
                review_strength += 1

            review_strength = min(review_strength, 30)

            # Content Activity (25 points)
            content_activity = 0
            bf = data['blog_frequency']
            if bf >= 8:
                content_activity += 15
            elif bf >= 4:
                content_activity += 10
            elif bf >= 2:
                content_activity += 6
            elif bf > 0:
                content_activity += 3

            bk_count = len(data['blog_keywords'])
            if bk_count >= 10:
                content_activity += 10
            elif bk_count >= 5:
                content_activity += 7
            elif bk_count >= 2:
                content_activity += 4
            elif bk_count > 0:
                content_activity += 2

            content_activity = min(content_activity, 25)

            # Ranking Position (25 points)
            ranking_score = 0
            kw_above = data['keywords_above_us']
            if len(kw_above) >= 10:
                ranking_score = 25
            elif len(kw_above) >= 5:
                ranking_score = 18
            elif len(kw_above) >= 3:
                ranking_score = 12
            elif len(kw_above) >= 1:
                ranking_score = 6

            ranking_score = min(ranking_score, 25)

            # Review Authenticity Concern (20 points) - higher suspicious = lower threat
            # (suspicious reviews mean their advantage is fake)
            authenticity_concern = 0
            ss = data['suspicious_score']
            pr = data['photo_review_ratio']
            if ss >= 70:
                authenticity_concern = 5  # very suspicious = less real threat
            elif ss >= 40:
                authenticity_concern = 10
            else:
                authenticity_concern = 18  # reviews look legit = real threat

            if pr >= 30:
                authenticity_concern = min(authenticity_concern + 2, 20)  # high photo ratio = more legit

            authenticity_concern = min(authenticity_concern, 20)

            total_threat = review_strength + content_activity + ranking_score + authenticity_concern
            total_threat = min(total_threat, 100)

            if total_threat >= 70:
                threat_level = "HIGH"
            elif total_threat >= 40:
                threat_level = "MEDIUM"
            else:
                threat_level = "LOW"

            # Action recommendations
            actions = []
            if ranking_score >= 12:
                kw_list = ', '.join(k['keyword'] for k in kw_above[:3])
                actions.append(f"Focus content on keywords where they beat us: {kw_list}")
            if data['review_velocity'] > 5:
                actions.append("Accelerate review collection campaign")
            if data['blog_frequency'] > 4:
                actions.append("Increase blog posting frequency to match")
            if data['avg_rating'] > 4.3 and data['total_reviews'] > 100:
                actions.append("Improve service quality to match their high rating")
            if data['suspicious_score'] >= 50:
                actions.append("Monitor for fake review patterns (possible report opportunity)")
            if not actions:
                actions.append("Continue monitoring")

            comp_report = {
                "competitor": cn,
                "total_reviews": tr,
                "avg_rating": ar,
                "review_velocity": rv,
                "response_rate": rr,
                "blog_frequency": bf,
                "blog_keywords": list(data['blog_keywords']),
                "keywords_above_us": kw_above,
                "suspicious_score": ss,
                "photo_review_ratio": pr,
                "threat_score": total_threat,
                "threat_level": threat_level,
                "breakdown": {
                    "review_strength": review_strength,
                    "content_activity": content_activity,
                    "ranking_position": ranking_score,
                    "authenticity": authenticity_concern,
                },
                "actions": actions,
            }
            competitor_reports.append(comp_report)

            # Build text
            lines.append(f"\n  --- {cn} ---")
            lines.append(f"    Threat Score : {total_threat}/100 [{threat_level}]")
            lines.append(f"    Breakdown    : Reviews({review_strength}/30) Content({content_activity}/25) Rank({ranking_score}/25) Auth({authenticity_concern}/20)")
            lines.append(f"    Reviews      : {tr} total | Rating {ar:.1f} | Velocity {rv:.1f}/week | Response {rr:.0f}%")
            lines.append(f"    Blog         : Freq {bf:.1f}/month | Keywords: {', '.join(list(data['blog_keywords'])[:5]) or 'none'}")
            lines.append(f"    Suspicious   : {ss}% | Photo ratio: {pr:.0f}%")
            if kw_above:
                kw_strs = [f"{k['keyword']}(#{k['their_rank']})" for k in kw_above[:5]]
                lines.append(f"    Beats us on  : {', '.join(kw_strs)}")
            lines.append(f"    Actions      : {' | '.join(actions[:3])}")

            if threat_level == "HIGH":
                self.alerts.append(
                    f"HIGH THREAT: {cn} (score {total_threat}/100) - "
                    f"{tr} reviews, {ar:.1f} rating, {rv:.1f} reviews/week, "
                    f"beats us on {len(kw_above)} keywords"
                )

        # Sort by threat score
        competitor_reports.sort(key=lambda x: x['threat_score'], reverse=True)

        # Summary
        high_count = sum(1 for c in competitor_reports if c['threat_level'] == 'HIGH')
        med_count = sum(1 for c in competitor_reports if c['threat_level'] == 'MEDIUM')
        low_count = sum(1 for c in competitor_reports if c['threat_level'] == 'LOW')

        lines.append(f"\n  {'='*50}")
        lines.append(f"  THREAT SUMMARY: {high_count} HIGH | {med_count} MEDIUM | {low_count} LOW")
        lines.append(f"  Total competitors analyzed: {len(competitor_reports)}")

        text = "\n".join(lines)
        result["competitors"] = competitor_reports
        result["text"] = text
        result["summary"] = (
            f"Analyzed {len(competitor_reports)} competitors. "
            f"{high_count} HIGH, {med_count} MEDIUM, {low_count} LOW threat."
        )

        print(text)
        print(f"\n    -> {len(competitor_reports)} competitors analyzed")
        return result

    # ====================================================================
    # REPORT 3: KEYWORD OPPORTUNITY (키워드 기회 분석)
    # ====================================================================

    def generate_keyword_opportunities(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Generate keyword opportunity analysis."""
        print("\n  [3/6] Keyword Opportunity Report...")
        result = {"keywords": [], "easy_wins": [], "long_term": [], "priority": [], "text": "", "summary": ""}

        # --- Get ad keyword data ---
        ad_data = {}
        if self._table_exists(conn, 'naver_ad_keyword_data'):
            rows = self._safe_query(conn, """
                SELECT keyword, monthly_search_pc, monthly_search_mobile,
                       total_search_volume, competition_level, avg_ad_count,
                       is_related, source_keyword
                FROM naver_ad_keyword_data
                ORDER BY total_search_volume DESC
            """)
            for row in rows:
                ad_data[row['keyword']] = row

        # --- Get our current ranks ---
        rank_map = {}
        if self._table_exists(conn, 'rank_history'):
            rank_rows = self._safe_query(conn, """
                SELECT keyword, device_type, rank, status
                FROM rank_history
                WHERE id IN (
                    SELECT MAX(id) FROM rank_history
                    GROUP BY keyword, device_type
                )
            """)
            for row in rank_rows:
                key = row['keyword']
                device = _norm_device(row.get('device_type'))
                if device == 'mobile':
                    if row.get('status') == 'found':
                        rank_map[key] = row.get('rank', 0) or 0
                    elif key not in rank_map:
                        rank_map[key] = 0  # not ranked

        # --- Get blog ranks ---
        blog_rank_map = {}
        if self._table_exists(conn, 'blog_rank_history'):
            br = self._safe_query(conn, """
                SELECT keyword, rank_position, found
                FROM blog_rank_history
                WHERE id IN (SELECT MAX(id) FROM blog_rank_history GROUP BY keyword)
            """)
            for row in br:
                blog_rank_map[row['keyword']] = row.get('rank_position', 0) if row.get('found') else 0

        # --- Get keyword trends ---
        trend_map = {}
        if self._table_exists(conn, 'keyword_trend_daily'):
            td = self._safe_query(conn, """
                SELECT keyword, trend_date, ratio
                FROM keyword_trend_daily
                ORDER BY keyword, trend_date
            """)
            kw_trends = defaultdict(list)
            for row in td:
                kw_trends[row['keyword']].append(row.get('ratio', 0) or 0)
            for kw, ratios in kw_trends.items():
                if len(ratios) >= 2:
                    first_half_avg = sum(ratios[:len(ratios)//2]) / max(1, len(ratios)//2)
                    second_half_avg = sum(ratios[len(ratios)//2:]) / max(1, len(ratios) - len(ratios)//2)
                    diff = second_half_avg - first_half_avg
                    if diff > 5:
                        trend_map[kw] = "RISING"
                    elif diff < -5:
                        trend_map[kw] = "FALLING"
                    else:
                        trend_map[kw] = "STABLE"

        # --- Get community mention counts ---
        mention_counts = {}
        lead_counts = {}
        if self._table_exists(conn, 'community_mentions'):
            mc = self._safe_query(conn, """
                SELECT keyword, COUNT(*) as cnt,
                       SUM(CASE WHEN is_lead_candidate = 1 THEN 1 ELSE 0 END) as leads
                FROM community_mentions
                GROUP BY keyword
            """)
            for row in mc:
                mention_counts[row['keyword']] = row['cnt']
                lead_counts[row['keyword']] = row.get('leads', 0) or 0

        # --- Get related keywords ---
        related_map = defaultdict(list)
        if self._table_exists(conn, 'naver_ad_keyword_data'):
            rel = self._safe_query(conn, """
                SELECT keyword, source_keyword, total_search_volume, competition_level
                FROM naver_ad_keyword_data
                WHERE is_related = 1
                ORDER BY source_keyword, total_search_volume DESC
            """)
            for row in rel:
                src = row.get('source_keyword', '')
                if src:
                    related_map[src].append({
                        'keyword': row['keyword'],
                        'volume': row.get('total_search_volume', 0) or 0,
                        'competition': row.get('competition_level', '?'),
                    })

        # --- Build keyword opportunity analysis ---
        # Combine all keywords: place + blog + any in ad_data
        all_kws = set(self.place_keywords + self.blog_keywords + list(ad_data.keys()))
        # Focus on keywords that are in our tracking or have our region
        tracked_kws = set(self.place_keywords + self.blog_keywords)

        comp_map = {"낮음": 1, "중간": 2, "높음": 3}

        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("  KEYWORD OPPORTUNITY REPORT (키워드 기회 분석)")
        lines.append(f"  {self.business_name} - {self.report_date}")
        lines.append("=" * 70)

        keyword_reports = []
        easy_wins = []
        long_term = []
        priority_capture = []

        for kw in sorted(tracked_kws):
            ad = ad_data.get(kw, {})
            volume = ad.get('total_search_volume', 0) or 0
            pc_vol = ad.get('monthly_search_pc', 0) or 0
            mobile_vol = ad.get('monthly_search_mobile', 0) or 0
            comp_level = ad.get('competition_level', '') or ''
            comp_score = comp_map.get(comp_level, 2)
            current_rank = rank_map.get(kw, 0)
            blog_rank = blog_rank_map.get(kw, 0)
            trend = trend_map.get(kw, 'UNKNOWN')
            mentions = mention_counts.get(kw, 0)
            leads = lead_counts.get(kw, 0)
            related = related_map.get(kw, [])[:5]

            # --- Opportunity Score ---
            # Volume factor (0-30)
            if volume >= 5000:
                vol_score = 30
            elif volume >= 1000:
                vol_score = 25
            elif volume >= 500:
                vol_score = 20
            elif volume >= 100:
                vol_score = 15
            elif volume >= 30:
                vol_score = 10
            elif volume > 0:
                vol_score = 5
            else:
                vol_score = 0

            # Competition factor (0-25)
            if comp_score == 1:  # 낮음
                comp_factor = 25
            elif comp_score == 2:  # 중간
                comp_factor = 15
            else:  # 높음
                comp_factor = 5

            # Rank proximity factor (0-25)
            if 1 <= current_rank <= 5:
                rank_factor = 10  # already good
            elif 6 <= current_rank <= 10:
                rank_factor = 25  # almost there
            elif 11 <= current_rank <= 20:
                rank_factor = 20  # within reach
            elif 21 <= current_rank <= 50:
                rank_factor = 12
            elif current_rank > 50:
                rank_factor = 5
            else:
                rank_factor = 8  # not ranked yet

            # Trend factor (0-20)
            if trend == "RISING":
                trend_factor = 20
            elif trend == "STABLE":
                trend_factor = 10
            elif trend == "FALLING":
                trend_factor = 3
            else:
                trend_factor = 8

            opportunity_score = vol_score + comp_factor + rank_factor + trend_factor

            # Classify opportunity type
            opp_type = "MONITOR"
            if volume >= 30 and comp_score <= 2 and 6 <= current_rank <= 20:
                opp_type = "EASY WIN"
                easy_wins.append(kw)
            elif volume >= 100 and comp_score >= 3 and (current_rank > 20 or current_rank == 0):
                opp_type = "LONG TERM"
                long_term.append(kw)
            elif trend == "RISING":
                opp_type = "PRIORITY CAPTURE"
                priority_capture.append(kw)
            elif 1 <= current_rank <= 5:
                opp_type = "DEFEND"

            kw_report = {
                "keyword": kw,
                "volume_total": volume,
                "volume_pc": pc_vol,
                "volume_mobile": mobile_vol,
                "competition": comp_level,
                "current_rank": current_rank if current_rank else "not_ranked",
                "blog_rank": blog_rank if blog_rank else "not_found",
                "trend": trend,
                "opportunity_score": opportunity_score,
                "opportunity_type": opp_type,
                "community_mentions": mentions,
                "lead_candidates": leads,
                "related_keywords": related,
                "score_breakdown": {
                    "volume": vol_score,
                    "competition": comp_factor,
                    "rank_proximity": rank_factor,
                    "trend": trend_factor,
                },
            }
            keyword_reports.append(kw_report)

            # Text output
            rank_str = f"#{current_rank}" if current_rank else "N/R"
            blog_str = f"#{blog_rank}" if blog_rank else "N/F"
            lines.append(f"\n  --- {kw} [{opp_type}] ---")
            lines.append(f"    Score   : {opportunity_score}/100 (Vol:{vol_score} Comp:{comp_factor} Rank:{rank_factor} Trend:{trend_factor})")
            lines.append(f"    Volume  : {volume:,} (PC: {pc_vol:,} / Mobile: {mobile_vol:,})")
            lines.append(f"    Comp    : {comp_level or 'N/A'}")
            lines.append(f"    Rank    : Place {rank_str} | Blog VIEW {blog_str}")
            lines.append(f"    Trend   : {trend}")
            if mentions:
                lines.append(f"    Community: {mentions} mentions | {leads} lead candidates")
            if related:
                rel_strs = [f"{r['keyword']}({r['volume']:,})" for r in related[:3]]
                lines.append(f"    Related : {', '.join(rel_strs)}")

        # Sort by opportunity score
        keyword_reports.sort(key=lambda x: x['opportunity_score'], reverse=True)

        lines.append(f"\n  {'='*50}")
        lines.append(f"  OPPORTUNITY SUMMARY")
        lines.append(f"  {'='*50}")
        lines.append(f"  Total keywords analyzed: {len(keyword_reports)}")
        lines.append(f"  EASY WIN     : {len(easy_wins)} - {', '.join(easy_wins[:5]) or 'none'}")
        lines.append(f"  LONG TERM    : {len(long_term)} - {', '.join(long_term[:5]) or 'none'}")
        lines.append(f"  PRIORITY     : {len(priority_capture)} - {', '.join(priority_capture[:5]) or 'none'}")
        if keyword_reports:
            top3 = keyword_reports[:3]
            lines.append(f"  Top 3 by score: {', '.join(f'{k['keyword']}({k['opportunity_score']})' for k in top3)}")

        text = "\n".join(lines)
        result["keywords"] = keyword_reports
        result["easy_wins"] = easy_wins
        result["long_term"] = long_term
        result["priority"] = priority_capture
        result["text"] = text
        result["summary"] = (
            f"Analyzed {len(keyword_reports)} keywords. "
            f"Easy wins: {len(easy_wins)}, Long term: {len(long_term)}, "
            f"Priority capture: {len(priority_capture)}."
        )

        if easy_wins:
            self.alerts.append(
                f"EASY WINS: {len(easy_wins)} keywords ready for quick ranking improvement: "
                f"{', '.join(easy_wins[:3])}"
            )

        print(text)
        print(f"\n    -> {len(keyword_reports)} keywords scored")
        return result

    # ====================================================================
    # REPORT 4: COMMUNITY & LEAD INTELLIGENCE
    # ====================================================================

    def generate_community_intelligence(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Generate community and lead intelligence report."""
        print("\n  [4/6] Community & Lead Intelligence Report...")
        result = {"platforms": {}, "leads": [], "top_posts": [], "text": "", "summary": ""}

        if not self._table_exists(conn, 'community_mentions'):
            result["summary"] = "community_mentions table not found. Skipped."
            print("    -> Skipped (missing community_mentions)")
            return result

        # --- Total mentions by platform ---
        platform_data = self._safe_query(conn, """
            SELECT platform, COUNT(*) as cnt,
                   SUM(CASE WHEN is_lead_candidate = 1 THEN 1 ELSE 0 END) as leads,
                   SUM(CASE WHEN is_our_mention = 1 THEN 1 ELSE 0 END) as our_mentions
            FROM community_mentions
            GROUP BY platform
            ORDER BY cnt DESC
        """)

        # --- Mention type distribution ---
        type_data = self._safe_query(conn, """
            SELECT mention_type, COUNT(*) as cnt
            FROM community_mentions
            WHERE mention_type IS NOT NULL AND mention_type != ''
            GROUP BY mention_type
            ORDER BY cnt DESC
        """)

        # --- Most active keywords ---
        kw_data = self._safe_query(conn, """
            SELECT keyword, COUNT(*) as cnt,
                   SUM(CASE WHEN is_lead_candidate = 1 THEN 1 ELSE 0 END) as leads
            FROM community_mentions
            GROUP BY keyword
            ORDER BY cnt DESC
            LIMIT 20
        """)

        # --- Lead candidates (top examples) ---
        lead_data = self._safe_query(conn, """
            SELECT platform, keyword, title, content_preview, url, comment_count, engagement_count
            FROM community_mentions
            WHERE is_lead_candidate = 1
            ORDER BY engagement_count DESC, comment_count DESC
            LIMIT 15
        """)

        # --- Top engagement posts ---
        top_posts = self._safe_query(conn, """
            SELECT platform, keyword, title, content_preview, url, comment_count, engagement_count, mention_type
            FROM community_mentions
            ORDER BY comment_count DESC, engagement_count DESC
            LIMIT 10
        """)

        # --- Our mentions ---
        our_mentions = self._safe_query(conn, """
            SELECT platform, keyword, title, url, mention_type
            FROM community_mentions
            WHERE is_our_mention = 1
            ORDER BY scanned_at DESC
            LIMIT 10
        """)

        # --- Build report ---
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("  COMMUNITY & LEAD INTELLIGENCE (커뮤니티 & 리드)")
        lines.append(f"  {self.business_name} - {self.report_date}")
        lines.append("=" * 70)

        total_mentions = sum(p.get('cnt', 0) for p in platform_data)
        total_leads = sum(p.get('leads', 0) for p in platform_data)
        total_our = sum(p.get('our_mentions', 0) for p in platform_data)

        lines.append(f"\n  OVERVIEW:")
        lines.append(f"    Total mentions    : {total_mentions:,}")
        lines.append(f"    Lead candidates   : {total_leads}")
        lines.append(f"    Our mentions      : {total_our}")

        lines.append(f"\n  BY PLATFORM:")
        platforms_dict = {}
        for p in platform_data:
            pname = p.get('platform', 'unknown')
            cnt = p.get('cnt', 0)
            leads = p.get('leads', 0)
            our = p.get('our_mentions', 0)
            lines.append(f"    {pname:>12}: {cnt:>5} mentions | {leads:>3} leads | {our:>3} ours")
            platforms_dict[pname] = {"mentions": cnt, "leads": leads, "our_mentions": our}

        if type_data:
            lines.append(f"\n  BY MENTION TYPE:")
            type_dist = {}
            for t in type_data:
                mt = t.get('mention_type', 'unknown')
                cnt = t.get('cnt', 0)
                lines.append(f"    {mt:>15}: {cnt}")
                type_dist[mt] = cnt
            result["type_distribution"] = type_dist

        if kw_data:
            lines.append(f"\n  MOST ACTIVE KEYWORDS:")
            for k in kw_data[:10]:
                kw = k.get('keyword', '')
                cnt = k.get('cnt', 0)
                leads = k.get('leads', 0)
                lead_str = f" ({leads} leads)" if leads else ""
                lines.append(f"    {kw:>25}: {cnt} mentions{lead_str}")

        if lead_data:
            lines.append(f"\n  TOP LEAD CANDIDATES ({len(lead_data)}):")
            for i, ld in enumerate(lead_data[:10], 1):
                title = (ld.get('title', '') or '')[:50]
                platform = ld.get('platform', '')
                kw = ld.get('keyword', '')
                comments = ld.get('comment_count', 0) or 0
                engagement = ld.get('engagement_count', 0) or 0
                url = ld.get('url', '')
                lines.append(f"    {i}. [{platform}] {title}")
                lines.append(f"       KW: {kw} | Comments: {comments} | Engagement: {engagement}")
                if url:
                    lines.append(f"       URL: {url[:80]}")

        if top_posts:
            lines.append(f"\n  TOP ENGAGEMENT POSTS:")
            for i, tp in enumerate(top_posts[:5], 1):
                title = (tp.get('title', '') or '')[:50]
                platform = tp.get('platform', '')
                comments = tp.get('comment_count', 0) or 0
                lines.append(f"    {i}. [{platform}] {title} ({comments} comments)")

        if our_mentions:
            lines.append(f"\n  OUR MENTIONS ({len(our_mentions)}):")
            for om in our_mentions[:5]:
                title = (om.get('title', '') or '')[:50]
                platform = om.get('platform', '')
                mt = om.get('mention_type', '')
                lines.append(f"    [{platform}] {title} ({mt})")

        text = "\n".join(lines)
        result["platforms"] = platforms_dict
        result["leads"] = [dict(ld) for ld in lead_data]
        result["top_posts"] = [dict(tp) for tp in top_posts]
        result["our_mentions"] = [dict(om) for om in our_mentions]
        result["keyword_activity"] = [dict(k) for k in kw_data]
        result["text"] = text
        result["summary"] = (
            f"Total {total_mentions:,} mentions across {len(platforms_dict)} platforms. "
            f"Lead candidates: {total_leads}. Our mentions: {total_our}."
        )

        if total_leads >= 5:
            self.alerts.append(
                f"LEADS: {total_leads} lead candidates found in communities. "
                f"Check lead manager for follow-up."
            )

        print(text)
        print(f"\n    -> {total_mentions} mentions, {total_leads} leads")
        return result

    # ====================================================================
    # REPORT 5: ANOMALY & ALERT REPORT
    # ====================================================================

    def generate_anomaly_report(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Detect anomalies and generate alert report."""
        print("\n  [5/6] Anomaly & Alert Report...")
        anomalies = []

        # 1. Rank drops > 5 positions
        if self._table_exists(conn, 'rank_history'):
            rank_data = self._safe_query(conn, """
                SELECT keyword, device_type, rank, status, checked_at
                FROM rank_history
                WHERE status = 'found' AND rank > 0
                ORDER BY keyword, device_type, checked_at
            """)
            kw_device_ranks = defaultdict(list)
            for row in rank_data:
                key = (row['keyword'], row.get('device_type', 'mobile') or 'mobile')
                kw_device_ranks[key].append(row)

            for (kw, device), records in kw_device_ranks.items():
                if len(records) >= 2:
                    # Compare last two scans
                    prev_rank = records[-2]['rank']
                    curr_rank = records[-1]['rank']
                    change = curr_rank - prev_rank  # positive = rank dropped
                    if change > 5:
                        date_str = records[-1].get('checked_at', '')
                        anomalies.append({
                            "type": "rank_drop",
                            "severity": "HIGH" if change > 10 else "MEDIUM",
                            "description": f"Rank drop: '{kw}' ({device}) {prev_rank} -> {curr_rank} (+{change}) on {date_str[:10]}",
                            "keyword": kw,
                            "device": device,
                            "change": change,
                            "date": date_str,
                        })

                    # Also detect significant improvements
                    if change < -5:
                        anomalies.append({
                            "type": "rank_improvement",
                            "severity": "INFO",
                            "description": f"Rank improvement: '{kw}' ({device}) {prev_rank} -> {curr_rank} ({change})",
                            "keyword": kw,
                            "device": device,
                            "change": change,
                        })

                    # Detect volatility (large swings within last 5 scans)
                    last_5 = records[-5:]
                    ranks = [r['rank'] for r in last_5]
                    if max(ranks) - min(ranks) > 15:
                        anomalies.append({
                            "type": "rank_volatility",
                            "severity": "WARNING",
                            "description": f"High volatility: '{kw}' ({device}) ranged {min(ranks)}-{max(ranks)} in last {len(last_5)} scans",
                            "keyword": kw,
                            "range": f"{min(ranks)}-{max(ranks)}",
                        })

        # 2. Competitor review spikes
        if self._table_exists(conn, 'competitor_reviews'):
            # Check for clusters of recent reviews per competitor
            review_clusters = self._safe_query(conn, """
                SELECT competitor_name, COUNT(*) as cnt,
                       MIN(review_date) as first_date, MAX(review_date) as last_date
                FROM competitor_reviews
                WHERE review_date >= date('now', '-14 days')
                GROUP BY competitor_name
                HAVING cnt >= 10
            """)
            for rc in review_clusters:
                anomalies.append({
                    "type": "review_spike",
                    "severity": "WARNING",
                    "description": f"Review spike: {rc['competitor_name']} gained {rc['cnt']} reviews in last 14 days ({rc.get('first_date', '')} to {rc.get('last_date', '')})",
                    "competitor": rc['competitor_name'],
                    "count": rc['cnt'],
                })

        # 3. Competitor blog activity spikes
        if self._table_exists(conn, 'competitor_blog_activity'):
            blog_clusters = self._safe_query(conn, """
                SELECT competitor_name, COUNT(*) as cnt
                FROM competitor_blog_activity
                WHERE post_date >= date('now', '-7 days') OR detected_at >= date('now', '-7 days')
                GROUP BY competitor_name
                HAVING cnt >= 5
            """)
            for bc in blog_clusters:
                anomalies.append({
                    "type": "blog_spike",
                    "severity": "WARNING",
                    "description": f"Blog spike: {bc['competitor_name']} posted {bc['cnt']} blog articles in last 7 days",
                    "competitor": bc['competitor_name'],
                    "count": bc['cnt'],
                })

        # 4. Keyword trend surges/drops
        if self._table_exists(conn, 'keyword_trend_daily'):
            trend_data = self._safe_query(conn, """
                SELECT keyword, ratio, trend_date
                FROM keyword_trend_daily
                ORDER BY keyword, trend_date
            """)
            kw_ratios = defaultdict(list)
            for row in trend_data:
                kw_ratios[row['keyword']].append(row.get('ratio', 0) or 0)
            for kw, ratios in kw_ratios.items():
                if len(ratios) >= 3:
                    avg_prev = sum(ratios[:-1]) / len(ratios[:-1])
                    latest = ratios[-1]
                    if avg_prev > 0:
                        pct_change = ((latest - avg_prev) / avg_prev) * 100
                        if pct_change > 50:
                            anomalies.append({
                                "type": "trend_surge",
                                "severity": "INFO",
                                "description": f"Search trend surge: '{kw}' up {pct_change:.0f}% (avg {avg_prev:.0f} -> {latest})",
                                "keyword": kw,
                                "pct_change": round(pct_change, 1),
                            })
                        elif pct_change < -30:
                            anomalies.append({
                                "type": "trend_drop",
                                "severity": "WARNING",
                                "description": f"Search trend drop: '{kw}' down {abs(pct_change):.0f}% (avg {avg_prev:.0f} -> {latest})",
                                "keyword": kw,
                                "pct_change": round(pct_change, 1),
                            })

        # 5. Data staleness warnings
        stale_checks = [
            ("rank_history", "checked_at", 72, "Place rank scan"),
            ("blog_rank_history", "tracked_at", 72, "Blog rank scan"),
            ("review_intelligence", "collected_at", 168, "Review intelligence"),
            ("competitor_blog_activity", "detected_at", 168, "Blog activity scan"),
            ("community_mentions", "scanned_at", 72, "Community monitor"),
            ("naver_ad_keyword_data", "collected_date", 336, "Ad keyword data"),
            ("geo_grid_rankings", "scanned_at", 168, "Geo-grid scan"),
        ]

        for table_name, date_col, hours_threshold, label in stale_checks:
            if self._table_exists(conn, table_name):
                latest = self._safe_query(conn, f"""
                    SELECT MAX({date_col}) as latest_date
                    FROM {table_name}
                """)
                if latest and latest[0].get('latest_date'):
                    latest_date = self._parse_date(latest[0]['latest_date'])
                    if latest_date:
                        hours_old = (datetime.now() - latest_date).total_seconds() / 3600
                        if hours_old > hours_threshold:
                            anomalies.append({
                                "type": "data_stale",
                                "severity": "WARNING",
                                "description": f"Stale data: {label} ({table_name}) last updated {hours_old:.0f}h ago (threshold: {hours_threshold}h)",
                                "table": table_name,
                                "hours_old": round(hours_old, 1),
                            })

        # 6. Suspicious competitor activity (review_intelligence suspicious_score)
        if self._table_exists(conn, 'review_intelligence'):
            suspicious = self._safe_query(conn, """
                SELECT competitor_name, suspicious_score
                FROM review_intelligence
                WHERE suspicious_score >= 50
            """)
            for s in suspicious:
                anomalies.append({
                    "type": "suspicious_reviews",
                    "severity": "INFO",
                    "description": f"Suspicious reviews: {s['competitor_name']} has {s['suspicious_score']}% suspicious score",
                    "competitor": s['competitor_name'],
                    "score": s['suspicious_score'],
                })

        # Sort by severity
        severity_order = {"HIGH": 0, "MEDIUM": 1, "WARNING": 2, "INFO": 3}
        anomalies.sort(key=lambda x: severity_order.get(x.get('severity', 'INFO'), 99))

        # Add HIGH anomalies to alerts
        for a in anomalies:
            if a['severity'] == 'HIGH':
                self.alerts.append(f"ANOMALY: {a['description']}")

        # Build report text
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("  ANOMALY & ALERT REPORT")
        lines.append(f"  {self.business_name} - {self.report_date}")
        lines.append("=" * 70)

        high_count = sum(1 for a in anomalies if a['severity'] == 'HIGH')
        med_count = sum(1 for a in anomalies if a['severity'] == 'MEDIUM')
        warn_count = sum(1 for a in anomalies if a['severity'] == 'WARNING')
        info_count = sum(1 for a in anomalies if a['severity'] == 'INFO')

        lines.append(f"\n  TOTAL: {len(anomalies)} anomalies detected")
        lines.append(f"  HIGH: {high_count} | MEDIUM: {med_count} | WARNING: {warn_count} | INFO: {info_count}")

        severity_icons = {"HIGH": "[!!!]", "MEDIUM": "[!!]", "WARNING": "[!]", "INFO": "[-]"}
        for a in anomalies:
            icon = severity_icons.get(a.get('severity', 'INFO'), '[-]')
            lines.append(f"\n  {icon} {a['description']}")

        text = "\n".join(lines)
        result = {
            "anomalies": anomalies,
            "counts": {"high": high_count, "medium": med_count, "warning": warn_count, "info": info_count},
            "text": text,
            "summary": f"Detected {len(anomalies)} anomalies ({high_count} HIGH, {med_count} MEDIUM, {warn_count} WARNING).",
        }

        print(text)
        print(f"\n    -> {len(anomalies)} anomalies detected")
        return result

    # ====================================================================
    # REPORT 6: WEEKLY SUMMARY (주간 종합 요약)
    # ====================================================================

    def generate_weekly_summary(
        self,
        conn: sqlite3.Connection,
        rank_intel: Dict,
        competitor_threat: Dict,
        keyword_opp: Dict,
        community_intel: Dict,
        anomaly_report: Dict,
    ) -> Dict[str, Any]:
        """Generate consolidated weekly intelligence summary."""
        print("\n  [6/6] Weekly Summary Report...")

        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("  WEEKLY INTELLIGENCE SUMMARY (주간 종합 요약)")
        lines.append(f"  {self.business_name} - {self.report_date}")
        lines.append("=" * 70)

        # --- Executive Summary ---
        rank_stats = rank_intel.get('summary_stats', {})
        avg_rank = rank_stats.get('avg_rank', 0)
        top10 = rank_stats.get('top10', 0)
        improving = rank_stats.get('improving', 0)
        declining = rank_stats.get('declining', 0)
        total_kw = rank_stats.get('total_keywords', 0)

        competitors = competitor_threat.get('competitors', [])
        high_threats = [c for c in competitors if c.get('threat_level') == 'HIGH']

        easy_wins = keyword_opp.get('easy_wins', [])
        priority_kws = keyword_opp.get('priority', [])

        community = community_intel.get('platforms', {})
        total_mentions = sum(p.get('mentions', 0) for p in community.values())
        total_leads = sum(p.get('leads', 0) for p in community.values())

        anomalies = anomaly_report.get('anomalies', [])
        high_anomalies = [a for a in anomalies if a.get('severity') == 'HIGH']

        exec_parts = []
        exec_parts.append(
            f"{self.business_name} tracks {total_kw} keywords with an average Place rank of {avg_rank}. "
            f"{top10} keywords are in the top 10."
        )
        if improving > declining:
            exec_parts.append(f"Positive trend: {improving} keywords improving vs {declining} declining.")
        elif declining > improving:
            exec_parts.append(f"Concerning trend: {declining} keywords declining vs {improving} improving.")
        if high_threats:
            exec_parts.append(
                f"{len(high_threats)} high-threat competitors identified: "
                f"{', '.join(c['competitor'] for c in high_threats[:3])}."
            )
        if total_leads > 0:
            exec_parts.append(f"{total_leads} lead candidates found across community platforms.")
        if high_anomalies:
            exec_parts.append(f"{len(high_anomalies)} critical anomalies require immediate attention.")

        lines.append(f"\n  EXECUTIVE SUMMARY:")
        lines.append(f"  {' '.join(exec_parts)}")

        # --- Top 3 Opportunities ---
        lines.append(f"\n  TOP 3 OPPORTUNITIES:")
        opp_list = []
        if easy_wins:
            opp_list.append(f"EASY WIN: Keywords '{', '.join(easy_wins[:3])}' are close to top 10 with low competition")
        if priority_kws:
            opp_list.append(f"RISING TRENDS: Keywords '{', '.join(priority_kws[:3])}' show rising search trends - capture now")
        if total_leads >= 3:
            opp_list.append(f"LEADS: {total_leads} lead candidates in communities waiting for engagement")

        # Fill up to 3
        kw_reports = keyword_opp.get('keywords', [])
        for kr in kw_reports:
            if len(opp_list) >= 3:
                break
            if kr.get('opportunity_type') not in ('EASY WIN', 'PRIORITY CAPTURE'):
                if kr.get('opportunity_score', 0) >= 50:
                    opp_list.append(f"OPPORTUNITY: '{kr['keyword']}' (score {kr['opportunity_score']}) has untapped potential")
        for i, opp in enumerate(opp_list[:3], 1):
            lines.append(f"    {i}. {opp}")
        if not opp_list:
            lines.append("    (No significant opportunities identified)")

        # --- Top 3 Threats ---
        lines.append(f"\n  TOP 3 THREATS:")
        threat_list = []
        for c in sorted(competitors, key=lambda x: x.get('threat_score', 0), reverse=True)[:3]:
            if c.get('threat_score', 0) > 30:
                threat_list.append(
                    f"{c['competitor']} (threat {c['threat_score']}/100): "
                    f"{c.get('total_reviews', 0)} reviews, beats us on {len(c.get('keywords_above_us', []))} keywords"
                )
        for ha in high_anomalies[:3]:
            if len(threat_list) < 3:
                threat_list.append(ha['description'])
        for i, threat in enumerate(threat_list[:3], 1):
            lines.append(f"    {i}. {threat}")
        if not threat_list:
            lines.append("    (No significant threats detected)")

        # --- Top 3 Action Items ---
        lines.append(f"\n  TOP 3 ACTION ITEMS:")
        action_list = []
        if easy_wins:
            action_list.append(f"Create optimized blog content for easy-win keywords: {', '.join(easy_wins[:2])}")
        if high_threats:
            best_threat = high_threats[0]
            action_list.append(
                f"Counter {best_threat['competitor']}: "
                f"focus on keywords they dominate and accelerate review collection"
            )
        if declining > 2:
            action_list.append(f"Investigate and reverse declining ranks ({declining} keywords dropping)")
        if total_leads >= 3:
            action_list.append(f"Engage {total_leads} lead candidates in communities before competitors do")
        if high_anomalies:
            action_list.append(f"Address {len(high_anomalies)} critical anomalies immediately")

        for i, action in enumerate(action_list[:3], 1):
            lines.append(f"    {i}. {action}")
        if not action_list:
            lines.append("    (No urgent action items)")

        # --- Key Metrics ---
        lines.append(f"\n  KEY METRICS:")
        lines.append(f"    Keywords tracked      : {total_kw}")
        lines.append(f"    Average Place rank    : {avg_rank}")
        lines.append(f"    Keywords in top 10    : {top10}")
        lines.append(f"    Improving / Declining : {improving} / {declining}")
        lines.append(f"    Competitors monitored : {len(competitors)}")
        lines.append(f"    High-threat competitors: {len(high_threats)}")
        lines.append(f"    Community mentions    : {total_mentions:,}")
        lines.append(f"    Lead candidates       : {total_leads}")
        lines.append(f"    Anomalies detected    : {len(anomalies)}")
        lines.append(f"    Total alerts          : {len(self.alerts)}")

        # --- All Alerts ---
        if self.alerts:
            lines.append(f"\n  ALL ALERTS ({len(self.alerts)}):")
            for i, alert in enumerate(self.alerts, 1):
                lines.append(f"    {i}. {alert}")

        text = "\n".join(lines)

        result = {
            "executive_summary": ' '.join(exec_parts),
            "opportunities": opp_list[:3],
            "threats": threat_list[:3],
            "actions": action_list[:3],
            "metrics": {
                "keywords_tracked": total_kw,
                "avg_rank": avg_rank,
                "top10": top10,
                "improving": improving,
                "declining": declining,
                "competitors": len(competitors),
                "high_threats": len(high_threats),
                "total_mentions": total_mentions,
                "total_leads": total_leads,
                "anomalies": len(anomalies),
                "alerts": len(self.alerts),
            },
            "text": text,
            "summary": ' '.join(exec_parts),
        }

        print(text)
        return result

    # ====================================================================
    # Telegram Notification
    # ====================================================================

    def _send_telegram_report(
        self,
        rank_intel: Dict,
        competitor_threat: Dict,
        keyword_opp: Dict,
        community_intel: Dict,
        anomaly_report: Dict,
        weekly_summary: Dict,
    ):
        """Send detailed Telegram notification. Split into multiple messages if needed."""
        try:
            from alert_bot import TelegramBot, AlertPriority
            config = ConfigManager()
            secrets = config.load_secrets()
            bot_token = secrets.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = secrets.get("TELEGRAM_CHAT_ID", "")
            bot = TelegramBot(bot_token, chat_id)
        except Exception as e:
            print(f"  [Telegram] Could not initialize: {e}")
            return

        messages = []

        # --- Message 1: Executive Summary & Rank Overview ---
        msg1_lines = []
        msg1_lines.append(f"[{self.business_name} Intelligence Report]")
        msg1_lines.append(f"{self.report_datetime}")
        msg1_lines.append("")

        # Executive summary
        exec_summary = weekly_summary.get('executive_summary', '')
        if exec_summary:
            msg1_lines.append(exec_summary)
            msg1_lines.append("")

        # Rank overview - all keywords with arrows
        msg1_lines.append("[Rank Overview]")
        kw_reports = rank_intel.get('keywords', [])
        for kr in kw_reports:
            kw = kr.get('keyword', '')
            m_rank = kr.get('mobile_rank', 'N/A')
            d_rank = kr.get('desktop_rank', 'N/A')
            m_change = kr.get('mobile_change', 0)
            trend = kr.get('trend', '')

            # Arrow for rank change
            if isinstance(m_change, (int, float)):
                if m_change < 0:
                    arrow = f" ^{abs(m_change)}"
                elif m_change > 0:
                    arrow = f" v{m_change}"
                else:
                    arrow = " ="
            else:
                arrow = ""

            # Rank display
            if isinstance(m_rank, int) and m_rank > 0:
                rank_str = f"#{m_rank}{arrow}"
            elif isinstance(m_rank, str) and m_rank not in ('N/A', '0'):
                rank_str = m_rank
            else:
                rank_str = "N/R"

            # Desktop
            if isinstance(d_rank, int) and d_rank > 0:
                desk_str = f"D:#{d_rank}"
            else:
                desk_str = ""

            trend_str = f" [{trend}]" if trend and trend != 'UNKNOWN' else ""
            vol = kr.get('search_volume', 0)
            vol_str = f" vol:{vol:,}" if vol else ""

            line = f"  {kw}: {rank_str}"
            if desk_str:
                line += f" {desk_str}"
            line += f"{trend_str}{vol_str}"
            msg1_lines.append(line)

        # Summary stats
        stats = rank_intel.get('summary_stats', {})
        if stats:
            msg1_lines.append("")
            msg1_lines.append(f"Avg rank: {stats.get('avg_rank', 0)} | Top5: {stats.get('top5', 0)} | Top10: {stats.get('top10', 0)} | Top20: {stats.get('top20', 0)}")
            msg1_lines.append(f"Improving: {stats.get('improving', 0)} | Declining: {stats.get('declining', 0)}")

        messages.append("\n".join(msg1_lines))

        # --- Message 2: Competitor Threats ---
        msg2_lines = []
        msg2_lines.append(f"[Competitor Threats]")
        comp_reports = competitor_threat.get('competitors', [])
        if comp_reports:
            for c in comp_reports[:10]:
                level = c.get('threat_level', 'LOW')
                level_icon = "!!!" if level == "HIGH" else ("!!" if level == "MEDIUM" else ".")
                cn = c.get('competitor', '')
                ts = c.get('threat_score', 0)
                reviews = c.get('total_reviews', 0)
                rating = c.get('avg_rating', 0)
                rv = c.get('review_velocity', 0)
                kw_above = len(c.get('keywords_above_us', []))

                msg2_lines.append(f"  [{level_icon}] {cn}: {ts}/100")
                msg2_lines.append(f"      Reviews: {reviews} | Rating: {rating:.1f} | Vel: {rv:.1f}/wk | Beats us: {kw_above} kws")

                # Top actions
                actions = c.get('actions', [])
                if actions:
                    msg2_lines.append(f"      -> {actions[0]}")
        else:
            msg2_lines.append("  No competitor data available.")

        messages.append("\n".join(msg2_lines))

        # --- Message 3: Opportunities & Community ---
        msg3_lines = []
        msg3_lines.append(f"[Keyword Opportunities]")
        kw_opp_list = keyword_opp.get('keywords', [])
        ew = keyword_opp.get('easy_wins', [])
        lt = keyword_opp.get('long_term', [])
        pr = keyword_opp.get('priority', [])

        if ew:
            msg3_lines.append(f"  EASY WIN: {', '.join(ew[:5])}")
        if pr:
            msg3_lines.append(f"  RISING: {', '.join(pr[:5])}")
        if lt:
            msg3_lines.append(f"  LONG TERM: {', '.join(lt[:5])}")

        # Top 5 by score
        for kr in kw_opp_list[:5]:
            msg3_lines.append(f"  {kr['keyword']}: score {kr['opportunity_score']} [{kr['opportunity_type']}] vol:{kr.get('volume_total', 0):,}")

        # Community
        msg3_lines.append("")
        msg3_lines.append("[Community & Leads]")
        platforms = community_intel.get('platforms', {})
        total_m = sum(p.get('mentions', 0) for p in platforms.values())
        total_l = sum(p.get('leads', 0) for p in platforms.values())
        msg3_lines.append(f"  Total mentions: {total_m:,} | Lead candidates: {total_l}")
        for pname, pdata in platforms.items():
            msg3_lines.append(f"  {pname}: {pdata.get('mentions', 0)} mentions, {pdata.get('leads', 0)} leads")

        messages.append("\n".join(msg3_lines))

        # --- Message 4: Alerts & Actions ---
        msg4_lines = []
        msg4_lines.append("[Alerts & Anomalies]")
        anomalies = anomaly_report.get('anomalies', [])
        counts = anomaly_report.get('counts', {})
        msg4_lines.append(f"  Total: {len(anomalies)} (HIGH: {counts.get('high', 0)} | MED: {counts.get('medium', 0)} | WARN: {counts.get('warning', 0)})")
        for a in anomalies[:10]:
            sev = a.get('severity', 'INFO')
            msg4_lines.append(f"  [{sev}] {a['description']}")

        msg4_lines.append("")
        msg4_lines.append("[Action Items]")
        actions = weekly_summary.get('actions', [])
        for i, action in enumerate(actions, 1):
            msg4_lines.append(f"  {i}. {action}")

        if self.alerts:
            msg4_lines.append("")
            msg4_lines.append(f"[All Alerts ({len(self.alerts)})]")
            for i, alert in enumerate(self.alerts, 1):
                msg4_lines.append(f"  {i}. {alert}")

        messages.append("\n".join(msg4_lines))

        # --- Send all messages ---
        print(f"\n  Sending {len(messages)} Telegram messages...")
        for i, msg in enumerate(messages, 1):
            # Split if over 4000 chars
            chunks = self._split_message(msg, 4000)
            for j, chunk in enumerate(chunks):
                try:
                    # Send as plain text (no parse_mode) to avoid Telegram parsing errors
                    payload = {
                        "chat_id": chat_id,
                        "text": chunk,
                    }
                    if bot.base_url:
                        import requests
                        response = requests.post(bot.base_url, json=payload, timeout=15)
                        if response.status_code == 200:
                            print(f"    Message {i}.{j+1} sent OK")
                        else:
                            print(f"    Message {i}.{j+1} failed: {response.text[:100]}")
                    else:
                        # Mock mode
                        print(f"\n  [MOCK TELEGRAM MSG {i}.{j+1}]")
                        print(chunk[:500])
                        print("  ...")

                    time.sleep(0.5)  # Rate limit between messages
                except Exception as e:
                    print(f"    Message {i}.{j+1} error: {e}")

    def _split_message(self, text: str, max_len: int = 4000) -> List[str]:
        """Split a message into chunks at line boundaries."""
        if len(text) <= max_len:
            return [text]

        chunks = []
        current = ""
        for line in text.split('\n'):
            if len(current) + len(line) + 1 > max_len:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = current + '\n' + line if current else line
        if current:
            chunks.append(current)
        return chunks

    # ====================================================================
    # Save & Output
    # ====================================================================

    def _save_report(self, report_type: str, summary: str, details: Dict[str, Any]):
        """Save a report to the intelligence_reports table."""
        try:
            # Strip non-serializable items
            clean_details = json.loads(json.dumps(details, ensure_ascii=False, default=str))
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO intelligence_reports
                    (report_type, report_date, summary, details, alerts)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    report_type,
                    self.report_date,
                    summary[:5000] if summary else "",
                    json.dumps(clean_details, ensure_ascii=False, default=str),
                    json.dumps(self.alerts, ensure_ascii=False),
                ))
                conn.commit()
                logger.info(f"Saved report: {report_type}")
        except Exception as e:
            logger.error(f"Failed to save report [{report_type}]: {e}")
            logger.debug(traceback.format_exc())

    # ====================================================================
    # Main Entry Point
    # ====================================================================

    def run(self):
        """Run all intelligence analyses and generate comprehensive reports."""
        print(f"\n{'='*70}")
        print(f"  Intelligence Synthesizer v2.0")
        print(f"  Business: {self.business_name}")
        print(f"  Report Date: {self.report_date}")
        print(f"  Started: {self.report_datetime}")
        print(f"  Keywords: {len(self.place_keywords)} place + {len(self.blog_keywords)} blog")
        print(f"{'='*70}")

        all_results = {}

        try:
            with self.db.get_new_connection() as conn:
                # Report 1: Rank Intelligence
                rank_intel = self.generate_rank_intelligence(conn)
                all_results['rank_intelligence'] = rank_intel

                # Report 2: Competitor Threat
                competitor_threat = self.generate_competitor_threat(conn)
                all_results['competitor_threat'] = competitor_threat

                # Report 3: Keyword Opportunities
                keyword_opp = self.generate_keyword_opportunities(conn)
                all_results['keyword_opportunities'] = keyword_opp

                # Report 4: Community & Lead Intelligence
                community_intel = self.generate_community_intelligence(conn)
                all_results['community_intelligence'] = community_intel

                # Report 5: Anomaly & Alert Report
                anomaly_report = self.generate_anomaly_report(conn)
                all_results['anomaly_report'] = anomaly_report

                # Report 6: Weekly Summary
                weekly_summary = self.generate_weekly_summary(
                    conn, rank_intel, competitor_threat, keyword_opp,
                    community_intel, anomaly_report
                )
                all_results['weekly_summary'] = weekly_summary

        except Exception as e:
            logger.error(f"Analysis error: {e}")
            logger.debug(traceback.format_exc())
            print(f"\n  ERROR during analysis: {e}")
            traceback.print_exc()
            return

        # Save all reports to DB
        self._save_report("rank_intelligence", rank_intel.get('summary', ''), rank_intel)
        self._save_report("competitor_threat", competitor_threat.get('summary', ''), competitor_threat)
        self._save_report("keyword_opportunities", keyword_opp.get('summary', ''), keyword_opp)
        self._save_report("community_intelligence", community_intel.get('summary', ''), community_intel)
        self._save_report("anomaly_report", anomaly_report.get('summary', ''), anomaly_report)
        self._save_report("weekly_summary", weekly_summary.get('summary', ''), weekly_summary)

        # Send Telegram notification
        try:
            self._send_telegram_report(
                rank_intel, competitor_threat, keyword_opp,
                community_intel, anomaly_report, weekly_summary
            )
        except Exception as e:
            print(f"\n  Telegram notification failed: {e}")
            logger.error(f"Telegram notification error: {e}")

        # Final output
        print(f"\n{'='*70}")
        print(f"  INTELLIGENCE REPORT COMPLETE")
        print(f"  6 reports generated and saved to intelligence_reports table.")
        print(f"  Total alerts: {len(self.alerts)}")
        print(f"  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

        return all_results


if __name__ == "__main__":
    try:
        synthesizer = IntelligenceSynthesizer()
        synthesizer.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
