#!/usr/bin/env python3
"""
Phase 4 API Live Test Script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

실제 백엔드 서버가 실행 중일 때 API 엔드포인트를 테스트합니다.

사용 방법:
    1. 먼저 백엔드 서버 실행: build_and_run.bat
    2. 테스트 실행: python tests/test_phase4_api_live.py

테스트 대상 API:
    - GET  /api/scheduler/health
    - POST /api/scheduler/apply-recommendations
    - GET  /api/scheduler/peak-hours
    - GET  /api/scheduler/keyword-priorities
    - GET  /api/scheduler/auto-rescan/status
    - GET  /api/scheduler/lead-reminders/status
    - GET  /api/scheduler/lead-transitions/preview
"""

import requests
import json
import sys
from datetime import datetime

# 서버 URL
BASE_URL = "http://localhost:8000"

# 테스트 결과 저장
results = []


def check_endpoint(method: str, endpoint: str, expected_keys: list = None, data: dict = None):
    """API 엔드포인트 테스트"""
    url = f"{BASE_URL}{endpoint}"

    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")

        success = response.status_code == 200
        response_data = response.json() if success else {}

        # 예상 키 검증
        if success and expected_keys:
            for key in expected_keys:
                if key not in response_data:
                    success = False
                    break

        results.append({
            "endpoint": endpoint,
            "method": method,
            "status": response.status_code,
            "success": success,
            "has_data": bool(response_data)
        })

        return success, response_data

    except requests.exceptions.ConnectionError:
        results.append({
            "endpoint": endpoint,
            "method": method,
            "status": "CONNECTION_ERROR",
            "success": False,
            "has_data": False
        })
        return False, {"error": "Connection refused. Is the server running?"}

    except Exception as e:
        results.append({
            "endpoint": endpoint,
            "method": method,
            "status": "ERROR",
            "success": False,
            "has_data": False
        })
        return False, {"error": str(e)}


def print_header():
    print("=" * 70)
    print("Phase 4 API Live Test")
    print("=" * 70)
    print(f"Server URL: {BASE_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 70)
    print()


def print_result(name: str, success: bool, data: dict = None, show_data: bool = False):
    icon = "✅" if success else "❌"
    print(f"{icon} {name}")

    if show_data and data:
        print(f"   Response: {json.dumps(data, indent=2, ensure_ascii=False)[:200]}...")


def main():
    print_header()

    # 1. 스케줄러 건강도 조회
    print("📊 Testing Scheduler Health API...")
    success, data = check_endpoint("GET", "/api/scheduler/health", ["success"])
    print_result("GET /api/scheduler/health", success)
    if success and "data" in data:
        summary = data.get("data", {}).get("summary", {})
        print(f"   - Total Jobs: {summary.get('total_jobs', 'N/A')}")
        print(f"   - Success Rate: {summary.get('overall_success_rate', 'N/A')}%")
    print()

    # 2. 피크 시간대 분석
    print("⏰ Testing Peak Hours API...")
    success, data = check_endpoint("GET", "/api/scheduler/peak-hours", ["success"])
    print_result("GET /api/scheduler/peak-hours", success)
    print()

    # 3. 키워드 우선순위 조회
    print("🔑 Testing Keyword Priorities API...")
    success, data = check_endpoint("GET", "/api/scheduler/keyword-priorities", ["success"])
    print_result("GET /api/scheduler/keyword-priorities", success)
    if success and "data" in data:
        summary = data.get("data", {})
        print(f"   - Total Keywords: {summary.get('total_keywords', 'N/A')}")
        counts = summary.get("counts", {})
        print(f"   - Critical: {counts.get('critical', 0)}, High: {counts.get('high', 0)}, Medium: {counts.get('medium', 0)}, Low: {counts.get('low', 0)}")
    print()

    # 4. 자동 재스캔 상태
    print("🔄 Testing Auto-Rescan Status API...")
    success, data = check_endpoint("GET", "/api/scheduler/auto-rescan/status", ["success"])
    print_result("GET /api/scheduler/auto-rescan/status", success)
    if success and "data" in data:
        status = data.get("data", {})
        print(f"   - Min Drop: {status.get('min_drop', 'N/A')}")
        print(f"   - Cooldown: {status.get('cooldown_minutes', 'N/A')} min")
        print(f"   - Active Cooldowns: {len(status.get('active_cooldowns', {}))}")
    print()

    # 5. 리드 재알림 상태
    print("🔔 Testing Lead Reminders Status API...")
    success, data = check_endpoint("GET", "/api/scheduler/lead-reminders/status", ["success"])
    print_result("GET /api/scheduler/lead-reminders/status", success)
    if success and "data" in data:
        status = data.get("data", {})
        print(f"   - Pending Reminders: {len(status.get('pending_reminders', []))}")
        stats = status.get("stats", {})
        print(f"   - Total Sent: {stats.get('total_reminders_sent', 0)}")
    print()

    # 6. 리드 상태 전이 미리보기
    print("🔀 Testing Lead Transitions Preview API...")
    success, data = check_endpoint("GET", "/api/scheduler/lead-transitions/preview", ["success"])
    print_result("GET /api/scheduler/lead-transitions/preview", success)
    if success and "data" in data:
        preview = data.get("data", {})
        print(f"   - Total Candidates: {preview.get('total_candidates', 0)}")
        by_rule = preview.get("by_rule", {})
        for rule, count in by_rule.items():
            if count > 0:
                print(f"   - {rule}: {count}")
    print()

    # 7. 권장사항 적용 (POST - 실제로 적용하지 않으려면 주석 처리)
    print("⚡ Testing Apply Recommendations API...")
    success, data = check_endpoint("POST", "/api/scheduler/apply-recommendations", ["success"])
    print_result("POST /api/scheduler/apply-recommendations", success)
    if success and "data" in data:
        result = data.get("data", {})
        print(f"   - Applied: {len(result.get('applied', []))}")
        print(f"   - Skipped: {len(result.get('skipped', []))}")
    print()

    # 8. 리드 상태 요약
    print("📋 Testing Lead Status Summary API...")
    success, data = check_endpoint("GET", "/api/scheduler/lead-status/summary", ["success"])
    print_result("GET /api/scheduler/lead-status/summary", success)
    if success and "data" in data:
        summary = data.get("data", {})
        mentions = summary.get("mentions", {})
        print(f"   - Mentions by status: {mentions}")
    print()

    # 결과 요약
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for r in results if r["success"])
    failed = len(results) - passed

    print(f"Total Tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print()

    if failed > 0:
        print("Failed Tests:")
        for r in results:
            if not r["success"]:
                print(f"  ❌ {r['method']} {r['endpoint']} - Status: {r['status']}")
        print()

    if passed == len(results):
        print("✅ All API tests passed!")
        return 0
    else:
        print("❌ Some tests failed. Check if the server is running.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
