#!/usr/bin/env python3
"""
Marketing Bot Test Runner
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

모든 테스트를 순차적으로 실행합니다.

사용법:
    python run_tests.py          # 모든 테스트 실행
    python run_tests.py --phase4 # Phase 4 테스트만 실행
    python run_tests.py --unit   # 단위 테스트만 실행
"""

import sys
import os
import subprocess
import argparse
from datetime import datetime

# 색상 코드 (Windows CMD 호환)
try:
    import colorama
    colorama.init()
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
except ImportError:
    GREEN = ""
    RED = ""
    YELLOW = ""
    RESET = ""

# 테스트 정의
TEST_SUITES = {
    "unit": {
        "name": "Unit Tests",
        "tests": [
            ("tests/test_unit.py", "기본 유닛 테스트"),
        ]
    },
    "integration": {
        "name": "Integration Tests",
        "tests": [
            ("tests/test_integration.py", "통합 테스트"),
        ]
    },
    "phase0": {
        "name": "Phase 0 Tests",
        "tests": [
            ("tests/test_phase0.py", "Phase 0 기초 테스트"),
        ]
    },
    "phase1": {
        "name": "Phase 1 Tests",
        "tests": [
            ("tests/test_phase1.py", "Phase 1 DB 최적화 테스트"),
        ]
    },
    "phase2": {
        "name": "Phase 2 Tests",
        "tests": [
            ("tests/test_phase2.py", "Phase 2 프론트엔드 최적화 테스트"),
        ]
    },
    "phase3": {
        "name": "Phase 3 Tests",
        "tests": [
            ("tests/test_phase3.py", "Phase 3 스크래퍼 병렬화 테스트"),
        ]
    },
    "phase4": {
        "name": "Phase 4 Scheduling Tests",
        "tests": [
            ("tests/test_phase4_scheduling.py", "Phase 4 스케줄링 자동화 테스트"),
        ]
    },
    "scrapers": {
        "name": "Scraper Tests",
        "tests": [
            ("tests/test_scrapers.py", "스크래퍼 테스트"),
        ]
    },
    "utilities": {
        "name": "Utility Tests",
        "tests": [
            ("tests/test_utilities.py", "유틸리티 테스트"),
        ]
    }
}


def run_test(test_file: str, description: str, verbose: bool = False) -> tuple:
    """단일 테스트 파일 실행"""
    python_cmd = "python3" if os.name != "nt" else "python"

    try:
        result = subprocess.run(
            [python_cmd, test_file],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

        success = result.returncode == 0

        if verbose or not success:
            return success, result.stdout + result.stderr
        else:
            # 마지막 몇 줄만 반환
            lines = result.stdout.strip().split('\n')
            summary = '\n'.join(lines[-5:])
            return success, summary

    except subprocess.TimeoutExpired:
        return False, "TIMEOUT: Test took too long (>120s)"
    except FileNotFoundError:
        return False, f"FILE NOT FOUND: {test_file}"
    except Exception as e:
        return False, f"ERROR: {str(e)}"


def print_header():
    print("=" * 70)
    print("Marketing Bot Test Runner")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")
    print("=" * 70)
    print()


def print_suite_header(suite_name: str):
    print(f"\n{YELLOW}━━━ {suite_name} ━━━{RESET}")


def print_result(description: str, success: bool, details: str = None, verbose: bool = False):
    icon = f"{GREEN}✅{RESET}" if success else f"{RED}❌{RESET}"
    status = "PASS" if success else "FAIL"

    print(f"  {icon} {description}: {status}")

    if verbose and details:
        for line in details.strip().split('\n')[-5:]:
            print(f"      {line}")


def main():
    parser = argparse.ArgumentParser(description="Marketing Bot Test Runner")
    parser.add_argument("--phase4", action="store_true", help="Run Phase 4 tests only")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--suite", type=str, help="Run specific suite (unit, integration, phase0-4, scrapers, utilities)")
    args = parser.parse_args()

    print_header()

    # 실행할 테스트 스위트 결정
    suites_to_run = []

    if args.suite:
        if args.suite in TEST_SUITES:
            suites_to_run = [args.suite]
        else:
            print(f"{RED}Unknown suite: {args.suite}{RESET}")
            print(f"Available suites: {', '.join(TEST_SUITES.keys())}")
            return 1
    elif args.phase4:
        suites_to_run = ["phase4"]
    elif args.unit:
        suites_to_run = ["unit"]
    elif args.all:
        suites_to_run = list(TEST_SUITES.keys())
    else:
        # 기본: Phase 4만 실행 (최신 개발 중인 모듈)
        suites_to_run = ["phase4"]

    # 결과 수집
    all_results = []
    total_tests = 0
    total_passed = 0

    for suite_key in suites_to_run:
        suite = TEST_SUITES[suite_key]
        print_suite_header(suite["name"])

        for test_file, description in suite["tests"]:
            if not os.path.exists(test_file):
                print(f"  ⚠️  {description}: FILE NOT FOUND ({test_file})")
                continue

            total_tests += 1
            success, details = run_test(test_file, description, args.verbose)

            if success:
                total_passed += 1

            print_result(description, success, details, args.verbose)
            all_results.append((description, success))

    # 요약
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Total: {total_tests}")
    print(f"Passed: {GREEN}{total_passed}{RESET}")
    print(f"Failed: {RED}{total_tests - total_passed}{RESET}")
    print()

    if total_passed == total_tests:
        print(f"{GREEN}✅ All tests passed!{RESET}")
        return 0
    else:
        print(f"{RED}❌ Some tests failed.{RESET}")
        print("\nFailed tests:")
        for desc, success in all_results:
            if not success:
                print(f"  - {desc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
