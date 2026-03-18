"""
Ambassador V2: Multi-Platform Influencer Discovery & Management
네이버 블로그 인플루언서 발굴 중심으로 구현
"""

import re
import json
import time
import random
from datetime import datetime
from typing import List, Dict, Optional
import requests

# Optional: BeautifulSoup for enhanced profile scraping
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from naver_api_client import NaverApiClient
from db.database import DatabaseManager
from utils import logger, ConfigManager

# Optional: AgentCrew for AI proposal generation
try:
    from agent_crew import AgentCrew
    HAS_AGENT_CREW = True
except ImportError:
    HAS_AGENT_CREW = False
    AgentCrew = None


class AmbassadorV2:
    """
    Multi-Platform Influencer Discovery & Management
    Phase 1: 네이버 블로그 인플루언서 발굴
    """

    def __init__(self):
        self.naver_client = NaverApiClient()
        self.crew = AgentCrew() if HAS_AGENT_CREW else None
        self.db = DatabaseManager()
        self.config = ConfigManager()

        # 발굴 키워드 설정 (확장)
        self.discovery_keywords = [
            # 핵심 키워드
            "{location} 한의원 후기",
            "{location} 한의원 추천",
            "{location} 다이어트 후기",
            "{location} 다이어트 한약",
            "{location} 병원 후기",
            "{location} 피부과 후기",
            # 체험단/협찬
            "{location} 체험단",
            "{location} 협찬",
            "{location} 원고료",
            "{location} 방문 리뷰",
            # 일상/육아
            "{location} 맛집 후기",
            "{location} 맛집 추천",
            "{location} 육아 블로그",
            "{location} 육아 일기",
            "{location} 일상 블로그",
            "{location} 주부 일상",
            # 뷰티/건강
            "{location} 뷰티 블로그",
            "{location} 피부 관리",
            "{location} 건강 관리",
            "{location} 운동 후기",
            # 지역 특화
            "{location} 블로거",
            "{location} 인플루언서",
            "{location} 리뷰어",
            "충북 {location} 맛집",
            "충청북도 {location}",
        ]

        # 관련성 키워드 (가중치 부여)
        self.relevance_keywords = {
            "high": ["한의원", "다이어트", "건강", "의료", "치료", "병원", "한약", "침"],
            "medium": ["후기", "체험단", "협찬", "리뷰", "추천", "방문"],
            "low": ["일상", "육아", "맛집", "여행", "뷰티"]
        }

        # 블랙리스트 키워드 (콘텐츠에 포함 시 제외)
        self.blacklist_keywords = [
            # 불법/부적절
            "카지노", "바카라", "도박", "대출", "성인", "19금",
            # 민감 의료
            "임신중절", "중절수술", "낙태",
            # 스팸
            "바이럴", "홍보대행", "마케팅대행"
        ]

        # 자사 블로그 제외 (블로그 ID 또는 이름에 포함된 키워드)
        self.exclude_own_blogs = [
            "규림", "kyurim", "eliteacu", "crazat7",  # 규림한의원 관련
            "gyurim", "gyulim", "kylim"
        ]

        # 업체/기관 블로그 제외 패턴 - 강력 (무조건 제외)
        self.exclude_business_strong = [
            # 의료기관 (명확한 업체)
            "한의원", "한방병원", "병원", "의원", "클리닉", "clinic",
            "재활의학과", "피부과", "내과", "외과", "정형외과", "치과",
            "한의사",  # 한의사 개인 블로그도 제외
            # 다이어트/뷰티 업체
            "쥬비스", "juvis", "다이어트센터", "비만클리닉", "365mc",
            # 약국
            "약국", "pharmacy",
            # 기타 업체
            "공식", "official", "원장", "대표원장"
        ]

        # 업체/기관 블로그 제외 패턴 - 약함 (개인 힌트 있으면 제외 안함)
        self.exclude_business_weak = [
            "센터", "center", "치료", "전문"
        ]

        # 개인 블로거 판별 키워드 (이 키워드가 있으면 개인 블로거일 가능성 높음)
        self.personal_blogger_hints = [
            "일상", "일기", "육아", "맘", "주부", "리뷰", "후기",
            "먹스타그램", "맛집", "데일리", "daily", "story", "log",
            "여행", "취미", "살림", "신혼", "아이", "딸", "아들"
        ]

        # 비관련 콘텐츠 제외 패턴 (관련 없는 분야의 블로거 제외)
        self.exclude_irrelevant_topics = [
            # 교육 분야
            "영어교육", "영어학원", "수학학원", "학원", "과외", "입시", "수능",
            "초등교육", "중등교육", "고등교육", "교육블로그", "공부법", "학습법",
            "토익", "토플", "ielts", "유학", "어학연수",
            # 부동산/금융
            "부동산", "아파트분양", "투자", "주식", "코인", "재테크",
            # IT/개발
            "프로그래밍", "코딩", "개발자", "it기업",
            # 기타 비관련
            "자동차", "중고차", "튜닝", "낚시", "캠핑러버", "캠핑장비", "등산장비",
            "게임", "e스포츠", "리그오브레전드", "배그"
        ]

        # 관련 콘텐츠 필수 키워드 (이 중 하나라도 있어야 통과)
        # 더 구체적인 키워드 사용 - 일반적인 "후기", "리뷰"는 제외
        self.required_relevance_topics = [
            # 의료/건강 (핵심)
            "한의원", "병원", "건강", "치료", "다이어트", "체중", "살빼기",
            "한약", "침", "추나", "교정", "통증", "피부", "여드름", "아토피",
            # 뷰티
            "뷰티", "피부관리", "화장품", "에스테틱", "마사지", "스파",
            # 지역 (필수)
            "청주", "충북", "충청북도", "흥덕", "서원", "상당",
            # 육아/가족 (잠재 고객층)
            "육아", "임신", "출산", "산후", "아기", "엄마", "주부",
            # 협찬/체험 (인플루언서 활동)
            "협찬", "체험단", "원고료"
        ]

    def discover_naver_bloggers(self, location: str = "청주", max_results: int = 50, min_score: int = 15) -> List[Dict]:
        """
        네이버 블로그 API로 인플루언서 발굴

        Args:
            location: 타겟 지역
            max_results: 최대 발굴 수
            min_score: 최소 관련성 점수 (기본 15)

        Returns:
            발굴된 블로거 리스트
        """
        logger.info(f"🔍 Ambassador V2: '{location}' 지역 블로거 발굴 시작...")
        logger.info(f"   설정: max_results={max_results}, min_score={min_score}")

        discovered_bloggers = {}  # blog_id -> blogger_info (중복 제거용)

        # 모든 키워드 검색 (max_results 도달해도 계속)
        for keyword_template in self.discovery_keywords:
            keyword = keyword_template.format(location=location)
            logger.info(f"   📝 검색 중: {keyword}")

            try:
                # 더 많은 결과 요청 (100개)
                result = self.naver_client.search_blog(keyword, count=100)
                items = result.get("items", [])

                new_count = 0
                skipped_business = 0
                skipped_irrelevant = 0
                for item in items:
                    blogger = self._extract_blogger_info(item)
                    if blogger and blogger["blog_id"] not in discovered_bloggers:
                        # 블랙리스트 체크
                        if self._is_blacklisted(item):
                            continue

                        # 자사 블로그 제외
                        if self._is_own_blog(blogger):
                            continue

                        # 타사 업체/기관 블로그 제외
                        if self._is_business_blog(blogger):
                            skipped_business += 1
                            continue

                        # 비관련 콘텐츠 블로거 제외
                        if self._is_irrelevant_content(blogger):
                            skipped_irrelevant += 1
                            continue

                        discovered_bloggers[blogger["blog_id"]] = blogger
                        new_count += 1

                if new_count > 0:
                    logger.info(f"      → {new_count}명 신규 발굴 (누적: {len(discovered_bloggers)}명)")

                # API 속도 제한 존중
                time.sleep(0.3 + random.random() * 0.3)

            except Exception as e:
                logger.error(f"   ❌ 검색 실패 ({keyword}): {e}")
                continue

        logger.info(f"   ✅ 총 {len(discovered_bloggers)}명의 블로거 발굴 완료")

        # 블로거 상세 분석 (max_results 제한 적용)
        logger.info(f"   🔬 블로거 분석 중...")
        analyzed_bloggers = []
        for i, (blog_id, blogger) in enumerate(list(discovered_bloggers.items())[:max_results * 2]):
            try:
                analyzed = self._analyze_blogger(blogger)
                if analyzed["relevance_score"] >= min_score:
                    analyzed_bloggers.append(analyzed)

                # 진행상황 표시 (50명마다)
                if (i + 1) % 50 == 0:
                    logger.info(f"      → {i + 1}명 분석 완료, {len(analyzed_bloggers)}명 적합")

            except Exception as e:
                logger.debug(f"   ⚠️ 블로거 분석 실패 ({blog_id}): {e}")

            # 충분히 모았으면 중단
            if len(analyzed_bloggers) >= max_results:
                break

        # 관련성 점수로 정렬
        analyzed_bloggers.sort(key=lambda x: x["relevance_score"], reverse=True)

        logger.info(f"   🎯 최종 {len(analyzed_bloggers)}명 선별 완료")

        return analyzed_bloggers

    def _extract_blogger_info(self, item: Dict) -> Optional[Dict]:
        """
        네이버 블로그 검색 결과에서 블로거 정보 추출

        Args:
            item: 검색 결과 아이템

        Returns:
            블로거 정보 딕셔너리
        """
        try:
            blog_link = item.get("bloggerlink", "")
            blogger_name = item.get("bloggername", "")

            # 블로그 ID 추출
            blog_id = None
            if "blog.naver.com/" in blog_link:
                match = re.search(r'blog\.naver\.com/([^/?]+)', blog_link)
                if match:
                    blog_id = match.group(1)

            if not blog_id:
                return None

            return {
                "blog_id": blog_id,
                "name": blogger_name,
                "profile_url": f"https://blog.naver.com/{blog_id}",
                "platform": "naver_blog",
                "sample_post": {
                    "title": self._clean_html(item.get("title", "")),
                    "description": self._clean_html(item.get("description", "")),
                    "link": item.get("link", ""),
                    "postdate": item.get("postdate", "")
                }
            }
        except Exception as e:
            logger.debug(f"블로거 정보 추출 실패: {e}")
            return None

    def _analyze_blogger(self, blogger: Dict) -> Dict:
        """
        블로거 상세 분석 (프로필 페이지 스크래핑)

        Args:
            blogger: 기본 블로거 정보

        Returns:
            분석된 블로거 정보
        """
        blog_id = blogger["blog_id"]
        profile_url = blogger["profile_url"]

        # 기본값 설정
        blogger["followers"] = 0
        blogger["total_posts"] = 0
        blogger["sponsored_experience"] = False
        blogger["content_categories"] = []
        blogger["relevance_score"] = 0

        try:
            # 블로그 프로필 페이지 요청
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(profile_url, headers=headers, timeout=5)

            if response.status_code == 200:
                page_text = response.text

                if HAS_BS4:
                    # BeautifulSoup 사용 (더 정확)
                    soup = BeautifulSoup(page_text, 'html.parser')

                    # 이웃 수 추출 시도 (여러 선택자 시도)
                    neighbor_selectors = [
                        ".buddy_count",
                        ".cnt",
                        "[class*='neighbor']",
                        "[class*='buddy']"
                    ]
                    for selector in neighbor_selectors:
                        elem = soup.select_one(selector)
                        if elem:
                            text = elem.get_text()
                            numbers = re.findall(r'[\d,]+', text)
                            if numbers:
                                blogger["followers"] = int(numbers[0].replace(",", ""))
                                break

                    page_text = soup.get_text()

                # 전체 게시글 수 추출 시도 (regex 기반, bs4 없이도 작동)
                post_count_patterns = [
                    r'전체글[^\d]*(\d+)',
                    r'게시글[^\d]*(\d+)',
                    r'총[^\d]*(\d+)[^\d]*글',
                    r'"totalCount":\s*(\d+)',
                    r'postCnt["\']?\s*:\s*(\d+)'
                ]
                for pattern in post_count_patterns:
                    match = re.search(pattern, page_text)
                    if match:
                        blogger["total_posts"] = int(match.group(1))
                        break

                # 이웃 수 추출 (regex fallback)
                if blogger["followers"] == 0:
                    neighbor_patterns = [
                        r'이웃[^\d]*(\d+)',
                        r'buddy[^\d]*(\d+)',
                        r'"buddyCount":\s*(\d+)'
                    ]
                    for pattern in neighbor_patterns:
                        match = re.search(pattern, page_text)
                        if match:
                            blogger["followers"] = int(match.group(1))
                            break

        except Exception as e:
            logger.debug(f"프로필 스크래핑 실패 ({blog_id}): {e}")

        # 협찬/체험단 경험 체크 (샘플 포스트 기반)
        sample_text = blogger.get("sample_post", {}).get("title", "") + \
                      blogger.get("sample_post", {}).get("description", "")

        sponsored_keywords = ["체험단", "협찬", "원고료", "제공", "소정의", "지원받아"]
        blogger["sponsored_experience"] = any(kw in sample_text for kw in sponsored_keywords)

        # 관련성 점수 계산
        blogger["relevance_score"] = self._calculate_relevance_score(blogger)

        return blogger

    def _calculate_relevance_score(self, blogger: Dict) -> int:
        """
        블로거 관련성 점수 계산 (0-100)

        기준:
        - 개인 블로거 특성 (30점) - 일상, 육아, 리뷰 등
        - 지역 관련성 (20점) - 청주/충북 언급
        - 활동량/이웃 수 (20점)
        - 협찬 경험 (20점)
        - 최근 활동 (10점)
        """
        score = 0
        blog_name = blogger.get("name", "")
        sample_text = blogger.get("sample_post", {}).get("title", "") + \
                      blogger.get("sample_post", {}).get("description", "")
        combined_text = f"{blog_name} {sample_text}"

        # 1. 개인 블로거 특성 (30점) - 업체가 아닌 개인 블로거 선호
        personal_hints_found = sum(1 for hint in self.personal_blogger_hints if hint in combined_text.lower())
        if personal_hints_found >= 3:
            score += 30
        elif personal_hints_found >= 2:
            score += 25
        elif personal_hints_found >= 1:
            score += 15
        else:
            score += 5

        # 2. 지역 관련성 (20점) - 청주/충북 지역 언급
        location_keywords = ["청주", "충북", "충청북도", "흥덕", "서원", "상당", "청원"]
        location_found = sum(1 for loc in location_keywords if loc in combined_text)
        if location_found >= 2:
            score += 20
        elif location_found >= 1:
            score += 15
        else:
            score += 5

        # 3. 활동량/이웃 수 (20점)
        followers = blogger.get("followers", 0)
        if followers >= 5000:
            score += 20
        elif followers >= 2000:
            score += 17
        elif followers >= 1000:
            score += 14
        elif followers >= 500:
            score += 10
        elif followers >= 100:
            score += 7
        else:
            score += 3

        # 4. 협찬 경험 (20점)
        if blogger.get("sponsored_experience"):
            score += 20
        else:
            # 협찬 관련 키워드 체크
            sponsored_hints = ["체험단", "협찬", "원고료", "제공받", "지원받"]
            if any(hint in combined_text for hint in sponsored_hints):
                score += 10

        # 5. 최근 활동 (10점) - postdate 기반
        postdate = blogger.get("sample_post", {}).get("postdate", "")
        if postdate:
            try:
                post_date = datetime.strptime(postdate, "%Y%m%d")
                days_ago = (datetime.now() - post_date).days
                if days_ago <= 7:
                    score += 10
                elif days_ago <= 30:
                    score += 7
                elif days_ago <= 90:
                    score += 4
            except Exception:
                pass

        return min(score, 100)

    def _is_blacklisted(self, item: Dict) -> bool:
        """블랙리스트 키워드 체크"""
        text = item.get("title", "") + item.get("description", "")
        return any(kw in text for kw in self.blacklist_keywords)

    def _is_irrelevant_content(self, blogger: Dict) -> bool:
        """
        비관련 콘텐츠 블로거 체크
        - 비관련 주제(교육, 부동산 등)가 블로그 이름에 포함되면 제외
        - 관련 주제가 하나도 없으면 제외
        """
        blog_name = blogger.get("name", "").lower()
        blog_id = blogger.get("blog_id", "").lower()
        sample_title = blogger.get("sample_post", {}).get("title", "").lower()
        sample_desc = blogger.get("sample_post", {}).get("description", "").lower()

        combined_text = f"{blog_name} {blog_id} {sample_title} {sample_desc}"

        # 1. 비관련 주제 체크 (블로그 이름에 있으면 무조건 제외)
        for topic in self.exclude_irrelevant_topics:
            if topic.lower() in blog_name:
                return True

        # 2. 관련 콘텐츠 필수 체크 (최소 1개 이상 있어야 통과)
        has_relevant_topic = any(
            topic.lower() in combined_text
            for topic in self.required_relevance_topics
        )

        if not has_relevant_topic:
            return True  # 관련 주제 없으면 제외

        return False

    def _is_own_blog(self, blogger: Dict) -> bool:
        """자사 블로그 체크"""
        blog_id = blogger.get("blog_id", "").lower()
        blog_name = blogger.get("name", "").lower()

        for keyword in self.exclude_own_blogs:
            kw_lower = keyword.lower()
            if kw_lower in blog_id or kw_lower in blog_name:
                return True
        return False

    def _is_business_blog(self, blogger: Dict) -> bool:
        """업체/기관 블로그 체크 (타사 한의원, 병원, 약국 등)"""
        blog_name = blogger.get("name", "").lower()
        blog_id = blogger.get("blog_id", "").lower()
        sample_title = blogger.get("sample_post", {}).get("title", "").lower()

        # 블로그 이름 기준으로 체크 (가장 신뢰도 높음)
        name_text = f"{blog_name} {blog_id}"

        # 강력 패턴: 무조건 제외
        for pattern in self.exclude_business_strong:
            if pattern.lower() in name_text:
                return True

        # 약한 패턴: 개인 힌트 없으면 제외
        combined_text = f"{blog_name} {blog_id} {sample_title}"
        for pattern in self.exclude_business_weak:
            if pattern.lower() in name_text:  # 이름에만 적용
                has_personal_hint = any(
                    hint in combined_text for hint in self.personal_blogger_hints
                )
                if not has_personal_hint:
                    return True

        return False

    def _is_likely_personal_blogger(self, blogger: Dict) -> bool:
        """개인 블로거 가능성 판별"""
        blog_name = blogger.get("name", "").lower()
        sample_title = blogger.get("sample_post", {}).get("title", "").lower()
        sample_desc = blogger.get("sample_post", {}).get("description", "").lower()

        combined_text = f"{blog_name} {sample_title} {sample_desc}"

        # 개인 블로거 힌트 개수
        hint_count = sum(1 for hint in self.personal_blogger_hints if hint in combined_text)

        return hint_count >= 1

    def _clean_html(self, text: str) -> str:
        """HTML 태그 제거"""
        return re.sub(r'<[^>]+>', '', text) if text else ""

    def save_influencer(self, blogger: Dict) -> int:
        """
        발굴된 인플루언서를 DB에 저장

        Returns:
            저장된 influencer의 ID (이미 존재하면 기존 ID)
        """
        try:
            # 이미 존재하는지 확인
            self.db.cursor.execute(
                "SELECT id FROM influencers WHERE platform = ? AND handle = ?",
                (blogger["platform"], blogger["blog_id"])
            )
            existing = self.db.cursor.fetchone()
            if existing:
                # 업데이트
                self.db.cursor.execute('''
                    UPDATE influencers SET
                        followers = ?,
                        total_posts = ?,
                        relevance_score = ?,
                        sponsored_experience = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    blogger.get("followers", 0),
                    blogger.get("total_posts", 0),
                    blogger.get("relevance_score", 0),
                    blogger.get("sponsored_experience", False),
                    existing[0]
                ))
                self.db.conn.commit()
                return existing[0]

            # 새로 삽입
            self.db.cursor.execute('''
                INSERT INTO influencers (
                    name, platform, handle, profile_url,
                    followers, total_posts, relevance_score,
                    sponsored_experience, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'discovered')
            ''', (
                blogger.get("name", ""),
                blogger["platform"],
                blogger["blog_id"],
                blogger["profile_url"],
                blogger.get("followers", 0),
                blogger.get("total_posts", 0),
                blogger.get("relevance_score", 0),
                blogger.get("sponsored_experience", False)
            ))
            self.db.conn.commit()
            return self.db.cursor.lastrowid

        except Exception as e:
            logger.error(f"인플루언서 저장 실패: {e}")
            return -1

    def generate_proposal(self, influencer_id: int, campaign_type: str = "체험단") -> str:
        """
        AI로 협업 제안서 생성

        Args:
            influencer_id: 인플루언서 DB ID
            campaign_type: 협업 유형 (체험단, 협찬, 이벤트 등)

        Returns:
            생성된 제안서 텍스트
        """
        # 인플루언서 정보 조회
        self.db.cursor.execute(
            "SELECT name, handle, profile_url, followers, relevance_score FROM influencers WHERE id = ?",
            (influencer_id,)
        )
        row = self.db.cursor.fetchone()
        if not row:
            return "인플루언서 정보를 찾을 수 없습니다."

        name, handle, profile_url, followers, score = row

        prompt = f"""
당신은 청주 규림한의원의 마케팅 담당자입니다.
다음 블로거에게 보낼 협업 제안 메시지를 작성해주세요.

[블로거 정보]
- 블로그명: {name}
- 블로그 주소: {profile_url}
- 이웃 수: {followers if followers else '확인 필요'}
- 관련성 점수: {score}/100

[협업 유형]
{campaign_type}

[규림한의원 정보]
- 위치: 청주시 흥덕구 복대동
- 주력 분야: 다이어트 한약, 안면비대칭 교정, 여드름 치료, 교통사고 치료
- 특징: 1:1 맞춤 상담, 체계적인 관리 프로그램

[작성 가이드]
1. 친근하고 정중한 톤 유지
2. 블로거의 콘텐츠에 관심을 표현
3. 구체적인 협업 내용 제시 (무료 체험, 원고료 등)
4. 연락처 안내
5. 200자 내외로 간결하게

[출력 형식]
제목: (제안서 제목)
---
(본문)
"""

        try:
            if not self.crew:
                return f"[AI 미설정] {name}님께 협업 제안서를 작성해주세요. (블로그: {profile_url})"
            proposal = self.crew.writer.generate(prompt)
            return proposal
        except Exception as e:
            logger.error(f"제안서 생성 실패: {e}")
            return f"제안서 생성 중 오류 발생: {e}"

    def update_status(self, influencer_id: int, status: str, notes: str = None):
        """
        인플루언서 상태 업데이트

        Status 종류:
        - discovered: 발굴됨
        - contacted: 연락함
        - negotiating: 협의 중
        - collaborated: 협업 완료
        - declined: 거절
        """
        try:
            if notes:
                self.db.cursor.execute(
                    "UPDATE influencers SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, notes, influencer_id)
                )
            else:
                self.db.cursor.execute(
                    "UPDATE influencers SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, influencer_id)
                )
            self.db.conn.commit()
            logger.info(f"인플루언서 #{influencer_id} 상태 업데이트: {status}")
        except Exception as e:
            logger.error(f"상태 업데이트 실패: {e}")

    def get_discovery_report(self) -> Dict:
        """발굴 현황 리포트"""
        try:
            self.db.cursor.execute('''
                SELECT
                    status,
                    COUNT(*) as count,
                    AVG(relevance_score) as avg_score,
                    AVG(followers) as avg_followers
                FROM influencers
                WHERE platform = 'naver_blog'
                GROUP BY status
            ''')
            rows = self.db.cursor.fetchall()

            report = {
                "by_status": {},
                "total": 0,
                "generated_at": datetime.now().isoformat()
            }

            for row in rows:
                status, count, avg_score, avg_followers = row
                report["by_status"][status] = {
                    "count": count,
                    "avg_relevance_score": round(avg_score or 0, 1),
                    "avg_followers": int(avg_followers or 0)
                }
                report["total"] += count

            return report
        except Exception as e:
            logger.error(f"리포트 생성 실패: {e}")
            return {"error": str(e)}

    def get_top_influencers(self, limit: int = 10, status: str = None) -> List[Dict]:
        """상위 인플루언서 목록 조회"""
        try:
            query = '''
                SELECT id, name, handle, profile_url, followers, relevance_score, status, sponsored_experience
                FROM influencers
                WHERE platform = 'naver_blog'
            '''
            params = []

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY relevance_score DESC LIMIT ?"
            params.append(limit)

            self.db.cursor.execute(query, params)
            rows = self.db.cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "handle": row[2],
                    "profile_url": row[3],
                    "followers": row[4],
                    "relevance_score": row[5],
                    "status": row[6],
                    "sponsored_experience": bool(row[7])
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"인플루언서 목록 조회 실패: {e}")
            return []

    def scout_and_save(self, location: str = "청주", max_results: int = 50, min_score: int = 15) -> Dict:
        """
        블로거 발굴 및 DB 저장 (메인 실행 함수)

        Args:
            location: 타겟 지역
            max_results: 최대 발굴 수 (기본 50)
            min_score: 최소 관련성 점수 (기본 15)

        Returns:
            실행 결과 요약
        """
        logger.info(f"🤝 Ambassador V2: {location} 지역 블로거 스카우팅 시작")

        # 발굴
        bloggers = self.discover_naver_bloggers(location, max_results, min_score)

        # 저장
        saved_count = 0
        updated_count = 0

        for blogger in bloggers:
            result_id = self.save_influencer(blogger)
            if result_id > 0:
                # 새로 저장인지 업데이트인지 확인
                self.db.cursor.execute(
                    "SELECT created_at, updated_at FROM influencers WHERE id = ?",
                    (result_id,)
                )
                row = self.db.cursor.fetchone()
                if row and row[0] != row[1]:
                    updated_count += 1
                else:
                    saved_count += 1

        result = {
            "location": location,
            "discovered": len(bloggers),
            "new_saved": saved_count,
            "updated": updated_count,
            "top_bloggers": bloggers[:5] if bloggers else [],
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"✅ 스카우팅 완료: {len(bloggers)}명 발굴, {saved_count}명 신규 저장, {updated_count}명 업데이트")

        return result


# 기존 ambassador.py와의 호환성을 위한 래퍼
class TheAmbassador(AmbassadorV2):
    """Legacy compatibility wrapper"""

    def scout_and_vet(self, location_filter="청주"):
        """기존 인터페이스 호환"""
        result = self.scout_and_save(location_filter, max_results=20)
        return result.get("top_bloggers", [])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ambassador V2: 네이버 블로그 인플루언서 발굴")
    parser.add_argument("--location", default="청주", help="타겟 지역 (기본: 청주)")
    parser.add_argument("--max", type=int, default=50, help="최대 발굴 수 (기본: 50)")
    parser.add_argument("--min-score", type=int, default=15, help="최소 관련성 점수 (기본: 15)")
    args = parser.parse_args()

    ambassador = AmbassadorV2()

    print("=" * 60)
    print("🤝 Ambassador V2: 네이버 블로그 인플루언서 발굴")
    print(f"   지역: {args.location} | 목표: {args.max}명 | 최소점수: {args.min_score}")
    print("=" * 60)

    # 발굴 실행
    result = ambassador.scout_and_save(args.location, max_results=args.max, min_score=args.min_score)

    print(f"\n📊 발굴 결과:")
    print(f"   - 발굴: {result['discovered']}명")
    print(f"   - 신규 저장: {result['new_saved']}명")
    print(f"   - 업데이트: {result['updated']}명")

    print(f"\n🏆 Top 5 블로거:")
    for i, blogger in enumerate(result.get("top_bloggers", [])[:5], 1):
        print(f"   {i}. {blogger['name']} (@{blogger['blog_id']})")
        print(f"      - 관련성: {blogger['relevance_score']}/100")
        print(f"      - 이웃 수: {blogger.get('followers', 'N/A')}")
        print(f"      - 협찬 경험: {'✅' if blogger.get('sponsored_experience') else '❌'}")
        print(f"      - URL: {blogger['profile_url']}")
        print()

    # 리포트
    print("\n📈 전체 현황:")
    report = ambassador.get_discovery_report()
    print(f"   총 인플루언서: {report.get('total', 0)}명")
    for status, data in report.get("by_status", {}).items():
        print(f"   - {status}: {data['count']}명 (평균 점수: {data['avg_relevance_score']})")
