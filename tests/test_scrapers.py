"""
Scraper Tests for Marketing Bot
Tests scraper patterns and basic functionality without actual network calls.
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScraperPatterns(unittest.TestCase):
    """Tests for scraper code patterns to ensure robustness."""
    
    def test_cafe_spy_has_driver_cleanup(self):
        """Verify cafe_spy.py has proper driver cleanup pattern."""
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'scrapers', 'cafe_spy.py'
        )
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for safe cleanup pattern
        self.assertIn('driver.quit()', content)
        self.assertIn('self.driver = None', content)
        # Check that bare except is not used
        self.assertNotIn('except:\n', content)
    
    def test_scraper_naver_place_has_try_finally(self):
        """Verify scraper_naver_place.py has try-finally for driver."""
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'scrapers', 'scraper_naver_place.py'
        )
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('try:', content)
        self.assertIn('finally:', content)
        self.assertIn('driver.quit()', content)
    
    def test_scraper_live_naver_has_timeout(self):
        """Verify scraper_live_naver.py sets page load timeout."""
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'scrapers', 'scraper_live_naver.py'
        )
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('set_page_load_timeout', content)
    
    def test_no_bare_except_in_scrapers(self):
        """Ensure no bare except blocks in main scrapers."""
        scraper_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'scrapers'
        )
        
        files_to_check = [
            'cafe_spy.py',
            'scraper_naver_place.py',
            'scraper_live_naver.py',
            'scraper_competitor.py'
        ]
        
        for filename in files_to_check:
            filepath = os.path.join(scraper_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Check that bare "except:" (with colon and newline) is not present
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped == 'except:':
                        self.fail(f"{filename} line {i+1} has bare except block")


class TestConfigValidation(unittest.TestCase):
    """Tests for config validation functionality."""
    
    def test_validate_returns_dict(self):
        """Test that validate() returns proper structure."""
        from utils import ConfigManager
        config = ConfigManager()
        result = config.validate()
        
        self.assertIsInstance(result, dict)
        self.assertIn('valid', result)
        self.assertIn('missing', result)
        self.assertIn('warnings', result)
    
    def test_validate_with_mock_env(self):
        """Test validation with mocked environment variables."""
        from utils import ConfigManager
        
        with patch.dict(os.environ, {
            'GEMINI_API_KEY': 'test_key',
            'GOOGLE_API_KEY': 'test_key'
        }):
            config = ConfigManager()
            result = config.validate()
            self.assertTrue(result['valid'])
            self.assertEqual(len(result['missing']), 0)


class TestRetryHelperIntegration(unittest.TestCase):
    """Tests for retry_helper module integration."""
    
    def test_safe_selenium_driver_exists(self):
        """Verify SafeSeleniumDriver class is available."""
        from retry_helper import SafeSeleniumDriver
        self.assertTrue(callable(SafeSeleniumDriver))
    
    def test_safe_subprocess_exists(self):
        """Verify safe_subprocess function is available."""
        from retry_helper import safe_subprocess
        self.assertTrue(callable(safe_subprocess))
    
    def test_circuit_breaker_exists(self):
        """Verify CircuitBreaker class is available."""
        from retry_helper import CircuitBreaker
        breaker = CircuitBreaker(name="test")
        self.assertEqual(breaker.state, "CLOSED")


class TestHTMLParsing(unittest.TestCase):
    """Tests for HTML parsing logic used in scrapers."""
    
    def test_beautifulsoup_import(self):
        """Verify BeautifulSoup is available for parsing."""
        from bs4 import BeautifulSoup
        html = "<html><body><div class='test'>Hello</div></body></html>"
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(soup.find('div', class_='test').text, 'Hello')
    
    def test_view_search_link_extraction(self):
        """Test that link extraction logic works with sample HTML."""
        from bs4 import BeautifulSoup
        
        # Simulate Naver View search result structure
        sample_html = '''
        <li class="bx">
            <a class="title_link" href="https://blog.example.com/123">Test Blog Title</a>
            <div class="dsc_link">This is a description</div>
            <span class="sub">2026.01.18</span>
            <span class="name">TestBlogger</span>
        </li>
        '''
        soup = BeautifulSoup(sample_html, 'html.parser')
        item = soup.find('li', class_='bx')
        
        title_el = item.select_one('.title_link')
        self.assertIsNotNone(title_el)
        self.assertEqual(title_el.text, 'Test Blog Title')
        self.assertEqual(title_el['href'], 'https://blog.example.com/123')
    
    def test_place_search_rank_detection(self):
        """Test rank detection logic for Naver Place results."""
        # Simulate place list items
        sample_items = [
            "다른한의원 청주 리뷰 100개 500m",
            "규림한의원 청주 리뷰 50개 300m",  # Target at rank 2
            "또다른한의원 리뷰 30개 1km"
        ]
        
        target_name = "규림한의원"
        found_rank = 0
        
        for idx, text in enumerate(sample_items):
            if "리뷰" in text or "m" in text:
                if target_name in text:
                    found_rank = idx + 1
                    break
        
        self.assertEqual(found_rank, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
