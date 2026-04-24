"""
WebSocket Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

실시간 업데이트를 위한 WebSocket 관리

[고도화 B-5] 이벤트 타입별 채널 시스템 추가
- 클라이언트가 관심 이벤트만 구독 가능
- scan_progress, rank_update, alert, review_detected 등 세분화된 채널
"""

from typing import List, Dict, Any, Set, Optional
from fastapi import WebSocket
from datetime import datetime
import json
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

# 지원하는 이벤트 타입
EVENT_TYPES = {
    "hud_update",           # 대시보드 메트릭 업데이트
    "scan_progress",        # 스캔 진행률 (Place Sniper, Pathfinder 등)
    "scan_complete",        # 스캔 완료
    "rank_update",          # 개별 키워드 순위 변동
    "rank_alert",           # 순위 급변 알림 (3위 이상 변동)
    "new_lead",             # 새 리드 발견
    "review_detected",      # 새 리뷰 감지
    "review_response_draft",# 리뷰 응답 초안 생성됨
    "viral_target_update",  # 바이럴 타겟 업데이트
    "scheduler_status",     # 스케줄러 상태
    "competitor_change",    # 경쟁사 변경 감지
    "alert",                # 일반 알림
    "pathfinder_progress",  # Pathfinder 진행률
    "pathfinder_complete",  # Pathfinder 완료
    "pathfinder_log",       # Pathfinder 실시간 로그
    "pathfinder_status",    # Pathfinder 상태
}


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # [성능 최적화] 마지막 활동 시간 추적 (좀비 연결 감지용)
        self._last_activity: Dict[WebSocket, float] = {}
        self._cleanup_task: asyncio.Task = None
        self._zombie_timeout = 300  # 5분 무응답 시 좀비 연결로 간주
        # [고도화 B-5] 클라이언트별 구독 채널
        self._subscriptions: Dict[WebSocket, Set[str]] = {}

    async def connect(self, websocket: WebSocket):
        """클라이언트 연결"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self._last_activity[websocket] = time.time()
        # [고도화 B-5] 기본적으로 모든 이벤트 구독
        self._subscriptions[websocket] = set(EVENT_TYPES)
        logger.info(f"✅ WebSocket 클라이언트 연결 (총 {len(self.active_connections)}개)")

        # 첫 연결 시 cleanup 태스크 시작
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def disconnect(self, websocket: WebSocket):
        """클라이언트 연결 해제"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        # [성능 최적화] 활동 시간 추적 정리
        self._last_activity.pop(websocket, None)
        # [고도화 B-5] 구독 정보 정리
        self._subscriptions.pop(websocket, None)
        logger.info(f"❌ WebSocket 클라이언트 연결 해제 (총 {len(self.active_connections)}개)")

    def subscribe(self, websocket: WebSocket, event_types: List[str]):
        """[고도화 B-5] 클라이언트가 특정 이벤트만 구독"""
        valid_types = set(event_types) & EVENT_TYPES
        if websocket in self._subscriptions:
            self._subscriptions[websocket] = valid_types

    def unsubscribe(self, websocket: WebSocket, event_types: List[str]):
        """[고도화 B-5] 특정 이벤트 구독 해제"""
        if websocket in self._subscriptions:
            self._subscriptions[websocket] -= set(event_types)

    async def send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """특정 클라이언트에게 메시지 전송"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"메시지 전송 실패: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """
        모든 연결된 클라이언트에게 브로드캐스트

        [고도화 B-5] 이벤트 타입 기반 필터링:
        메시지에 'type' 필드가 있으면 해당 이벤트를 구독한 클라이언트에게만 전송
        """
        disconnected = []
        event_type = message.get('type', '')

        for connection in self.active_connections:
            # [고도화 B-5] 구독 필터링
            if event_type and connection in self._subscriptions:
                if event_type not in self._subscriptions[connection]:
                    continue

            try:
                await connection.send_json(message)
                # [성능 최적화] 성공 시 활동 시간 업데이트
                self._last_activity[connection] = time.time()
            except Exception as e:
                logger.debug(f"브로드캐스트 실패: {e}")
                disconnected.append(connection)

        # 연결 끊긴 클라이언트 제거
        for conn in disconnected:
            self.disconnect(conn)

    def update_activity(self, websocket: WebSocket):
        """[성능 최적화] 클라이언트 활동 시간 업데이트 (ping 수신 시)"""
        if websocket in self.active_connections:
            self._last_activity[websocket] = time.time()

    async def _periodic_cleanup(self):
        """
        [성능 최적화] 좀비 연결 정리 태스크
        - 5분 동안 무응답인 연결 감지 및 제거
        - 60초마다 체크
        """
        while self.active_connections:
            await asyncio.sleep(60)

            current_time = time.time()
            zombies = []

            for connection in self.active_connections:
                last_seen = self._last_activity.get(connection, current_time)
                if current_time - last_seen > self._zombie_timeout:
                    zombies.append(connection)
                    print(f"🧟 좀비 연결 감지 ({current_time - last_seen:.0f}초 무응답)")

            # 좀비 연결 정리
            for zombie in zombies:
                try:
                    await zombie.close()
                except Exception:
                    pass
                self.disconnect(zombie)

            if zombies:
                print(f"🧹 좀비 연결 {len(zombies)}개 정리됨")

    async def send_hud_update(self, data: Dict[str, Any]):
        """HUD 메트릭 업데이트 전송"""
        await self.broadcast({
            'type': 'hud_update',
            'data': data
        })

    async def send_pathfinder_progress(self, progress: int, message: str):
        """Pathfinder 진행 상황 전송"""
        await self.broadcast({
            'type': 'pathfinder_progress',
            'data': {
                'progress': progress,
                'message': message
            }
        })

    async def send_pathfinder_complete(self, stats: Dict[str, Any]):
        """Pathfinder 완료 전송"""
        await self.broadcast({
            'type': 'pathfinder_complete',
            'data': stats
        })

    async def send_ranking_update(self, keyword: str, rank: int):
        """순위 업데이트 전송"""
        await self.broadcast({
            'type': 'ranking_update',
            'data': {
                'keyword': keyword,
                'rank': rank
            }
        })

    async def send_new_lead(self, lead: Dict[str, Any]):
        """새 리드 발견 전송"""
        await self.broadcast({
            'type': 'new_lead',
            'data': lead
        })

    async def send_viral_target_update(self, target: Dict[str, Any]):
        """바이럴 타겟 업데이트 전송"""
        await self.broadcast({
            'type': 'viral_target_update',
            'data': target
        })

    async def send_scheduler_status(self, status: str, task: str):
        """스케줄러 상태 전송"""
        await self.broadcast({
            'type': 'scheduler_status',
            'data': {
                'status': status,
                'task': task
            }
        })

    async def send_pathfinder_log(self, line: str):
        """Pathfinder 실시간 로그 전송"""
        await self.broadcast({
            'type': 'pathfinder_log',
            'data': {
                'line': line,
                'timestamp': None  # 프론트엔드에서 현재 시간 사용
            }
        })

    async def send_pathfinder_status(self, status_data: dict):
        """Pathfinder 상태 전송 (running/completed/idle)"""
        await self.broadcast({
            'type': 'pathfinder_status',
            'data': status_data
        })

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [고도화 B-5] 새 이벤트 타입 메서드
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def send_scan_progress(self, module: str, progress: int, message: str,
                                  current: int = 0, total: int = 0):
        """스캔 진행률 전송 (Place Sniper, Pathfinder 등)"""
        await self.broadcast({
            'type': 'scan_progress',
            'data': {
                'module': module,
                'progress': progress,
                'message': message,
                'current': current,
                'total': total,
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def send_scan_complete(self, module: str, result: Dict[str, Any]):
        """스캔 완료 전송"""
        await self.broadcast({
            'type': 'scan_complete',
            'data': {
                'module': module,
                'result': result,
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def send_rank_alert(self, keyword: str, old_rank: int, new_rank: int,
                               device_type: str = "mobile"):
        """순위 급변 알림 (3위 이상 변동 시)"""
        change = old_rank - new_rank  # 양수면 상승
        await self.broadcast({
            'type': 'rank_alert',
            'data': {
                'keyword': keyword,
                'old_rank': old_rank,
                'new_rank': new_rank,
                'change': change,
                'direction': 'up' if change > 0 else 'down',
                'device_type': device_type,
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def send_review_detected(self, competitor_name: str, content_preview: str,
                                     sentiment: str = "neutral", star_rating: float = None):
        """새 리뷰 감지 전송"""
        await self.broadcast({
            'type': 'review_detected',
            'data': {
                'competitor_name': competitor_name,
                'content_preview': content_preview[:100],
                'sentiment': sentiment,
                'star_rating': star_rating,
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def send_review_response_draft(self, review_id: int, draft_preview: str):
        """리뷰 응답 초안 생성 알림"""
        await self.broadcast({
            'type': 'review_response_draft',
            'data': {
                'review_id': review_id,
                'draft_preview': draft_preview[:200],
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def send_competitor_change(self, competitor_name: str, change_type: str,
                                       details: str):
        """경쟁사 변경 감지 전송"""
        await self.broadcast({
            'type': 'competitor_change',
            'data': {
                'competitor_name': competitor_name,
                'change_type': change_type,
                'details': details,
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def send_alert(self, level: str, title: str, message: str,
                          action_url: str = None):
        """일반 알림 전송 (level: info, warning, critical)"""
        await self.broadcast({
            'type': 'alert',
            'data': {
                'level': level,
                'title': title,
                'message': message,
                'action_url': action_url,
                'timestamp': datetime.now().isoformat(),
            }
        })

    async def handle_client_message(self, websocket: WebSocket, data: Dict[str, Any]):
        """
        [고도화 B-5] 클라이언트 메시지 처리

        클라이언트가 보내는 메시지 형식:
        - {"action": "subscribe", "events": ["hud_update", "rank_alert"]}
        - {"action": "unsubscribe", "events": ["pathfinder_log"]}
        - {"action": "ping"}
        """
        action = data.get('action', '')

        if action == 'subscribe':
            events = data.get('events', [])
            self.subscribe(websocket, events)
            logger.debug(f"Client subscribed to: {events}")

        elif action == 'unsubscribe':
            events = data.get('events', [])
            self.unsubscribe(websocket, events)
            logger.debug(f"Client unsubscribed from: {events}")

        elif action == 'ping':
            self.update_activity(websocket)
            try:
                await websocket.send_json({'type': 'pong', 'data': {}})
            except Exception:
                pass


# 전역 WebSocket 매니저 인스턴스
ws_manager = WebSocketManager()
