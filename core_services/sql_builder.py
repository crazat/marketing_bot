"""
SQL Query Builder
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 보안 강화 - SQL 인젝션 방지 유틸리티

화이트리스트 검증 기반의 안전한 SQL 쿼리 빌더:
- 테이블명/컬럼명 검증
- 동적 쿼리 안전하게 구성
- 파라미터화 쿼리 지원
"""

import re
import logging
from typing import List, Optional, Tuple, Any, Set
from enum import Enum

logger = logging.getLogger(__name__)


class SQLInjectionError(Exception):
    """SQL 인젝션 시도 감지 시 발생하는 예외"""
    pass


class SortOrder(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


# 허용된 테이블명 화이트리스트
ALLOWED_TABLES: Set[str] = {
    # 핵심 테이블
    'mentions',
    'keyword_insights',
    'rank_history',
    'viral_targets',
    'competitors',
    'competitor_reviews',
    'competitor_weaknesses',
    'opportunity_keywords',

    # 인플루언서/협업
    'influencers',
    'influencer_collaborations',

    # 시스템 테이블
    'chat_sessions',
    'chat_messages',
    'insights',
    'system_logs',
    'events_log',
    'schedule_history',

    # 스캔 관련
    'scan_history',
    'briefing_runs',
    'briefing_task_results',
    'sentinel_threats',
    'daily_stats',

    # Q&A
    'qa_repository',

    # Instagram
    'instagram_competitors',
    'instagram_posts',

    # 에이전트
    'agent_actions',

    # 댓글 템플릿
    'comment_templates',
}

# SQL 키워드 블랙리스트 (사용자 입력에 포함되면 안됨)
SQL_KEYWORDS_BLACKLIST: Set[str] = {
    'DROP', 'DELETE', 'TRUNCATE', 'INSERT', 'UPDATE',
    'ALTER', 'CREATE', 'EXEC', 'EXECUTE', 'UNION',
    'SCRIPT', 'JAVASCRIPT', '--', ';', '/*', '*/',
}


def validate_table_name(table_name: str) -> str:
    """
    테이블명 검증

    Args:
        table_name: 검증할 테이블명

    Returns:
        검증된 테이블명

    Raises:
        SQLInjectionError: 허용되지 않은 테이블명
    """
    if not table_name:
        raise SQLInjectionError("테이블명이 비어있습니다")

    # 소문자로 정규화
    normalized = table_name.lower().strip()

    # 화이트리스트 검증
    if normalized not in ALLOWED_TABLES:
        logger.warning(f"⚠️ 허용되지 않은 테이블 접근 시도: {table_name}")
        raise SQLInjectionError(f"허용되지 않은 테이블: {table_name}")

    return normalized


def validate_column_name(column_name: str) -> str:
    """
    컬럼명 검증 (기본 형식 검사)

    Args:
        column_name: 검증할 컬럼명

    Returns:
        검증된 컬럼명

    Raises:
        SQLInjectionError: 유효하지 않은 컬럼명
    """
    if not column_name:
        raise SQLInjectionError("컬럼명이 비어있습니다")

    # 알파벳, 숫자, 밑줄만 허용
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column_name):
        logger.warning(f"⚠️ 유효하지 않은 컬럼명: {column_name}")
        raise SQLInjectionError(f"유효하지 않은 컬럼명: {column_name}")

    # SQL 키워드 검사
    upper_name = column_name.upper()
    if upper_name in SQL_KEYWORDS_BLACKLIST:
        raise SQLInjectionError(f"예약어는 컬럼명으로 사용 불가: {column_name}")

    return column_name


def validate_columns(columns: List[str]) -> List[str]:
    """복수 컬럼명 검증"""
    return [validate_column_name(col) for col in columns]


def sanitize_user_input(value: str) -> str:
    """
    사용자 입력 값 정제 (SQL 인젝션 방지)

    주의: 이 함수는 쿼리 파라미터용이 아님 (파라미터는 ? 바인딩 사용)
    주로 LIKE 검색용 와일드카드 이스케이프에 사용

    Args:
        value: 사용자 입력 값

    Returns:
        정제된 값
    """
    if not value:
        return ""

    # 위험한 문자 제거
    sanitized = value.replace("'", "''")  # 싱글 쿼트 이스케이프
    sanitized = sanitized.replace("\\", "\\\\")  # 백슬래시 이스케이프

    # SQL 키워드 검사 (경고만)
    upper_val = sanitized.upper()
    for keyword in SQL_KEYWORDS_BLACKLIST:
        if keyword in upper_val:
            logger.warning(f"⚠️ 사용자 입력에 SQL 키워드 포함: {keyword}")

    return sanitized


def build_select_query(
    table: str,
    columns: List[str] = None,
    where_clauses: List[str] = None,
    order_by: str = None,
    order_dir: SortOrder = SortOrder.DESC,
    limit: int = None,
    offset: int = None
) -> str:
    """
    안전한 SELECT 쿼리 빌더

    Args:
        table: 테이블명 (화이트리스트 검증됨)
        columns: 조회할 컬럼 목록 (None이면 *)
        where_clauses: WHERE 조건 목록 (예: ["status = ?", "date > ?"])
        order_by: 정렬 컬럼
        order_dir: 정렬 방향
        limit: LIMIT 값
        offset: OFFSET 값

    Returns:
        안전한 SQL 쿼리 문자열

    Example:
        query = build_select_query(
            table='mentions',
            columns=['id', 'title', 'status'],
            where_clauses=['status = ?', 'date > ?'],
            order_by='created_at',
            limit=50
        )
        cursor.execute(query, ('pending', '2026-01-01'))
    """
    # 테이블 검증
    safe_table = validate_table_name(table)

    # 컬럼 검증
    if columns:
        safe_columns = ", ".join(validate_columns(columns))
    else:
        safe_columns = "*"

    # 쿼리 빌드
    query = f"SELECT {safe_columns} FROM {safe_table}"

    # WHERE 절
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    # ORDER BY
    if order_by:
        safe_order = validate_column_name(order_by)
        query += f" ORDER BY {safe_order} {order_dir.value}"

    # LIMIT/OFFSET
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    if offset is not None:
        query += f" OFFSET {int(offset)}"

    return query


def build_insert_query(
    table: str,
    columns: List[str]
) -> Tuple[str, str]:
    """
    안전한 INSERT 쿼리 빌더

    Args:
        table: 테이블명
        columns: 삽입할 컬럼 목록

    Returns:
        (쿼리 문자열, 파라미터 플레이스홀더)

    Example:
        query, placeholders = build_insert_query('mentions', ['title', 'content'])
        # query = "INSERT INTO mentions (title, content) VALUES (?, ?)"
        cursor.execute(query, (title, content))
    """
    safe_table = validate_table_name(table)
    safe_columns = validate_columns(columns)

    col_list = ", ".join(safe_columns)
    placeholders = ", ".join(["?"] * len(safe_columns))

    query = f"INSERT INTO {safe_table} ({col_list}) VALUES ({placeholders})"
    return query, placeholders


def build_update_query(
    table: str,
    set_columns: List[str],
    where_clauses: List[str]
) -> str:
    """
    안전한 UPDATE 쿼리 빌더

    Args:
        table: 테이블명
        set_columns: SET 절 컬럼 목록 (예: ['status = ?', 'updated_at = ?'])
        where_clauses: WHERE 조건 목록

    Returns:
        쿼리 문자열

    Example:
        query = build_update_query(
            'mentions',
            ['status = ?', 'updated_at = CURRENT_TIMESTAMP'],
            ['id = ?']
        )
        cursor.execute(query, ('contacted', lead_id))
    """
    safe_table = validate_table_name(table)

    # SET 절의 컬럼명 검증 (= 앞부분만)
    for clause in set_columns:
        col_part = clause.split('=')[0].strip()
        if col_part and col_part not in ('CURRENT_TIMESTAMP',):
            validate_column_name(col_part)

    set_clause = ", ".join(set_columns)
    where_clause = " AND ".join(where_clauses)

    return f"UPDATE {safe_table} SET {set_clause} WHERE {where_clause}"


def get_table_columns(cursor, table_name: str) -> List[str]:
    """
    안전하게 테이블 컬럼 목록 조회

    Args:
        cursor: DB 커서
        table_name: 테이블명 (화이트리스트 검증됨)

    Returns:
        컬럼명 리스트
    """
    safe_table = validate_table_name(table_name)
    cursor.execute(f"PRAGMA table_info({safe_table})")
    return [row[1] for row in cursor.fetchall()]


def add_table_to_whitelist(table_name: str) -> None:
    """런타임에 허용 테이블 추가 (주의: 신중하게 사용)"""
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        ALLOWED_TABLES.add(table_name.lower())
        logger.info(f"✅ 테이블 화이트리스트 추가: {table_name}")
    else:
        raise SQLInjectionError(f"유효하지 않은 테이블명: {table_name}")


def select_column_safely(
    columns: List[str],
    primary: str,
    fallback: str,
    default: str = "NULL"
) -> str:
    """
    컬럼 존재 여부에 따라 안전하게 컬럼 선택

    Args:
        columns: 테이블의 실제 컬럼 리스트
        primary: 우선 사용할 컬럼명
        fallback: 대체 컬럼명
        default: 둘 다 없을 경우 기본값

    Returns:
        검증된 컬럼명 또는 기본값

    Example:
        date_col = select_column_safely(columns, 'created_at', 'scraped_at')
    """
    if primary in columns:
        validate_column_name(primary)
        return primary
    elif fallback in columns:
        validate_column_name(fallback)
        return fallback
    else:
        return default


def build_dynamic_where(
    conditions: List[Tuple[str, str, Any]],
    columns: List[str]
) -> Tuple[str, List[Any]]:
    """
    동적 WHERE 절 안전하게 구성

    Args:
        conditions: [(컬럼명, 연산자, 값)] 튜플 리스트
        columns: 테이블의 실제 컬럼 리스트

    Returns:
        (WHERE 절 문자열, 파라미터 리스트)

    Example:
        where_str, params = build_dynamic_where([
            ('status', '=', 'pending'),
            ('platform', 'LIKE', 'youtube%'),
        ], columns)
    """
    ALLOWED_OPERATORS = {'=', '!=', '<', '>', '<=', '>=', 'LIKE', 'IN', 'IS'}

    clauses = []
    params = []

    for col, op, val in conditions:
        # 컬럼이 테이블에 존재하는지 확인
        if col not in columns:
            continue

        # 컬럼명 검증
        validate_column_name(col)

        # 연산자 화이트리스트 검증
        if op.upper() not in ALLOWED_OPERATORS:
            logger.warning(f"⚠️ 허용되지 않은 연산자: {op}")
            continue

        if op.upper() == 'IN' and isinstance(val, (list, tuple)):
            placeholders = ', '.join(['?'] * len(val))
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(val)
        elif op.upper() == 'IS' and val is None:
            clauses.append(f"{col} IS NULL")
        else:
            clauses.append(f"{col} {op} ?")
            params.append(val)

    where_str = " AND ".join(clauses) if clauses else "1=1"
    return where_str, params


def build_safe_order_by(
    order_col: str,
    order_dir: str,
    columns: List[str],
    default_col: str = "id"
) -> str:
    """
    안전한 ORDER BY 절 구성

    Args:
        order_col: 정렬 컬럼명
        order_dir: 정렬 방향 (ASC/DESC)
        columns: 테이블의 실제 컬럼 리스트
        default_col: 기본 정렬 컬럼

    Returns:
        안전한 ORDER BY 절 문자열
    """
    # 컬럼 검증
    if order_col and order_col in columns:
        validate_column_name(order_col)
        safe_col = order_col
    else:
        safe_col = default_col if default_col in columns else "id"

    # 정렬 방향 검증
    safe_dir = "DESC" if order_dir.upper() == "DESC" else "ASC"

    return f"ORDER BY {safe_col} {safe_dir}"
