import json
import os
import threading
from datetime import datetime

class TaskManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TaskManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(self.root_dir, 'db', 'tasks.json')
        
        # Ensure DB dir exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Load tasks from file if exists
        self.tasks = self._load_tasks()
        
        self._initialized = True
        # logger.info("TaskManager Initialized (Persistent Mode)") # logger causing import loops sometimes

    def _load_tasks(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert keys back to string if needed (JSON does this by default)
                    return data
            except json.JSONDecodeError:
                # Corrupted file handling
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak_path = f"{self.db_path}.{timestamp}.bak"
                
                print(f"[WARNING] Tasks DB corrupted. Renaming to {bak_path}")
                try:
                    os.rename(self.db_path, bak_path)
                    
                    # [Robustness] Attempt to recover from latest .bak if exists
                    # Find backup files pattern: tasks.json.*.bak
                    # This logic is simple: just look for the most recent bak that is NOT the one we just made
                    # implementation omitted for brevity, just reset safe for now but at least we save the bad one
                except Exception as e:
                    print(f"Error handling corrupted DB: {e}")
                
                return {} # Return empty for fresh start
            except Exception as e:
                # Other IO errors
                print(f"Error loading tasks DB: {e}")
                return {}
        return {}

    def _save_tasks(self):
        try:
            with self._lock:
                # [Robustness] Atomic Write Pattern
                # 1. Write to tmp file
                tmp_path = f"{self.db_path}.tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.tasks, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno()) # Force write to disk
                
                # 2. Rename tmp to real (Atomic on POSIX and modern Windows)
                os.replace(tmp_path, self.db_path)
        except Exception as e:
            # logger might be risky here if recursive, print is safer for core IO failure
            print(f"Failed to save tasks (Atomic Write Failed): {e}")

    def run_task(self, name, command_list):
        import subprocess
        import uuid
        
        task_id = str(uuid.uuid4())[:8]
        
        task_info = {
            "id": task_id,
            "name": name,
            "command": " ".join(command_list),
            "status": "Running",
            "start_time": str(datetime.now()),
            "end_time": None,
            "pid": None,
            "logs": [],
            "return_code": None
        }
        self.tasks[task_id] = task_info
        self._save_tasks()
        
        # Run in separate thread
        t = threading.Thread(target=self._worker, args=(task_id, command_list))
        t.daemon = True
        t.start()
        
        return task_id

    def _worker(self, task_id, command_list):
        import subprocess
        import time
        
        try:
            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1
            )
            
            # [Robustness] Save PID immediately
            self.tasks[task_id]["pid"] = process.pid
            self._save_tasks()
            
            last_save_time = time.time()
            # Buffer logs in memory, save only every 3.0 seconds
            
            for line in process.stdout:
                self.tasks[task_id]["logs"].append(line)
                
                # [Phase 4 Optimization] 
                # Throttle disk writes to prevent Dropbox Sync Lock / IO Bottleneck
                current_time = time.time()
                if current_time - last_save_time > 3.0:
                    self._save_tasks()
                    last_save_time = current_time
                    
            process.wait()
            
            # Final Save
            self.tasks[task_id]["status"] = "Completed" if process.returncode == 0 else "Failed"
            self.tasks[task_id]["return_code"] = process.returncode
            self.tasks[task_id]["end_time"] = str(datetime.now())
            self._save_tasks()
            
        except Exception as e:
            self.tasks[task_id]["status"] = "Error"
            self.tasks[task_id]["logs"].append(f"Execution Exception: {e}")
            self._save_tasks()

    def get_task(self, task_id):
        # Reload to get updates from other processes? 
        # Actually TaskManager is usually 'Writer' (Scheduler) or 'Reader' (Dashboard).
        # Dashboard should RELOAD every time.
        self.tasks = self._load_tasks() 
        return self.tasks.get(task_id)

    def get_all_tasks(self):
        self.tasks = self._load_tasks()
        # Return list sorted by start_time desc
        return sorted(self.tasks.values(), key=lambda x: x['start_time'], reverse=True)

    def stop_task(self, task_id):
        """Stops a running task by killing its process tree."""
        task = self.tasks.get(task_id)
        if not task or task['status'] not in ['Running', 'Pending']:
            return False
            
        pid = task.get('pid')
        if pid:
            import psutil
            try:
                parent = psutil.Process(pid)
                # Kill children first (e.g. chromedriver started by python)
                for child in parent.children(recursive=True):
                    try: child.kill() 
                    except: pass
                parent.kill()
                
                task['status'] = 'Stopped'
                task['end_time'] = str(datetime.now())
                self.tasks[task_id] = task
                self._save_tasks()
                return True
            except psutil.NoSuchProcess:
                # Already dead
                task['status'] = 'Failed (Ghost)'
                self._save_tasks()
                return False
            except Exception as e:
                print(f"Failed to stop task {task_id}: {e}")
                return False
        return False
