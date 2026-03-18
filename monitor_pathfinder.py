"""Pathfinder 실행 모니터링 및 결과 확인"""
import time
import subprocess
import sys
from utils import ConfigManager

def is_pathfinder_running():
    """Pathfinder가 실행 중인지 확인"""
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq python.exe'],
            capture_output=True,
            text=True,
            shell=True
        )
        # pathfinder.py가 실행 중인지 확인
        with open('pathfinder_test_run.log', 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1]
                # 최근 5초 이내 로그가 있으면 실행 중
                return '2026-01-26' in last_line
    except Exception:
        pass
    return False

def get_completion_stats():
    """완료 통계 가져오기"""
    try:
        with open('pathfinder_test_run.log', 'r', encoding='utf-8', errors='ignore') as f:
            log_content = f.read()

        # 완료된 카테고리 수
        completed = log_content.count("Category '")
        completed_lines = [line for line in log_content.split('\n') if "finished. Secured" in line]

        # Campaign Complete 확인
        is_complete = "Campaign Complete" in log_content or "작전 완료" in log_content

        return {
            'completed_categories': len(completed_lines),
            'is_complete': is_complete,
            'last_completed': completed_lines[-1] if completed_lines else None
        }
    except Exception:
        return {'completed_categories': 0, 'is_complete': False, 'last_completed': None}

print("Pathfinder 모니터링 시작...")
print("=" * 60)

start_time = time.time()
check_interval = 30  # 30초마다 확인
max_wait_time = 600  # 최대 10분 대기

while True:
    elapsed = time.time() - start_time
    stats = get_completion_stats()

    print(f"\n[{int(elapsed)}초 경과]")
    print(f"  완료된 카테고리: {stats['completed_categories']}")
    if stats['last_completed']:
        print(f"  최근 완료: {stats['last_completed'].strip()}")

    if stats['is_complete']:
        print("\n" + "=" * 60)
        print("Pathfinder 실행 완료!")
        print("=" * 60)
        break

    if elapsed > max_wait_time:
        print(f"\n최대 대기 시간({max_wait_time}초) 초과")
        print("수동으로 확인해주세요.")
        break

    if not is_pathfinder_running() and elapsed > 60:
        print("\nPathfinder 프로세스가 종료된 것 같습니다.")
        print("로그를 확인하여 정상 완료 여부를 판단하세요.")
        break

    print(f"  다음 체크: {check_interval}초 후...")
    time.sleep(check_interval)

# 최종 DB 확인
print("\n최종 결과 확인 중...")
import sqlite3

config = ConfigManager()
conn = sqlite3.connect(config.db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN search_volume >= 10 THEN 1 END) as with_volume,
        COUNT(CASE WHEN opp_score >= 500 THEN 1 END) as kei_500,
        AVG(search_volume) as avg_vol
    FROM keyword_insights
""")

total, with_vol, kei_500, avg_vol = cursor.fetchone()
conn.close()

print("\n" + "=" * 60)
print("DATABASE 최종 결과")
print("=" * 60)
print(f"Total Keywords: {total:,}")
print(f"With Volume (>=10): {with_vol:,} ({with_vol/max(1,total)*100:.1f}%)")
print(f"KEI 500+: {kei_500:,} ({kei_500/max(1,total)*100:.1f}%)")
print(f"Avg Search Volume: {int(avg_vol):,}")
print("=" * 60)

if total > 0:
    print("\n다음 단계:")
    print("  python test_pathfinder_improvements.py  # 상세 검증")
    print("  streamlit run dashboard_ultra.py  # Dashboard 확인")
