#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔬 전체 파이프라인 종합 테스트
- 30개 대표 키워드 (롱테일, 일반, 핫 키워드 혼합)
- 검색 → 필터링 → AI 분석 → DB 저장
- 차단 메커니즘 작동 확인
- 실시간 통계 모니터링
"""

import sys
import os
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')
sys.stdout.reconfigure(encoding='utf-8')

def test_full_pipeline():
    """전체 파이프라인 테스트"""
    from viral_hunter import ViralHunter
    import time

    print(f"\n{'='*70}")
    print("🔬 Viral Hunter 전체 파이프라인 테스트")
    print(f"{'='*70}\n")

    # ViralHunter 초기화
    print("📦 ViralHunter 초기화 중...")
    try:
        hunter = ViralHunter()
        print("   ✅ 초기화 완료\n")
    except Exception as e:
        print(f"   ❌ 초기화 실패: {e}")
        print("   → WSL 환경에서는 DB 접근 문제가 있을 수 있습니다.")
        print("   → Windows PowerShell에서 실행을 권장합니다.\n")
        return

    # 대표 키워드 선택 (다양한 타입)
    test_keywords = [
        # 롱테일 키워드 (10개)
        "복대동 다이어트", "청주 아토피 피부", "청주 생리통", "청주 손땀",
        "율량동 여드름", "청주 편두통", "청주 불면증", "청주 수족냉증",
        "청주 갱년기", "청주 산후조리",

        # 일반 키워드 (10개)
        "청주 한의원", "청주 다이어트", "청주 교통사고", "청주 추나",
        "청주 피부과", "청주 여드름", "청주 입원", "청주 야간진료",
        "청주 새살침", "율량동 한의원",

        # 핫 키워드 (10개)
        "청주 다이어트 한의원", "청주 교통사고 한의원", "청주 여드름 치료",
        "청주 추나요법", "청주 한방 다이어트", "청주 교통사고 치료",
        "청주 척추 교정", "청주 체형 교정", "청주 턱관절", "청주 안면비대칭"
    ]

    print(f"📋 테스트 키워드: {len(test_keywords)}개")
    print(f"   - 롱테일: 10개 (검색 결과 적을 것)")
    print(f"   - 일반: 10개 (검색 결과 중간)")
    print(f"   - 핫: 10개 (검색 결과 많을 것)")
    print(f"\n⏱️  예상 소요 시간: 10-15분")
    print(f"   (403 발생 시 자동 2-5분 대기 포함)\n")

    # 실행 전 확인
    input("▶️  Enter 키를 눌러 테스트 시작...")

    start_time = time.time()

    # hunt() 실행 (실제 파이프라인)
    print(f"\n{'='*70}")
    print("🎯 검색 시작...")
    print(f"{'='*70}\n")

    try:
        results = hunter.hunt(
            keywords=test_keywords,
            limit_keywords=None,
            max_per_platform=10  # 플랫폼당 10개씩
        )

        elapsed = time.time() - start_time

        print(f"\n{'='*70}")
        print("📊 테스트 결과 요약")
        print(f"{'='*70}\n")

        print(f"⏱️  소요 시간: {elapsed/60:.1f}분 ({elapsed:.0f}초)")
        print(f"📦 총 발견: {len(results)}개 타겟")

        # 플랫폼별 통계
        platform_counts = {}
        for r in results:
            platform_counts[r.platform] = platform_counts.get(r.platform, 0) + 1

        print(f"\n플랫폼별:")
        for platform, count in platform_counts.items():
            icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(platform, "📌")
            print(f"   {icon} {platform}: {count}개")

        # HOT LEAD 통계
        hot_leads = [r for r in results if "🔥" in r.content_preview or r.priority_score >= 80]
        print(f"\n🔥 HOT LEAD: {len(hot_leads)}개")

        # API 통계
        api_stats = hunter.searcher.get_stats()
        print(f"\n📈 API 통계:")
        print(f"   요청: {api_stats['requests']}건")
        print(f"   에러: {api_stats['errors']}건 ({api_stats['error_rate']})")
        print(f"   캐시 히트: {api_stats['cache_hits']}건")
        print(f"\n🛡️ 차단 감지:")
        print(f"   총 검색: {api_stats['total_searches']}회")
        print(f"   성공: {api_stats['successful_searches']}회 ({api_stats['success_rate']})")
        print(f"   연속 실패: {api_stats['consecutive_failures']}회")
        print(f"   차단 상태: {'🚨 차단됨' if api_stats['is_blocked'] else '✅ 정상'}")
        print(f"   현재 delay: {api_stats['current_delay']}")

        # 샘플 결과 출력
        if results:
            print(f"\n{'='*70}")
            print("📋 발견된 타겟 샘플 (상위 10개)")
            print(f"{'='*70}\n")

            for i, target in enumerate(results[:10], 1):
                platform_icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(target.platform, "📌")
                hot_icon = "🔥" if target.priority_score >= 80 else ""
                print(f"{i:2}. {hot_icon}{platform_icon} [{target.platform.upper()}] {target.title[:50]}...")
                print(f"     점수: {target.priority_score:.0f} | 키워드: {', '.join(target.matched_keywords[:2])}")
                print(f"     URL: {target.url[:70]}...")
                print()

        # 최종 평가
        print(f"{'='*70}")
        print("🎯 종합 평가")
        print(f"{'='*70}\n")

        success_rate = float(api_stats['success_rate'].rstrip('%'))

        if success_rate >= 90:
            print("✅ 우수: 90% 이상 성공률")
        elif success_rate >= 70:
            print("⚠️  양호: 70-90% 성공률 (일부 차단 발생)")
        else:
            print("❌ 주의: 70% 미만 성공률 (차단 문제 있음)")

        if api_stats['is_blocked']:
            print("🚨 현재 차단 상태 - 추가 대기 필요")
        elif api_stats['consecutive_failures'] >= 5:
            print("⚠️  연속 실패 감지 - delay 증가됨")
        else:
            print("✅ 정상 작동 - 차단 없음")

        if len(results) > 0:
            print(f"✅ 타겟 발견 성공 - {len(results)}개")
        else:
            print("❌ 타겟 0개 - 문제 있음")

        print(f"\n{'='*70}")
        print("📝 결론")
        print(f"{'='*70}\n")

        if success_rate >= 90 and len(results) > 0 and not api_stats['is_blocked']:
            print("🎉 전체 파이프라인 정상 작동!")
            print("   → 303개 전체 키워드 실행 가능")
            print("   → 예상 소요 시간: 60-90분")
        elif success_rate >= 70:
            print("⚠️  부분적 문제 있음")
            print("   → 403 에러가 발생했지만 자동 복구됨")
            print("   → 전체 실행 가능하나 시간 더 소요 예상")
        else:
            print("❌ 문제 있음 - 추가 조사 필요")
            print("   → 10-15분 대기 후 재시도 권장")

        print(f"\n{'='*70}\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  사용자가 중단했습니다.")
    except Exception as e:
        print(f"\n\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_full_pipeline()
