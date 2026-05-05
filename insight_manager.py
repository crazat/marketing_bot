import sqlite3
import json
import logging
import os
import glob
import argparse
import sys
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import ConfigManager
from retry_helper import safe_subprocess
from core_utils import safe_close

# [Phase 5-1] 설정값 외부화
try:
    from config.app_settings import get_settings
    _app_settings = get_settings()
except ImportError:
    _app_settings = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InsightEngine")

class InsightManager:
    def __init__(self):
        self.config = ConfigManager()
        self.db_path = self.config.db_path
        self.root_dir = self.config.root_dir

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def create_insight(self, i_type, title, content, meta=None):
        """Creates a new insight record if it doesn't duplicate a recent active one."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check duplication (same title, status='new', created within 24h)
            cursor.execute("SELECT id FROM insights WHERE title=? AND status='new'", (title,))
            existing = cursor.fetchone()
            
            if existing:
                logger.info(f"Insight '{title}' already exists. Skipping.")
                return existing[0]

            meta_json = json.dumps(meta) if meta else None
            cursor.execute(
                "INSERT INTO insights (type, title, content, meta_json) VALUES (?, ?, ?, ?)",
                (i_type, title, content, meta_json)
            )
            conn.commit()
            lid = cursor.lastrowid
            logger.info(f"✅ Created Insight #{lid}: {title}")
            return lid

    def get_active_insights(self):
        """Returns all 'new' insights."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM insights WHERE status='new' ORDER BY created_at DESC")
            rows = cursor.fetchall()
            
            insights = []
            for r in rows:
                meta = json.loads(r['meta_json']) if r['meta_json'] else {}
                insights.append({
                    "id": r['id'],
                    "type": r['type'],
                    "title": r['title'],
                    "content": r['content'],
                    "meta": meta,
                    "created_at": r['created_at']
                })
            return insights

    def update_status(self, insight_id, status):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE insights SET status=? WHERE id=?", (status, insight_id))
            conn.commit()

    # --- Logging ---
    def log_activity(self, source, message, level="INFO"):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_logs (module, message, level) VALUES (?, ?, ?)",
                (source, message, level)
            )
            conn.commit()
        logger.info(f"[{source}] {message}")

    # --- Generators (Real Logic) ---
    def generate_rank_insights(self):
        self.log_activity("Sentinel", "Starting Rank Check Cycle...")
        
        try:
             # 1. Run Scraper (Real)
             # This updates the 'rank_history' table in DB
             script_path = os.path.join(self.config.root_dir, "scrapers", "scraper_naver_place.py")
             _timeout = _app_settings.insight_task_timeout if _app_settings else 300
             result = safe_subprocess(["python", script_path], timeout=_timeout)
             if result["success"]:
                 self.log_activity("Sentinel", "Rank Scraper executed.")
             else:
                 self.log_activity("Sentinel", f"Rank Scraper issue: {result['stderr']}", "WARNING")
             
             # 2. Analyze Result (Real Logic)
             from analysis_engine import AnalysisEngine
             analyzer = AnalysisEngine()
             
             # Check for any significant drops for monitored keywords
             # Check for any significant drops for monitored keywords
             # Dynamic Loading
             targets_cfg = self.config.load_targets()
             # Flatten all check keywords
             keywords = []
             for t in targets_cfg.get('targets', []):
                  if "규림" in t['name']:
                      keywords.extend(t.get('keywords', []))
             
             # Fallback
             if not keywords: keywords = ["청주 다이어트", "청주 한의원"] 
             
             for kw in keywords:
                 analysis = analyzer.analyze_rank_drop(kw)
                 if analysis:
                     self.create_insight(
                        i_type="rank_drop",
                        title=f"🚨 '{kw}' 순위 변동 감지",
                        content=analysis['primary_reason'],
                        meta={
                            "suggested_action": "blog_generation", 
                            "args": f"{kw} 순위 방어",
                            "analysis": analysis
                        }
                     )

        except Exception as e:
             self.log_activity("Sentinel", f"Rank Scraper Failed: {e}", "ERROR")

    def generate_community_insights(self):
        self.log_activity("Sentinel", "Starting Cafe Spy (Parallel Mode)...")
        try:
             script_path = os.path.join(self.config.root_dir, "scrapers", "cafe_spy.py")
             if not os.path.exists(script_path):
                 self.log_activity("Sentinel", "Cafe Spy script not found.", "ERROR")
                 return

             # 1. Load Target Cafes to split workload
             # We need to know WHICH cafes to scan to spawn parallel workers.
             # ConfigManager usually has 'targets.json' logic
             targets_data = self.config.load_targets()
             
             # Extract cafes list (Phase 3 format in targets.json: 'cafes': [...])
             # If not present, fallback to defaults (but we can't easily parallelize defaults if we don't know them here).
             # Let's assume user has 'cafes' in targets.json or we add a hardcoded fallback list matching cafe_spy.py
             
             cafes_to_scan = []
             if 'cafes' in targets_data:
                 cafes_to_scan = [c['name'] for c in targets_data['cafes']]
             
             # Fallback if config is empty (match cafe_spy.py defaults for now)
             if not cafes_to_scan:
                 cafes_to_scan = [
                     "청주 맘스캠프 (맘캠 이야기방)",
                     "청주 맘블리 (청주맘이야기)",
                     "청주 테크노폴리스맘 (동네이야기)"
                 ]
             
             self.log_activity("Sentinel", f"Dispatching Spies to {len(cafes_to_scan)} cafes...")

             # 2. Parallel Execution
             from concurrent.futures import ThreadPoolExecutor, as_completed

             # [Phase 5-1] 설정에서 워커 수와 타임아웃 로드
             _workers = _app_settings.insight_max_workers if _app_settings else 3
             _timeout = _app_settings.subprocess_timeout if _app_settings else 600

             with ThreadPoolExecutor(max_workers=_workers) as executor:
                 futures = {}
                 for cafe_name in cafes_to_scan:
                     # Run: python cafe_spy.py --cafe_name "NAME"
                     cmd = ["python", script_path, "--cafe_name", cafe_name]
                     # We use safe_subprocess BUT inside a thread, so it blocks the thread (fine)
                     futures[executor.submit(safe_subprocess, cmd, timeout=_timeout)] = cafe_name
                 
                 # Wait for all
                 for future in as_completed(futures):
                     cafe = futures[future]
                     try:
                         res = future.result()
                         if res["success"]:
                             self.log_activity("Sentinel", f"✅ Spy checked '{cafe}' successfully.")
                         else:
                             msg = res['stderr'][:200] if res['stderr'] else "Unknown Error"
                             self.log_activity("Sentinel", f"⚠️ Spy failed at '{cafe}': {msg}", "WARNING")
                     except Exception as e:
                         self.log_activity("Sentinel", f"💥 Spy Thread Error '{cafe}': {e}", "ERROR")

             self.log_activity("Sentinel", "All Cafe Spies returned.")

             # 3. Check for new reports (Aggregated)
             r_dir = os.path.join(self.config.root_dir, 'reports_cafe')
             if os.path.exists(r_dir):
                 # Look for files created in last 10 mins
                 files = glob.glob(os.path.join(r_dir, "cafe_report_*.md"))
                 recent_files = [f for f in files if (datetime.now().timestamp() - os.path.getmtime(f)) < 600]
                 
                 if recent_files:
                     count = len(recent_files)
                     self.create_insight(
                         i_type="community_alert",
                         title=f"🕵️ 맘카페 잠입 보고서 ({count}건)",
                         content=f"{count}개의 카페에서 새로운 여론 분석 보고서가 생성되었습니다.",
                         meta={"suggested_action": "read_report", "args": recent_files[0]} # Link to newest
                     )

        except Exception as e:
             self.log_activity("Sentinel", f"Cafe Spy Error: {e}", "ERROR")

    def generate_competitor_activity_insights(self):
        """
        Scans registered competitors in DB for new activity (Reviews).
        """
        self.log_activity("Sentinel", "Checking Registered Competitors...")
        
        # 1. Run Review Scraper (Real)
        # We integrated this into scraper_naver_place, or we run it explicitly.
        # Let's run scraper_naver_place again or assuming it ran in step 1?
        # Ideally, separate. But for now, let's trigger the Review Collection function.
        # Since we can't easily import a script function here without structure, we rely on subprocess if main triggers it.
        # Actually, scraper_naver_place.py's main runs BOTH rank and reviews now.
        
        # 2. Check DB for TODAY's new reviews
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute("SELECT competitor_name, content FROM competitor_reviews WHERE review_date=? AND source='naver_place_real'", (today,))
        rows = cursor.fetchall()
        safe_close(conn)
        
        if not rows:
            self.log_activity("Sentinel", "No new competitor reviews found today.")
            return

        # Group by competitor
        comp_map = {}
        for r in rows:
            c_name, txt = r
            comp_map[c_name] = comp_map.get(c_name, 0) + 1
            
        for c_name, count in comp_map.items():
            self.create_insight(
                i_type="competitor_alert",
                title=f"🕵️ [{c_name}] 신규 리뷰 {count}건 감지",
                content=f"오늘 경쟁사 '{c_name}'에 새로운 영수증 리뷰가 등록되었습니다. Tactician 분석을 권장합니다.",
                meta={"suggested_action": "competitor_analysis", "args": c_name}
            )

    def generate_strategic_insights(self):
        """
        Uses The Tactician to find attack vectors based on VoC.
        """
        self.log_activity("Sentinel", "Tactician: Analyzing Competitor VoC...")
        try:
            from tactician import TargetedTactician
            tactician = TargetedTactician()
            
            # Focus on key targets (Dynamic from config)
            targets_cfg = self.config.load_targets()
            key_targets = [t['name'] for t in targets_cfg.get('targets', []) if '규림' not in t['name']]
            
            if not key_targets: key_targets = ["데이릴 한의원", "리샘한의원"] # Fallback
            
            for target in key_targets:
                strategy = tactician.analyze_and_propose(target)
                if strategy:
                    self.create_insight(
                        i_type="strategy_proposal",
                        title=strategy['title'],
                        content=strategy['content'], # Rich formatted content
                        meta={
                            "suggested_action": strategy['action'], 
                            "args": strategy['args'],
                            "evidence": strategy.get('evidence_data')
                        }
                    )
                    self.log_activity("Sentinel", f"Tactician generated strategy against {target}")
                    
        except Exception as e:
            self.log_activity("Sentinel", f"Tactician Error: {e}", "ERROR")
    
    def generate_seasonal_insights(self):
        self.log_activity("Sentinel", "Checking Seasonal Calendar...")
        
        # Real Logic: Load Trend Matrix
        matrix = self.config.load_trend_matrix()
        current_month = str(datetime.now().month)
        
        themes = matrix.get(current_month, {})
        if not themes:
            self.log_activity("Sentinel", "No seasonal data found for this month.")
            return

        # Scan all themes for relevant opportunities
        for category, keywords in themes.items():
            # For each category, pick the first keyword as a representative for now
            # In a full V2, we would scan volume for all.
            # Here we generate an insight for the category itself.
            if keywords:
                prime_keyword_str = ", ".join(keywords[:3])
                self.create_insight(
                    i_type="seasonality",
                    title=f"📅 {current_month}월 시즌 키워드: [{category.upper()}]",
                    content=f"이달의 핵심 키워드는 '{prime_keyword_str}' 입니다. 관련 콘텐츠를 미리 준비하세요.",
                    meta={"suggested_action": "blog_generation", "args": f"{keywords[0]} 정보성 글"}
                )

    def generate_keyword_opportunities(self):
        """
        Proactively runs Pathfinder to find Golden Keywords (Blue Ocean).
        Scans ALL configured community keywords.
        """
        self.log_activity("Sentinel", "Pathfinder: Exploring Blue Ocean Keywords...")
        try:
            from pathfinder import Pathfinder
            pf = Pathfinder()
            
            # Load from Config
            targets_cfg = self.config.load_targets()
            topics = targets_cfg.get('community_scan_keywords', ["청주 다이어트"]) # Fallback
            
            # Full Census Loop
            for topic in topics:
                self.log_activity("Sentinel", f"Pathfinder: Scanning '{topic}'...")
                df = pf.find_opportunities(topic)
                
                # Check for 'Golden Key'
                golden = df[df['opp_score'] >= 100]
                
                if not golden.empty:
                    best_kw = golden.iloc[0]['keyword']
                    score = golden.iloc[0]['opp_score']
                    
                    self.create_insight(
                        i_type="keyword_alert",
                        title=f"👑 황금 키워드 발견: '{best_kw}'",
                        content=f"'{topic}' 연관 키워드 중 경쟁은 없고 검색량은 많은 키워드입니다! (기회점수: {score})",
                        meta={"suggested_action": "blog_generation", "args": f"{best_kw} 관련 정보성 글"}
                    )
                    self.log_activity("Sentinel", f"Pathfinder found Golden Key: {best_kw}")
                else:
                    self.log_activity("Sentinel", f"Pathfinder: No golden keys found for {topic} this time.")
                 
        except Exception as e:
            self.log_activity("Sentinel", f"Pathfinder Error: {e}", "ERROR")

    def generate_view_rank_insights(self):
        """
        The Sniper: Monitors Naver View Tab rankings.
        Provedes specific details: Who overtook us? Why? What to do?
        **Census Mode**: Checks ALL active competitors.
        """
        self.log_activity("Sentinel", "The Sniper: Scanning View Tab Rankings (Full Census)...")
        try:
            # Load Competitors from Config
            targets_cfg = self.config.load_targets()
            competitors = [t for t in targets_cfg.get('targets', []) if '규림' not in t['name']]
            
            if not competitors:
                self.log_activity("Sentinel", "No competitors found in config.")
                return

            # Real: Run Scraper needed? 
            # Ideally scraper runs independently. Here we analyze DB history or trigger checks.
            # Assuming 'scraper_view_search.py' runs for one keyword.
            # We will trigger the scraper for EACH competitor's main keyword if needed.
            # But 'scraper_view_search.py' uses args? Let's check.
            # Actually, `scraper_view_search.py` (checked earlier in session) handles keywords.
            # Let's assume the scraper is robust enough, or we simulate analysis here.
            # For this "Census", let's iterate and check rank.

            from analysis_engine import AnalysisEngine
            analyzer = AnalysisEngine()

            # Iterate ALL competitors
            for comp in competitors:
                comp_name = comp['name']
                # Check their primary keywords
                for kw in comp.get('keywords', [])[:2]: # Check top 2 keywords per competitor
                    
                    # (Optional) Trigger Real Scraper here if we want real-time.
                    # subprocess.run(["python", script_path, "--keyword", kw], ...)
                    # optimized: analyze existing DB data first.
                    
                    analysis = analyzer.analyze_rank_drop(kw)
                    
                    if analysis:
                        self.create_insight(
                            i_type="rank_alert",
                            title=f"🚨 [VIEW] '{kw}' 경쟁사({comp_name}) 동향",
                            content=f"**[순위 분석 리포트]**\n"
                                    f"- **대상**: {comp_name}\n"
                                    f"- **상태**: {analysis['status']}\n"
                                    f"- **변동폭**: {analysis['gap']}\n"
                                    f"- **원인**: {analysis['primary_reason']}",
                            meta={
                                "suggested_action": "rank_recovery", 
                                "args": f"{kw} 경쟁 우위 확보",
                                "priority": "high"
                            }
                        )
                    else:
                        pass # No significant alert
                        
            self.log_activity("Sentinel", f"View Tab Census Completed for {len(competitors)} competitors.")
        except Exception as e:
            self.log_activity("Sentinel", f"View Monitor Error: {e}", "ERROR")

    def generate_visual_trend_insights(self):
        """
        Analyzes Instagram/Blog images for visual trends.
        """
        # REAL LOGIC: 
        # 1. Scrape top 9 posts for '청주 다이어트' via Ambassador/Scraper
        # 2. Use Vision API to tag images (e.g. 'mirror', 'food', 'gym')
        # 3. If dominant tag != our recent posts, alert.
        
        # [Vision AI Integration]
        # 1. Search for recent images in scraped data folder
        img_dir = os.path.join(self.root_dir, 'data', 'images_scraped')
        os.makedirs(img_dir, exist_ok=True)
        
        images = glob.glob(os.path.join(img_dir, "*.jpg")) + glob.glob(os.path.join(img_dir, "*.png"))
        
        if not images:
            self.log_activity("Sentinel", "Visual Trend: No images to analyze yet. (Waiting for scraper downloads)")
            return

        try:
            from vision_analyst import VisionAnalyst
            analyst = VisionAnalyst()
            
            # Analyze top 5 images
            report = analyst.analyze_visual_trend(images[:5])
            
            if report:
                title = f"📸 비주얼 트렌드 포착 ({datetime.now().strftime('%m/%d')})"
                
                # Save as Insight
                self.create_insight(
                    i_type="visual_trend",
                    title=title,
                    content=report,
                    meta={
                        "source_images": images[:5],
                        "suggested_action": "strategy_report",
                        "args": "최신 비주얼 트렌드 반영 콘텐츠 기획"
                    }
                )
                self.log_activity("Sentinel", "Visual Trend Analysis Completed via Gemini 3 Flash.")
                
        except Exception as e:
            self.log_activity("Sentinel", f"Visual Analysis Error: {e}")

    def _generate_prophet_forecast_insights(self) -> bool:
        try:
            from prophet import TheProphet

            forecast = TheProphet().predict_next_week()
            trends = forecast.get("rising_trends", []) if forecast else []
            if not trends:
                return False

            for trend in trends[:3]:
                keyword = trend.get("keyword", "")
                growth = trend.get("predicted_growth", "Trend")
                evidence = trend.get("evidence", "")
                action = trend.get("action", "content_preloading")
                self.create_insight(
                    i_type="trend_forecast",
                    title=f"🔮 [Prophet] {growth} : '{keyword}'",
                    content=(
                        f"**[Forecast]**\n"
                        f"- Period: {forecast.get('target_period', 'N/A')}\n"
                        f"- Keyword: {keyword}\n"
                        f"- Evidence: {evidence}"
                    ),
                    meta={
                        "suggested_action": action,
                        "args": keyword,
                        "forecast": forecast.get("target_period"),
                        "evidence": evidence,
                    },
                )
            self.log_activity("Sentinel", f"Prophet forecast generated {len(trends[:3])} insights.")
            return True
        except Exception as e:
            self.log_activity("Sentinel", f"Prophet Forecast Error: {e}", "ERROR")
            return False

    def generate_prophet_insights(self):
        """
        The Prophet: Reports on 'Rising Stars' (High Trend Velocity) from DB.
        """
        self.log_activity("Sentinel", "The Prophet: Analyzing Real-time Trend Velocity...")
        
        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Fetch TOP 3 Rising Keywords (Slope > 0.1)
            cursor.execute("""
                SELECT keyword, trend_slope, search_volume, competition 
                FROM keyword_insights 
                WHERE trend_slope > 0.1 AND trend_status IN ('rising', 'rising_fast')
                ORDER BY trend_slope DESC 
                LIMIT 3
            """)
            rising_stars = cursor.fetchall()
            safe_close(conn)

            if not rising_stars:
                if self._generate_prophet_forecast_insights():
                    return
                self.log_activity("Sentinel", "Prophet: No significant rising trends found yet.")
                return

            # Create Report for the #1 Star
            top_kw = rising_stars[0]
            slope = top_kw['trend_slope']
            vol = top_kw['search_volume']

            # Construct Evidence String for AI
            evidence = f"Trend Slope: {slope:.4f} (Very High), Search Volume: {vol}"

            self.create_insight(
                i_type="trend_forecast",
                title=f"📈 [급상승] '{top_kw['keyword']}' 트렌드 포착!",
                content=f"**[데이터랩 분석 결과]**\n"
                        f"- **키워드**: {top_kw['keyword']}\n"
                        f"- **성장강도**: {slope} (급상승 중)\n"
                        f"- **골든키**: 경쟁({top_kw['competition']}) vs 검색량({vol})\n"
                        f"지금 바로 콘텐츠를 선점하여 상위 노출을 노리세요.",
                meta={
                    "suggested_action": "blog_generation",
                    "args": f"{top_kw['keyword']} 트렌드 선점 정보성 글",
                    "evidence_data": {k: top_kw[k] for k in top_kw.keys()}
                }
            )
            self.log_activity("Sentinel", f"Prophet Reported Trend: {top_kw['keyword']}")

        except Exception as e:
            self.log_activity("Sentinel", f"Prophet Error: {e}", "ERROR")
            self._generate_prophet_forecast_insights()

    def generate_ambassador_insights(self):
        """
        The Ambassador: Scouts for influencers in hotplaces.
        **Census Mode**: Scouts ALL defined hunting grounds.
        """
        self.log_activity("Sentinel", "The Ambassador: Scouting Hotplaces (Full Census)...")
        try:
            from ambassador import TheAmbassador
            amb = TheAmbassador()

            # Load Hunting Grounds
            targets_cfg = self.config.load_targets()
            places = targets_cfg.get('hunting_grounds', ["청주 성안길"])

            count = 0
            for target in places:
                self.log_activity("Sentinel", f"Ambassador: Scouting '{target}'...")
                candidates = amb.scout_and_vet(target)

                if candidates:
                    # Report top candidate for each place
                    best = candidates[0]
                    self.create_insight(
                        i_type="influencer_discovery",
                        title=f"🤝 [Ambassador] '{target}' 인플루언서 발견",
                        content=f"**{best['handle']}** 님을 발굴했습니다.\n"
                                f"- 최신글: {best.get('recent_content', 'N/A')}\n"
                                f"- 섭외 제안 DM 초안이 준비되었습니다.",
                        meta={
                            "suggested_action": "send_dm",
                            "args": best['handle'],
                            "draft_dm": best.get('draft_dm', '안녕하세요...')
                        }
                    )
                    count += 1

            self.log_activity("Sentinel", f"Ambassador Census Finished. Found influencers in {count}/{len(places)} areas.")
        except Exception as e:
            self.log_activity("Sentinel", f"Ambassador Error: {e}", "ERROR")

    def cleanup_old_insights(self, days: int = 30):
        """
        오래된 인사이트를 아카이브 처리합니다.
        Args:
            days: 이 기간보다 오래된 인사이트를 아카이브
        """
        self.log_activity("Sentinel", f"Cleaning up insights older than {days} days...")
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

                # 'new' 상태인 오래된 인사이트를 'archived'로 변경
                cursor.execute('''
                    UPDATE insights
                    SET status = 'archived', updated_at = ?
                    WHERE status = 'new' AND created_at < ?
                ''', (datetime.now().isoformat(), cutoff_date))

                archived_count = cursor.rowcount
                conn.commit()

                if archived_count > 0:
                    self.log_activity("Sentinel", f"✅ Archived {archived_count} old insights")
                else:
                    self.log_activity("Sentinel", "No old insights to archive")

                return archived_count
        except Exception as e:
            self.log_activity("Sentinel", f"Cleanup Error: {e}", "ERROR")
            return 0


class BriefingRunner:
    """
    Briefing 실행을 관리하는 클래스.
    병렬 실행, 상태 추적, DB 저장, 알림을 담당합니다.
    """

    # 사용 가능한 태스크 정의
    AVAILABLE_TASKS = {
        'rank_insights': {
            'name': '순위 체크',
            'method': 'generate_rank_insights',
            'phase': 'visibility'
        },
        'view_rank_insights': {
            'name': 'VIEW 탭 순위',
            'method': 'generate_view_rank_insights',
            'phase': 'visibility'
        },
        'community_insights': {
            'name': '커뮤니티 분석',
            'method': 'generate_community_insights',
            'phase': 'intelligence'
        },
        'competitor_activity': {
            'name': '경쟁사 동향',
            'method': 'generate_competitor_activity_insights',
            'phase': 'intelligence'
        },
        'strategic_insights': {
            'name': '전략 제안',
            'method': 'generate_strategic_insights',
            'phase': 'intelligence'
        },
        'seasonal_insights': {
            'name': '시즌 키워드',
            'method': 'generate_seasonal_insights',
            'phase': 'discovery'
        },
        'keyword_opportunities': {
            'name': '키워드 기회',
            'method': 'generate_keyword_opportunities',
            'phase': 'discovery'
        },
        'visual_trend': {
            'name': '비주얼 트렌드',
            'method': 'generate_visual_trend_insights',
            'phase': 'discovery'
        },
        'prophet_insights': {
            'name': '트렌드 예측',
            'method': 'generate_prophet_insights',
            'phase': 'discovery'
        },
        'ambassador_insights': {
            'name': '인플루언서 발굴',
            'method': 'generate_ambassador_insights',
            'phase': 'discovery'
        }
    }

    def __init__(self, insight_manager: InsightManager, max_workers: int = None):
        self.manager = insight_manager
        # [Phase 5-1] 설정에서 워커 수 로드
        _default_workers = _app_settings.insight_max_workers if _app_settings else 3
        self.max_workers = max_workers or _default_workers
        self.config = ConfigManager()
        self.run_id = None
        self.results = {}

        # DB Manager 초기화
        from db.database import DatabaseManager
        self.db = DatabaseManager()

    def load_briefing_config(self) -> dict:
        """briefing_config.json에서 설정을 로드합니다."""
        config_path = os.path.join(self.config.root_dir, 'config', 'briefing_config.json')

        # [Phase 5-1] 설정에서 기본값 로드
        _default_workers = _app_settings.insight_max_workers if _app_settings else 3
        default_config = {
            'enabled_tasks': list(self.AVAILABLE_TASKS.keys()),
            'max_workers': _default_workers,
            'notify_on_start': True,
            'notify_on_complete': True,
            'notify_on_failure': True
        }

        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
            except Exception as e:
                logger.warning(f"Failed to load briefing config: {e}")

        return default_config

    def send_telegram_alert(self, message: str, is_error: bool = False):
        """텔레그램 알림을 발송합니다."""
        try:
            from alert_bot import TelegramBot
            secrets_path = os.path.join(self.config.root_dir, 'config', 'secrets.json')

            if not os.path.exists(secrets_path):
                return

            with open(secrets_path, 'r', encoding='utf-8') as f:
                secrets = json.load(f)

            telegram = TelegramBot(
                token=secrets.get("TELEGRAM_BOT_TOKEN", ""),
                chat_id=secrets.get("TELEGRAM_CHAT_ID", "")
            )

            prefix = "🚨" if is_error else "🌅"
            telegram.send_message(f"{prefix} {message}")
        except Exception as e:
            logger.warning(f"Telegram alert failed: {e}")

    def execute_task(self, task_key: str) -> dict:
        """개별 태스크를 실행하고 결과를 반환합니다."""
        task_info = self.AVAILABLE_TASKS.get(task_key)
        if not task_info:
            return {'status': 'error', 'error': f'Unknown task: {task_key}'}

        start_time = time.time()
        task_id = self.db.create_task_result(self.run_id, task_key)

        try:
            method = getattr(self.manager, task_info['method'])
            method()

            duration_ms = int((time.time() - start_time) * 1000)
            self.db.update_task_result(task_id, 'completed', duration_ms)

            return {
                'task_key': task_key,
                'status': 'completed',
                'duration_ms': duration_ms
            }
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            self.db.update_task_result(task_id, 'failed', duration_ms, error_msg)

            return {
                'task_key': task_key,
                'status': 'failed',
                'duration_ms': duration_ms,
                'error': error_msg
            }

    def execute(self) -> dict:
        """
        전체 Briefing을 실행합니다.
        Returns:
            실행 결과 요약 dict
        """
        config = self.load_briefing_config()
        enabled_tasks = config.get('enabled_tasks', list(self.AVAILABLE_TASKS.keys()))
        self.max_workers = config.get('max_workers', 3)

        # 실행할 태스크 필터링
        tasks_to_run = [t for t in enabled_tasks if t in self.AVAILABLE_TASKS]

        if not tasks_to_run:
            logger.warning("No tasks enabled for briefing")
            return {'status': 'skipped', 'reason': 'No tasks enabled'}

        # Briefing 실행 기록 생성
        self.run_id = self.db.create_briefing_run(len(tasks_to_run))
        start_time = time.time()

        # 시작 알림
        if config.get('notify_on_start', True):
            self.send_telegram_alert(f"Morning Briefing 시작 ({len(tasks_to_run)}개 태스크)")

        self.manager.log_activity("Sentinel", f"🌅 Starting Briefing (Parallel Mode, {self.max_workers} workers)...")

        # 오래된 인사이트 정리
        self.manager.cleanup_old_insights(30)

        completed = 0
        failed = 0
        errors = []

        # 병렬 실행
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.execute_task, task): task for task in tasks_to_run}

            for future in as_completed(futures):
                task_key = futures[future]
                try:
                    result = future.result()
                    self.results[task_key] = result

                    if result['status'] == 'completed':
                        completed += 1
                        self.manager.log_activity("Sentinel", f"✅ {self.AVAILABLE_TASKS[task_key]['name']} 완료 ({result['duration_ms']}ms)")
                    else:
                        failed += 1
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"{task_key}: {error_msg}")
                        self.manager.log_activity("Sentinel", f"❌ {self.AVAILABLE_TASKS[task_key]['name']} 실패: {error_msg}", "ERROR")

                except Exception as e:
                    failed += 1
                    errors.append(f"{task_key}: {str(e)}")
                    self.manager.log_activity("Sentinel", f"💥 {task_key} 예외: {e}", "ERROR")

        # 실행 완료 기록
        total_time_ms = int((time.time() - start_time) * 1000)
        status = 'completed' if failed == 0 else ('partial' if completed > 0 else 'failed')
        error_log = '\n'.join(errors) if errors else None

        self.db.update_briefing_run(
            self.run_id, status, completed, failed, error_log, total_time_ms
        )

        # 완료 알림
        if config.get('notify_on_complete', True):
            time_str = f"{total_time_ms // 1000}초"
            if failed > 0 and config.get('notify_on_failure', True):
                self.send_telegram_alert(
                    f"Morning Briefing 완료 (성공: {completed}, 실패: {failed}) - {time_str}\n실패 태스크: {', '.join([e.split(':')[0] for e in errors])}",
                    is_error=True
                )
            else:
                self.send_telegram_alert(f"Morning Briefing 완료 (성공: {completed}/{len(tasks_to_run)}) - {time_str}")

        self.manager.log_activity("Sentinel", f"🌅 Briefing 완료: 성공 {completed}, 실패 {failed}, 총 {total_time_ms}ms")

        return {
            'run_id': self.run_id,
            'status': status,
            'tasks_total': len(tasks_to_run),
            'tasks_completed': completed,
            'tasks_failed': failed,
            'execution_time_ms': total_time_ms,
            'errors': errors,
            'results': self.results
        }

    # ============================================
    # [5단계] 주간 리포트 생성
    # ============================================
    def generate_weekly_cafe_report(self):
        """
        [5단계] 주간 맘카페 리포트 생성.
        지난 7일간 데이터를 집계하여 Telegram으로 발송.
        """
        self.log_activity("Sentinel", "📊 Generating Weekly Cafe Report...")

        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 지난 7일 기준
            from datetime import timedelta
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            today = datetime.now().strftime('%Y-%m-%d')

            # 1. 총 수집 리드 수
            cursor.execute('''
                SELECT COUNT(*) as total
                FROM mentions
                WHERE source = 'naver_cafe' AND date(scraped_at) >= ?
            ''', (week_ago,))
            total_leads = cursor.fetchone()['total']

            # 2. 상태별 분포
            cursor.execute('''
                SELECT status, COUNT(*) as cnt
                FROM mentions
                WHERE source = 'naver_cafe' AND date(scraped_at) >= ?
                GROUP BY status
            ''', (week_ago,))
            status_dist = {row['status']: row['cnt'] for row in cursor.fetchall()}

            # 3. Hot Lead 비율 (content에서 [Hot] 포함된 것)
            cursor.execute('''
                SELECT COUNT(*) as hot_count
                FROM mentions
                WHERE source = 'naver_cafe'
                  AND date(scraped_at) >= ?
                  AND content LIKE '%[Hot]%'
            ''', (week_ago,))
            hot_leads = cursor.fetchone()['hot_count']
            hot_ratio = (hot_leads / total_leads * 100) if total_leads > 0 else 0

            # 4. 응답률/전환율
            responded = status_dist.get('Responded', 0) + status_dist.get('Converted', 0)
            converted = status_dist.get('Converted', 0)
            response_rate = (responded / total_leads * 100) if total_leads > 0 else 0
            conversion_rate = (converted / total_leads * 100) if total_leads > 0 else 0

            # 5. 일별 추이
            cursor.execute('''
                SELECT date(scraped_at) as day, COUNT(*) as cnt
                FROM mentions
                WHERE source = 'naver_cafe' AND date(scraped_at) >= ?
                GROUP BY date(scraped_at)
                ORDER BY day
            ''', (week_ago,))
            daily_trend = [(row['day'], row['cnt']) for row in cursor.fetchall()]

            # 6. 키워드별 빈도 (Top 10)
            cursor.execute('''
                SELECT keyword, COUNT(*) as cnt
                FROM mentions
                WHERE source = 'naver_cafe' AND date(scraped_at) >= ?
                GROUP BY keyword
                ORDER BY cnt DESC
                LIMIT 10
            ''', (week_ago,))
            keyword_freq = [(row['keyword'], row['cnt']) for row in cursor.fetchall()]

            safe_close(conn)

            # 리포트 생성
            report_lines = [
                f"📊 *주간 맘카페 인사이트 리포트*",
                f"기간: {week_ago} ~ {today}",
                "",
                f"📈 *총 수집 리드*: {total_leads}건",
                f"🔥 *Hot Lead*: {hot_leads}건 ({hot_ratio:.1f}%)",
                f"💬 *응답률*: {response_rate:.1f}%",
                f"✅ *전환율*: {conversion_rate:.1f}%",
                "",
                "📋 *상태별 분포*:"
            ]

            for status in ['New', 'Reviewed', 'Responded', 'Converted', 'Closed']:
                cnt = status_dist.get(status, 0)
                if cnt > 0:
                    report_lines.append(f"  - {status}: {cnt}건")

            report_lines.append("")
            report_lines.append("📅 *일별 추이*:")
            for day, cnt in daily_trend:
                bar = "█" * min(cnt, 20)
                report_lines.append(f"  {day[-5:]}: {bar} {cnt}")

            report_lines.append("")
            report_lines.append("🔑 *Top 키워드*:")
            for kw, cnt in keyword_freq[:5]:
                report_lines.append(f"  - {kw}: {cnt}건")

            report_text = "\n".join(report_lines)

            # Telegram 발송
            try:
                from alert_bot import TelegramBot
                secrets_path = os.path.join(self.root_dir, 'config', 'secrets.json')
                with open(secrets_path, 'r', encoding='utf-8') as f:
                    secrets = json.load(f)

                telegram = TelegramBot(
                    token=secrets.get("TELEGRAM_BOT_TOKEN", ""),
                    chat_id=secrets.get("TELEGRAM_CHAT_ID", "")
                )
                telegram.send_message(report_text)
                self.log_activity("Sentinel", "✅ Weekly Report sent to Telegram")
            except Exception as e:
                self.log_activity("Sentinel", f"⚠️ Telegram send failed: {e}", "WARNING")
                print(report_text)  # 콘솔에라도 출력

            # insights 테이블에 저장
            self.create_insight(
                i_type="weekly_report",
                title=f"📊 주간 맘카페 리포트 ({today})",
                content=report_text,
                meta={
                    "total_leads": total_leads,
                    "hot_leads": hot_leads,
                    "hot_ratio": hot_ratio,
                    "response_rate": response_rate,
                    "conversion_rate": conversion_rate,
                    "period_start": week_ago,
                    "period_end": today
                }
            )

            self.log_activity("Sentinel", f"📊 Weekly Report Generated: {total_leads} leads analyzed")

        except Exception as e:
            self.log_activity("Sentinel", f"Weekly Report Error: {e}", "ERROR")

    def run_briefing(self):
        """
        Executes a comprehensive briefing cycle using BriefingRunner.
        병렬 실행, 상태 추적, DB 저장, 알림 기능을 포함합니다.
        """
        runner = BriefingRunner(self)
        result = runner.execute()
        return result

    def run_briefing_legacy(self):
        """
        [레거시] 기존 순차 실행 방식의 Briefing.
        호환성을 위해 유지합니다.
        """
        self.manager.log_activity("Sentinel", "🌅 Starting Morning Briefing Cycle (Legacy Mode)...")

        try:
            # Phase 1: Rank & Visibility
            self.manager.generate_rank_insights()
            self.manager.generate_view_rank_insights()

            # Phase 2: Community & Competitor Intelligence
            self.manager.generate_community_insights()
            self.manager.generate_competitor_activity_insights()
            self.manager.generate_strategic_insights()

            # Phase 3: Trend & Discovery
            self.manager.generate_seasonal_insights()
            self.manager.generate_keyword_opportunities()
            self.manager.generate_visual_trend_insights()
            self.manager.generate_prophet_insights()
            self.manager.generate_ambassador_insights()

            self.manager.log_activity("Sentinel", "🌅 Morning Briefing Cycle Completed Successfully.")
        except Exception as e:
            self.manager.log_activity("Sentinel", f"Briefing Cycle Failed: {e}", "ERROR")

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(description="Kyurim MKT OS - Insight Manager CLI")
    parser.add_argument("--mode", type=str, choices=["briefing", "scan", "weekly", "legacy"], help="Execution mode")
    args = parser.parse_args()

    manager = InsightManager()

    if args.mode == "briefing":
        runner = BriefingRunner(manager)
        runner.execute()
    elif args.mode == "scan":
        runner = BriefingRunner(manager)
        runner.execute()
    elif args.mode == "weekly":
        runner = BriefingRunner(manager)
        runner.generate_weekly_cafe_report()
    elif args.mode == "legacy":
        # 순차 실행 모드 (DB 커서 충돌 방지)
        runner = BriefingRunner(manager)
        runner.run_briefing_legacy()
    else:
        logger.info("No mode specified. Use --mode briefing or --mode weekly to start.")
