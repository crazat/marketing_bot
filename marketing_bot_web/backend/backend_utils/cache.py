"""
API 응답 캐싱 유틸리티
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TTL 기반 인메모리 캐시로 DB 부하 감소
"""

import time
import hashlib
import json
import threading
import logging
from typing import Any, Optional, Callable, TypeVar
from functools import wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry:
    """캐시 엔트리"""
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)


class TTLCache:
    """
    TTL 기반 인메모리 캐시

    사용법:
        cache = TTLCache(default_ttl=60)  # 60초 TTL
        cache.set("key", "value")
        value = cache.get("key")
    """

    def __init__(self, default_ttl: int = 60, max_size: int = 1000):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """캐시에서 값 조회"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if time.time() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """캐시에 값 저장"""
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # 최대 크기 초과 시 만료된 항목 정리
            if len(self._cache) >= self.max_size:
                self._cleanup_expired()

            # 여전히 초과하면 가장 오래된 항목 제거
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k].created_at)
                del self._cache[oldest_key]

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> bool:
        """캐시에서 값 삭제"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """캐시 전체 비우기"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def invalidate_pattern(self, pattern: str) -> int:
        """패턴에 맞는 키 모두 삭제"""
        count = 0
        with self._lock:
            keys_to_delete = [k for k in self._cache if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
                count += 1
        return count

    def _cleanup_expired(self) -> None:
        """만료된 항목 정리 (lock 없이 - 호출자가 lock 보유)"""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if now > v.expires_at]
        for key in expired_keys:
            del self._cache[key]

    def get_stats(self) -> dict:
        """캐시 통계"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 1)
            }


# 글로벌 캐시 인스턴스
_api_cache = TTLCache(default_ttl=60, max_size=500)
_db_cache = TTLCache(default_ttl=300, max_size=200)


def get_api_cache() -> TTLCache:
    """API 응답 캐시 (짧은 TTL)"""
    return _api_cache


def get_db_cache() -> TTLCache:
    """DB 쿼리 캐시 (긴 TTL)"""
    return _db_cache


def cache_key(*args, **kwargs) -> str:
    """캐시 키 생성"""
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.md5(key_data.encode()).hexdigest()


def cached(ttl: int = 60, cache_instance: Optional[TTLCache] = None):
    """
    함수 결과 캐싱 데코레이터

    사용법:
        @cached(ttl=120)
        async def get_metrics():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache = cache_instance or _api_cache

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            key = f"{func.__module__}.{func.__name__}:{cache_key(*args, **kwargs)}"

            # 캐시 조회
            cached_value = cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {func.__name__}")
                return cached_value

            # 함수 실행 및 캐싱
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl)
            logger.debug(f"Cache SET: {func.__name__}")
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            key = f"{func.__module__}.{func.__name__}:{cache_key(*args, **kwargs)}"

            cached_value = cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {func.__name__}")
                return cached_value

            result = func(*args, **kwargs)
            cache.set(key, result, ttl)
            logger.debug(f"Cache SET: {func.__name__}")
            return result

        # async 함수인지 확인
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def invalidate_cache(pattern: str = "") -> dict:
    """캐시 무효화"""
    api_cleared = _api_cache.invalidate_pattern(pattern) if pattern else 0
    db_cleared = _db_cache.invalidate_pattern(pattern) if pattern else 0

    if not pattern:
        _api_cache.clear()
        _db_cache.clear()
        return {"cleared": "all"}

    return {"api_cleared": api_cleared, "db_cleared": db_cleared}


def get_cache_stats() -> dict:
    """전체 캐시 통계"""
    return {
        "api_cache": _api_cache.get_stats(),
        "db_cache": _db_cache.get_stats()
    }
