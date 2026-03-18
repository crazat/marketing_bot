"""
TikTok Analysis API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[멀티채널 확장] 틱톡 분석 API
- 틱톡 비디오 수집 및 분석
- 해시태그/음악 트렌드 추적
- 경쟁사 틱톡 모니터링
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path
import sqlite3
import json
from datetime import datetime

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent.parent)  # backend 디렉토리
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response

router = APIRouter()


# 보안: days 파라미터 범위 제한
def validate_days(days: int) -> int:
    """days 파라미터 검증 및 제한"""
    if days < 1:
        return 1
    if days > 365:
        return 365
    return days


def _ensure_tiktok_tables(cursor):
    """TikTok 테이블 생성"""
    # tiktok_videos 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiktok_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            author_username TEXT,
            author_nickname TEXT,
            video_url TEXT,
            description TEXT,
            hashtags TEXT DEFAULT '[]',
            view_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            save_count INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            duration_seconds INTEGER,
            music_title TEXT,
            music_author TEXT,
            is_original_music INTEGER DEFAULT 0,
            cover_url TEXT,
            category TEXT,
            is_competitor INTEGER DEFAULT 0,
            posted_at TIMESTAMP,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # tiktok_trends 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiktok_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trend_type TEXT NOT NULL,
            trend_key TEXT NOT NULL,
            trend_name TEXT,
            category TEXT DEFAULT 'general',
            video_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            avg_engagement_rate REAL DEFAULT 0,
            growth_rate REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            is_rising INTEGER DEFAULT 0,
            related_trends TEXT DEFAULT '[]',
            sample_video_ids TEXT DEFAULT '[]',
            tracked_date TEXT DEFAULT (DATE('now')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trend_type, trend_key, tracked_date)
        )
    """)


@router.get("/status")
@handle_exceptions
async def get_tiktok_status() -> Dict[str, Any]:
    """
    틱톡 API 상태 확인

    Returns:
        연동 상태 및 통계
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_tiktok_tables(cursor)
    conn.commit()

    # 비디오 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total_videos,
            COUNT(DISTINCT author_username) as unique_accounts,
            SUM(CASE WHEN is_competitor = 1 THEN 1 ELSE 0 END) as competitor_videos
        FROM tiktok_videos
    """)
    video_stats = dict(cursor.fetchone())

    # 트렌드 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total_trends,
            SUM(CASE WHEN is_rising = 1 THEN 1 ELSE 0 END) as rising_trends
        FROM tiktok_trends
        WHERE tracked_date = date('now')
    """)
    trend_stats = dict(cursor.fetchone())

    # 최근 스캔 시간
    cursor.execute("""
        SELECT MAX(scraped_at) as last_scan
        FROM tiktok_videos
    """)
    last_scan = cursor.fetchone()['last_scan']

    conn.close()

    # API 설정 확인
    config_path = Path(parent_dir) / 'config' / 'config.json'
    api_configured = False
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                api_configured = bool(config.get('TIKTOK_API_KEY'))
        except Exception:
            pass

    return success_response({
        'status': 'active' if video_stats['total_videos'] > 0 else 'inactive',
        'api_configured': api_configured,
        'videos': video_stats,
        'trends': trend_stats,
        'last_scan': last_scan
    })


@router.get("/videos")
@handle_exceptions
async def get_tiktok_videos(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간"),
    account: Optional[str] = Query(default=None, description="특정 계정 필터"),
    competitor_only: bool = Query(default=False, description="경쟁사만 필터"),
    limit: int = Query(default=50, ge=1, le=200, description="최대 조회 수"),
    sort_by: str = Query(default="engagement_rate", description="정렬 기준")
) -> Dict[str, Any]:
    """
    틱톡 비디오 목록 조회

    Args:
        days: 조회 기간
        account: 특정 계정 필터
        competitor_only: 경쟁사만 필터
        limit: 최대 조회 수
        sort_by: 정렬 기준 (engagement_rate, view_count, like_count, posted_at)

    Returns:
        비디오 목록
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_tiktok_tables(cursor)
    conn.commit()

    days = validate_days(days)
    date_offset = f'-{days} days'

    # 정렬 기준 검증
    valid_sort = ['engagement_rate', 'view_count', 'like_count', 'posted_at', 'scraped_at']
    if sort_by not in valid_sort:
        sort_by = 'engagement_rate'

    # 쿼리 구성
    query = f"""
        SELECT
            id, video_id, author_username, author_nickname, video_url,
            description, hashtags, view_count, like_count, comment_count,
            share_count, engagement_rate, duration_seconds, music_title,
            is_competitor, posted_at, scraped_at
        FROM tiktok_videos
        WHERE scraped_at >= datetime('now', ?)
    """
    params = [date_offset]

    if account:
        query += " AND author_username = ?"
        params.append(account)

    if competitor_only:
        query += " AND is_competitor = 1"

    query += f" ORDER BY {sort_by} DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            AVG(view_count) as avg_views,
            AVG(engagement_rate) as avg_engagement,
            SUM(view_count) as total_views
        FROM tiktok_videos
        WHERE scraped_at >= datetime('now', ?)
    """, (date_offset,))
    stats_row = cursor.fetchone()

    conn.close()

    videos = []
    for row in rows:
        video = dict(row)
        if video.get('hashtags'):
            try:
                video['hashtags'] = json.loads(video['hashtags'])
            except Exception:
                video['hashtags'] = []
        video['is_competitor'] = bool(video.get('is_competitor'))
        videos.append(video)

    stats = {
        'total': stats_row['total'] if stats_row else 0,
        'avg_views': int(stats_row['avg_views'] or 0) if stats_row else 0,
        'avg_engagement': round(stats_row['avg_engagement'] or 0, 2) if stats_row else 0,
        'total_views': int(stats_row['total_views'] or 0) if stats_row else 0
    }

    return success_response({
        'videos': videos,
        'stats': stats,
        'filters': {
            'days': days,
            'account': account,
            'competitor_only': competitor_only,
            'sort_by': sort_by
        }
    })


@router.get("/trends")
@handle_exceptions
async def get_tiktok_trends(
    trend_type: Optional[str] = Query(default=None, description="트렌드 유형 (hashtag, music)"),
    days: int = Query(default=7, ge=1, le=30, description="조회 기간"),
    rising_only: bool = Query(default=False, description="상승 트렌드만"),
    limit: int = Query(default=30, ge=1, le=100, description="최대 조회 수")
) -> Dict[str, Any]:
    """
    틱톡 트렌드 조회

    Args:
        trend_type: 트렌드 유형 (hashtag, music)
        days: 조회 기간
        rising_only: 상승 트렌드만 필터
        limit: 최대 조회 수

    Returns:
        트렌드 목록
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_tiktok_tables(cursor)
    conn.commit()

    # 쿼리 구성
    query = """
        SELECT
            id, trend_type, trend_key, trend_name, category,
            video_count, view_count, avg_engagement_rate,
            growth_rate, trend_score, is_rising, related_trends,
            tracked_date
        FROM tiktok_trends
        WHERE tracked_date >= date('now', ?)
    """
    params = [f'-{days} days']

    if trend_type:
        query += " AND trend_type = ?"
        params.append(trend_type)

    if rising_only:
        query += " AND is_rising = 1"

    query += " ORDER BY trend_score DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # 트렌드 유형별 통계
    cursor.execute("""
        SELECT
            trend_type,
            COUNT(*) as count,
            SUM(CASE WHEN is_rising = 1 THEN 1 ELSE 0 END) as rising
        FROM tiktok_trends
        WHERE tracked_date = date('now')
        GROUP BY trend_type
    """)
    type_stats = {row['trend_type']: {'count': row['count'], 'rising': row['rising']}
                  for row in cursor.fetchall()}

    conn.close()

    trends = []
    for row in rows:
        trend = dict(row)
        if trend.get('related_trends'):
            try:
                trend['related_trends'] = json.loads(trend['related_trends'])
            except Exception:
                trend['related_trends'] = []
        trend['is_rising'] = bool(trend.get('is_rising'))
        trends.append(trend)

    return success_response({
        'trends': trends,
        'total': len(trends),
        'by_type': type_stats,
        'filters': {
            'trend_type': trend_type,
            'days': days,
            'rising_only': rising_only
        }
    })


class ScanRequest(BaseModel):
    """스캔 요청 모델"""
    accounts: List[str] = Field(default=[], max_length=20, description="스캔할 계정 목록")
    hashtags: List[str] = Field(default=[], max_length=50, description="스캔할 해시태그")
    scan_trending: bool = Field(default=True, description="트렌딩 스캔 여부")


@router.post("/scan")
@handle_exceptions
async def start_tiktok_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    틱톡 스캔 시작

    Args:
        request: 스캔 설정

    Returns:
        스캔 시작 결과
    """
    def run_scan():
        """백그라운드 스캔 작업"""
        try:
            # 스크래퍼 모듈 임포트 시도
            scraper_path = Path(parent_dir) / 'scrapers'
            sys.path.insert(0, str(scraper_path))

            # scraper_tiktok_monitor.py가 있으면 실행
            tiktok_scraper_path = scraper_path / 'scraper_tiktok_monitor.py'
            if tiktok_scraper_path.exists():
                import subprocess
                cmd = ['python', str(tiktok_scraper_path)]
                subprocess.Popen(cmd, cwd=parent_dir)
            else:
                print("[TikTok] 스크래퍼가 없습니다: scraper_tiktok_monitor.py")

        except Exception as e:
            print(f"[TikTok] 스캔 오류: {e}")

    background_tasks.add_task(run_scan)

    return success_response({
        'message': '틱톡 스캔이 시작되었습니다',
        'scan_config': {
            'accounts': len(request.accounts),
            'hashtags': len(request.hashtags),
            'scan_trending': request.scan_trending
        }
    })


class AddAccountRequest(BaseModel):
    """계정 추가 요청"""
    username: str = Field(..., min_length=1, max_length=100)
    is_competitor: bool = Field(default=True)
    category: Optional[str] = None


@router.post("/accounts")
@handle_exceptions
async def add_tiktok_account(request: AddAccountRequest) -> Dict[str, Any]:
    """
    틱톡 모니터링 계정 추가

    Args:
        request: 계정 정보

    Returns:
        추가 결과
    """
    try:
        # config/targets.json에 저장
        targets_path = Path(parent_dir) / 'config' / 'targets.json'

        if targets_path.exists():
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}

        if 'tiktok_accounts' not in data:
            data['tiktok_accounts'] = []

        # 중복 확인
        existing = [acc['username'] for acc in data['tiktok_accounts']]
        if request.username in existing:
            return error_response(f'계정 @{request.username}은 이미 등록되어 있습니다')

        # 추가
        new_account = {
            'username': request.username,
            'is_competitor': request.is_competitor,
            'category': request.category,
            'added_at': datetime.now().isoformat()
        }
        data['tiktok_accounts'].append(new_account)

        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return success_response({
            'message': f'계정 @{request.username}이 추가되었습니다',
            'account': new_account
        })

    except Exception as e:
        return error_response(str(e))


@router.get("/accounts")
@handle_exceptions
async def get_tiktok_accounts() -> Dict[str, Any]:
    """
    등록된 틱톡 모니터링 계정 목록

    Returns:
        계정 목록
    """
    try:
        targets_path = Path(parent_dir) / 'config' / 'targets.json'

        if targets_path.exists():
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                accounts = data.get('tiktok_accounts', [])
        else:
            accounts = []

        return success_response({
            'accounts': accounts,
            'total': len(accounts)
        })

    except Exception as e:
        return error_response(str(e))


@router.delete("/accounts/{username}")
@handle_exceptions
async def remove_tiktok_account(username: str) -> Dict[str, Any]:
    """
    틱톡 모니터링 계정 삭제

    Args:
        username: 삭제할 계정명

    Returns:
        삭제 결과
    """
    try:
        targets_path = Path(parent_dir) / 'config' / 'targets.json'

        if not targets_path.exists():
            return error_response('설정 파일이 없습니다')

        with open(targets_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'tiktok_accounts' not in data:
            return error_response(f'계정 @{username}을 찾을 수 없습니다')

        original_count = len(data['tiktok_accounts'])
        data['tiktok_accounts'] = [
            acc for acc in data['tiktok_accounts']
            if acc['username'] != username
        ]

        if len(data['tiktok_accounts']) == original_count:
            return error_response(f'계정 @{username}을 찾을 수 없습니다')

        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return success_response({
            'message': f'계정 @{username}이 삭제되었습니다'
        })

    except Exception as e:
        return error_response(str(e))


@router.get("/analytics")
@handle_exceptions
async def get_tiktok_analytics(
    days: int = Query(default=30, ge=1, le=90, description="분석 기간")
) -> Dict[str, Any]:
    """
    틱톡 분석 데이터

    채널 성과, 트렌드 분석, 경쟁사 비교 등

    Args:
        days: 분석 기간

    Returns:
        분석 데이터
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_tiktok_tables(cursor)
    conn.commit()

    days = validate_days(days)
    date_offset = f'-{days} days'

    # 전체 성과 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total_videos,
            SUM(view_count) as total_views,
            SUM(like_count) as total_likes,
            SUM(comment_count) as total_comments,
            AVG(engagement_rate) as avg_engagement,
            MAX(engagement_rate) as top_engagement
        FROM tiktok_videos
        WHERE scraped_at >= datetime('now', ?)
    """, (date_offset,))
    overall_stats = dict(cursor.fetchone())

    # 일별 추이
    cursor.execute("""
        SELECT
            date(scraped_at) as date,
            COUNT(*) as videos,
            SUM(view_count) as views,
            AVG(engagement_rate) as avg_engagement
        FROM tiktok_videos
        WHERE scraped_at >= datetime('now', ?)
        GROUP BY date(scraped_at)
        ORDER BY date ASC
    """, (date_offset,))
    daily_trend = [dict(row) for row in cursor.fetchall()]

    # 계정별 성과
    cursor.execute("""
        SELECT
            author_username,
            COUNT(*) as video_count,
            SUM(view_count) as total_views,
            AVG(engagement_rate) as avg_engagement
        FROM tiktok_videos
        WHERE scraped_at >= datetime('now', ?)
        GROUP BY author_username
        ORDER BY total_views DESC
        LIMIT 10
    """, (date_offset,))
    top_accounts = [dict(row) for row in cursor.fetchall()]

    # Top 해시태그
    cursor.execute("""
        SELECT trend_key as hashtag, video_count, avg_engagement_rate, trend_score
        FROM tiktok_trends
        WHERE trend_type = 'hashtag'
            AND tracked_date >= date('now', ?)
        ORDER BY trend_score DESC
        LIMIT 10
    """, (date_offset,))
    top_hashtags = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return success_response({
        'period_days': days,
        'overall': overall_stats,
        'daily_trend': daily_trend,
        'top_accounts': top_accounts,
        'top_hashtags': top_hashtags
    })
