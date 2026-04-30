import time
import subprocess
import sys
import os
import json
import logging
from datetime import datetime

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Logging Setup
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'scheduler.log'),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    encoding='utf-8'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

class ChronosScheduler:
    """
    Master Timeline Scheduler for Kyurim MKT OS.
    Aligns perfectly with Dashboard Ultra's Chronos Timeline.
    """
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.state_file = os.path.join(self.root_dir, 'db', 'scheduler_state.json')
        self.python_exe = sys.executable
        
        # DEFINITION: Must match Dashboard Ultra Timeline
        self.timeline = [
            {"time": "08:10", "label": "Reputation Sentinel", "cmd": "sentinel_agent.py", "type": "daemon"},
            {"time": "09:00", "label": "Place Sniper", "cmd": "scrapers/scraper_naver_place.py", "type": "script"},
            {"time": "10:30", "label": "Briefing", "cmd": "insight_manager.py", "args": ["--mode", "briefing"], "type": "script"},
            {"time": "12:00", "label": "Ambassador", "cmd": "ambassador_v2.py", "type": "script"},
            {"time": "14:00", "label": "Cafe Swarm", "cmd": "run_cafe_swarm.py", "type": "script"},
            {"time": "15:00", "label": "Carrot Farm", "cmd": "carrot_farmer.py", "type": "script"},
            {"time": "16:00", "label": "Instagram", "cmd": "scrapers/scraper_instagram.py", "type": "script"},
            {"time": "18:30", "label": "YouTube", "cmd": "scrapers/scraper_youtube.py", "type": "script"},
            {"time": "21:00", "label": "Place Watch", "cmd": "scrapers/scraper_live_naver.py", "type": "script"},
            {"time": "21:30", "label": "TikTok", "cmd": "scrapers/scraper_tiktok_monitor.py", "type": "script"},
            {"time": "03:00", "label": "Pathfinder", "cmd": "pathfinder.py", "args": ["--legion", "10000"], "type": "daemon"},
            # [5단계] 주간 리포트 (일요일 20:00)
            {"time": "20:00", "label": "Weekly Report", "cmd": "insight_manager.py", "args": ["--mode", "weekly"], "type": "script", "day_of_week": 6}
        ]
        
        self.last_run = self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f: return json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load scheduler state: {e}")
        return {}

    def _save_state(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.last_run, f, indent=2)

    def run_task(self, task):
        label = task['label']
        cmd_path = os.path.join(self.root_dir, task['cmd'])
        args = task.get('args', [])

        logging.info(f"🚀 Starting Task: {label}")
        print(f"\n[{datetime.now().strftime('%H:%M')}] 🚀 Executing: {label}")

        full_cmd = [self.python_exe, cmd_path] + args

        try:
            if task['type'] == 'daemon':
                # 수정안 4: daemon 로그 파일로 리디렉션
                log_filename = label.lower().replace(' ', '_') + '_daemon.log'
                log_path = os.path.join(LOG_DIR, log_filename)
                log_file = open(log_path, 'a', encoding='utf-8')

                # Launch and forget (background)
                # Use DETACHED_PROCESS flags on Windows
                creation_flags = 0x00000008 | 0x00000200 if sys.platform == 'win32' else 0
                subprocess.Popen(
                    full_cmd,
                    creationflags=creation_flags,
                    shell=False,
                    stdout=log_file,
                    stderr=log_file
                )
                logging.info(f"✅ Daemon Launched: {label} (log: {log_path})")
            else:
                # Run and wait (foreground script)
                subprocess.run(full_cmd, check=True, timeout=600)
                logging.info(f"✅ Task Completed: {label}")
                
            # Update State
            self.last_run[task['time']] = datetime.now().strftime("%Y-%m-%d")
            self._save_state()
            
        except Exception as e:
            logging.error(f"❌ Task Failed ({label}): {e}")

    def start(self):
        print("\nChronos Scheduler is disabled.")
        print("Use Codex natural-language commands to run Pathfinder, Viral Hunter, or reports on demand.\n")
        logging.info("Chronos Scheduler disabled; exiting.")
        return

        print(f"\n⏳ Chronos Scheduler Initiated. Monitoring {len(self.timeline)} events.")
        print("   Keep this window open for automatic marketing execution.\n")
        
        while True:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today = now.strftime("%Y-%m-%d")
            
            for task in self.timeline:
                target_time = task['time']

                # [5단계] 요일 체크 (day_of_week가 있으면 해당 요일에만 실행)
                if 'day_of_week' in task:
                    if now.weekday() != task['day_of_week']:
                        continue

                # Check if matches current minute AND hasn't run today
                if current_time == target_time:
                    last_run_date = self.last_run.get(target_time)
                    if last_run_date != today:
                        self.run_task(task)
            
            time.sleep(30) # Check every 30s

if __name__ == "__main__":
    try:
        scheduler = ChronosScheduler()
        scheduler.start()
    except KeyboardInterrupt:
        print("\n🛑 Scheduler Stopped.")
