import time
import schedule
import subprocess
import os
import sys
from datetime import datetime
from utils import ConfigManager, logger
from alert_bot import AlertSystem

# [Phase 5-1] 설정값 외부화
try:
    from config.app_settings import get_settings
    _app_settings = get_settings()
except ImportError:
    _app_settings = None

# [Phase 2.1] Event Bus Integration
try:
    from core.event_bus import publish_event, EventType
    HAS_EVENT_BUS = True
except ImportError:
    HAS_EVENT_BUS = False

# [Phase 2.3] Adaptive Scheduler Integration
try:
    from core.adaptive_scheduler import get_adaptive_scheduler
    HAS_ADAPTIVE_SCHEDULER = True
except ImportError:
    HAS_ADAPTIVE_SCHEDULER = False

# [Phase 4] Auto Rescan Handler
try:
    from core.auto_rescan_handler import initialize_auto_rescan
    HAS_AUTO_RESCAN = True
except ImportError:
    HAS_AUTO_RESCAN = False

# [Phase 4] Lead Reminder Scheduler
try:
    from marketing_bot_web.backend.services.lead_reminder_scheduler import run_lead_reminders
    HAS_LEAD_REMINDER = True
except ImportError:
    HAS_LEAD_REMINDER = False

# [Phase 4] Lead Status Automator
try:
    from marketing_bot_web.backend.services.lead_status_automator import run_status_transitions
    HAS_LEAD_AUTOMATOR = True
except ImportError:
    HAS_LEAD_AUTOMATOR = False

class SchedulerService:
    def __init__(self):
        self.config = ConfigManager()
        self.alert_system = AlertSystem()
        self.root_dir = self.config.root_dir

    def start(self):
        logger.info("⏰ Scheduler Service Started. Waiting for jobs...")
        self.alert_system.bot.send_message("⏰ Marketing OS v5.2 (Swarm+) Online.")

        # [Phase 4] Auto Rescan Handler 초기화
        if HAS_AUTO_RESCAN:
            try:
                initialize_auto_rescan()
                logger.info("🔄 [Phase 4] Auto Rescan Handler initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Auto Rescan Handler: {e}")
        
        # --- Adjusted Agent Schedules (v5.2 - Total War Staggered) ---
        
        # 1. Day Shift (Light/Mid)
        schedule.every(1).hours.do(self.job_sentinel) # 24h Watch (News/Blog)
        schedule.every().day.at("09:00").do(self.job_sniper) # Rank Check
        schedule.every().day.at("10:30").do(self.job_morning_briefing) # Briefing
        schedule.every().day.at("12:00").do(self.job_ambassador) # Influencer
        
        # 2. Strategy Shift (Mid) - Detailed Operations
        schedule.every().day.at("10:00").do(self.job_competitor)  # Competitor Deep Scan
        schedule.every().day.at("14:00").do(self.job_cafe_swarm)  # Mom Cafe / Community
        schedule.every().day.at("14:30").do(self.job_viral_hunter)  # Viral Hunter
        schedule.every().day.at("15:00").do(self.job_carrot)      # Carrot Market
        schedule.every().day.at("16:00").do(self.job_instagram)   # Instagram
        
        # 3. Night Shift (Heavy - Video Ops)
        schedule.every().day.at("18:30").do(self.job_youtube)
        schedule.every().day.at("21:00").do(self.job_sniper)
        schedule.every().day.at("21:30").do(self.job_tiktok)  # TikTok Hybrid Monitor
        
        # 4. Dawn Shift (Maximum Load - Deep Mining)
        schedule.every().day.at("03:00").do(self.job_pathfinder)

        # 5. Prophet (Trend Forecast)
        schedule.every().monday.at("09:30").do(self.job_prophet)
        schedule.every().thursday.at("09:30").do(self.job_prophet)
        schedule.every().sunday.at("09:30").do(self.job_prophet)
        
        # 6. Database Maintenance (02:00 - before heavy Pathfinder at 03:00)
        schedule.every().day.at("02:00").do(self.job_db_backup)

        # 7. [Phase 1-3] Notification Trigger (30분마다)
        schedule.every(30).minutes.do(self.job_notification_check)

        # 8. [Phase 4] Hot Lead Reminder (4시간마다)
        schedule.every(4).hours.do(self.job_lead_reminder)

        # 9. [Phase 4] Lead Status Automator (매일 06:00)
        schedule.every().day.at("06:00").do(self.job_lead_status_automation)

        logger.info("   ✅ Agents Deployed: Total War Schedule (Staggered Mode).")
        
        while True:
            schedule.run_pending()
            time.sleep(60)

    # --- STATE TRACKING ---
    def _update_state(self, job_name, time_str):
        import json
        state_file = os.path.join(self.root_dir, 'db', 'scheduler_state.json')
        data = {}
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.debug(f"Failed to read scheduler state: {e}")
        
        today = datetime.now().strftime("%Y-%m-%d")
        data[time_str] = today
        
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save scheduler state: {e}")

    # --- JOB DEFINITIONS ---

    def job_db_backup(self):
        """Database Maintenance: Backup, Integrity Check, WAL (02:00)"""
        logger.info("💾 [DB Backup] Starting daily maintenance...")
        try:
            from db_backup import DatabaseBackup
            backup = DatabaseBackup()
            results = backup.run_daily_maintenance()
            if results.get('backup_path'):
                logger.info("   ✅ Backup created successfully")
            self._update_state("db_backup", "02:00")
        except Exception as e:
            logger.error(f"DB Backup Failed: {e}")

    def job_sentinel(self):
        """🛡️ Agent Sentinel: Real-time Brand & Social Watch (1h)"""
        logger.info("🛡️ [Sentinel] Starting 24h Brand Watch...")
        try:
            from social_monitor import SocialMonitor
            monitor = SocialMonitor()
            result = monitor.run_cycle()
            logger.info(f"   📡 Social Scan: {result}")
            self._run_script("scraper_news.py", "규림한의원")
        except Exception as e:
            logger.error(f"Sentinel Failed: {e}")

    def job_sniper(self):
        """🔫 Agent Sniper: View & Place Rank (09:00 / 21:00)"""
        logger.info("🔫 [Sniper] Starting Rank Patrol...")
        try:
            self._run_script("scraper_view_search.py", "")
            self._run_script("scraper_naver_place.py", "")
            logger.info("🔫 [Sniper] Mission Complete.")
            h = datetime.now().hour
            slot = "09:00" if h < 14 else "21:00"
            self._update_state("sniper", slot)
        except Exception as e:
            logger.error(f"Sniper Failed: {e}")

    def job_competitor(self):
        """⚔️ Agent Tactician Part 1: Competitor Analysis (10:00)"""
        logger.info("⚔️ [Competitor] Starting Deep Scan...")
        try:
            self._run_script("scraper_competitor.py", "")
            self._update_state("competitor", "10:00")
        except Exception as e:
            logger.error(f"Competitor Job Failed: {e}")

    def job_cafe_swarm(self):
        """🐝 Agent Tactician Part 2: Cafe Swarm (14:00)"""
        logger.info("🐝 [Cafe Swarm] Launching Invasion...")
        try:
            self.alert_system.bot.send_message("⚔️ [Tactician] 맘카페/커뮤니티 침투 조사를 시작합니다.")
            swarm_script = os.path.join(self.root_dir, 'run_cafe_swarm.py')
            log_dir = os.path.join(self.root_dir, 'logs')
            if not os.path.exists(log_dir): os.makedirs(log_dir)
            with open(os.path.join(log_dir, 'swarm_execution.log'), 'a', encoding='utf-8') as log_f:
                subprocess.Popen([sys.executable, swarm_script], stdout=log_f, stderr=log_f)
            self._update_state("cafe_swarm", "14:00")
        except Exception as e:
            logger.error(f"Cafe Swarm Failed: {e}")

    def job_carrot(self):
        """🥕 Agent Tactician Part 3: Carrot Market (15:00)"""
        logger.info("🥕 [Carrot] Starting Neighborhood Watch...")
        try:
            self.alert_system.bot.send_message("⚔️ [Tactician] 당근마켓 동네생활 모니터링을 시작합니다.")
            script_name = "carrot_farmer.py"
            _timeout = _app_settings.subprocess_timeout if _app_settings else 600
            if not os.path.exists(os.path.join(self.root_dir, 'scrapers', script_name)):
                cmd = [sys.executable, os.path.join(self.root_dir, script_name)]
                subprocess.run(cmd, check=True, timeout=_timeout)
            else:
                self._run_script(script_name, "")
            self._update_state("carrot", "15:00")
        except Exception as e:
            logger.error(f"Carrot Job Failed: {e}")

    def job_instagram(self):
        """📸 Agent Tactician Part 4: Instagram (16:00) - LIMITED MODE"""
        logger.info("📸 [Instagram] Starting Visual Scan (LIMITED MODE - Google Bypass)...")
        try:
            self.alert_system.bot.send_message("📸 [Instagram] 조사 시작 (제한 모드: 3-7일 지연 데이터)")
            self._run_script("scraper_instagram.py", "")
            self._update_state("instagram", "16:00")
        except Exception as e:
            logger.error(f"Instagram Job Failed: {e}")

    def job_pathfinder(self):
        """🔭 Agent Pathfinder: Explores new keywords (3 AM)"""
        logger.info("🔭 [Pathfinder] Starting Deep Space Exploration...")
        try:
            from pathfinder import Pathfinder
            pf = Pathfinder()
            seeds = ["청주 다이어트", "청주 한의원", "청주 교통사고", "청주 야간진료"]
            for seed in seeds:
                pf.find_opportunities(seed)
            logger.info("🔭 [Pathfinder] Mission Complete.")
            self._update_state("pathfinder", "03:00")
        except Exception as e:
            logger.error(f"Pathfinder Failed: {e}")

    def job_morning_briefing(self):
        """🌅 Secretary: Morning Briefing (10:30 AM)"""
        logger.info("🌅 Starting Morning Briefing Routine (10:30)...")
        try:
            self._run_script("scraper_news.py", "청주 독감 청주 날씨 청주 교통")
            self.alert_system.check_alerts()
            self.alert_system.bot.send_message("🌅 [Morning Official] 원장님, 아침 브리핑 리포트가 대시보드에 준비되었습니다.")
            self._update_state("morning", "10:30")
        except Exception as e:
            logger.error(f"Morning Job Failed: {e}")

    def job_ambassador(self):
        """🤝 Ambassador: Influencer Scout (12:00 PM)"""
        logger.info("🤝 [Ambassador] Scouting Local Influencers...")
        try:
            from ambassador import TheAmbassador
            amb = TheAmbassador()
            results = amb.scout_and_vet(None)
            if results:
                self.alert_system.bot.send_message(f"🤝 [Ambassador] 오늘 발견한 인플루언서 {len(results)}명 (대시보드 확인)")
            self._update_state("ambassador", "12:00")
        except Exception as e:
            logger.error(f"Ambassador Failed: {e}")

    def job_prophet(self):
        """🔮 Prophet: Trend Forecast (Mon/Thu/Sun)"""
        logger.info("🔮 [Prophet] Forecasting Trends...")
        try:
            from prophet import TheProphet
            p = TheProphet()
            p.predict_next_week()
            self.alert_system.bot.send_message("🔮 [Prophet] 주간 트렌드 예측 보고서가 생성되었습니다.")
            self._update_state("prophet", "09:30")
        except Exception as e:
            logger.error(f"Prophet Failed: {e}")

    def job_youtube(self):
        """📺 YouTube Sentinel (18:30)"""
        logger.info("📺 [YouTube] Starting Video Ops...")
        try:
            self._run_script("scraper_youtube.py", "")
            self.alert_system.bot.send_message("📺 [YouTube] 유튜브 리뷰/댓글 전수 감시 완료.")
            self._update_state("youtube", "18:30")
        except Exception as e:
            logger.error(f"YouTube Job Failed: {e}")

    def job_tiktok(self):
        """🎵 TikTok Hybrid Monitor (21:30) - ACTIVE"""
        logger.info("🎵 [TikTok] Starting Hybrid Monitor (Creative Center + API)...")
        try:
            self.alert_system.bot.send_message("🎵 [TikTok] 트렌드 모니터링을 시작합니다 (하이브리드 모드)")
            self._run_script("scraper_tiktok_monitor.py", "")
            logger.info("🎵 [TikTok] Hybrid Monitor Complete.")
            self._update_state("tiktok", "21:30")
        except Exception as e:
            logger.error(f"TikTok Job Failed: {e}")

    def job_viral_hunter(self):
        """🎯 Viral Hunter: 바이럴 마케팅 타겟 발굴 (14:30)"""
        logger.info("🎯 [Viral Hunter] Starting Target Discovery...")
        try:
            self.alert_system.bot.send_message("🎯 [Viral Hunter] 바이럴 침투 타겟 스캔을 시작합니다.")
            # viral_hunter.py --scan --limit-keywords 10
            script_path = os.path.join(self.root_dir, 'viral_hunter.py')
            cmd = [sys.executable, script_path, "--scan"]
            _timeout = _app_settings.subprocess_timeout if _app_settings else 600
            subprocess.run(cmd, check=True, timeout=_timeout)
            logger.info("🎯 [Viral Hunter] Target Discovery Complete.")
            self._update_state("viral_hunter", "14:30")
        except Exception as e:
            logger.error(f"Viral Hunter Job Failed: {e}")

    def job_notification_check(self):
        """🔔 [Phase 1-3] Notification Check: 알림 트리거 체크 (30분마다)"""
        logger.info("🔔 [Notification Check] Running notification triggers...")
        try:
            import asyncio
            from marketing_bot_web.backend.services.notification_trigger import run_notification_checks

            # asyncio.run()을 사용하여 비동기 함수 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(run_notification_checks())
                total_alerts = sum(len(alerts) for alerts in result.values())
                if total_alerts > 0:
                    logger.info(f"🔔 [Notification Check] {total_alerts} alerts sent.")
                else:
                    logger.info("🔔 [Notification Check] No alerts triggered.")
            finally:
                loop.close()
        except ImportError as e:
            logger.warning(f"Notification trigger module not available: {e}")
        except Exception as e:
            logger.error(f"Notification check failed: {e}")

    def job_lead_reminder(self):
        """🔔 [Phase 4] Hot Lead Reminder: 골든타임 재알림 (4시간마다)"""
        logger.info("🔔 [Lead Reminder] Running Hot Lead reminders...")
        try:
            if not HAS_LEAD_REMINDER:
                logger.warning("Lead Reminder module not available")
                return

            result = run_lead_reminders()
            sent = result.get('sent', 0)
            failed = result.get('failed', 0)

            if sent > 0:
                logger.info(f"🔔 [Lead Reminder] {sent} reminders sent, {failed} failed.")
                self.alert_system.bot.send_message(
                    f"🔔 [골든타임] Hot Lead 재알림 {sent}건 발송 완료"
                )
            else:
                logger.info("🔔 [Lead Reminder] No pending reminders.")

        except Exception as e:
            logger.error(f"Lead Reminder failed: {e}")

    def job_lead_status_automation(self):
        """🔄 [Phase 4] Lead Status Automation: 리드 상태 자동 전이 (매일 06:00)"""
        logger.info("🔄 [Lead Status] Running automatic status transitions...")
        try:
            if not HAS_LEAD_AUTOMATOR:
                logger.warning("Lead Status Automator module not available")
                return

            result = run_status_transitions(dry_run=False)
            total = result.get('total_transitioned', 0)

            if total > 0:
                logger.info(f"🔄 [Lead Status] {total} leads transitioned.")
                self.alert_system.bot.send_message(
                    f"🔄 [리드 관리] {total}건 상태 자동 전이 완료"
                )

                # 상세 로그
                for rule_key, count in result.get('by_rule', {}).items():
                    if count > 0:
                        logger.info(f"   - {rule_key}: {count}건")
            else:
                logger.info("🔄 [Lead Status] No transitions needed.")

            self._update_state("lead_status_automation", "06:00")

        except Exception as e:
            logger.error(f"Lead Status Automation failed: {e}")

    def _run_script(self, script_name, args=""):
        script_path = os.path.join(self.root_dir, 'scrapers', script_name)
        cmd = [sys.executable, script_path] + args.split()
        start_time = datetime.now()
        _timeout = _app_settings.subprocess_timeout if _app_settings else 600

        try:
            subprocess.run(cmd, check=True, timeout=_timeout)
            duration = (datetime.now() - start_time).total_seconds()

            # [Phase 2.1] 스케줄 실행 성공 이벤트
            if HAS_EVENT_BUS:
                try:
                    publish_event(
                        EventType.SCHEDULE_EXECUTED,
                        {
                            "script": script_name,
                            "args": args,
                            "duration_seconds": duration,
                            "status": "success"
                        },
                        source="scheduler"
                    )
                except Exception:
                    pass

            # [Phase 2.3] Adaptive Scheduler 메트릭 기록
            if HAS_ADAPTIVE_SCHEDULER:
                try:
                    scheduler = get_adaptive_scheduler()
                    scheduler.record_execution(script_name, "success", duration)
                except Exception:
                    pass

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Script {script_name} TIMED OUT (killed after 10m).")
            self._publish_schedule_failed(script_name, "timeout", start_time)
            self._record_adaptive_failure(script_name, "timeout", duration)

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Script {script_name} failed: {e}")
            self._publish_schedule_failed(script_name, str(e), start_time)
            self._record_adaptive_failure(script_name, "failed", duration)

    def _publish_schedule_failed(self, script_name: str, error: str, start_time: datetime):
        """[Phase 2.1] 스케줄 실행 실패 이벤트 발행"""
        if not HAS_EVENT_BUS:
            return

        try:
            duration = (datetime.now() - start_time).total_seconds()
            publish_event(
                EventType.SCHEDULE_FAILED,
                {
                    "script": script_name,
                    "error": error[:200],
                    "duration_seconds": duration,
                    "status": "failed"
                },
                source="scheduler"
            )
        except Exception:
            pass

    def _record_adaptive_failure(self, script_name: str, status: str, duration: float):
        """[Phase 2.3] Adaptive Scheduler 실패 기록"""
        if not HAS_ADAPTIVE_SCHEDULER:
            return

        try:
            scheduler = get_adaptive_scheduler()
            scheduler.record_execution(script_name, status, duration)
        except Exception:
            pass

        
if __name__ == "__main__":
    service = SchedulerService()
    try:
        service.start()
    except KeyboardInterrupt:
        logger.info("Scheduler User Cancelled")
