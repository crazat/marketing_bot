import sys
import os
import time
import random
import json
import argparse
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")
import logging

logger = logging.getLogger(__name__)

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'marketing_bot_web', 'backend'))

# [Phase 2.1] Event Bus Integration
try:
    from core.event_bus import publish_event, EventType
    HAS_EVENT_BUS = True
except ImportError:
    HAS_EVENT_BUS = False
    logger.debug("Event bus not available")

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from db.database import DatabaseManager
from services.ai_client import ai_generate, ai_generate_json

class CompetitorScout:
    def __init__(self, target_name, headless=True, search_suffix="후기"):
        self.target_name = target_name
        self.headless = headless
        self.search_suffix = search_suffix
        self.report_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports_competitor')
        if not os.path.exists(self.report_dir):
            os.makedirs(self.report_dir)
            
        self.has_llm = True  # ai_client handles initialization

    def scrape_naver_view(self, extra_keyword=""):
        """Uses Naver API to fetch Blog/Cafe posts securely."""
        from naver_api_client import NaverApiClient
        client = NaverApiClient()
        
        search_query = f"{self.target_name} {extra_keyword}".strip()
        print(f"🔍 API Searching: '{search_query}' (Deep Scan Mode)...")
        
        # [MODIFIED] Large Scale Data Collection (100 each = 200 total)
        blogs = client.search_blog(search_query, 100)
        cafes = client.search_cafe(search_query, 100)
        
        raw_items = blogs.get('items', []) + cafes.get('items', [])
        
        collected_data = []
        import re
        def clean(text): return re.sub(r'<.*?>', '', text)
        
        # Deep Crawl Enhancement
        # To avoid making 200 selenium calls which takes hours, we prioritize top 20 or use a faster method?
        # User requested "Upgrade to click and collect".
        # We will scan top 20 deeply, others shallow. 
        # Or if "Deep Scan" is the goal, maybe top 30.
        
        print("   🕷️ Deep Crawl initiated for Top 20 results (Quality over Quantity)...")
        from selenium.webdriver.common.by import By
        import time

        for idx, item in enumerate(raw_items):
            try:
                title = clean(item['title'])
                desc = clean(item['description'])
                date = item.get('postdate', 'Unknown')
                link = item['link']
                
                content = desc
                # Deep Crawl for Top 20 items
                if idx < 20: 
                    try:
                        full_body = self._run_deep_crawl(link)
                        if full_body:
                            content = full_body
                            print(f"      📖 read: {title[:20]}...")
                    except Exception as e:
                        logger.warning(f"Deep read fail for {link}: {e}")
                        pass

                entry = f"- [{date}] {title}\n  Content: {content}\n  Link: {link}"
                collected_data.append(entry)
            except Exception as item_err:
                logger.error(f"Error processing item {idx}: {item_err}", exc_info=True)
                continue
            
        print(f"   ✅ Collected {len(collected_data)} items (Top 20 Deep Scanned).")
        return collected_data

    def _run_deep_crawl(self, url):
        """Temp Selenium Worker for single page using STEALTH DRIVER."""
        from retry_helper import SafeSeleniumDriver
        import time
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from bs4 import BeautifulSoup
        
        # We instantiate a fresh driver for each deep crawl OR keep one alive?
        # Keeping one alive is faster.
        if not hasattr(self, 'driver') or self.driver is None:
             self._safe_driver_ctx = SafeSeleniumDriver(headless=self.headless)
             self.driver = self._safe_driver_ctx.__enter__()
             
        try:
             self.driver.execute_script(f"window.open('{url}', '_blank');")
             self.driver.switch_to.window(self.driver.window_handles[-1])
             
             # [Robustness] Use WebDriverWait instead of random sleep
             try:
                 WebDriverWait(self.driver, 10).until(
                     EC.presence_of_element_located((By.TAG_NAME, "body"))
                 )
             except Exception as e:
                logger.warning(f"WebDriverWait timed out or failed for URL {url}: {e}", exc_info=True)
                pass # Warning, but proceed to try parsing
             
             full_text = None
             
             # Detect Type by URL
             is_blog = 'blog.naver' in url
             is_cafe = 'cafe.naver' in url
             
             if is_blog:
                 try:
                     self.driver.switch_to.frame("mainFrame")
                     WebDriverWait(self.driver, 5).until(
                         EC.presence_of_element_located((By.CSS_SELECTOR, ".se-main-container, #postViewArea"))
                     )
                     soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                     el = soup.select_one('.se-main-container') or soup.select_one('#postViewArea')
                     if el: full_text = el.get_text(separator=' ').strip()[:3000]
                 except Exception: 
                     logger.debug("Blog content extraction failed (Safe fail)")
                     pass
             elif is_cafe:
                 try:
                     self.driver.switch_to.frame("cafe_main")
                     WebDriverWait(self.driver, 5).until(
                         EC.presence_of_element_located((By.CSS_SELECTOR, ".se-main-container, .ContentRenderer"))
                     )
                     soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                     el = soup.select_one('.se-main-container') or soup.select_one('.ContentRenderer')
                     if el: full_text = el.get_text(separator=' ').strip()[:3000]
                 except Exception: pass # Optional field
             else:
                  soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                  full_text = soup.select_one('body').get_text(separator=' ').strip()[:3000]

             self.driver.close()
             self.driver.switch_to.window(self.driver.window_handles[0])
             return full_text
        except Exception as e:
             logger.error(f"Deep Crawl Driver Error for {url}: {e}", exc_info=True)
             if len(self.driver.window_handles) > 1:
                 self.driver.close()
                 self.driver.switch_to.window(self.driver.window_handles[0])
             return None

    def close(self):
        """Explicit cleanup method."""
        if hasattr(self, '_safe_driver_ctx'):
            self._safe_driver_ctx.__exit__(None, None, None)
        elif hasattr(self, 'driver') and self.driver:
            try: self.driver.quit()
            except Exception: pass
            
    def __del__(self):
        self.close()

    def analyze_with_gemini(self, all_data):
        """
        [BATCH OPTIMIZED] AI 분석을 배치 단위로 수행하여 API 비용 절감.
        200개 데이터를 20개씩 묶어서 10회 API 호출 (기존 200회 → 10회)
        """
        if not self.has_llm:
            return "⚠️ AI 분석을 위한 API 키가 설정되지 않았습니다."

        BATCH_SIZE = 20
        all_insights = []

        print(f"   📊 AI 분석 시작 (총 {len(all_data)}개 데이터, 배치 크기: {BATCH_SIZE})")

        # 배치 단위로 분석
        for batch_idx in range(0, len(all_data), BATCH_SIZE):
            batch = all_data[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            total_batches = (len(all_data) + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"   🔄 배치 {batch_num}/{total_batches} 분석 중...")

            # 배치 데이터를 텍스트로 변환
            batch_text = ""
            for i, item in enumerate(batch):
                # 데이터 형식: "- [날짜] 제목\n  Content: 내용\n  Link: URL"
                batch_text += f"\n[항목 {i+1}]\n{item[:500]}\n"  # 각 항목 500자 제한

            prompt = f"""
당신은 마케팅 분석 전문가입니다. 다음은 '{self.target_name}'에 대한 온라인 게시물/리뷰입니다.

[분석 대상 데이터]
{batch_text}

각 항목을 분석하여 다음을 파악하세요:
1. 전반적인 감성 (긍정/부정/중립)
2. 주요 언급 키워드 및 관심사
3. 가격/서비스/효과에 대한 언급
4. 불만 사항이나 약점
5. 경쟁 우위 요소

JSON 형식으로 요약하세요:
{{
  "overall_sentiment": "positive/negative/neutral",
  "positive_count": 숫자,
  "negative_count": 숫자,
  "key_themes": ["주제1", "주제2"],
  "complaints": ["불만1", "불만2"],
  "strengths": ["강점1", "강점2"],
  "price_mentions": "가격 관련 요약",
  "service_mentions": "서비스 관련 요약"
}}
"""

            try:
                result_text = ai_generate(prompt, temperature=0.3, max_tokens=4096)
                all_insights.append({
                    'batch': batch_num,
                    'analysis': result_text
                })
            except Exception as e:
                logger.error(f"배치 {batch_num} 분석 실패: {e}")
                all_insights.append({
                    'batch': batch_num,
                    'analysis': f"분석 실패: {str(e)}"
                })

        # 최종 보고서 생성
        print(f"   📝 최종 보고서 생성 중...")

        final_prompt = f"""
다음은 '{self.target_name}'에 대한 배치별 분석 결과입니다. 이를 종합하여 최종 보고서를 작성하세요.

[배치별 분석 결과]
{json.dumps(all_insights, ensure_ascii=False, indent=2)}

다음 형식의 마크다운 보고서를 작성하세요:

# {self.target_name} 경쟁사 분석 보고서

## 📊 종합 요약
- 분석 데이터: {len(all_data)}건
- 전반적 평판: (긍정/부정/중립 비율)

## 💡 주요 발견사항

### 강점 (고객이 좋아하는 점)
-

### 약점 (불만 및 개선 필요 사항)
-

## 🎯 마케팅 기회
-

## 📈 권장 전략
-

## ⚠️ 위협 요소
-
"""

        try:
            report_text = ai_generate(final_prompt, temperature=0.3, max_tokens=4096)

            # [Phase 2.1] 약점 발견 이벤트 발행
            self._publish_weakness_events(report_text, all_insights, len(all_data))

            return report_text
        except Exception as e:
            logger.error(f"최종 보고서 생성 실패: {e}")
            # 폴백: 개별 분석 결과 연결
            fallback_report = f"# {self.target_name} 분석 보고서\n\n"
            fallback_report += f"분석 데이터: {len(all_data)}건\n\n"
            for insight in all_insights:
                fallback_report += f"## 배치 {insight['batch']}\n{insight['analysis']}\n\n"
            return fallback_report

    def _publish_weakness_events(self, report_text: str, all_insights: list, data_count: int):
        """
        [Phase 2.1] 분석 결과에서 약점을 추출하고 이벤트 발행
        """
        if not HAS_EVENT_BUS:
            return

        try:
            # 약점 섹션 추출 (마크다운에서)
            weaknesses = []

            # 패턴 1: "### 약점" 섹션에서 추출
            weakness_match = re.search(r'### 약점[^#]*?(?=###|##|$)', report_text, re.DOTALL)
            if weakness_match:
                section = weakness_match.group(0)
                # 불릿 포인트 추출
                bullets = re.findall(r'[-*]\s*(.+?)(?:\n|$)', section)
                weaknesses.extend([b.strip() for b in bullets if len(b.strip()) > 5])

            # 패턴 2: all_insights의 complaints에서 추출
            for insight in all_insights:
                try:
                    analysis = insight.get('analysis', '')
                    # JSON 블록 찾기
                    json_match = re.search(r'\{[^{}]*"complaints"[^{}]*\}', analysis, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group(0))
                        if 'complaints' in data:
                            weaknesses.extend(data['complaints'])
                except Exception:
                    pass

            # 중복 제거
            weaknesses = list(set(weaknesses))[:10]  # 최대 10개

            if weaknesses:
                publish_event(
                    EventType.COMPETITOR_WEAKNESS_DETECTED,
                    {
                        "competitor_name": self.target_name,
                        "weaknesses": weaknesses,
                        "weakness_count": len(weaknesses),
                        "analyzed_data_count": data_count,
                        "analysis_type": "deep_scan"
                    },
                    source="competitor_scout"
                )
                logger.info(f"🎯 경쟁사 약점 {len(weaknesses)}개 발견: {self.target_name}")

        except Exception as e:
            logger.debug(f"Failed to publish weakness event: {e}")

    def run(self):
        print(f"[{datetime.now()}] 🕵️ Deep Scan Started for: {self.target_name}")
        try:
            reviews = self.scrape_naver_view(self.search_suffix)
            prices = self.scrape_naver_view("가격")
            
            # Merge and Dedup (by Link)
            seen_links = set()
            all_data = []
            for x in reviews + prices:
                # Extract link for dedup
                link = x.split("Link: ")[-1].strip()
                if link not in seen_links:
                    seen_links.add(link)
                    all_data.append(x)
            
            if not all_data:
                print("❌ No data found to analyze.")
                report_content = "❌ 데이터 수집 실패."
            else:
                # PASS ALL DATA
                report_content = self.analyze_with_gemini(all_data)
            
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"{timestamp}_{self.target_name}_DeepReport.md"
            save_path = os.path.join(self.report_dir, filename)
            
            final_md = report_content
            
            # Append Top 20 sources for reference (Not full list to keep file readable, but user wants to know we used many)
            if all_data:
                final_md += f"\n\n---\n### 📎 Ref: Analyzed Sources (Total {len(all_data)} items - Showing Top 20)\n"
                final_md += "\n".join(all_data[:20])
                if len(all_data) > 20: final_md += f"\n... and {len(all_data)-20} more."
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(final_md)
                
            print(f"💾 Report Saved: {save_path}")
        finally:
            self.close()

if __name__ == "__main__":
    import atexit
    
    # [Robustness] use argparse
    parser = argparse.ArgumentParser(description="Competitor Scout Bot")
    parser.add_argument("target_name", nargs="*", help="Target Name (can be multiple words)")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode")
    parser.add_argument("--suffix", default="후기", help="Search suffix")
    
    # Handle known args to avoid crashing on extra flags from Orchestrator (if any)
    args, unknown = parser.parse_known_args()
    
    # Reconstruct target name if split by spaces
    target = " ".join(args.target_name).strip() if args.target_name else "규림한의원"
    
    scout = CompetitorScout(target, headless=not args.headed, search_suffix=args.suffix)
    atexit.register(scout.close) # [Robustness] Ensure cleanup on exit
    scout.run()
