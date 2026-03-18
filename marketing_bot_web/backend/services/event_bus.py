"""
Event Bus System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

모듈 간 이벤트 발행/구독 시스템
- 키워드 발굴, 리드 발견, 순위 변동 등 이벤트를 다른 모듈에서 구독
- 자동 연동 및 알림 트리거
"""

from typing import Dict, Any, List, Callable, Awaitable, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue
import asyncio
import threading
import logging

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """이벤트 타입 정의"""
    # 키워드 관련
    KEYWORD_DISCOVERED = "keyword.discovered"
    KEYWORD_APPROVED = "keyword.approved"
    KEYWORD_GRADE_CHANGED = "keyword.grade_changed"

    # 리드 관련
    LEAD_DISCOVERED = "lead.discovered"
    LEAD_HOT_DETECTED = "lead.hot_detected"
    LEAD_STATUS_CHANGED = "lead.status_changed"
    LEAD_CONVERTED = "lead.converted"

    # 순위 관련
    RANK_UPDATED = "rank.updated"
    RANK_IMPROVED = "rank.improved"
    RANK_DROPPED = "rank.dropped"
    RANK_TOP10_ENTERED = "rank.top10_entered"

    # 바이럴 관련
    VIRAL_TARGET_ADDED = "viral.target_added"
    VIRAL_COMMENT_COMPLETED = "viral.comment_completed"

    # 경쟁사 관련
    COMPETITOR_RANK_SURGE = "competitor.rank_surge"
    COMPETITOR_NEW_ENTRY = "competitor.new_entry"
    COMPETITOR_WEAKNESS_FOUND = "competitor.weakness_found"

    # 분석 관련
    ANALYTICS_ALERT = "analytics.alert"
    HEALTH_SCORE_CHANGED = "analytics.health_score_changed"


@dataclass
class Event:
    """이벤트 데이터 클래스"""
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


# 이벤트 핸들러 타입
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """이벤트 버스 싱글톤"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._subscribers: Dict[EventType, List[EventHandler]] = {}
        self._event_history: List[Event] = []
        self._max_history = 100
        # [안정성 개선] 구독자 딕셔너리 동시성 보호
        self._subscribers_lock = threading.Lock()

        # [안정성 개선] 동기 컨텍스트에서의 이벤트 처리를 위한 백그라운드 스레드
        self._sync_queue: Queue = Queue()
        self._sync_thread: Optional[threading.Thread] = None
        self._running = True
        self._start_sync_processor()

        self._initialized = True
        logger.info("EventBus 초기화 완료")

    def _start_sync_processor(self):
        """동기 컨텍스트에서 발생한 이벤트를 처리하는 백그라운드 스레드"""
        def process_sync_events():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            while self._running:
                try:
                    # 1초 타임아웃으로 큐에서 이벤트 가져오기
                    event = self._sync_queue.get(timeout=1.0)
                    if event is None:  # 종료 신호
                        break
                    # 이벤트 처리
                    loop.run_until_complete(self.publish(event))
                except Exception:
                    # Queue.Empty 또는 기타 예외 - 계속 대기
                    continue

            loop.close()
            logger.debug("EventBus 동기 프로세서 종료")

        self._sync_thread = threading.Thread(
            target=process_sync_events,
            daemon=True,
            name="EventBus-SyncProcessor"
        )
        self._sync_thread.start()
        logger.debug("EventBus 동기 프로세서 시작")

    def shutdown(self):
        """EventBus 종료 (서버 종료 시 호출)"""
        self._running = False
        self._sync_queue.put(None)  # 종료 신호
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        logger.info("EventBus 종료 완료")

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """이벤트 구독 (스레드 안전)"""
        with self._subscribers_lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(f"이벤트 구독 등록: {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """이벤트 구독 해제 (스레드 안전)"""
        with self._subscribers_lock:
            if event_type in self._subscribers:
                if handler in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(handler)
                    logger.debug(f"이벤트 구독 해제: {event_type.value}")

    async def publish(self, event: Event) -> None:
        """이벤트 발행"""
        # 히스토리 저장
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        logger.info(f"이벤트 발행: {event.type.value} | {event.data}")

        # 구독자들에게 전달 (스레드 안전하게 핸들러 목록 복사)
        with self._subscribers_lock:
            handlers = list(self._subscribers.get(event.type, []))
        if not handlers:
            logger.debug(f"구독자 없음: {event.type.value}")
            return

        # 비동기로 모든 핸들러 실행
        tasks = []
        for handler in handlers:
            tasks.append(self._safe_execute(handler, event))

        if tasks:
            await asyncio.gather(*tasks)

    async def _safe_execute(self, handler: EventHandler, event: Event) -> None:
        """핸들러 안전 실행 (예외 처리)"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"이벤트 핸들러 실행 오류: {event.type.value} | {e}")

    def emit(self, event_type: EventType, data: Dict[str, Any], source: str = "system") -> None:
        """
        동기 이벤트 발행 (Non-blocking)

        [안정성 개선] asyncio.run() 대신 백그라운드 스레드 사용
        - async 컨텍스트: loop.create_task() 사용
        - sync 컨텍스트: 큐에 넣고 백그라운드 스레드에서 처리
        """
        event = Event(type=event_type, data=data, source=source)

        try:
            loop = asyncio.get_running_loop()
            # async 컨텍스트 - 태스크로 실행
            loop.create_task(self.publish(event))
        except RuntimeError:
            # sync 컨텍스트 - 큐에 넣어서 백그라운드 스레드가 처리
            self._sync_queue.put(event)
            logger.debug(f"이벤트 큐에 추가 (sync): {event_type.value}")

    async def emit_async(self, event_type: EventType, data: Dict[str, Any], source: str = "system") -> None:
        """비동기 이벤트 발행"""
        event = Event(type=event_type, data=data, source=source)
        await self.publish(event)

    def get_recent_events(self, limit: int = 20, event_type: EventType = None) -> List[Dict[str, Any]]:
        """최근 이벤트 조회"""
        events = self._event_history

        if event_type:
            events = [e for e in events if e.type == event_type]

        return [e.to_dict() for e in events[-limit:]]

    def get_subscriber_count(self, event_type: EventType = None) -> Dict[str, int]:
        """구독자 수 조회"""
        if event_type:
            return {event_type.value: len(self._subscribers.get(event_type, []))}

        return {k.value: len(v) for k, v in self._subscribers.items()}


# 전역 이벤트 버스 인스턴스
event_bus = EventBus()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def on_event(event_type: EventType):
    """이벤트 핸들러 데코레이터"""
    def decorator(func: EventHandler):
        event_bus.subscribe(event_type, func)
        return func
    return decorator


async def emit_keyword_discovered(keyword: str, grade: str, source: str = "pathfinder"):
    """키워드 발굴 이벤트 발행"""
    await event_bus.emit_async(
        EventType.KEYWORD_DISCOVERED,
        {"keyword": keyword, "grade": grade},
        source
    )

    # S/A급인 경우 추가 이벤트
    if grade in ['S', 'A']:
        await event_bus.emit_async(
            EventType.KEYWORD_APPROVED,
            {"keyword": keyword, "grade": grade, "auto_approved": True},
            source
        )


async def emit_lead_discovered(lead_id: int, score: int, platform: str, keyword: str = None):
    """리드 발견 이벤트 발행"""
    await event_bus.emit_async(
        EventType.LEAD_DISCOVERED,
        {"lead_id": lead_id, "score": score, "platform": platform, "keyword": keyword},
        "lead_manager"
    )

    # Hot 리드인 경우 추가 이벤트
    if score >= 80:
        await event_bus.emit_async(
            EventType.LEAD_HOT_DETECTED,
            {"lead_id": lead_id, "score": score, "platform": platform, "keyword": keyword},
            "lead_manager"
        )


async def emit_rank_updated(keyword: str, new_rank: int, prev_rank: int = None):
    """순위 업데이트 이벤트 발행"""
    await event_bus.emit_async(
        EventType.RANK_UPDATED,
        {"keyword": keyword, "new_rank": new_rank, "prev_rank": prev_rank},
        "battle"
    )

    # 순위 변동 이벤트
    if prev_rank:
        if new_rank < prev_rank:
            await event_bus.emit_async(
                EventType.RANK_IMPROVED,
                {"keyword": keyword, "new_rank": new_rank, "prev_rank": prev_rank, "change": prev_rank - new_rank},
                "battle"
            )
        elif new_rank > prev_rank:
            await event_bus.emit_async(
                EventType.RANK_DROPPED,
                {"keyword": keyword, "new_rank": new_rank, "prev_rank": prev_rank, "change": new_rank - prev_rank},
                "battle"
            )

    # Top 10 진입 이벤트
    if new_rank <= 10 and (prev_rank is None or prev_rank > 10):
        await event_bus.emit_async(
            EventType.RANK_TOP10_ENTERED,
            {"keyword": keyword, "rank": new_rank},
            "battle"
        )


async def emit_competitor_alert(competitor: str, keyword: str, event_type: str, details: Dict[str, Any]):
    """경쟁사 알림 이벤트 발행"""
    if event_type == "rank_surge":
        await event_bus.emit_async(
            EventType.COMPETITOR_RANK_SURGE,
            {"competitor": competitor, "keyword": keyword, **details},
            "competitor"
        )
    elif event_type == "new_entry":
        await event_bus.emit_async(
            EventType.COMPETITOR_NEW_ENTRY,
            {"competitor": competitor, "keyword": keyword, **details},
            "competitor"
        )
