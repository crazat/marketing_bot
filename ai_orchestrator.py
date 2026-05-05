"""
AI Orchestrator Module for Marketing Bot.

This module serves as the central command router for the marketing bot system.
It uses LLM to classify user intents and dispatches commands to appropriate
scrapers, analyzers, and content generators.

Key Features:
    - Intent classification with retry logic
    - Tool dispatch (13 available tools)
    - Database status context fetching
    - Script execution management

Classes:
    AIOrchestrator: Main orchestrator class for handling user commands.

Example:
    >>> orchestrator = AIOrchestrator()
    >>> result = orchestrator.process_command("분석해줘 규림한의원")
    >>> print(result['content'])
"""
import os
import sys
import json
import pandas as pd
import subprocess
from datetime import datetime
import glob
import requests

import sqlite3
from utils import ConfigManager, logger
from retry_helper import retry_with_backoff, with_fallback
from task_manager import TaskManager

# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))
from services.ai_client import ai_generate, ai_generate_json

class AIOrchestrator:
    def __init__(self):
        self.config = ConfigManager()
        self.root_dir = self.config.root_dir
        self.db_path = self.config.db_path
        self.task_manager = TaskManager()
        ai_disabled = os.getenv("MARKETING_BOT_DISABLE_AI", os.getenv("DISABLE_AI", "false")).lower()
        tests_disable_ai = (
            "pytest" in sys.modules
            and os.getenv("MARKETING_BOT_ENABLE_AI_IN_TESTS", "false").lower() != "true"
        )
        self.has_llm = bool(self.config.get_api_key("GEMINI_API_KEY")) and not tests_disable_ai and ai_disabled not in {
            "1",
            "true",
            "yes",
            "on",
        }

    # _load_api_key removed (using centralized ai_client)
        
    def _get_status_context(self):
        """Fetches real-time status from DB and filesystem."""
        context = "No Data"
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. CRM Leads by Channel (Today & Total)
                sources = {
                    "Karrot Market": "karrot",
                    "YouTube Comments": "youtube_comment",
                    "Instagram": "instagram_hashtag",
                    "Google News": "google_news_rss"
                }
                crm_status = []
                for name, key in sources.items():
                    cursor.execute("SELECT count(*) FROM mentions WHERE source=? AND status='New'", (key,))
                    cnt = cursor.fetchone()[0]
                    if cnt > 0: crm_status.append(f"- {name}: {cnt} items")
                
                crm_text = ", ".join(crm_status) if crm_status else "No new leads."

                # 2. Naver Place Rank (Top 3 Keywords)
                cursor.execute("SELECT max(date) FROM rank_history")
                latest_date = cursor.fetchone()[0]
                
                rank_info = "No Rank Data"
                if latest_date:
                    cursor.execute("SELECT keyword, rank FROM rank_history WHERE date=? AND rank > 0 ORDER BY rank ASC LIMIT 3", (latest_date,))
                    rows = cursor.fetchall()
                    if rows:
                        ranks = [f"{r[0]}({r[1]}위)" for r in rows]
                        rank_info = ", ".join(ranks)
                    else:
                        rank_info = "All keywords outside Top 50"

            # 3. Blog Drafts Count (Filesystem)
            draft_dir = os.path.join(self.root_dir, 'drafts_premium')
            draft_count = len(glob.glob(os.path.join(draft_dir, "*.md"))) if os.path.exists(draft_dir) else 0

            context = f"""
            [🏥 Clinic Status Report]
            1. 🎯 CRM (New Leads): {crm_text}
            2. 🥇 Naver Rank ({latest_date}): {rank_info}
            3. 📝 Blog Drafts: {draft_count} ready to post.
            """
        except Exception as e: 
            logger.error("Error fetching status context", exc_info=True)
            context = f"Error fetching status: {e}"
        return context

    def process_command(self, user_input):
        if not self.has_llm: 
            return {"type": "text", "content": "❌ AI System Offline."}

        # 1. Intent Classification with Context
        print(f"AI Processing: {user_input}")
        status_ctx = self._get_status_context()
        intent_data = self._classify_intent(user_input, status_ctx)
        
        if not intent_data:
            return {"type": "text", "content": "죄송해요, 어떤 작업을 원하시는지 잘 모르겠어요."}
        
        tool = intent_data.get("tool")
        args = intent_data.get("args")
        if args is None: args = ""
        reason = intent_data.get("reason", "")
        
        # 2. Execution & Structured Response Construction
        # Default response wrapper
        response_obj = {
            "type": "text",
            "content": f"🤖 **AI Co-pilot**: {reason}",
            "meta": {"title": tool, "timestamp": datetime.now().strftime("%H:%M:%S")}
        }
        
        try:
            if tool == "status_report":
                response_obj["content"] = f"📊 **병원 현황 리포트**\n{status_ctx}"
                # In future, can make this a 'dashboard' type
                
            elif tool == "smart_research":
                # For now keeping text, but marked as text
                res = self._run_script("scraper_news.py", args)
                response_obj["content"] += res
                
            elif tool == "competitor_analysis":
                # Check for Full Census Request
                if not args or args.upper() == "ALL" or "전체" in args:
                    targets_cfg = self.config.load_targets()
                    competitors = [t['name'] for t in targets_cfg.get('targets', []) if '규림' not in t['name']]
                    
                    if not competitors:
                        response_obj["content"] = "⚠️ 설정(targets.json)에 등록된 경쟁사가 없습니다."
                    else:
                        # [Parallel Execution] Dispatch tasks via TaskManager
                        task_ids = []
                        for comp in competitors:
                            # Use TaskManager to run in background
                            tid = self.task_manager.run_task(
                                f"Competitor Scan: {comp}", 
                                ["python", os.path.join(self.root_dir, "scrapers", "scraper_competitor.py"), comp]
                            )
                            task_ids.append(tid)
                        
                        response_obj["content"] = f"🚀 **경쟁사 전수 조사(Parallel Mode)** 시작!\n"
                        response_obj["content"] += f"총 {len(task_ids)}개의 정찰 봇(Scout Bot)이 동시에 파견되었습니다.\n"
                        response_obj["content"] += f"작업 ID: {', '.join(task_ids)}\n"
                        response_obj["content"] += "잠시 후 대시보드에서 완료 알림을 확인하세요."
                        
                        response_obj["type"] = "text"
                else:
                    # Single Target
                    res = self._run_script("scraper_competitor.py", args)
                    response_obj["content"] += res
                    
                    # Check for latest report to show in Canvas
                    r_dir = os.path.join(self.root_dir, 'reports_competitor')
                    if os.path.exists(r_dir):
                        latest = sorted(glob.glob(os.path.join(r_dir, "*.md")), key=os.path.getmtime, reverse=True)
                        if latest:
                            response_obj["type"] = "report_viewer"
                            response_obj["data"] = {"file_path": latest[0]}
                            response_obj["meta"]["title"] = f"Competitor Analysis: {args}"

            elif tool == "blog_generation":
                raw_text = self._run_blog_gen(args)
                
                # Check for error
                if str(raw_text).startswith("Gen Error"):
                     response_obj["content"] = raw_text
                else:
                    # Save to file
                    # Sanitize filename
                    safe_args = "".join([c for c in args if c.isalnum() or c in (' ','_')]).strip().replace(' ','_')
                    filename = f"Draft_{datetime.now().strftime('%Y%m%d_%H%M')}_{safe_args[:20]}.md"
                    save_path = os.path.join(self.root_dir, "reports_blog", filename)
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(raw_text)
                    
                    # Also index to Librarian (Optional but good)
                    try:
                        from librarian import Librarian
                        lib = Librarian()
                        lib.index_report(save_path, "blog_draft")
                    except Exception:
                        pass
                        
                    response_obj["type"] = "report_viewer"
                    response_obj["data"] = {"file_path": save_path}
                    response_obj["meta"]["title"] = f"📝 Blog Draft: {args}"
                    response_obj["content"] = "블로그 초안이 생성되었습니다. 우측 캔버스를 확인하세요."

            elif tool == "keyword_mining":
                try:
                    from pathfinder import Pathfinder
                    pf = Pathfinder()
                    df = pf.find_opportunities(args)
                    
                    # Create a scatter chart for visualization
                    # X=Competition, Y=Volume, Color=Tag
                    chart_data = {
                        "dataset": df.to_dict('records'),
                        "x_col": "competition",
                        "y_col": "volume",
                        "color_col": "tag",
                        "chart_type": "scatter", 
                        "summary": "우측 상단(볼륨 높고 경쟁 낮음)에 있는 키워드가 '황금 키워드'입니다."
                    }
                    
                    response_obj["type"] = "chart" 
                    response_obj["content"] = "키워드 발굴 완료! 'Golden Key'를 공략하세요."
                    response_obj["data"] = chart_data
                    response_obj["meta"]["title"] = f"Opportunity Map: {args}"
                    response_obj["type"] = "dataframe"
                    response_obj["data"] = {"rows": df.to_dict('records')}
                except Exception as e:
                    response_obj["content"] = f"Pathfinder Error: {e}"

            elif tool == "karrot_scan":
                try:
                    from carrot_farmer import CarrotFarmer
                    farmer = CarrotFarmer()
                    results = farmer.harvest_and_reply(args)
                    
                    # Convert results to a simple dataframe for display
                    if results:
                        response_obj["type"] = "dataframe"
                        response_obj["data"] = {"rows": results}
                        response_obj["meta"]["title"] = f"🥕 Carrot Harvest: {args}"
                        response_obj["content"] = "당근마켓에서 질문글을 발견하고 답글 초안을 작성했습니다."
                    else:
                        response_obj["content"] = "당근마켓에서 관련 질문을 찾지 못했습니다."
                except Exception as e:
                    response_obj["content"] = f"Carrot Error: {e}"

            elif tool == "video_script":
                try:
                    from director import TheDirector
                    director = TheDirector()
                    script_content = director.action(args)
                    
                    response_obj["content"] = script_content
                except Exception as e:
                    response_obj["content"] = f"Director Error: {e}"

            elif tool == "trend_forecast":
                try:
                    from prophet import TheProphet
                    p = TheProphet()
                    forecast = p.predict_next_week()
                    
                    # Convert to dataframe for display
                    if forecast.get('rising_trends'):
                        df = pd.DataFrame(forecast['rising_trends'])
                        response_obj["type"] = "dataframe"
                        response_obj["data"] = {"rows": df.to_dict('records')}
                        response_obj["meta"]["title"] = f"🔮 Prophet Forecast: {forecast['target_period']}"
                        response_obj["content"] = "다음 주 트렌드 예측 보고서입니다. 미리 준비하세요."
                    else:
                        response_obj["content"] = "에측할 데이터가 부족합니다."
                except Exception as e:
                    response_obj["content"] = f"Prophet Error: {e}"

            elif tool == "influencer_scout":
                try:
                    from ambassador import TheAmbassador
                    amb = TheAmbassador()
                    # Args = Location (e.g. "성안길", "현대백화점") or None
                    target_loc = args if args and "청주" not in args else None # Simple heuristic
                    results = amb.scout_and_vet(target_loc)
                    
                    formatted_text = f"**🕵️ Surgical Scout Report**\n(Target: {target_loc if target_loc else 'Random Hotplace'})\n\n"
                    
                    if not results:
                        formatted_text += "진성 인플루언서를 찾지 못했습니다. (기준 미달)"
                    
                    for r in results:
                        # Handle missing stats from Google Search Scout
                        f_count = r.get('followers')
                        if isinstance(f_count, int):
                            eng = ((r.get('avg_likes',0) + r.get('avg_comments',0)) / f_count) * 100
                            valid_txt = f"| Eng: {eng:.1f}%"
                        else:
                            valid_txt = "(Stats Unavailable)"
                            
                        formatted_text += f"**✅ {r['handle']}** {valid_txt}\n"
                        formatted_text += f"> *Source: Google*\n"
                        formatted_text += f"> *Snippet: {r.get('recent_content', 'N/A')}*\n\n"
                        formatted_text += f"**💌 Draft DM**:\n```text\n{r['draft_dm']}\n```\n---\n"
                    
                    response_obj["content"] = formatted_text
                    response_obj["meta"]["title"] = "🤝 Vetted Ambassador List"
                    
                except Exception as e:
                    response_obj["content"] = f"Ambassador Error: {e}"

            elif tool == "naver_rank":
                # Run script
                self._run_script("scraper_naver_place.py")
                
                # Fetch Data from DB for Chart
                with sqlite3.connect(self.db_path) as conn:
                    df = pd.read_sql_query("SELECT * FROM rank_history WHERE target_name LIKE '%Naver%' ORDER BY checked_at DESC", conn)
                
                if not df.empty:
                    response_obj["type"] = "chart"
                    response_obj["data"] = {
                        "chart_type": "line",
                        "dataset": df.to_dict('records'),
                        "x_col": "date",
                        "y_col": "rank",
                        "color_col": "keyword",
                        "summary": "최신 네이버 플레이스 순위 변동 그래프입니다."
                    }
                    response_obj["meta"]["title"] = "Naver Place Ranking"
                    response_obj["content"] = "네이버 순위 점검을 완료했습니다. 우측 그래프를 확인하세요."
                else:
                    response_obj["content"] += "\n(데이터가 충분하지 않아 그래프를 그릴 수 없습니다.)"

            elif tool == "google_seo":
                res = self._run_script("scraper_google.py", args)
                response_obj["content"] += res
                
            elif tool == "news_scan":
                res = self._run_script("scraper_news.py", args)
                response_obj["content"] += res
                
            elif tool == "community_scan":
                 # [Parallel Execution] for Cafes
                 targets_cfg = self.config.load_targets()
                 cafes = targets_cfg.get('cafes', [])
                 
                 # If no cafes in config, check if user provided args as a single cafe?
                 # Or if args is "ALL", do all. 
                 # Current logic was: _run_script("cafe_spy.py", args) which handled list internally if no args.
                 # But cafe_spy.py internal loop is sequential.
                 # To make it parallel, we must iterate here and call cafe_spy.py per cafe.
                 
                 if not cafes:
                     # Fallback to single run if config missing
                     res = self._run_script("cafe_spy.py", args)
                     response_obj["content"] += res
                 else:
                     task_ids = []
                     # If args is specific cafe, filter.
                     target_list = [c for c in cafes if args in c] if args and "전체" not in args else cafes
                     
                     for cafe in target_list:
                         tid = self.task_manager.run_task(
                            f"Cafe Spy: {cafe}",
                            ["python", os.path.join(self.root_dir, "scrapers", "cafe_spy.py"), "--cafe_name", cafe]
                         )
                         task_ids.append(tid)
                         
                     response_obj["content"] = f"🕵️ **맘카페 잠입 수사(Parallel Mode)** 시작!\n"
                     response_obj["content"] += f"총 {len(task_ids)}명의 스파이(Spy Agent)가 각 카페({', '.join(target_list)})로 잠입했습니다.\n"
                     response_obj["content"] += "작업이 완료되면 보고서가 생성됩니다."
                 
                 # Show latest cafe report (optional, maybe not relevant if async just started)
                 # r_dir = os.path.join(self.root_dir, 'reports_cafe') ...

            elif tool == "strategy_report":
                try:
                    # Use AgentCrew to write a strategic report
                    from agent_crew import AgentCrew
                    crew = AgentCrew()
                    
                    prompt = f"""
                    Write a 'Competitor Counter-Strategy Report' (Markdown).
                    Target Subject: {args}
                    
                    Structure:
                    # 🛡️ Counter-Strategy Report: {args}
                    ## 1. Situation Analysis
                    (Analyze why this is a threat/opportunity based on the keyword)
                    
                    ## 2. Our Core Message (USP)
                    (How Kyurim Clinic should position itself)
                    
                    ## 3. Action Plan
                    - Blog Topic: ...
                    - Instagram Visual: ...
                    - Event Idea: ...
                    
                    ## 4. Expected Outcome
                    """
                    
                    report_content = crew.writer.generate(prompt)
                    
                    # Save Report
                    filename = f"Strategy_{datetime.now().strftime('%Y%m%d_%H%M')}_{args[:10]}.md"
                    save_path = os.path.join(self.root_dir, "reports_strategy", filename)
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(report_content)
                        
                    response_obj["type"] = "report_viewer"
                    response_obj["data"] = {"file_path": save_path}
                    response_obj["meta"]["title"] = f"📑 Strategy: {args}"
                    response_obj["content"] = "요청하신 대응 전략 보고서를 작성했습니다."
                    
                except Exception as e:
                    response_obj["content"] = f"Strategy Gen Failed: {e}"

            else:
                response_obj["content"] = f"알 수 없는 도구 요청입니다: {tool}"
                
            return response_obj
            
        except Exception as e:
            logger.error(f"Error executing tool '{tool}'", exc_info=True)
            return {"type": "text", "content": f"Error executing tool '{tool}': {e}"}

    def _classify_intent(self, user_input, status_ctx):
        prompt = f"""
        You are the 'OS Router' for a marketing dashboard.
        Current System Status: {status_ctx}
        
        Map the user's request to one of the following tools.
        
        [Tools]
        0. status_report (args: none) -> for "how is it going?", "current status", "summary".
        1. competitor_analysis (args: competitor_name) -> for "analyze X", "spy on X".
        2. blog_generation (args: topic) -> for "write blog about X".
        3. naver_rank (args: none) -> for "check ranking", "refresh rank".
        4. google_seo (args: keywords) -> for "google rank".
        5. news_scan (args: keywords) -> for "news about X".
        6. community_scan (args: keywords) -> for "mom cafe scan".
        7. keyword_mining (args: seed_keyword) -> for "find keywords", "blue ocean", "recommend keywords".
        8. karrot_scan (args: keyword) -> for "karrot market", "neighborhood", "danggeun".
        9. video_script (args: topic) -> for "video script", "reels", "shorts", "youtube".
        10. trend_forecast (args: none) -> for "predict trend", "future", "next week", "forecast".
        11. influencer_scout (args: potential_niche) -> for "influencer", "ambassador", "scout", "DM".
        12. strategy_report (args: topic) -> for "strategy report", "counter strategy", "report study", "대응 전략".
        
        [User Input]: "{user_input}"
        
        [Output Format JSON]:
        {{
            "tool": "tool_name",
            "args": "extracted_argument_string",
            "reason": "Short polite confirmation in Korean."
        }}
        """
        try:
            result = ai_generate_json(prompt, temperature=0.3)
            if result:
                return result
            logger.error("Failed to parse intent from AI response")
            return None
        except Exception as e:
            logger.error(f"Router Error: {e}")
            return None

    def _run_script(self, script_name, args=None):
        script_path = os.path.join(self.root_dir, "scrapers", script_name)
        cmd = ["python", script_path]
        if args: 
            # Handle args logic relevant to specific scripts if needed
            # Only split if it's a string
            if isinstance(args, str):
                cmd.extend(args.split())
            elif isinstance(args, list):
                cmd.extend(args) 
            
        try:
            # Explicitly merge stderr to stdout if you want to see everything, 
            # OR keep separate to filter warnings.
            # Here we capture both but rely on returncode.
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
            
            if result.returncode == 0:
                # Summarize output - take last 50 lines to ensure all found items are visible
                lines = result.stdout.strip().split('\n')
                summary = "\n".join(lines[-50:]) if len(lines) > 50 else result.stdout
                
                # [Robustness] Warning Check: Sometimes script exits 0 but prints stack trace
                if "Traceback" in summary or "Error:" in summary:
                     logger.warning(f"Script {script_name} exit 0 but output contains errors.")
                
                return f"\n✅ 실행 완료:\n```\n{summary}\n```"
            else:
                stderr_val = result.stderr if result.stderr else ""
                
                # If stderr is empty, check stdout for clues
                if not stderr_val.strip():
                     stderr_val = f"No Stderr. Stdout:\n{result.stdout[-500:]}"
                
                # Filter out FutureWarnings from stderr if they are the only "error"
                # Many libraries emit these to stderr
                err_lines = [line for line in stderr_val.split('\n') if "FutureWarning" not in line and line.strip()]
                
                if not err_lines: 
                    # It was just warnings, but return code was non-zero? That's rare.
                    # Or maybe return code was 0 but we fell here? No.
                    pass

                logger.error(f"Script {script_name} failed with code {result.returncode}")
                return f"\n❌ 오류 발생 (Exit Code {result.returncode}):\n{stderr_val}"
        except subprocess.TimeoutExpired:
             logger.error(f"Script {script_name} timed out.")
             return f"\n⏳ 실행 시간 초과 (Timeout 300s)"
        except Exception as e:
            return f"\nExecution Failed: {e}"

    def _run_blog_gen(self, topic):
        # Call the content generator directly
        try:
            from content_studio_v3_llm import LLMContentGenerator
            gen = LLMContentGenerator()
            res = gen.generate_premium_blog(topic)
            return res
        except Exception as e:
            return f"Gen Error: {e}"
