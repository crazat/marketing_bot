"""
Centralized Logging Configuration for Marketing Bot.
Provides unified logging across all modules with file rotation.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# [Phase 5-1] 설정값 외부화 - app_settings에서 로드
try:
    from config.app_settings import get_settings
    _settings = get_settings()
    DEFAULT_LOG_DIR = _settings.log_dir
    DEFAULT_LOG_LEVEL = getattr(logging, _settings.log_level.upper(), logging.INFO)
    MAX_LOG_SIZE = _settings.log_max_size_mb * 1024 * 1024
    BACKUP_COUNT = _settings.log_backup_count
except ImportError:
    # 설정 로드 실패 시 기본값 사용
    DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    DEFAULT_LOG_LEVEL = logging.INFO
    MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB
    BACKUP_COUNT = 5

# Ensure log directory exists
os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Add color to level name
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    RotatingFileHandler that catches PermissionError on Windows.
    Instead of crashing, it logs an error to stderr and continues without rotating.
    """
    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            # Common on Windows when file is locked. Lowering to stdout to keep stderr clean.
            sys.stdout.write(f"\n[INFO] Log rotation deferred (file busy): {os.path.basename(self.baseFilename)}\n")
        except Exception as e:
            sys.stderr.write(f"\n[ERROR] Log rotation failed: {e}\n")


def setup_logging(
    log_level=DEFAULT_LOG_LEVEL,
    log_dir=DEFAULT_LOG_DIR,
    console_output=True,
    file_output=True
):
    """
    Configure centralized logging for the entire application.
    
    Args:
        log_level: Minimum log level (default: INFO)
        log_dir: Directory for log files
        console_output: Enable console logging
        file_output: Enable file logging with rotation
    
    Usage:
        from logging_config import setup_logging
        setup_logging()
        
        # Then in any module:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("This will be logged properly")
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers = []
    
    # Format string
    log_format = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Console Handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        
        # Use colors on Windows if supported, plain format otherwise
        if sys.platform.startswith('win'):
            try:
                # Enable ANSI colors on Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                console_handler.setFormatter(ColoredFormatter(log_format, date_format))
            except Exception:
                # Windows 콘솔 색상 설정 실패 시 기본 포매터 사용
                console_handler.setFormatter(logging.Formatter(log_format, date_format))
        else:
            console_handler.setFormatter(ColoredFormatter(log_format, date_format))
        
        root_logger.addHandler(console_handler)
    
    # File Handler (Rotating)
    if file_output:
        os.makedirs(log_dir, exist_ok=True)
        
        # Main log file
        log_file = os.path.join(log_dir, 'marketing_bot.log')
        file_handler = SafeRotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(file_handler)
        
        # Error log file (only errors and above)
        error_log_file = os.path.join(log_dir, 'errors.log')
        error_handler = SafeRotatingFileHandler(
            error_log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(error_handler)
    
    # Suppress noisy loggers
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    
    # Enable DB Logging for critical errors
    add_db_logging(min_level=logging.ERROR)
    
    logging.info("Logging system initialized")
    return root_logger


def get_logger(name):
    """
    Get a logger with the specified name.
    Convenience function for consistent logger access.
    
    Usage:
        from logging_config import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)


# Database logging handler (optional)
class DatabaseLogHandler(logging.Handler):
    """
    Handler that writes log records to the SQLite database.
    Use for critical events that need to be tracked.
    """
    
    def __init__(self, db_path=None):
        super().__init__()
        self.db_path = db_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'db', 'marketing_data.db'
        )
        
    def emit(self, record):
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_logs (level, module, message, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                record.levelname,
                record.name,
                self.format(record),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass  # Fail silently for logging


def add_db_logging(min_level=logging.ERROR):
    """
    Add database logging for critical events.
    Only logs errors and above by default.
    """
    db_handler = DatabaseLogHandler()
    db_handler.setLevel(min_level)
    db_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(db_handler)


if __name__ == "__main__":
    # Test logging setup
    setup_logging(log_level=logging.DEBUG)
    
    logger = get_logger("TestModule")
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    print(f"\n✅ Logs written to: {DEFAULT_LOG_DIR}")
