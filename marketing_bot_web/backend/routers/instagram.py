"""
Instagram Analysis API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Instagram 경쟁사 분석

[멀티채널 확장]
- 릴스 분석 API
- 해시태그 트렌드 API
- 해시태그 추적 API
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
parent_dir = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, parent_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response

router = APIRouter()


class InstagramAccount(BaseModel):
    username: str
    category: str = "한의원"


# 보안: days 파라미터 범위 제한 (1-365일)
def validate_days(days: int) -> int:
    """days 파라미터 검증 및 제한"""
    if days < 1:
        return 1
    if days > 365:
        return 365
    return days


@router.get("/stats")
async def get_instagram_stats(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (1-365일)")
) -> Dict[str, Any]:
    """
    Instagram 경쟁사 통계

    Args:
        days: 조회 기간 (일)

    Returns:
        통계 정보
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 보안: 파라미터 바인딩 사용 (SQL Injection 방지)
        days = validate_days(days)
        date_offset = f'-{days} days'

        # 총 포스트 수
        cursor.execute("""
            SELECT COUNT(*) FROM instagram_competitors
            WHERE created_at >= datetime('now', ?)
        """, (date_offset,))
        total_posts = cursor.fetchone()[0]

        # 평균 참여율
        cursor.execute("""
            SELECT AVG(engagement_rate) FROM instagram_competitors
            WHERE created_at >= datetime('now', ?)
        """, (date_offset,))
        avg_engagement = cursor.fetchone()[0]

        # 계정별 통계
        cursor.execute("""
            SELECT
                account_username,
                COUNT(*) as post_count,
                AVG(engagement_rate) as avg_engagement
            FROM instagram_competitors
            WHERE created_at >= datetime('now', ?)
            GROUP BY account_username
        """, (date_offset,))
        by_account = [
            {'account': row[0], 'posts': row[1], 'engagement': round(row[2], 2) if row[2] else 0}
            for row in cursor.fetchall()
        ]

        return {
            'total_posts': total_posts if total_posts else 0,
            'avg_engagement_rate': round(avg_engagement, 2) if avg_engagement else 0,
            'by_account': by_account
        }

    except Exception as e:
        # 테이블이 없으면 기본값 반환
        return {
            'total_posts': 0,
            'avg_engagement_rate': 0,
            'by_account': []
        }
    finally:
        if conn:
            conn.close()

@router.get("/hashtag-analysis")
async def get_hashtag_analysis(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (1-365일)")
) -> List[Dict[str, Any]]:
    """
    해시태그 분석

    Args:
        days: 조회 기간 (일)

    Returns:
        해시태그별 사용 빈도 및 참여율
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 보안: 파라미터 바인딩 사용 (SQL Injection 방지)
        days = validate_days(days)
        date_offset = f'-{days} days'

        # 해시태그 데이터 조회 (JSON 파싱)
        cursor.execute("""
            SELECT hashtags, engagement_rate
            FROM instagram_competitors
            WHERE created_at >= datetime('now', ?) AND hashtags IS NOT NULL
        """, (date_offset,))

        # 해시태그 집계
        hashtag_stats = {}
        for row in cursor.fetchall():
            hashtags_json = row[0]
            engagement = row[1] if row[1] else 0

            try:
                hashtags = json.loads(hashtags_json) if isinstance(hashtags_json, str) else hashtags_json
                if hashtags:
                    for tag in hashtags:
                        if tag not in hashtag_stats:
                            hashtag_stats[tag] = {'count': 0, 'total_engagement': 0}
                        hashtag_stats[tag]['count'] += 1
                        hashtag_stats[tag]['total_engagement'] += engagement
            except (json.JSONDecodeError, TypeError):
                pass  # 잘못된 JSON 형식은 무시

        # 평균 계산 및 정렬
        result = []
        for tag, stats in hashtag_stats.items():
            result.append({
                'hashtag': tag,
                'usage_count': stats['count'],
                'avg_engagement': round(stats['total_engagement'] / stats['count'], 2) if stats['count'] > 0 else 0
            })

        result.sort(key=lambda x: x['usage_count'], reverse=True)

        return result[:50]  # 상위 50개만 반환

    except Exception:
        # 테이블이 없으면 빈 배열 반환
        return []
    finally:
        if conn:
            conn.close()

@router.get("/content-analysis")
async def get_content_analysis(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (1-365일)")
) -> Dict[str, Any]:
    """
    콘텐츠 유형 분석

    Args:
        days: 조회 기간 (일)

    Returns:
        콘텐츠 유형별 통계 (이미지/비디오/캐러셀)
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 보안: 파라미터 바인딩 사용 (SQL Injection 방지)
        days = validate_days(days)
        date_offset = f'-{days} days'

        # 콘텐츠 유형별 통계
        cursor.execute("""
            SELECT
                content_type,
                COUNT(*) as count,
                AVG(engagement_rate) as avg_engagement
            FROM instagram_competitors
            WHERE created_at >= datetime('now', ?)
            GROUP BY content_type
        """, (date_offset,))

        by_type = {}
        for row in cursor.fetchall():
            content_type = row[0] if row[0] else 'unknown'
            by_type[content_type] = {
                'count': row[1],
                'avg_engagement': round(row[2], 2) if row[2] else 0
            }

        return {
            'by_type': by_type,
            'total': sum(stats['count'] for stats in by_type.values())
        }

    except Exception:
        # 테이블이 없으면 기본값 반환
        return {
            'by_type': {},
            'total': 0
        }
    finally:
        if conn:
            conn.close()

@router.post("/accounts")
async def add_instagram_account(account: InstagramAccount) -> Dict[str, str]:
    """
    Instagram 경쟁사 계정 추가

    Args:
        account: 계정 정보

    Returns:
        상태 메시지
    """
    try:
        # config/targets.json 파일 읽기/쓰기
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')

        # 기존 데이터 읽기
        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}

        # instagram_competitors 배열 초기화
        if 'instagram_competitors' not in data:
            data['instagram_competitors'] = []

        # 새 계정 추가
        new_account = {
            'username': account.username,
            'category': account.category
        }
        data['instagram_competitors'].append(new_account)

        # 파일 저장
        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            'status': 'success',
            'message': f'Instagram 계정 "@{account.username}" 추가 완료'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/posts")
async def get_competitor_posts(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (1-365일)"),
    account: Optional[str] = Query(default=None, description="특정 계정 필터링"),
    limit: int = Query(default=50, ge=1, le=200, description="최대 조회 수")
) -> Dict[str, Any]:
    """
    [Phase 7.1] 경쟁사 Instagram 포스트 목록

    Args:
        days: 조회 기간 (일)
        account: 특정 계정만 필터링
        limit: 최대 조회 수

    Returns:
        포스트 목록
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        days = validate_days(days)
        date_offset = f'-{days} days'

        # 기본 쿼리
        query = """
            SELECT
                id, account_username, post_url, caption, hashtags,
                like_count, comment_count, engagement_rate,
                content_type, posted_at, created_at
            FROM instagram_competitors
            WHERE created_at >= datetime('now', ?)
        """
        params = [date_offset]

        # 계정 필터링
        if account:
            query += " AND account_username = ?"
            params.append(account)

        query += " ORDER BY posted_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        posts = []
        for row in rows:
            post = dict(row)
            # hashtags JSON 파싱
            if post.get('hashtags'):
                try:
                    post['hashtags'] = json.loads(post['hashtags']) if isinstance(post['hashtags'], str) else post['hashtags']
                except json.JSONDecodeError:
                    post['hashtags'] = []
            posts.append(post)

        return {
            "posts": posts,
            "total": len(posts),
            "filters": {
                "days": days,
                "account": account
            }
        }

    except Exception:
        # 테이블이 없으면 빈 배열 반환
        return {"posts": [], "total": 0, "filters": {"days": days, "account": account}}
    finally:
        if conn:
            conn.close()


class AnalysisRequest(BaseModel):
    account: Optional[str] = None
    analysis_type: str = "comprehensive"  # comprehensive, hashtag, content, timing


@router.post("/analysis")
async def analyze_competitor_content(request: AnalysisRequest = None) -> Dict[str, Any]:
    """
    [Phase 7.1] AI 기반 경쟁사 콘텐츠 분석

    Gemini AI를 사용하여 경쟁사 Instagram 콘텐츠를 분석합니다.

    Args:
        request: 분석 요청 (account: 특정 계정, analysis_type: 분석 유형)

    Returns:
        AI 분석 결과
    """
    try:
        from services.ai_client import ai_generate

        # DB에서 최근 데이터 가져오기
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        account = request.account if request else None
        analysis_type = request.analysis_type if request else "comprehensive"

        try:
            # 기본 쿼리
            query = """
                SELECT account_username, caption, hashtags, like_count, comment_count,
                       engagement_rate, content_type, posted_at
                FROM instagram_competitors
                WHERE created_at >= datetime('now', '-30 days')
            """
            params = []

            if account:
                query += " AND account_username = ?"
                params.append(account)

            query += " ORDER BY engagement_rate DESC LIMIT 30"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                return {
                    "analysis": "분석할 데이터가 없습니다. 먼저 Instagram 스캔을 실행해주세요.",
                    "recommendations": [],
                    "data_count": 0
                }

            # 분석용 데이터 준비
            posts_summary = []
            for row in rows:
                hashtags = row['hashtags']
                if hashtags:
                    try:
                        hashtags = json.loads(hashtags) if isinstance(hashtags, str) else hashtags
                    except (json.JSONDecodeError, TypeError):
                        hashtags = []

                posts_summary.append({
                    "account": row['account_username'],
                    "caption_preview": (row['caption'] or '')[:100],
                    "hashtags": hashtags[:5] if hashtags else [],
                    "likes": row['like_count'],
                    "comments": row['comment_count'],
                    "engagement": row['engagement_rate'],
                    "type": row['content_type']
                })
        finally:
            conn.close()

        # AI 분석 프롬프트
        prompt = f"""당신은 한의원 마케팅 전문가입니다. 다음 경쟁 한의원들의 Instagram 포스트 데이터를 분석해주세요.

데이터 (최근 30일, 참여율 상위 {len(posts_summary)}개 포스트):
{json.dumps(posts_summary, ensure_ascii=False, indent=2)}

분석 유형: {analysis_type}

다음 형식으로 분석해주세요:

## 핵심 인사이트
- (3-5개의 핵심 발견점)

## 잘 되는 콘텐츠 유형
- (참여율이 높은 콘텐츠의 특징)

## 추천 해시태그
- (경쟁사들이 많이 사용하는 효과적인 해시태그 10개)

## 우리 한의원을 위한 제안
- (규림한의원이 벤치마킹할 수 있는 구체적인 액션 3-5개)

간결하고 실용적으로 작성해주세요."""

        analysis_result = ai_generate(prompt, temperature=0.7, max_tokens=1500)

        # 주요 추천 사항 추출 (간단한 파싱)
        recommendations = []
        lines = analysis_result.split('\n')
        in_recommendations = False
        for line in lines:
            if '제안' in line or '추천' in line:
                in_recommendations = True
                continue
            if in_recommendations and line.strip().startswith('-'):
                rec = line.strip().lstrip('-').strip()
                if rec:
                    recommendations.append(rec)
            if in_recommendations and line.strip().startswith('#'):
                break

        return {
            "analysis": analysis_result,
            "recommendations": recommendations[:5],
            "data_count": len(posts_summary),
            "analysis_type": analysis_type,
            "analyzed_at": datetime.now().isoformat() if 'datetime' in dir() else None
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Instagram Analysis] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts")
async def get_instagram_accounts() -> List[Dict[str, Any]]:
    """
    등록된 Instagram 계정 목록

    Returns:
        계정 목록
    """
    try:
        # config/targets.json 파일 읽기
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')

        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                accounts = data.get('instagram_competitors', [])

                # ID 추가 (인덱스 기반)
                for idx, acc in enumerate(accounts):
                    acc['id'] = idx + 1

                return accounts
        else:
            return []

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/token-status")
async def get_token_status() -> Dict[str, Any]:
    """
    [Phase 5.2] Instagram API 토큰 상태 확인

    Returns:
        - configured: API 설정 여부
        - token_expiry: 토큰 만료일
        - days_until_expiry: 만료까지 남은 일수
        - status: 상태 (valid, expiring_soon, expired, not_configured)
    """
    try:
        # Instagram API 클라이언트 임포트
        sys.path.insert(0, os.path.join(parent_dir, 'scrapers'))
        from instagram_api_client import InstagramGraphAPI

        api = InstagramGraphAPI()

        if not api.is_configured():
            return {
                'configured': False,
                'status': 'not_configured',
                'message': 'Instagram API 자격 증명이 설정되지 않았습니다',
                'required_keys': [
                    'INSTAGRAM_APP_ID',
                    'INSTAGRAM_APP_SECRET',
                    'INSTAGRAM_ACCESS_TOKEN',
                    'INSTAGRAM_BUSINESS_ACCOUNT_ID'
                ]
            }

        # 토큰 만료일 확인
        if api.token_expiry:
            days_until_expiry = (api.token_expiry - datetime.now()).days

            if days_until_expiry < 0:
                status = 'expired'
                message = '토큰이 만료되었습니다. 갱신이 필요합니다.'
            elif days_until_expiry < 7:
                status = 'expiring_soon'
                message = f'토큰이 {days_until_expiry}일 후 만료됩니다. 갱신을 권장합니다.'
            elif days_until_expiry < 14:
                status = 'warning'
                message = f'토큰이 {days_until_expiry}일 후 만료됩니다.'
            else:
                status = 'valid'
                message = f'토큰이 정상입니다. ({days_until_expiry}일 남음)'

            return {
                'configured': True,
                'status': status,
                'message': message,
                'token_expiry': api.token_expiry.isoformat() if api.token_expiry else None,
                'days_until_expiry': days_until_expiry
            }
        else:
            # 만료일 정보 없음
            return {
                'configured': True,
                'status': 'unknown',
                'message': '토큰 만료일 정보가 없습니다. secrets.json에 INSTAGRAM_TOKEN_EXPIRY를 설정하세요.',
                'token_expiry': None,
                'days_until_expiry': None
            }

    except ImportError:
        return {
            'configured': False,
            'status': 'error',
            'message': 'Instagram API 클라이언트를 로드할 수 없습니다'
        }
    except Exception as e:
        return {
            'configured': False,
            'status': 'error',
            'message': str(e)
        }


# ============================================
# [멀티채널 확장] 릴스 분석 API
# ============================================

@router.get("/reels")
@handle_exceptions
async def get_reels_analysis(
    account: Optional[str] = Query(default=None, description="특정 계정 필터"),
    days: int = Query(default=30, ge=1, le=365, description="조회 기간 (1-365일)"),
    limit: int = Query(default=50, ge=1, le=200, description="최대 조회 수")
) -> Dict[str, Any]:
    """
    [MC-1] 릴스 분석 데이터 조회

    Args:
        account: 특정 계정만 필터링
        days: 조회 기간
        limit: 최대 조회 수

    Returns:
        릴스 분석 목록
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        days = validate_days(days)
        date_offset = f'-{days} days'

        # 쿼리 구성
        query = """
            SELECT
                id, account_username, reel_id, reel_url, caption, hashtags,
                view_count, like_count, comment_count, engagement_rate,
                duration_seconds, audio_name, analyzed_at
            FROM instagram_reels_analysis
            WHERE analyzed_at >= datetime('now', ?)
        """
        params = [date_offset]

        if account:
            query += " AND account_username = ?"
            params.append(account)

        query += " ORDER BY engagement_rate DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 통계
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                AVG(view_count) as avg_views,
                AVG(like_count) as avg_likes,
                AVG(engagement_rate) as avg_engagement
            FROM instagram_reels_analysis
            WHERE analyzed_at >= datetime('now', ?)
        """, (date_offset,))
        stats_row = cursor.fetchone()

        reels = []
        for row in rows:
            reel = dict(row)
            if reel.get('hashtags'):
                try:
                    reel['hashtags'] = json.loads(reel['hashtags'])
                except Exception:
                    reel['hashtags'] = []
            reels.append(reel)

        stats = {
            'total': stats_row['total'] if stats_row else 0,
            'avg_views': int(stats_row['avg_views'] or 0) if stats_row else 0,
            'avg_likes': int(stats_row['avg_likes'] or 0) if stats_row else 0,
            'avg_engagement': round(stats_row['avg_engagement'] or 0, 2) if stats_row else 0
        }

        return success_response({
            'reels': reels,
            'stats': stats,
            'filters': {
                'account': account,
                'days': days
            }
        })

    except Exception as e:
        return success_response({
            'reels': [],
            'stats': {'total': 0, 'avg_views': 0, 'avg_likes': 0, 'avg_engagement': 0},
            'error': str(e)
        })
    finally:
        if conn:
            conn.close()


@router.get("/hashtag-trends")
@handle_exceptions
async def get_hashtag_trends(
    days: int = Query(default=7, ge=1, le=30, description="조회 기간 (1-30일)"),
    limit: int = Query(default=30, ge=1, le=100, description="최대 조회 수")
) -> Dict[str, Any]:
    """
    [MC-2] 해시태그 트렌드 조회

    Args:
        days: 조회 기간
        limit: 최대 조회 수

    Returns:
        해시태그 트렌드 목록
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 최근 트렌드 조회
        cursor.execute("""
            SELECT
                hashtag, category, post_count, avg_engagement_rate,
                top_posts_engagement, growth_rate, is_trending, trend_score,
                related_hashtags, tracked_date
            FROM instagram_hashtag_trends
            WHERE tracked_date >= date('now', ?)
            ORDER BY trend_score DESC
            LIMIT ?
        """, (f'-{days} days', limit))

        rows = cursor.fetchall()

        trends = []
        for row in rows:
            trend = dict(row)
            if trend.get('related_hashtags'):
                try:
                    trend['related_hashtags'] = json.loads(trend['related_hashtags'])
                except Exception:
                    trend['related_hashtags'] = []
            trend['is_trending'] = bool(trend.get('is_trending'))
            trends.append(trend)

        # 트렌딩 수 계산
        trending_count = sum(1 for t in trends if t['is_trending'])

        return success_response({
            'trends': trends,
            'total': len(trends),
            'trending_count': trending_count,
            'period_days': days
        })

    except Exception as e:
        return success_response({
            'trends': [],
            'total': 0,
            'trending_count': 0,
            'error': str(e)
        })
    finally:
        if conn:
            conn.close()


class TrackHashtagsRequest(BaseModel):
    """해시태그 추적 요청"""
    hashtags: List[str] = Field(..., min_length=1, max_length=50)


@router.post("/track-hashtags")
@handle_exceptions
async def track_hashtags(
    request: TrackHashtagsRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    [MC-3] 해시태그 추적 시작

    특정 해시태그들의 트렌드를 추적합니다.

    Args:
        request: 추적할 해시태그 목록

    Returns:
        추적 시작 결과
    """
    try:
        # 백그라운드에서 분석 실행
        def analyze_hashtags():
            try:
                sys.path.insert(0, str(Path(parent_dir).parent / 'scrapers'))
                from instagram_reels_analyzer import InstagramReelsAnalyzer

                analyzer = InstagramReelsAnalyzer()
                analyzer.analyze_hashtag_trends(request.hashtags)
            except Exception as e:
                print(f"[Instagram] 해시태그 분석 오류: {e}")

        background_tasks.add_task(analyze_hashtags)

        return success_response({
            'message': f'{len(request.hashtags)}개 해시태그 추적이 시작되었습니다',
            'hashtags': request.hashtags
        })

    except Exception as e:
        return error_response(str(e))


class AnalyzeAccountRequest(BaseModel):
    """계정 분석 요청"""
    username: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/analyze-reels")
@handle_exceptions
async def analyze_account_reels(
    request: AnalyzeAccountRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    [MC-4] 계정 릴스 분석 시작

    특정 Instagram 계정의 릴스를 분석합니다.

    Args:
        request: 분석할 계정 정보

    Returns:
        분석 시작 결과
    """
    try:
        def analyze_account():
            try:
                sys.path.insert(0, str(Path(parent_dir).parent / 'scrapers'))
                from instagram_reels_analyzer import InstagramReelsAnalyzer

                analyzer = InstagramReelsAnalyzer()
                analyzer.analyze_account_reels(request.username, request.limit)
            except Exception as e:
                print(f"[Instagram] 계정 분석 오류: {e}")

        background_tasks.add_task(analyze_account)

        return success_response({
            'message': f'@{request.username} 계정 분석이 시작되었습니다',
            'username': request.username,
            'limit': request.limit
        })

    except Exception as e:
        return error_response(str(e))


@router.get("/reels-report")
@handle_exceptions
async def get_reels_report(
    account: Optional[str] = Query(default=None, description="특정 계정 필터"),
    days: int = Query(default=30, ge=1, le=90, description="리포트 기간")
) -> Dict[str, Any]:
    """
    [MC-5] 릴스 성과 리포트

    릴스 분석 데이터를 기반으로 성과 리포트를 생성합니다.

    Args:
        account: 특정 계정 필터
        days: 리포트 기간

    Returns:
        성과 리포트
    """
    try:
        sys.path.insert(0, str(Path(parent_dir).parent / 'scrapers'))
        from instagram_reels_analyzer import InstagramReelsAnalyzer

        analyzer = InstagramReelsAnalyzer()
        result = analyzer.get_performance_report(username=account, days=days)

        return success_response(result)

    except ImportError:
        return error_response("릴스 분석기를 로드할 수 없습니다")
    except Exception as e:
        return error_response(str(e))
