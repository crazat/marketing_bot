"""
프로젝트 경로 설정 유틸리티
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[코드 품질 개선] 중복 경로 설정 코드 제거
- 모든 라우터/서비스에서 이 모듈을 import하여 경로 설정
- 자동으로 프로젝트 루트 및 backend 디렉토리를 sys.path에 추가

사용법:
    # 라우터 파일 상단에서
    import setup_paths  # 이 한 줄로 경로 설정 완료

    # 또는 명시적으로
    from setup_paths import PROJECT_ROOT, BACKEND_DIR
"""

import os
import sys
from pathlib import Path

# 경로 계산
BACKEND_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = BACKEND_DIR.parent.parent.resolve()

# 경로를 sys.path에 추가 (중복 방지)
_paths_to_add = [
    str(PROJECT_ROOT),
    str(BACKEND_DIR),
]

for _path in _paths_to_add:
    if _path not in sys.path:
        sys.path.insert(0, _path)

# 편의용 경로 상수
CONFIG_DIR = PROJECT_ROOT / 'config'
DB_DIR = PROJECT_ROOT / 'db'
LOGS_DIR = PROJECT_ROOT / 'logs'
SCRAPERS_DIR = PROJECT_ROOT / 'scrapers'


def get_project_root() -> Path:
    """프로젝트 루트 경로 반환"""
    return PROJECT_ROOT


def get_config_path(filename: str) -> Path:
    """설정 파일 경로 반환"""
    return CONFIG_DIR / filename


def get_db_path(filename: str = 'marketing_data.db') -> Path:
    """데이터베이스 파일 경로 반환"""
    if filename == 'marketing_data.db':
        override = os.getenv('MARKETING_BOT_DB_PATH') or os.getenv('APP_DB_PATH')
        if override:
            return Path(override)
    return DB_DIR / filename


def get_log_path(filename: str) -> Path:
    """로그 파일 경로 반환"""
    LOGS_DIR.mkdir(exist_ok=True)
    return LOGS_DIR / filename


# [Phase 8] 설정 로드 헬퍼 함수
import json
from typing import Dict, Any, Optional

_config_cache: Dict[str, Any] = {}


def load_config(filename: str = 'config.json', use_cache: bool = True) -> Dict[str, Any]:
    """
    설정 파일 로드 (캐싱 지원)

    Args:
        filename: 설정 파일명 (기본 config.json)
        use_cache: 캐시 사용 여부 (기본 True)

    Returns:
        설정 딕셔너리

    Raises:
        FileNotFoundError: 파일이 없을 때
        json.JSONDecodeError: JSON 파싱 오류
    """
    if use_cache and filename in _config_cache:
        return _config_cache[filename]

    config_path = get_config_path(filename)
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if use_cache:
        _config_cache[filename] = config

    return config


def get_api_key(service: str) -> Optional[str]:
    """
    API 키 조회 헬퍼

    Args:
        service: 서비스명 (gemini, naver 등)

    Returns:
        API 키 또는 None
    """
    try:
        config = load_config()
        return config.get('api_keys', {}).get(service)
    except Exception:
        return None


def clear_config_cache():
    """설정 캐시 클리어 (설정 파일 수정 후 호출)"""
    _config_cache.clear()
