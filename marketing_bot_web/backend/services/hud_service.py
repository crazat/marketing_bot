"""hud_service — hud.py(3376줄) 순수 함수·TTL 캐시 이관.

이관 대상:
- convert_to_kst: UTC→KST 변환
- get_scan_progress_from_log: 로그 파일에서 진행률 파싱
- TTLCache: 범용 TTL 캐시 클래스

hud.py는 FastAPI 라우터만 남기는 방향.
"""
from __future__ import annotations

import glob
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


def convert_to_kst(utc_timestamp: Optional[str]) -> Optional[str]:
    """UTC ISO → KST (+9h) 문자열. 실패 시 원본 반환.

    SQLite CURRENT_TIMESTAMP 형식 'YYYY-MM-DD HH:MM:SS' 지원.
    """
    if not utc_timestamp:
        return None
    try:
        dt = datetime.strptime(utc_timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
        return (dt + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError):
        return utc_timestamp


def parse_scan_progress_from_log(
    module_name: str,
    project_root: str,
) -> Dict[str, Any]:
    """로그 파일에서 모듈별 진행률 파싱.

    Pathfinder(PHASE 1~5), Place Sniper(N/M 키워드), 일반(%) 순으로 매칭.
    """
    log_dir = os.path.join(project_root, 'logs')

    if module_name == 'pathfinder' or module_name == 'pathfinder_legion':
        log_file = os.path.join(log_dir, 'pathfinder_live.log')
    else:
        pattern = f'{module_name}_*.log'
        files = glob.glob(os.path.join(log_dir, pattern))
        log_file = max(files, key=os.path.getmtime) if files else None

    if not log_file or not os.path.exists(log_file):
        return {"status": "idle", "progress": 0, "message": "대기 중"}

    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        if not lines:
            return {"status": "running", "progress": 0, "message": "시작 중..."}

        progress = 0
        message = ""
        for line in reversed(lines[-20:]):
            line = line.strip()
            if not line:
                continue
            if '키워드 수집 완료' in line or 'PHASE 5' in line:
                return {"status": "completed", "progress": 100, "message": "완료"}
            if 'PHASE' in line:
                m = re.search(r'PHASE (\d)', line)
                if m:
                    phase = int(m.group(1))
                    progress = min(phase * 20, 95)
                    message = line[:100]
                    break
            if '키워드 스캔' in line or '스캔 중' in line:
                m = re.search(r'(\d+)/(\d+)', line)
                if m:
                    cur, total = int(m.group(1)), int(m.group(2))
                    progress = int((cur / total) * 100) if total > 0 else 0
                    message = line[:100]
                    break
            if '%' in line:
                m = re.search(r'(\d+)%', line)
                if m:
                    progress = int(m.group(1))
                    message = line[:100]
                    break
            if not message and line:
                message = line[:100]
        return {"status": "running", "progress": progress, "message": message}
    except Exception as e:
        return {"status": "error", "progress": 0, "message": str(e)}


class TTLCache:
    """[T3] 간단한 TTL(Time-To-Live) 캐시 — 스레드 안전."""

    def __init__(self, ttl_seconds: int = 30):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            if time.time() - self._timestamps[key] > self.ttl:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
                return None
            return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
