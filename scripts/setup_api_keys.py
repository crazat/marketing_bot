#!/usr/bin/env python3
"""
API 키 설정 도구
Instagram과 TikTok API 키를 secrets.json에 쉽게 추가할 수 있습니다.
"""

import sys
import os
import json
from pathlib import Path

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
SECRETS_FILE = PROJECT_ROOT / "config" / "secrets.json"


def print_header(title):
    """헤더 출력"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_section(title):
    """섹션 출력"""
    print(f"\n{'-'*70}")
    print(f"  {title}")
    print(f"{'-'*70}\n")


def load_secrets():
    """secrets.json 로드"""
    if not SECRETS_FILE.exists():
        print(f"⚠️  secrets.json 파일이 없습니다: {SECRETS_FILE}")
        return {}

    try:
        with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ secrets.json 로드 실패: {e}")
        return {}


def save_secrets(secrets):
    """secrets.json 저장"""
    try:
        # 백업 생성
        if SECRETS_FILE.exists():
            backup_file = SECRETS_FILE.with_suffix('.json.backup')
            import shutil
            shutil.copy2(SECRETS_FILE, backup_file)
            print(f"✅ 백업 생성: {backup_file.name}")

        # 저장
        with open(SECRETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(secrets, f, indent=4, ensure_ascii=False)

        print(f"✅ secrets.json 저장 완료!")
        return True
    except Exception as e:
        print(f"❌ 저장 실패: {e}")
        return False


def check_instagram_keys(secrets):
    """Instagram 키 확인"""
    required_keys = [
        'INSTAGRAM_APP_ID',
        'INSTAGRAM_APP_SECRET',
        'INSTAGRAM_ACCESS_TOKEN',
        'INSTAGRAM_BUSINESS_ACCOUNT_ID'
    ]

    missing = [key for key in required_keys if key not in secrets or not secrets[key]]

    if not missing:
        print("✅ Instagram API 키가 모두 설정되어 있습니다.")
        return True
    else:
        print(f"⚠️  누락된 키: {', '.join(missing)}")
        return False


def check_tiktok_keys(secrets):
    """TikTok 키 확인"""
    required_keys = [
        'TIKTOK_CLIENT_KEY',
        'TIKTOK_CLIENT_SECRET'
    ]

    missing = [key for key in required_keys if key not in secrets or not secrets[key]]

    if not missing:
        print("✅ TikTok API 키가 모두 설정되어 있습니다.")
        return True
    else:
        print(f"⚠️  누락된 키: {', '.join(missing)}")
        return False


def setup_instagram(secrets):
    """Instagram API 키 설정"""
    print_section("📸 Instagram Graph API 키 입력")

    print("📖 가이드: docs/INSTAGRAM_SETUP_GUIDE.md 참조")
    print()
    print("4개의 키가 필요합니다:")
    print("  1. INSTAGRAM_APP_ID")
    print("  2. INSTAGRAM_APP_SECRET")
    print("  3. INSTAGRAM_ACCESS_TOKEN (장기 토큰)")
    print("  4. INSTAGRAM_BUSINESS_ACCOUNT_ID")
    print()

    # 기존 값 확인
    existing = {
        'INSTAGRAM_APP_ID': secrets.get('INSTAGRAM_APP_ID', ''),
        'INSTAGRAM_APP_SECRET': secrets.get('INSTAGRAM_APP_SECRET', ''),
        'INSTAGRAM_ACCESS_TOKEN': secrets.get('INSTAGRAM_ACCESS_TOKEN', ''),
        'INSTAGRAM_BUSINESS_ACCOUNT_ID': secrets.get('INSTAGRAM_BUSINESS_ACCOUNT_ID', '')
    }

    for key, current_value in existing.items():
        if current_value:
            print(f"현재 {key}: {current_value[:20]}... (설정됨)")
            response = input(f"  변경하시겠습니까? (y/N): ").strip().lower()
            if response != 'y':
                continue

        value = input(f"\n{key} 입력: ").strip()
        if value:
            secrets[key] = value
            print(f"  ✅ 저장됨")
        else:
            print(f"  ⚠️  건너뜀")

    return secrets


def setup_tiktok(secrets):
    """TikTok API 키 설정"""
    print_section("🎵 TikTok Research API 키 입력")

    print("⚠️  주의: TikTok Research API는 승인이 필요합니다.")
    print("   학술 연구자, 비영리 단체만 승인 가능")
    print()
    print("📖 가이드: docs/TIKTOK_SETUP_GUIDE.md 참조")
    print()
    print("2개의 키가 필요합니다:")
    print("  1. TIKTOK_CLIENT_KEY")
    print("  2. TIKTOK_CLIENT_SECRET")
    print()

    response = input("TikTok Research API 승인을 받으셨습니까? (y/N): ").strip().lower()
    if response != 'y':
        print()
        print("💡 대안: TikTok Creative Center 크롤러를 사용하세요 (승인 불필요)")
        print("   python3 scrapers/tiktok_creative_center.py --trends")
        print()
        return secrets

    # 기존 값 확인
    existing = {
        'TIKTOK_CLIENT_KEY': secrets.get('TIKTOK_CLIENT_KEY', ''),
        'TIKTOK_CLIENT_SECRET': secrets.get('TIKTOK_CLIENT_SECRET', '')
    }

    for key, current_value in existing.items():
        if current_value:
            print(f"현재 {key}: {current_value[:20]}... (설정됨)")
            response = input(f"  변경하시겠습니까? (y/N): ").strip().lower()
            if response != 'y':
                continue

        value = input(f"\n{key} 입력: ").strip()
        if value:
            secrets[key] = value
            print(f"  ✅ 저장됨")
        else:
            print(f"  ⚠️  건너뜀")

    return secrets


def test_instagram():
    """Instagram API 테스트"""
    print_section("🧪 Instagram API 테스트")

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from scrapers.instagram_api_client import InstagramGraphAPI

        api = InstagramGraphAPI()

        if not api.is_configured():
            print("❌ API 키가 설정되지 않았습니다.")
            return False

        result = api.test_connection()

        if result['success']:
            print(f"✅ {result['message']}")
            if result.get('account'):
                account = result['account']
                print(f"\n계정 정보:")
                print(f"  Username: @{account.get('username', 'N/A')}")
                print(f"  Followers: {account.get('followers_count', 'N/A'):,}")
                print(f"  Media: {account.get('media_count', 'N/A')}")
            return True
        else:
            print(f"❌ {result['message']}")
            return False
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        return False


def test_tiktok():
    """TikTok API 테스트"""
    print_section("🧪 TikTok API 테스트")

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from scrapers.tiktok_api_client import TikTokAPIStatus

        result = TikTokAPIStatus.test_connection()

        if result['success']:
            print(f"✅ {result['message']}")
            return True
        else:
            print(f"❌ {result['message']}")
            return False
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        return False


def main():
    """메인 함수"""
    print_header("🔧 API 키 설정 도구")

    print("이 도구는 Instagram과 TikTok API 키를 secrets.json에 추가합니다.")
    print()

    # secrets.json 로드
    secrets = load_secrets()

    # 현재 상태 확인
    print_section("📊 현재 설정 상태")

    instagram_ok = check_instagram_keys(secrets)
    tiktok_ok = check_tiktok_keys(secrets)

    print()

    # 메뉴
    while True:
        print_section("📋 메뉴")
        print("1. Instagram API 키 설정")
        print("2. TikTok API 키 설정")
        print("3. Instagram API 테스트")
        print("4. TikTok API 테스트")
        print("5. 현재 설정 확인")
        print("0. 종료")
        print()

        choice = input("선택 (0-5): ").strip()

        if choice == '1':
            secrets = setup_instagram(secrets)
            if save_secrets(secrets):
                print("\n💡 테스트를 실행하려면 메뉴에서 '3'을 선택하세요.")

        elif choice == '2':
            secrets = setup_tiktok(secrets)
            if save_secrets(secrets):
                print("\n💡 테스트를 실행하려면 메뉴에서 '4'를 선택하세요.")

        elif choice == '3':
            test_instagram()

        elif choice == '4':
            test_tiktok()

        elif choice == '5':
            secrets = load_secrets()
            print_section("📊 현재 설정 상태")
            check_instagram_keys(secrets)
            check_tiktok_keys(secrets)

        elif choice == '0':
            print("\n👋 종료합니다.")
            break

        else:
            print("\n❌ 잘못된 선택입니다.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
