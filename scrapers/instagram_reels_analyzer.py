"""
Instagram Reels Analyzer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[멀티채널 확장] 인스타그램 릴스/스토리 분석기
- 경쟁사 릴스 콘텐츠 수집 및 분석
- 해시태그 트렌드 추적
- 참여율 기반 성과 분석

사용법:
    python instagram_reels_analyzer.py --account <username>
    python instagram_reels_analyzer.py --trending
"""

import sqlite3
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import time
import random

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'
CONFIG_PATH = PROJECT_ROOT / 'config' / 'config.json'
SECRETS_PATH = PROJECT_ROOT / 'config' / 'secrets.json'

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class InstagramReelsAnalyzer:
    """인스타그램 릴스 분석기"""

    def __init__(self):
        self.db_path = str(DB_PATH)
        self.api_client = None
        self._init_api_client()
        self._ensure_tables()

    def _init_api_client(self):
        """Instagram Graph API 클라이언트 초기화"""
        try:
            # secrets.json에서 API 설정 로드
            if SECRETS_PATH.exists():
                with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
                    secrets = json.load(f)

                access_token = secrets.get('INSTAGRAM_ACCESS_TOKEN')
                if access_token:
                    self.access_token = access_token
                    self.api_configured = True
                    logger.info("Instagram Graph API 설정됨")
                    return

            self.api_configured = False
            logger.warning("Instagram API 설정이 없습니다. 스크래핑 모드로 실행합니다.")

        except Exception as e:
            logger.error(f"API 클라이언트 초기화 오류: {e}")
            self.api_configured = False

    def _ensure_tables(self):
        """DB 테이블 확인/생성"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # instagram_reels_analysis 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS instagram_reels_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_username TEXT NOT NULL,
                    reel_id TEXT NOT NULL UNIQUE,
                    reel_url TEXT,
                    caption TEXT,
                    hashtags TEXT DEFAULT '[]',
                    view_count INTEGER DEFAULT 0,
                    like_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    share_count INTEGER DEFAULT 0,
                    save_count INTEGER DEFAULT 0,
                    engagement_rate REAL DEFAULT 0,
                    duration_seconds INTEGER,
                    audio_name TEXT,
                    audio_is_original INTEGER DEFAULT 0,
                    thumbnail_url TEXT,
                    posted_at TIMESTAMP,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # instagram_hashtag_trends 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS instagram_hashtag_trends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hashtag TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    post_count INTEGER DEFAULT 0,
                    avg_engagement_rate REAL DEFAULT 0,
                    top_posts_engagement REAL DEFAULT 0,
                    growth_rate REAL DEFAULT 0,
                    is_trending INTEGER DEFAULT 0,
                    trend_score REAL DEFAULT 0,
                    related_hashtags TEXT DEFAULT '[]',
                    tracked_date TEXT DEFAULT (DATE('now')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(hashtag, tracked_date)
                )
            """)

            conn.commit()
            logger.debug("DB 테이블 확인 완료")

        except Exception as e:
            logger.error(f"DB 테이블 생성 오류: {e}")
            raise

        finally:
            if conn:
                conn.close()

    def analyze_account_reels(self, username: str, limit: int = 20) -> Dict[str, Any]:
        """
        특정 계정의 릴스 분석

        Args:
            username: Instagram 사용자명
            limit: 분석할 릴스 수

        Returns:
            분석 결과
        """
        logger.info(f"계정 분석 시작: @{username}")

        if self.api_configured:
            return self._analyze_via_api(username, limit)
        else:
            return self._analyze_via_scraping(username, limit)

    def _analyze_via_api(self, username: str, limit: int) -> Dict[str, Any]:
        """Graph API를 통한 분석 (비즈니스 계정만 가능)"""
        # 현재는 기본 구조만 제공
        # 실제 구현은 Instagram Graph API 문서 참조
        return {
            'success': False,
            'error': 'Graph API 분석은 비즈니스 계정 연동 후 사용 가능합니다.',
            'username': username
        }

    def _analyze_via_scraping(self, username: str, limit: int) -> Dict[str, Any]:
        """웹 스크래핑을 통한 분석"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # Chrome 설정
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            # [Phase 2 안정성] driver 초기화를 try 블록 안으로 이동
            driver = None
            reels_data = []

            try:
                driver = webdriver.Chrome(options=chrome_options)
                # 프로필 페이지 접근
                profile_url = f"https://www.instagram.com/{username}/reels/"
                driver.get(profile_url)
                time.sleep(3)

                # 로그인 팝업 닫기 시도
                try:
                    close_btn = driver.find_element(By.CSS_SELECTOR, '[aria-label="닫기"]')
                    close_btn.click()
                    time.sleep(1)
                except Exception:
                    pass

                # 릴스 썸네일 수집
                wait = WebDriverWait(driver, 10)
                reel_links = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[href*="/reel/"]'))
                )

                collected_urls = []
                for link in reel_links[:limit]:
                    try:
                        href = link.get_attribute('href')
                        if href and '/reel/' in href and href not in collected_urls:
                            collected_urls.append(href)
                    except Exception:
                        continue

                logger.info(f"발견된 릴스: {len(collected_urls)}개")

                # 각 릴스 분석
                for i, reel_url in enumerate(collected_urls):
                    try:
                        reel_data = self._scrape_reel(driver, reel_url)
                        if reel_data:
                            reel_data['account_username'] = username
                            reels_data.append(reel_data)
                            self._save_reel(reel_data)
                            logger.info(f"  [{i+1}/{len(collected_urls)}] 릴스 분석 완료")

                        # 요청 간 랜덤 딜레이
                        time.sleep(random.uniform(2, 4))

                    except Exception as e:
                        logger.warning(f"  [{i+1}] 릴스 분석 실패: {e}")
                        continue

            finally:
                # [Phase 2] driver가 초기화되었을 때만 quit 호출
                if driver:
                    driver.quit()

            return {
                'success': True,
                'username': username,
                'reels_analyzed': len(reels_data),
                'reels': reels_data
            }

        except ImportError:
            return {
                'success': False,
                'error': 'Selenium이 설치되어 있지 않습니다. pip install selenium',
                'username': username
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'username': username
            }

    def _scrape_reel(self, driver, reel_url: str) -> Optional[Dict[str, Any]]:
        """개별 릴스 스크래핑"""
        try:
            driver.get(reel_url)
            time.sleep(2)

            # 릴스 ID 추출
            reel_id = reel_url.split('/reel/')[-1].rstrip('/')

            # 기본 데이터
            reel_data = {
                'reel_id': reel_id,
                'reel_url': reel_url,
                'caption': '',
                'hashtags': [],
                'view_count': 0,
                'like_count': 0,
                'comment_count': 0,
                'engagement_rate': 0
            }

            # 캡션 추출
            try:
                caption_elem = driver.find_element(By.CSS_SELECTOR, 'h1, span[class*="Caption"]')
                reel_data['caption'] = caption_elem.text
                # 해시태그 추출
                hashtags = [word[1:] for word in reel_data['caption'].split() if word.startswith('#')]
                reel_data['hashtags'] = hashtags
            except Exception:
                pass

            # 조회수/좋아요수 추출 (Instagram UI 구조에 따라 조정 필요)
            try:
                metrics = driver.find_elements(By.CSS_SELECTOR, 'span[class*="Count"], span[class*="count"]')
                for metric in metrics:
                    text = metric.text.lower()
                    if '회' in text or 'view' in text:
                        reel_data['view_count'] = self._parse_count(text)
                    elif '좋아요' in text or 'like' in text:
                        reel_data['like_count'] = self._parse_count(text)
            except Exception:
                pass

            # 참여율 계산
            if reel_data['view_count'] > 0:
                reel_data['engagement_rate'] = round(
                    (reel_data['like_count'] + reel_data['comment_count']) / reel_data['view_count'] * 100, 2
                )

            reel_data['analyzed_at'] = datetime.now().isoformat()

            return reel_data

        except Exception as e:
            logger.error(f"릴스 스크래핑 오류: {e}")
            return None

    def _parse_count(self, text: str) -> int:
        """숫자 문자열 파싱 (예: '1.2만' -> 12000)"""
        try:
            text = text.replace(',', '').replace(' ', '')
            if '만' in text:
                num = float(text.replace('만', '').replace('회', '').replace('개', ''))
                return int(num * 10000)
            elif 'k' in text.lower():
                num = float(text.lower().replace('k', '').replace('회', '').replace('개', ''))
                return int(num * 1000)
            elif 'm' in text.lower():
                num = float(text.lower().replace('m', '').replace('회', '').replace('개', ''))
                return int(num * 1000000)
            else:
                return int(''.join(filter(str.isdigit, text)) or 0)
        except Exception:
            return 0

    def _save_reel(self, reel_data: Dict[str, Any]):
        """릴스 데이터 저장"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO instagram_reels_analysis
                (account_username, reel_id, reel_url, caption, hashtags,
                 view_count, like_count, comment_count, engagement_rate, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reel_data.get('account_username'),
                reel_data.get('reel_id'),
                reel_data.get('reel_url'),
                reel_data.get('caption'),
                json.dumps(reel_data.get('hashtags', []), ensure_ascii=False),
                reel_data.get('view_count', 0),
                reel_data.get('like_count', 0),
                reel_data.get('comment_count', 0),
                reel_data.get('engagement_rate', 0),
                reel_data.get('analyzed_at')
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"릴스 저장 오류: {e}")
        finally:
            conn.close()

    def analyze_hashtag_trends(self, hashtags: List[str] = None) -> Dict[str, Any]:
        """
        해시태그 트렌드 분석

        Args:
            hashtags: 분석할 해시태그 목록 (None이면 DB에서 수집)

        Returns:
            트렌드 분석 결과
        """
        logger.info("해시태그 트렌드 분석 시작")

        if hashtags is None:
            # DB에서 최근 수집된 해시태그 가져오기
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT hashtags FROM instagram_reels_analysis
                    WHERE analyzed_at > datetime('now', '-7 days')
                """)
                rows = cursor.fetchall()
            finally:
                if conn:
                    conn.close()

            all_hashtags = []
            for row in rows:
                try:
                    tags = json.loads(row[0]) if row[0] else []
                    all_hashtags.extend(tags)
                except (json.JSONDecodeError, TypeError):
                    continue

            # 빈도순 정렬
            from collections import Counter
            hashtag_counts = Counter(all_hashtags)
            hashtags = [tag for tag, count in hashtag_counts.most_common(50)]

        if not hashtags:
            return {
                'success': False,
                'error': '분석할 해시태그가 없습니다',
                'trends': []
            }

        trends = []
        conn = None

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            for tag in hashtags:
                try:
                    # 해시태그별 통계 계산
                    cursor.execute("""
                        SELECT
                            COUNT(*) as post_count,
                            AVG(engagement_rate) as avg_engagement,
                            MAX(engagement_rate) as top_engagement
                        FROM instagram_reels_analysis
                        WHERE hashtags LIKE ?
                        AND analyzed_at > datetime('now', '-7 days')
                    """, (f'%"{tag}"%',))

                    row = cursor.fetchone()
                    if row and row[0] > 0:
                        trend_data = {
                            'hashtag': tag,
                            'post_count': row[0],
                            'avg_engagement_rate': round(row[1] or 0, 2),
                            'top_posts_engagement': round(row[2] or 0, 2),
                            'is_trending': row[0] >= 5,  # 5개 이상이면 트렌딩
                            'trend_score': round((row[0] * 0.3 + (row[1] or 0) * 0.7), 2)
                        }
                        trends.append(trend_data)
                        self._save_hashtag_trend(trend_data)

                except Exception as e:
                    logger.warning(f"해시태그 '{tag}' 분석 오류: {e}")
                    continue

            # 트렌드 점수순 정렬
            trends.sort(key=lambda x: x['trend_score'], reverse=True)

            return {
                'success': True,
                'analyzed': len(trends),
                'trends': trends[:30]  # 상위 30개
            }

        except Exception as e:
            logger.error(f"해시태그 트렌드 분석 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'trends': trends
            }

        finally:
            if conn:
                conn.close()

    def _save_hashtag_trend(self, trend_data: Dict[str, Any]):
        """해시태그 트렌드 저장"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO instagram_hashtag_trends
                (hashtag, post_count, avg_engagement_rate, top_posts_engagement,
                 is_trending, trend_score, tracked_date)
                VALUES (?, ?, ?, ?, ?, ?, date('now'))
            """, (
                trend_data['hashtag'],
                trend_data['post_count'],
                trend_data['avg_engagement_rate'],
                trend_data['top_posts_engagement'],
                1 if trend_data['is_trending'] else 0,
                trend_data['trend_score']
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"트렌드 저장 오류: {e}")
        finally:
            conn.close()

    def get_performance_report(self, username: str = None, days: int = 30) -> Dict[str, Any]:
        """
        릴스 성과 리포트 생성

        Args:
            username: 특정 계정 필터 (None이면 전체)
            days: 분석 기간

        Returns:
            성과 리포트
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where_clause = f"WHERE analyzed_at > datetime('now', '-{days} days')"
        if username:
            where_clause += f" AND account_username = '{username}'"

        # 전체 통계
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_reels,
                AVG(view_count) as avg_views,
                AVG(like_count) as avg_likes,
                AVG(engagement_rate) as avg_engagement,
                MAX(engagement_rate) as top_engagement,
                COUNT(DISTINCT account_username) as accounts
            FROM instagram_reels_analysis
            {where_clause}
        """)
        stats = dict(cursor.fetchone())

        # Top 10 릴스
        cursor.execute(f"""
            SELECT account_username, reel_url, caption, view_count, like_count, engagement_rate
            FROM instagram_reels_analysis
            {where_clause}
            ORDER BY engagement_rate DESC
            LIMIT 10
        """)
        top_reels = [dict(row) for row in cursor.fetchall()]

        # 해시태그 트렌드
        cursor.execute("""
            SELECT hashtag, post_count, avg_engagement_rate, trend_score
            FROM instagram_hashtag_trends
            WHERE tracked_date = date('now')
            ORDER BY trend_score DESC
            LIMIT 10
        """)
        trending_hashtags = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            'success': True,
            'period_days': days,
            'username': username,
            'stats': stats,
            'top_reels': top_reels,
            'trending_hashtags': trending_hashtags
        }


def main():
    """메인 실행"""
    parser = argparse.ArgumentParser(description='Instagram Reels Analyzer')
    parser.add_argument('--account', '-a', help='분석할 Instagram 계정')
    parser.add_argument('--trending', '-t', action='store_true', help='해시태그 트렌드 분석')
    parser.add_argument('--report', '-r', action='store_true', help='성과 리포트 생성')
    parser.add_argument('--limit', '-l', type=int, default=20, help='릴스 분석 수 (기본: 20)')
    parser.add_argument('--days', '-d', type=int, default=30, help='리포트 기간 (기본: 30일)')

    args = parser.parse_args()
    analyzer = InstagramReelsAnalyzer()

    if args.account:
        print(f"\n{'='*60}")
        print(f"📸 Instagram Reels Analyzer - @{args.account}")
        print(f"{'='*60}\n")

        result = analyzer.analyze_account_reels(args.account, args.limit)

        if result['success']:
            print(f"\n✅ 분석 완료: {result['reels_analyzed']}개 릴스")
        else:
            print(f"\n❌ 분석 실패: {result.get('error')}")

    elif args.trending:
        print(f"\n{'='*60}")
        print("📈 Instagram Hashtag Trends")
        print(f"{'='*60}\n")

        result = analyzer.analyze_hashtag_trends()

        if result['success']:
            print(f"분석된 해시태그: {result['analyzed']}개\n")
            for i, trend in enumerate(result['trends'][:20], 1):
                emoji = "🔥" if trend['is_trending'] else "📊"
                print(f"{i:2}. {emoji} #{trend['hashtag']}")
                print(f"    게시물: {trend['post_count']} | 참여율: {trend['avg_engagement_rate']}% | 점수: {trend['trend_score']}")
        else:
            print(f"❌ 분석 실패: {result.get('error')}")

    elif args.report:
        print(f"\n{'='*60}")
        print(f"📊 Instagram Reels Performance Report ({args.days}일)")
        print(f"{'='*60}\n")

        result = analyzer.get_performance_report(days=args.days)

        if result['success']:
            stats = result['stats']
            print(f"총 릴스: {stats['total_reels']}개")
            print(f"평균 조회수: {int(stats['avg_views'] or 0):,}")
            print(f"평균 좋아요: {int(stats['avg_likes'] or 0):,}")
            print(f"평균 참여율: {stats['avg_engagement'] or 0:.2f}%")
            print(f"\n🏆 Top 10 릴스:")
            for i, reel in enumerate(result['top_reels'], 1):
                print(f"  {i}. @{reel['account_username']} - {reel['engagement_rate']}%")
        else:
            print("데이터가 없습니다.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
