#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 프로덕션 전체 테스트 (303개 키워드)
- 실제 환경과 동일한 조건
- 전체 키워드 (config/targets.json + config/campaigns.json)
- 검색 → 필터링 → AI 분석 → DB 저장
- 차단 메커니즘 작동 확인
- 실시간 통계 모니터링

예상 소요 시간: 60-120분 (차단 발생 시 더 소요)
"""

import sys
import os
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')
sys.stdout.reconfigure(encoding='utf-8')

def test_production():
    """프로덕션 환경 전체 테스트"""
    from viral_hunter import ViralHunter
    import time
    from datetime import datetime

    print(f"\n{'='*70}")
    print("🚀 프로덕션 전체 테스트 (303개 키워드)")
    print(f"{'='*70}\n")
    print(f"⏰ 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ViralHunter 초기화
    print("📦 ViralHunter 초기화 중...")
    try:
        hunter = ViralHunter()
        print("   ✅ 초기화 완료")
        print(f"   📁 DB: {hunter.db.db_path}\n")
    except Exception as e:
        print(f"   ❌ 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        return

    # 키워드 로드 (실제 환경과 동일)
    print("📋 키워드 로딩 중...")
    keywords = hunter._load_keywords()
    print(f"   ✅ 총 {len(keywords)}개 키워드 로드")
    print(f"   📝 첫 10개: {keywords[:10]}\n")

    # 예상 시간 계산
    estimated_time = len(keywords) * 3 * 2  # 키워드 × 3플랫폼 × 2초
    print(f"⏱️  예상 소요 시간:")
    print(f"   정상: {estimated_time/60:.0f}분")
    print(f"   403 발생 시: {(estimated_time + 600)/60:.0f}분 (5-10분 대기 포함)")
    print(f"\n💡 실시간 진행 상황이 출력됩니다.")
    print(f"   Ctrl+C로 중단 가능 (DB는 안전하게 보호됨)\n")

    # 실행 전 마지막 확인
    print(f"{'='*70}")
    print("⚠️  주의사항:")
    print("   1. 90분 이상 소요 예상")
    print("   2. 네이버 403 에러 시 자동 5-10분 대기")
    print("   3. 연속 10개 실패 시 추가 5분 대기")
    print("   4. DB는 안전하게 트랜잭션 처리")
    print(f"{'='*70}\n")

    input("▶️  Enter 키를 눌러 전체 테스트 시작...")

    start_time = time.time()

    # 진행 상황 콜백
    def progress_callback(stage, current, total, message):
        elapsed = time.time() - start_time
        print(f"[{elapsed/60:.1f}분] [{stage}] {current}/{total} - {message}")

    # hunt() 실행 (전체 파이프라인)
    print(f"\n{'='*70}")
    print("🎯 전체 검색 시작...")
    print(f"{'='*70}\n")

    try:
        results = hunter.hunt(
            keywords=None,  # None = 전체 키워드 로드
            limit_keywords=None,  # 제한 없음
            max_per_platform=15,  # 실제 설정과 동일
            progress_callback=progress_callback
        )

        elapsed = time.time() - start_time
        end_time = datetime.now()

        print(f"\n{'='*70}")
        print("📊 전체 테스트 결과")
        print(f"{'='*70}\n")

        print(f"⏰ 시작: {datetime.fromtimestamp(start_time).strftime('%H:%M:%S')}")
        print(f"⏰ 종료: {end_time.strftime('%H:%M:%S')}")
        print(f"⏱️  소요 시간: {elapsed/60:.1f}분 ({elapsed:.0f}초)")
        print(f"\n📦 총 발견: {len(results)}개 타겟")

        # 플랫폼별 통계
        platform_counts = {}
        for r in results:
            platform_counts[r.platform] = platform_counts.get(r.platform, 0) + 1

        print(f"\n플랫폼별:")
        for platform, count in sorted(platform_counts.items()):
            icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(platform, "📌")
            print(f"   {icon} {platform}: {count}개")

        # HOT LEAD 통계
        hot_leads = [r for r in results if "🔥" in r.content_preview or r.priority_score >= 80]
        print(f"\n🔥 HOT LEAD: {len(hot_leads)}개")

        if hot_leads:
            print(f"\n   상위 5개:")
            for i, lead in enumerate(hot_leads[:5], 1):
                platform_icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(lead.platform, "📌")
                print(f"   {i}. {platform_icon} {lead.title[:50]}... (점수: {lead.priority_score:.0f})")

        # API 통계
        api_stats = hunter.searcher.get_stats()
        print(f"\n{'='*70}")
        print(f"📈 API 통계")
        print(f"{'='*70}\n")
        print(f"   요청: {api_stats['requests']}건")
        print(f"   에러: {api_stats['errors']}건 ({api_stats['error_rate']})")
        print(f"   캐시 히트: {api_stats['cache_hits']}건")

        print(f"\n{'='*70}")
        print(f"🛡️ 차단 감지 시스템")
        print(f"{'='*70}\n")
        print(f"   총 검색: {api_stats['total_searches']}회")
        print(f"   성공: {api_stats['successful_searches']}회 ({api_stats['success_rate']})")
        print(f"   연속 실패: {api_stats['consecutive_failures']}회")
        print(f"   차단 상태: {'🚨 차단됨' if api_stats['is_blocked'] else '✅ 정상'}")
        print(f"   최종 delay: {api_stats['current_delay']}")

        # 카테고리별 통계
        category_counts = {}
        for r in results:
            category = r.category if hasattr(r, 'category') else '기타'
            category_counts[category] = category_counts.get(category, 0) + 1

        if category_counts:
            print(f"\n{'='*70}")
            print(f"📂 카테고리별")
            print(f"{'='*70}\n")
            for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"   {category}: {count}개")

        # 최종 평가
        print(f"\n{'='*70}")
        print("🎯 종합 평가")
        print(f"{'='*70}\n")

        success_rate = float(api_stats['success_rate'].rstrip('%'))

        # 성공률 평가
        if success_rate >= 90:
            print("✅ 성공률: 우수 (90% 이상)")
        elif success_rate >= 70:
            print("⚠️  성공률: 양호 (70-90%)")
        else:
            print("❌ 성공률: 주의 (70% 미만)")

        # 차단 상태 평가
        if api_stats['is_blocked']:
            print("🚨 차단 상태: 현재 차단됨")
        elif api_stats['consecutive_failures'] >= 5:
            print("⚠️  차단 상태: 부분 차단 (자동 복구됨)")
        else:
            print("✅ 차단 상태: 정상")

        # 타겟 발견 평가
        if len(results) > 500:
            print(f"✅ 타겟 발견: 우수 ({len(results)}개)")
        elif len(results) > 100:
            print(f"⚠️  타겟 발견: 양호 ({len(results)}개)")
        else:
            print(f"❌ 타겟 발견: 부족 ({len(results)}개)")

        # 효율성 평가
        if elapsed < 3600:  # 60분 미만
            print(f"✅ 소요 시간: 우수 ({elapsed/60:.0f}분)")
        elif elapsed < 5400:  # 90분 미만
            print(f"⚠️  소요 시간: 양호 ({elapsed/60:.0f}분)")
        else:
            print(f"❌ 소요 시간: 느림 ({elapsed/60:.0f}분)")

        # 최종 결론
        print(f"\n{'='*70}")
        print("📝 최종 결론")
        print(f"{'='*70}\n")

        if success_rate >= 85 and len(results) > 100 and not api_stats['is_blocked']:
            print("🎉 전체 시스템 정상 작동!")
            print("   ✅ 프로덕션 배포 가능")
            print("   ✅ Dashboard에서 안전하게 사용 가능")
        elif success_rate >= 70 and len(results) > 50:
            print("⚠️  일부 문제 있으나 작동 가능")
            print("   ⚠️  403 에러 발생했으나 자동 복구됨")
            print("   ⚠️  프로덕션 사용 가능 (느림)")
        else:
            print("❌ 문제가 있습니다")
            print("   ❌ 추가 디버깅 필요")
            if success_rate < 70:
                print("   → 성공률이 낮습니다")
            if len(results) < 50:
                print("   → 타겟 발견이 부족합니다")
            if api_stats['is_blocked']:
                print("   → 현재 차단 상태입니다")

        print(f"\n{'='*70}\n")

        # 샘플 저장
        if results:
            sample_file = "/mnt/c/Projects/marketing_bot/test_results_sample.txt"
            try:
                with open(sample_file, 'w', encoding='utf-8') as f:
                    f.write(f"전체 테스트 결과 샘플\n")
                    f.write(f"{'='*70}\n\n")
                    f.write(f"총 발견: {len(results)}개\n")
                    f.write(f"HOT LEAD: {len(hot_leads)}개\n\n")
                    f.write(f"상위 20개 타겟:\n")
                    f.write(f"{'='*70}\n\n")
                    for i, r in enumerate(results[:20], 1):
                        f.write(f"{i}. [{r.platform.upper()}] {r.title}\n")
                        f.write(f"   점수: {r.priority_score:.0f} | URL: {r.url}\n\n")
                print(f"📁 샘플 결과 저장: {sample_file}")
            except Exception as e:
                print(f"⚠️  샘플 저장 실패: {e}")

    except KeyboardInterrupt:
        print("\n\n⚠️  사용자가 중단했습니다.")
        elapsed = time.time() - start_time
        print(f"   진행 시간: {elapsed/60:.1f}분")
        print("   DB는 안전하게 보호되었습니다.")
    except Exception as e:
        print(f"\n\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_production()
