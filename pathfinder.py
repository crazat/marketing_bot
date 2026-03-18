
import random
import pandas as pd
import json
import os
from agent_crew import AgentCrew
from utils import logger, ConfigManager
import urllib3
import concurrent.futures
import threading
from scrapers.naver_autocomplete import NaverAutocompleteScraper

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Pathfinder:
    """
    Pathfinder V3: LEGION (Multi-Campaign Parallel Scanner)
    """
    def __init__(self):
        self.config = ConfigManager()
        # reusing crew's model for brainstorming
        self.crew = AgentCrew() 
        self.db_lock = threading.Lock() 

    def run_campaign(self):
        """
        Executes the 'Legion' Strategy:
        Iterates through all categories in `campaigns.json` and performs massive PARALLEL harvesting.
        """
        campaign_path = os.path.join(ConfigManager().root_dir, 'config', 'campaigns.json')
        if not os.path.exists(campaign_path):
            logger.error("Campaign config not found!")
            return
            
        with open(campaign_path, 'r', encoding='utf-8') as f:
            campaign = json.load(f)
            
        logger.info(f"⚔️ Starting Campaign: {campaign.get('campaign_name', 'Unnamed')} (Parallel Mode)")
        self._log_progress(f"⚔️ TOTAL WAR 개시! {len(campaign['targets'])}개 전선 동시 진격...")
        
        total_found = 0
        targets = campaign['targets']
        
        # [Parallel Execution] Max 3 Categories at once to respect API limits & DB
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_cat = {executor.submit(self._process_category_target, t): t['category'] for t in targets}
            
            for future in concurrent.futures.as_completed(future_to_cat):
                cat = future_to_cat[future]
                try:
                    count = future.result()
                    total_found += count
                    logger.info(f"✅ Category '{cat}' finished. Secured {count} insights.")
                    self._log_progress(f"✅ [{cat}] 점령 완료! +{count}개 키워드 확보 (누적: {total_found})")
                except Exception as exc:
                    logger.error(f"❌ Category '{cat}' generated an exception: {exc}")
            
        logger.info(f"🎉 Campaign Complete. Total Insights Secured: {total_found}")
        self._log_progress(f"🎉 작전 완료! 총 {total_found}개 키워드 확보")
        return total_found
    
    def _log_progress(self, message):
        """Write progress to system_logs for live dashboard updates"""
        try:
            import sqlite3
            with sqlite3.connect(ConfigManager().db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO system_logs (module, level, message)
                    VALUES (?, ?, ?)
                ''', ('Pathfinder', 'INFO', message))
                conn.commit()
        except Exception as e:
            logger.debug(f"Progress logging failed: {e}")

    def _process_category_target(self, target):
        """Worker function for a single campaign category (BATCH PROCESSING UPGRADE)"""
        category = target['category']
        if not category:
            logger.error("Skipping target with missing category")
            return 0
        
        seeds = target.get('seeds', target.get('seed_keywords', []))
        if not seeds:
            logger.error(f"❌ Category '{category}' has no seeds! Check campaigns.json.")
            return 0
        
        logger.info(f"🚩 Frontline: {category} (Seeds: {len(seeds)})")
        
        from scrapers.keyword_harvester import KeywordHarvester
        from scrapers.naver_ad_manager import NaverAdManager
        
        harvester = KeywordHarvester()
        ad_mgr = NaverAdManager()
        
        # [Strategy 2 & 3] Dynamic Intent & Negative Feedback
        intent_prompt = self._get_dynamic_intent()
        excludes = self._get_negative_keywords(limit=20)
        exclude_str = ", ".join(excludes) if excludes else "None"
        
        logger.info(f"   🧠 Intent: {intent_prompt[:30]}... | Excludes: {len(excludes)}")
        
        total_seeds_pool = []
        
        # [Strategy 1] Full Seed Coverage (Batch Processing)
        # Process seeds in chunks of 5
        chunk_size = 5
        for i in range(0, len(seeds), chunk_size):
            chunk = seeds[i:i + chunk_size]
            logger.info(f"   🧱 Processing Batch {i//chunk_size + 1}: {chunk}")
            
            # AI Expansion for this chunk
            expanded_batch = list(chunk)
            try:
                prompt = f"""당신은 네이버 검색 키워드 전문가입니다.
다음 키워드들의 변형, 유사어, 롱테일 버전을 최대한 많이 생성하세요.
원본 키워드: {', '.join(chunk)}

[탐색 의도/관점]: "{intent_prompt}"
[제외할 키워드 (이미 수집됨)]: {exclude_str}

규칙:
- 지역명 '청주'를 포함하세요
- 위 [탐색 의도]에 맞는 구체적인 상황을 상상하세요.
- [제외할 키워드]는 절대 포함하지 마세요.
- 최소 10개 이상 생성
- 한 줄에 하나씩, 키워드만 출력 (설명 없이)"""
                
                ai_response = self.crew.researcher.generate(prompt)
                if ai_response:
                    ai_keywords = [line.strip() for line in ai_response.split('\n') if line.strip() and len(line.strip()) > 3]
                    # Filter excludes again just in case
                    ai_keywords = [k for k in ai_keywords if k not in excludes]
                    expanded_batch.extend(ai_keywords[:30]) # Cap per batch
                    logger.info(f"      + AI harvested {len(ai_keywords)} keywords for this batch.")
            except Exception as e:
                logger.warning(f"AI expansion failed for batch {chunk}: {e}")
            
            total_seeds_pool.extend(expanded_batch)
            
        # Deduplicate total pool
        total_seeds_pool = list(set(total_seeds_pool))
        logger.info(f"   🔥 Total Expanded Seeds for {category}: {len(total_seeds_pool)}")
            
        try:
            # [OPTIMIZED] Depth 축소 (4 → 2): Longtail 과도 생성 방지
            # Depth 4는 6단어 이상의 비현실적 키워드 생성 (예: "복대동 허벅지 살빼기 부작용 한의원")
            # Depth 2는 3-4단어의 실제 검색되는 키워드 생성
            candidates = harvester.harvest(total_seeds_pool, depth=2, max_limit=5000) 
        except Exception as e:
            logger.error(f"Harvest failed for {category}: {e}")
            candidates = seeds
            
        logger.info(f"   -> Gathered {len(candidates)} candidates for {category}.")
        # [UNLEASHED] Fetch True Search Volume (Demand) + Bonus Keywords
        # API now returns ~100 related keywords for every batch.
        search_vol_map = ad_mgr.get_keyword_volumes(candidates)
        
        # Calculate Bonus yield
        total_kws_found = list(search_vol_map.keys())
        bonus_count = len(total_kws_found) - len(candidates)
        if bonus_count > 0:
            logger.info(f"   🎁 Bonus: Ad API revealed {bonus_count} additional related keywords!")
        
        insights = []
        
        # Assimilate ALL relevant keywords (Original + Bonus)
        for kw in total_kws_found:
            # [CRITICAL] 모든 키워드에 블랙리스트 적용 (candidates 여부 무관)

            # 경쟁사 및 비한의원 블랙리스트 (최우선 체크)
            competitor_blacklist = [
                # 다른 업종 의료기관
                "피부과", "성형외과", "정형외과", "산부인과", "이비인후과",
                "내과", "정신과", "정신건강의학과", "비뇨기과",
                # 경쟁사 병원/의원명
                "스노우", "미하이", "와인", "365MC", "더모", "리엔",
                "연세", "아름다운", "예쁜", "맑은", "밝은",
                # 의료 관련 아닌 업종
                "미용실", "헤어샵", "네일", "왁싱", "마사지", "스웨디시",
                "에스테틱", "스파", "필라테스", "요가", "PT", "헬스장"
            ]

            has_competitor = any(comp in kw for comp in competitor_blacklist)
            if has_competitor:
                logger.debug(f"⛔ Competitor keyword blocked: {kw}")
                continue

            # [IMPROVED FILTER] 보너스 키워드 추가 필터 (청주 중심)
            if kw not in candidates:
                # 청주 전용 지역명 (규림 제외 - 전국 지점 혼동 방지)
                cheongju_locations = [
                    "청주",
                    # 4개 구
                    "상당", "서원", "흥덕", "청원", "상당구", "서원구", "흥덕구", "청원구",
                    # 주요 동/읍 (흥덕구)
                    "복대동", "가경동", "분평동", "봉명동", "사창동", "강서동",
                    "송정동", "향정동", "신봉동", "신성동", "장성동",
                    # 서원구
                    "산남동", "수곡동", "모충동", "사직동", "남이면", "현도면",
                    # 상당구
                    "율량동", "용암동", "금천동", "성화동", "우암동", "탑동", "영동", "중앙동",
                    # 청원구
                    "내덕동", "오창", "오송", "오창읍", "오송읍", "북이면", "내수읍",
                    # 주요 시설/지역
                    "청주역", "터미널", "육거리", "중앙공원", "운천", "성안길"
                ]

                # 다른 지역명 블랙리스트 (규림 전국 지점 필터링)
                other_cities = [
                    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
                    "강남", "강서", "강북", "서초", "송파", "마포", "영등포", "용산",
                    "해운대", "수영", "동래", "연제"  # 부산 주요 구
                ]

                has_cheongju = any(loc in kw for loc in cheongju_locations)
                has_other_city = any(city in kw for city in other_cities)

                # 청주 관련 없거나, 다른 도시명 포함되면 제외
                if not has_cheongju or has_other_city:
                    logger.debug(f"Bonus keyword filtered out (not Cheongju exclusive): {kw}")
                    continue

                # [NEW] 옵션 B: 한의원 중심 필터 (보너스 키워드만)
                # 한의원 관련 키워드
                hanbang_terms = [
                    "한의원", "한방", "한약", "침", "뜸", "추나", "부항", "교정",
                    "공진단", "경옥고", "보약", "총명탕"
                ]

                # 한의원이 다루는 증상 키워드 (대폭 확장)
                hanbang_symptoms = [
                    # 비만/체중 관리
                    "다이어트", "비만", "살빼기", "체중감량", "복부비만", "식욕억제",

                    # 피부 질환
                    "여드름", "피부", "흉터", "아토피", "건선", "습진", "피부염",
                    "기미", "주근깨", "잡티", "모공", "여드름흉터",

                    # 탈모
                    "탈모", "원형탈모", "지루성두피", "두피", "탈모치료", "발모",

                    # 통증 관리
                    "통증", "디스크", "허리", "목", "무릎", "어깨", "팔", "손목",
                    "발목", "관절", "근육통", "신경통", "요통", "좌골신경통",
                    "오십견", "팔저림", "손목통증", "족저근막염", "관절염",

                    # 교통사고/외상
                    "교통사고", "후유증", "입원", "염좌", "타박상", "골절",

                    # 체형 교정
                    "안면비대칭", "체형교정", "골반교정", "턱관절", "측만증",
                    "거북목", "일자목", "휜다리", "골반불균형", "척추측만증",

                    # 여성 질환
                    "갱년기", "폐경", "생리통", "산후조리", "생리불순", "냉대하",
                    "자궁근종", "난임", "불임", "임신준비", "산후비만", "산후우울",
                    "여성질환", "방광염", "요실금",

                    # 남성 질환
                    "남성갱년기", "전립선", "발기부전", "조루", "성기능",

                    # 정신/신경
                    "불면증", "수면", "피로", "스트레스", "우울증", "불안증",
                    "공황장애", "화병", "신경쇠약", "만성피로",

                    # 소화기
                    "소화불량", "위염", "변비", "담적", "역류성식도염", "설사",
                    "과민성대장", "장염", "복통", "식욕부진", "구토",

                    # 호흡기
                    "비염", "알레르기", "축농증", "감기", "기침", "천식", "후비루",
                    "코막힘", "재채기", "비중격만곡", "알레르기비염", "만성비염",

                    # 두통/어지럼증
                    "두통", "편두통", "어지럼증", "현기증", "메니에르", "이명",
                    "난청", "귀울림",

                    # 순환/대사
                    "다한증", "냉증", "수족냉증", "손발저림", "부종", "하지정맥류",
                    "고혈압", "당뇨", "고지혈증", "지방간", "간질환", "신장",

                    # 안과 증상
                    "안구건조증", "눈피로", "시력", "눈떨림", "결막염",

                    # 성장/발달
                    "성장판", "키성장", "성조숙증", "저신장", "성장부진",

                    # 소아 질환
                    "소아", "아이", "야뇨증", "식욕부진", "아토피", "비염",
                    "감기", "잔병치레", "면역력", "키성장",

                    # 수험생/학습
                    "수험생", "집중력", "총명탕", "기억력", "학습능력", "시험",

                    # 중풍/뇌혈관
                    "중풍", "뇌졸중", "반신마비", "언어장애", "안면마비", "구안와사",

                    # 면역/만성질환
                    "면역력", "대상포진", "체질개선", "암", "항암", "면역",
                    "잔병치레", "만성질환",

                    # 수면
                    "코골이", "수면무호흡증", "수면장애",

                    # 기타
                    "체질", "건강검진", "예방", "관리", "치료", "개선"
                ]

                has_hanbang = any(term in kw for term in hanbang_terms)
                has_symptom = any(term in kw for term in hanbang_symptoms)

                # 한의원 관련 또는 한의원 증상이 있어야 함
                if not (has_hanbang or has_symptom):
                    logger.debug(f"Bonus keyword filtered out (not hanbang-related): {kw}")
                    continue
            
            # 1. Supply (Blog Count)
            # Note: For massive lists, this linear scan might be slow.
            # Future optimization: Async FastScanner
            doc_count = harvester.get_naver_blog_count(kw)

            # [NEW] 공급 필터 - 가짜 Golden 및 Red Ocean 제거
            MIN_SUPPLY = 10       # 블로그 10개 미만 = 수요 없음 (가짜 Golden)
            MAX_SUPPLY = 30000    # 블로그 3만개 초과 = Red Ocean (경쟁 불가)

            if doc_count < MIN_SUPPLY:
                logger.debug(f"⚠️ Fake golden (no demand): {kw} (Supply: {doc_count})")
                continue

            if doc_count > MAX_SUPPLY:
                logger.debug(f"🔴 Red ocean (too competitive): {kw} (Supply: {doc_count:,})")
                continue

            vol = search_vol_map.get(kw, 0)

            # [OPTIMIZED] 최소 검색량 10
            # 검색량 10-20 구간에 좋은 longtail Golden Keywords가 많음
            # 너무 높이면 일반적이고 경쟁 심한 키워드만 남음
            MIN_MONTHLY_SEARCHES = 10
            if vol < MIN_MONTHLY_SEARCHES:
                logger.debug(f"Skipping low-volume keyword: {kw} (Vol: {vol})")
                continue  # 검색량 10 미만 키워드는 무의미하므로 제외

            # 2. Opportunity Score (KEI)
            opp_score, tag = self._analyze_opportunity(vol, doc_count)
            
            # 3. Detect Region (Fix for :region parameter binding error)
            regions = ["청주", "세종", "진천", "증평", "괴산", "보은"]
            detected_region = next((r for r in regions if r in kw), "기타")
            
            insights.append({
                "keyword": kw,
                "volume": doc_count,
                "competition": "Low" if doc_count < 500 else "High",
                "opp_score": opp_score,
                "tag": tag,
                "search_volume": vol,
                "region": detected_region,
                "category": category  # ✅ 카테고리 필드 추가
            })
            
        # Bulk Save
        self._batch_save_to_db(insights)
        
        return len(insights)

    def _get_dynamic_intent(self):
        """Randomly selects a search persona/intent."""
        intents = [
            "환자들이 걱정하는 부작용, 통증, 회복기간 위주의 검색어",
            "비용, 가격, 싼곳, 저렴한곳, 실비보험 적용 여부 위주의 가성비 검색어",
            "찐후기, 내돈내산, 솔직후기, 비추 후기 등 평판 위주의 검색어",
            "야간진료, 주말진료, 일요일 문여는곳, 입원가능한곳 등 편의성 위주",
            "잘하는곳, 유명한곳, 명의, 추천 등 신뢰도/명성 위주",
            "맘카페나 커뮤니티에서 엄마들이 물어볼법한 구어체 질문형 키워드"
        ]
        return random.choice(intents)

    def _get_negative_keywords(self, limit=20):
        """Fetches frequently collected keywords from DB to exclude."""
        try:
            import sqlite3
            with sqlite3.connect(self.config.db_path) as conn:
                cursor = conn.cursor()
                # Get high volume keywords or just random heavy ones
                cursor.execute("SELECT keyword FROM keyword_insights ORDER BY search_volume DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _is_medically_relevant(self, keyword):
        """
        [Advanced Filter V2]
        Determines if a keyword is relevant to the clinic's business.
        Rule: (Has Region AND Has Medical Term) AND (No Blacklist Terms)
        """
        kw = keyword.replace(" ", "")
        
        # 0. Always Allow Brand
        if "규림" in kw:
            return True

        # 1. Region Check
        regions = ["청주", "세종", "진천", "증평", "괴산", "보은", "오창", "오송", "가경", "복대", "율량", "산남", "용암", "금천", "분평", "사창", "봉명", "비하", "강서", "송절"]
        has_region = any(r in kw for r in regions)
        if not has_region:
            return False

        # 2. Blacklist Check (Strict Sectors)
        blacklist = [
            "항공권", "여행", "날씨", "버스", "터미널", "맛집", "카페", "가볼만한곳", "데이트", 
            "영화", "숙소", "호텔", "펜션", "캠핑", "주차", "세차", "중고차", "부동산", "아파트", 
            "분양", "지도", "시청", "구청", "법원", "세무서", "휴게소", "배달", "퀵", 
            "용달", "이사", "청소", "알바", "일자리", "벼룩시장", "당근", "중고", "노래방",
            "스키", "썰매", "물놀이", "수영장", "계곡", "아이폰", "수리", "유기견", "보호소",
            "애견", "강아지", "고양이", "동물", "공무원", "학원", "독서실", "스터디", "스포츠"
        ]
        if any(b in kw for b in blacklist):
            return False

        # 3. Medical/Intent Domain Check (Specific)
        medical_terms = [
            # Medical Institutions
            "한의원", "병원", "피부과", "정형외과", "내과", "이비인후과", "치과", "안과", "비뇨기과", "산부인과", "의원", "클리닉",
            # Diet & Obesity
            "다이어트", "감량", "살빼", "비만", "체중", "피티", "PT", "운동", "요가", "필라테스", 
            # Skin & Beauty
            "여드름", "피부", "흉터", "모공", "잡티", "기미", "점빼", "리프팅", "보톡스", "필러", "슈링크", "인모드", "울쎄라", "안면", "비대칭", "윤곽", "주름", "매선",
            # Pain & Rehab
            "교통사고", "입원", "물리치료", "도수치료", "추나", "침잘", "통증", "디스크", "관절", "허리", "어깨", "목", "무릎", "손목", "엘보",
            # Woman & Postpartum
            "갱년기", "폐경", "생리", "산후", "조리", "유산", "임신", "난임", "여성", "질환", "방광염", "질염",
            # Internal & Stress
            "소화", "위장", "담적", "역류성", "과민성", "변비", "설사", "두통", "어지럼", "이석증", "불면", "수면", "공황", "우울", "불안", "스트레스", "자율신경",
            # Immunue & Features
            "비염", "축농증", "감기", "보약", "공진단", "경옥고", "면역", "피로", "대상포진",
            # Growth & Study
            "성장", "키", "수능한약", "총명탕"
        ]
        
        # [Refinement] "센터" is too broad, only allow if preceded by a medical term
        if "센터" in kw:
            allowed_centers = ["다이어트센터", "교정센터", "비만센터", "통증센터", "성장센터", "산후조리센터"]
            if not any(ac in kw for ac in allowed_centers):
                return False

        has_medical = any(m in kw for m in medical_terms)
        return has_medical

    def _revalidate_category(self, keyword, current_category):
        """
        [Category Shield]
        Ensures a keyword harvested under a parent category actually belongs there.
        """
        kw = keyword.replace(" ", "")
        
        # Category signature terms
        category_vitals = {
            "다이어트": ["다이어트", "비만", "살", "체중", "감량", "식욕", "한약"],
            "여드름_피부": ["여드름", "피부", "흉터", "모공", "기미", "잡티"],
            "교통사고_입원": ["교통사고", "입원", "자동차", "후유증"],
            "통증_디스크": ["통증", "디스크", "허리", "목", "어깨", "추나", "도수"],
            "안면비대칭_교정": ["안면비대칭", "교정", "턱", "비대칭", "얼굴"]
        }
        
        if current_category in category_vitals:
            vitals = category_vitals[current_category]
            if not any(v in kw for v in vitals):
                # Check if it fits another specific category
                for alt_cat, alt_vitals in category_vitals.items():
                    if any(av in kw for av in alt_vitals):
                        return alt_cat
                return "기타"
        
        return current_category

    # ============================================================
    # PATHFINDER V3: Naver 자동완성 기반 실제 검색 키워드 수집
    # ============================================================

    def run_campaign_v3(self, max_keywords: int = 500):
        """
        Pathfinder V3: Naver 자동완성 + Ad API 보너스 기반 실제 검색 키워드 수집

        기존 방식의 문제점:
        - AI가 생성한 비현실적 키워드 (검색량 0)
        - 너무 구체적인 longtail (6단어 이상)

        V3의 해결책:
        - Naver 자동완성 API에서 실제 검색되는 키워드만 수집
        - Naver Ad API가 반환하는 보너스 관련 키워드 활용
        - 한의원 관련성 필터로 고품질 키워드만 저장

        Args:
            max_keywords: 최대 수집 키워드 수 (기본 500)
        """
        logger.info(f"🚀 Pathfinder V3 시작! 목표: {max_keywords}개 실제 검색 키워드")
        self._log_progress(f"🚀 Pathfinder V3 발동! Naver 자동완성 + Ad API 보너스 수집")

        # 1. 초기 시드 생성 (간결한 2-3단어)
        seeds = self._generate_simple_seeds_v3()
        logger.info(f"📦 초기 시드: {len(seeds)}개")

        # 2. Naver 자동완성으로 확장
        autocomplete_scraper = NaverAutocompleteScraper(delay=0.3)

        cheongju_regions = [
            "청주", "상당", "서원", "흥덕", "청원",
            "복대", "가경", "율량", "오창", "오송",
            "분평", "봉명", "산남", "용암", "금천"
        ]

        # BFS 확장 (depth=2로 적절한 longtail까지)
        expanded_keywords = autocomplete_scraper.expand_keywords_bfs(
            seed_keywords=seeds,
            max_depth=2,
            max_total=max_keywords,
            region_filter=cheongju_regions
        )

        logger.info(f"🔍 자동완성 확장 완료: {len(expanded_keywords)}개")
        self._log_progress(f"🔍 자동완성 확장: {len(expanded_keywords)}개 실제 검색어 수집")

        # 3. 검색량 조회 (Naver Ad API - 보너스 키워드 포함)
        from scrapers.naver_ad_manager import NaverAdManager
        ad_mgr = NaverAdManager()

        search_vol_map = ad_mgr.get_keyword_volumes(expanded_keywords)

        # Ad API가 반환한 모든 키워드 활용 (보너스 포함)
        all_keywords = list(search_vol_map.keys())
        bonus_count = len(all_keywords) - len(expanded_keywords)
        logger.info(f"📊 검색량 조회 완료: {len(all_keywords)}개 (보너스: {bonus_count}개)")

        # 4. 청주 지역 필터
        cheongju_keywords = []
        for kw in all_keywords:
            if any(loc in kw for loc in cheongju_regions):
                cheongju_keywords.append(kw)

        logger.info(f"📍 청주 관련 키워드: {len(cheongju_keywords)}개")

        # 5. 필터링 및 KEI 계산
        from scrapers.keyword_harvester import KeywordHarvester
        harvester = KeywordHarvester()

        insights = []
        filtered_count = {"competitor": 0, "not_hanbang": 0, "supply_low": 0, "supply_high": 0, "volume_low": 0}

        # 경쟁사/비한의원 블랙리스트 (강화)
        competitor_blacklist = [
            # 다른 의료 업종
            "피부과", "성형외과", "정형외과", "산부인과", "이비인후과",
            "내과", "정신과", "비뇨기과", "치과", "안과", "신경외과",
            # 미용/뷰티 (비한의원)
            "미용실", "헤어샵", "네일", "왁싱", "마사지", "에스테틱",
            "필라테스", "요가", "헬스장", "크로스핏", "복싱", "PT",
            # 피부과 시술
            "보톡스", "필러", "레이저제모", "울쎄라", "써마지", "인모드",
            # 비의료 서비스
            "세차", "배터리", "공방", "가구", "블랙박스", "폐기물", "이사",
            "네일", "속눈썹", "반영구", "문신", "타투",
            # 경쟁사 이름
            "스노우", "미하이", "365", "비타", "포에버", "동안나라",
        ]

        # 한의원 관련 용어 (필수 포함)
        hanbang_terms = [
            "한의원", "한방", "한약", "침", "뜸", "추나", "부항", "교정",
            "공진단", "경옥고", "보약", "총명탕", "한방병원"
        ]

        # 한의원 치료 질환
        hanbang_symptoms = [
            "다이어트", "비만", "살빼", "체중", "감량",
            "여드름", "피부", "모공", "흉터", "아토피",
            "탈모", "두피",
            "통증", "디스크", "허리", "목", "어깨", "무릎", "관절",
            "교통사고", "후유증", "입원",
            "안면비대칭", "체형교정", "턱관절",
            "갱년기", "폐경", "생리", "산후",
            "불면증", "수면",
            "비염", "축농증", "알레르기",
            "두통", "어지럼", "이명",
            "소화", "위장", "역류",
        ]

        for kw in cheongju_keywords:
            # 5-1. 경쟁사/비한의원 필터
            if any(comp in kw for comp in competitor_blacklist):
                filtered_count["competitor"] += 1
                continue

            # 5-2. 한의원 관련성 체크
            has_hanbang = any(term in kw for term in hanbang_terms)
            has_symptom = any(term in kw for term in hanbang_symptoms)

            if not (has_hanbang or has_symptom):
                filtered_count["not_hanbang"] += 1
                continue

            # 5-3. 검색량 필터 (완화: 5 이상)
            vol = search_vol_map.get(kw, 0)
            if vol < 5:
                filtered_count["volume_low"] += 1
                continue

            # 5-4. 공급(블로그 수) 조회 및 필터
            doc_count = harvester.get_naver_blog_count(kw)

            if doc_count < 10:
                filtered_count["supply_low"] += 1
                continue

            if doc_count > 30000:
                filtered_count["supply_high"] += 1
                continue

            # 5-5. KEI 계산
            opp_score, tag = self._analyze_opportunity(vol, doc_count)

            # 5-6. 카테고리 추정
            category = self._detect_category_v3(kw)

            # 5-7. 지역 감지
            regions = ["청주", "오창", "오송", "복대", "가경", "율량", "산남"]
            detected_region = next((r for r in regions if r in kw), "청주")

            insights.append({
                "keyword": kw,
                "volume": doc_count,
                "competition": "Low" if doc_count < 500 else "Medium" if doc_count < 5000 else "High",
                "opp_score": opp_score,
                "tag": tag,
                "search_volume": vol,
                "region": detected_region,
                "category": category
            })

            # 목표 달성 시 조기 종료
            if len(insights) >= max_keywords:
                break

        # 필터링 통계 로깅
        logger.info(f"📋 필터링 결과:")
        logger.info(f"   - 경쟁사/비한의원 업종: {filtered_count['competitor']}개")
        logger.info(f"   - 한의원 비관련: {filtered_count['not_hanbang']}개")
        logger.info(f"   - 검색량 부족: {filtered_count['volume_low']}개")
        logger.info(f"   - 공급 부족 (가짜 Golden): {filtered_count['supply_low']}개")
        logger.info(f"   - 공급 과다 (Red Ocean): {filtered_count['supply_high']}개")
        logger.info(f"   → 최종 저장: {len(insights)}개")

        # 6. DB 저장
        self._batch_save_to_db(insights)

        # 7. 통계 출력
        golden_count = sum(1 for i in insights if i['opp_score'] >= 500)
        gold_count = sum(1 for i in insights if 300 <= i['opp_score'] < 500)
        silver_count = sum(1 for i in insights if 100 <= i['opp_score'] < 300)

        logger.info(f"🎉 V3 완료! 총 {len(insights)}개 키워드 저장")
        logger.info(f"   - KEI 500+ (Golden): {golden_count}개")
        logger.info(f"   - KEI 300-499 (Gold): {gold_count}개")
        logger.info(f"   - KEI 100-299 (Silver): {silver_count}개")

        self._log_progress(f"🎉 V3 완료! {len(insights)}개 저장 (Golden: {golden_count}, Gold: {gold_count})")

        return len(insights)

    def _generate_simple_seeds_v3(self) -> list:
        """
        V3용 간결한 시드 생성 (2-3단어)

        기존 AI 시드의 문제:
        - 47개 지역 × 10개 용어 × 9개 의도 × 5개 시설 = 21,150개 조합
        - "복대동 허벅지 살빼기 부작용 한의원" (6단어) → 검색량 0

        V3 시드:
        - 청주 + 핵심 용어 (2단어)
        - 청주 + 핵심 용어 + 의도 (3단어)
        - 총 ~100개 간결한 시드
        """
        seeds = []

        base_region = "청주"

        # 카테고리별 핵심 용어 (각 3-5개로 제한)
        category_terms = {
            "다이어트": ["다이어트", "다이어트한약", "비만", "살빼기"],
            "여드름_피부": ["여드름", "피부", "피부관리", "모공"],
            "교통사고_입원": ["교통사고", "교통사고한의원", "자동차사고"],
            "통증_디스크": ["허리통증", "목디스크", "어깨통증", "무릎통증"],
            "안면비대칭_교정": ["안면비대칭", "얼굴비대칭", "턱관절", "체형교정"],
            "리프팅_탄력": ["리프팅", "매선", "피부탄력", "주름"],
            "갱년기_호르몬": ["갱년기", "폐경", "여성호르몬"],
            "불면증_수면": ["불면증", "수면", "수면장애"],
            "소화불량_위장": ["소화불량", "위장", "담적병", "역류성식도염"],
            "두통_어지럼증": ["두통", "어지럼증", "편두통", "이명"],
            "알레르기_아토피": ["비염", "아토피", "알레르기", "축농증"],
            "산후조리_여성": ["산후조리", "산후비만", "여성질환"],
            "탈모": ["탈모", "탈모치료", "원형탈모"],
            "면역_보약": ["보약", "면역력", "공진단", "경옥고"],
        }

        # 구매 의도 수식어
        intent_modifiers = ["가격", "후기", "추천", "잘하는곳", "효과"]

        for category, terms in category_terms.items():
            for term in terms:
                # 기본 시드: "청주 다이어트"
                seeds.append(f"{base_region} {term}")

                # 의도 추가 시드 (첫 2개 의도만): "청주 다이어트 가격"
                for intent in intent_modifiers[:2]:
                    seeds.append(f"{base_region} {term} {intent}")

        # 주요 동네별 시드 (상위 5개 동네만)
        major_dongs = ["오창", "가경동", "복대동", "율량동", "분평동"]
        core_terms = ["한의원", "다이어트", "교통사고"]

        for dong in major_dongs:
            for term in core_terms:
                seeds.append(f"{dong} {term}")

        # 중복 제거
        seeds = list(set(seeds))
        logger.info(f"V3 시드 생성 완료: {len(seeds)}개 (간결한 2-3단어)")

        return seeds

    def _detect_category_v3(self, keyword: str) -> str:
        """
        키워드에서 카테고리 자동 감지

        Args:
            keyword: 분석할 키워드

        Returns:
            감지된 카테고리명
        """
        kw = keyword.replace(" ", "").lower()

        category_patterns = {
            "다이어트": ["다이어트", "비만", "살빼", "체중", "감량"],
            "여드름_피부": ["여드름", "피부", "모공", "흉터", "기미"],
            "교통사고_입원": ["교통사고", "자동차사고", "후유증"],
            "통증_디스크": ["통증", "디스크", "허리", "목", "어깨", "무릎", "관절"],
            "안면비대칭_교정": ["안면비대칭", "비대칭", "턱관절", "교정", "체형"],
            "리프팅_탄력": ["리프팅", "매선", "탄력", "주름"],
            "갱년기_호르몬": ["갱년기", "폐경", "호르몬", "여성"],
            "불면증_수면": ["불면증", "수면", "잠"],
            "소화불량_위장": ["소화", "위장", "담적", "역류", "변비"],
            "두통_어지럼증": ["두통", "어지럼", "편두통", "이명"],
            "알레르기_아토피": ["비염", "아토피", "알레르기", "축농증"],
            "산후조리_여성": ["산후", "여성", "생리"],
            "탈모": ["탈모", "두피"],
            "면역_보약": ["보약", "면역", "공진단", "경옥고", "보양"],
        }

        for category, patterns in category_patterns.items():
            if any(pat in kw for pat in patterns):
                return category

        return "기타"

    # ============================================================
    # LEGION MODE: 10만 키워드 단일 실행
    # ============================================================
    
    def run_campaign_legion(self, target_count=100000):
        """
        LEGION MODE: 목표 키워드 수에 도달할 때까지 무한 확장 (Category Tracking 적용)
        """
        if target_count <= 10000:
            mode_name = "TOTAL WAR (전면전)"
            mode_emoji = "⚔️"
        else:
            mode_name = "LEGION MODE"
            mode_emoji = "🦁"
            
        logger.info(f"{mode_emoji} {mode_name} ACTIVATED! Target: {target_count:,} keywords")
        self._log_progress(f"{mode_emoji} {mode_name} 발동! 목표: {target_count:,}개")
        
        # [Category Tracking System]
        # Map: Keyword -> Category
        self.keyword_category_map = {} 
        
        # 전체 수집된 키워드: {keyword: search_volume}
        collected_keywords = {}
        
        # Queue per Category: {category: [list of seeds]}
        category_queues = {}
        
        # [FIX 1] Track seeds already used to prevent duplicate expansion
        used_as_seed = set()
        
        # 1. [AI-POWERED] 대량 시드 자동 생성 (campaigns.json 대신 AI 조합)
        initial_seeds = self._generate_ai_seeds()
        
        # Merge with manual seeds from campaigns.json (for any custom additions)
        manual_seeds = self._load_all_seeds()
        for ms in manual_seeds:
            if ms not in initial_seeds:
                initial_seeds.append(ms)
        
        logger.info(f"📦 AI Generated + Manual Seeds: {len(initial_seeds):,} total seeds!")
        
        # 2. 초기화
        for kw, cat in initial_seeds:
            if cat not in category_queues:
                category_queues[cat] = []
            category_queues[cat].append(kw)
            self.keyword_category_map[kw] = cat
            used_as_seed.add(kw)  # Mark initial seeds as used
            
            # [FIX 2] Add initial seeds to collected_keywords so they appear in final results
            if self._is_medically_relevant(kw):
                collected_keywords[kw] = 0  # Volume will be updated by Ad API
        
        round_num = 0
        
        while len(collected_keywords) < target_count:
            # Check if we have any pending seeds
            total_pending = sum(len(q) for q in category_queues.values())
            if total_pending == 0:
                logger.info(f"🛑 No more seeds to process. Stopping.")
                break
                
            round_num += 1
            logger.info(f"🔄 Round {round_num}: Pending Seeds {total_pending:,} across {len(category_queues)} categories...")
            
            # Round Robin Processing per Category
            round_new_keywords = {} # just for metrics
            
            for cat, queue in list(category_queues.items()): # Loop snapshot
                if not queue: continue
                if len(collected_keywords) >= target_count: break
                
                # Pop batch (Max 10 per category per round to keep diversity)
                batch_size = min(len(queue), 10)
                current_batch = queue[:batch_size]
                category_queues[cat] = queue[batch_size:] # Remove processed
                
                # Expand specific batch
                # logger.info(f"   🧱 [{cat}] Expanding {len(current_batch)} seeds...")
                
                try:
                    # API returns {kw: volume}
                    expanded_results = self._expand_via_ad_api(current_batch)
                    
                    for kw, vol in expanded_results.items():
                        # [REVALIDATION] Fix Category Drift
                        valid_cat = self._revalidate_category(kw, cat)
                        
                        # Track Category
                        if kw not in self.keyword_category_map:
                            self.keyword_category_map[kw] = valid_cat
                            
                        # Add to collected if relevant (Local + Domain Relevant)
                        if kw not in collected_keywords:
                            if self._is_medically_relevant(kw):
                                collected_keywords[kw] = vol
                                round_new_keywords[kw] = vol
                                
                                # Add to queue for next depth
                                # [Strategic Expansion] High Buying Intent signals -> Dig deeper immediately
                                intent_signals = ["가격", "비용", "후기", "추천", "잘하는곳", "진료", "효과", "부작용", "통증", "실비", "보험"]
                                is_golden_seed = any(sig in kw for sig in intent_signals)
                                
                                # Only add to queue if not already used as seed
                                if vol > 10 and kw not in used_as_seed:
                                    used_as_seed.add(kw)
                                    if is_golden_seed:
                                        # 🚀 VIP Pass: Front of the line (DFS style)
                                        category_queues[valid_cat].insert(0, kw)
                                    else:
                                        # Regular Pass: Back of the line
                                        category_queues[valid_cat].append(kw)
                                    
                except Exception as e:
                    logger.warning(f"Error expanding category {cat}: {e}")

            # Progress Logic
            fresh_count = len(round_new_keywords)
            logger.info(f"   ✅ Round {round_num} Complete: +{fresh_count} new keywords. Total: {len(collected_keywords):,}")
            self._log_progress(f"   ✅ Round {round_num}: +{fresh_count}개 발견 (누적: {len(collected_keywords):,})")
            
            if fresh_count == 0 and total_pending == 0:
                break
        
        # 4. 병렬 Supply 스캔
        logger.info(f"📊 Scanning supply for {len(collected_keywords):,} keywords (Parallel Mode)...")
        results = self._parallel_supply_scan(collected_keywords)
        
        # [CRITICAL FIX] Enforce Revalidated Category & Search Volume Lineage
        for res in results:
            kw = res['keyword']
            cat = self.keyword_category_map.get(kw, "기타")
            sv = collected_keywords.get(kw, 0)
            
            res['category'] = cat
            res['search_volume'] = sv
            # Update Tag to include Category (e.g., "[Diet] Blue Ocean")
            res['tag'] = f"[{cat}] {res['tag']}"
        
        # 5. [New] Trend Velocity Analysis (Smart Sampling)
        results = self._enrich_with_trends(results)
        
        # 6. DB 저장
        logger.info(f"💾 Saving {len(results):,} insights into {len(category_queues)} categories...")
        self._batch_save_to_db(results)
        
        return len(results)
    
    def _load_all_seeds(self):
        """Load all seeds from campaigns.json as (keyword, category) tuples"""
        campaign_path = os.path.join(self.config.root_dir, 'config', 'campaigns.json')
        seeds = [] # List of (kw, cat)
        try:
            with open(campaign_path, 'r', encoding='utf-8') as f:
                campaign = json.load(f)
                for target in campaign.get('targets', []):
                    cat = target.get('category', '기타')
                    target_seeds = target.get('seeds', target.get('seed_keywords', []))
                    for s in target_seeds:
                        seeds.append((s, cat))
        except Exception as e:
            logger.error(f"Failed to load campaigns.json: {e}")
        # Dedupe while preserving order
        seen = set()
        ordered_seeds = []
        for s in seeds:
            if s not in seen:
                seen.add(s)
                ordered_seeds.append(s)
        return ordered_seeds
    
    def _generate_ai_seeds(self):
        """
        [IMPROVED] 청주 중심 2-3단어 간결한 시드 생성
        기존 문제: 47개 지역 × 10개 용어 × 9개 의도 × 5개 시설 = 21,150개/카테고리 (비현실적)
        개선: 청주 중심으로 간결하게 992개 시드 생성 (99.7% 감소)
        """
        logger.info("🤖 청주 중심 Smart Seed 생성 중...")

        # === 청주 중심 지역 설정 ===
        base_region = "청주"

        # 청주 4개 구
        cheongju_districts = ["상당", "서원", "흥덕", "청원"]

        # 주요 동네 (인구 많은 15개)
        major_dongs = [
            "복대동", "가경동", "분평동", "봉명동", "사창동",  # 흥덕구/서원구
            "산남동", "수곡동", "모충동", "강서동", "내덕동",  # 서원구
            "율량동", "성화동", "용암동", "금천동", "우암동"   # 청원구/상당구
        ]

        # 카테고리별 핵심 용어 (각 5개 이하로 간소화)
        category_terms = {
            "다이어트": ["다이어트", "비만", "살빼기", "체중감량", "한약다이어트"],
            "안면비대칭_교정": ["안면비대칭", "체형교정", "골반교정", "거북목", "턱관절"],
            "여드름_피부": ["여드름", "피부", "흉터", "모공", "기미"],
            "리프팅_탄력": ["리프팅", "주름", "탄력", "동안침", "매선"],
            "교통사고_입원": ["교통사고", "입원", "후유증", "보험", "야간진료"],
            "통증_디스크": ["허리디스크", "목디스크", "허리통증", "추나", "도수치료"],
            "갱년기_호르몬": ["갱년기", "폐경", "여성호르몬", "안면홍조", "불면"],
            "불면증_수면": ["불면증", "수면장애", "피로", "만성피로", "수면"],
            "소화불량_위장": ["소화불량", "위염", "역류성식도염", "담적", "변비"],
            "두통_어지럼증": ["두통", "편두통", "어지럼증", "이석증", "현기증"],
            "알레르기_아토피": ["아토피", "비염", "알레르기", "축농증", "두드러기"],
            "자율신경_스트레스": ["공황장애", "우울증", "불안장애", "스트레스", "화병"],
            "산후조리_여성": ["산후조리", "산후보약", "생리통", "난임", "임신준비"],
            "다한증_냉증": ["다한증", "손땀", "냉증", "수족냉증", "발냉증"],
            "수험생_집중력": ["수험생", "총명탕", "집중력", "기억력", "수능한약"],
            "면역_보약": ["공진단", "경옥고", "보약", "면역력", "대상포진"]
        }

        # 구매 의도 시그널 (3개만)
        high_intent_signals = ["가격", "후기", "추천"]

        generated_seeds = []

        # === 간결한 시드 생성 로직 ===
        for category, terms in category_terms.items():
            # [레벨 1] 청주 + 핵심 용어 (5개)
            for term in terms:
                generated_seeds.append((f"{base_region} {term}", category))

            # [레벨 2] 청주 + 4개 구 + 핵심 3개 (12개)
            for district in cheongju_districts:
                for term in terms[:3]:  # 핵심 3개만
                    generated_seeds.append((f"{base_region} {district} {term}", category))

            # [레벨 3] 주요 동네 + 핵심 2개 (30개)
            for dong in major_dongs:
                for term in terms[:2]:  # 핵심 2개만
                    generated_seeds.append((f"{dong} {term}", category))

            # [레벨 4] 청주 + 용어 + 의도 (15개)
            for term in terms:
                for intent in high_intent_signals:
                    generated_seeds.append((f"{base_region} {term} {intent}", category))

        # 중복 제거
        seen = set()
        unique_seeds = []
        for seed in generated_seeds:
            if seed[0] not in seen:
                seen.add(seed[0])
                unique_seeds.append(seed)

        logger.info(f"🎯 청주 중심 Smart Seed {len(unique_seeds):,}개 생성 완료!")
        logger.info(f"   ✅ 기존 대비 99%+ 감소, 실제 검색되는 키워드 중심")
        return unique_seeds
    
    def _expand_via_ad_api(self, seeds):
        """
        시드 키워드들을 Ad API에 던져서 연관 키워드 대량 수집
        반환: {keyword: search_volume} 딕셔너리
        """
        from scrapers.naver_ad_manager import NaverAdManager
        ad_mgr = NaverAdManager()
        
        all_results = {}
        # Ad API는 5개씩 처리
        for i in range(0, len(seeds), 5):
            chunk = seeds[i:i+5]
            try:
                chunk_results = ad_mgr.get_keyword_volumes(chunk)
                all_results.update(chunk_results)
            except Exception as e:
                logger.warning(f"Ad API chunk failed: {e}")
                
        return all_results
    
    def _select_next_seeds(self, new_keywords, already_collected, limit=500):
        """
        다음 라운드에 사용할 시드 선정 (기존 방식 - 호환성 유지)
        """
        candidates = [(kw, vol) for kw, vol in new_keywords.items() 
                     if kw not in already_collected and vol > 10]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [kw for kw, vol in candidates[:limit]]
    
    def _select_next_seeds_diverse(self, new_keywords, already_used, limit=500):
        """
        다양성 확보를 위한 계층화된 시드 선정
        - 고볼륨 40% + 중볼륨 40% + 랜덤 20%
        """
        # 이미 시드로 사용되지 않은 키워드만
        candidates = [(kw, vol) for kw, vol in new_keywords.items() 
                     if kw not in already_used and vol > 0]
        
        if not candidates:
            return []
        
        # 볼륨 기준 정렬
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        total = len(candidates)
        
        # 계층 분할
        high_vol = candidates[:total // 3]  # 상위 1/3
        mid_vol = candidates[total // 3: 2 * total // 3]  # 중간 1/3
        low_vol = candidates[2 * total // 3:]  # 하위 1/3
        
        result = []
        
        # 고볼륨에서 40%
        high_count = min(len(high_vol), int(limit * 0.4))
        result.extend([kw for kw, vol in high_vol[:high_count]])
        
        # 중볼륨에서 40%
        mid_count = min(len(mid_vol), int(limit * 0.4))
        result.extend([kw for kw, vol in mid_vol[:mid_count]])
        
        # 랜덤에서 20% (전체에서 무작위 선택)
        remaining = limit - len(result)
        if remaining > 0 and low_vol:
            random_sample = random.sample(low_vol, min(len(low_vol), remaining))
            result.extend([kw for kw, vol in random_sample])
        
        return result[:limit]
    
    def _parallel_supply_scan(self, keywords_with_vol, max_workers=4):
        """
        ThreadPoolExecutor로 Supply(블로그 수) 병렬 조회
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from scrapers.keyword_harvester import KeywordHarvester
        import time
        
        harvester = KeywordHarvester()
        results = []
        total = len(keywords_with_vol)
        
        def scan_one(kw, vol):
            try:
                doc_count = harvester.get_naver_blog_count(kw)
                # opp_score, tag = self._analyze_opportunity(vol, doc_count)
                
                # Manual Score Calculation to avoid dependency issue
                if doc_count == 0: doc_count = 1 # Prevent zero division
                opp_score = round((vol / doc_count) * 10, 2)
                
                tag = "Golden Key 👑" if opp_score >= 1000 and doc_count < 1000 else "쏘쏘😐"
                if opp_score < 100: tag = "Red Ocean 🔴"
                
                # Region detection
                regions = ["청주", "세종", "진천", "증평", "괴산", "보은"]
                detected_region = next((r for r in regions if r in kw), "기타")
                
                # Retrieve Category from Map
                category = self.keyword_category_map.get(kw, '기타')
                
                return {
                    "keyword": kw,
                    "volume": doc_count,
                    "competition": "Low" if doc_count < 5000 else "High", # Adjusted threshold
                    "opp_score": opp_score,
                    "tag": tag,
                    "search_volume": vol,
                    "region": detected_region,
                    "category": category
                }
            except Exception as e:
                # logger.warning(f"Scan failed for {kw}: {e}")
                return None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(scan_one, kw, vol): kw 
                      for kw, vol in keywords_with_vol.items()}
            
            completed = 0
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception:
                    pass
                    
                completed += 1
                if completed % 1000 == 0:
                    logger.info(f"   📊 Supply scan progress: {completed:,}/{total:,}")
                    self._log_progress(f"   📊 스캔 진행: {completed:,}/{total:,}")
        
        return results
        

    def _enrich_with_trends(self, insights):
        """
        [Emerging Stars Optimization]
        Smart Sampling: Prioritize keywords with High KEI or Buying Intent markers.
        """
        from scrapers.naver_datalab_manager import NaverDataLabManager
        from datetime import datetime
        
        dl_mgr = NaverDataLabManager()
        enriched_count = 0
        
        # [SMART SORTING] Prioritize Opportunities (not just volume)
        # High KEI = High Opportunity. We check these first.
        insights.sort(key=lambda x: x.get('opp_score', 0), reverse=True)
        
        logger.info("📈 Analyzing Trend Velocity for Opportunities (Emerging Stars Focus)...")
        
        trend_check_count = 0
        MAX_TREND_CHECKS = 950 # Safety buffer for 1000/day quota
        
        # High Intent Markers
        intent_markers = ["가격", "비용", "후기", "추천", "효과", "통증", "실비", "잘하는"]
        
        for item in insights:
            # Initialize defaults
            item['trend_slope'] = 0.0
            item['trend_status'] = 'unknown'
            item['trend_checked_at'] = None
            
            # Stop if quota safety limit reached
            if trend_check_count >= MAX_TREND_CHECKS:
                continue

            # SMART SAMPLING CONDITION:
            # 1. Opp Score > 50 (Decent KEI)
            # 2. OR Search Volume > 100 AND Doc Count < 1000 (Very low competition)
            # 3. OR contains high intent marker
            search_vol = item.get('search_volume', 0)
            doc_count = item.get('volume', 999999)
            opp_score = item.get('opp_score', 0)
            kw = item.get('keyword', "")
            
            is_candidate = (opp_score >= 50) or (search_vol > 100 and doc_count < 1000) or any(m in kw for m in intent_markers)
            
            if is_candidate:
                slope = dl_mgr.get_trend_slope(kw)
                trend_check_count += 1
                
                if slope is not None:
                    item['trend_slope'] = slope
                    item['trend_checked_at'] = datetime.now().isoformat()
                    
                    if slope > 0.5: item['trend_status'] = 'rising_fast'
                    elif slope > 0: item['trend_status'] = 'rising'
                    elif slope > -0.5: item['trend_status'] = 'stable'
                    else: item['trend_status'] = 'falling'
                    
                    enriched_count += 1
                    if enriched_count % 20 == 0:
                        logger.info(f"   🔥 Enriched {enriched_count} gems with trend data.")
                        
        logger.info(f"✅ Trend Analysis Complete. {enriched_count} gems discovered. (Used: {trend_check_count})")
        return insights
    def _batch_save_to_db(self, insights):
        """Efficient batch insert with verification and error handling"""
        if not insights: 
            logger.warning("⚠️ No insights to save!")
            return False
            
        with self.db_lock:
            try:
                import sqlite3
                with sqlite3.connect(self.config.db_path, timeout=30) as conn:
                    cursor = conn.cursor()
                    # Updated schema includes search_volume, region, category AND Trend Data
                    cursor.execute('''CREATE TABLE IF NOT EXISTS keyword_insights (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT UNIQUE,
                        volume INTEGER,
                        competition TEXT,
                        opp_score REAL,
                        tag TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        search_volume INTEGER DEFAULT 0,
                        region TEXT DEFAULT '기타',
                        category TEXT DEFAULT '기타',
                        trend_slope REAL DEFAULT 0.0,
                        trend_status TEXT DEFAULT 'unknown',
                        trend_checked_at TIMESTAMP
                    )''')
                    
                    # Ensure all insights have required keys with defaults
                    for insight in insights:
                        insight.setdefault('region', '기타')
                        insight.setdefault('category', '기타')
                        insight.setdefault('trend_slope', 0.0)
                        insight.setdefault('trend_status', 'unknown')
                        insight.setdefault('trend_checked_at', None)
                    
                    cursor.executemany('''
                        INSERT INTO keyword_insights (
                            keyword, volume, competition, opp_score, tag, created_at, 
                            search_volume, region, category, 
                            trend_slope, trend_status, trend_checked_at
                        )
                        VALUES (
                            :keyword, :volume, :competition, :opp_score, :tag, datetime('now'), 
                            :search_volume, :region, :category,
                            :trend_slope, :trend_status, :trend_checked_at
                        )
                        ON CONFLICT(keyword) DO UPDATE SET
                            volume=excluded.volume,
                            competition=excluded.competition,
                            opp_score=excluded.opp_score,
                            tag=excluded.tag,
                            created_at=datetime('now'),
                            search_volume=excluded.search_volume,
                            region=excluded.region,
                            category=excluded.category,
                            trend_slope=excluded.trend_slope,
                            trend_status=excluded.trend_status,
                            trend_checked_at=excluded.trend_checked_at
                    ''', insights)
                    conn.commit()
                    
                    logger.info(f"✅ Saved {len(insights)} insights to DB successfully")
                    self._log_progress(f"💾 저장 완료: {len(insights)}개 키워드")
                    return True
                    
            except sqlite3.OperationalError as e:
                logger.error(f"❌ DB Operational Error: {e}", exc_info=True)
                self._log_progress(f"❌ DB 저장 실패: {str(e)[:50]}")
                return False
            except Exception as e:
                logger.error(f"❌ Unexpected DB Error: {e}", exc_info=True)
                self._log_progress(f"❌ 예상치 못한 오류: {str(e)[:50]}")
                return False

    # Keep legacy 'find_opportunities' for backward compatibility or single runs
    def find_opportunities(self, seed_keyword="청주 다이어트"):
        # Wrap single run logic...
        # For V3, we prioritize campaign. 
        # But if user enters single keyword in UI, we default to this.
        # Let's keep existing logic but just update it to use _batch_save?
        # Actually, let's Redirect single run to use the harvesting logic we just verified.
        
        # ... (Existing Logic refined)
        return self.run_campaign_single(seed_keyword)
        
    def run_campaign_single(self, seed_keyword):
        # The logic we just verified in V2
        from scrapers.keyword_harvester import KeywordHarvester
        from scrapers.naver_ad_manager import NaverAdManager
        
        harvester = KeywordHarvester()
        ad_mgr = NaverAdManager()
        
        logger.info(f"🚀 Single Target Mission: {seed_keyword}")
        
        # AI Expand
        seeds = [seed_keyword]
        try:
             # Basic expansion just to be safe
             if not self.crew: self.crew = AgentCrew()
             ai_output = self.crew.researcher.generate(f"List 10 related keywords for '{seed_keyword}' for Naver. Comma separated.")
             if ai_output and "Error" not in ai_output:
                new = [s.strip() for s in ai_output.split(',') if len(s) > 1]
                seeds.extend(new)
        except Exception as e:
            logger.warning(f"AI seed expansion failed: {e}")

        # [OPTIMIZED] Depth 2 유지 (적절한 깊이)
        candidates = harvester.harvest(seeds, depth=2, max_limit=300)
        
        # [NEW] Get True Demand (Search Volume)
        logger.info(f"💰 Fetching True Demand for {len(candidates)} keywords via Naver Ad API...")
        search_vol_map = ad_mgr.get_keyword_volumes(candidates)
        
        results = self._swarm_scan(candidates)
        
        insights = []
        for r in results:
            kw = r['keyword']
            doc_count = r['volume'] # 'volume' here is actually blog document count (Supply)
            search_vol = search_vol_map.get(kw, 0) # Demand
            
            score, tag = self._analyze_opportunity(search_vol, doc_count)
            
            insights.append({
                "keyword": kw,
                "volume": doc_count, # Keep legacy name for schema compatibility or rename? Schema expects 'volume'. Let's keep it as doc count.
                "competition": r['competition'],
                "opp_score": score,
                "tag": tag,
                "search_volume": search_vol, # [NEW]
                "category": "단일검색"  # Single keyword search mode
            })
        self._batch_save_to_db(insights)
        return pd.DataFrame(insights)

    def _analyze_opportunity(self, search_vol, doc_count):
        """
        Calculates Trend-Based KEI (Keyword Efficiency Index).
        Formula: (Search Volume ^ 2) / (Document Count + 1)
        High Score = High Demand, Low Supply.
        """
        # Robust conversion
        try:
            search_vol = int(search_vol) if search_vol else 0
            doc_count = int(doc_count) if doc_count else 0
        except Exception:
            search_vol = 0
            doc_count = 1

        if doc_count == 0: doc_count = 1 # Avoid division by zero
        if doc_count < 0: return 0, "Error"

        # 1. Calculate KEI
        try:
            kei = (search_vol ** 2) / doc_count
        except Exception:
            kei = 0
            
        # 2. Normalize Score (0 - 10000 range roughly)
        # KEI values can be huge. 
        # e.g., Search 1000, Docs 10 => 1,000,000 / 10 = 100,000
        # Search 100, Docs 100 => 10,000 / 100 = 100
        # Let's cap at 12000 for UI consistency
        
        opp_score = min(kei, 12000)
        if search_vol > 1000 and doc_count < 50:
            opp_score = 12000 # Jackpot
        
        # 3. Assign Tags based on Saturation & Demand
        tag = ""
        saturation = doc_count
        
        if search_vol > 500 and saturation < 100:
             tag = "Real Jackpot 💎" # High Demand, Empty
        elif saturation < 50:
            tag = "Super Blue Ocean 💎"
        elif saturation < 500:
             tag = "Golden Key 👑"
        else:
             if search_vol > 5000:
                 tag = "High Traffic 🚦"
             else:
                 tag = "Red Ocean 🔴"
            
        return round(opp_score, 1), tag

    def _swarm_scan(self, keywords, max_workers=2):
        """
        Executes parallel API scans (Blazing Fast but throttled slightly to avoid 401/429).
        """
        import concurrent.futures
        import time
        
        results = []
        # Check API Keys first
        self.client_id = self.config.get_api_key("NAVER_CLIENT_ID")
        self.client_secret = self.config.get_api_key("NAVER_CLIENT_SECRET")
        
        mode = "API" if (self.client_id and self.client_secret) else "SELENIUM"
        
        print(f"🐝 Swarm scanning {len(keywords)} keywords using {mode} Mode...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Map keyword to future
            future_to_kw = {executor.submit(self._scan_keyword, kw, mode): kw for kw in keywords}
            
            for future in concurrent.futures.as_completed(future_to_kw):
                kw = future_to_kw[future]
                try:
                    res = future.result()
                    results.append(res)
                    # Gentle delay to prevent burst
                    time.sleep(0.05) 
                except Exception as e:
                    logger.error(f"Worker failed on {kw}: {e}")
                    
        return results

    def _scan_keyword(self, kw, mode):
        """
        Scans a single keyword for volume/saturation.
        """
        vol = 0
        tag = "Red Ocean 🔴"
        
        if mode == "API":
            vol = self._get_volume_api(kw)
        else:
            # Fallback to Selenium (Slow & Flaky)
            # For now, if API is missing, we return 0 and warn
            # Or re-implement the fallback logic if absolutely needed.
            # But "Volume 3" bug suggests Selenium is bad here.
            # Let's try a simpler requests scrape if API missing?
            vol = 0 
            tag = "API Key Missing ❌"

        # Opportunity Logic
        score, tag = self._analyze_opportunity(vol, "Low") # Competition is placeholder
            
        print(f"   Checked '{kw}': {vol} (Mode: {mode})")
        
        return {
            "keyword": kw,
            "volume": vol,
            "competition": "High" if vol > 5000 else "Low",
            "opp_score": score,
            "tag": tag
        }

    def _get_volume_api(self, kw):
        import requests
        try:
            url = "https://openapi.naver.com/v1/search/blog.json"
            headers = {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret
            }
            params = {"query": kw, "display": 1, "sort": "sim"}
            resp = requests.get(url, headers=headers, params=params, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('total', 0)
            elif resp.status_code == 401:
                logger.error("Naver API 401 Unauthorized")
                return -1
            else:
                return -1
        except Exception as e:
            logger.error(f"API Error {kw}: {e}")
            return -1

if __name__ == "__main__":
    import sqlite3
    import json
    from datetime import datetime
    import sys
    from db.status_manager import status_manager

    pf = Pathfinder()
    # Explicitly mark as RUNNING at start
    status_manager.update_status("Pathfinder", "RUNNING", "Initializing Pathfinder Operations...")
    
    # Mode Selection based on Arguments
    # No args -> "Total War" (Campaign Mode)
    # Args -> "Single Mission" (Target Mode)
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        # LEGION MODE: python pathfinder.py --legion [target_count]
        if arg == "--legion":
            target = int(sys.argv[2]) if len(sys.argv) > 2 else 100000
            print(f"🦁 Launching LEGION MODE (Target: {target:,})...")
            status_manager.update_status("Pathfinder", "RUNNING", f"LEGION MODE: {target:,} Keywords...")
            try:
                count = pf.run_campaign_legion(target_count=target)
                status_manager.update_status("Pathfinder", "COMPLETED", f"Legion Optimized: {count:,} Gems Found")
                print(f"🎉 LEGION MODE Complete! {count:,} keywords analyzed.")
            except Exception as e:
                status_manager.update_status("Pathfinder", "ERROR", f"Legion Failed: {str(e)[:50]}")
                raise e
        else:
            # Single keyword mode
            target_kw = arg
            df = pf.find_opportunities(target_kw)
            print(df.head())
            
            # [PERSISTENCE FIX] Save to DB so Dashboard sees it
            try:
                # Check for Golden Keys
                golden = df[df['opp_score'] >= 100]
                
                if not golden.empty:
                    # Connect to DB
                    db_path = pf.config.db_path
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        
                        # Create Insight for the best one
                        best_kw = golden.iloc[0]['keyword']
                        score = golden.iloc[0]['opp_score']
                        
                        # Add [Single] tag to differentiate
                        title = f"👑 황금 키워드 발견: '{best_kw}'"
                        content = f"'{target_kw}' 연관 키워드 중 경쟁은 없고 검색량은 많은 키워드입니다! (기회점수: {score})"
                        meta = {
                            "suggested_action": "blog_generation",
                            "args": f"{best_kw} 관련 정보성 글",
                            "source": "pathfinder_script"
                        }
                        
                        # Check for duplicate recent insight
                        cursor.execute("SELECT id FROM insights WHERE title=? AND status='new'", (title,))
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO insights (type, title, content, meta_json) VALUES (?, ?, ?, ?)",
                                ("keyword_alert", title, content, json.dumps(meta))
                            )
                            lid = cursor.lastrowid
                            print(f"✅ Saved Insight #{lid} to DB.")
                        else:
                            print(f"ℹ️ Insight '{title}' already exists.")
                            
                else:
                    print("No Golden Keys found this run.")

            except Exception as e:
                print(f"❌ Failed to save results to DB: {e}")
            
    else:
        # Default: CAMPAIGN MODE (Total War)
        print("⚔️ Launching Total War Campaign...")
        status_manager.update_status("Pathfinder", "RUNNING", "TOTAL WAR: Multi-Category Expansion...")
        try:
            pf.run_campaign()
            status_manager.update_status("Pathfinder", "COMPLETED", "Total War Finished")
            print("✅ Total War Completed.")
        except Exception as e:
            status_manager.update_status("Pathfinder", "ERROR", f"War Failed: {str(e)[:50]}")
            raise e
