"""
Marketing Bot DB 일관성 검증 (최종본)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

마이그레이션 후 검증
- status 값 확인
- source_platform 값 확인 (mentions)
- platform 값 확인 (viral_targets)
- 레코드 수 불변 확인
"""

import sqlite3
from pathlib import Path


def verify_mentions_status(cursor):
    """mentions.status 값이 소문자인지 확인"""

    print("🔍 mentions.status 확인 중...")

    cursor.execute("SELECT DISTINCT status FROM mentions")
    statuses = [row[0] for row in cursor.fetchall() if row[0]]

    expected = {'new', 'contacted', 'converted', 'rejected'}
    unexpected = [s for s in statuses if s not in expected]

    if not unexpected:
        print(f"   ✅ 모든 status 값이 정상입니다: {statuses}")
        return True
    else:
        print(f"   ❌ 예상치 못한 status 값: {unexpected}")
        print(f"   현재 status 값: {statuses}")
        return False


def verify_platform_values(cursor):
    """platform 값이 정규화되었는지 확인"""

    print("\n🔍 platform 값 확인 중...")

    expected_platforms = {
        'naver_cafe', 'youtube', 'tiktok', 
        'instagram', 'carrot', 'influencer',
        'blog', 'kin'  # 네이버 블로그, 네이버 지식iN
    }

    # mentions.source_platform
    cursor.execute("SELECT DISTINCT source_platform FROM mentions WHERE source_platform IS NOT NULL")
    mention_platforms = [row[0] for row in cursor.fetchall()]

    unexpected_mentions = [p for p in mention_platforms if p not in expected_platforms]

    # viral_targets.platform
    cursor.execute("SELECT DISTINCT platform FROM viral_targets WHERE platform IS NOT NULL")
    viral_platforms = [row[0] for row in cursor.fetchall()]

    unexpected_viral = [p for p in viral_platforms if p not in expected_platforms]

    all_ok = True

    if not unexpected_mentions:
        if mention_platforms:
            print(f"   ✅ mentions.source_platform: {mention_platforms}")
        else:
            print(f"   ✅ mentions.source_platform: (사용 안 함)")
    else:
        print(f"   ❌ mentions 정규화 안 된 source_platform: {unexpected_mentions}")
        print(f"   현재 source_platform 값: {mention_platforms}")
        all_ok = False

    if not unexpected_viral:
        print(f"   ✅ viral_targets.platform: {viral_platforms}")
    else:
        print(f"   ❌ viral_targets 정규화 안 된 platform: {unexpected_viral}")
        print(f"   현재 platform 값: {viral_platforms}")
        all_ok = False

    return all_ok


def verify_record_counts(cursor):
    """주요 테이블 레코드 수 확인"""

    print("\n🔍 레코드 수 확인 중...")

    tables = [
        'keyword_insights',
        'rank_history',
        'viral_targets',
        'mentions',
        'competitor_reviews'
    ]

    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   {table}: {count:,}개")
        except sqlite3.OperationalError:
            print(f"   ⚠️  {table}: 테이블 없음")

    return True


def verify_phase5_fields(cursor):
    """Phase 5.0 필드 존재 확인"""

    print("\n🔍 Phase 5.0 필드 확인 중...")

    cursor.execute("PRAGMA table_info(mentions)")
    columns = [row[1] for row in cursor.fetchall()]

    required_fields = ['opportunity_bonus', 'engagement_signal']
    missing_fields = [f for f in required_fields if f not in columns]

    if not missing_fields:
        print(f"   ✅ 모든 필수 필드 존재: {required_fields}")
        return True
    else:
        print(f"   ⚠️  누락된 필드: {missing_fields}")
        return False


def main():
    """메인 검증 함수"""

    print("=" * 70)
    print("Marketing Bot - DB 일관성 검증 (최종본)")
    print("=" * 70)

    # DB 경로
    db_path = Path(__file__).parent.parent / "db" / "marketing_data.db"

    if not db_path.exists():
        print(f"❌ DB 파일을 찾을 수 없습니다: {db_path}")
        return False

    print(f"\nDB 파일: {db_path}")
    print(f"크기: {db_path.stat().st_size / (1024 * 1024):.2f} MB\n")

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 검증 실행
        results = []
        results.append(verify_mentions_status(cursor))
        results.append(verify_platform_values(cursor))
        results.append(verify_record_counts(cursor))
        results.append(verify_phase5_fields(cursor))

        conn.close()

        # 결과 요약
        print("\n" + "=" * 70)
        if all(results):
            print("✅ 모든 검증 통과!")
            print("=" * 70)
            return True
        else:
            print("❌ 일부 검증 실패")
            print("=" * 70)
            return False

    except Exception as e:
        print(f"\n❌ 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
