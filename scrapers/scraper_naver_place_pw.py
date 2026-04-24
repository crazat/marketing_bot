"""
Naver Place Rank Tracker - Playwright Version
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 B-1b] 기존 Selenium 기반 scraper_naver_place.py의 Playwright 마이그레이션

핵심 변경:
- Selenium BrowserPool → PlaywrightPool (async 기반)
- ThreadPoolExecutor → asyncio.Semaphore 병렬 제어
- driver.find_elements → page.locator / page.query_selector_all
- driver.switch_to.frame → page.frame_locator
- 리소스 차단 내장 (이미지/폰트/CSS) → 속도 2~5x 향상
- 자동 대기(ActionabilityCheck) → 불안정한 explicit wait 제거

사용법:
    python scrapers/scraper_naver_place_pw.py
    python scrapers/scraper_naver_place_pw.py -w 5        # 5개 컨텍스트 동시
    python scrapers/scraper_naver_place_pw.py --sequential # 순차 모드
"""

import sys
import os
import asyncio
import json
import random
import time
import argparse
import logging
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Sentry
try:
    from scrapers.sentry_init import init_sentry
    init_sentry("scraper_naver_place_pw")
except Exception:
    pass

from db.database import DatabaseManager
from db.status_manager import status_manager
from utils import logger

# Event Bus (optional)
try:
    from core.event_bus import publish_event, EventType
    HAS_EVENT_BUS = True
except ImportError:
    HAS_EVENT_BUS = False

# Windows Encoding Fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# 기존 모듈에서 헬퍼 함수 재사용
from scrapers.scraper_naver_place import (
    _get_previous_rank,
    _publish_rank_event,
)


# ============================================================================
# Playwright 기반 스캔 함수
# ============================================================================

async def _extract_places_from_page(page, device_type: str) -> List[Tuple[str, bool, int]]:
    """
    페이지에서 플레이스 항목 추출

    Returns:
        [(place_name, is_ad, index), ...]
    """
    extracted = []

    if device_type == "mobile":
        # 모바일: 메인 페이지 스크롤
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.8)

        # li 요소에서 플레이스 항목 필터링
        all_li = await page.query_selector_all("li")
        place_items = []

        for li in all_li:
            try:
                text = await li.inner_text()
                if not text:
                    continue
                if ("km" in text or "m " in text) and ("진료" in text or "영업" in text or "휴무" in text):
                    place_items.append(li)
                elif any(kw in text for kw in ["한의원", "병원", "약국", "의원", "클리닉"]):
                    if len(text) > 20:
                        place_items.append(li)
            except Exception:
                pass

        for idx, item in enumerate(place_items):
            try:
                name, is_ad = await _extract_name_from_element(item)
                extracted.append((name, is_ad, idx))
            except Exception:
                extracted.append(("", False, idx))

    else:
        # 데스크톱: iframe 내부 검색
        try:
            frame = page.frame_locator("#searchIframe")

            # 스크롤 컨테이너 찾기 + 점진적 스크롤
            scroll_selector = "#_pcmap_list_scroll_container, .Ryr1F"
            try:
                await frame.locator(scroll_selector).first.wait_for(timeout=10000)
            except Exception:
                logger.debug("스크롤 컨테이너를 찾을 수 없음")

            # 점진적 스크롤 (기존 Selenium 로직과 동일: 800px씩, 최소 10회)
            no_change_count = 0
            for scroll_attempt in range(50):
                await frame.locator("body").evaluate("""
                    () => {
                        const el = document.querySelector('#_pcmap_list_scroll_container') ||
                                   document.querySelector('.Ryr1F');
                        if (el) el.scrollTop += 800;
                    }
                """)
                await asyncio.sleep(0.5)

                if scroll_attempt < 10:
                    continue

                at_bottom = await frame.locator("body").evaluate("""
                    () => {
                        const el = document.querySelector('#_pcmap_list_scroll_container') ||
                                   document.querySelector('.Ryr1F');
                        if (!el) return true;
                        return (el.scrollTop + el.clientHeight >= el.scrollHeight - 10);
                    }
                """)

                if at_bottom:
                    no_change_count += 1
                    if no_change_count >= 3:
                        break
                else:
                    no_change_count = 0

            # iframe 내의 li 요소 수집
            all_li = await frame.locator("li").all()
            place_items = []

            for li in all_li:
                try:
                    text = await li.inner_text()
                    if not text:
                        continue
                    if ("km" in text or "m " in text) and ("진료" in text or "영업" in text or "휴무" in text):
                        place_items.append(li)
                    elif any(kw in text for kw in ["한의원", "병원", "약국", "의원", "클리닉"]):
                        if len(text) > 20:
                            place_items.append(li)
                except Exception:
                    pass

            for idx, item in enumerate(place_items):
                try:
                    name, is_ad = await _extract_name_from_element(item)
                    extracted.append((name, is_ad, idx))
                except Exception:
                    extracted.append(("", False, idx))

        except Exception as e:
            logger.debug(f"iframe 처리 오류: {e}")

    return extracted


async def _extract_name_from_element(element) -> Tuple[str, bool]:
    """
    요소에서 업체명과 광고 여부 추출

    Returns:
        (place_name, is_ad)
    """
    is_ad = False
    place_name = ""

    try:
        text = await element.inner_text()
        lines = text.strip().split('\n')

        # 광고 감지
        if "광고" in text:
            is_ad = True

        # 첫 번째 의미 있는 라인을 업체명으로
        for line in lines:
            line = line.strip()
            if line and line != "광고" and len(line) > 1:
                # "N번째" 패턴 스킵
                if line[0].isdigit() and "." in line[:4]:
                    line = line.split(".", 1)[-1].strip()
                if line:
                    place_name = line
                    break

    except Exception:
        pass

    return place_name, is_ad


async def _scan_single_keyword_pw(
    pool,
    keyword: str,
    target_name: str,
    device_type: str,
    competitors: List[str],
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    단일 키워드 Playwright 스캔 (기존 _scan_single_keyword의 async 버전)
    """
    from scrapers.playwright_engine import managed_page, random_delay

    result = {
        "keyword": keyword,
        "device_type": device_type,
        "status": "error",
        "rank": 0,
        "total_results": 0,
        "note": "",
        "competitor_ranks": {}
    }

    db = DatabaseManager()

    async with semaphore:
        # 네이버 차단 방지 딜레이
        await random_delay(1.5, 3.5)

        try:
            async with managed_page(pool) as page:
                # URL 설정
                if device_type == "mobile":
                    url = f"https://m.place.naver.com/place/list?query={keyword}"
                else:
                    url = f"https://map.naver.com/p/search/{keyword}"

                logger.info(f"   🔍 [{device_type}] Scanning: {keyword}...")

                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(2 + random.random() * 2)

                # 플레이스 항목 추출
                extracted_places = await _extract_places_from_page(page, device_type)
                total_results = len(extracted_places)

                found_rank = 0
                rank_status = "error"
                rank_note = ""

                if not extracted_places:
                    content = await page.content()
                    if "검색결과가 없습니다" in content:
                        rank_status = "no_results"
                        rank_note = f"[{device_type}] 검색 결과 없음"
                    else:
                        rank_status = "no_results"
                        rank_note = f"[{device_type}] DOM 파싱 실패"
                else:
                    # 타겟 순위 계산
                    real_rank = 0
                    is_target_ad = False
                    target_normalized = target_name.replace(" ", "")

                    for place_name, is_ad, idx in extracted_places:
                        if not is_ad:
                            real_rank += 1

                        place_normalized = place_name.replace(" ", "")
                        if target_normalized in place_normalized:
                            if is_ad:
                                is_target_ad = True
                                rank_note = f"[{device_type}] 광고 게재 중 (위치: {idx + 1})"
                            else:
                                found_rank = real_rank
                                rank_status = "found"
                            break

                    if found_rank > 0:
                        result["status"] = "found"
                    elif is_target_ad:
                        rank_status = "found"
                        found_rank = 0
                    else:
                        rank_status = "not_in_results"
                        rank_note = f"[{device_type}] 상위 {total_results}개에 미포함"

                # 이전 순위 조회
                previous_rank, _ = _get_previous_rank(db, keyword, target_name)

                # DB 저장
                db.insert_rank(keyword, found_rank, target_name,
                               status=rank_status, total_results=total_results,
                               note=rank_note, device_type=device_type)

                # 순위 이벤트 발행
                if rank_status == "found" and found_rank > 0:
                    _publish_rank_event(keyword, target_name, found_rank, previous_rank, total_results)

                # 경쟁사 순위 체크
                if extracted_places and rank_status != "error":
                    for comp_name in competitors:
                        if comp_name == target_name:
                            continue

                        comp_rank = 0
                        comp_status = "not_in_results"
                        comp_note = ""
                        real_rank = 0
                        comp_normalized = comp_name.replace(" ", "")

                        for place_name, is_ad, idx in extracted_places:
                            if not is_ad:
                                real_rank += 1
                            place_normalized = place_name.replace(" ", "")
                            if comp_normalized in place_normalized:
                                if is_ad:
                                    comp_note = f"광고 게재 중 (위치: {idx + 1})"
                                else:
                                    comp_rank = real_rank
                                    comp_status = "found"
                                break

                        db.insert_rank(keyword, comp_rank, comp_name,
                                       status=comp_status, total_results=total_results,
                                       note=comp_note, device_type=device_type)
                        result["competitor_ranks"][comp_name] = comp_rank

                result.update({
                    "status": rank_status,
                    "rank": found_rank,
                    "total_results": total_results,
                    "note": rank_note
                })

        except Exception as e:
            logger.error(f"      ⚠️ [{device_type}] Error scanning {keyword}: {e}")
            db.insert_rank(keyword, 0, target_name,
                           status="error", total_results=0,
                           note=f"[{device_type}] {str(e)[:150]}", device_type=device_type)
            result["note"] = str(e)[:150]

    return result


async def _scan_keywords_parallel_pw(
    keywords: List[str],
    target_name: str,
    device_type: str,
    max_workers: int = 3,
) -> List[Dict[str, Any]]:
    """
    키워드 병렬 스캔 (Playwright async 버전)
    """
    from scrapers.playwright_engine import PlaywrightPool

    mobile = (device_type == "mobile")
    semaphore = asyncio.Semaphore(max_workers)

    # 경쟁사 목록 로드
    competitors = _load_competitors()

    async with PlaywrightPool(pool_size=max_workers, mobile=mobile, headless=True) as pool:
        tasks = [
            _scan_single_keyword_pw(pool, kw, target_name, device_type, competitors, semaphore)
            for kw in keywords
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 예외를 에러 결과로 변환
    final_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"Task failed for {keywords[i]}: {r}")
            final_results.append({
                "keyword": keywords[i],
                "device_type": device_type,
                "status": "error",
                "rank": 0,
                "total_results": 0,
                "note": str(r)[:150],
                "competitor_ranks": {}
            })
        else:
            final_results.append(r)

    return final_results


def _load_competitors() -> List[str]:
    """경쟁사 목록 로드"""
    try:
        targets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'targets.json'
        )
        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [t['name'] for t in data.get('targets', []) if t.get('priority') != 'Low']
    except Exception as e:
        logger.error(f"경쟁사 목록 로드 실패: {e}")
    return []


async def check_naver_place_rank_pw(max_workers: int = 3):
    """
    네이버 플레이스 순위 체크 (Playwright 메인 함수)
    """
    # 키워드 로드
    kw_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'keywords.json'
    )
    keywords = []
    if os.path.exists(kw_path):
        try:
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                keywords = data.get("naver_place", [])
        except Exception as e:
            logger.error(f"❌ Failed to load keywords.json: {e}")
            return

    if not keywords:
        logger.error("❌ No keywords found. Aborting.")
        return

    logger.info(f"📋 Loaded {len(keywords)} Target Keywords")

    # 타겟명 로드
    target_name = "규림한의원"
    try:
        from utils import ConfigManager
        cfg = ConfigManager()
        targets_data = cfg.load_targets()
        for t in targets_data.get('targets', []):
            if "규림" in t['name']:
                target_name = t['name']
                break
    except Exception:
        pass

    logger.info(f"🎯 Target Name: {target_name}")
    print(f"🚀 Naver Place Rank Tracker [PLAYWRIGHT] Started (workers={max_workers})")
    status_manager.update_status("Place Sniper", "RUNNING", f"Checking Ranks... [PW-PARALLEL w={max_workers}]")

    start_time = time.time()

    # 1. 모바일 스캔
    logger.info("📱 Phase 1: Mobile PARALLEL Scan (Playwright)...")
    mobile_results = await _scan_keywords_parallel_pw(keywords, target_name, "mobile", max_workers)

    # 2. 데스크톱 스캔
    logger.info("🖥️ Phase 2: Desktop PARALLEL Scan (Playwright)...")
    desktop_results = await _scan_keywords_parallel_pw(keywords, target_name, "desktop", max_workers)

    # 결과 요약
    mobile_found = sum(1 for r in mobile_results if r["status"] == "found" and r["rank"] > 0)
    desktop_found = sum(1 for r in desktop_results if r["status"] == "found" and r["rank"] > 0)

    elapsed = time.time() - start_time
    logger.info(f"📊 Results: Mobile {mobile_found}/{len(keywords)}, Desktop {desktop_found}/{len(keywords)}")
    logger.info(f"⏱️ Total time: {elapsed:.1f}s")

    status_manager.update_status(
        "Place Sniper", "IDLE",
        f"Completed: M:{mobile_found}/{len(keywords)}, D:{desktop_found}/{len(keywords)} ({elapsed:.0f}s)"
    )

    print(f"\n✅ Place Sniper [PLAYWRIGHT] Complete: {elapsed:.1f}s")
    print(f"   📱 Mobile: {mobile_found}/{len(keywords)} found")
    print(f"   🖥️ Desktop: {desktop_found}/{len(keywords)} found")


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naver Place Rank Tracker (Playwright)")
    parser.add_argument("-w", "--workers", type=int, default=3, help="동시 브라우저 컨텍스트 수 (기본: 3)")
    parser.add_argument("--skip-reviews", action="store_true", help="리뷰 수집 스킵")
    args = parser.parse_args()

    asyncio.run(check_naver_place_rank_pw(max_workers=args.workers))
