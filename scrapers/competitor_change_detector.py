#!/usr/bin/env python3
"""
Competitor Change Detector - 경쟁사 변경 감지기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

경쟁사 네이버 플레이스 프로필 및 블로그 변경을 실시간 감지합니다.
- 프로필 정보 해시 비교 (업체명, 설명, 메뉴, 사진 수, 운영시간)
- 변경 유형/심각도 분류
- 경쟁사 블로그 포스팅 빈도 모니터링
- 고심각도 변경 시 Telegram 알림 발송
"""

import os
import sys
import json
import time
import random
import hashlib
import traceback
import logging
import re
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

import requests
from bs4 import BeautifulSoup

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


# ============================================================================
# Constants
# ============================================================================

HASH_FILE_PATH = os.path.join(project_root, 'scraped_data', 'competitor_hashes.json')

GRAPHQL_ENDPOINT = "https://pcmap-api.place.naver.com/graphql"

PLACE_DETAIL_QUERY = [
    {
        "operationName": "getPlaceDetail",
        "variables": {
            "input": {
                "businessId": None,  # 런타임에 채움
                "isNx": False,
                "deviceType": "pcmap",
            }
        },
        "query": """query getPlaceDetail($input: PlaceDetailInput) {
            placeDetail(input: $input) {
                basicInfo {
                    id
                    name
                    description
                    category
                    businessHours { isDayOff openTime closeTime }
                    phone
                    address
                    imageCount
                }
                menuInfo {
                    menuList { name price }
                    menuCount
                }
            }
        }"""
    }
]

# 변경 유형별 심각도 매핑
CHANGE_SEVERITY = {
    'menu_change': 'high',
    'hours_changed': 'high',
    'profile_update': 'medium',
    'description_changed': 'medium',
    'photo_added': 'medium',
    'category_changed': 'medium',
    'phone_changed': 'low',
    'address_changed': 'low',
    'blog_frequency_change': 'low',
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


class CompetitorChangeDetector:
    """경쟁사 프로필/블로그 변경을 감지합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_targets()
        self._load_hashes()
        self._init_telegram()
        self._last_request_time = 0

    def _ensure_table(self):
        """competitor_changes 테이블이 없으면 생성합니다."""
        with self.db.get_new_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS competitor_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competitor_name TEXT NOT NULL,
                    place_id TEXT,
                    change_type TEXT NOT NULL,
                    severity TEXT DEFAULT 'low',
                    old_value TEXT,
                    new_value TEXT,
                    details TEXT,
                    notified INTEGER DEFAULT 0,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_competitor_changes_name_date
                ON competitor_changes (competitor_name, detected_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_competitor_changes_severity
                ON competitor_changes (severity, detected_at)
            """)
            conn.commit()
        logger.info("competitor_changes 테이블 준비 완료")

    def _load_targets(self):
        """config/targets.json에서 경쟁사 목록을 로드합니다."""
        self.targets = []
        targets_path = os.path.join(project_root, 'config', 'targets.json')

        try:
            if os.path.exists(targets_path):
                with open(targets_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.targets = data.get('targets', [])
        except Exception as e:
            logger.error(f"targets.json 로드 실패: {e}")

        logger.info(f"경쟁사 {len(self.targets)}개 로드")

    def _load_hashes(self):
        """저장된 해시 파일을 로드합니다."""
        self.hashes = {}

        # scraped_data 디렉토리 확인
        hash_dir = os.path.dirname(HASH_FILE_PATH)
        os.makedirs(hash_dir, exist_ok=True)

        try:
            if os.path.exists(HASH_FILE_PATH):
                with open(HASH_FILE_PATH, 'r', encoding='utf-8') as f:
                    self.hashes = json.load(f)
        except Exception as e:
            logger.warning(f"해시 파일 로드 실패 (새로 생성됨): {e}")
            self.hashes = {}

    def _save_hashes(self):
        """해시 파일을 저장합니다."""
        try:
            with open(HASH_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.hashes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"해시 파일 저장 실패: {e}")

    def _init_telegram(self):
        """Telegram 알림 봇을 초기화합니다."""
        self.telegram_bot = None
        try:
            from alert_bot import TelegramBot, AlertPriority
            self.AlertPriority = AlertPriority

            token = self.config.get_api_key('TELEGRAM_BOT_TOKEN')
            chat_id = self.config.get_api_key('TELEGRAM_CHAT_ID')
            self.telegram_bot = TelegramBot(token=token, chat_id=chat_id)
            logger.info("Telegram 알림 봇 초기화 완료")
        except ImportError:
            logger.info("alert_bot 모듈 없음, Telegram 알림 비활성화")
        except Exception as e:
            logger.warning(f"Telegram 봇 초기화 실패: {e}")

    def _rate_limit(self, min_delay: float = 2.0):
        """요청 간 딜레이를 적용합니다."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(min_delay, min_delay + 1.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self) -> Dict[str, str]:
        """랜덤 User-Agent가 포함된 헤더를 반환합니다."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.naver.com/",
        }

    def _extract_place_id(self, naver_place_url: str) -> Optional[str]:
        """네이버 플레이스 URL에서 place_id를 추출합니다."""
        if not naver_place_url:
            return None
        match = re.search(r'place\.naver\.com/\w+/(\d+)', naver_place_url)
        return match.group(1) if match else None

    def _compute_hash(self, data: str) -> str:
        """문자열의 MD5 해시를 생성합니다."""
        return hashlib.md5(data.encode('utf-8')).hexdigest()

    # ========================================================================
    # Place Profile Fetching
    # ========================================================================

    def _fetch_place_profile_graphql(self, place_id: str) -> Optional[Dict]:
        """GraphQL API로 플레이스 프로필 정보를 가져옵니다."""
        query_body = json.loads(json.dumps(PLACE_DETAIL_QUERY))
        query_body[0]["variables"]["input"]["businessId"] = place_id

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://pcmap.place.naver.com",
            "Referer": "https://pcmap.place.naver.com/",
            "User-Agent": random.choice(USER_AGENTS),
        }

        try:
            response = requests.post(
                GRAPHQL_ENDPOINT,
                headers=headers,
                json=query_body,
                timeout=15
            )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                detail = data[0].get('data', {}).get('placeDetail', {})
            elif isinstance(data, dict):
                detail = data.get('data', {}).get('placeDetail', {})
            else:
                return None

            basic = detail.get('basicInfo', {}) or {}
            menu_info = detail.get('menuInfo', {}) or {}

            return {
                'name': basic.get('name', ''),
                'description': basic.get('description', ''),
                'category': basic.get('category', ''),
                'phone': basic.get('phone', ''),
                'address': basic.get('address', ''),
                'image_count': basic.get('imageCount', 0) or 0,
                'business_hours': json.dumps(basic.get('businessHours', []) or [], ensure_ascii=False),
                'menu_list': json.dumps(menu_info.get('menuList', []) or [], ensure_ascii=False),
                'menu_count': menu_info.get('menuCount', 0) or 0,
            }

        except requests.exceptions.RequestException as e:
            logger.warning(f"GraphQL 프로필 요청 실패 (place_id={place_id}): {e}")
            return None

    def _fetch_place_profile_fallback(self, place_id: str) -> Optional[Dict]:
        """모바일 웹페이지에서 프로필 정보를 파싱합니다."""
        url = f"https://m.place.naver.com/hospital/{place_id}/home"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # 기본 정보 추출 시도
            name_el = soup.select_one('.GHAhO') or soup.select_one('h2')
            name = name_el.get_text(strip=True) if name_el else ''

            desc_el = soup.select_one('.T8RFa')
            description = desc_el.get_text(strip=True) if desc_el else ''

            return {
                'name': name,
                'description': description,
                'category': '',
                'phone': '',
                'address': '',
                'image_count': 0,
                'business_hours': '[]',
                'menu_list': '[]',
                'menu_count': 0,
            }
        except Exception as e:
            logger.warning(f"폴백 프로필 파싱 실패 (place_id={place_id}): {e}")
            return None

    # ========================================================================
    # Blog Monitoring
    # ========================================================================

    def _check_blog_activity(self, blog_url: str) -> Optional[Dict]:
        """경쟁사 블로그의 최근 포스팅 활동을 확인합니다."""
        if not blog_url:
            return None

        match = re.search(r'blog\.naver\.com/(\w+)', blog_url)
        if not match:
            return None

        blog_id = match.group(1)
        list_url = f"https://blog.naver.com/PostList.naver"
        params = {
            "blogId": blog_id,
            "currentPage": 1,
            "categoryNo": 0,
            "countPerPage": 10,
        }

        try:
            response = requests.get(
                list_url,
                params=params,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # 최근 포스트 날짜 추출
            post_dates = []
            date_pattern = re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})')

            for text_el in soup.find_all(string=date_pattern):
                match = date_pattern.search(text_el)
                if match:
                    try:
                        date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                        post_dates.append(date)
                    except ValueError:
                        continue

            # 포스트 수 (링크 기반)
            post_links = soup.find_all('a', href=re.compile(rf'{blog_id}/\d+'))
            unique_posts = set()
            for link in post_links:
                href = link.get('href', '')
                post_match = re.search(r'/(\d+)$', href)
                if post_match:
                    unique_posts.add(post_match.group(1))

            recent_count = len(unique_posts)
            latest_date = max(post_dates).strftime("%Y-%m-%d") if post_dates else None

            return {
                'blog_id': blog_id,
                'recent_post_count': recent_count,
                'latest_post_date': latest_date,
                'post_dates': [d.strftime("%Y-%m-%d") for d in sorted(post_dates, reverse=True)[:10]],
            }

        except Exception as e:
            logger.debug(f"블로그 활동 확인 실패 ({blog_id}): {e}")
            return None

    # ========================================================================
    # Change Detection
    # ========================================================================

    def _detect_changes(self, competitor_name: str, place_id: str,
                        current_profile: Dict) -> List[Dict[str, Any]]:
        """
        저장된 해시와 현재 프로필을 비교하여 변경사항을 감지합니다.

        Returns:
            변경 내역 리스트
        """
        changes = []
        hash_key = f"place_{place_id}"
        old_hashes = self.hashes.get(hash_key, {})
        new_hashes = {}

        # 각 섹션별 해시 비교
        sections = {
            'name': ('name', 'profile_update'),
            'description': ('description', 'description_changed'),
            'category': ('category', 'category_changed'),
            'phone': ('phone', 'phone_changed'),
            'address': ('address', 'address_changed'),
            'business_hours': ('business_hours', 'hours_changed'),
            'menu_list': ('menu_list', 'menu_change'),
            'image_count': ('image_count', 'photo_added'),
        }

        for section_key, (profile_key, change_type) in sections.items():
            current_value = str(current_profile.get(profile_key, ''))
            current_hash = self._compute_hash(current_value)
            new_hashes[section_key] = current_hash

            old_hash = old_hashes.get(section_key)
            if old_hash and old_hash != current_hash:
                old_value_stored = old_hashes.get(f"{section_key}_value", "")
                severity = CHANGE_SEVERITY.get(change_type, 'low')

                changes.append({
                    'competitor_name': competitor_name,
                    'place_id': place_id,
                    'change_type': change_type,
                    'severity': severity,
                    'old_value': old_value_stored[:500] if old_value_stored else "(이전 값 없음)",
                    'new_value': current_value[:500],
                    'details': f"{section_key} 변경 감지",
                })

            # 현재 값 저장 (다음 비교를 위해)
            new_hashes[f"{section_key}_value"] = current_value[:500]

        # 해시 업데이트
        new_hashes['last_checked'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.hashes[hash_key] = new_hashes

        return changes

    def _detect_blog_changes(self, competitor_name: str, blog_data: Dict) -> List[Dict[str, Any]]:
        """블로그 포스팅 빈도 변화를 감지합니다."""
        changes = []
        if not blog_data:
            return changes

        blog_id = blog_data['blog_id']
        hash_key = f"blog_{blog_id}"
        old_data = self.hashes.get(hash_key, {})

        old_count = old_data.get('recent_post_count', 0)
        new_count = blog_data['recent_post_count']

        # 포스팅 빈도 급증 감지 (이전보다 2배 이상)
        if old_count > 0 and new_count >= old_count * 2:
            changes.append({
                'competitor_name': competitor_name,
                'place_id': None,
                'change_type': 'blog_frequency_change',
                'severity': 'medium',
                'old_value': f"최근 포스트 {old_count}건",
                'new_value': f"최근 포스트 {new_count}건 (급증)",
                'details': f"블로그 포스팅 빈도 급증 감지 ({blog_id})",
            })

        # 블로그 데이터 해시 업데이트
        self.hashes[hash_key] = {
            'recent_post_count': new_count,
            'latest_post_date': blog_data.get('latest_post_date'),
            'last_checked': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        return changes

    # ========================================================================
    # DB & Notification
    # ========================================================================

    def _save_changes(self, changes: List[Dict[str, Any]]):
        """변경사항을 DB에 저장합니다."""
        if not changes:
            return

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                for change in changes:
                    cursor.execute("""
                        INSERT INTO competitor_changes
                        (competitor_name, place_id, change_type, severity,
                         old_value, new_value, details, notified, detected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        change['competitor_name'],
                        change.get('place_id'),
                        change['change_type'],
                        change['severity'],
                        change.get('old_value'),
                        change.get('new_value'),
                        change.get('details'),
                        0,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                conn.commit()
                logger.info(f"변경사항 {len(changes)}건 DB 저장 완료")
        except Exception as e:
            logger.error(f"변경사항 DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

    def _send_telegram_alert(self, changes: List[Dict[str, Any]]):
        """고심각도 변경에 대해 Telegram 알림을 발송합니다."""
        if not self.telegram_bot:
            return

        high_changes = [c for c in changes if c['severity'] == 'high']
        if not high_changes:
            return

        try:
            lines = ["*[경쟁사 변경 감지]*\n"]

            for change in high_changes:
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(change['severity'], "⚪")
                lines.append(f"{severity_emoji} *{change['competitor_name']}*")
                lines.append(f"  유형: {change['change_type']}")
                if change.get('new_value'):
                    # Markdown 특수문자 이스케이프
                    new_val = change['new_value'][:200].replace('*', '\\*').replace('_', '\\_')
                    lines.append(f"  변경: {new_val}")
                lines.append("")

            lines.append(f"감지 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

            message = "\n".join(lines)
            priority = self.AlertPriority.CRITICAL if any(
                c['change_type'] in ('menu_change', 'hours_changed') for c in high_changes
            ) else self.AlertPriority.WARNING

            self.telegram_bot.send_message(message, priority=priority)
            logger.info(f"Telegram 알림 발송: 고심각도 변경 {len(high_changes)}건")

        except Exception as e:
            logger.error(f"Telegram 알림 발송 실패: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Main Runner
    # ========================================================================

    def check_competitor(self, target: Dict) -> List[Dict[str, Any]]:
        """단일 경쟁사의 변경을 확인합니다."""
        name = target.get('name', 'Unknown')
        monitor_urls = target.get('monitor_urls', {})
        naver_place_url = monitor_urls.get('naver_place', '')
        blog_url = monitor_urls.get('blog', '')

        all_changes = []

        # 1. 플레이스 프로필 변경 감지
        place_id = self._extract_place_id(naver_place_url)
        if place_id:
            print(f"  [{name}] 플레이스 프로필 확인 중...", end=" ")
            self._rate_limit()

            profile = self._fetch_place_profile_graphql(place_id)
            if not profile:
                self._rate_limit(min_delay=1.0)
                profile = self._fetch_place_profile_fallback(place_id)

            if profile:
                place_changes = self._detect_changes(name, place_id, profile)
                if place_changes:
                    print(f"-> {len(place_changes)}건 변경 감지!")
                    all_changes.extend(place_changes)
                else:
                    print("-> 변경 없음")
            else:
                print("-> 프로필 가져오기 실패")

        # 2. 블로그 활동 모니터링
        if blog_url:
            print(f"  [{name}] 블로그 활동 확인 중...", end=" ")
            self._rate_limit()

            blog_data = self._check_blog_activity(blog_url)
            if blog_data:
                blog_changes = self._detect_blog_changes(name, blog_data)
                if blog_changes:
                    print(f"-> {len(blog_changes)}건 변경 감지!")
                    all_changes.extend(blog_changes)
                else:
                    latest = blog_data.get('latest_post_date', 'N/A')
                    count = blog_data.get('recent_post_count', 0)
                    print(f"-> 최근 {count}건, 최신: {latest}")
            else:
                print("-> 블로그 확인 실패")

        return all_changes

    def run(self):
        """전체 경쟁사에 대해 변경 감지를 실행합니다."""
        if not self.targets:
            print("모니터링할 경쟁사가 없습니다.")
            return

        print(f"\n{'='*60}")
        print(f" Competitor Change Detector")
        print(f" 대상 경쟁사: {len(self.targets)}개")
        print(f" 해시 파일: {HASH_FILE_PATH}")
        is_first_run = not bool(self.hashes)
        if is_first_run:
            print(f" [첫 실행] 베이스라인 해시를 생성합니다 (변경 감지는 다음 실행부터)")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        all_changes = []
        success_count = 0
        error_count = 0

        for idx, target in enumerate(self.targets, 1):
            name = target.get('name', 'Unknown')
            print(f"\n  [{idx}/{len(self.targets)}] {name}")

            try:
                changes = self.check_competitor(target)
                all_changes.extend(changes)
                success_count += 1
            except Exception as e:
                error_count += 1
                print(f"  [{name}] 오류: {e}")
                logger.error(f"[{name}] 변경 감지 오류: {e}")
                logger.debug(traceback.format_exc())

        # 해시 파일 저장
        self._save_hashes()

        # 변경사항 DB 저장
        if all_changes:
            self._save_changes(all_changes)

        # Telegram 알림 (고심각도)
        if all_changes:
            self._send_telegram_alert(all_changes)

        # 결과 요약
        print(f"\n{'='*60}")
        print(f" 감지 완료! 확인: {success_count}/{len(self.targets)}")
        if error_count:
            print(f" 오류: {error_count}건")
        print(f" 총 변경사항: {len(all_changes)}건")
        if is_first_run:
            print(f" [첫 실행 완료] 베이스라인 저장됨. 다음 실행부터 변경 감지가 시작됩니다.")
        print(f"{'='*60}")

        if all_changes:
            print(f"\n 변경 내역:")
            for change in all_changes:
                severity_icon = {"high": "!!", "medium": "!", "low": "."}.get(change['severity'], "")
                print(f"   [{severity_icon:2s}] {change['competitor_name']} - {change['change_type']} ({change['severity']})")
                if change.get('details'):
                    print(f"        {change['details']}")

            # 심각도별 통계
            severity_counts = {}
            for c in all_changes:
                sev = c['severity']
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

            print(f"\n 심각도 분포: ", end="")
            parts = []
            for sev in ['high', 'medium', 'low']:
                if sev in severity_counts:
                    parts.append(f"{sev}={severity_counts[sev]}")
            print(", ".join(parts))

        return all_changes


if __name__ == "__main__":
    try:
        detector = CompetitorChangeDetector()
        detector.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
