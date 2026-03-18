"""
Event Bus System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 2.1] 모듈 간 이벤트 기반 통신 시스템
- 이벤트 발행/구독 패턴
- 비동기 이벤트 처리
- 이벤트 이력 로깅
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import threading

logger = logging.getLogger(__name__)


class EventType(Enum):
    """시스템 이벤트 타입"""

    # 키워드 관련
    KEYWORD_DISCOVERED = "keyword.discovered"           # 새 키워드 발견
    KEYWORD_GRADED = "keyword.graded"                   # 키워드 등급 부여
    KEYWORD_ADDED_TO_TRACKING = "keyword.added"         # 추적 목록에 추가

    # 순위 관련
    RANK_CHECKED = "rank.checked"                       # 순위 확인 완료
    RANK_CHANGED = "rank.changed"                       # 순위 변동 감지
    RANK_DROPPED = "rank.dropped"                       # 순위 급락 (5위 이상)
    RANK_IMPROVED = "rank.improved"                     # 순위 상승

    # 경쟁사 관련
    COMPETITOR_REVIEW_COLLECTED = "competitor.review"   # 경쟁사 리뷰 수집
    COMPETITOR_WEAKNESS_DETECTED = "competitor.weakness"  # 약점 발견
    COMPETITOR_ACTIVITY_SPIKE = "competitor.activity"   # 활동량 급증

    # 리드 관련
    LEAD_DISCOVERED = "lead.discovered"                 # 새 리드 발견
    LEAD_SCORED = "lead.scored"                         # 리드 스코어링 완료
    LEAD_HOT = "lead.hot"                               # Hot Lead 감지
    LEAD_STATUS_CHANGED = "lead.status"                 # 리드 상태 변경

    # 바이럴 관련
    VIRAL_TARGET_FOUND = "viral.found"                  # 바이럴 타겟 발견
    VIRAL_COMMENT_GENERATED = "viral.comment"           # 댓글 생성 완료

    # 시스템 관련
    SCAN_STARTED = "scan.started"                       # 스캔 시작
    SCAN_COMPLETED = "scan.completed"                   # 스캔 완료
    SCAN_FAILED = "scan.failed"                         # 스캔 실패
    ALERT_SENT = "alert.sent"                           # 알림 전송됨

    # 스케줄 관련
    SCHEDULE_EXECUTED = "schedule.executed"             # 스케줄 실행됨
    SCHEDULE_FAILED = "schedule.failed"                 # 스케줄 실행 실패


@dataclass
class Event:
    """이벤트 데이터 구조"""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: datetime = None
    source: str = "system"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    """
    싱글톤 이벤트 버스
    모든 모듈에서 동일한 인스턴스를 공유
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

        self._handlers: Dict[EventType, List[Callable]] = {}
        self._async_handlers: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history = 1000
        self._db_logging = True
        self._initialized = True
        logger.info("EventBus initialized")

    def subscribe(self, event_type: EventType, handler: Callable):
        """
        동기 이벤트 핸들러 등록

        Args:
            event_type: 구독할 이벤트 타입
            handler: 이벤트 발생 시 호출될 함수 (event: Event) -> None
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug(f"Handler registered for {event_type.value}")

    def subscribe_async(self, event_type: EventType, handler: Callable):
        """
        비동기 이벤트 핸들러 등록

        Args:
            event_type: 구독할 이벤트 타입
            handler: async 이벤트 핸들러 (event: Event) -> None
        """
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = []

        if handler not in self._async_handlers[event_type]:
            self._async_handlers[event_type].append(handler)
            logger.debug(f"Async handler registered for {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """핸들러 등록 해제"""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

        if event_type in self._async_handlers and handler in self._async_handlers[event_type]:
            self._async_handlers[event_type].remove(handler)

    def publish(self, event: Event):
        """
        동기 이벤트 발행
        모든 등록된 핸들러를 순차적으로 호출
        """
        # 이력 저장
        self._add_to_history(event)

        # DB에 로깅
        if self._db_logging:
            self._log_to_db(event)

        # 동기 핸들러 호출
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.event_type.value}: {e}")

        logger.debug(f"Event published: {event.event_type.value} ({len(handlers)} handlers)")

    async def publish_async(self, event: Event):
        """
        비동기 이벤트 발행
        모든 등록된 핸들러를 동시에 호출
        """
        # 이력 저장
        self._add_to_history(event)

        # DB에 로깅
        if self._db_logging:
            self._log_to_db(event)

        # 동기 핸들러 먼저 호출
        sync_handlers = self._handlers.get(event.event_type, [])
        for handler in sync_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Sync handler error for {event.event_type.value}: {e}")

        # 비동기 핸들러 동시 호출
        async_handlers = self._async_handlers.get(event.event_type, [])
        if async_handlers:
            tasks = []
            for handler in async_handlers:
                tasks.append(self._safe_async_call(handler, event))
            await asyncio.gather(*tasks)

        logger.debug(f"Async event published: {event.event_type.value}")

    async def _safe_async_call(self, handler: Callable, event: Event):
        """안전한 비동기 핸들러 호출"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Async handler error for {event.event_type.value}: {e}")

    def _add_to_history(self, event: Event):
        """이벤트 이력에 추가"""
        self._event_history.append(event)

        # 최대 이력 초과 시 오래된 것 제거
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

    def _log_to_db(self, event: Event):
        """이벤트를 DB에 로깅"""
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            db.cursor.execute('''
                INSERT INTO events_log (event_type, payload, source, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                event.event_type.value,
                event.to_json(),
                event.source,
                event.timestamp.isoformat()
            ))
            db.conn.commit()
        except Exception as e:
            # DB 테이블이 없으면 무시 (마이그레이션 전)
            logger.debug(f"Event DB logging failed (table may not exist): {e}")

    def get_recent_events(
        self,
        event_type: EventType = None,
        limit: int = 100
    ) -> List[Event]:
        """최근 이벤트 조회"""
        events = self._event_history

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return events[-limit:]

    def get_event_stats(self) -> Dict[str, int]:
        """이벤트 타입별 통계"""
        stats = {}
        for event in self._event_history:
            type_name = event.event_type.value
            stats[type_name] = stats.get(type_name, 0) + 1
        return stats

    def clear_history(self):
        """이벤트 이력 초기화"""
        self._event_history = []


# 편의 함수
_event_bus = None

def get_event_bus() -> EventBus:
    """EventBus 싱글톤 인스턴스 반환"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def publish_event(
    event_type: EventType,
    data: Dict[str, Any],
    source: str = "system"
):
    """이벤트 발행 편의 함수"""
    event = Event(event_type=event_type, data=data, source=source)
    get_event_bus().publish(event)


async def publish_event_async(
    event_type: EventType,
    data: Dict[str, Any],
    source: str = "system"
):
    """비동기 이벤트 발행 편의 함수"""
    event = Event(event_type=event_type, data=data, source=source)
    await get_event_bus().publish_async(event)


def subscribe_event(event_type: EventType, handler: Callable):
    """이벤트 구독 편의 함수"""
    get_event_bus().subscribe(event_type, handler)


def subscribe_event_async(event_type: EventType, handler: Callable):
    """비동기 이벤트 구독 편의 함수"""
    get_event_bus().subscribe_async(event_type, handler)
