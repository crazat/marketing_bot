
import sqlite3
import json
import os
import glob
from datetime import datetime
from utils import ConfigManager

class Librarian:
    """
    The Librarian manages the long-term memory of the system.
    It indexes reports and provides context for new queries.
    """
    def __init__(self):
        self.config = ConfigManager()
        self.db_path = self.config.db_path
        self.root_dir = self.config.root_dir

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def index_report(self, file_path, doc_type, summary=None, keywords=None):
        """
        Adds a file to the knowledge index.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Determine title from filename
        title = os.path.basename(file_path).replace(".md", "").replace("_", " ")
        
        # If summary/keywords missing, in a real app we would use LLM to generating them here.
        # For this prototype, we assume they are passed or basic extraction.
        if not summary:
            # Simple read first 3 lines
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    summary = "".join(lines[:3]).strip()
            except Exception:
                summary = "No summary available."
        
        kw_json = json.dumps(keywords if keywords else [])
        
        try:
            cursor.execute("""
            INSERT INTO knowledge_index (source_file, doc_type, title, summary, keywords) 
            VALUES (?, ?, ?, ?, ?)
            """, (file_path, doc_type, title, summary, kw_json))
            conn.commit()
            print(f"📚 Librarian indexed: {title}")
        except sqlite3.IntegrityError:
            # Update existing?
            print(f"📚 Librarian: File already indexed ({title})")
        
        conn.close()

    def search_knowledge(self, query):
        """
        Simple keyword search in title and summary.
        In modern RAG, this would use vector embeddings.
        """
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Simple LIKE query for prototype
        like_query = f"%{query}%"
        cursor.execute("""
        SELECT title, summary, created_at, source_file 
        FROM knowledge_index 
        WHERE title LIKE ? OR summary LIKE ? OR keywords LIKE ?
        ORDER BY created_at DESC LIMIT 3
        """, (like_query, like_query, like_query))
        
        rows = cursor.fetchall()
        results = []
        for r in rows:
            results.append(f"- [{r['created_at'][:10]}] {r['title']}: {r['summary']}")
            
        conn.close()
        
        if results:
            return "\n".join(results)
        else:
            return "관련된 과거 기록이 없습니다."

    def build_context_string(self, user_query):
        """
        Generates the 'Context' block to be injected into LLM prompt.
        """
        known_facts = self.search_knowledge(user_query)
        if "관련된 과거 기록이 없습니다" in known_facts:
            return ""
        
        return f"""
[Librarian Memory]
사용자의 질문과 관련된 과거 리포트 요약입니다. 답변 시 참고하세요.
{known_facts}
"""

if __name__ == "__main__":
    # Test
    lib = Librarian()
    print("Librarian initialized.")
