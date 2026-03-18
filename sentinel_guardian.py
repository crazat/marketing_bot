"""
Sentinel Guardian v2.0 - Enhanced Process Watchdog
===================================================
Features:
- Process monitoring with auto-restart
- Telegram crash alerts
- Crash pattern analysis
- Daily health reports
- Resource monitoring (memory/CPU)
"""

import subprocess
import time
import sys
import os
import datetime
import json
import psutil

# Add project root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class SentinelGuardian:
    """
    Enhanced watchdog for background processes.
    """
    
    def __init__(self):
        self.target_script = "background_runner.py"
        self.log_file = "guardian_crash.log"
        self.stats_file = "guardian_stats.json"
        self.retries = 0
        self.max_retries = 10
        self.cycle_interval = 21600  # 6 hours
        
        # Load or initialize stats
        self.stats = self._load_stats()
        
        # Try to import alert system
        try:
            from alert_bot import AlertSystem
            self.alert = AlertSystem()
            self.alerts_enabled = True
        except:
            self.alert = None
            self.alerts_enabled = False
    
    def _load_stats(self):
        """Load guardian statistics"""
        default_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'crashes': 0,
            'last_crash': None,
            'last_success': None,
            'crash_patterns': {},
            'started_at': datetime.datetime.now().isoformat()
        }
        
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return default_stats
    
    def _save_stats(self):
        """Save guardian statistics"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Failed to save stats: {e}")
    
    def log(self, msg, level="INFO"):
        """Log message to file and console"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {msg}"
        
        print(log_line)
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
    def send_alert(self, msg, is_critical=False):
        """Send Telegram alert if enabled"""
        if self.alerts_enabled and self.alert:
            try:
                prefix = "[CRITICAL]" if is_critical else "[Guardian]"
                self.alert.bot.send_message(f"{prefix} {msg}")
            except:
                pass
    
    def get_system_resources(self):
        """Get current system resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'disk_percent': disk.percent
            }
        except:
            return None
    
    def analyze_crash(self, error_output):
        """Analyze crash pattern and update statistics"""
        # Common error patterns
        patterns = {
            'memory_error': ['MemoryError', 'Out of memory'],
            'timeout_error': ['TimeoutError', 'Timeout', 'timed out'],
            'network_error': ['ConnectionError', 'URLError', 'Network'],
            'selenium_error': ['WebDriverException', 'selenium'],
            'api_error': ['APIError', 'RateLimitError', 'QuotaExceeded'],
            'database_error': ['sqlite3', 'database is locked']
        }
        
        detected_pattern = 'unknown_error'
        error_str = str(error_output).lower()
        
        for pattern_name, keywords in patterns.items():
            if any(kw.lower() in error_str for kw in keywords):
                detected_pattern = pattern_name
                break
        
        # Update pattern statistics
        if detected_pattern not in self.stats['crash_patterns']:
            self.stats['crash_patterns'][detected_pattern] = 0
        self.stats['crash_patterns'][detected_pattern] += 1
        
        return detected_pattern
    
    def generate_health_report(self):
        """Generate daily health report"""
        uptime_start = datetime.datetime.fromisoformat(self.stats['started_at'])
        uptime = datetime.datetime.now() - uptime_start
        
        success_rate = 0
        if self.stats['total_runs'] > 0:
            success_rate = round(self.stats['successful_runs'] / self.stats['total_runs'] * 100, 1)
        
        resources = self.get_system_resources()
        
        report = f"""
=== Guardian Health Report ===
Time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
Uptime: {uptime.days}d {uptime.seconds//3600}h
Total Runs: {self.stats['total_runs']}
Success Rate: {success_rate}%
Crashes: {self.stats['crashes']}
"""
        if resources:
            report += f"""
--- System Resources ---
CPU: {resources['cpu_percent']}%
Memory: {resources['memory_percent']}% ({resources['memory_available_gb']} GB free)
Disk: {resources['disk_percent']}%
"""
        if self.stats['crash_patterns']:
            report += "\n--- Crash Patterns ---\n"
            for pattern, count in sorted(self.stats['crash_patterns'].items(), key=lambda x: -x[1]):
                report += f"  {pattern}: {count}\n"
        
        return report
    
    def run_once(self):
        """Run target script once and handle result"""
        self.stats['total_runs'] += 1
        start_time = time.time()
        
        try:
            self.log(f"Launching: {self.target_script}")
            
            result = subprocess.run(
                [sys.executable, self.target_script],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour max
            )
            
            duration = round(time.time() - start_time, 1)
            
            if result.returncode == 0:
                self.stats['successful_runs'] += 1
                self.stats['last_success'] = datetime.datetime.now().isoformat()
                self.retries = 0
                self.log(f"Completed successfully in {duration}s")
                return True
            else:
                raise subprocess.CalledProcessError(result.returncode, self.target_script, result.stderr)
                
        except subprocess.TimeoutExpired:
            self.handle_crash("Process timeout (>1 hour)", "timeout_error")
            return False
            
        except subprocess.CalledProcessError as e:
            self.handle_crash(f"Exit code {e.returncode}: {e.stderr[:200] if e.stderr else 'No output'}", str(e.stderr))
            return False
            
        except Exception as e:
            self.handle_crash(str(e), str(e))
            return False
    
    def handle_crash(self, error_msg, error_output):
        """Handle crash: log, analyze, alert"""
        self.stats['crashes'] += 1
        self.stats['last_crash'] = datetime.datetime.now().isoformat()
        self.retries += 1
        
        # Analyze crash pattern
        pattern = self.analyze_crash(error_output)
        
        self.log(f"CRASH [{pattern}]: {error_msg[:100]}", level="ERROR")
        
        # Send alert
        alert_msg = f"Worker crashed!\nPattern: {pattern}\nRetry: {self.retries}/{self.max_retries}\n{error_msg[:100]}"
        self.send_alert(alert_msg, is_critical=(self.retries >= self.max_retries - 2))
        
        self._save_stats()
    
    def run_forever(self):
        """Main loop: run target, sleep, repeat"""
        self.log("=" * 50)
        self.log("Sentinel Guardian v2.0 Activated")
        self.log(f"Watching: {self.target_script}")
        self.log(f"Cycle interval: {self.cycle_interval}s ({self.cycle_interval//3600}h)")
        self.log(f"Alerts: {'Enabled' if self.alerts_enabled else 'Disabled'}")
        self.log("=" * 50)
        
        # Send startup alert
        self.send_alert("Guardian started. Monitoring active.")
        
        last_health_report = datetime.datetime.now()
        
        while True:
            try:
                # Run the worker
                success = self.run_once()
                
                # Check if we should send health report (every 24 hours)
                if (datetime.datetime.now() - last_health_report).total_seconds() > 86400:
                    report = self.generate_health_report()
                    self.log(report)
                    self.send_alert(f"Daily Health Report\nSuccess Rate: {self.stats.get('successful_runs', 0)}/{self.stats.get('total_runs', 0)}")
                    last_health_report = datetime.datetime.now()
                
                # Handle retries
                if not success:
                    if self.retries > self.max_retries:
                        self.log("CRITICAL: Max retries exceeded. Stopping.", level="CRITICAL")
                        self.send_alert("CRITICAL: Max retries exceeded. Guardian stopping.", is_critical=True)
                        break
                    
                    # Exponential backoff
                    wait_time = min(300, 2 ** self.retries)
                    self.log(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    # Success - wait for next cycle
                    self.log(f"Sleeping for {self.cycle_interval//3600} hours...")
                    time.sleep(self.cycle_interval)
                
                self._save_stats()
                
            except KeyboardInterrupt:
                self.log("Guardian stopped by user")
                self.send_alert("Guardian stopped by user.")
                break
                
            except Exception as e:
                self.log(f"Guardian internal error: {e}", level="ERROR")
                time.sleep(60)


def log_crash(msg):
    """Legacy function for backward compatibility"""
    with open("guardian_crash.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] {msg}\n")


def run_forever():
    """Legacy function - now uses SentinelGuardian class"""
    guardian = SentinelGuardian()
    guardian.run_forever()


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    guardian = SentinelGuardian()
    
    # If --report flag, just print health report
    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        print(guardian.generate_health_report())
    else:
        guardian.run_forever()
