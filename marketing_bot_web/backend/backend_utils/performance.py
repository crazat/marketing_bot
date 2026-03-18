"""
성능 모니터링 유틸리티
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API 응답 시간, DB 쿼리 시간 측정 및 로깅
"""

import time
import logging
import threading
from typing import Any, Callable, Dict, Optional
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """단일 성능 메트릭"""
    name: str
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceMonitor:
    """
    성능 모니터링 싱글톤

    사용법:
        monitor = PerformanceMonitor()

        # API 응답 시간 측정
        with monitor.measure("api_get_metrics"):
            result = await get_metrics()

        # 통계 조회
        stats = monitor.get_stats()
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._metrics: Dict[str, list] = defaultdict(list)
        self._metrics_lock = threading.Lock()
        self._max_metrics_per_endpoint = 100  # 엔드포인트당 최대 저장 개수
        self._slow_threshold_ms = 500  # 느린 응답 임계값 (ms)
        self._initialized = True

    class _MeasureContext:
        """측정 컨텍스트 매니저"""
        def __init__(self, monitor: 'PerformanceMonitor', name: str, metadata: Optional[Dict] = None):
            self.monitor = monitor
            self.name = name
            self.metadata = metadata or {}
            self.start_time = None

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = (time.perf_counter() - self.start_time) * 1000  # ms
            success = exc_type is None

            metric = PerformanceMetric(
                name=self.name,
                duration_ms=round(duration, 2),
                success=success,
                metadata=self.metadata
            )

            self.monitor._record(metric)

            # 느린 응답 경고
            if duration > self.monitor._slow_threshold_ms:
                logger.warning(f"🐢 느린 응답: {self.name} ({duration:.0f}ms)")

            return False  # 예외 전파

    def measure(self, name: str, metadata: Optional[Dict] = None):
        """측정 컨텍스트 시작"""
        return self._MeasureContext(self, name, metadata)

    def _record(self, metric: PerformanceMetric):
        """메트릭 기록"""
        with self._metrics_lock:
            metrics_list = self._metrics[metric.name]
            metrics_list.append(metric)

            # 최대 개수 초과 시 오래된 것 제거
            if len(metrics_list) > self._max_metrics_per_endpoint:
                self._metrics[metric.name] = metrics_list[-self._max_metrics_per_endpoint:]

    def get_stats(self, name: Optional[str] = None) -> Dict[str, Any]:
        """통계 조회"""
        with self._metrics_lock:
            if name:
                return self._calculate_stats(name, self._metrics.get(name, []))

            result = {}
            for endpoint_name, metrics in self._metrics.items():
                result[endpoint_name] = self._calculate_stats(endpoint_name, metrics)

            return result

    def _calculate_stats(self, name: str, metrics: list) -> Dict[str, Any]:
        """통계 계산"""
        if not metrics:
            return {"name": name, "count": 0}

        durations = [m.duration_ms for m in metrics]
        success_count = sum(1 for m in metrics if m.success)

        return {
            "name": name,
            "count": len(metrics),
            "success_rate": round(success_count / len(metrics) * 100, 1),
            "avg_ms": round(sum(durations) / len(durations), 1),
            "min_ms": round(min(durations), 1),
            "max_ms": round(max(durations), 1),
            "p95_ms": round(sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0], 1),
            "slow_count": sum(1 for d in durations if d > self._slow_threshold_ms)
        }

    def get_slow_endpoints(self, threshold_ms: Optional[float] = None) -> list:
        """느린 엔드포인트 목록"""
        threshold = threshold_ms or self._slow_threshold_ms
        slow = []

        with self._metrics_lock:
            for name, metrics in self._metrics.items():
                if metrics:
                    avg = sum(m.duration_ms for m in metrics) / len(metrics)
                    if avg > threshold:
                        slow.append({"name": name, "avg_ms": round(avg, 1)})

        return sorted(slow, key=lambda x: x["avg_ms"], reverse=True)

    def clear(self):
        """메트릭 초기화"""
        with self._metrics_lock:
            self._metrics.clear()


# 글로벌 인스턴스
_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """성능 모니터 싱글톤 반환"""
    return _monitor


def timed(name: Optional[str] = None):
    """
    함수 실행 시간 측정 데코레이터

    Usage:
        @timed("get_metrics")
        async def get_metrics():
            ...
    """
    def decorator(func: Callable) -> Callable:
        metric_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with _monitor.measure(metric_name):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with _monitor.measure(metric_name):
                return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def log_db_query(query: str, duration_ms: float, params: Optional[tuple] = None):
    """DB 쿼리 로깅"""
    # 쿼리 요약 (첫 50자)
    query_summary = query.strip()[:50].replace('\n', ' ')

    if duration_ms > 100:  # 100ms 이상
        logger.warning(f"🐌 느린 쿼리 ({duration_ms:.0f}ms): {query_summary}...")
    else:
        logger.debug(f"DB 쿼리 ({duration_ms:.1f}ms): {query_summary}...")

    _monitor._record(PerformanceMetric(
        name="db_query",
        duration_ms=duration_ms,
        metadata={"query": query_summary}
    ))
