"""
Instagram Competitor Analyzer

경쟁사 Instagram 계정을 분석하여 포스팅 전략, 해시태그, 참여율 등을 추적합니다.

Features:
- 경쟁사 계정 포스트 수집
- 해시태그 역분석
- 참여율 비교
- 인기 콘텐츠 분석
"""

import sys
import os
import json
import time
import random
import re
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager


@dataclass
class CompetitorPost:
    """경쟁사 포스트 데이터"""
    competitor_name: str
    username: str
    post_id: str
    post_url: str
    caption: str
    hashtags: List[str]
    like_count: int
    comment_count: int
    media_type: str
    posted_at: str


class InstagramCompetitorAnalyzer:
    """Instagram 경쟁사 분석기"""

    def __init__(self):
        self.db = DatabaseManager()
        self.competitors = self._load_competitors()
        self.api_client = None
        self.use_api = False

        # API 클라이언트 초기화
        self._init_api()

    def _load_competitors(self) -> List[Dict]:
        """targets.json에서 Instagram 경쟁사 목록 로드"""
        competitors = []
        try:
            targets_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'targets.json'
            )
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for target in data.get('targets', []):
                monitor_urls = target.get('monitor_urls', {})
                instagram_url = monitor_urls.get('instagram', '')

                # Instagram URL에서 username 추출
                if instagram_url:
                    username = self._extract_username(instagram_url)
                    if username:
                        competitors.append({
                            'name': target.get('name', ''),
                            'username': username,
                            'priority': target.get('priority', 'Medium'),
                            'category': target.get('category', '')
                        })

            # Instagram handle이 별도로 지정된 경우도 처리
            if 'instagram_competitors' in data:
                for comp in data['instagram_competitors']:
                    competitors.append(comp)

            print(f"[{datetime.now()}] Loaded {len(competitors)} Instagram competitors")
            return competitors

        except Exception as e:
            print(f"[{datetime.now()}] Failed to load competitors: {e}")
            return []

    def _extract_username(self, url: str) -> Optional[str]:
        """Instagram URL에서 username 추출"""
        # https://www.instagram.com/username
        # https://instagram.com/username/
        patterns = [
            r'instagram\.com/([a-zA-Z0-9._]+)/?',
            r'@([a-zA-Z0-9._]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _init_api(self):
        """Instagram Graph API 초기화"""
        try:
            from scrapers.instagram_api_client import InstagramGraphAPI
            self.api_client = InstagramGraphAPI()

            if self.api_client.is_configured():
                result = self.api_client.test_connection()
                if result['success']:
                    self.use_api = True
                    print(f"[{datetime.now()}] Instagram API connected")
                else:
                    print(f"[{datetime.now()}] API connection failed, using scraper fallback")
        except Exception as e:
            print(f"[{datetime.now()}] API init failed: {e}")

    def _extract_hashtags(self, caption: str) -> List[str]:
        """캡션에서 해시태그 추출"""
        if not caption:
            return []
        hashtags = re.findall(r'#([가-힣a-zA-Z0-9_]+)', caption)
        return hashtags

    def run(self, limit_per_competitor: int = 20):
        """
        전체 경쟁사 분석 실행

        Args:
            limit_per_competitor: 경쟁사당 수집할 포스트 수
        """
        print(f"\n{'='*60}")
        print(f"🔍 Instagram 경쟁사 분석 시작")
        print(f"{'='*60}")
        print(f"   경쟁사 수: {len(self.competitors)}")
        print(f"   포스트 제한: {limit_per_competitor}/경쟁사")
        print(f"   모드: {'API' if self.use_api else 'Scraper'}")
        print(f"{'='*60}\n")

        total_collected = 0

        for comp in self.competitors:
            name = comp['name']
            username = comp['username']
            priority = comp.get('priority', 'Medium')

            print(f"\n📊 [{priority}] {name} (@{username})")
            print(f"   {'─'*40}")

            try:
                posts = self._collect_posts(username, limit_per_competitor)

                for post in posts:
                    post.competitor_name = name

                    # DB 저장
                    self.db.insert_instagram_competitor({
                        'competitor_name': name,
                        'username': username,
                        'post_id': post.post_id,
                        'post_url': post.post_url,
                        'caption': post.caption,
                        'hashtags': post.hashtags,
                        'like_count': post.like_count,
                        'comment_count': post.comment_count,
                        'media_type': post.media_type,
                        'posted_at': post.posted_at
                    })
                    total_collected += 1

                print(f"   ✅ 수집: {len(posts)}개 포스트")

                # 간단한 통계
                if posts:
                    avg_likes = sum(p.like_count for p in posts) / len(posts)
                    avg_comments = sum(p.comment_count for p in posts) / len(posts)
                    all_hashtags = []
                    for p in posts:
                        all_hashtags.extend(p.hashtags)

                    print(f"   📈 평균 좋아요: {avg_likes:.0f}")
                    print(f"   💬 평균 댓글: {avg_comments:.0f}")
                    print(f"   #️⃣ 총 해시태그: {len(set(all_hashtags))}종류")

            except Exception as e:
                print(f"   ❌ 오류: {e}")

            # Rate limiting
            time.sleep(2 + random.random() * 2)

        # 최종 리포트
        self._print_summary_report()

        print(f"\n{'='*60}")
        print(f"✅ 완료: 총 {total_collected}개 포스트 수집")
        print(f"{'='*60}\n")

        return total_collected

    def _collect_posts(self, username: str, limit: int) -> List[CompetitorPost]:
        """
        경쟁사 포스트 수집

        Note: Instagram Graph API는 다른 비즈니스 계정 포스트에
        직접 접근할 수 없어서 해시태그 기반 우회 또는
        웹 스크래핑이 필요합니다.
        """
        posts = []

        # 방법 1: 해시태그 기반 수집 (API 가능)
        if self.use_api and self.api_client:
            posts = self._collect_via_hashtag_search(username, limit)

        # 방법 2: 웹 스크래핑 폴백
        if not posts:
            posts = self._collect_via_scraper(username, limit)

        return posts

    def _collect_via_hashtag_search(self, username: str, limit: int) -> List[CompetitorPost]:
        """
        해시태그 검색을 통한 경쟁사 포스트 수집

        경쟁사 username을 해시태그로 검색하거나
        관련 키워드로 검색 후 username 필터링
        """
        posts = []

        try:
            # 경쟁사 관련 해시태그로 검색
            search_tags = [username, username.replace('_', '')]

            for tag in search_tags:
                try:
                    media_list = self.api_client.search_hashtag(tag, limit=limit)

                    for media in media_list:
                        caption = media.get('caption', '') or ''
                        hashtags = self._extract_hashtags(caption)

                        posts.append(CompetitorPost(
                            competitor_name='',
                            username=username,
                            post_id=media.get('id', ''),
                            post_url=media.get('permalink', ''),
                            caption=caption,
                            hashtags=hashtags,
                            like_count=media.get('like_count', 0),
                            comment_count=media.get('comments_count', 0),
                            media_type=media.get('media_type', 'IMAGE'),
                            posted_at=media.get('timestamp', '')
                        ))

                        if len(posts) >= limit:
                            break

                except Exception as e:
                    print(f"      해시태그 #{tag} 검색 실패: {e}")

                if len(posts) >= limit:
                    break

        except Exception as e:
            print(f"      API 수집 실패: {e}")

        return posts[:limit]

    def _collect_via_scraper(self, username: str, limit: int) -> List[CompetitorPost]:
        """
        웹 스크래핑을 통한 포스트 수집 (Google 우회)
        """
        posts = []

        try:
            from retry_helper import SafeSeleniumDriver
            from selenium.webdriver.common.by import By

            with SafeSeleniumDriver(headless=True, mobile=True) as driver:
                # Google에서 Instagram 프로필 포스트 검색
                query = f'site:instagram.com/p/ "{username}"'
                search_url = f"https://www.google.com/search?q={query}&tbs=qdr:m"

                driver.get(search_url)
                time.sleep(3 + random.random() * 2)

                results = driver.find_elements(By.CSS_SELECTOR, ".g")

                for res in results[:limit]:
                    try:
                        title_el = res.find_element(By.TAG_NAME, "h3")
                        link_el = res.find_element(By.TAG_NAME, "a")

                        title = title_el.text
                        link = link_el.get_attribute("href")

                        if "/p/" not in link and "/reel/" not in link:
                            continue

                        # Post ID 추출
                        post_id_match = re.search(r'/p/([a-zA-Z0-9_-]+)', link)
                        post_id = post_id_match.group(1) if post_id_match else ''

                        # Snippet에서 해시태그 추출
                        snippet = ""
                        try:
                            snippet_el = res.find_element(By.CSS_SELECTOR, ".VwiC3b")
                            snippet = snippet_el.text
                        except Exception:
                            pass

                        hashtags = self._extract_hashtags(snippet)

                        posts.append(CompetitorPost(
                            competitor_name='',
                            username=username,
                            post_id=post_id,
                            post_url=link,
                            caption=snippet,
                            hashtags=hashtags,
                            like_count=0,  # Google에서 알 수 없음
                            comment_count=0,
                            media_type='UNKNOWN',
                            posted_at=datetime.now().strftime("%Y-%m-%d")
                        ))

                    except Exception:
                        continue

        except ImportError:
            print(f"      Selenium not available for scraping")
        except Exception as e:
            print(f"      스크래핑 실패: {e}")

        return posts

    def _print_summary_report(self):
        """분석 요약 리포트 출력"""
        print(f"\n{'='*60}")
        print(f"📊 경쟁사 분석 요약 리포트")
        print(f"{'='*60}")

        stats = self.db.get_instagram_competitor_stats(days=30)
        hashtag_analysis = self.db.get_instagram_hashtag_analysis(days=30)
        content_analysis = self.db.get_instagram_content_analysis(days=30)

        # 경쟁사별 통계
        print(f"\n🏆 경쟁사 참여율 순위")
        print(f"   {'─'*45}")
        for i, comp in enumerate(stats.get('competitors', [])[:5], 1):
            engagement = comp['avg_likes'] + comp['avg_comments']
            print(f"   {i}. {comp['name']} (@{comp['username']})")
            print(f"      포스트: {comp['post_count']}개 | "
                  f"평균 좋아요: {comp['avg_likes']:.0f} | "
                  f"평균 댓글: {comp['avg_comments']:.0f}")
            print(f"      포스팅 빈도: {comp['posting_frequency']}/주")

        # 인기 해시태그
        print(f"\n#️⃣ 경쟁사 인기 해시태그 TOP 10")
        print(f"   {'─'*45}")
        for i, tag in enumerate(hashtag_analysis.get('popular_hashtags', [])[:10], 1):
            print(f"   {i}. #{tag['tag']} (사용: {tag['count']}회, 평균 참여: {tag['avg_engagement']:.0f})")

        # 인기 콘텐츠
        print(f"\n🔥 가장 인기있는 포스트 TOP 5")
        print(f"   {'─'*45}")
        for i, post in enumerate(content_analysis.get('top_posts', [])[:5], 1):
            total_eng = post['likes'] + post['comments']
            print(f"   {i}. {post['competitor']} - {post['type']}")
            print(f"      ❤️ {post['likes']} | 💬 {post['comments']} | 총 참여: {total_eng}")
            if post['caption']:
                print(f"      \"{post['caption'][:60]}...\"")

        # 콘텐츠 유형 분포
        print(f"\n📸 콘텐츠 유형 분포")
        print(f"   {'─'*45}")
        for media_type, count in content_analysis.get('content_types', {}).items():
            print(f"   {media_type}: {count}개")

    def analyze_hashtag_gap(self, our_hashtags: List[str]) -> Dict:
        """
        우리가 사용하지 않는 경쟁사 해시태그 분석

        Args:
            our_hashtags: 우리가 사용하는 해시태그 목록

        Returns:
            dict: {
                'missing_hashtags': [우리가 안 쓰는 인기 해시태그],
                'opportunity_score': float
            }
        """
        hashtag_analysis = self.db.get_instagram_hashtag_analysis(days=30)

        our_set = set(h.lower().replace('#', '') for h in our_hashtags)
        competitor_hashtags = hashtag_analysis.get('popular_hashtags', [])

        missing = []
        for tag_data in competitor_hashtags:
            tag = tag_data['tag'].lower()
            if tag not in our_set:
                missing.append({
                    'tag': tag_data['tag'],
                    'competitor_usage': tag_data['count'],
                    'avg_engagement': tag_data['avg_engagement']
                })

        # 기회 점수 계산 (놓치고 있는 인기 해시태그가 많을수록 높음)
        opportunity = min(100, len(missing) * 5)

        return {
            'missing_hashtags': missing,
            'opportunity_score': opportunity,
            'recommendation': self._generate_hashtag_recommendations(missing[:10])
        }

    def _generate_hashtag_recommendations(self, missing_tags: List[Dict]) -> str:
        """해시태그 추천 메시지 생성"""
        if not missing_tags:
            return "경쟁사 대비 해시태그 커버리지가 우수합니다."

        top_tags = [f"#{t['tag']}" for t in missing_tags[:5]]
        return f"추천 해시태그: {', '.join(top_tags)}"


def add_instagram_competitor(name: str, username: str, priority: str = "Medium"):
    """
    targets.json에 Instagram 경쟁사 추가

    Usage:
        python instagram_competitor_analyzer.py --add "미올한의원" "miol_clinic" "High"
    """
    targets_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'targets.json'
    )

    with open(targets_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # instagram_competitors 섹션 추가 (없으면)
    if 'instagram_competitors' not in data:
        data['instagram_competitors'] = []

    # 중복 체크
    existing = [c['username'] for c in data['instagram_competitors']]
    if username in existing:
        print(f"이미 존재하는 경쟁사: @{username}")
        return False

    data['instagram_competitors'].append({
        'name': name,
        'username': username,
        'priority': priority
    })

    with open(targets_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"✅ 경쟁사 추가됨: {name} (@{username}) - {priority}")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Instagram 경쟁사 분석")
    parser.add_argument('--add', nargs=3, metavar=('NAME', 'USERNAME', 'PRIORITY'),
                        help='새 경쟁사 추가')
    parser.add_argument('--limit', type=int, default=20,
                        help='경쟁사당 수집할 포스트 수 (기본: 20)')
    parser.add_argument('--report', action='store_true',
                        help='기존 데이터로 리포트만 출력')

    args = parser.parse_args()

    if args.add:
        add_instagram_competitor(args.add[0], args.add[1], args.add[2])
    elif args.report:
        analyzer = InstagramCompetitorAnalyzer()
        analyzer._print_summary_report()
    else:
        analyzer = InstagramCompetitorAnalyzer()
        analyzer.run(limit_per_competitor=args.limit)
