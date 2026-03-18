import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

class StatusManager:
    """
    Manages the real-time status of marketing bots.
    Used by the dashboard to show live state buttons (pulsing green, red error, etc).
    """
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to db/bot_status.db relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, 'bot_status.db')
        else:
            self.db_path = db_path
            
        self._init_db()

    def _init_db(self):
        """Initialize the status database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_activities (
                        bot_name TEXT PRIMARY KEY,
                        status TEXT DEFAULT 'IDLE',
                        current_task TEXT,
                        last_update TIMESTAMP
                    )
                """)
                # Pre-populate common bots if not exist
                bots = [
                    "Place Sniper", "Briefing", "Ambassador", "Cafe Swarm",
                    "Carrot Farm", "Instagram Monitor", "YouTube Monitor",
                    "Place Watch", "TikTok Monitor", "Pathfinder"
                ]
                for bot in bots:
                    conn.execute("""
                        INSERT OR IGNORE INTO bot_activities (bot_name, status, current_task, last_update)
                        VALUES (?, 'IDLE', 'Ready', ?)
                    """, (bot, datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            print(f"[StatusManager] Init Error: {e}")

    def update_status(self, bot_name: str, status: str, task_desc: str = ""):
        """
        Update the status of a specific bot.
        
        Args:
            bot_name: Name of the bot (e.g., "Place Sniper")
            status: 'IDLE', 'RUNNING', 'COMPLETED', 'ERROR'
            task_desc: Short description of current action
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO bot_activities (bot_name, status, current_task, last_update)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(bot_name) DO UPDATE SET
                        status = excluded.status,
                        current_task = excluded.current_task,
                        last_update = excluded.last_update
                """, (bot_name, status, task_desc, datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            print(f"[StatusManager] Update Error: {e}")

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all bot statuses for the dashboard.
        Returns: { 'Place Sniper': { 'status': 'RUNNING', ... }, ... }
        """
        results = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM bot_activities")
                rows = cursor.fetchall()
                for row in rows:
                    results[row['bot_name']] = dict(row)
        except Exception as e:
            print(f"[StatusManager] Read Error: {e}")
        return results

    def get_status(self, bot_name: str) -> Dict[str, Any]:
        """Get status for a single bot."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM bot_activities WHERE bot_name = ?", (bot_name,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            print(f"[StatusManager] Read One Error: {e}")
        return {}

# Singleton for easy import
status_manager = StatusManager()
