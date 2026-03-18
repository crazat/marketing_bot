#!/usr/bin/env python3
"""
의료 리뷰 플랫폼 모니터링
- 모두닥(modoodoc.com), 굿닥(goodoc.co.kr) 등 의료 리뷰 플랫폼 수집
- 우리 한의원 리뷰 및 경쟁사 리뷰 모니터링
- 평점, 리뷰 내용, 치료 유형별 분석
"""
import sys
import os
import re
import time
import json
import logging
import traceback
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any
from urllib.parse import quote, urljoin

# Robust Path Setup for Hybrid Execution (Standalone vs Module)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from db.database import DatabaseManager
    from utils import ConfigManager, logger
except ImportError:
    print("Import Error: Check directory structure.")
    sys.exit(1)

# Force UTF-8 output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)


class MedicalReviewMonitor:
    """
    의료 리뷰 플랫폼 모니터링 엔진.
    모두닥, 굿닥 등에서 리뷰를 수집하여 분석합니다.
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    ]

    # 치료 유형 분류 키워드
    TREATMENT_PATTERNS = {
        "다이어트": ["다이어트", "살빼", "체중", "비만", "감량", "한약"],
        "교통사고": ["교통사고", "사고", "후유증", "보험"],
        "통증": ["통증", "허리", "목", "어깨", "무릎", "디스크", "추나"],
        "피부": ["여드름", "피부", "아토피", "습진", "트러블"],
        "비대칭": ["비대칭", "안면", "체형", "교정"],
        "일반진료": ["감기", "보약", "한약", "침", "뜸"],
    }

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()

        # Load business profile
        self.business_name = None
        self.business_short_names = []
        self.region = "청주"
        self._load_business_profile()

        # Load competitor names
        self.competitor_names = self._load_competitor_names()

        # All clinic names to search
        self.search_targets = self._build_search_targets()

        # User-Agent rotation
        self._ua_index = 0

        # Ensure DB table
        self._ensure_table()

    def _load_business_profile(self):
        """config/business_profile.json에서 업체 정보 로드"""
        profile_path = os.path.join(project_root, 'config', 'business_profile.json')
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                business = data.get('business', {})
                self.business_name = business.get('name', '')
                short_name = business.get('short_name', '')
                self.business_short_names = [
                    self.business_name,
                    short_name,
                ] if short_name else [self.business_name]
                self.region = business.get('region', '청주')
                logger.info(f"Business profile loaded: {self.business_name}")
        except Exception as e:
            logger.error(f"Error loading business profile: {e}")

    def _load_competitor_names(self) -> List[str]:
        """config/targets.json에서 경쟁사 이름 로드"""
        competitors = []
        targets_path = os.path.join(project_root, 'config', 'targets.json')
        try:
            if os.path.exists(targets_path):
                with open(targets_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for comp in data.get('competitors', []):
                    name = comp.get('name', '')
                    if name:
                        competitors.append(name)
                logger.info(f"Loaded {len(competitors)} competitor names")
            else:
                # Fallback: root targets.json
                fallback = os.path.join(project_root, 'targets.json')
                if os.path.exists(fallback):
                    with open(fallback, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    for comp in data.get('competitors', []):
                        name = comp.get('name', '')
                        if name:
                            competitors.append(name)
        except Exception as e:
            logger.error(f"Error loading competitor names: {e}")

        return competitors

    def _build_search_targets(self) -> List[Dict[str, Any]]:
        """검색 대상 목록 구성 (우리 + 경쟁사)"""
        targets = []

        # Our clinic
        if self.business_name:
            targets.append({
                "name": self.business_name,
                "is_our_clinic": True,
            })

        # Competitors
        for comp_name in self.competitor_names:
            targets.append({
                "name": comp_name,
                "is_our_clinic": False,
            })

        return targets

    def _ensure_table(self):
        """medical_platform_reviews 테이블 생성"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS medical_platform_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        clinic_name TEXT NOT NULL,
                        is_our_clinic INTEGER DEFAULT 0,
                        reviewer TEXT,
                        rating REAL,
                        content TEXT,
                        treatment_type TEXT,
                        review_date TEXT,
                        review_url TEXT,
                        url_hash TEXT UNIQUE,
                        scanned_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_medical_reviews_clinic
                    ON medical_platform_reviews(clinic_name, platform)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_medical_reviews_date
                    ON medical_platform_reviews(scanned_at)
                ''')
                conn.commit()
                logger.info("medical_platform_reviews table ensured")
        except Exception as e:
            logger.error(f"Error creating medical_platform_reviews table: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """User-Agent 로테이션된 헤더 반환"""
        ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
        self._ua_index += 1
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _url_hash(self, url: str) -> str:
        """URL 해시 생성 (중복 방지용)"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def _classify_treatment(self, text: str) -> str:
        """리뷰 텍스트에서 치료 유형 분류"""
        if not text:
            return "일반진료"

        text_lower = text
        scores = {}
        for treatment, patterns in self.TREATMENT_PATTERNS.items():
            score = sum(1 for p in patterns if p in text_lower)
            if score > 0:
                scores[treatment] = score

        if scores:
            return max(scores, key=scores.get)

        return "일반진료"

    def scrape_modoodoc(self, clinic_name: str) -> List[Dict[str, Any]]:
        """
        모두닥(modoodoc.com) 리뷰 수집

        Args:
            clinic_name: 한의원 이름

        Returns:
            수집된 리뷰 리스트
        """
        import requests
        from bs4 import BeautifulSoup

        results = []
        search_url = f"https://www.modoodoc.com/search?query={quote(clinic_name)}"

        try:
            response = requests.get(search_url, headers=self._get_headers(), timeout=15)

            if response.status_code == 403:
                logger.warning(f"Modoodoc blocked access (403) for '{clinic_name}'. Skipping.")
                return results

            if response.status_code != 200:
                logger.warning(f"Modoodoc returned status {response.status_code} for '{clinic_name}'")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # 검색 결과에서 한의원 페이지 링크 찾기
            clinic_links = soup.select("a[href*='/hospital/'], a[href*='/clinic/'], .hospital-item a, .search-result a")

            clinic_url = None
            for link in clinic_links:
                link_text = link.get_text(strip=True)
                href = link.get("href", "")
                if clinic_name[:2] in link_text:
                    clinic_url = href if href.startswith("http") else urljoin("https://www.modoodoc.com", href)
                    break

            if not clinic_url:
                logger.debug(f"Modoodoc: clinic page not found for '{clinic_name}'")
                return results

            time.sleep(1)  # Rate limit before fetching clinic page

            # 한의원 페이지에서 리뷰 수집
            clinic_response = requests.get(clinic_url, headers=self._get_headers(), timeout=15)
            if clinic_response.status_code != 200:
                return results

            clinic_soup = BeautifulSoup(clinic_response.text, 'html.parser')

            # 리뷰 요소 파싱
            review_items = clinic_soup.select(
                ".review-item, .review-card, .review-list-item, "
                "[class*='review'], .comment-item"
            )

            for review_el in review_items[:30]:  # 최대 30개 리뷰
                try:
                    # 리뷰 내용
                    content_el = review_el.select_one(
                        ".review-content, .review-text, .content, p, "
                        "[class*='content'], [class*='text']"
                    )
                    content = content_el.get_text(strip=True) if content_el else ""

                    if not content or len(content) < 5:
                        continue

                    # 평점
                    rating = None
                    rating_el = review_el.select_one(
                        ".rating, .star, .score, [class*='rating'], [class*='star']"
                    )
                    if rating_el:
                        # Try to extract numeric rating
                        rating_text = rating_el.get_text(strip=True)
                        nums = re.findall(r'[\d.]+', rating_text)
                        if nums:
                            rating = float(nums[0])
                        # Check style width for star rating
                        style = rating_el.get("style", "")
                        width_match = re.search(r'width:\s*([\d.]+)%', style)
                        if width_match and not rating:
                            rating = round(float(width_match.group(1)) / 20, 1)

                    # 작성자
                    reviewer_el = review_el.select_one(
                        ".reviewer, .author, .nickname, .user-name, "
                        "[class*='author'], [class*='nickname']"
                    )
                    reviewer = reviewer_el.get_text(strip=True) if reviewer_el else ""

                    # 날짜
                    date_el = review_el.select_one(
                        ".date, .time, .created, [class*='date'], [class*='time']"
                    )
                    review_date = date_el.get_text(strip=True) if date_el else ""

                    # 고유 URL 생성 (리뷰별 URL이 없는 경우)
                    review_url = f"{clinic_url}#review-{hashlib.md5(content[:50].encode()).hexdigest()[:8]}"

                    results.append({
                        "platform": "modoodoc",
                        "clinic_name": clinic_name,
                        "reviewer": reviewer,
                        "rating": rating,
                        "content": content[:500],
                        "treatment_type": self._classify_treatment(content),
                        "review_date": review_date,
                        "review_url": review_url,
                    })

                except Exception as e:
                    logger.debug(f"Error parsing Modoodoc review: {e}")
                    continue

        except requests.exceptions.Timeout:
            logger.warning(f"Modoodoc timeout for '{clinic_name}'")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Modoodoc request failed for '{clinic_name}': {e}")
        except Exception as e:
            logger.error(f"Modoodoc scraping error for '{clinic_name}': {e}")
            logger.error(traceback.format_exc())

        return results

    def scrape_goodoc(self, clinic_name: str) -> List[Dict[str, Any]]:
        """
        굿닥(goodoc.co.kr) 리뷰 수집

        Args:
            clinic_name: 한의원 이름

        Returns:
            수집된 리뷰 리스트
        """
        import requests
        from bs4 import BeautifulSoup

        results = []
        search_url = f"https://www.goodoc.co.kr/search?query={quote(clinic_name)}"

        try:
            response = requests.get(search_url, headers=self._get_headers(), timeout=15)

            if response.status_code == 403:
                logger.warning(f"Goodoc blocked access (403) for '{clinic_name}'. Skipping.")
                return results

            if response.status_code != 200:
                logger.warning(f"Goodoc returned status {response.status_code} for '{clinic_name}'")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')

            # 검색 결과에서 한의원 페이지 링크 찾기
            clinic_links = soup.select(
                "a[href*='/hospital/'], a[href*='/clinic/'], "
                ".hospital-card a, .search-item a, [class*='hospital'] a"
            )

            clinic_url = None
            for link in clinic_links:
                link_text = link.get_text(strip=True)
                href = link.get("href", "")
                if clinic_name[:2] in link_text:
                    clinic_url = href if href.startswith("http") else urljoin("https://www.goodoc.co.kr", href)
                    break

            if not clinic_url:
                logger.debug(f"Goodoc: clinic page not found for '{clinic_name}'")
                return results

            time.sleep(1)  # Rate limit before fetching clinic page

            # 한의원 페이지에서 리뷰 수집
            clinic_response = requests.get(clinic_url, headers=self._get_headers(), timeout=15)
            if clinic_response.status_code != 200:
                return results

            clinic_soup = BeautifulSoup(clinic_response.text, 'html.parser')

            # 전체 평점 추출
            overall_rating = None
            overall_el = clinic_soup.select_one(
                ".overall-rating, .total-score, .average-rating, "
                "[class*='overall'], [class*='average']"
            )
            if overall_el:
                nums = re.findall(r'[\d.]+', overall_el.get_text())
                if nums:
                    overall_rating = float(nums[0])

            # 리뷰 요소 파싱
            review_items = clinic_soup.select(
                ".review-item, .review-card, .review-list-item, "
                "[class*='review'], .comment-card"
            )

            for review_el in review_items[:30]:  # 최대 30개 리뷰
                try:
                    # 리뷰 내용
                    content_el = review_el.select_one(
                        ".review-content, .review-text, .content, p, "
                        "[class*='content'], [class*='text']"
                    )
                    content = content_el.get_text(strip=True) if content_el else ""

                    if not content or len(content) < 5:
                        continue

                    # 평점 (개별 리뷰)
                    rating = None
                    rating_el = review_el.select_one(
                        ".rating, .star, .score, [class*='rating'], [class*='star']"
                    )
                    if rating_el:
                        rating_text = rating_el.get_text(strip=True)
                        nums = re.findall(r'[\d.]+', rating_text)
                        if nums:
                            rating = float(nums[0])
                        # Star width percentage
                        style = rating_el.get("style", "")
                        width_match = re.search(r'width:\s*([\d.]+)%', style)
                        if width_match and not rating:
                            rating = round(float(width_match.group(1)) / 20, 1)

                    # 개별 평점이 없으면 전체 평점 사용
                    if rating is None:
                        rating = overall_rating

                    # 작성자
                    reviewer_el = review_el.select_one(
                        ".reviewer, .author, .nickname, .user-name, "
                        "[class*='author'], [class*='nickname']"
                    )
                    reviewer = reviewer_el.get_text(strip=True) if reviewer_el else ""

                    # 날짜
                    date_el = review_el.select_one(
                        ".date, .time, .created, [class*='date'], [class*='time']"
                    )
                    review_date = date_el.get_text(strip=True) if date_el else ""

                    # 고유 URL 생성
                    review_url = f"{clinic_url}#review-{hashlib.md5(content[:50].encode()).hexdigest()[:8]}"

                    results.append({
                        "platform": "goodoc",
                        "clinic_name": clinic_name,
                        "reviewer": reviewer,
                        "rating": rating,
                        "content": content[:500],
                        "treatment_type": self._classify_treatment(content),
                        "review_date": review_date,
                        "review_url": review_url,
                    })

                except Exception as e:
                    logger.debug(f"Error parsing Goodoc review: {e}")
                    continue

        except requests.exceptions.Timeout:
            logger.warning(f"Goodoc timeout for '{clinic_name}'")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Goodoc request failed for '{clinic_name}': {e}")
        except Exception as e:
            logger.error(f"Goodoc scraping error for '{clinic_name}': {e}")
            logger.error(traceback.format_exc())

        return results

    def save_review(self, review: Dict[str, Any], is_our_clinic: bool) -> bool:
        """
        리뷰를 DB에 저장 (중복 방지)

        Returns:
            True if saved, False if duplicate or error
        """
        review_url = review.get("review_url", "")
        if not review_url:
            return False

        url_hash = self._url_hash(review_url)

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO medical_platform_reviews
                    (platform, clinic_name, is_our_clinic, reviewer, rating, content,
                     treatment_type, review_date, review_url, url_hash, scanned_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    review["platform"],
                    review["clinic_name"],
                    1 if is_our_clinic else 0,
                    review.get("reviewer", ""),
                    review.get("rating"),
                    review.get("content", ""),
                    review.get("treatment_type", ""),
                    review.get("review_date", ""),
                    review_url,
                    url_hash,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error saving medical review: {e}")
            return False

    def run(self):
        """전체 의료 리뷰 플랫폼 모니터링 실행"""
        if not self.search_targets:
            logger.warning("No search targets configured (no business name or competitors).")
            print("[Medical Review Monitor] No clinic names configured.")
            return

        print(f"[{datetime.now()}] Medical Review Monitor 시작")
        print(f"  우리 한의원: {self.business_name}")
        print(f"  경쟁사: {len(self.competitor_names)}개")
        print(f"  총 검색 대상: {len(self.search_targets)}개")
        print()

        total_saved = 0
        our_reviews = 0
        competitor_reviews = 0

        for i, target in enumerate(self.search_targets, 1):
            clinic_name = target["name"]
            is_ours = target["is_our_clinic"]
            label = "우리" if is_ours else "경쟁사"

            print(f"[{i}/{len(self.search_targets)}] '{clinic_name}' ({label}) 리뷰 수집 중...")

            # --- Platform 1: 모두닥 ---
            try:
                modoodoc_reviews = self.scrape_modoodoc(clinic_name)
                saved = 0
                for review in modoodoc_reviews:
                    if self.save_review(review, is_ours):
                        saved += 1
                        if is_ours:
                            our_reviews += 1
                        else:
                            competitor_reviews += 1
                print(f"  [모두닥] {saved}건 신규 저장 (총 {len(modoodoc_reviews)}건 수집)")
                total_saved += saved
            except Exception as e:
                logger.error(f"Modoodoc monitoring error for '{clinic_name}': {e}")
                logger.error(traceback.format_exc())
                print(f"  [모두닥] 오류 발생: {e}")

            time.sleep(3)  # Rate limit between platforms

            # --- Platform 2: 굿닥 ---
            try:
                goodoc_reviews = self.scrape_goodoc(clinic_name)
                saved = 0
                for review in goodoc_reviews:
                    if self.save_review(review, is_ours):
                        saved += 1
                        if is_ours:
                            our_reviews += 1
                        else:
                            competitor_reviews += 1
                print(f"  [굿닥] {saved}건 신규 저장 (총 {len(goodoc_reviews)}건 수집)")
                total_saved += saved
            except Exception as e:
                logger.error(f"Goodoc monitoring error for '{clinic_name}': {e}")
                logger.error(traceback.format_exc())
                print(f"  [굿닥] 오류 발생: {e}")

            # Rate limit between clinics
            if i < len(self.search_targets):
                time.sleep(3)

            print()

        print(f"[{datetime.now()}] Medical Review Monitor 완료")
        print(f"  총 신규 저장: {total_saved}건")
        print(f"  우리 한의원 리뷰: {our_reviews}건")
        print(f"  경쟁사 리뷰: {competitor_reviews}건")

    def get_review_summary(self, clinic_name: str = None) -> Dict[str, Any]:
        """리뷰 요약 조회"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                if clinic_name:
                    cursor.execute('''
                        SELECT platform, COUNT(*) as count, AVG(rating) as avg_rating
                        FROM medical_platform_reviews
                        WHERE clinic_name = ?
                        GROUP BY platform
                    ''', (clinic_name,))
                else:
                    cursor.execute('''
                        SELECT clinic_name, platform, COUNT(*) as count, AVG(rating) as avg_rating,
                               is_our_clinic
                        FROM medical_platform_reviews
                        GROUP BY clinic_name, platform
                        ORDER BY is_our_clinic DESC, count DESC
                    ''')

                rows = cursor.fetchall()
                return {"reviews": [dict(row) for row in rows]}
        except Exception as e:
            logger.error(f"Error fetching review summary: {e}")
            return {"reviews": []}


if __name__ == "__main__":
    monitor = MedicalReviewMonitor()
    monitor.run()
