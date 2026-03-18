"""
Data Export API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4.1] 데이터 내보내기 기능
- 리드, 키워드, 경쟁사 데이터 CSV 내보내기
- 날짜 범위 필터링 지원
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import sys
import os
from pathlib import Path
import sqlite3
import csv
import io

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent.parent)  # backend 디렉토리
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response

router = APIRouter()

# [성능 최적화] 스트리밍 배치 크기
STREAMING_BATCH_SIZE = 1000


def _generate_csv_streaming(conn, cursor, columns: List[str]):
    """
    [성능 최적화] 제너레이터 기반 CSV 스트리밍
    - 메모리 효율: 한 번에 BATCH_SIZE 행만 처리
    - 대량 데이터에서도 일정한 메모리 사용
    - 제너레이터 종료 시 DB 연결 자동 정리
    """
    try:
        # BOM + 헤더 출력
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        yield output.getvalue()

        # 배치 단위로 데이터 스트리밍
        while True:
            rows = cursor.fetchmany(STREAMING_BATCH_SIZE)
            if not rows:
                break

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
            writer.writerows([dict(row) for row in rows])
            yield output.getvalue()
    finally:
        # 스트리밍 완료 후 DB 연결 정리
        if conn:
            conn.close()


def _generate_csv(data: List[Dict], columns: List[str]) -> str:
    """딕셔너리 리스트를 CSV 문자열로 변환 (소량 데이터용)"""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


@router.get("/leads")
@handle_exceptions
async def export_leads(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 30
) -> StreamingResponse:
    """
    리드 데이터 CSV 내보내기 (스트리밍)

    Args:
        status: 상태 필터 (pending, contacted, replied, converted, rejected)
        platform: 플랫폼 필터 (youtube, naver, instagram, tiktok)
        days: 최근 N일 데이터 (기본 30일)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 테이블 존재 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="리드 데이터가 없습니다")

    # 필터 조건 구성
    where_clauses = []
    params = []

    # 날짜 필터
    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    where_clauses.append("(created_at >= ? OR scraped_at >= ?)")
    params.extend([date_threshold, date_threshold])

    if status:
        where_clauses.append("status = ?")
        params.append(status)

    if platform:
        where_clauses.append("(platform = ? OR source LIKE ?)")
        params.extend([platform, f"%{platform}%"])

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cursor.execute(f"""
        SELECT
            id,
            COALESCE(platform, source) as platform,
            title,
            COALESCE(summary, content) as content,
            url,
            COALESCE(author, target_name) as author,
            COALESCE(status, 'pending') as status,
            COALESCE(created_at, scraped_at) as created_at,
            notes,
            contact_info,
            expected_revenue,
            actual_revenue
        FROM mentions
        {where_clause}
        ORDER BY created_at DESC
    """, params)

    columns = [
        'id', 'platform', 'title', 'content', 'url', 'author',
        'status', 'created_at', 'notes', 'contact_info',
        'expected_revenue', 'actual_revenue'
    ]

    filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    # [성능 최적화] 스트리밍 방식으로 대용량 데이터 처리
    return StreamingResponse(
        _generate_csv_streaming(conn, cursor, columns),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
    )


@router.get("/keywords")
@handle_exceptions
async def export_keywords(
    grade: Optional[str] = None,
    category: Optional[str] = None,
    days: int = 90
) -> StreamingResponse:
    """
    키워드 데이터 CSV 내보내기 (스트리밍)

    Args:
        grade: 등급 필터 (S, A, B, C)
        category: 카테고리 필터
        days: 최근 N일 데이터 (기본 90일)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="키워드 데이터가 없습니다")

    where_clauses = []
    params = []

    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    where_clauses.append("created_at >= ?")
    params.append(date_threshold)

    if grade:
        where_clauses.append("grade = ?")
        params.append(grade.upper())

    if category:
        where_clauses.append("category = ?")
        params.append(category)

    where_clause = "WHERE " + " AND ".join(where_clauses)

    cursor.execute(f"""
        SELECT
            id,
            keyword,
            search_volume,
            document_count,
            grade,
            category,
            source,
            trend_status,
            kei,
            priority_v3,
            created_at
        FROM keyword_insights
        {where_clause}
        ORDER BY grade ASC, search_volume DESC
    """, params)

    columns = [
        'id', 'keyword', 'search_volume', 'document_count', 'grade',
        'category', 'source', 'trend_status', 'kei', 'priority_v3', 'created_at'
    ]

    filename = f"keywords_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        _generate_csv_streaming(conn, cursor, columns),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
    )


@router.get("/rank-history")
@handle_exceptions
async def export_rank_history(
    keyword: Optional[str] = None,
    days: int = 30
) -> StreamingResponse:
    """
    순위 히스토리 CSV 내보내기 (스트리밍)

    Args:
        keyword: 특정 키워드 필터
        days: 최근 N일 데이터 (기본 30일)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="순위 데이터가 없습니다")

    where_clauses = []
    params = []

    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    where_clauses.append("date >= ?")
    params.append(date_threshold)

    if keyword:
        where_clauses.append("keyword = ?")
        params.append(keyword)

    where_clause = "WHERE " + " AND ".join(where_clauses)

    cursor.execute(f"""
        SELECT
            id,
            keyword,
            rank,
            status,
            date,
            checked_at
        FROM rank_history
        {where_clause}
        ORDER BY date DESC, keyword ASC
    """, params)

    columns = ['id', 'keyword', 'rank', 'status', 'date', 'checked_at']

    filename = f"rank_history_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        _generate_csv_streaming(conn, cursor, columns),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
    )


@router.get("/viral-targets")
@handle_exceptions
async def export_viral_targets(
    status: Optional[str] = None,
    days: int = 30
) -> StreamingResponse:
    """
    바이럴 타겟 CSV 내보내기 (스트리밍)

    Args:
        status: 상태 필터 (pending, approved, posted, skipped)
        days: 최근 N일 데이터 (기본 30일)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="바이럴 타겟 데이터가 없습니다")

    where_clauses = []
    params = []

    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    where_clauses.append("discovered_at >= ?")
    params.append(date_threshold)

    if status:
        where_clauses.append("comment_status = ?")
        params.append(status)

    where_clause = "WHERE " + " AND ".join(where_clauses)

    cursor.execute(f"""
        SELECT
            id,
            platform,
            title,
            url,
            priority_score,
            comment_status,
            generated_comment,
            discovered_at
        FROM viral_targets
        {where_clause}
        ORDER BY priority_score DESC
    """, params)

    columns = [
        'id', 'platform', 'title', 'url', 'priority_score',
        'comment_status', 'generated_comment', 'discovered_at'
    ]

    filename = f"viral_targets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        _generate_csv_streaming(conn, cursor, columns),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
    )


@router.get("/competitors")
@handle_exceptions
async def export_competitors(
    days: int = 365
) -> StreamingResponse:
    """
    경쟁사 데이터 CSV 내보내기 (스트리밍)

    Args:
        days: 최근 N일 데이터 (기본 365일)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 경쟁사 리뷰 테이블 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_reviews'")
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="경쟁사 데이터가 없습니다")

    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT
            id,
            competitor_name,
            source,
            content,
            sentiment,
            keywords,
            review_date,
            scraped_at
        FROM competitor_reviews
        WHERE scraped_at >= ? OR review_date >= ?
        ORDER BY competitor_name ASC, review_date DESC
    """, (date_threshold, date_threshold))

    columns = [
        'id', 'competitor_name', 'source', 'content', 'sentiment',
        'keywords', 'review_date', 'scraped_at'
    ]

    filename = f"competitors_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        _generate_csv_streaming(conn, cursor, columns),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
    )


@router.get("/competitor-weaknesses")
@handle_exceptions
async def export_competitor_weaknesses() -> StreamingResponse:
    """
    경쟁사 약점 분석 결과 CSV 내보내기 (스트리밍)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="경쟁사 약점 데이터가 없습니다")

    cursor.execute("""
        SELECT
            id,
            competitor_name,
            weakness_type,
            description,
            severity,
            source_url,
            created_at
        FROM competitor_weaknesses
        ORDER BY severity DESC, competitor_name ASC
    """)

    columns = [
        'id', 'competitor_name', 'weakness_type', 'description',
        'severity', 'source_url', 'created_at'
    ]

    filename = f"competitor_weaknesses_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        _generate_csv_streaming(conn, cursor, columns),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
    )


@router.get("/summary")
@handle_exceptions
async def get_export_summary() -> Dict[str, Any]:
    """
    내보내기 가능한 데이터 요약 조회
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        summary = {
            "leads": {"count": 0, "last_updated": None},
            "keywords": {"count": 0, "last_updated": None},
            "rank_history": {"count": 0, "last_updated": None},
            "viral_targets": {"count": 0, "last_updated": None},
            "competitors": {"count": 0, "last_updated": None},
            "competitor_weaknesses": {"count": 0, "last_updated": None}
        }

        # 리드 수
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*), MAX(COALESCE(created_at, scraped_at)) FROM mentions")
            row = cursor.fetchone()
            summary["leads"]["count"] = row[0] or 0
            summary["leads"]["last_updated"] = row[1]

        # 키워드 수
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*), MAX(created_at) FROM keyword_insights")
            row = cursor.fetchone()
            summary["keywords"]["count"] = row[0] or 0
            summary["keywords"]["last_updated"] = row[1]

        # 순위 히스토리 수
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*), MAX(date) FROM rank_history")
            row = cursor.fetchone()
            summary["rank_history"]["count"] = row[0] or 0
            summary["rank_history"]["last_updated"] = row[1]

        # 바이럴 타겟 수
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='viral_targets'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*), MAX(discovered_at) FROM viral_targets")
            row = cursor.fetchone()
            summary["viral_targets"]["count"] = row[0] or 0
            summary["viral_targets"]["last_updated"] = row[1]

        # 경쟁사 리뷰 수
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_reviews'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*), MAX(scraped_at) FROM competitor_reviews")
            row = cursor.fetchone()
            summary["competitors"]["count"] = row[0] or 0
            summary["competitors"]["last_updated"] = row[1]

        # 경쟁사 약점 수
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*), MAX(created_at) FROM competitor_weaknesses")
            row = cursor.fetchone()
            summary["competitor_weaknesses"]["count"] = row[0] or 0
            summary["competitor_weaknesses"]["last_updated"] = row[1]

        return success_response(summary)
    finally:
        if conn:
            conn.close()
