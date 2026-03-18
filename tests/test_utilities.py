"""
Tests for new utility modules: db_backup, api_tracker
"""
import pytest
import os
import sys
import tempfile
import sqlite3

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDatabaseBackup:
    """Tests for db_backup.py module"""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing"""
        path = str(tmp_path / "test.db")
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT INTO test (name) VALUES ('test1')")
        conn.commit()
        conn.close()
        return path
    
    def test_integrity_check(self, temp_db, monkeypatch):
        """Test database integrity check"""
        from db_backup import DatabaseBackup
        
        backup = DatabaseBackup()
        # Override db_path for testing
        monkeypatch.setattr(backup, 'db_path', temp_db)
        
        result = backup.check_integrity()
        assert result == True
    
    def test_wal_mode_enable(self, temp_db, monkeypatch):
        """Test WAL mode activation"""
        from db_backup import DatabaseBackup
        
        backup = DatabaseBackup()
        monkeypatch.setattr(backup, 'db_path', temp_db)
        
        result = backup.enable_wal_mode()
        assert result == True
        
        # Verify WAL mode is active
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        
        assert mode.lower() == 'wal'
    
    def test_backup_creation(self, temp_db, monkeypatch, tmp_path):
        """Test backup file creation"""
        from db_backup import DatabaseBackup
        
        backup = DatabaseBackup()
        monkeypatch.setattr(backup, 'db_path', temp_db)
        monkeypatch.setattr(backup, 'backup_dir', str(tmp_path / 'backups'))
        os.makedirs(backup.backup_dir, exist_ok=True)
        
        backup_path = backup.create_backup()
        
        assert backup_path is not None
        assert os.path.exists(backup_path)
        assert backup_path.endswith('.db')


class TestAPITracker:
    """Tests for api_tracker.py module"""
    
    @pytest.fixture
    def temp_tracker_db(self):
        """Create a temporary database for tracker"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)
    
    def test_log_call(self, temp_tracker_db, monkeypatch):
        """Test API call logging"""
        from api_tracker import APIUsageTracker
        
        # Mock the db_path
        tracker = APIUsageTracker()
        tracker.db_path = temp_tracker_db
        tracker._ensure_table()
        
        # Log a call
        tracker.log_call('gemini', 'test_endpoint', tokens=100, success=True)
        
        # Verify it was logged
        conn = sqlite3.connect(temp_tracker_db)
        cursor = conn.cursor()
        cursor.execute("SELECT api_name, tokens_used, success FROM api_usage")
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == 'gemini'
        assert row[1] == 100
        assert row[2] == 1
    
    def test_daily_count(self, temp_tracker_db):
        """Test daily call count"""
        from api_tracker import APIUsageTracker
        
        tracker = APIUsageTracker()
        tracker.db_path = temp_tracker_db
        tracker._ensure_table()
        
        # Log multiple calls
        tracker.log_call('naver_search', 'blog/test1')
        tracker.log_call('naver_search', 'blog/test2')
        tracker.log_call('gemini', 'generate')
        
        # Check counts
        naver_count = tracker.get_daily_count('naver_search')
        gemini_count = tracker.get_daily_count('gemini')
        
        assert naver_count == 2
        assert gemini_count == 1
    
    def test_daily_stats(self, temp_tracker_db):
        """Test daily statistics aggregation"""
        from api_tracker import APIUsageTracker
        
        tracker = APIUsageTracker()
        tracker.db_path = temp_tracker_db
        tracker._ensure_table()
        
        # Log calls
        tracker.log_call('gemini', 'test', tokens=500, success=True)
        tracker.log_call('gemini', 'test', tokens=300, success=False, error='test error')
        
        stats = tracker.get_daily_stats()
        
        assert 'gemini' in stats
        assert stats['gemini']['calls'] == 2
        assert stats['gemini']['tokens'] == 800
        assert stats['gemini']['failures'] == 1


class TestCodeQuality:
    """Tests to verify code quality improvements"""
    
    def test_no_hardcoded_paths_in_cafe_spy(self):
        """Verify ChromeDriver path is not hardcoded"""
        cafe_spy_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scrapers', 'cafe_spy.py'
        )
        
        with open(cafe_spy_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Should not contain old hardcoded path
        assert r'C:\Users\craza\.wdm\drivers' not in content
        assert 'CHROMEDRIVER_PATH' in content or 'ChromeDriverManager' in content
    
    def test_no_duplicate_imports_in_cafe_spy(self):
        """Verify no duplicate imports in cafe_spy.py"""
        cafe_spy_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scrapers', 'cafe_spy.py'
        )
        
        with open(cafe_spy_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Count import statements
        import_lines = [l.strip() for l in lines[:30] if l.strip().startswith('import ')]
        
        # No exact duplicates
        assert len(import_lines) == len(set(import_lines))


class TestPromptManager:
    """Tests for PromptManager and BatchProcessor"""
    
    def test_prompt_manager_load(self):
        """Test PromptManager loads prompts correctly"""
        from prompt_manager import PromptManager
        
        pm = PromptManager()
        prompts = pm.list_prompts()
        
        # Should have expected categories
        assert 'cafe_spy' in prompts
        assert 'content_generation' in prompts
        assert 'sentinel' in prompts
    
    def test_prompt_manager_get(self):
        """Test PromptManager.get() with variable substitution"""
        from prompt_manager import PromptManager
        
        pm = PromptManager()
        result = pm.get('cafe_spy', 'lead_analysis',
                       title='테스트 제목',
                       author='테스트 작성자',
                       body='테스트 본문')
        
        assert 'prompt' in result
        assert 'temperature' in result
        assert 'model_preference' in result
        assert '테스트 제목' in result['prompt']
    
    def test_prompt_manager_missing_prompt(self):
        """Test PromptManager handles missing prompts gracefully"""
        from prompt_manager import PromptManager
        
        pm = PromptManager()
        result = pm.get('nonexistent', 'category')
        
        assert 'prompt' in result
        assert 'Missing prompt' in result['prompt']
    
    def test_batch_processor_init(self):
        """Test BatchProcessor initialization"""
        from prompt_manager import BatchProcessor
        
        processor = BatchProcessor(batch_size=5)
        
        assert processor.batch_size == 5
        assert processor.prompt_manager is not None
    
    def test_batch_processor_format_leads(self):
        """Test lead formatting for batch processing"""
        from prompt_manager import BatchProcessor
        
        processor = BatchProcessor()
        
        leads = [
            {'title': 'Test 1', 'author': 'Author1', 'body': 'Body 1'},
            {'title': 'Test 2', 'author': 'Author2', 'body': 'Body 2'}
        ]
        
        formatted = processor._format_leads(leads)
        
        assert '[LEAD 1]' in formatted
        assert '[LEAD 2]' in formatted
        assert 'Test 1' in formatted
        assert 'Test 2' in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
