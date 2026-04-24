"""[L1/L2] Marketing Bot 공용 유틸리티.

여러 파일에 중복된 보일러플레이트를 한 곳에 통합:
- sys.path 초기화 (루트 + backend 추가)
- matched_keywords JSON 파싱
- 공용 타임스탬프 변환 등
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, List


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "marketing_bot_web" / "backend"


def ensure_paths() -> None:
    """[L1] sys.path에 프로젝트 루트와 backend를 1회 추가.

    14+ 곳에 복붙된 `sys.path.insert(...)` 패턴을 대체.
    멱등 (여러 번 호출해도 중복 삽입 없음).
    """
    root = str(PROJECT_ROOT)
    backend = str(BACKEND_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    if backend not in sys.path and BACKEND_DIR.exists():
        sys.path.insert(0, backend)


def parse_matched_keywords(value: Any) -> List[str]:
    """[L2] matched_keywords JSON 파싱 공용 함수.

    viral_targets.matched_keywords 컬럼은 JSON 문자열 또는 list로 존재.
    여러 파일에 반복된 `json.loads(...); except: []` 패턴을 대체.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if x]
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
            if isinstance(parsed, str):
                return [parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            # 쉼표로 구분된 문자열 폴백
            return [t.strip() for t in value.split(',') if t.strip()]
    return []


def safe_close(conn) -> None:
    """[C2] DB 연결을 안전하게 닫기 (예외 무시).

    try/finally 블록에서 반복되는 `try: conn.close() except: pass` 대체.
    """
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass
