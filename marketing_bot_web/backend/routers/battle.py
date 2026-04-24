"""
Battle Intelligence API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

키워드 순위 추적 및 분석
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import os
import sqlite3
import json

# [코드 품질 개선] 공통 경로 설정 사용
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import setup_paths
parent_dir = str(setup_paths.PROJECT_ROOT)

from db.database import DatabaseManager
from core_services.sql_builder import validate_table_name, get_table_columns
from backend_utils.logger import get_router_logger
from backend_utils.error_handlers import handle_exceptions
from backend_utils.cache import TTLCache, get_api_cache

router = APIRouter()
logger = get_router_logger('battle')

# [성능 최적화] API 응답 캐시 (30초 TTL)
_ranking_cache = TTLCache(default_ttl=30, max_size=50)

# 키워드 목표 순위 설정 파일
KEYWORD_TARGETS_FILE = os.path.join(parent_dir, 'config', 'keyword_targets.json')


def load_keyword_targets() -> Dict[str, int]:
    """키워드별 목표 순위 로드"""
    try:
        if os.path.exists(KEYWORD_TARGETS_FILE):
            with open(KEYWORD_TARGETS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('targets', {})
    except Exception as e:
        logger.warning(f"목표 순위 로드 실패: {e}")
    return {}


def save_keyword_targets(targets: Dict[str, int]) -> bool:
    """키워드별 목표 순위 저장"""
    try:
        data = {
            "_description": "키워드별 목표 순위 설정",
            "targets": targets
        }
        with open(KEYWORD_TARGETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"목표 순위 저장 실패: {e}")
        return False


def get_keyword_search_volume(cursor, keyword: str) -> int:
    """
    키워드의 검색량 조회 (캐시 우선, API 폴백)
    - keyword_volume_cache 테이블에서 먼저 조회
    - 없으면 NaverAdManager API 호출
    - 공백 제거 버전도 함께 검색
    """
    keyword_no_space = keyword.replace(" ", "")

    # 1. 캐시에서 조회
    cursor.execute("""
        SELECT volume FROM keyword_volume_cache
        WHERE keyword = ? OR keyword = ?
    """, (keyword, keyword_no_space))
    cache_row = cursor.fetchone()

    if cache_row and cache_row[0] > 0:
        logger.debug(f"캐시에서 검색량 발견: {keyword} = {cache_row[0]}")
        return cache_row[0]

    # 2. API 호출
    try:
        from scrapers.naver_ad_manager import NaverAdManager
        ad_manager = NaverAdManager()
        volumes = ad_manager.get_keyword_volumes([keyword])
        if volumes:
            volume = volumes.get(keyword, 0) or volumes.get(keyword_no_space, 0)
            if volume > 0:
                logger.debug(f"API에서 검색량 조회: {keyword} = {volume}")
                return volume
    except Exception as e:
        logger.warning(f"검색량 조회 실패 (계속 진행): {e}")

    return 0


class RankingKeyword(BaseModel):
    keyword: str
    target_rank: int = 10
    category: Optional[str] = "기타"

    @field_validator('keyword')
    @classmethod
    def keyword_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('키워드는 필수입니다')
        if len(v.strip()) < 2:
            raise ValueError('키워드는 최소 2자 이상이어야 합니다')
        return v.strip()

    @field_validator('target_rank')
    @classmethod
    def target_rank_must_be_positive(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError('목표 순위는 1~100 사이여야 합니다')
        return v

def calculate_decline_streak(cursor, keyword: str) -> Dict[str, Any]:
    """
    키워드의 연속 하락 일수 계산
    - 최근 7일간의 순위 기록을 분석
    - 연속으로 순위가 하락한 일수를 반환
    """
    cursor.execute("""
        SELECT rank, COALESCE(date, checked_at) as scan_date
        FROM rank_history
        WHERE keyword = ? AND status = 'found' AND rank > 0
        ORDER BY COALESCE(date, checked_at) DESC
        LIMIT 7
    """, (keyword,))

    records = cursor.fetchall()

    if len(records) < 2:
        return {'decline_streak': 0, 'decline_amount': 0, 'is_declining': False}

    # 연속 하락 일수 계산 (순위가 증가하면 하락)
    decline_streak = 0
    decline_amount = 0
    first_rank = records[0]['rank']

    for i in range(len(records) - 1):
        current_rank = records[i]['rank']
        previous_rank = records[i + 1]['rank']

        # 순위 숫자가 증가 = 하락 (예: 3위 → 5위)
        if current_rank > previous_rank:
            decline_streak += 1
            decline_amount += (current_rank - previous_rank)
        else:
            break

    return {
        'decline_streak': decline_streak,
        'decline_amount': decline_amount,
        'is_declining': decline_streak >= 2  # 2일 이상 연속 하락 시 경고
    }


def calculate_all_decline_streaks(cursor, target_name: str = None) -> Dict[str, Dict[str, Any]]:
    """
    [최적화] 모든 키워드의 연속 하락 일수를 한 번에 계산
    - N+1 쿼리 문제 해결: 키워드 수만큼 쿼리 → 단일 쿼리
    - 최근 7일간의 순위 기록을 모든 키워드에 대해 한 번에 분석
    - target_name 필터: 메인 타겟의 데이터만 조회 (경쟁사 제외)
    """
    # target_name이 없으면 기본값 사용
    if not target_name:
        target_name = _get_main_target_name()

    # 모든 키워드의 최근 7일 순위 데이터를 한 번에 조회
    cursor.execute("""
        WITH ranked_data AS (
            SELECT
                keyword,
                rank,
                COALESCE(date, checked_at) as scan_date,
                ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
            FROM rank_history
            WHERE status = 'found' AND rank > 0 AND target_name = ?
        )
        SELECT keyword, rank, scan_date, rn
        FROM ranked_data
        WHERE rn <= 7
        ORDER BY keyword, rn ASC
    """, (target_name,))

    rows = cursor.fetchall()

    # 키워드별로 데이터 그룹화
    keyword_data: Dict[str, list] = {}
    for row in rows:
        keyword = row['keyword']
        if keyword not in keyword_data:
            keyword_data[keyword] = []
        keyword_data[keyword].append({'rank': row['rank'], 'rn': row['rn']})

    # 각 키워드의 decline_streak 계산
    results: Dict[str, Dict[str, Any]] = {}
    for keyword, records in keyword_data.items():
        if len(records) < 2:
            results[keyword] = {'decline_streak': 0, 'decline_amount': 0, 'is_declining': False}
            continue

        # rn 순서대로 정렬 (rn=1이 가장 최신)
        records.sort(key=lambda x: x['rn'])

        decline_streak = 0
        decline_amount = 0

        for i in range(len(records) - 1):
            current_rank = records[i]['rank']
            previous_rank = records[i + 1]['rank']

            # 순위 숫자가 증가 = 하락 (예: 3위 → 5위)
            if current_rank > previous_rank:
                decline_streak += 1
                decline_amount += (current_rank - previous_rank)
            else:
                break

        results[keyword] = {
            'decline_streak': decline_streak,
            'decline_amount': decline_amount,
            'is_declining': decline_streak >= 2
        }

    return results


def _get_main_target_name() -> str:
    """business_profile.json에서 메인 타겟 이름 조회"""
    try:
        profile_path = os.path.join(parent_dir, 'config', 'business_profile.json')
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('business', {}).get('name', '규림한의원')
    except Exception as e:
        logger.warning(f"business_profile.json 로드 실패: {e}")
    return '규림한의원'


@router.get("/ranking-keywords")
async def get_ranking_keywords() -> List[Dict[str, Any]]:
    """
    순위 추적 중인 키워드 목록 조회 (모바일/데스크톱 순위 포함)
    - status: scanned (순위 발견), not_found (순위권 밖), pending (스캔 대기)
    - decline_streak: 연속 하락 일수
    - decline_amount: 총 하락 폭
    - is_declining: 경고 필요 여부 (2일 이상 연속 하락)
    - mobile_rank: 모바일 순위
    - desktop_rank: 데스크톱 순위
    """
    # [성능 최적화] 캐시 조회 (30초 TTL)
    cached = _ranking_cache.get('ranking_keywords')
    if cached is not None:
        logger.debug("ranking-keywords 캐시 히트")
        return cached

    conn = None  # [안정성 개선] try/finally 패턴으로 연결 누수 방지
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 메인 타겟 이름 조회 (경쟁사 데이터 필터링용)
        main_target = _get_main_target_name()

        # 모든 키워드의 최신 스캔 결과 조회 (디바이스 타입별)
        # found 상태 우선 (동일 시간에 found와 not_in_results가 있으면 found 선택)
        # [FIX] target_name 필터 추가: 메인 타겟의 순위만 조회 (경쟁사 데이터 제외)
        cursor.execute("""
            WITH latest_scans AS (
                SELECT
                    keyword,
                    rank,
                    status,
                    date,
                    checked_at,
                    note,
                    COALESCE(device_type, 'mobile') as device_type,
                    ROW_NUMBER() OVER (
                        PARTITION BY keyword, COALESCE(device_type, 'mobile')
                        ORDER BY
                            COALESCE(date, checked_at) DESC,
                            CASE WHEN status = 'found' AND rank > 0 THEN 0 ELSE 1 END,
                            rank DESC
                    ) as rn
                FROM rank_history
                WHERE target_name = ?
            ),
            previous_found AS (
                SELECT
                    keyword,
                    rank,
                    COALESCE(device_type, 'mobile') as device_type,
                    ROW_NUMBER() OVER (
                        PARTITION BY keyword, COALESCE(device_type, 'mobile')
                        ORDER BY COALESCE(date, checked_at) DESC
                    ) as rn
                FROM rank_history
                WHERE status = 'found' AND rank > 0 AND target_name = ?
            )
            SELECT
                l.keyword,
                l.rank as current_rank,
                l.status as scan_status,
                l.note,
                l.device_type,
                10 as target_rank,
                COALESCE(p.rank - l.rank, 0) as rank_change,
                k.category,
                k.search_volume,
                COALESCE(l.date, l.checked_at) as last_checked
            FROM latest_scans l
            LEFT JOIN previous_found p ON l.keyword = p.keyword
                AND p.device_type = l.device_type AND p.rn = 2
            LEFT JOIN keyword_insights k ON l.keyword = k.keyword
            WHERE l.rn = 1
        """, (main_target, main_target))

        # 디바이스 타입별로 그룹화
        all_rows = cursor.fetchall()
        keyword_device_data: Dict[str, Dict[str, dict]] = {}

        for row in all_rows:
            keyword = row['keyword']
            device = row['device_type']

            if keyword not in keyword_device_data:
                keyword_device_data[keyword] = {}

            keyword_device_data[keyword][device] = dict(row)

        # 목표 순위 로드
        keyword_targets = load_keyword_targets()

        # [최적화] 모든 키워드의 하락 추세를 한 번에 계산 (N+1 쿼리 문제 해결)
        all_decline_info = calculate_all_decline_streaks(cursor, main_target)

        # 결과 변환 (모바일/데스크톱 순위 병합)
        results = []
        for keyword, device_data in keyword_device_data.items():
            # 모바일 데이터 (우선)
            mobile_data = device_data.get('mobile', {})
            desktop_data = device_data.get('desktop', {})

            # 기본 데이터는 모바일 우선, 없으면 데스크톱
            primary_data = mobile_data if mobile_data else desktop_data

            scan_status = primary_data.get('scan_status', '')
            current_rank = primary_data.get('current_rank') or 0

            # 상태 결정
            if scan_status == 'found' and current_rank > 0:
                status = 'scanned'  # 순위 발견됨
                display_rank = current_rank
            elif scan_status in ('not_in_results', 'no_results'):
                status = 'not_found'  # 스캔됐지만 순위권 밖
                display_rank = 0
            elif scan_status == 'error':
                status = 'error'  # 스캔 오류
                display_rank = 0
            else:
                status = 'pending'  # 스캔 대기
                display_rank = 0

            # 모바일/데스크톱 개별 순위 추출
            mobile_rank = 0
            desktop_rank = 0

            if mobile_data:
                m_status = mobile_data.get('scan_status', '')
                if m_status == 'found' and mobile_data.get('current_rank', 0) > 0:
                    mobile_rank = mobile_data.get('current_rank', 0)

            if desktop_data:
                d_status = desktop_data.get('scan_status', '')
                if d_status == 'found' and desktop_data.get('current_rank', 0) > 0:
                    desktop_rank = desktop_data.get('current_rank', 0)

            # 하락 추세 분석 (미리 계산된 데이터에서 조회)
            decline_info = all_decline_info.get(
                keyword,
                {'decline_streak': 0, 'decline_amount': 0, 'is_declining': False}
            )

            results.append({
                'keyword': keyword,
                'current_rank': display_rank,  # 대표 순위 (모바일 우선)
                'mobile_rank': mobile_rank,    # 모바일 순위
                'desktop_rank': desktop_rank,  # 데스크톱 순위
                'target_rank': keyword_targets.get(keyword, 10),
                'rank_change': primary_data.get('rank_change') or 0 if status == 'scanned' else 0,
                'category': primary_data.get('category') or '기타',
                'search_volume': primary_data.get('search_volume') or 0,
                'last_checked': primary_data.get('last_checked'),
                'status': status,
                'note': primary_data.get('note', ''),
                'decline_streak': decline_info['decline_streak'],
                'decline_amount': decline_info['decline_amount'],
                'is_declining': decline_info['is_declining']
            })

        # 최신순 정렬
        results.sort(key=lambda x: x['last_checked'] or '', reverse=True)

        # [성능 최적화] 결과 캐시 저장
        _ranking_cache.set('ranking_keywords', results)

        return results  # 전체 반환 (제한 없음)

    except Exception as e:
        logger.error(f"get_ranking_keywords 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"순위 키워드 조회 실패: {str(e)}")
    finally:
        if conn:
            conn.close()


@router.post("/ranking-keywords/refresh-volumes")
async def refresh_keyword_volumes() -> Dict[str, Any]:
    """
    추적 중인 키워드들의 검색량 일괄 업데이트
    - keyword_insights에 없거나 검색량이 0인 키워드들의 검색량을 조회
    - Naver API는 공백 없는 키워드를 반환하므로, 공백 제거 버전도 함께 매칭
    """
    conn = None  # [안정성 개선] try/finally 패턴
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # [Phase 2 최적화] 최근 30일 내 활성 키워드만 대상 (전체 로드 방지)
        cursor.execute("""
            SELECT DISTINCT keyword FROM rank_history
            WHERE checked_at >= date('now', '-30 days')
        """)
        all_keywords = [row[0] for row in cursor.fetchall()]

        if not all_keywords:
            return {"status": "success", "message": "추적 중인 키워드 없음", "updated": 0}

        # 2. keyword_insights에서 검색량이 0이거나 없는 키워드 찾기
        placeholders = ','.join(['?' for _ in all_keywords])
        cursor.execute(f"""
            SELECT keyword, search_volume FROM keyword_insights
            WHERE keyword IN ({placeholders})
        """, all_keywords)
        existing = {row[0]: row[1] for row in cursor.fetchall()}

        # 검색량이 없거나 0인 키워드
        keywords_to_update = [kw for kw in all_keywords if kw not in existing or existing.get(kw, 0) == 0]

        if not keywords_to_update:
            return {"status": "success", "message": "모든 키워드에 검색량이 있음", "updated": 0}

        # 3. keyword_volume_cache에서 공백 제거 버전으로 검색량 찾기 (배치 쿼리)
        updated_count = 0
        matched_from_cache = 0

        # [N+1 최적화] 모든 키워드의 공백 제거 버전을 한 번에 조회
        keyword_map = {kw.replace(" ", ""): kw for kw in keywords_to_update}
        no_space_keywords = list(keyword_map.keys())

        if no_space_keywords:
            cache_placeholders = ','.join(['?' for _ in no_space_keywords])
            cursor.execute(f"""
                SELECT keyword, volume FROM keyword_volume_cache
                WHERE keyword IN ({cache_placeholders}) AND volume > 0
            """, no_space_keywords)
            cache_results = {row[0]: row[1] for row in cursor.fetchall()}

            # 배치 INSERT를 위한 데이터 준비
            insert_data = []
            for no_space_kw, volume in cache_results.items():
                original_kw = keyword_map.get(no_space_kw)
                if original_kw:
                    insert_data.append((original_kw, volume))
                    matched_from_cache += 1
                    logger.debug(f"캐시에서 매칭: {original_kw} = {volume} (공백 제거: {no_space_kw})")

            # 배치 INSERT 실행
            if insert_data:
                cursor.executemany("""
                    INSERT INTO keyword_insights (keyword, search_volume, category, created_at)
                    VALUES (?, ?, '기타', datetime('now'))
                    ON CONFLICT(keyword) DO UPDATE SET
                        search_volume = excluded.search_volume
                """, insert_data)
                updated_count = len(insert_data)

        conn.commit()

        # 4. 캐시에서 못 찾은 키워드는 API 호출
        remaining_keywords = [kw for kw in keywords_to_update
                            if kw.replace(" ", "") not in [k.replace(" ", "") for k in existing.keys()]]

        if remaining_keywords and matched_from_cache < len(keywords_to_update):
            try:
                from scrapers.naver_ad_manager import NaverAdManager
                ad_manager = NaverAdManager()
                volumes = ad_manager.get_keyword_volumes(remaining_keywords)

                if volumes:
                    # [N+1 최적화] 배치 INSERT로 변환
                    api_insert_data = []
                    for keyword in remaining_keywords:
                        keyword_no_space = keyword.replace(" ", "")
                        volume = volumes.get(keyword, 0) or volumes.get(keyword_no_space, 0)

                        if volume > 0:
                            api_insert_data.append((keyword, volume))
                            logger.debug(f"API에서 업데이트: {keyword} = {volume}")

                    if api_insert_data:
                        cursor.executemany("""
                            INSERT INTO keyword_insights (keyword, search_volume, category, created_at)
                            VALUES (?, ?, '기타', datetime('now'))
                            ON CONFLICT(keyword) DO UPDATE SET
                                search_volume = excluded.search_volume
                        """, api_insert_data)
                        updated_count += len(api_insert_data)

                    conn.commit()
            except Exception as e:
                logger.warning(f"검색량 API 조회 실패: {e}")

        return {
            "status": "success",
            "message": f"{updated_count}개 키워드 검색량 업데이트 (캐시: {matched_from_cache})",
            "updated": updated_count,
            "total_checked": len(keywords_to_update),
            "matched_from_cache": matched_from_cache
        }

    except Exception as e:
        logger.error(f"refresh_keyword_volumes 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/ranking-trends")
async def get_ranking_trends(
    days: int = 14,
    keyword_filter: Optional[str] = None,
    device_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    순위 트렌드 조회 (모바일/데스크톱 구분)

    Args:
        days: 조회 기간 (일)
        keyword_filter: 키워드 필터
        device_type: 디바이스 타입 필터 ('mobile', 'desktop', None=전체)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 메인 타겟 이름 조회 (경쟁사 데이터 필터링용)
        main_target = _get_main_target_name()

        # 날짜 필터 (date 컬럼은 YYYY-MM-DD 형식)
        date_cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 키워드별 순위 히스토리 (date 컬럼 사용, status='found'만)
        # SQL Injection 방지를 위해 파라미터화된 쿼리 사용
        # [FIX] target_name 필터 추가: 메인 타겟의 순위만 조회
        params: List[str] = [main_target, date_cutoff]
        keyword_filter_sql = ""
        device_filter_sql = ""

        if keyword_filter:
            keyword_filter_sql = "AND keyword LIKE ?"
            params.append(f"%{keyword_filter}%")

        if device_type and device_type in ('mobile', 'desktop'):
            device_filter_sql = "AND COALESCE(device_type, 'mobile') = ?"
            params.append(device_type)

        cursor.execute(f"""
            SELECT keyword, rank, date, checked_at, COALESCE(device_type, 'mobile') as device_type
            FROM rank_history
            WHERE target_name = ?
            AND date >= ?
            AND status = 'found'
            AND rank > 0
            {keyword_filter_sql}
            {device_filter_sql}
            ORDER BY keyword, date
        """, tuple(params))

        # 키워드별, 디바이스별로 그룹화
        trends: Dict[str, Dict[str, list]] = {}
        for row in cursor.fetchall():
            keyword = row['keyword']
            dev_type = row['device_type']
            if keyword not in trends:
                trends[keyword] = {'mobile': [], 'desktop': []}
            # date 컬럼 사용 (YYYY-MM-DD), 없으면 checked_at 사용
            date_value = row['date'] or row['checked_at']
            trends[keyword][dev_type].append({
                'rank': row['rank'],
                'date': date_value,
                'device_type': dev_type
            })

        # 요약 통계
        improving = 0
        declining = 0
        stable = 0

        for keyword, device_data in trends.items():
            # 모바일 기준으로 트렌드 계산 (우선순위)
            history = device_data.get('mobile', []) or device_data.get('desktop', [])
            if len(history) >= 2:
                first_rank = history[0]['rank']
                last_rank = history[-1]['rank']
                diff = first_rank - last_rank  # 양수면 순위 상승 (숫자가 작아짐)

                if diff > 2:
                    improving += 1
                elif diff < -2:
                    declining += 1
                else:
                    stable += 1
            elif len(history) == 1:
                # 히스토리가 1개인 경우도 stable로 계산
                stable += 1

        conn.close()

        return {
            "keywords": trends,
            "summary": {
                "improving": improving,
                "declining": declining,
                "stable": stable,
                "total": len(trends)
            }
        }

    except Exception as e:
        logger.error(f"ranking-trends 오류: {str(e)}", exc_info=True)
        return {
            "keywords": {},
            "summary": {
                "improving": 0,
                "declining": 0,
                "stable": 0,
                "total": 0
            }
        }
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

@router.post("/ranking-keywords")
async def add_ranking_keyword(keyword: RankingKeyword) -> Dict[str, str]:
    """
    순위 추적 키워드 추가 (검색량 자동 조회)
    - Naver API는 공백 없는 키워드를 반환하므로 캐시에서 공백 제거 버전도 확인
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 1. 검색량 조회 (헬퍼 함수 사용)
        search_volume = get_keyword_search_volume(cursor, keyword.keyword)

        # 2. keyword_insights에 INSERT 또는 UPDATE
        cursor.execute("""
            INSERT INTO keyword_insights (keyword, search_volume, category, created_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(keyword) DO UPDATE SET
                search_volume = CASE
                    WHEN excluded.search_volume > 0 THEN excluded.search_volume
                    ELSE search_volume
                END,
                category = excluded.category
        """, (keyword.keyword, search_volume, keyword.category))

        # 3. rank_history에 초기 기록 추가
        cursor.execute("""
            INSERT OR IGNORE INTO rank_history (keyword, rank, checked_at)
            VALUES (?, ?, datetime('now'))
        """, (keyword.keyword, 0))

        conn.commit()
        conn.close()

        # keywords.json에도 추가 (스캔 대상에 포함)
        keywords_path = os.path.join(parent_dir, 'config', 'keywords.json')
        try:
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)

            if keyword.keyword not in keywords_data.get('naver_place', []):
                keywords_data.setdefault('naver_place', []).append(keyword.keyword)
                with open(keywords_path, 'w', encoding='utf-8') as f:
                    json.dump(keywords_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"keywords.json 업데이트 실패: {e}")

        return {
            "status": "success",
            "message": f"'{keyword.keyword}' 순위 추적 시작"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

@router.delete("/ranking-keywords/{keyword}")
async def remove_ranking_keyword(keyword: str) -> Dict[str, str]:
    """
    순위 추적 키워드 제거
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM rank_history WHERE keyword = ?", (keyword,))
        conn.commit()
        conn.close()

        # keywords.json에서도 제거
        keywords_path = os.path.join(parent_dir, 'config', 'keywords.json')
        try:
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)

            if keyword in keywords_data.get('naver_place', []):
                keywords_data['naver_place'].remove(keyword)
                with open(keywords_path, 'w', encoding='utf-8') as f:
                    json.dump(keywords_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"keywords.json 업데이트 실패: {e}")

        return {
            "status": "success",
            "message": f"'{keyword}' 순위 추적 중지"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class UpdateKeywordRequest(BaseModel):
    """키워드 수정 요청"""
    new_keyword: str
    category: Optional[str] = None

    @field_validator('new_keyword')
    @classmethod
    def new_keyword_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('새 키워드는 비어있을 수 없습니다')
        return v.strip()


@router.put("/ranking-keywords/{old_keyword}")
async def update_ranking_keyword(old_keyword: str, request: UpdateKeywordRequest) -> Dict[str, str]:
    """
    순위 추적 키워드 수정 (이름 변경 + 검색량 조회)
    """
    try:
        new_keyword = request.new_keyword

        if old_keyword == new_keyword and not request.category:
            return {
                "status": "success",
                "message": "변경 사항 없음"
            }

        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 1. 새 키워드의 검색량 조회 (키워드가 변경된 경우, 헬퍼 함수 사용)
        search_volume = 0
        if old_keyword != new_keyword:
            search_volume = get_keyword_search_volume(cursor, new_keyword)

        # 2. rank_history에서 키워드 업데이트
        cursor.execute("""
            UPDATE rank_history
            SET keyword = ?
            WHERE keyword = ?
        """, (new_keyword, old_keyword))

        # 3. keyword_insights 처리
        # 기존 키워드가 있는지 확인
        cursor.execute("SELECT search_volume, category FROM keyword_insights WHERE keyword = ?", (old_keyword,))
        old_row = cursor.fetchone()

        if old_row and old_keyword != new_keyword:
            # 기존 키워드가 있고 이름 변경 시: 기존 삭제 후 새로 추가
            old_volume, old_category = old_row
            cursor.execute("DELETE FROM keyword_insights WHERE keyword = ?", (old_keyword,))

            # 새 검색량이 없으면 기존 값 유지
            final_volume = search_volume if search_volume > 0 else old_volume
            final_category = request.category or old_category

            cursor.execute("""
                INSERT INTO keyword_insights (keyword, search_volume, category, created_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(keyword) DO UPDATE SET
                    search_volume = CASE WHEN excluded.search_volume > 0 THEN excluded.search_volume ELSE search_volume END,
                    category = excluded.category
            """, (new_keyword, final_volume, final_category))

        elif not old_row:
            # 기존 키워드가 없으면 새로 추가
            cursor.execute("""
                INSERT INTO keyword_insights (keyword, search_volume, category, created_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(keyword) DO UPDATE SET
                    search_volume = CASE WHEN excluded.search_volume > 0 THEN excluded.search_volume ELSE search_volume END,
                    category = excluded.category
            """, (new_keyword, search_volume, request.category or '기타'))

        elif request.category:
            # 이름 변경 없이 카테고리만 변경
            cursor.execute("""
                UPDATE keyword_insights
                SET category = ?
                WHERE keyword = ?
            """, (request.category, new_keyword))

        conn.commit()
        conn.close()

        # keywords.json에서도 업데이트
        keywords_path = os.path.join(parent_dir, 'config', 'keywords.json')
        try:
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)

            # naver_place에서 교체
            if old_keyword in keywords_data.get('naver_place', []):
                idx = keywords_data['naver_place'].index(old_keyword)
                keywords_data['naver_place'][idx] = new_keyword
                with open(keywords_path, 'w', encoding='utf-8') as f:
                    json.dump(keywords_data, f, ensure_ascii=False, indent=2)

            # blog_seo에서 교체
            elif old_keyword in keywords_data.get('blog_seo', []):
                idx = keywords_data['blog_seo'].index(old_keyword)
                keywords_data['blog_seo'][idx] = new_keyword
                with open(keywords_path, 'w', encoding='utf-8') as f:
                    json.dump(keywords_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"keywords.json 업데이트 실패: {e}")

        return {
            "status": "success",
            "message": f"'{old_keyword}' → '{new_keyword}' 변경 완료"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/competitor-vitals")
async def get_competitor_vitals() -> Dict[str, Any]:
    """
    경쟁사 활력 정보 (리뷰 활동량 기반)

    Returns:
        - competitors: 경쟁사별 활동량 목록
        - summary: 요약 통계
    """
    import json

    default_response = {
        "competitors": [],
        "summary": {
            "total_competitors": 0,
            "most_active": "-",
            "avg_reviews_30d": 0
        }
    }

    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # competitor_reviews 테이블에서 경쟁사별 리뷰 통계 조회
        # review_date 기준으로 최근 7일/30일 계산 (실제 리뷰 작성일)
        cursor.execute("""
            SELECT
                competitor_name,
                COUNT(*) as total_reviews,
                COUNT(CASE WHEN review_date >= date('now', '-30 days') THEN 1 END) as reviews_30d,
                COUNT(CASE WHEN review_date >= date('now', '-7 days') THEN 1 END) as reviews_7d,
                COUNT(CASE WHEN sentiment = 'positive' THEN 1 END) as positive_count,
                COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative_count,
                ROUND(AVG(CASE WHEN star_rating IS NOT NULL THEN star_rating END), 1) as avg_star_rating,
                COUNT(CASE WHEN star_rating IS NOT NULL THEN 1 END) as rated_count,
                MAX(scraped_at) as last_scraped
            FROM competitor_reviews
            GROUP BY competitor_name
            ORDER BY reviews_30d DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return default_response

        competitors = []
        total_reviews_30d = 0
        most_active_name = "-"
        most_active_count = 0

        for row in rows:
            comp_name = row['competitor_name']
            reviews_30d = row['reviews_30d'] or 0
            total_reviews_30d += reviews_30d

            if reviews_30d > most_active_count:
                most_active_count = reviews_30d
                most_active_name = comp_name

            # 감성 분석 결과
            positive = row['positive_count'] or 0
            negative = row['negative_count'] or 0
            total = row['total_reviews'] or 0
            sentiment_ratio = round((positive / total) * 100, 1) if total > 0 else 0

            competitors.append({
                'name': comp_name,
                'total_reviews': total,
                'reviews_30d': reviews_30d,
                'reviews_7d': row['reviews_7d'] or 0,
                'positive_ratio': sentiment_ratio,
                'avg_star_rating': row['avg_star_rating'],
                'rated_count': row['rated_count'] or 0,
                'last_scraped': row['last_scraped'],
                'trend': 'active' if reviews_30d >= 10 else 'moderate' if reviews_30d >= 5 else 'low'
            })

        return {
            "competitors": competitors,
            "summary": {
                "total_competitors": len(competitors),
                "most_active": most_active_name,
                "avg_reviews_30d": round(total_reviews_30d / len(competitors), 1) if competitors else 0,
                "total_reviews_30d": total_reviews_30d
            }
        }

    except Exception as e:
        logger.error(f"competitor-vitals 오류: {str(e)}", exc_info=True)
        return default_response
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/reputation-score")
async def get_reputation_score(
    target: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """
    [고도화 V2-3] 통합 평판 점수

    네이버(40%) + 커뮤니티(25%) 가중 합산.
    경쟁사 대비 상대 지수 포함.
    """
    try:
        from services.reputation_engine import calculate_reputation_score

        db = DatabaseManager()
        result = calculate_reputation_score(
            db_path=db.db_path,
            target_name=target,
            days=days,
        )
        return result

    except Exception as e:
        logger.error(f"reputation-score 오류: {e}", exc_info=True)
        return {"error": str(e), "overall_score": 0}


class TargetRankUpdate(BaseModel):
    keyword: str
    target_rank: int

    @field_validator('target_rank')
    @classmethod
    def validate_target_rank(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError('목표 순위는 1~100 사이여야 합니다')
        return v


@router.put("/ranking-keywords/{keyword}/target-rank")
async def update_target_rank(keyword: str, data: TargetRankUpdate) -> Dict[str, Any]:
    """
    키워드의 목표 순위 업데이트

    Args:
        keyword: 키워드
        data: 목표 순위 데이터

    Returns:
        - status: 성공/실패
        - message: 결과 메시지
    """
    try:
        # 현재 목표 순위 로드
        targets = load_keyword_targets()

        # 업데이트
        targets[keyword] = data.target_rank

        # 저장
        if save_keyword_targets(targets):
            return {
                "status": "success",
                "message": f"'{keyword}'의 목표 순위가 {data.target_rank}위로 설정되었습니다"
            }
        else:
            raise HTTPException(status_code=500, detail="목표 순위 저장 실패")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 순위 예측 API - 선형 회귀 기반
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _linear_regression(x: List[float], y: List[float]) -> tuple:
    """
    간단한 선형 회귀 계산

    Returns:
        (slope, intercept, r_squared)
    """
    n = len(x)
    if n < 2:
        return 0.0, y[0] if y else 0.0, 0.0

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi ** 2 for xi in x)
    sum_y2 = sum(yi ** 2 for yi in y)

    # 기울기 & 절편
    denominator = n * sum_x2 - sum_x ** 2
    if denominator == 0:
        return 0.0, sum_y / n, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    # R² 계산 (결정계수)
    y_mean = sum_y / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))

    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return slope, intercept, max(0, min(1, r_squared))


@router.get("/ranking-forecast")
async def get_ranking_forecast(days: int = 14, forecast_days: int = 7) -> Dict[str, Any]:
    """
    [Phase 4.0] 순위 예측 API

    최근 N일 데이터를 기반으로 선형 회귀 분석을 통해 향후 순위를 예측합니다.

    Args:
        days: 분석에 사용할 과거 데이터 일수 (기본 14일)
        forecast_days: 예측할 미래 일수 (기본 7일)

    Returns:
        키워드별 예측 결과:
        - current_rank: 현재 순위
        - predicted_rank: 예측 순위 (forecast_days 후)
        - slope: 일일 순위 변화율 (음수=상승, 양수=하락)
        - trend: 추세 (improving/declining/stable)
        - confidence: 예측 신뢰도 (R² 값)
        - data_points: 분석에 사용된 데이터 수
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # keywords.json에서 추적 중인 키워드 로드
        keywords_path = os.path.join(parent_dir, 'config', 'keywords.json')
        tracked_keywords = []

        if os.path.exists(keywords_path):
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)
                tracked_keywords = keywords_data.get('naver_place', [])

        if not tracked_keywords:
            conn.close()
            return {"forecasts": [], "summary": {"improving": 0, "declining": 0, "stable": 0}}

        # 목표 순위 로드
        targets = load_keyword_targets()

        # 분석 기간
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        forecasts = []
        summary = {"improving": 0, "declining": 0, "stable": 0}

        # [N+1 최적화] 모든 키워드의 rank_history를 한 번에 조회
        placeholders = ','.join(['?' for _ in tracked_keywords])
        cursor.execute(f"""
            SELECT keyword, DATE(checked_at) as check_date, rank
            FROM rank_history
            WHERE keyword IN ({placeholders}) AND status = 'found' AND checked_at >= ?
            ORDER BY keyword, checked_at ASC
        """, (*tracked_keywords, start_date))

        all_rows = cursor.fetchall()

        # 키워드별로 그룹화
        keyword_ranks_map = {}
        for keyword, check_date, rank in all_rows:
            if keyword not in keyword_ranks_map:
                keyword_ranks_map[keyword] = {}
            keyword_ranks_map[keyword][check_date] = rank

        for keyword in tracked_keywords:
            daily_ranks = keyword_ranks_map.get(keyword, {})

            if len(daily_ranks) < 3:
                # 데이터 부족
                continue

            dates = sorted(daily_ranks.keys())
            ranks = [daily_ranks[d] for d in dates]

            # X값: 날짜 인덱스 (0, 1, 2, ...)
            x = list(range(len(ranks)))
            y = ranks

            # 선형 회귀 수행
            slope, intercept, r_squared = _linear_regression(x, y)

            # 현재 순위 (가장 최근)
            current_rank = ranks[-1]

            # ─────────────────────────────────────────────
            # 고도화된 예측 모델 적용
            # ─────────────────────────────────────────────

            # 1. 지수 이동 평균 (EMA) 계산
            alpha = 0.3
            ema = ranks[-1]
            for rank in reversed(ranks[:-1][:14]):  # 최근 14일
                ema = alpha * rank + (1 - alpha) * ema

            # 2. 모멘텀 (가속도) 계산
            if len(ranks) >= 6:
                very_recent = sum(ranks[-3:]) / 3
                slightly_older = sum(ranks[-6:-3]) / 3
                older_avg = sum(ranks[-14:-7]) / 7 if len(ranks) >= 14 else sum(ranks[:-7]) / max(1, len(ranks) - 7) if len(ranks) > 7 else very_recent
                recent_avg = sum(ranks[-7:]) / min(7, len(ranks))
                trend_delta = older_avg - recent_avg
                acceleration = (slightly_older - very_recent) - (trend_delta / 2)
            else:
                acceleration = 0
                trend_delta = 0

            # 3. 예측 순위 계산 (EMA + 트렌드 + 가속도)
            base_prediction = ema
            trend_effect = (slope * forecast_days * -1) * 0.5  # 선형 회귀 기반
            accel_effect = acceleration * 0.3 * (forecast_days / 7)

            predicted_rank = round(base_prediction + trend_effect + accel_effect)
            predicted_rank = max(1, min(100, predicted_rank))  # 1~100 범위 제한

            # 4. 변동성 계산 및 신뢰 구간
            recent_ranks = ranks[-7:] if len(ranks) >= 7 else ranks
            recent_avg = sum(recent_ranks) / len(recent_ranks)
            variance = sum((r - recent_avg) ** 2 for r in recent_ranks) / len(recent_ranks)
            volatility = variance ** 0.5

            confidence_margin = volatility * (1 + forecast_days / 14)
            predicted_lower = max(1, round(predicted_rank - confidence_margin))
            predicted_upper = min(100, round(predicted_rank + confidence_margin))

            # 추세 판단
            if slope < -0.1:
                trend = "improving"
                summary["improving"] += 1
            elif slope > 0.1:
                trend = "declining"
                summary["declining"] += 1
            else:
                trend = "stable"
                summary["stable"] += 1

            # 목표 순위
            target_rank = targets.get(keyword, 10)

            # 목표 달성 예측
            on_track = predicted_rank <= target_rank

            forecasts.append({
                "keyword": keyword,
                "current_rank": current_rank,
                "predicted_rank": predicted_rank,
                "predicted_lower": predicted_lower,
                "predicted_upper": predicted_upper,
                "target_rank": target_rank,
                "slope": round(slope, 3),
                "trend": trend,
                "confidence": round(r_squared * 100, 1),
                "on_track": on_track,
                "data_points": len(ranks),
                "rank_change": predicted_rank - current_rank,
                "model_factors": {
                    "ema": round(ema, 1),
                    "acceleration": round(acceleration, 2),
                    "volatility": round(volatility, 2)
                }
            })

        conn.close()

        # 순위 변화가 큰 순으로 정렬
        forecasts.sort(key=lambda x: abs(x['slope']), reverse=True)

        return {
            "forecasts": forecasts,
            "summary": summary,
            "analysis_period_days": days,
            "forecast_days": forecast_days
        }

    except Exception as e:
        logger.error(f"순위 예측 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"순위 예측 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/forecast-accuracy")
async def get_forecast_accuracy(
    backtest_days: int = 7,
    analysis_days: int = 14
) -> Dict[str, Any]:
    """
    [Phase 4.0 P2-3] 예측 정확도 검증 API (백테스팅)

    과거 시점에서 예측했던 결과를 실제 결과와 비교하여 정확도를 계산합니다.

    Args:
        backtest_days: 몇 일 전 시점에서 예측했는지 (기본 7일)
        analysis_days: 예측에 사용할 분석 기간 (기본 14일)

    Returns:
        키워드별 예측 vs 실제 비교 결과:
        - predicted_rank: 과거 시점에서 예측한 순위
        - actual_rank: 실제 순위
        - error: 예측 오차 (예측 - 실제)
        - accuracy_pct: 정확도 % (100 - |오차|/실제*100, 최대 100)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # keywords.json에서 추적 중인 키워드 로드
        keywords_path = os.path.join(parent_dir, 'config', 'keywords.json')
        tracked_keywords = []

        if os.path.exists(keywords_path):
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords_data = json.load(f)
                tracked_keywords = keywords_data.get('naver_place', [])

        if not tracked_keywords:
            conn.close()
            return {
                "accuracy_results": [],
                "summary": {
                    "total_predictions": 0,
                    "avg_accuracy_pct": 0,
                    "avg_error": 0,
                    "perfect_predictions": 0
                }
            }

        # 백테스트 기준점: backtest_days일 전
        backtest_date = (datetime.now() - timedelta(days=backtest_days)).strftime('%Y-%m-%d')
        # 예측에 사용할 데이터 시작점: backtest_date - analysis_days
        analysis_start = (datetime.now() - timedelta(days=backtest_days + analysis_days)).strftime('%Y-%m-%d')

        accuracy_results = []
        total_errors = []
        perfect_count = 0

        # [N+1 최적화] 과거 데이터 배치 조회
        placeholders = ','.join(['?' for _ in tracked_keywords])
        cursor.execute(f"""
            SELECT keyword, DATE(checked_at) as check_date, rank
            FROM rank_history
            WHERE keyword IN ({placeholders}) AND status = 'found'
            AND checked_at >= ? AND checked_at < ?
            ORDER BY keyword, checked_at ASC
        """, (*tracked_keywords, analysis_start, backtest_date))

        past_data_all = cursor.fetchall()

        # 키워드별로 그룹화
        past_data_map = {}
        for keyword, check_date, rank in past_data_all:
            if keyword not in past_data_map:
                past_data_map[keyword] = {}
            past_data_map[keyword][check_date] = rank

        # [N+1 최적화] 실제 순위 배치 조회 (최신 순위)
        cursor.execute(f"""
            SELECT keyword, rank
            FROM rank_history rh1
            WHERE keyword IN ({placeholders}) AND status = 'found'
            AND checked_at = (
                SELECT MAX(checked_at) FROM rank_history rh2
                WHERE rh2.keyword = rh1.keyword AND rh2.status = 'found'
            )
        """, tracked_keywords)

        actual_ranks_map = {row[0]: row[1] for row in cursor.fetchall()}

        for keyword in tracked_keywords:
            daily_ranks = past_data_map.get(keyword, {})

            if len(daily_ranks) < 3:
                continue

            dates = sorted(daily_ranks.keys())
            ranks = [daily_ranks[d] for d in dates]

            # 선형 회귀
            x = list(range(len(ranks)))
            y = ranks
            slope, intercept, r_squared = _linear_regression(x, y)

            # 예측 (backtest_days 후 = 오늘)
            future_x = len(ranks) - 1 + backtest_days
            predicted_rank = round(slope * future_x + intercept)
            predicted_rank = max(1, min(100, predicted_rank))

            # 실제 순위 조회 (배치에서 가져옴)
            actual_rank = actual_ranks_map.get(keyword)
            if not actual_rank:
                continue

            # 오차 계산
            error = predicted_rank - actual_rank
            abs_error = abs(error)

            # 정확도 % (순위 기반, 실제 순위 대비 오차율로 계산)
            error_rate = abs_error / max(actual_rank, 1) * 100
            accuracy_pct = max(0, 100 - error_rate)

            # 완벽 예측 (±1 이내)
            if abs_error <= 1:
                perfect_count += 1

            total_errors.append(abs_error)

            accuracy_results.append({
                "keyword": keyword,
                "predicted_rank": predicted_rank,
                "actual_rank": actual_rank,
                "error": error,
                "abs_error": abs_error,
                "accuracy_pct": round(accuracy_pct, 1),
                "confidence": round(r_squared * 100, 1),
                "data_points": len(ranks),
                "is_accurate": abs_error <= 3  # ±3 이내면 정확
            })

        conn.close()

        # 통계 요약
        total_predictions = len(accuracy_results)
        avg_accuracy = sum(r['accuracy_pct'] for r in accuracy_results) / total_predictions if total_predictions > 0 else 0
        avg_error = sum(total_errors) / len(total_errors) if total_errors else 0
        accurate_count = sum(1 for r in accuracy_results if r['is_accurate'])

        # 정확도 높은 순으로 정렬
        accuracy_results.sort(key=lambda x: x['accuracy_pct'], reverse=True)

        return {
            "accuracy_results": accuracy_results,
            "summary": {
                "total_predictions": total_predictions,
                "avg_accuracy_pct": round(avg_accuracy, 1),
                "avg_error": round(avg_error, 2),
                "perfect_predictions": perfect_count,
                "accurate_predictions": accurate_count,
                "accuracy_rate": round(accurate_count / total_predictions * 100, 1) if total_predictions > 0 else 0
            },
            "backtest_days": backtest_days,
            "analysis_days": analysis_days
        }

    except Exception as e:
        logger.error(f"예측 정확도 검증 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"예측 정확도 검증 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/rank-drop-alerts")
async def get_rank_drop_alerts(
    min_drop: int = 3,
    include_trends: bool = True
) -> Dict[str, Any]:
    """
    [Phase 6.1] 순위 하락 알림 조회

    순위가 하락한 키워드들을 조회합니다.

    Args:
        min_drop: 최소 하락 폭 (기본 3순위 이상 하락)
        include_trends: 연속 하락 추세 포함 여부

    Returns:
        - alerts: 순위 하락 키워드 목록
        - summary: 요약 정보
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 메인 타겟 이름 조회 (경쟁사 데이터 필터링용)
        main_target = _get_main_target_name()

        # 최근 순위 변화 조회
        # [FIX] target_name 필터 추가
        cursor.execute("""
            WITH latest_scans AS (
                SELECT
                    keyword,
                    rank,
                    status,
                    date,
                    checked_at,
                    ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
                FROM rank_history
                WHERE target_name = ?
            ),
            previous_found AS (
                SELECT
                    keyword,
                    rank,
                    ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
                FROM rank_history
                WHERE status = 'found' AND rank > 0 AND target_name = ?
            )
            SELECT
                l.keyword,
                l.rank as current_rank,
                p.rank as previous_rank,
                (p.rank - l.rank) as rank_change,
                l.status,
                COALESCE(l.date, l.checked_at) as last_checked
            FROM latest_scans l
            LEFT JOIN previous_found p ON l.keyword = p.keyword AND p.rn = 2
            WHERE l.rn = 1
            AND l.status = 'found'
            AND l.rank > 0
            AND p.rank > 0
            AND (l.rank - p.rank) >= ?
            ORDER BY (l.rank - p.rank) DESC
        """, (main_target, main_target, min_drop))

        alerts = []
        for row in cursor.fetchall():
            alert = {
                "keyword": row["keyword"],
                "current_rank": row["current_rank"],
                "previous_rank": row["previous_rank"],
                "rank_drop": row["current_rank"] - row["previous_rank"],
                "last_checked": row["last_checked"],
                "severity": "critical" if row["current_rank"] - row["previous_rank"] >= 10 else
                           "high" if row["current_rank"] - row["previous_rank"] >= 5 else "medium"
            }
            alerts.append(alert)

        # 연속 하락 추세 추가
        if include_trends:
            decline_info = calculate_all_decline_streaks(cursor, main_target)
            for alert in alerts:
                keyword = alert["keyword"]
                if keyword in decline_info:
                    alert["decline_streak"] = decline_info[keyword]["decline_streak"]
                    alert["decline_amount"] = decline_info[keyword]["decline_amount"]
                    alert["is_declining"] = decline_info[keyword]["is_declining"]

        conn.close()

        # 심각도별 개수
        critical_count = sum(1 for a in alerts if a["severity"] == "critical")
        high_count = sum(1 for a in alerts if a["severity"] == "high")
        medium_count = sum(1 for a in alerts if a["severity"] == "medium")

        return {
            "alerts": alerts,
            "total": len(alerts),
            "summary": {
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count
            },
            "min_drop_threshold": min_drop
        }

    except Exception as e:
        logger.error(f"순위 하락 알림 조회 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"순위 하락 알림 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/generate-rank-alerts")
async def generate_rank_drop_notifications(
    min_drop: int = 3
) -> Dict[str, Any]:
    """
    [Phase 6.1] 순위 하락 알림 자동 생성

    순위가 하락한 키워드에 대해 notifications 테이블에 알림을 생성합니다.
    24시간 내 동일 키워드에 대한 알림이 있으면 중복 생성하지 않습니다.

    Args:
        min_drop: 최소 하락 폭 (기본 3순위 이상 하락)

    Returns:
        - created_count: 생성된 알림 수
        - skipped_count: 중복으로 건너뛴 알림 수
        - alerts: 생성된 알림 목록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 메인 타겟 이름 조회 (경쟁사 데이터 필터링용)
        main_target = _get_main_target_name()

        # notifications 테이블 생성 (없으면)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                title TEXT NOT NULL,
                message TEXT,
                link TEXT,
                metadata TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 순위 하락 키워드 조회
        # [FIX] target_name 필터 추가
        cursor.execute("""
            WITH latest_scans AS (
                SELECT
                    keyword,
                    rank,
                    status,
                    ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
                FROM rank_history
                WHERE target_name = ?
            ),
            previous_found AS (
                SELECT
                    keyword,
                    rank,
                    ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
                FROM rank_history
                WHERE status = 'found' AND rank > 0 AND target_name = ?
            )
            SELECT
                l.keyword,
                l.rank as current_rank,
                p.rank as previous_rank
            FROM latest_scans l
            LEFT JOIN previous_found p ON l.keyword = p.keyword AND p.rn = 2
            WHERE l.rn = 1
            AND l.status = 'found'
            AND l.rank > 0
            AND p.rank > 0
            AND (l.rank - p.rank) >= ?
        """, (main_target, main_target, min_drop))

        dropped_keywords = cursor.fetchall()

        created_alerts = []
        skipped_count = 0

        # [Phase 6.1] N+1 쿼리 최적화: 24시간 내 알림이 있는 키워드를 한 번에 조회
        cursor.execute("""
            SELECT DISTINCT reference_keyword FROM notifications
            WHERE type = 'rank_change'
            AND reference_keyword IS NOT NULL
            AND created_at >= datetime('now', '-1 day')
        """)
        recent_alert_keywords = {row[0] for row in cursor.fetchall()}

        for kw in dropped_keywords:
            keyword = kw["keyword"]
            current_rank = kw["current_rank"]
            previous_rank = kw["previous_rank"]
            drop = current_rank - previous_rank

            # [Phase 6.1] 인덱스 활용: reference_keyword 컬럼으로 빠른 조회
            if keyword in recent_alert_keywords:
                skipped_count += 1
                continue

            # 심각도 결정
            priority = "critical" if drop >= 10 else "high" if drop >= 5 else "medium"

            # 알림 생성
            title = f"📉 '{keyword}' 순위 {drop}위 하락"
            message = f"'{keyword}'가 {previous_rank}위에서 {current_rank}위로 하락했습니다. 즉시 확인이 필요합니다."
            metadata = json.dumps({
                "keyword": keyword,
                "current_rank": current_rank,
                "previous_rank": previous_rank,
                "drop": drop
            }, ensure_ascii=False)

            # [Phase 6.1] reference_keyword 컬럼 추가하여 인덱스 활용
            cursor.execute("""
                INSERT INTO notifications (type, priority, title, message, link, metadata, reference_keyword)
                VALUES ('rank_change', ?, ?, ?, ?, ?, ?)
            """, (priority, title, message, '/battle', metadata, keyword))

            created_alerts.append({
                "keyword": keyword,
                "drop": drop,
                "priority": priority,
                "title": title
            })

        conn.commit()
        conn.close()

        return {
            "success": True,
            "created_count": len(created_alerts),
            "skipped_count": skipped_count,
            "alerts": created_alerts,
            "message": f"{len(created_alerts)}개의 순위 하락 알림이 생성되었습니다"
        }

    except Exception as e:
        logger.error(f"순위 하락 알림 생성 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"순위 하락 알림 생성 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 6.2] 경쟁사 순위 추적 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CompetitorRankingCreate(BaseModel):
    """경쟁사 순위 기록 생성"""
    competitor_name: str
    keyword: str
    rank: int
    note: Optional[str] = None

    @field_validator('rank')
    @classmethod
    def rank_must_be_valid(cls, v: int) -> int:
        if v < 0 or v > 200:
            raise ValueError('순위는 0~200 사이여야 합니다 (0=순위권 밖)')
        return v


@router.post("/competitor-rankings")
async def add_competitor_ranking(data: CompetitorRankingCreate) -> Dict[str, Any]:
    """
    [Phase 6.2] 경쟁사 순위 기록 추가

    특정 키워드에 대한 경쟁사의 순위를 기록합니다.

    Args:
        data: 경쟁사명, 키워드, 순위, 비고

    Returns:
        생성된 기록 ID
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO competitor_rankings (competitor_name, keyword, rank, note)
            VALUES (?, ?, ?, ?)
        """, (data.competitor_name, data.keyword, data.rank, data.note))

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "success": True,
            "id": record_id,
            "message": f"'{data.competitor_name}'의 '{data.keyword}' 순위({data.rank}위) 기록 완료"
        }
    except Exception as e:
        logger.error(f"경쟁사 순위 기록 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/competitor-rankings")
async def get_competitor_rankings(
    keyword: Optional[str] = None,
    competitor: Optional[str] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    [Phase 6.2] 경쟁사 순위 목록 조회

    Args:
        keyword: 키워드 필터 (선택)
        competitor: 경쟁사 필터 (선택)
        days: 조회 기간 (기본 30일)

    Returns:
        경쟁사별 순위 히스토리
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        date_cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT competitor_name, keyword, rank, scanned_at, note
            FROM competitor_rankings
            WHERE DATE(scanned_at) >= ?
        """
        params: List[str] = [date_cutoff]

        if keyword:
            query += " AND keyword = ?"
            params.append(keyword)

        if competitor:
            query += " AND competitor_name = ?"
            params.append(competitor)

        query += " ORDER BY scanned_at DESC"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        # 경쟁사별로 그룹화
        by_competitor: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            comp = row['competitor_name']
            if comp not in by_competitor:
                by_competitor[comp] = []
            by_competitor[comp].append({
                'keyword': row['keyword'],
                'rank': row['rank'],
                'scanned_at': row['scanned_at'],
                'note': row['note']
            })

        conn.close()

        return {
            "by_competitor": by_competitor,
            "total_records": len(rows),
            "competitors_count": len(by_competitor),
            "period_days": days
        }
    except Exception as e:
        logger.error(f"경쟁사 순위 조회 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/competitor-rankings/compare")
async def compare_rankings_with_competitors(
    keyword: Optional[str] = None
) -> Dict[str, Any]:
    """
    [Phase 6.2] 우리 업체와 경쟁사 순위 비교

    동일 키워드에 대해 우리 업체와 경쟁사의 최신 순위를 비교합니다.
    [FIX] rank_history 테이블에서 경쟁사 순위도 조회 (target_name 기준 구분)

    Args:
        keyword: 특정 키워드 필터 (선택, 없으면 전체)

    Returns:
        키워드별 순위 비교 결과 (프론트엔드 형식에 맞춤)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 메인 타겟 이름 조회
        main_target = _get_main_target_name()

        # [FIX] rank_history에서 우리 업체와 경쟁사 순위 모두 조회
        # 우리 업체: target_name = main_target
        # 경쟁사: target_name != main_target

        # 1. 우리 업체 순위 조회 (rank_history에서 최신, 모바일 기준)
        our_ranks_params = [main_target]
        our_ranks_query = """
            WITH latest_our_ranks AS (
                SELECT
                    keyword,
                    rank,
                    status,
                    COALESCE(date, checked_at) as scanned_at,
                    ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
                FROM rank_history
                WHERE target_name = ?
                AND COALESCE(device_type, 'mobile') = 'mobile'
            )
            SELECT keyword, rank, status, scanned_at
            FROM latest_our_ranks
            WHERE rn = 1
        """
        if keyword:
            our_ranks_query = """
                WITH latest_our_ranks AS (
                    SELECT
                        keyword,
                        rank,
                        status,
                        COALESCE(date, checked_at) as scanned_at,
                        ROW_NUMBER() OVER (PARTITION BY keyword ORDER BY COALESCE(date, checked_at) DESC) as rn
                    FROM rank_history
                    WHERE target_name = ?
                    AND keyword = ?
                    AND COALESCE(device_type, 'mobile') = 'mobile'
                )
                SELECT keyword, rank, status, scanned_at
                FROM latest_our_ranks
                WHERE rn = 1
            """
            our_ranks_params.append(keyword)

        cursor.execute(our_ranks_query, tuple(our_ranks_params))
        our_rows = cursor.fetchall()
        our_ranks = {row['keyword']: {
            'rank': row['rank'] if row['status'] == 'found' else 0,
            'status': row['status'],
            'scanned_at': row['scanned_at']
        } for row in our_rows}

        # 2. 경쟁사 순위 조회 (rank_history에서 target_name != main_target)
        comp_ranks_params = [main_target]
        comp_ranks_query = """
            WITH latest_comp_ranks AS (
                SELECT
                    target_name as competitor_name,
                    keyword,
                    rank,
                    status,
                    COALESCE(date, checked_at) as scanned_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY target_name, keyword
                        ORDER BY COALESCE(date, checked_at) DESC
                    ) as rn
                FROM rank_history
                WHERE target_name != ?
                AND COALESCE(device_type, 'mobile') = 'mobile'
            )
            SELECT competitor_name, keyword, rank, status, scanned_at
            FROM latest_comp_ranks
            WHERE rn = 1 AND status = 'found' AND rank > 0
        """
        if keyword:
            comp_ranks_query = """
                WITH latest_comp_ranks AS (
                    SELECT
                        target_name as competitor_name,
                        keyword,
                        rank,
                        status,
                        COALESCE(date, checked_at) as scanned_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY target_name, keyword
                            ORDER BY COALESCE(date, checked_at) DESC
                        ) as rn
                    FROM rank_history
                    WHERE target_name != ?
                    AND keyword = ?
                    AND COALESCE(device_type, 'mobile') = 'mobile'
                )
                SELECT competitor_name, keyword, rank, status, scanned_at
                FROM latest_comp_ranks
                WHERE rn = 1 AND status = 'found' AND rank > 0
            """
            comp_ranks_params.append(keyword)

        cursor.execute(comp_ranks_query, tuple(comp_ranks_params))
        comp_rows = cursor.fetchall()

        # 키워드별로 비교 데이터 생성
        comparisons: Dict[str, Dict[str, Any]] = {}

        # 우리 순위 먼저 추가
        for kw, data in our_ranks.items():
            comparisons[kw] = {
                'keyword': kw,
                'our_rank': data['rank'],
                'our_status': data['status'],
                'competitors': []  # [FIX] 배열로 변경 (프론트엔드 형식)
            }

        # 경쟁사 순위 추가
        for row in comp_rows:
            kw = row['keyword']
            comp_name = row['competitor_name']

            if kw not in comparisons:
                comparisons[kw] = {
                    'keyword': kw,
                    'our_rank': our_ranks.get(kw, {}).get('rank', 0),
                    'our_status': our_ranks.get(kw, {}).get('status', 'unknown'),
                    'competitors': []
                }

            # [FIX] 배열 형식으로 경쟁사 추가
            comparisons[kw]['competitors'].append({
                'name': comp_name,
                'rank': row['rank'],
                'scanned_at': row['scanned_at']
            })

        # 비교 결과 계산
        results = []
        for kw, data in comparisons.items():
            our_rank = data['our_rank']
            competitors = data['competitors']

            # 우리보다 순위가 높은(숫자가 작은) 경쟁사 수
            better_count = sum(1 for c in competitors if c['rank'] > 0 and c['rank'] < our_rank)
            worse_count = sum(1 for c in competitors if c['rank'] > 0 and c['rank'] > our_rank)

            # 순위 차이 계산 (배열 형식으로 수정)
            rank_gaps = {}
            for comp in competitors:
                if comp['rank'] > 0 and our_rank > 0:
                    rank_gaps[comp['name']] = our_rank - comp['rank']  # 양수 = 우리가 뒤처짐

            # 최고 순위 경쟁사 찾기
            best_competitor = None
            if competitors:
                sorted_comps = sorted(competitors, key=lambda x: x['rank'])
                if sorted_comps:
                    best_competitor = sorted_comps[0]['name']

            # [FIX] 프론트엔드 형식에 맞춰 our_position 사용
            # leading: 선두 (모든 경쟁사보다 높음)
            # competitive: 경쟁 (비슷함)
            # behind: 추격 필요 (경쟁사보다 낮음)
            # not_ranked: 우리 순위 없음
            if our_rank == 0:
                our_position = 'not_ranked'
            elif len(competitors) == 0:
                our_position = 'leading'  # 경쟁사 데이터 없으면 선두로
            elif better_count == 0 and worse_count > 0:
                our_position = 'leading'  # 모든 경쟁사보다 높음
            elif better_count > worse_count:
                our_position = 'behind'   # 경쟁사보다 낮음
            else:
                our_position = 'competitive'  # 비슷하거나 경쟁 중

            results.append({
                'keyword': kw,
                'our_rank': our_rank,
                'our_status': data['our_status'],
                'competitors': competitors,  # 배열 형식
                'best_competitor': best_competitor,
                'our_position': our_position,  # [FIX] 프론트엔드 형식
                'better_than_us': better_count,
                'worse_than_us': worse_count,
                'rank_gaps': rank_gaps,
            })

        conn.close()

        # 경쟁 상태별 요약 (프론트엔드 형식)
        leading_count = sum(1 for r in results if r['our_position'] == 'leading')
        competitive_count = sum(1 for r in results if r['our_position'] == 'competitive')
        behind_count = sum(1 for r in results if r['our_position'] == 'behind')
        not_ranked_count = sum(1 for r in results if r['our_position'] == 'not_ranked')

        return {
            "comparisons": results,
            "summary": {
                "total_keywords": len(results),
                "leading": leading_count,
                "competitive": competitive_count,
                "behind": behind_count,
                "not_ranked": not_ranked_count
            }
        }
    except Exception as e:
        logger.error(f"순위 비교 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
