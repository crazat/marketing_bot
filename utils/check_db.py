#!/usr/bin/env python3
"""
DB 검증 스크립트
터미널에서 실행한 스크립트의 DB 저장 여부를 확인합니다.
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Fallback: 색상 없이 출력
    class Fore:
        GREEN = RED = YELLOW = BLUE = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "marketing_data.db"


def get_db_connection() -> sqlite3.Connection:
    """DB 연결 생성"""
    if not DB_PATH.exists():
        print(f"{Fore.RED}❌ DB 파일을 찾을 수 없습니다: {DB_PATH}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"{Fore.RED}❌ DB 연결 실패: {e}")
        sys.exit(1)


def format_number(num: int) -> str:
    """숫자를 천 단위 구분자로 포맷"""
    return f"{num:,}"


def print_header(text: str):
    """헤더 출력"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{text}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")


def print_success(text: str):
    """성공 메시지 출력"""
    print(f"{Fore.GREEN}✓ {text}")


def print_error(text: str):
    """에러 메시지 출력"""
    print(f"{Fore.RED}✗ {text}")


def print_warning(text: str):
    """경고 메시지 출력"""
    print(f"{Fore.YELLOW}⚠ {text}")


def print_info(text: str):
    """정보 메시지 출력"""
    print(f"{Fore.BLUE}ℹ {text}")


def check_table_count(conn: sqlite3.Connection, table: str, since_minutes: int = 0) -> Tuple[int, Dict]:
    """테이블의 데이터 개수 확인"""
    cursor = conn.cursor()

    try:
        # 전체 개수
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_count = cursor.fetchone()[0]

        # 최근 N분 이내 추가된 데이터
        recent_count = 0
        if since_minutes > 0:
            time_threshold = datetime.now() - timedelta(minutes=since_minutes)
            time_str = time_threshold.strftime('%Y-%m-%d %H:%M:%S')

            # 테이블별로 timestamp 컬럼명이 다를 수 있음
            timestamp_columns = ['created_at', 'scanned_date', 'discovered_at', 'added_at']
            for col in timestamp_columns:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} >= ?", (time_str,))
                    recent_count = cursor.fetchone()[0]
                    break
                except sqlite3.OperationalError:
                    continue

        # 추가 통계 (테이블별 특화)
        stats = {}
        if table == 'keyword_insights':
            # 등급별 분포
            cursor.execute("SELECT grade, COUNT(*) FROM keyword_insights GROUP BY grade")
            stats['grades'] = {row[0]: row[1] for row in cursor.fetchall()}

        elif table == 'viral_targets':
            # 플랫폼별 분포
            cursor.execute("SELECT platform, COUNT(*) FROM viral_targets GROUP BY platform")
            stats['platforms'] = {row[0]: row[1] for row in cursor.fetchall()}

        elif table == 'rank_history':
            # 상태별 분포
            cursor.execute("SELECT status, COUNT(*) FROM rank_history GROUP BY status")
            stats['statuses'] = {row[0]: row[1] for row in cursor.fetchall()}

        elif table == 'competitor_weaknesses':
            # 약점 유형별 분포
            cursor.execute("SELECT weakness_type, COUNT(*) FROM competitor_weaknesses GROUP BY weakness_type")
            stats['types'] = {row[0]: row[1] for row in cursor.fetchall()}

        return total_count, recent_count, stats

    except sqlite3.OperationalError as e:
        print_error(f"테이블 '{table}' 조회 실패: {e}")
        return 0, 0, {}


def show_table_info(conn: sqlite3.Connection, table: str, since_minutes: int = 0):
    """테이블 정보 출력"""
    print_header(f"테이블: {table}")

    total, recent, stats = check_table_count(conn, table, since_minutes)

    print_info(f"전체 데이터: {Fore.WHITE}{Style.BRIGHT}{format_number(total)}개")

    if since_minutes > 0:
        if recent > 0:
            print_success(f"최근 {since_minutes}분 이내: {Fore.GREEN}{Style.BRIGHT}{format_number(recent)}개")
        else:
            print_warning(f"최근 {since_minutes}분 이내: 0개")

    # 추가 통계 출력
    if stats:
        print(f"\n{Fore.MAGENTA}📊 분포:")
        for category, items in stats.items():
            print(f"  {Fore.CYAN}{category}:")
            for key, count in items.items():
                print(f"    {Fore.WHITE}{key}: {Fore.YELLOW}{format_number(count)}개")


def show_scan_runs(conn: sqlite3.Connection, limit: int = 10):
    """스캔 실행 기록 조회"""
    print_header("최근 스캔 실행 기록")

    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT mode, status, grade_s_count, grade_a_count, grade_b_count, grade_c_count,
                   started_at, completed_at
            FROM scan_runs
            ORDER BY started_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()

        if not rows:
            print_warning("스캔 실행 기록이 없습니다.")
            return

        for row in rows:
            mode = row[0]
            status = row[1]
            s_count = row[2] or 0
            a_count = row[3] or 0
            b_count = row[4] or 0
            c_count = row[5] or 0
            started = row[6]
            completed = row[7]

            status_color = Fore.GREEN if status == 'completed' else Fore.YELLOW
            print(f"\n{Fore.CYAN}모드: {Fore.WHITE}{mode}")
            print(f"{Fore.CYAN}상태: {status_color}{status}")
            print(f"{Fore.CYAN}등급: {Fore.RED}S:{s_count} {Fore.YELLOW}A:{a_count} {Fore.GREEN}B:{b_count} {Fore.BLUE}C:{c_count}")
            print(f"{Fore.CYAN}시작: {Fore.WHITE}{started}")
            if completed:
                print(f"{Fore.CYAN}완료: {Fore.WHITE}{completed}")

    except sqlite3.OperationalError as e:
        print_error(f"scan_runs 테이블 조회 실패: {e}")


def show_summary(conn: sqlite3.Connection):
    """전체 요약 출력"""
    print_header("DB 전체 요약")

    tables = [
        'keyword_insights',
        'viral_targets',
        'rank_history',
        'competitor_weaknesses',
        'leads',
        'scan_runs',
    ]

    for table in tables:
        total, _, _ = check_table_count(conn, table)
        if total > 0:
            print_success(f"{table}: {Fore.WHITE}{Style.BRIGHT}{format_number(total)}개")
        else:
            print_warning(f"{table}: 0개")


def verify_scan(conn: sqlite3.Connection, scan_type: str):
    """특정 스캔 유형의 실행 결과 검증"""
    print_header(f"{scan_type.upper()} 스캔 검증")

    if scan_type == 'pathfinder':
        # keyword_insights 테이블 확인
        total, recent, stats = check_table_count(conn, 'keyword_insights', since_minutes=30)

        if total == 0:
            print_error("keyword_insights 테이블에 데이터가 없습니다.")
            return

        print_success(f"총 키워드: {format_number(total)}개")

        if 'grades' in stats:
            print(f"\n{Fore.MAGENTA}📊 등급별 분포:")
            for grade in ['S', 'A', 'B', 'C']:
                count = stats['grades'].get(grade, 0)
                color = {
                    'S': Fore.RED,
                    'A': Fore.YELLOW,
                    'B': Fore.GREEN,
                    'C': Fore.BLUE
                }.get(grade, Fore.WHITE)
                print(f"  {color}{grade}등급: {format_number(count)}개")

        # scan_runs 기록 확인
        show_scan_runs(conn, limit=3)

    elif scan_type == 'viral':
        total, recent, stats = check_table_count(conn, 'viral_targets', since_minutes=30)

        if total == 0:
            print_error("viral_targets 테이블에 데이터가 없습니다.")
            return

        print_success(f"총 바이럴 타겟: {format_number(total)}개")

        if 'platforms' in stats:
            print(f"\n{Fore.MAGENTA}📊 플랫폼별 분포:")
            for platform, count in stats['platforms'].items():
                print(f"  {Fore.WHITE}{platform}: {Fore.YELLOW}{format_number(count)}개")


def main():
    parser = argparse.ArgumentParser(description='DB 검증 스크립트')
    parser.add_argument('--table', type=str, help='확인할 테이블명')
    parser.add_argument('--since', type=int, help='최근 N분 이내 데이터만 확인')
    parser.add_argument('--latest', type=int, help='최근 N개 레코드 확인')
    parser.add_argument('--scan-runs', action='store_true', help='스캔 실행 기록 확인')
    parser.add_argument('--summary', action='store_true', help='전체 요약')
    parser.add_argument('--verify-scan', type=str, choices=['pathfinder', 'viral'], help='스캔 검증')

    args = parser.parse_args()

    # DB 연결
    conn = get_db_connection()

    try:
        if args.summary:
            show_summary(conn)
        elif args.scan_runs:
            show_scan_runs(conn, limit=args.latest or 10)
        elif args.verify_scan:
            verify_scan(conn, args.verify_scan)
        elif args.table:
            show_table_info(conn, args.table, since_minutes=args.since or 0)
        else:
            parser.print_help()

    finally:
        conn.close()


if __name__ == '__main__':
    main()
