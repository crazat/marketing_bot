"""
Marketing Bot DB 일관성 마이그레이션 (수정본)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 2: 데이터베이스 일관성 개선
- mentions.status 소문자 통일
- source_platform 정규화 (mentions)
- platform 정규화 (viral_targets)
- 트랜잭션 사용으로 안전성 보장
"""

import sqlite3
from pathlib import Path
from datetime import datetime


def migrate_mentions_status(cursor):
    """mentions.status 소문자 통일 (New → new)"""

    print("📝 mentions.status 소문자 통일 중...")

    # 현재 상태 확인
    cursor.execute("SELECT DISTINCT status FROM mentions")
    current_statuses = [row[0] for row in cursor.fetchall()]
    print(f"   현재 status 값: {current_statuses}")

    # 소문자로 변환
    cursor.execute("UPDATE mentions SET status = LOWER(status)")
    affected = cursor.rowcount

    # 결과 확인
    cursor.execute("SELECT DISTINCT status FROM mentions")
    new_statuses = [row[0] for row in cursor.fetchall()]

    print(f"   ✅ {affected}개 레코드 업데이트")
    print(f"   새 status 값: {new_statuses}")


def migrate_platform_normalization(cursor):
    """platform 값 정규화 (한글 → 영문)"""

    print("\n📝 platform 값 정규화 중...")

    # 매핑 테이블
    mapping = {
        '네이버 카페': 'naver_cafe',
        '네이버카페': 'naver_cafe',
        'naver cafe': 'naver_cafe',
        'cafe': 'naver_cafe',
        '유튜브': 'youtube',
        'Youtube': 'youtube',
        'YouTube': 'youtube',
        '틱톡': 'tiktok',
        'TikTok': 'tiktok',
        '인스타그램': 'instagram',
        'Instagram': 'instagram',
        '당근마켓': 'carrot',
        '당근': 'carrot',
        '인플루언서': 'influencer',
        'Influencer': 'influencer',
    }

    total_affected = 0

    # 1. mentions.source_platform 정규화
    print("\n   [mentions.source_platform]")
    for old_value, new_value in mapping.items():
        cursor.execute(
            "UPDATE mentions SET source_platform = ? WHERE source_platform = ?",
            (new_value, old_value)
        )
        affected = cursor.rowcount
        if affected > 0:
            print(f"      '{old_value}' → '{new_value}' ({affected}개)")
            total_affected += affected

    # 결과 확인
    cursor.execute("SELECT DISTINCT source_platform FROM mentions WHERE source_platform IS NOT NULL")
    mention_platforms = [row[0] for row in cursor.fetchall()]
    print(f"      정규화 후 값: {mention_platforms}")

    # 2. viral_targets.platform 정규화
    print("\n   [viral_targets.platform]")
    for old_value, new_value in mapping.items():
        cursor.execute(
            "UPDATE viral_targets SET platform = ? WHERE platform = ?",
            (new_value, old_value)
        )
        affected = cursor.rowcount
        if affected > 0:
            print(f"      '{old_value}' → '{new_value}' ({affected}개)")
            total_affected += affected

    # 결과 확인
    cursor.execute("SELECT DISTINCT platform FROM viral_targets WHERE platform IS NOT NULL")
    viral_platforms = [row[0] for row in cursor.fetchall()]
    print(f"      정규화 후 값: {viral_platforms}")

    print(f"\n   ✅ 총 {total_affected}개 레코드 정규화")


def migrate_phase5_defaults(cursor):
    """Phase 5.0 필드 기본값 설정"""

    print("\n📝 Phase 5.0 필드 기본값 설정 중...")

    # mentions 테이블에 필요한 컬럼 추가 (없으면)
    cursor.execute("PRAGMA table_info(mentions)")
    columns = [row[1] for row in cursor.fetchall()]

    new_columns = []

    if 'opportunity_bonus' not in columns:
        cursor.execute("ALTER TABLE mentions ADD COLUMN opportunity_bonus INTEGER DEFAULT 0")
        new_columns.append('opportunity_bonus')

    if 'engagement_signal' not in columns:
        cursor.execute("ALTER TABLE mentions ADD COLUMN engagement_signal TEXT DEFAULT 'passive'")
        new_columns.append('engagement_signal')

    if new_columns:
        print(f"   ✅ 컬럼 추가: {', '.join(new_columns)}")
    else:
        print(f"   ✅ 모든 컬럼 이미 존재함")


def verify_migration(cursor):
    """마이그레이션 검증"""

    print("\n🔍 마이그레이션 검증 중...")

    # 1. status 값 확인
    cursor.execute("SELECT DISTINCT status FROM mentions")
    statuses = [row[0] for row in cursor.fetchall()]
    expected_statuses = {'new', 'contacted', 'converted', 'rejected'}

    if all(s in expected_statuses or (s and s.islower()) for s in statuses if s):
        print(f"   ✅ status 값 정상: {statuses}")
    else:
        print(f"   ⚠️  예상치 못한 status 값: {statuses}")

    # 2. source_platform 값 확인
    cursor.execute("SELECT DISTINCT source_platform FROM mentions WHERE source_platform IS NOT NULL")
    platforms = [row[0] for row in cursor.fetchall()]
    expected_platforms = {'naver_cafe', 'youtube', 'tiktok', 'instagram', 'carrot', 'influencer'}

    unexpected = [p for p in platforms if p not in expected_platforms and p is not None]
    if not unexpected:
        print(f"   ✅ mentions.source_platform 정규화 완료: {platforms}")
    else:
        print(f"   ⚠️  정규화되지 않은 source_platform: {unexpected}")

    # 3. viral_targets.platform 값 확인
    cursor.execute("SELECT DISTINCT platform FROM viral_targets WHERE platform IS NOT NULL")
    viral_platforms = [row[0] for row in cursor.fetchall()]

    unexpected_viral = [p for p in viral_platforms if p not in expected_platforms and p is not None]
    if not unexpected_viral:
        print(f"   ✅ viral_targets.platform 정규화 완료: {viral_platforms}")
    else:
        print(f"   ⚠️  정규화되지 않은 platform: {unexpected_viral}")


def main():
    """메인 실행 함수"""

    print("=" * 70)
    print("Marketing Bot - DB 일관성 마이그레이션 (수정본)")
    print("=" * 70)

    # DB 경로
    db_path = Path(__file__).parent.parent / "db" / "marketing_data.db"

    if not db_path.exists():
        print(f"❌ DB 파일을 찾을 수 없습니다: {db_path}")
        return

    print(f"\nDB 파일: {db_path}")
    print(f"크기: {db_path.stat().st_size / (1024 * 1024):.2f} MB\n")

    try:
        # 트랜잭션 시작
        conn = sqlite3.connect(str(db_path))
        conn.execute("BEGIN TRANSACTION")
        cursor = conn.cursor()

        # 마이그레이션 실행
        migrate_mentions_status(cursor)
        migrate_platform_normalization(cursor)
        migrate_phase5_defaults(cursor)

        # 검증
        verify_migration(cursor)

        # 커밋
        conn.commit()
        print("\n✅ 트랜잭션 커밋 완료!")

    except Exception as e:
        print(f"\n❌ 마이그레이션 실패: {e}")
        print("롤백 중...")
        conn.rollback()
        raise

    finally:
        conn.close()

    print("\n" + "=" * 70)
    print("✅ 마이그레이션 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
