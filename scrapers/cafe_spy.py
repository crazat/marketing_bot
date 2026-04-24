import sys
import json
import time
import random
import os
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

# Robust Path Setup for Hybrid Execution (Standalone vs Module)

# Determine the project root based on the script location
# cafe_spy.py is in /scrapers, so root is one level up
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'marketing_bot_web', 'backend'))

# Now standard imports should work if running from root or scrapers/
try:
    from db.database import DatabaseManager
    from utils import logger, ConfigManager
    from alert_bot import TelegramBot
    from services.ai_client import ai_generate
except ImportError:
    # This might happen if project structure is totally different, but sys.path insert shields us
    print("⚠️ Import Error: Check directory structure.")
    sys.exit(1)

# Force UTF-8 output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

class CafeSpy:
    """
    Phase 2: Naver Cafe Scraper (Community Spy).
    Monitors target Mom Cafes for keywords related to the clinic.
    """
    def __init__(self, config_path=None):
        self.db = DatabaseManager()
        
        # Resolve config path relative to this script
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            target_in_config = os.path.join(base_dir, 'config', 'targets.json')
            target_in_root = os.path.join(base_dir, 'targets.json')
            
            if os.path.exists(target_in_config):
                self.config_path = target_in_config
            else:
                self.config_path = target_in_root
        else:
            self.config_path = config_path

        self._load_config()
        self.driver = None
        self.data_dir = os.path.join(os.path.dirname(self.config_path), 'scraped_data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Default Cafes (Hardcoded fallback)
        default_cafes = [
            {
                "name": "청주 맘스캠프 (맘캠 이야기방)",
                "base_url": "https://cafe.naver.com/cjcjmom",
                "menu_id": "12"
            },
            {
                "name": "청주 맘블리 (청주맘이야기)",
                "base_url": "https://cafe.naver.com/cjcjmommy",
                "menu_id": "5"
            },
            {
                "name": "청주 테크노폴리스맘 (동네이야기)",
                "base_url": "https://cafe.naver.com/technomomis",
                "menu_id": "5"
            }
        ]
        
        # Load extra cafes from config if present
        extra_cafes = self.config.get('cafes', [])
        
        self.target_cafes = extra_cafes if extra_cafes else default_cafes
        self.report_lines = []
        self.all_leads = [] # [Fix] Instance variable for emergency recovery

        # [1단계] TelegramBot 초기화 (Hot Lead 알림용)
        try:
            config = ConfigManager(project_root)
            self.telegram = TelegramBot(
                token=config.get_api_key("TELEGRAM_BOT_TOKEN") or "",
                chat_id=config.get_api_key("TELEGRAM_CHAT_ID") or ""
            )
        except Exception as e:
            print(f"⚠️ TelegramBot 초기화 실패: {e}")
            self.telegram = TelegramBot()  # Mock 모드로 동작

        # [핵심 수정] 마케팅 리드 품질 필터 설정
        self.MAX_POST_AGE_DAYS = 180  # 6개월 이내 게시물 수집 (확장됨)
        
        # 광고/홍보글 제외 키워드 (이런 단어가 있으면 광고글)
        self.AD_EXCLUDE_KEYWORDS = [
            # 업체 홍보
            "체험단", "이벤트", "할인", "협력업체", "입점", "모집", "프리마켓",
            "동행인사", "동행 인사", "인사드립니다", "입점했습니다",
            # 무관한 분야
            "강아지", "반려견", "슬개골", "성형외과", "분양", "아파트",
            "주식", "코인", "부동산", "매매", "임대", "분양권",
            "케이크", "베이커리", "과일", "생선", "맛집", "카페", "음식점",
            "돌잔치", "환갑", "돌사진", "파티올", "스튜디오",
            "휴대폰", "통신", "핸드폰", "가구", "인테리어", "줄눈", "헌옷",
            # 성형 (한의원 아님)
            "성형", "쌍수", "코수술", "지방흡입",
            # [2단계] 무관 의료 분야 추가
            # 소아과
            "소아과", "소아청소년과", "예방접종", "영유아검진",
            # 산부인과
            "산부인과", "출산", "제왕절개", "산후조리원",
            # 치과
            "치과", "임플란트", "치아교정", "충치", "스케일링",
            # 안과
            "안과", "라식", "라섹", "백내장",
            # 이비인후과
            "이비인후과", "코골이수술", "비염수술",
            # 피부과 (시술 위주)
            "피부과", "레이저", "보톡스", "필러"
        ]
        
        # 질문글 감지 패턴 (이런 패턴이 있어야 진짜 질문글)
        self.INQUIRY_PATTERNS = [
            "추천", "어디", "궁금", "있을까요", "있나요", "알려주세요",
            "가봤는데", "다니시는분", "해보신분", "경험", "후기",
            "좋은곳", "잘하는", "괜찮은", "어떤가요", "어때요",
            "고민", "도움", "상담", "문의", "질문",
            # 추가 패턴
            "받을 수", "수 있는", "되는곳", "되나요", "가능한",
            "어디서", "어떻게", "뭐가", "뭘로", "좋은"
        ]
        
        # 진료 관련 키워드 (규림한의원 진료과목 기준)
        self.HEALTH_KEYWORDS = [
            # ===== 다이어트 =====
            "다이어트", "살빼기", "체중", "뱃살", "허벅지", "팔뚝", "식욕", "요요",
            "체중감량", "감량", "비만", "다이어트약", "다이어트한약", "감비환", "지방",
            
            # ===== 비대칭 교정 =====
            "비대칭", "안면비대칭", "얼굴비대칭", "골반비대칭", "어깨비대칭",
            "턱관절", "턱", "교정", "체형교정", "자세교정", "휜다리", "일자목",
            "거북목", "척추측만", "측만증",
            
            # ===== 통증 =====
            "허리", "목", "어깨", "무릎", "관절", "통증", "디스크", "추나",
            "허리통증", "목통증", "어깨통증", "무릎통증", "손목", "손저림",
            "오십견", "근막통증", "근육통", "담", "담결림",
            
            # ===== 자동차보험/교통사고 =====
            "교통사고", "자동차사고", "자동차보험", "자보", "보험입원",
            "사고입원", "교통사고한의원", "사고치료", "추돌", "접촉사고",
            "입원", "입원치료", "재활", "도수치료",
            
            # ===== 피부/여드름/흉터 =====
            "여드름", "피부", "트러블", "아토피", "두드러기", "피부염",
            "여드름흉터", "흉터", "여드름자국", "피부트러블", "성인여드름",
            "등여드름", "가슴여드름", "턱여드름", "이마여드름",
            "모공", "피부재생", "피부관리",
            
            # ===== 기타 한의원 관련 =====
            "한의원", "한방", "침", "뜸", "한약", "보약", "보양", "면역",
            "체질", "사상체질", "공진단", "경옥고",
            
            # ===== 진료 편의성 =====
            "야간진료", "일요일진료", "365일", "주말진료", "야간한의원"
        ]

    def _send_hot_lead_alert(self, lead: dict, analysis: dict):
        """
        [1단계] Hot Lead 발견 시 Telegram 즉시 알림.
        """
        title = lead.get('title', '제목 없음')[:50]
        cafe = lead.get('cafe', 'Unknown')
        author = lead.get('author', 'Unknown')
        url = lead.get('link', '')
        summary = analysis.get('summary', '')[:100]

        message = (
            f"🔥 *Hot Lead 발견!*\n\n"
            f"*제목*: {title}...\n"
            f"*카페*: {cafe}\n"
            f"*작성자*: {author}\n"
            f"*요약*: {summary}\n\n"
            f"[바로가기]({url})"
        )

        try:
            self.telegram.send_message(message)
            print(f"   📤 Hot Lead 알림 발송: {title}...")
        except Exception as e:
            print(f"   ⚠️ 알림 발송 실패: {e}")

    def _is_marketing_lead(self, title: str, body: str = "") -> bool:
        """
        [완화된 필터] 마케팅 리드 적합성 판단.
        조건: (1) 광고글 아님 AND (2) 질문글임 OR 건강 관련
        """
        text = f"{title} {body}".lower()
        title_lower = title.lower() if title else ""
        
        # 1. 광고/홍보글 먼저 제외
        for ad_word in self.AD_EXCLUDE_KEYWORDS:
            if ad_word in title_lower:
                print(f"   🚫 광고글 제외 ('{ad_word}'): {title[:40]}...")
                return False
        
        # 2. 질문글 패턴 확인
        is_inquiry = any(pattern in text for pattern in self.INQUIRY_PATTERNS)
        
        # 3. 건강/진료 관련 확인
        is_health_related = any(keyword in text for keyword in self.HEALTH_KEYWORDS)
        
        # [완화] 질문글이거나 OR 건강 관련이면 수집
        if is_inquiry and is_health_related:
            print(f"   ✅ 핵심 리드 (질문+건강): {title[:40]}...")
            return True
        elif is_health_related:
            print(f"   🟡 건강 관련 (질문 아님): {title[:40]}...")
            return True  # 건강 관련이면 질문 아니어도 수집
        elif is_inquiry:
            print(f"   ⚠️ 질문글이지만 건강 무관: {title[:40]}...")
            return False
        else:
            print(f"   ❌ 질문글 아님 (홍보/정보글): {title[:40]}...")
            return False

    def _is_relevant_post(self, title: str) -> bool:
        """[호환성 유지] 기존 코드와 호환 - 간단한 체크만"""
        if not title:
            return False
        
        # 광고 제외만 수행 (상세 판단은 _is_marketing_lead에서)
        for ad_word in self.AD_EXCLUDE_KEYWORDS:
            if ad_word in title:
                return False
        return True

    def _is_before_cutoff(self, date_str: str, cutoff_date: str) -> bool:
        """
        [3단계] 증분 스캔: 게시물이 cutoff_date보다 이전인지 확인.
        cutoff_date보다 이전이면 True (스킵해야 함).
        """
        if not cutoff_date or not date_str:
            return False  # cutoff가 없으면 스킵하지 않음

        try:
            today = datetime.now()

            # 상대 날짜 처리: "1일 전", "23시간 전" 등
            if "시간 전" in date_str or "분 전" in date_str:
                return False  # 최근 게시물

            match_days = re.search(r'(\d+)일 전', date_str)
            if match_days:
                days_ago = int(match_days.group(1))
                post_date = today.replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=days_ago)
            else:
                # 절대 날짜: "2026.01.20."
                date_match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', date_str)
                if date_match:
                    post_date = datetime(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3))
                    )
                else:
                    return False  # 파싱 실패시 스킵하지 않음

            # cutoff_date 파싱
            cutoff_match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', cutoff_date)
            if cutoff_match:
                cutoff = datetime(
                    int(cutoff_match.group(1)),
                    int(cutoff_match.group(2)),
                    int(cutoff_match.group(3))
                )
                return post_date <= cutoff

            return False
        except Exception as e:
            print(f"   ⚠️ Cutoff date check error: {e}")
            return False

    def _is_recent_post(self, date_str: str) -> bool:
        """날짜 필터: MAX_POST_AGE_DAYS 이내 게시물만 허용."""
        if not date_str:
            return True
        
        try:
            from datetime import datetime
            import re
            
            today = datetime.now()
            
            # 상대 날짜: "1일 전", "23시간 전", "1주 전"
            if "시간 전" in date_str or "분 전" in date_str:
                return True
            
            match_days = re.search(r'(\d+)일 전', date_str)
            if match_days:
                return int(match_days.group(1)) <= self.MAX_POST_AGE_DAYS
            
            match_weeks = re.search(r'(\d+)주 전', date_str)
            if match_weeks:
                return (int(match_weeks.group(1)) * 7) <= self.MAX_POST_AGE_DAYS
            
            match_months = re.search(r'(\d+)개월 전', date_str)
            if match_months:
                return (int(match_months.group(1)) * 30) <= self.MAX_POST_AGE_DAYS
            
            # 절대 날짜: "2026.01.20."
            date_match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', date_str)
            if date_match:
                post_date = datetime(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3))
                )
                return (today - post_date).days <= self.MAX_POST_AGE_DAYS
            
            return True
        except Exception as e:
            print(f"   ⚠️ Date parsing error: {e}")
            return True

    def _load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
            
        # Extract keywords from 'targets' + 'community_scan_keywords'
        self.spy_keywords = set()
        
        # 1. From generic list in config
        for kw in self.config.get('community_scan_keywords', []):
            self.spy_keywords.add(kw)
            
        # 2. From competitor targets (if you want to spy on them too)
        for target in self.config.get('targets', []):
            for kw in target.get('keywords', []):
                self.spy_keywords.add(kw)
        
        # Fallback if empty
        if not self.spy_keywords:
            self.spy_keywords = {"청주 한의원", "청주 다이어트"}
            
        print(f">> Loaded {len(self.spy_keywords)} keywords for monitoring.")

    def _batch_analyze_leads(self, leads: list) -> dict:
        """
        [BATCH PROCESSING] Analyze multiple leads in a single AI call.
        Reduces API calls by 5-10x and saves ~64% tokens.
        
        Returns:
            Dict mapping lead index to analysis: {0: {'summary': ..., 'score': ..., 'reply': ...}, ...}
        """
        if not leads:
            return {}
        
        print(f"   🧠 Batch analyzing {len(leads)} leads...")
        
        try:
            # Try using BatchProcessor from prompt_manager
            from prompt_manager import BatchProcessor
            processor = BatchProcessor(batch_size=10)
            
            # Prepare leads with required fields
            prepared_leads = []
            for i, lead in enumerate(leads):
                prepared_leads.append({
                    'id': i,
                    'title': lead.get('title', ''),
                    'author': lead.get('author', 'Unknown'),
                    'body': lead.get('body', '') or lead.get('content', '')
                })
            
            results = processor.process_leads(prepared_leads)
            
            # Convert to dict indexed by original position
            analysis_dict = {}
            for result in results:
                idx = result.get('id', 0)
                analysis_dict[idx] = {
                    'summary': result.get('summary', '요약 없음'),
                    'score': result.get('score', 'Unknown'),
                    'reply': result.get('reply', '분석 실패')
                }
            
            print(f"   ✅ Batch analysis complete: {len(analysis_dict)} leads processed")
            return analysis_dict
            
        except ImportError:
            print("   ⚠️ BatchProcessor not available, falling back to individual analysis")
            return self._fallback_individual_analysis(leads)
        except Exception as e:
            print(f"   ❌ Batch analysis failed: {e}")
            return self._fallback_individual_analysis(leads)
    
    def _fallback_individual_analysis(self, leads: list) -> dict:
        """Fallback to individual AI calls if batch processing fails."""
        results = {}

        for i, lead in enumerate(leads):
            try:
                from prompt_manager import get_prompt_manager
                pm = get_prompt_manager()
                prompt_info = pm.get('cafe_spy', 'lead_analysis',
                                     title=lead.get('title', ''),
                                     author=lead.get('author', 'Unknown'),
                                     body=(lead.get('body', '') or '')[:1000])

                text = ai_generate(prompt_info['prompt'], temperature=0.5, max_tokens=4096)

                # Parse response
                summary_match = re.search(r'SUMMARY[:\s]*(.*?)(?=SCORE|$)', text, re.IGNORECASE | re.DOTALL)
                score_match = re.search(r'SCORE[:\s]*(\w+)', text, re.IGNORECASE)
                reply_match = re.search(r'REPLY[:\s]*(.*?)(?=---|\Z)', text, re.IGNORECASE | re.DOTALL)

                results[i] = {
                    'summary': summary_match.group(1).strip() if summary_match else '요약 없음',
                    'score': score_match.group(1).strip() if score_match else 'Unknown',
                    'reply': reply_match.group(1).strip() if reply_match else '분석 실패'
                }

            except Exception as e:
                results[i] = {'summary': f'Error: {str(e)[:50]}', 'score': 'Unknown', 'reply': ''}

        return results

    def _init_driver(self):
        """Initialize Chrome driver with dynamic path resolution."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            import os
            
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Priority: ENV > WDM > Fallback
            driver_path = os.environ.get('CHROMEDRIVER_PATH')
            
            if driver_path and os.path.exists(driver_path):
                logger.info(f"Using ChromeDriver from ENV: {driver_path}")
                self.driver = webdriver.Chrome(service=Service(driver_path), options=options)
            else:
                # Use WebDriverManager for automatic driver management
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    logger.info("Using WebDriverManager for ChromeDriver...")
                    self.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=options
                    )
                except ImportError:
                    # Fallback to system PATH
                    logger.warning("WebDriverManager not installed, using system PATH")
                    self.driver = webdriver.Chrome(options=options)
            
            self.driver.set_page_load_timeout(60)
            logger.info("ChromeDriver initialized successfully.")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}", exc_info=True)
            raise

    def search_via_cafe_internal(self, cafe_name, base_url, keyword):
        """
        [Phase 1.2] Search via Cafe's internal ArticleSearchList API.
        This ensures results are ONLY from the target cafe.
        """
        print(f"🔎 Cafe Internal Search: '{keyword}' in '{cafe_name}'...")
        
        # Ensure driver is alive
        if not self.driver:
            self._init_driver()
        
        # Extract cafe_id from base_url (e.g., "https://cafe.naver.com/cjcjmom" -> "cjcjmom")
        from urllib.parse import quote
        cafe_id = base_url.rstrip('/').split('/')[-1]
        encoded_keyword = quote(keyword)
        
        # Use cafe's internal search URL
        internal_url = f"https://cafe.naver.com/{cafe_id}/ArticleSearchList.nhn?search.searchBy=0&search.query={encoded_keyword}&search.sortBy=date"
        print(f"   📍 Search URL: {internal_url}")
        
        self.driver.get(internal_url)

        # [성능 최적화] 고정 대기 → 명시적 대기로 전환
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#cafe_main, .article-board, .article_lst"))
            )
        except Exception:
            time.sleep(2)

        # Handle iframe if present
        try:
            self.driver.switch_to.frame("cafe_main")
        except Exception:
            pass

        # Scroll for more results
        for _ in range(2):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # [성능 최적화] 스크롤 후 문서 로드 완료 대기
            try:
                WebDriverWait(self.driver, 3).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                time.sleep(0.5)
        
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        
        # Selectors for cafe internal search results
        article_selectors = [
            'div.article-board tbody tr',
            'ul.article-movie-sub li',
            '.article_lst li',
            '.article-album-sub li',
            'tr[class*="article"]',
            'div.inner_list a'
        ]
        
        found_leads = []
        items = []
        
        for sel in article_selectors:
            items = soup.select(sel)
            if items:
                print(f"   ✅ Found {len(items)} items with selector: {sel}")
                break
        
        if not items:
            print(f"   ⚠️ No items found with any selector")
            return found_leads
        
        for item in items[:20]:  # Limit to 20 items
            try:
                # Title extraction
                title_el = item.select_one('a.article, a.tit, .item_subject a, .board-list a, a[class*="article"]')
                if not title_el:
                    # Try alternate: any link with substantial text
                    for a_tag in item.select('a'):
                        text = a_tag.get_text(strip=True)
                        if len(text) > 5:
                            title_el = a_tag
                            break
                
                if not title_el:
                    continue
                
                title = title_el.get_text(strip=True)
                href = title_el.get('href', '')
                
                # Build full link
                if href and not href.startswith('http'):
                    link = f"https://cafe.naver.com{href}" if href.startswith('/') else f"https://cafe.naver.com/{cafe_id}/{href}"
                else:
                    link = href
                
                # Author
                author_el = item.select_one('.td_name, .writer, .p-nick, [class*="author"], [class*="nick"]')
                author = author_el.get_text(strip=True) if author_el else "Unknown"
                
                # Date
                date_el = item.select_one('.td_date, .date, .time, [class*="date"]')
                date = date_el.get_text(strip=True) if date_el else ""
                
                if title and link:
                    # [Phase 2] Apply date filter
                    if not self._is_recent_post(date):
                        print(f"   ⏰ Skipped (too old): {title[:30]}... | {date}")
                        continue
                    
                    # [Phase 2] Apply relevance filter
                    if not self._is_relevant_post(title):
                        continue
                    
                    print(f"      👀 Accept: {title[:30]}... | {date}")
                    found_leads.append({
                        "cafe": cafe_name,
                        "title": title,
                        "keywords": [keyword],
                        "author": author,
                        "date": date,
                        "link": link,
                        "referer_url": internal_url
                    })
            except Exception as e:
                print(f"   ⚠️ Error processing item: {e}")
                continue
        
        # Deep Read for selected leads
        detailed_leads = self._deep_read_leads(found_leads)
        return detailed_leads

    def _deep_read_leads(self, found_leads):
        """[Phase 1.2] Extracted Deep Read logic for reuse by both search methods."""
        detailed_leads = []
        seen_links = set()  # [Phase 3.1] Duplicate prevention
        
        for item in found_leads:
            # [Phase 3.1] Skip duplicates
            if item['link'] in seen_links:
                print(f"      ⏭️ Skip duplicate: {item['title'][:30]}...")
                continue
            seen_links.add(item['link'])
            
            try:
                print(f"      📖 Reading: {item['title'][:30]}...")

                self.driver.get(item['link'])

                # [성능 최적화] 명시적 대기
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#cafe_main, .article_container, .ArticleContentBox"))
                    )
                except Exception:
                    time.sleep(1.5)

                try:
                    self.driver.switch_to.frame("cafe_main")
                except Exception:
                    pass 
                
                deep_soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                
                content_el = None
                # [Phase 1.1] Expanded content selectors
                content_selectors = [
                    '.se-main-container',
                    '.ContentRenderer', 
                    '.article_viewer',
                    '#tbody',
                    '.article_container',
                    '.se-module-text',
                    '.NHN_Writeform_Main',
                    '#postContent',
                    '.post_content',
                    'div[class*="article"]',
                    'div[class*="content"]'
                ]
                
                for sel in content_selectors:
                    content_el = deep_soup.select_one(sel)
                    if content_el:
                        print(f"      ✅ Content found with selector: {sel}")
                        break
                    
                if content_el:
                    # Clean trash
                    for trash in content_el.select('.se-map, .se-sticker, .se-video, script, style'):
                        trash.decompose()
                    
                    body_text = content_el.get_text(strip=True)[:1000]
                    print(f"      📄 Body extracted: {len(body_text)} chars")
                    
                    # Image Download
                    try:
                        import requests
                        img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'images_scraped')
                        os.makedirs(img_dir, exist_ok=True)
                        
                        images = content_el.select('img.se-image-resource')
                        if not images: images = content_el.select('img')

                        collected_imgs = []
                        for i, img in enumerate(images[:3]):
                            src = img.get('src')
                            if src and "http" in src:
                                # [Phase 2] 재시도 로직 추가 (최대 2회)
                                for attempt in range(2):
                                    try:
                                        res = requests.get(src, timeout=3)
                                        if res.status_code == 200:
                                            safe_title = "".join([c for c in item['title'] if c.isalnum()])[:10]
                                            fname = f"cafe_bypass_{safe_title}_{i}.jpg"
                                            with open(os.path.join(img_dir, fname), 'wb') as f:
                                                f.write(res.content)
                                            collected_imgs.append(fname)
                                            break  # 성공 시 루프 종료
                                    except Exception as dl_err:
                                        if attempt == 1:  # 마지막 시도에서도 실패
                                            print(f"      ⚠️ Image download failed: {dl_err}")
                                        time.sleep(0.5)  # 재시도 전 대기
                        
                        if collected_imgs:
                            item['images'] = collected_imgs
                            body_text += f"\n[Images Captured: {len(collected_imgs)}]"
                    except Exception as img_err:
                        pass
                else:
                    # Fallback: try to get any text from body
                    body_container = deep_soup.find('body')
                    if body_container:
                        body_text = body_container.get_text(strip=True)[:500]
                        print(f"      ⚠️ Fallback body extraction: {len(body_text)} chars")
                    else:
                        body_text = "Content Restricted (Member Only)"
                        print("      ❌ No content found")
                
                # [Phase 1.1] Extract Real Author & Date with expanded selectors
                try:
                    author_selectors = ['.nickname', '.nick_box', '.WriterInfo .nick', '.profile_info .nick', 'a.nick', '[class*="nickname"]']
                    for sel in author_selectors:
                        nick_el = deep_soup.select_one(sel)
                        if nick_el:
                            item['author'] = nick_el.get_text(strip=True)
                            break
                    
                    date_selectors = ['.date', '.article_info .date', '.WriterInfo .date', 'time', '.datetime', '[class*="date"]']
                    for sel in date_selectors:
                        date_el = deep_soup.select_one(sel)
                        if date_el:
                            item['date'] = date_el.get_text(strip=True)
                            break
                except Exception as meta_err:
                    print(f"      ⚠️ Metadata extraction error: {meta_err}")

                item['body'] = body_text
                detailed_leads.append(item)
                
            except Exception as e:
                print(f"      ⚠️ Deep read error: {e}")
                
        return detailed_leads

    def search_via_portal(self, cafe_name, base_url, keyword, cutoff_date=None):
        """
        [Legacy] Search via Portal - kept for fallback.
        Uses Naver Portal search which may include results from other cafes.
        [3단계] cutoff_date 이전 게시물은 스킵 (증분 스캔).
        """
        print(f"🔎 Portal Search (Fallback): '{keyword}' in '{cafe_name}'...")
        
        if not self.driver:
            self._init_driver()
        
        import re
        from urllib.parse import quote
        clean_name = re.sub(r'\s*\(.*?\)', '', cafe_name).strip()
        query = f"{clean_name} {keyword}"
        encoded_query = quote(query)
        portal_url = f"https://search.naver.com/search.naver?ssc=tab.cafe.all&query={encoded_query}"
        
        self.driver.get(portal_url)

        # [성능 최적화] 명시적 대기
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".cafe_info_box, .total_area, .lst_total"))
            )
        except Exception:
            time.sleep(2)

        for _ in range(3):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # [성능 최적화] 스크롤 후 로드 대기
            try:
                WebDriverWait(self.driver, 3).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                time.sleep(0.5)

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        
        cfg = ConfigManager()
        selectors = cfg.get_selector('cafe_spy', 'portal_search')
        if not selectors:
            selectors = {
                "post_list_items": "li.bx, .view_wrap",
                "title_link": ".title_link, a.api_txt_lines",
                "source_name": ".name, .sub_txt"
            }
        
        items = soup.select(selectors['post_list_items'])
        print(f"   Found {len(items)} items")
        
        found_leads = []
        
        for item in items[:30]: 
            try:
                title_el = item.select_one(selectors['title_link'])
                if not title_el:
                    continue
                
                title = title_el.get_text(strip=True)
                link = title_el['href']
                
                name_el = item.select_one(selectors['source_name'])
                source_name = name_el.get_text(strip=True) if name_el else ""
                
                author = "Unknown" 
                date_el = item.select_one('.sub') or item.select_one('.date')
                date = date_el.get_text(strip=True) if date_el else ""

                # [Fix Plan B] Filter by target cafe name
                # Extract clean cafe name for comparison
                import re
                clean_target = re.sub(r'\s*\(.*?\)', '', cafe_name).strip()
                source_check = source_name.lower()
                
                # Check if this result is from our target cafe
                if clean_target.lower() not in source_check and cafe_name.lower() not in source_check:
                    # Check cafe URL in link as backup
                    cafe_id = base_url.rstrip('/').split('/')[-1]
                    if cafe_id not in link:
                        print(f"   ❌ Filtered (wrong cafe): {source_name}")
                        continue

                # [Phase 2] Apply date filter
                if not self._is_recent_post(date):
                    print(f"   ⏰ Skipped (too old): {title[:30]}... | {date}")
                    continue

                # [3단계] 증분 스캔: cutoff_date 이전 게시물 스킵
                if cutoff_date and self._is_before_cutoff(date, cutoff_date):
                    print(f"   ⏭️ Skipped (before cutoff): {title[:30]}... | {date}")
                    continue

                # [핵심] 마케팅 리드 필터 적용 (질문글 + 건강관련)
                if not self._is_marketing_lead(title):
                    continue

                found_leads.append({
                    "cafe": source_name,
                    "title": title,
                    "keywords": [keyword], 
                    "author": author,
                    "date": date,
                    "link": link,
                    "referer_url": portal_url 
                })
            except Exception as e:
                print(f"   ⚠️ Error processing item: {e}")
                continue
        
        return self._deep_read_leads(found_leads)

    def run(self, cafe_filter=None, keyword_override=None):
        print(f"[{datetime.now()}] Starting Cafe Spy Phase 3...")
        self.db.log_system_event("Cafe Spy", "🚀 Cafe Spy started scanning...")

        try:
            self._init_driver()
            self._load_config()

            global_keywords = list(self.spy_keywords)

            if keyword_override:
                print(f">> Argument Keyword Override: {keyword_override}")
                global_keywords = [k.strip() for k in keyword_override.split(',')]

            if not global_keywords: global_keywords = ["다이어트", "한의원"]

            print(f"🔑 Global Keywords used: {len(global_keywords)} items")
            self.all_leads = []

            target_list = self.target_cafes
            if cafe_filter:
                print(f"🎯 [Worker Mode] Locking Targets: {cafe_filter}")
                self.db.log_system_event("Cafe Spy", f"🎯 Filter applied: {cafe_filter}")
                filtered = []
                for name in cafe_filter:
                    found = [c for c in self.target_cafes if name in c['name']]
                    filtered.extend(found)
                target_list = filtered

            self.active_targets = target_list
            total_leads_session = 0

            for cafe in target_list:
                cafe_name = cafe['name']
                cafe_id = cafe['base_url'].rstrip('/').split('/')[-1]
                self.db.log_system_event("Cafe Spy", f"🏥 Scanning: {cafe_name}...")

                # [3단계] 증분 스캔: 마지막 스캔 정보 조회
                last_scan = self.db.get_last_scan('naver_cafe', cafe_id)
                cutoff_date = last_scan['last_post_date'] if last_scan else None
                if cutoff_date:
                    print(f"   📅 증분 스캔: {cutoff_date} 이후 게시물만 수집")
                else:
                    print(f"   📅 전체 스캔: 최초 실행")

                if "override_keywords" in cafe:
                    current_kws = cafe["override_keywords"]
                    print(f"\n🌍 Scanning {cafe_name} with Specials: {current_kws}")
                else:
                    current_kws = global_keywords
                    print(f"\n🏘️ Scanning {cafe_name} with Globals...")

                cafe_leads_count = 0
                latest_date = None

                for kw in current_kws:
                    try:
                        # [Fix] Use portal search with post-filtering by cafe name
                        # (cafe internal search URL no longer works)
                        leads = self.search_via_portal(cafe_name, cafe['base_url'], kw, cutoff_date)
                        if leads:
                            count = len(leads)
                            total_leads_session += count
                            cafe_leads_count += count
                            self.all_leads.extend(leads)
                            self.db.log_system_event("Cafe Spy", f"✅ Found {count} new leads in {cafe_name} ('{kw}')")

                            # 최신 날짜 추적
                            for lead in leads:
                                if lead.get('date') and (not latest_date or lead['date'] > latest_date):
                                    latest_date = lead['date']

                        time.sleep(random.uniform(1, 2))
                    except Exception as e:
                        logger.error(f"Scan error for {cafe_name}/{kw}: {e}")
                        self.db.log_system_event("Cafe Spy", f"❌ Error scanning {cafe_name}: {str(e)}", "ERROR")

                # [3단계] 스캔 히스토리 업데이트
                if cafe_leads_count > 0 and latest_date:
                    self.db.update_scan_history('naver_cafe', cafe_id, latest_date, cafe_leads_count)
                    print(f"   📝 스캔 히스토리 업데이트: {cafe_id} | {latest_date} | {cafe_leads_count}건")

            self.db.log_system_event("Cafe Spy", f"🏁 Scan finished. Total leads: {total_leads_session}")
            self.process_and_save_leads(global_keywords, target_list)
        finally:
            self._cleanup_driver()

    def process_and_save_leads(self, target_keywords=None, target_list=None):
        """Processes collected leads (AI + DB) and appends to report."""
        import re  # Fix: Ensure re is available throughout function
        
        if not self.all_leads:
            print("\n💨 No raw leads to process.")
            return

        # [Phase 5.2] Report Filename Construction (Early for Dedup)
        cafe_suffix = ""
        if hasattr(self, 'active_targets') and self.active_targets and len(self.active_targets) == 1:
            cafe_name = self.active_targets[0]['name'].replace(' ', '').replace('(', '').replace(')', '')
            cafe_suffix = f"_{cafe_name}"
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r_dir = os.path.join(base_dir, 'reports_cafe')
        os.makedirs(r_dir, exist_ok=True)
        date_str = datetime.now().strftime('%Y%m%d')
        r_path = os.path.join(r_dir, f"cafe_report{cafe_suffix}_{date_str}.md")

        # [Phase 5.2] Load existing titles for deduplication
        existing_signatures = set()
        file_exists = os.path.exists(r_path)
        
        if file_exists:
            try:
                with open(r_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    titles = re.findall(r'^##\s+.\s+(.+)$', content, re.MULTILINE)
                    for t in titles:
                        existing_signatures.add(t.strip())
                print(f"📚 Loaded {len(existing_signatures)} existing items from report.")
            except Exception as e:
                print(f"⚠️ Failed to read existing report: {e}")

        # Filter new leads
        new_leads = []
        seen_links = set()
        
        for lead in self.all_leads:
            sig = lead['title'].strip()
            if sig in existing_signatures:
                continue
            if sig in seen_links:
                continue
            seen_links.add(sig)
            new_leads.append(lead)

        if not new_leads:
            print("💨 All leads already reported. Skipping.")
            return

        print(f"✨ Processing {len(new_leads)} NEW leads with AI...")
        
        if not target_keywords: target_keywords = ["(Recovered)"]
        if not target_list: target_list = [{"name": "(Recovered)"}]

        # Prepare new report lines
        self.report_lines = []
        if not file_exists:
            self.report_lines = [
                f"# ☕ 맘카페 잠입 리포트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
                f"**감시 키워드**: {', '.join(target_keywords)}",
                f"**탐색 대상**: {[c['name'] for c in target_list]}",
                "---"
            ]
        
        # ============================================
        # [BATCH PROCESSING] Analyze all leads at once
        # ============================================
        analyses = self._batch_analyze_leads(new_leads)
        
        for i, lead in enumerate(new_leads):
            # Get analysis from batch results
            analysis = analyses.get(i, {}) if analyses else {}
            
            ai_summary = analysis.get('summary', '요약 없음')
            score = analysis.get('score', 'Unknown')
            ai_reply = analysis.get('reply', '분석 실패')
            
            icon = "🔥" if "Hot" in score else "😐" if "Warm" in score else "❄️"
            print(f"      {icon} AI Strategy: {score} | {ai_summary[:30]}...")

            # [1단계] Hot Lead 즉시 알림
            if "Hot" in score:
                self._send_hot_lead_alert(lead, analysis)
            
            final_content = f"[{score}] {ai_summary}\n\n[Reply] {ai_reply}\n\n[Body]\n{lead.get('body','')}\n\nAuthor: {lead['author']} | Cafe: {lead['cafe']}"
            self.db.insert_mention({
                "target_name": "MomCafe",
                "keyword": "DeepScan",
                "source": "naver_cafe",
                "title": lead['title'],
                "content": final_content,
                "url": lead['link'],
                "date_posted": lead['date']
            })
            
            self.report_lines.append(f"## {icon} {lead['title']}")
            self.report_lines.append(f"**{lead['cafe']}** | {lead['date']} | {lead['author']}")
            self.report_lines.append(f"")
            self.report_lines.append(f"**📝 3초 요약**")
            self.report_lines.append(f"{ai_summary}")
            self.report_lines.append(f"")
            self.report_lines.append(f"**💬 AI 전략 댓글 (규림 홍보)**")
            self.report_lines.append(f"```text")
            self.report_lines.append(f"{ai_reply}")
            self.report_lines.append(f"```")
            self.report_lines.append(f"")
            self.report_lines.append(f"🔴 **[게시글 바로가기 (Click)]({lead['link']})**")
            self.report_lines.append("---")
            
        # Append to file
        if self.report_lines:
            try:
                with open(r_path, 'a', encoding='utf-8') as f:
                    if file_exists:
                        f.write("\n") # Spacing between sessions
                    f.write("\n".join(self.report_lines))
                print(f"\n📄 Report Updated: {r_path}")
            except Exception as e:
                print(f"⚠️ Report append failed: {e}")

        # [Phase 2 메모리 정리] 처리 완료 후 리드 리스트 정리
        self.all_leads.clear()

    def _cleanup_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"⚠️ Driver cleanup warning: {e}")
            self.driver = None

    def save_report(self):
        # Legacy stub
        pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cafe_name", type=str, help="Specific cafe to scan")
    parser.add_argument("--keyword", type=str, help="Override keyword")
    args = parser.parse_args()

    try:
        spy = CafeSpy()
        filter_cafes = [args.cafe_name] if args.cafe_name else None
        spy.run(cafe_filter=filter_cafes, keyword_override=args.keyword)
    except Exception as e:
        import traceback
        traceback.print_exc()
        if 'spy' in locals():
            try:
                spy.process_and_save_leads() 
                spy._cleanup_driver()
            except Exception:
                pass
        sys.exit(1)
