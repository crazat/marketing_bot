"""
데이터 보존 정책 자동화
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V3-4] 55+ 테이블의 데이터 보존/아카이브/정리 자동화

정책:
- rank_history: 365일 보존 (이전 데이터 월별 집계로 압축)
- community_mentions: 180일 보존
- competitor_reviews: 무기한 보존 (핵심 데이터)
- scraper_run_metrics: 90일 보존
- weather_log: 90일 보존
- viral_velocity: 60일 보존
- 월 1회 VACUUM 실행
"""

import sqlite3
import os
import shutil
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# 테이블별 보존 기간 (일)
RETENTION_POLICIES = {
    "scraper_run_metrics": 90,
    "weather_log": 90,
    "viral_velocity": 60,
    "community_mentions": 180,
    "healthcare_news": 180,
    "keyword_trend_daily": 365,
    "blog_rank_history": 365,
    "web_visibility": 365,
    "search_demographics": 365,
    "ad_competition_tracking": 180,
    "naver_ad_related_keywords": 180,
    "content_compliance_checks": 180,
    "review_responses": 365,
}

# 날짜 컬럼 매핑 (테이블별 날짜 컬럼명)
DATE_COLUMNS = {
    "scraper_run_metrics": "run_at",
    "weather_log": "fetched_at",
    "viral_velocity": "detected_at",
    "community_mentions": "created_at",
    "healthcare_news": "created_at",
    "keyword_trend_daily": "date",
    "blog_rank_history": "scanned_at",
    "web_visibility": "scanned_at",
    "search_demographics": "scanned_at",
    "ad_competition_tracking": "tracked_at",
    "naver_ad_related_keywords": "collected_at",
    "content_compliance_checks": "checked_at",
    "review_responses": "created_at",
}


def run_retention_cleanup(db_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    보존 정책에 따라 오래된 데이터 정리

    Args:
        db_path: DB 경로
        dry_run: True이면 삭제하지 않고 대상 건수만 반환

    Returns:
        {cleaned: {table: count}, total_deleted, vacuum_done}
    """
    conn = None
    results = {"cleaned": {}, "total_deleted": 0, "errors": []}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for table, retention_days in RETENTION_POLICIES.items():
            date_col = DATE_COLUMNS.get(table)
            if not date_col:
                continue

            # 테이블 존재 확인
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not cursor.fetchone():
                continue

            try:
                if dry_run:
                    cursor.execute(f"""
                        SELECT COUNT(*) as cnt FROM {table}
                        WHERE {date_col} < datetime('now', ? || ' days')
                    """, (f"-{retention_days}",))
                    count = cursor.fetchone()[0]
                else:
                    cursor.execute(f"""
                        DELETE FROM {table}
                        WHERE {date_col} < datetime('now', ? || ' days')
                    """, (f"-{retention_days}",))
                    count = cursor.rowcount

                if count > 0:
                    results["cleaned"][table] = count
                    results["total_deleted"] += count
                    logger.info(f"  {'[DRY RUN] ' if dry_run else ''}🧹 {table}: {count}건 {'삭제 예정' if dry_run else '삭제됨'} ({retention_days}일 보존)")

            except Exception as e:
                results["errors"].append({"table": table, "error": str(e)})
                logger.error(f"  {table} 정리 실패: {e}")

        if not dry_run:
            conn.commit()

    except Exception as e:
        logger.error(f"보존 정책 실행 실패: {e}")
        results["errors"].append({"error": str(e)})
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    return results


def run_vacuum(db_path: str) -> Dict[str, Any]:
    """
    VACUUM 실행 (DB 파일 크기 최적화)

    VACUUM은 트랜잭션 외부에서만 실행 가능하므로 별도 연결 사용.
    """
    try:
        # VACUUM 전 크기
        before_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()

        # VACUUM 후 크기
        after_size = os.path.getsize(db_path)
        saved = before_size - after_size

        result = {
            "before_mb": round(before_size / 1048576, 2),
            "after_mb": round(after_size / 1048576, 2),
            "saved_mb": round(saved / 1048576, 2),
            "saved_percent": round((saved / max(before_size, 1)) * 100, 1),
        }

        logger.info(f"🗜️ VACUUM 완료: {result['before_mb']}MB → {result['after_mb']}MB ({result['saved_mb']}MB 절약)")
        return result

    except Exception as e:
        logger.error(f"VACUUM 실패: {e}")
        return {"error": str(e)}


def get_table_sizes(db_path: str) -> List[Dict[str, Any]]:
    """테이블별 행 수 및 예상 크기"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master WHERE type='table' ORDER BY name
    """)
    tables = [r[0] for r in cursor.fetchall()]

    sizes = []
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            retention = RETENTION_POLICIES.get(table, "무기한")
            sizes.append({
                "table": table,
                "rows": count,
                "retention_days": retention,
            })
        except Exception:
            pass

    conn.close()

    # 행 수 기준 정렬
    return sorted(sizes, key=lambda x: x["rows"], reverse=True)


def run_full_maintenance(db_path: str) -> Dict[str, Any]:
    """
    전체 유지보수 실행 (보존 정책 + VACUUM)

    schedule.json에서 월 1회 실행 권장
    """
    logger.info("🔧 데이터 유지보수 시작...")

    # 1. 보존 정책 적용
    cleanup = run_retention_cleanup(db_path, dry_run=False)

    # 2. VACUUM
    vacuum = run_vacuum(db_path)

    # 3. 테이블 크기 현황
    table_sizes = get_table_sizes(db_path)
    top_tables = table_sizes[:10]

    result = {
        "cleanup": cleanup,
        "vacuum": vacuum,
        "top_tables": top_tables,
        "total_tables": len(table_sizes),
        "total_rows": sum(t["rows"] for t in table_sizes),
        "executed_at": datetime.now().isoformat(),
    }

    logger.info(f"🔧 유지보수 완료: {cleanup['total_deleted']}건 정리, {vacuum.get('saved_mb', 0)}MB 절약")
    return result
