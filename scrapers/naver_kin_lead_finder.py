#!/usr/bin/env python3
"""
Naver 지식인 Lead Finder
- Naver Kin Search API를 활용한 고의도 리드 발굴 전문 모듈
- Q&A 게시글에서 추천 요청/비교/경험 문의 등을 스코어링
- 고점수 리드는 viral_targets에 자동 등록 + Telegram 알림
"""
import sys
import os
import re
import time
import json
import logging
import hashlib
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Robust Path Setup for Hybrid Execution (Standalone vs Module)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Force UTF-8 output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    from db.database import DatabaseManager
    from utils import ConfigManager
except ImportError:
    print("Import Error: Check directory structure.")
    sys.exit(1)

logger = logging.getLogger(__name__)


class NaverKinLeadFinder:
    """
    Naver 지식인 API 기반 리드 발굴 엔진.
    고의도 질문을 스코어링하여 리드 후보를 자동 감지합니다.
    """

    # Naver Kin Search API endpoint
    KIN_API_URL = 'https://openapi.naver.com/v1/search/kin.json'

    # Focused lead discovery queries
    BASE_QUERIES = [
        "청주 한의원 추천",
        "청주 다이어트 한약 어디",
        "청주 교통사고 한의원 추천",
        "한의원 추천해주세요 청주",
        "청주 좋은 한의원",
        "청주 한약 효과",
    ]

    # Location keywords for scoring
    LOCATION_KEYWORDS = ['청주', '충북', '충청북도', '흥덕구', '상당구', '청원구', '서원구']

    # Recommendation-seeking keywords
    RECOMMENDATION_KEYWORDS = ['추천', '어디', '좋은곳', '알려주세요', '추천해주세요', '소개', '괜찮은']

    # Treatment-specific keywords
    TREATMENT_KEYWORDS = [
        '다이어트', '교통사고', '안면비대칭', '여드름', '체형교정',
        '추나', '한약', '침', '디스크', '통증',
    ]

    # Intent classification patterns
    INTENT_PATTERNS = {
        'seeking_recommendation': ['추천', '어디', '좋은곳', '알려주세요', '추천해주세요', '소개해주세요'],
        'comparing_options': ['비교', '차이', 'vs', '어디가 나', '어디가 더', '뭐가 다', '둘 다'],
        'asking_experience': ['후기', '경험', '다녀보', '가봤', '효과', '다녀왔', '솔직', '리뷰'],
        'general_inquiry': ['궁금', '질문', '문의', '알고 싶', '어떤가요', '괜찮나요'],
    }

    # Category keyword mapping (from business_profile.json patterns)
    CATEGORY_MAP = {
        '다이어트': ['다이어트', '살빼', '체중', '비만', '감량', '산후다이어트', '다이어트한약'],
        '비대칭/교정': ['비대칭', '안면비대칭', '얼굴비대칭', '체형교정', '골반', '교정', '추나'],
        '피부': ['피부', '여드름', '아토피', '습진', '트러블'],
        '교통사고': ['교통사고', '자동차사고', '교통사고한의원', '사고후유증'],
        '통증/디스크': ['통증', '디스크', '허리', '목', '어깨', '관절', '척추'],
    }

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()

        # Load API keys for rotation
        self.api_keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS")

        # Fallback to single key
        if not self.api_keys:
            cid = self.config.get_api_key("NAVER_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})

        self.current_key_index = 0

        if self.api_keys:
            logger.info(f"Loaded {len(self.api_keys)} Naver Search API Key(s) for rotation.")
        else:
            logger.warning("Naver Search API credentials not found. Lead finder will be disabled.")

        # Telegram bot (optional)
        self.telegram_bot = None
        self._init_telegram()

        # Business profile
        self.business_name = ""
        self.region = "청주"
        self._load_business_profile()

        # Ensure DB tables
        self._ensure_tables()

    def _load_business_profile(self):
        """config/business_profile.json에서 업체 정보 로드"""
        profile_path = os.path.join(project_root, 'config', 'business_profile.json')
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                business = data.get('business', {})
                self.business_name = business.get('name', '')
                self.region = business.get('region', '청주')
        except Exception as e:
            logger.error(f"Error loading business profile: {e}")

    def _init_telegram(self):
        """Telegram 알림 봇 초기화 (선택사항)"""
        try:
            from alert_bot import TelegramBot
            token = self.config.get_api_key('TELEGRAM_BOT_TOKEN')
            chat_id = self.config.get_api_key('TELEGRAM_CHAT_ID')
            if token and chat_id:
                self.telegram_bot = TelegramBot(token=token, chat_id=chat_id)
                logger.info("Telegram notification bot initialized")
        except ImportError:
            logger.debug("alert_bot module not found, Telegram notifications disabled")
        except Exception as e:
            logger.warning(f"Telegram init failed: {e}")

    def _ensure_tables(self):
        """필요한 DB 테이블 생성/확인"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                # community_mentions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS community_mentions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        keyword TEXT NOT NULL,
                        title TEXT,
                        content_preview TEXT,
                        author TEXT,
                        url TEXT,
                        url_hash TEXT UNIQUE,
                        comment_count INTEGER DEFAULT 0,
                        engagement_count INTEGER DEFAULT 0,
                        mention_type TEXT DEFAULT 'mention',
                        is_lead_candidate INTEGER DEFAULT 0,
                        is_our_mention INTEGER DEFAULT 0,
                        scanned_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_community_url_hash
                    ON community_mentions(url_hash)
                ''')
                conn.commit()
                logger.info("DB tables ensured")
        except Exception as e:
            logger.error(f"Error ensuring DB tables: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """현재 API 키로 헤더 생성"""
        if not self.api_keys:
            return {}
        key_data = self.api_keys[self.current_key_index]
        return {
            "X-Naver-Client-Id": key_data["id"],
            "X-Naver-Client-Secret": key_data["secret"],
        }

    def _rotate_key(self):
        """다음 API 키로 강제 로테이션"""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.info(f"API Key rotated to index {self.current_key_index}")

    def _advance_key_round_robin(self):
        """요청 배치마다 키 순환"""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 제거"""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _url_hash(url: str) -> str:
        """URL MD5 해시 생성"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def _build_queries(self) -> List[str]:
        """검색 쿼리 목록 생성 (기본 + keywords.json 파생)"""
        queries = list(self.BASE_QUERIES)

        # Load keywords.json and generate derived queries
        kw_path = os.path.join(project_root, 'config', 'keywords.json')
        try:
            if os.path.exists(kw_path):
                with open(kw_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                all_keywords = data.get('naver_place', []) + data.get('blog_seo', [])

                for kw in all_keywords:
                    derived_rec = f"{kw} 추천"
                    derived_where = f"{kw} 어디"
                    if derived_rec not in queries:
                        queries.append(derived_rec)
                    if derived_where not in queries:
                        queries.append(derived_where)
        except Exception as e:
            logger.error(f"Error loading keywords for query building: {e}")

        return queries

    def search_kin(self, query: str, display: int = 30) -> List[Dict[str, Any]]:
        """
        Naver 지식인 Search API 호출

        Args:
            query: 검색 키워드
            display: 결과 수 (최대 100)

        Returns:
            API 응답 items 리스트
        """
        if not self.api_keys:
            return []

        params = {
            'query': query,
            'display': display,
            'sort': 'date',
        }

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            headers = self._get_headers()
            try:
                response = requests.get(
                    self.KIN_API_URL,
                    headers=headers,
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('items', [])

                elif response.status_code in [401, 429]:
                    logger.warning(
                        f"API Error {response.status_code} for '{query}'. "
                        f"Rotating key... (attempt {attempt + 1}/{max_retries})"
                    )
                    self._rotate_key()
                    time.sleep(1.0)
                    continue

                else:
                    logger.warning(
                        f"API Error {response.status_code} for '{query}': "
                        f"{response.text[:200]}"
                    )
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for '{query}' (attempt {attempt + 1})")
                time.sleep(2.0)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for '{query}': {e}")
                break

        return []

    def score_question(self, title: str, description: str) -> int:
        """
        질문의 리드 품질을 스코어링 (0-100)

        Scoring criteria:
            +30: contains location keywords (청주, 충북)
            +25: asking for recommendation
            +20: mentions specific treatment
            +15: appears recent (within 7 days)
            +10: has few/no answers
            -20: already answered with many responses

        Args:
            title: 질문 제목 (HTML 제거됨)
            description: 질문 내용 미리보기 (HTML 제거됨)

        Returns:
            0-100 score
        """
        score = 0
        combined = f"{title} {description}"

        # +30: Location match
        if any(loc in combined for loc in self.LOCATION_KEYWORDS):
            score += 30

        # +25: Recommendation-seeking
        if any(kw in combined for kw in self.RECOMMENDATION_KEYWORDS):
            score += 25

        # +20: Specific treatment mention
        if any(kw in combined for kw in self.TREATMENT_KEYWORDS):
            score += 20

        # +15: Recency heuristic (check for date-like patterns or recent indicators)
        recency_indicators = ['오늘', '어제', '최근', '요즘', '이번주', '이번 주', '며칠']
        if any(ind in combined for ind in recency_indicators):
            score += 15

        # +10 / -20: Answer count heuristic from description
        few_answer_signals = ['답변 0', '답변이 없', '아직 답변', '0개의 답변']
        many_answer_signals = ['채택', '답변 완료', '답변 5', '답변 10']

        if any(sig in combined for sig in few_answer_signals):
            score += 10
        elif any(sig in combined for sig in many_answer_signals):
            score -= 20

        # Clamp to 0-100
        return max(0, min(100, score))

    def classify_intent(self, title: str, description: str) -> str:
        """
        질문의 의도를 분류

        Returns:
            'seeking_recommendation', 'comparing_options',
            'asking_experience', 'general_inquiry'
        """
        combined = f"{title} {description}"

        # Score each intent
        best_intent = 'general_inquiry'
        best_score = 0

        for intent, patterns in self.INTENT_PATTERNS.items():
            match_count = sum(1 for p in patterns if p in combined)
            if match_count > best_score:
                best_score = match_count
                best_intent = intent

        return best_intent

    def _detect_category(self, text: str) -> Optional[str]:
        """텍스트에서 카테고리 감지"""
        for category, keywords in self.CATEGORY_MAP.items():
            if any(kw in text for kw in keywords):
                return category
        return None

    def _register_viral_target(self, lead: Dict[str, Any]) -> bool:
        """
        고점수 리드를 viral_targets 테이블에 자동 등록

        Args:
            lead: scored lead dict

        Returns:
            True if registered, False if already exists or failed
        """
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # Check for URL dedup in viral_targets
                cursor.execute(
                    'SELECT COUNT(*) FROM viral_targets WHERE url = ?',
                    (lead['url'],)
                )
                count = cursor.fetchone()[0]
                if count > 0:
                    return False

                # Detect category from content
                combined = f"{lead['title']} {lead['content_preview']}"
                category = self._detect_category(combined) or '기타'

                # Generate a unique ID
                target_id = f"kin_lead_{self._url_hash(lead['url'])[:12]}"

                cursor.execute('''
                    INSERT OR IGNORE INTO viral_targets
                    (id, platform, url, title, content_preview, matched_keywords,
                     category, is_commentable, comment_status, priority_score,
                     discovered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    target_id,
                    'naver_kin',
                    lead['url'],
                    lead['title'][:500],
                    lead['content_preview'][:1000],
                    json.dumps([lead.get('keyword', '')], ensure_ascii=False),
                    category,
                    1,
                    'pending',
                    lead.get('score', 0),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ))
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(
                        f"Registered viral target: {lead['title'][:40]}... "
                        f"(score={lead.get('score', 0)}, category={category})"
                    )
                    return True

        except Exception as e:
            logger.error(f"Error registering viral target: {e}")

        return False

    def _send_telegram_notification(self, lead: Dict[str, Any]):
        """고점수 리드에 대한 Telegram 알림 발송"""
        if not self.telegram_bot:
            return

        try:
            message = (
                f"[Kin Lead Alert] Score: {lead.get('score', 0)}\n"
                f"Title: {lead['title'][:100]}\n"
                f"Intent: {lead.get('intent', 'unknown')}\n"
                f"URL: {lead['url']}\n"
                f"Keyword: {lead.get('keyword', '')}"
            )
            self.telegram_bot.send_message(message)
            logger.info(f"Telegram notification sent for lead: {lead['title'][:40]}...")
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")

    def save_lead(self, lead: Dict[str, Any]) -> bool:
        """
        리드를 community_mentions 테이블에 저장

        Returns:
            True if inserted (new), False if skipped (duplicate)
        """
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO community_mentions
                    (platform, keyword, title, content_preview, author,
                     url, url_hash, comment_count, engagement_count,
                     mention_type, is_lead_candidate, is_our_mention, scanned_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'naver_kin',
                    lead.get('keyword', ''),
                    lead.get('title', ''),
                    lead.get('content_preview', ''),
                    lead.get('author', ''),
                    lead.get('url', ''),
                    lead.get('url_hash', ''),
                    0,
                    0,
                    lead.get('intent', 'general_inquiry'),
                    1 if lead.get('score', 0) >= 50 else 0,
                    0,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error saving lead: {e}")
            return False

    def run(self) -> Dict[str, Any]:
        """
        메인 실행: 모든 쿼리에 대해 지식인 검색 및 스코어링

        Returns:
            실행 결과 요약
        """
        if not self.api_keys:
            logger.error("No API keys configured. Aborting.")
            return {'error': 'No API keys configured'}

        queries = self._build_queries()
        if not queries:
            logger.warning("No queries built. Aborting.")
            return {'error': 'No queries'}

        logger.info(f"Starting Naver Kin Lead Finder with {len(queries)} queries")

        all_leads: List[Dict[str, Any]] = []
        seen_urls: set = set()
        total_requests = 0
        new_saved = 0
        viral_registered = 0
        telegram_sent = 0

        for q_idx, query in enumerate(queries):
            logger.info(f"[{q_idx + 1}/{len(queries)}] Searching: '{query}'")

            # Rotate key per query
            self._advance_key_round_robin()

            items = self.search_kin(query, display=30)
            total_requests += 1

            for item in items:
                title = self._strip_html(item.get('title', ''))
                description = self._strip_html(item.get('description', ''))
                link = item.get('link', '')

                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                # Score the question
                score = self.score_question(title, description)
                intent = self.classify_intent(title, description)

                lead = {
                    'keyword': query,
                    'title': title[:500],
                    'content_preview': description[:1000],
                    'author': '',
                    'url': link,
                    'url_hash': self._url_hash(link),
                    'score': score,
                    'intent': intent,
                }

                all_leads.append(lead)

                # Save to community_mentions
                if self.save_lead(lead):
                    new_saved += 1

                # Auto-register high-score leads as viral targets
                if score >= 70:
                    if self._register_viral_target(lead):
                        viral_registered += 1

                # Telegram notification for very high score leads
                if score >= 80:
                    self._send_telegram_notification(lead)
                    telegram_sent += 1

            # Rate limit: 0.3s between requests
            time.sleep(0.3)

        # Sort all leads by score descending
        all_leads.sort(key=lambda x: x['score'], reverse=True)

        summary = {
            'queries_searched': len(queries),
            'total_requests': total_requests,
            'total_leads_found': len(all_leads),
            'new_saved': new_saved,
            'viral_targets_registered': viral_registered,
            'telegram_notifications': telegram_sent,
            'top_leads': all_leads[:20],
            'score_distribution': {
                'high_90+': sum(1 for l in all_leads if l['score'] >= 90),
                'good_70_89': sum(1 for l in all_leads if 70 <= l['score'] < 90),
                'medium_50_69': sum(1 for l in all_leads if 50 <= l['score'] < 70),
                'low_under_50': sum(1 for l in all_leads if l['score'] < 50),
            },
        }

        return summary

    def print_summary(self, summary: Dict[str, Any]):
        """결과 요약 및 스코어링 테이블 출력"""
        print("\n" + "=" * 80)
        print("  Naver Kin Lead Finder - Results")
        print("=" * 80)

        if 'error' in summary:
            print(f"  ERROR: {summary['error']}")
            return

        print(f"  Queries searched:          {summary['queries_searched']}")
        print(f"  Total API requests:        {summary['total_requests']}")
        print(f"  Total leads found:         {summary['total_leads_found']}")
        print(f"  New records saved:         {summary['new_saved']}")
        print(f"  Viral targets registered:  {summary['viral_targets_registered']}")
        print(f"  Telegram notifications:    {summary['telegram_notifications']}")

        # Score distribution
        dist = summary.get('score_distribution', {})
        print()
        print("  Score Distribution:")
        print("  " + "-" * 40)
        print(f"    90+  (Excellent) : {dist.get('high_90+', 0)}")
        print(f"    70-89 (Good)     : {dist.get('good_70_89', 0)}")
        print(f"    50-69 (Medium)   : {dist.get('medium_50_69', 0)}")
        print(f"    <50   (Low)      : {dist.get('low_under_50', 0)}")

        # Top leads table
        top_leads = summary.get('top_leads', [])
        if top_leads:
            print()
            print("  Top Leads (sorted by score):")
            print("  " + "-" * 76)
            print(f"  {'Score':>5s} | {'Intent':<25s} | {'Title':<42s}")
            print("  " + "-" * 76)

            for lead in top_leads[:15]:
                score = lead.get('score', 0)
                intent = lead.get('intent', 'unknown')
                title = lead.get('title', '')[:40]

                # Highlight high-score leads
                marker = ""
                if score >= 90:
                    marker = " *** TOP"
                elif score >= 70:
                    marker = " ** HIGH"
                elif score >= 50:
                    marker = " *"

                print(f"  {score:>5d} | {intent:<25s} | {title:<42s}{marker}")

            if len(top_leads) > 15:
                print(f"  ... and {len(top_leads) - 15} more leads")

        print("=" * 80)


def main():
    """Standalone execution entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("  Naver Kin Lead Finder")
    print("  High-intent Q&A lead discovery via Naver Search API")
    print("=" * 80)

    finder = NaverKinLeadFinder()
    summary = finder.run()
    finder.print_summary(summary)

    return summary


if __name__ == '__main__':
    main()
