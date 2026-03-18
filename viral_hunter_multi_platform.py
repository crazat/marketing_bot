#!/usr/bin/env python3
"""
Viral Hunter - 멀티 플랫폼 확장 버전
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

플랫폼:
1. 네이버 (카페, 블로그, 지식인) - 기존
2. 당근마켓 - 신규 ⭐
3. YouTube 댓글 - 신규 ⭐
4. 네이버 플레이스 리뷰 - 신규 ⭐
5. Instagram - 신규
6. TikTok - 신규
"""

import sys
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viral_hunter import ViralTarget, ViralHunter
from db.database import DatabaseManager
from utils import logger


# ============================================
# 플랫폼 어댑터 인터페이스
# ============================================

class PlatformAdapter(ABC):
    """
    플랫폼별 어댑터 베이스 클래스
    각 플랫폼은 이 인터페이스를 구현
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    @abstractmethod
    def search(self, keyword: str, max_results: int = 15) -> List[ViralTarget]:
        """키워드로 타겟 검색"""
        pass

    @abstractmethod
    def is_commentable(self, target: ViralTarget) -> bool:
        """댓글 작성 가능 여부"""
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """플랫폼 이름"""
        pass


# ============================================
# 당근마켓 어댑터 (즉시 사용 가능)
# ============================================

class KarrotAdapter(PlatformAdapter):
    """당근마켓 어댑터"""

    def __init__(self, db: DatabaseManager):
        super().__init__(db)
        # 기존 스크래퍼 임포트
        try:
            from scrapers.scraper_karrot import KarrotScraper
            self.scraper = KarrotScraper()
        except ImportError:
            logger.warning("KarrotScraper not available")
            self.scraper = None

    def get_platform_name(self) -> str:
        return "karrot"

    def search(self, keyword: str, max_results: int = 15) -> List[ViralTarget]:
        """당근마켓 검색"""
        if not self.scraper:
            return []

        targets = []

        try:
            import requests
            from bs4 import BeautifulSoup

            url = f"https://www.daangn.com/search/{keyword}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')

            articles = soup.select("article.flea-market-article")[:max_results]

            for art in articles:
                try:
                    title_el = art.select_one(".article-title")
                    desc_el = art.select_one(".article-content")
                    link_el = art.select_one("a.flea-market-article-link")

                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    content = desc_el.get_text(strip=True) if desc_el else ""
                    link = "https://www.daangn.com" + link_el['href'] if link_el else ""

                    target = ViralTarget(
                        platform="karrot",
                        url=link,
                        title=title,
                        content_preview=content[:200],
                        matched_keywords=[keyword],
                        is_commentable=True,  # 당근은 댓글/채팅 가능
                        priority_score=len([keyword])  # 간단한 점수
                    )

                    targets.append(target)

                except Exception as e:
                    logger.debug(f"Failed to parse karrot article: {e}")
                    continue

        except Exception as e:
            logger.error(f"Karrot search failed: {e}")

        logger.info(f"🥕 당근마켓: {len(targets)}개 타겟 발견")
        return targets

    def is_commentable(self, target: ViralTarget) -> bool:
        """당근은 모두 댓글 가능 (채팅)"""
        return True


# ============================================
# YouTube 어댑터
# ============================================

class YouTubeAdapter(PlatformAdapter):
    """YouTube 어댑터"""

    def __init__(self, db: DatabaseManager):
        super().__init__(db)
        try:
            from scrapers.scraper_youtube import YouTubeSentinel
            self.scraper = YouTubeSentinel()
        except ImportError:
            logger.warning("YouTubeSentinel not available")
            self.scraper = None

    def get_platform_name(self) -> str:
        return "youtube"

    def search(self, keyword: str, max_results: int = 15) -> List[ViralTarget]:
        """YouTube 영상 검색"""
        # YouTube API 또는 Selenium으로 검색
        targets = []

        try:
            # YouTube API로 검색
            if self.scraper and self.scraper.api_client:
                videos = self.scraper.api_client.search_videos(keyword, max_results=max_results)

                for video in videos:
                    target = ViralTarget(
                        platform="youtube",
                        url=f"https://www.youtube.com/watch?v={video['video_id']}",
                        title=video['title'],
                        content_preview=video.get('description', '')[:200],
                        matched_keywords=[keyword],
                        is_commentable=True,
                        priority_score=len([keyword])
                    )
                    targets.append(target)

        except Exception as e:
            logger.error(f"YouTube search failed: {e}")

        logger.info(f"📺 YouTube: {len(targets)}개 타겟 발견")
        return targets

    def is_commentable(self, target: ViralTarget) -> bool:
        """YouTube는 대부분 댓글 가능"""
        return True


# ============================================
# 네이버 플레이스 어댑터
# ============================================

class NaverPlaceAdapter(PlatformAdapter):
    """네이버 플레이스 어댑터"""

    def __init__(self, db: DatabaseManager):
        super().__init__(db)
        from scrapers.scraper_naver_place import check_naver_place_rank
        self.scraper = check_naver_place_rank

    def get_platform_name(self) -> str:
        return "naver_place"

    def search(self, keyword: str, max_results: int = 15) -> List[ViralTarget]:
        """네이버 플레이스 검색 (경쟁사 질문 게시판)"""
        targets = []

        try:
            # 네이버 플레이스 검색
            # 경쟁사 플레이스의 "질문하기" 게시판 타겟팅
            url = f"https://m.place.naver.com/place/list?query={keyword}"

            # 간단 구현 (실제로는 스크래핑 필요)
            target = ViralTarget(
                platform="naver_place",
                url=url,
                title=f"{keyword} - 네이버 플레이스",
                content_preview="질문 게시판 타겟",
                matched_keywords=[keyword],
                is_commentable=True,
                priority_score=len([keyword])
            )
            targets.append(target)

        except Exception as e:
            logger.error(f"Naver Place search failed: {e}")

        logger.info(f"⭐ 네이버 플레이스: {len(targets)}개 타겟 발견")
        return targets

    def is_commentable(self, target: ViralTarget) -> bool:
        """플레이스는 질문 게시판 활용"""
        return True


# ============================================
# Instagram 어댑터
# ============================================

class InstagramAdapter(PlatformAdapter):
    """Instagram 어댑터 (개선 버전)"""

    # 해시태그 확장 사전
    HASHTAG_EXPANSION = {
        "다이어트": ["다이어트", "살빼기", "체중감량", "한약다이어트", "한의원다이어트"],
        "피부과": ["피부과", "피부관리", "피부케어", "피부고민", "피부과추천"],
        "여드름": ["여드름", "여드름치료", "트러블", "피부트러블", "여드름피부과"],
        "한의원": ["한의원", "한방", "한방치료", "한의원추천"],
        "교통사고": ["교통사고", "교통사고한의원", "교통사고후유증", "사고후유증"],
        "입원": ["입원", "입원치료", "입원실비", "통원치료"],
    }

    # 지역 해시태그 매핑
    LOCATION_HASHTAGS = {
        "청주": ["청주", "청주맛집", "청주데일리", "청주일상", "충북", "충청북도"],
        "충주": ["충주", "충주맛집", "충주데일리", "충북"],
        "제천": ["제천", "제천맛집", "충북"],
    }

    # 최소 참여도 기준 (개선: 신규 게시물도 수집 가능하도록 완화)
    MIN_LIKES = 5    # 개선: 10→5 (신규 바이럴 포착)
    MIN_COMMENTS = 1  # 개선: 2→1 (초기 참여도 게시물 포함)

    def __init__(self, db: DatabaseManager):
        super().__init__(db)
        try:
            from scrapers.instagram_api_client import InstagramGraphAPI
            self.api = InstagramGraphAPI()
            if not self.api.is_configured():
                logger.warning("Instagram API not configured")
                self.api = None
        except ImportError:
            logger.warning("InstagramGraphAPI not available")
            self.api = None

    def get_platform_name(self) -> str:
        return "instagram"

    def _expand_hashtags(self, keyword: str) -> List[str]:
        """키워드를 여러 해시태그로 확장"""
        hashtags = []

        # 공백 제거 버전 (기본)
        base_hashtag = keyword.replace("#", "").replace(" ", "")
        hashtags.append(base_hashtag)

        # 키워드 분리 (공백 기준)
        words = keyword.replace("#", "").split()

        # 각 단어 추가
        for word in words:
            if word and word not in hashtags:
                hashtags.append(word)

        # 확장 사전에서 동의어 추가
        for word in words:
            if word in self.HASHTAG_EXPANSION:
                for synonym in self.HASHTAG_EXPANSION[word]:
                    if synonym not in hashtags:
                        hashtags.append(synonym)

        # 지역 해시태그 자동 추가
        for location, location_tags in self.LOCATION_HASHTAGS.items():
            if location in keyword:
                for tag in location_tags:
                    if tag not in hashtags:
                        hashtags.append(tag)

        return hashtags

    def search(self, keyword: str, max_results: int = 15) -> List[ViralTarget]:
        """Instagram 해시태그 검색 (개선 버전)"""
        if not self.api:
            return []

        targets = []
        seen_urls = set()  # 중복 제거용

        try:
            # 1. 해시태그 확장
            hashtags = self._expand_hashtags(keyword)
            logger.info(f"📷 Instagram 검색: '{keyword}' → {len(hashtags)}개 해시태그 ({', '.join(hashtags[:3])}...)")

            # 2. 각 해시태그별로 검색 (상위 3개만)
            for hashtag in hashtags[:3]:
                try:
                    # 2-1. 인기 게시물 우선 검색
                    top_media = self.api.search_hashtag_top(hashtag, limit=5)

                    # 2-2. 최근 게시물 검색
                    recent_media = self.api.search_hashtag(hashtag, limit=10)

                    # 통합
                    media_list = top_media + recent_media

                    for media in media_list:
                        permalink = media.get('permalink', '')

                        # 중복 제거
                        if permalink in seen_urls:
                            continue
                        seen_urls.add(permalink)

                        caption = media.get('caption', '')
                        timestamp = media.get('timestamp', '')
                        like_count = media.get('like_count', 0)
                        comments_count = media.get('comments_count', 0)

                        # 3. 최소 참여도 필터
                        if like_count < self.MIN_LIKES and comments_count < self.MIN_COMMENTS:
                            continue

                        # 관심 점수 계산 (좋아요 + 댓글 수)
                        priority = like_count * 0.1 + comments_count * 2

                        target = ViralTarget(
                            platform="instagram",
                            url=permalink,
                            title=f"Instagram: {caption[:50] if caption else 'No caption'}...",
                            content_preview=caption[:200] if caption else "",
                            matched_keywords=[keyword],
                            is_commentable=True,
                            priority_score=priority
                        )
                        targets.append(target)

                except Exception as e:
                    logger.debug(f"해시태그 '{hashtag}' 검색 실패: {e}")
                    continue

            # 우선순위 정렬 (참여도 높은 순)
            targets.sort(key=lambda x: x.priority_score, reverse=True)

            # 최대 결과 수 제한
            targets = targets[:max_results]

        except Exception as e:
            logger.error(f"Instagram search failed: {e}")

        logger.info(f"📷 Instagram: {len(targets)}개 타겟 발견 (좋아요 {self.MIN_LIKES}+ 또는 댓글 {self.MIN_COMMENTS}+)")
        return targets

    def is_commentable(self, target: ViralTarget) -> bool:
        """Instagram은 모두 댓글 가능"""
        return True


# ============================================
# TikTok 어댑터
# ============================================

class TikTokAdapter(PlatformAdapter):
    """TikTok 어댑터"""

    def __init__(self, db: DatabaseManager):
        super().__init__(db)
        try:
            from scrapers.tiktok_api_client import TikTokResearchAPIClient
            self.api = TikTokResearchAPIClient()
            if not self.api.is_configured():
                logger.warning("TikTok API not configured")
                self.api = None
        except ImportError:
            logger.warning("TikTokResearchAPIClient not available")
            self.api = None

    def get_platform_name(self) -> str:
        return "tiktok"

    def search(self, keyword: str, max_results: int = 15) -> List[ViralTarget]:
        """TikTok 영상 검색"""
        if not self.api:
            return []

        targets = []

        try:
            # 영상 검색
            videos = self.api.search_videos(
                query=keyword,
                region_code="KR",
                max_count=max_results
            )

            for video in videos:
                video_id = video.get('id', '')
                desc = video.get('video_description', '')
                username = video.get('username', 'Unknown')
                view_count = video.get('view_count', 0)
                like_count = video.get('like_count', 0)
                comment_count = video.get('comment_count', 0)

                # 관심 점수 계산
                priority = view_count * 0.001 + like_count * 0.1 + comment_count * 2

                target = ViralTarget(
                    platform="tiktok",
                    url=f"https://www.tiktok.com/@{username}/video/{video_id}",
                    title=f"@{username}: {desc[:50] if desc else 'No description'}...",
                    content_preview=desc[:200] if desc else "",
                    matched_keywords=[keyword],
                    is_commentable=True,
                    priority_score=priority
                )
                targets.append(target)

        except Exception as e:
            logger.error(f"TikTok search failed: {e}")

        logger.info(f"🎵 TikTok: {len(targets)}개 타겟 발견")
        return targets

    def is_commentable(self, target: ViralTarget) -> bool:
        """TikTok은 모두 댓글 가능"""
        return True


# ============================================
# 멀티 플랫폼 Viral Hunter
# ============================================

class MultiPlatformViralHunter(ViralHunter):
    """
    멀티 플랫폼 지원 Viral Hunter
    기존 ViralHunter를 상속하여 확장
    """

    def __init__(self):
        super().__init__()

        # 플랫폼 어댑터 등록
        self.adapters = {
            'karrot': KarrotAdapter(self.db),
            'youtube': YouTubeAdapter(self.db),
            'naver_place': NaverPlaceAdapter(self.db),
            'instagram': InstagramAdapter(self.db),
            'tiktok': TikTokAdapter(self.db),
        }

        # 활성화된 플랫폼만 카운트
        active_adapters = [name for name, adapter in self.adapters.items()
                          if hasattr(adapter, 'api') and adapter.api or
                          hasattr(adapter, 'scraper') and adapter.scraper]

        total_platforms = len(active_adapters) + 3  # +3 for Naver (카페, 블로그, 지식인)

        logger.info(f"✅ 멀티 플랫폼 모드: {total_platforms}개 플랫폼")
        logger.info(f"   • 네이버 (카페, 블로그, 지식인)")
        for name in self.adapters.keys():
            adapter = self.adapters[name]
            # API/Scraper 설정 여부 확인
            is_active = (hasattr(adapter, 'api') and adapter.api) or \
                       (hasattr(adapter, 'scraper') and adapter.scraper)
            status = "✅" if is_active else "⚠️ (미설정)"
            logger.info(f"   • {name} {status}")

    def hunt_multi_platform(self, keywords: List[str] = None,
                           platforms: List[str] = None,
                           max_per_platform: int = 15) -> List[ViralTarget]:
        """
        멀티 플랫폼 타겟 발굴

        Args:
            keywords: 검색 키워드 (None이면 자동 로드)
            platforms: 검색할 플랫폼 리스트 (None이면 전체)
            max_per_platform: 플랫폼당 최대 결과 수

        Returns:
            발견된 ViralTarget 리스트
        """
        if keywords is None:
            keywords = self._load_keywords()

        if platforms is None:
            platforms = ['naver'] + list(self.adapters.keys())

        print(f"\n{'='*60}")
        print(f"🚀 멀티 플랫폼 Viral Hunter 스캔 시작")
        print(f"   키워드: {len(keywords)}개")
        print(f"   플랫폼: {', '.join(platforms)}")
        print(f"{'='*60}\n")

        all_targets = []
        seen_urls = set()

        for i, kw in enumerate(keywords, 1):
            print(f"\n[{i}/{len(keywords)}] '{kw}' 검색 중...")

            # 1. 기존 네이버 (카페, 블로그, 지식인)
            if 'naver' in platforms:
                naver_targets = self.searcher.search_all(kw, max_per_platform)
                for target in naver_targets:
                    if target.url not in seen_urls:
                        seen_urls.add(target.url)
                        all_targets.append(target)

            # 2. 추가 플랫폼
            for platform_name in platforms:
                if platform_name == 'naver':
                    continue

                adapter = self.adapters.get(platform_name)
                if adapter:
                    try:
                        platform_targets = adapter.search(kw, max_per_platform)
                        for target in platform_targets:
                            if target.url not in seen_urls:
                                seen_urls.add(target.url)
                                all_targets.append(target)
                    except Exception as e:
                        logger.error(f"Platform {platform_name} error: {e}")

            # 진행 상황
            if i % 5 == 0:
                print(f"   📊 진행: {i}/{len(keywords)} | 수집: {len(all_targets)}개")

        print(f"\n{'='*60}")
        print(f"✅ 스캔 완료: 총 {len(all_targets)}개 타겟 발견")

        # 플랫폼별 통계
        platform_stats = {}
        for target in all_targets:
            platform_stats[target.platform] = platform_stats.get(target.platform, 0) + 1

        print(f"\n📊 플랫폼별 통계:")
        for platform, count in sorted(platform_stats.items(), key=lambda x: -x[1]):
            print(f"   • {platform}: {count}개")

        print(f"{'='*60}\n")

        return all_targets


# ============================================
# 메인 실행
# ============================================

def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='멀티 플랫폼 Viral Hunter')
    parser.add_argument('--platforms', type=str,
                       help='검색할 플랫폼 (쉼표 구분, 예: naver,karrot,youtube)')
    parser.add_argument('--limit', type=int, default=10,
                       help='키워드 제한 수')
    parser.add_argument('--save-db', action='store_true',
                       help='DB 저장 여부')

    args = parser.parse_args()

    # 멀티 플랫폼 Viral Hunter 초기화
    hunter = MultiPlatformViralHunter()

    # 플랫폼 선택
    platforms = None
    if args.platforms:
        platforms = [p.strip() for p in args.platforms.split(',')]

    # 타겟 발굴
    targets = hunter.hunt_multi_platform(
        keywords=hunter._load_keywords()[:args.limit],
        platforms=platforms,
        max_per_platform=15
    )

    # DB 저장
    if args.save_db:
        print(f"\n💾 DB 저장 중...")
        for target in targets:
            try:
                hunter.db.insert_viral_target(target.to_dict())
            except Exception as e:
                logger.debug(f"DB insert failed: {e}")
        print(f"✅ {len(targets)}개 타겟 저장 완료")

    print(f"\n🎯 다음 단계:")
    print(f"   1. Dashboard에서 타겟 확인")
    print(f"   2. AI 댓글 생성")
    print(f"   3. 수동 검토 후 게시")


if __name__ == "__main__":
    main()
