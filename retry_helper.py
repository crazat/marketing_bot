"""
Retry and Error Recovery Utilities for Marketing Bot.
Provides decorators and helpers for robust error handling.
"""
import time
import functools
import logging

logger = logging.getLogger("RetryHelper")

def retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0, exceptions=(Exception,)):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry
    
    Usage:
        @retry_with_backoff(max_retries=3, exceptions=(ConnectionError, TimeoutError))
        def fetch_data():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"[Retry {attempt + 1}/{max_retries}] {func.__name__} failed: {e}. Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"[Final Failure] {func.__name__} failed after {max_retries} retries: {e}")
            
            raise last_exception
        return wrapper
    return decorator


def with_fallback(fallback_value=None, fallback_func=None, exceptions=(Exception,)):
    """
    Decorator that provides a fallback value or function on failure.
    
    Args:
        fallback_value: Static value to return on failure
        fallback_func: Function to call on failure (receives exception as arg)
        exceptions: Tuple of exceptions to catch
    
    Usage:
        @with_fallback(fallback_value=[], exceptions=(TimeoutError,))
        def fetch_items():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.warning(f"[Fallback] {func.__name__} failed: {e}. Using fallback.")
                if fallback_func:
                    return fallback_func(e)
                return fallback_value
        return wrapper
    return decorator



# List of diverse User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36"
]

class SafeSeleniumDriver:
    """
    Context manager for safe Selenium driver operations.
    Ensures driver is properly closed even on exceptions.
    Now includes STEALTH MODE (Anti-Detection).
    
    Usage:
        with SafeSeleniumDriver() as driver:
            driver.get(url)
            ...
        
        # With mobile emulation
        with SafeSeleniumDriver(mobile=True) as driver:
            driver.get(url)
    """
    def __init__(self, headless=True, timeout=30, mobile=False, extra_options=None):
        self.headless = headless
        self.timeout = timeout
        self.mobile = mobile
        self.extra_options = extra_options or []
        self.driver = None
    
    def __enter__(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        import random
        
        options = Options()
        if self.headless:
            options.add_argument("--headless")
            
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled") # Key Anti-Bot flag
        
        # [Stealth 1] Random User-Agent
        ua = random.choice(USER_AGENTS)
        options.add_argument(f"user-agent={ua}")
        
        # [Stealth 2] Exclude automation switches
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Mobile emulation support
        if self.mobile:
            mobile_emulation = {"deviceName": "iPhone X"}
            options.add_experimental_option("mobileEmulation", mobile_emulation)
        
        # Apply extra options
        for opt in self.extra_options:
            options.add_argument(opt)
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), 
            options=options
        )
        
        # [Stealth 3] Remove navigator.webdriver flag via CDP
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.implicitly_wait(10)  # 요소 찾을 때 최대 10초 대기
        return self.driver
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")
        return False  # Don't suppress exceptions


class CircuitBreaker:
    """
    Circuit Breaker pattern for preventing cascade failures.
    
    When failures exceed threshold, the circuit opens and blocks
    further calls for a cooldown period.
    
    Usage:
        breaker = CircuitBreaker(threshold=3, reset_after=300)
        
        if breaker.is_open():
            return fallback_value
            
        try:
            result = risky_operation()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
    """
    def __init__(self, name="default", threshold=3, reset_after=300):
        self.name = name
        self.threshold = threshold
        self.reset_after = reset_after  # seconds
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def is_open(self):
        """Check if circuit is open (blocking calls)."""
        if self.state == "OPEN":
            # Check if enough time has passed for reset
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.reset_after:
                    self.state = "HALF_OPEN"
                    logger.info(f"[CircuitBreaker:{self.name}] State changed to HALF_OPEN")
                    return False
            return True
        return False
    
    def record_success(self):
        """Record a successful call."""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failures = 0
            logger.info(f"[CircuitBreaker:{self.name}] Circuit CLOSED after recovery")
        self.failures = max(0, self.failures - 1)  # Gradually reduce failure count
    
    def record_failure(self):
        """Record a failed call."""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.threshold:
            self.state = "OPEN"
            logger.warning(f"[CircuitBreaker:{self.name}] Circuit OPEN after {self.failures} failures")
    
    def get_status(self):
        """Get current circuit status."""
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "threshold": self.threshold
        }


def safe_subprocess(cmd, timeout=300, cwd=None, capture=True):
    """
    Execute subprocess with timeout and error handling.
    
    Args:
        cmd: Command as list (e.g., ["python", "script.py"])
        timeout: Timeout in seconds (default: 5 minutes)
        cwd: Working directory
        capture: Whether to capture output
        
    Returns:
        dict: {"success": bool, "stdout": str, "stderr": str, "returncode": int}
    """
    import subprocess
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding='utf-8',
            errors='replace', # [Robustness] Prevent crash on non-utf8 chars (Windows CP949 etc)
            timeout=timeout,
            cwd=cwd
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout if capture else "",
            "stderr": result.stderr if capture else "",
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Subprocess timeout ({timeout}s): {' '.join(cmd)}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Timeout after {timeout} seconds",
            "returncode": -1
        }
    except Exception as e:
        logger.error(f"Subprocess error: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }


def safe_request(url, timeout=10, retries=3):
    """
    Make a safe HTTP request with retries.

    Returns:
        Response object or None on failure
    """
    import requests

    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if attempt < retries - 1:
                logger.warning(f"Request to {url} failed (attempt {attempt + 1}): {e}")
                time.sleep(1 * (attempt + 1))
            else:
                logger.error(f"Request to {url} failed after {retries} attempts: {e}")
                return None


def parallel_execute(tasks, max_workers=5, delay_between_starts=0.5, show_progress=True):
    """
    [성능 최적화] 안전한 병렬 실행 유틸리티

    네이버 차단 방지를 위해 작업 시작 간 딜레이를 적용합니다.

    Args:
        tasks: [(func, args, kwargs), ...] 형태의 작업 목록
        max_workers: 동시 실행할 최대 작업자 수
        delay_between_starts: 작업 시작 간 딜레이 (초)
        show_progress: 진행률 표시 여부

    Returns:
        [(task_index, result_or_exception), ...] 형태의 결과 목록

    Usage:
        def fetch_url(url):
            return requests.get(url).text

        tasks = [(fetch_url, (url,), {}) for url in urls]
        results = parallel_execute(tasks, max_workers=3, delay_between_starts=1.0)

        for idx, result in results:
            if isinstance(result, Exception):
                print(f"Task {idx} failed: {result}")
            else:
                print(f"Task {idx}: {len(result)} chars")
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    results = []
    total = len(tasks)
    completed = 0
    lock = threading.Lock()

    def execute_task(index, func, args, kwargs):
        nonlocal completed
        try:
            result = func(*args, **kwargs)
            return index, result
        except Exception as e:
            logger.warning(f"Task {index} failed: {e}")
            return index, e
        finally:
            with lock:
                completed += 1
                if show_progress and completed % 5 == 0:
                    print(f"   진행: {completed}/{total}...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, (func, args, kwargs) in enumerate(tasks):
            future = executor.submit(execute_task, i, func, args, kwargs or {})
            futures.append(future)

            # 작업 시작 간 딜레이 (차단 방지)
            if delay_between_starts > 0 and i < len(tasks) - 1:
                time.sleep(delay_between_starts)

        for future in as_completed(futures):
            results.append(future.result())

    # 인덱스 순으로 정렬
    results.sort(key=lambda x: x[0])
    return results


def batch_process(items, process_func, batch_size=10, delay_between_batches=2.0):
    """
    [성능 최적화] 배치 처리 유틸리티

    대량 데이터를 배치로 나누어 처리하며, 배치 간 딜레이를 적용합니다.

    Args:
        items: 처리할 항목 목록
        process_func: 배치를 처리할 함수 (batch -> results)
        batch_size: 배치 크기
        delay_between_batches: 배치 간 딜레이 (초)

    Returns:
        모든 배치의 결과를 합친 리스트

    Usage:
        def process_batch(keywords):
            return [analyze(kw) for kw in keywords]

        results = batch_process(all_keywords, process_batch, batch_size=20)
    """
    all_results = []
    total_batches = (len(items) + batch_size - 1) // batch_size

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_num = i // batch_size + 1

        try:
            results = process_func(batch)
            all_results.extend(results if isinstance(results, list) else [results])
            logger.debug(f"Batch {batch_num}/{total_batches} completed: {len(batch)} items")
        except Exception as e:
            logger.error(f"Batch {batch_num}/{total_batches} failed: {e}")

        # 마지막 배치가 아니면 딜레이
        if i + batch_size < len(items) and delay_between_batches > 0:
            time.sleep(delay_between_batches)

    return all_results


if __name__ == "__main__":
    # Test the retry decorator
    @retry_with_backoff(max_retries=2, initial_delay=0.5)
    def test_function():
        raise ConnectionError("Test error")
    
    try:
        test_function()
    except ConnectionError:
        print("✅ Retry helper working correctly - caught after retries")
    
    # Test Circuit Breaker
    breaker = CircuitBreaker(name="test", threshold=2, reset_after=1)
    print(f"Initial state: {breaker.get_status()}")
    breaker.record_failure()
    breaker.record_failure()
    print(f"After 2 failures: {breaker.get_status()}")
    print(f"Is open: {breaker.is_open()}")
    print("✅ Circuit breaker working correctly")
