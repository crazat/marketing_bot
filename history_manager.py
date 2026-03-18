import sqlite3
import json
import os
import glob
from datetime import datetime
from utils import ConfigManager

class HistoryManager:
    def __init__(self):
        self.config = ConfigManager()
        self.db_path = self.config.db_path
        self.root_dir = self.config.root_dir

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # --- Chat Persistence ---
    def create_session(self, title=None):
        if not title:
            title = f"New Session ({datetime.now().strftime('%m-%d %H:%M')})"
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_sessions (title) VALUES (?)", (title,))
        conn.commit()
        session_id = cursor.lastrowid
        conn.close()
        return session_id

    def save_message(self, session_id, role, content, meta=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        meta_json = json.dumps(meta) if meta else None
        cursor.execute(
            "INSERT INTO chat_messages (session_id, role, content, meta_json) VALUES (?, ?, ?, ?)",
            (session_id, role, content, meta_json)
        )
        conn.commit()
        conn.close()

    def get_all_sessions(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at FROM chat_sessions ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_session_messages(self, session_id):
        conn = self.get_connection()
        # dict_factory
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
        rows = cursor.fetchall()
        
        messages = []
        for r in rows:
            meta = json.loads(r['meta_json']) if r['meta_json'] else None
            messages.append({
                "role": r['role'],
                "content": r['content'],
                "meta": meta
            })
        conn.close()
        return messages

    # --- File Archive ---
    def get_archived_files(self):
        """
        Scans reports directories and returns a structured dict.
        """
        archive = {}
        
        # Define categories and paths
        categories = {
            "🕵️ Competitor Reports": os.path.join(self.root_dir, 'reports_competitor'),
            "☕ Cafe Reports": os.path.join(self.root_dir, 'reports_cafe'),
            "📝 Blog Drafts": os.path.join(self.root_dir, 'reports_blog'),
            "📑 Strategy Reports": os.path.join(self.root_dir, 'reports_strategy')
        }
        
        for cat, path in categories.items():
            if os.path.exists(path):
                files = sorted(glob.glob(os.path.join(path, "*.md")), key=os.path.getmtime, reverse=True)
                file_list = []
                for f in files:
                    file_list.append({
                        "name": os.path.basename(f),
                        "path": f,
                        "time": datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M')
                    })
                if file_list:
                    archive[cat] = file_list
        
        return archive
